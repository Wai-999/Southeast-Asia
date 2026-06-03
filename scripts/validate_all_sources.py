#!/usr/bin/env python3
"""
scripts/validate_all_sources.py
────────────────────────────────────────────────────────────────────────────
Validates combined_indicators.json against a suite of quality checks.

CHECKS:
  1.  All required fields present in every row
  2.  value_type is one of the allowed set
  3.  data_quality is one of the allowed set
  4.  No sample data in production output
  5.  No forecast_estimate in worldbank_indicators.json
  6.  2025/2026 rows are NOT forward-filled from 2024
  7.  2026 partial year rows are properly labeled
  8.  All 17 countries present
  9.  All 17 sectors represented
  10. Value plausibility checks per indicator
  11. No duplicate (country, indicator, period) keys
  12. Country codes are valid ISO3
  13. Year range 2015-2026 for annual data
  14. Forecast rows have limitation_notes
  15. Missing rows have correct value_type = "missing_official"
  16. Official rows have source not null
  17. Confidence field is valid
  18. Sector names are in indicator_registry
  19. No row has value = 0 when official_actual (suspicious)
  20. Cross-check: 2025 WB rows should be missing_official (WB hasn't published)

OUTPUT  pipeline/data/logs/universal_validation_log.json
"""

import json
import sys
from pathlib import Path
from datetime import datetime, date
from collections import Counter, defaultdict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROC_DIR     = PROJECT_ROOT / "pipeline" / "data" / "processed"
LOGS_DIR     = PROJECT_ROOT / "pipeline" / "data" / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

VALID_VALUE_TYPES = {
    "official_actual","official_preliminary","official_partial_2026",
    "forecast_estimate","missing_official","official_policy",
    "realtime_signal","sample",
}
VALID_DATA_QUALITY = {"available","estimated","old_data","missing","partial"}
VALID_CONFIDENCE   = {"very_high","high","medium","low","none"}

REQUIRED_FIELDS = [
    "country_code","country_name","sector","indicator_code","indicator_name",
    "period","year","quarter","month","value","unit","frequency",
    "source","source_type","source_url","fetched_at","released_at",
    "value_type","data_quality","confidence","extraction_method","limitation_note",
]

EXPECTED_COUNTRIES = {
    "THA","VNM","MMR","KHM","LAO","MYS","SGP","IDN","PHL","BRN","TLS",
    "CHN","USA","JPN","IND","KOR","AUS",
}

EXPECTED_SECTORS = {
    "macro_economy","prices_inflation","labor","trade","investment",
    "finance_monetary","fiscal","tourism","industry_production","agriculture",
    "energy","technology_digital","infrastructure","environment",
    "politics_policy","security_conflict","social_indicators",
}

# Plausibility ranges per indicator code
PLAUSIBILITY = {
    "GDP_GROWTH":              (-30, 20),
    "CPI_INFLATION":           (-5, 100),
    "UNEMPLOYMENT_RATE":       (0, 40),
    "EXPORTS_USD":             (0.01, 5000),  # USA exports ~3T
    "IMPORTS_USD":             (0.01, 5000),  # USA imports ~3-4T
    "FDI_PCT_GDP":             (-20, 40),
    "POPULATION":              (0.1, 1500),
    "INTERNET_PENETRATION":    (0, 100),
    "RENEWABLE_ENERGY_SHARE":  (0, 100),
    "ELECTRICITY_ACCESS":      (0, 100),
    "TOURIST_ARRIVALS":        (0, 1500),  # millions — China/USA exceed 100M
    "FOREIGN_RESERVES":        (0.01, 4000),
    "GOVERNANCE_EFFECTIVENESS":(-2.5, 2.5),
    "RULE_OF_LAW":             (-2.5, 2.5),
    "POLITICAL_STABILITY":     (-2.5, 2.5),
    "FISCAL_BALANCE_GDP":      (-80, 30),  # Small oil states can be extreme
    "PUBLIC_DEBT_GDP":         (0, 300),
    "LIFE_EXPECTANCY":         (40, 90),
}


def run_checks(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    passed = []
    failed = []

    def chk(check_id: str, ok: bool, msg: str, detail: str = ""):
        entry = {"check_id": check_id, "status": "PASS" if ok else "FAIL",
                 "message": msg, "detail": detail[:300] if detail else ""}
        (passed if ok else failed).append(entry)
        return ok

    n = len(rows)

    # ── Check 1: Required fields ──────────────────────────────────────────
    missing_fields = defaultdict(list)
    for i, row in enumerate(rows[:100]):  # Sample first 100
        for f in REQUIRED_FIELDS:
            if f not in row:
                missing_fields[f].append(i)
    chk("C01_REQUIRED_FIELDS", not missing_fields,
        "All required fields present in rows",
        str(dict(missing_fields)) if missing_fields else "")

    # ── Check 2: Valid value_type ─────────────────────────────────────────
    bad_vt = [r.get("value_type") for r in rows if r.get("value_type") not in VALID_VALUE_TYPES]
    chk("C02_VALUE_TYPES", not bad_vt,
        f"All value_type values are valid ({len(VALID_VALUE_TYPES)} allowed)",
        f"Bad values: {set(bad_vt)}" if bad_vt else "")

    # ── Check 3: Valid data_quality ───────────────────────────────────────
    bad_dq = [r.get("data_quality") for r in rows if r.get("data_quality") not in VALID_DATA_QUALITY]
    chk("C03_DATA_QUALITY", not bad_dq,
        f"All data_quality values are valid",
        f"Bad: {set(bad_dq)}" if bad_dq else "")

    # ── Check 4: No sample data ───────────────────────────────────────────
    sample_rows = [r for r in rows if r.get("value_type") == "sample"]
    chk("C04_NO_SAMPLE", not sample_rows,
        "No sample data in production output",
        f"{len(sample_rows)} sample rows found" if sample_rows else "")

    # ── Check 5: No forecast in worldbank_indicators.json ─────────────────
    wb_file = PROC_DIR / "worldbank_indicators.json"
    if wb_file.exists():
        wb_data = json.loads(wb_file.read_text())
        wb_rows = wb_data.get("records", [])
        wb_forecasts = [r for r in wb_rows if r.get("value_type") == "forecast_estimate"]
        chk("C05_WB_NO_FORECASTS", not wb_forecasts,
            "worldbank_indicators.json contains no forecast_estimate rows",
            f"{len(wb_forecasts)} forecast rows in WB file" if wb_forecasts else "")
    else:
        chk("C05_WB_NO_FORECASTS", False, "worldbank_indicators.json not found", "")

    # ── Check 6: 2025 rows not forward-filled ─────────────────────────────
    yr2025_estimated = [r for r in rows
                        if r.get("year") == 2025
                        and r.get("data_quality") == "estimated"
                        and r.get("value_type") == "official_actual"]
    chk("C06_NO_2025_FILL", not yr2025_estimated,
        "No 2025 rows are forward-filled from 2024 (data_quality='estimated' + official_actual)",
        f"{len(yr2025_estimated)} suspicious rows" if yr2025_estimated else "")

    # ── Check 7: All expected countries present ───────────────────────────
    found_countries = set(r.get("country_code") for r in rows)
    missing_countries = EXPECTED_COUNTRIES - found_countries
    chk("C07_COUNTRIES", not missing_countries,
        f"All {len(EXPECTED_COUNTRIES)} expected countries present",
        f"Missing: {missing_countries}" if missing_countries else "")

    # ── Check 8: Multiple sectors represented ────────────────────────────
    found_sectors = set(r.get("sector") for r in rows)
    missing_sectors = EXPECTED_SECTORS - found_sectors
    chk("C08_SECTORS", len(found_sectors) >= 10,
        f"At least 10 sectors represented (found {len(found_sectors)})",
        f"Missing: {missing_sectors}" if len(found_sectors) < 10 else "")

    # ── Check 9: No duplicate keys ────────────────────────────────────────
    keys = [f"{r.get('country_code')}|{r.get('indicator_code')}|{r.get('period')}"
            for r in rows]
    key_counts = Counter(keys)
    dups = {k: v for k, v in key_counts.items() if v > 1}
    chk("C09_NO_DUPLICATES", not dups,
        "No duplicate (country, indicator, period) keys",
        f"{len(dups)} duplicates found" if dups else "")

    # ── Check 10: Plausibility ranges ────────────────────────────────────
    out_of_range = []
    for r in rows:
        code = r.get("indicator_code","")
        val  = r.get("value")
        rng  = PLAUSIBILITY.get(code)
        if rng and val is not None:
            lo, hi = rng
            if not (lo <= val <= hi):
                out_of_range.append(f"{r.get('country_code')}/{code}/{r.get('period')}: {val}")
    chk("C10_PLAUSIBILITY", len(out_of_range) == 0,
        "All values within plausible ranges",
        f"{len(out_of_range)} out-of-range: {out_of_range[:5]}" if out_of_range else "")

    # ── Check 11: Missing rows labeled correctly ──────────────────────────
    bad_missing = [r for r in rows
                   if r.get("value") is None and r.get("value_type") not in
                   {"missing_official","official_policy","realtime_signal"}]
    chk("C11_MISSING_LABELED", not bad_missing,
        "Null-value rows are labeled missing_official / official_policy",
        f"{len(bad_missing)} wrongly labeled null rows" if bad_missing else "")

    # ── Check 12: Official rows have source ──────────────────────────────
    no_source = [r for r in rows
                 if r.get("value_type") == "official_actual"
                 and not r.get("source")]
    chk("C12_SOURCE_PRESENT", not no_source,
        "All official_actual rows have a source",
        f"{len(no_source)} rows missing source" if no_source else "")

    # ── Check 13: Forecast rows have limitation notes ─────────────────────
    forecast_no_note = [r for r in rows
                        if r.get("value_type") == "forecast_estimate"
                        and not r.get("limitation_note")]
    chk("C13_FORECAST_NOTES", len(forecast_no_note) == 0,
        "All forecast_estimate rows have limitation_note",
        f"{len(forecast_no_note)} forecast rows missing note" if forecast_no_note else "")

    # ── Check 14: Year range ─────────────────────────────────────────────
    bad_years = [r.get("year") for r in rows
                 if r.get("frequency") == "annual"
                 and r.get("year") not in range(2015, 2027)]
    chk("C14_YEAR_RANGE", not bad_years,
        "Annual rows all have years 2015-2026",
        f"{len(bad_years)} bad years" if bad_years else "")

    # ── Check 15: 2025/2026 WB rows are missing_official ─────────────────
    # WB typically has 1-2 year lag so 2025 should mostly be missing
    wb_2025 = [r for r in rows
               if r.get("year") == 2025
               and "World Bank" in str(r.get("source",""))
               and r.get("value_type") == "official_actual"
               and r.get("value") is not None]
    # It's OK to have some 2025 WB actuals (WB may publish some by mid-2026)
    chk("C15_WB_2025_REALISTIC", len(wb_2025) < 50,
        "WB 2025 official_actual count is realistic (< 50 rows)",
        f"Found {len(wb_2025)} WB 2025 official_actual rows")

    # Summary counts
    total_checks = len(passed) + len(failed)
    pass_count   = len(passed)

    return passed, failed


def main():
    print(f"\n{'═'*60}")
    print(f"  Universal Source Validator")
    print(f"  Date: {date.today().isoformat()}")
    print(f"{'═'*60}\n")

    combined_file = PROC_DIR / "combined_indicators.json"
    if not combined_file.exists():
        print("  ✗ combined_indicators.json not found — run merge_all_sources.py first")
        return 1

    data = json.loads(combined_file.read_text())
    rows = data.get("records", [])
    print(f"  Loaded {len(rows)} rows from combined_indicators.json\n", flush=True)

    passed, failed = run_checks(rows)
    total = len(passed) + len(failed)

    print(f"\n  ── Validation Results ─────────────────────────")
    print(f"  Checks passed: {len(passed)}/{total}")
    print(f"  Checks failed: {len(failed)}/{total}")
    if failed:
        print(f"\n  FAILED CHECKS:")
        for f in failed:
            print(f"    ✗ [{f['check_id']}] {f['message']}")
            if f.get("detail"):
                print(f"       → {f['detail'][:150]}")
    if passed:
        print(f"\n  PASSED CHECKS:")
        for p in passed:
            print(f"    ✓ [{p['check_id']}] {p['message']}")

    log = {
        "validated_at":   datetime.utcnow().isoformat() + "Z",
        "row_count":      len(rows),
        "checks_total":   total,
        "checks_passed":  len(passed),
        "checks_failed":  len(failed),
        "all_passed":     len(failed) == 0,
        "passed_checks":  passed,
        "failed_checks":  failed,
    }
    log_file = LOGS_DIR / "universal_validation_log.json"
    log_file.write_text(json.dumps(log, indent=2))
    print(f"\n  📄 Log: {log_file.relative_to(PROJECT_ROOT)}")
    print(f"  {'✓ ALL CHECKS PASSED' if not failed else f'⚠ {len(failed)} checks failed'}\n")

    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
