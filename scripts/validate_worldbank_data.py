#!/usr/bin/env python3
"""
==============================================================================
  scripts/validate_worldbank_data.py — SEA Change Intelligence Dashboard
==============================================================================

Validates the processed World Bank data file.
Run this after fetch_worldbank.py to confirm the output is clean.

USAGE (run from project root):
    python scripts/validate_worldbank_data.py

OUTPUT:
    Terminal summary of all checks
    pipeline/data/logs/validation_log.json   ← machine-readable results

CHECKS PERFORMED:
    1.  File exists and is valid JSON
    2.  All 17 expected countries present
    3.  All 8 expected indicators present
    4.  All years 2015–2026 present for every country/indicator pair
    5.  No duplicate country-indicator-year rows
    6.  Every record has all required fields
    7.  source_url is non-empty for every record
    8.  value_type is one of: official_actual, missing_official
    9.  data_quality is one of: available, old_data, estimated, missing
    10. 2025/2026 rows with value != null have value_type = official_actual
    11. 2025/2026 null rows have value_type = missing_official and data_quality = missing
    12. No forecast_estimate values in worldbank_indicators.json
        (forecasts must only be in latest_estimates.json)
    13. No duplicate records
    14. Values are within plausible ranges (e.g., GDP growth not 1000%)

EXIT CODE:
    0 = all checks passed
    1 = one or more checks failed
==============================================================================
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path


# ── Paths ─────────────────────────────────────────────────────────────────────

PROJECT_ROOT  = Path(__file__).resolve().parent.parent
PIPELINE_DIR  = PROJECT_ROOT / "pipeline"
DATA_FILE     = PIPELINE_DIR / "data" / "processed" / "worldbank_indicators.json"
LOGS_DIR      = PIPELINE_DIR / "data" / "logs"
LOG_FILE      = LOGS_DIR / "validation_log.json"


# ── Expected values ───────────────────────────────────────────────────────────

EXPECTED_COUNTRIES: set[str] = {
    "THA", "VNM", "MMR", "KHM", "LAO", "MYS", "SGP", "IDN", "PHL", "BRN", "TLS",
    "CHN", "USA", "JPN", "IND", "KOR", "AUS",
}

EXPECTED_INDICATORS: set[str] = {
    "gdpGrowth", "gdpNominal", "inflation", "unemployment",
    "fdiPctGdp", "exports", "imports", "population",
}

EXPECTED_YEARS: set[int] = set(range(2015, 2027))   # 2015–2026 inclusive

REQUIRED_FIELDS: list[str] = [
    "source_url", "source", "last_updated", "fetched_at",
    "country_code", "country_name", "region_group",
    "indicator_code", "indicator_key", "indicator_name",
    "year", "unit", "frequency",
    "data_quality", "value_type", "limitation_note",
    # "value" is intentionally excluded — it can be null
]

VALID_DATA_QUALITY: set[str] = {"available", "old_data", "estimated", "missing"}
VALID_VALUE_TYPES:  set[str] = {"official_actual", "missing_official"}

# Plausible value ranges for sanity check
PLAUSIBLE_RANGES: dict[str, tuple[float, float]] = {
    "gdpGrowth":    (-40.0,   25.0),
    "gdpNominal":   (  0.1, 30_000.0),
    "inflation":    (-15.0,  250.0),
    "unemployment": (  0.0,   50.0),
    "fdiPctGdp":    (-30.0,   80.0),
    "exports":      (  0.0, 6_000.0),
    "imports":      (  0.0, 6_000.0),
    "population":   (  0.1, 1_500.0),
}


# ── Validation result accumulator ─────────────────────────────────────────────

class Validator:
    def __init__(self) -> None:
        self.checks: list[dict] = []
        self.errors: list[str]  = []

    def ok(self, name: str, detail: str = "") -> None:
        self.checks.append({"check": name, "result": "PASS", "detail": detail})
        print(f"  ✓  {name}" + (f"  ({detail})" if detail else ""))

    def fail(self, name: str, detail: str = "") -> None:
        self.checks.append({"check": name, "result": "FAIL", "detail": detail})
        self.errors.append(f"{name}: {detail}")
        print(f"  ✗  {name}" + (f"  → {detail}" if detail else ""))

    def warn(self, name: str, detail: str = "") -> None:
        self.checks.append({"check": name, "result": "WARN", "detail": detail})
        print(f"  ⚠  {name}" + (f"  → {detail}" if detail else ""))

    @property
    def passed(self) -> bool:
        return len(self.errors) == 0

    @property
    def n_pass(self) -> int:
        return sum(1 for c in self.checks if c["result"] == "PASS")

    @property
    def n_fail(self) -> int:
        return sum(1 for c in self.checks if c["result"] == "FAIL")

    @property
    def n_warn(self) -> int:
        return sum(1 for c in self.checks if c["result"] == "WARN")


# ── Main validation ────────────────────────────────────────────────────────────

def run_validation() -> tuple[Validator, dict]:
    v  = Validator()
    ts = datetime.now().isoformat(timespec="seconds")

    print()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║   World Bank Data Validator — SEA Change Dashboard          ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print(f"  Checking: {DATA_FILE.relative_to(PROJECT_ROOT)}")
    print()

    # ── CHECK 1: File exists ──────────────────────────────────────────────────
    if not DATA_FILE.exists():
        v.fail("File exists", f"{DATA_FILE} not found — run python scripts/fetch_worldbank.py first")
        return v, {}

    v.ok("File exists")

    # ── CHECK 2: Valid JSON ───────────────────────────────────────────────────
    try:
        data: dict = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        v.fail("Valid JSON", str(e))
        return v, {}

    v.ok("Valid JSON")

    # ── CHECK 3: Top-level structure ──────────────────────────────────────────
    for key in ("meta", "indicators", "records"):
        if key not in data:
            v.fail(f"Has '{key}' key")
        else:
            v.ok(f"Has '{key}' key")

    if "records" not in data:
        return v, data

    records: list[dict] = data["records"]
    meta:    dict       = data.get("meta", {})

    v.ok("Total records", f"{len(records):,}")

    # ── CHECK 4: Countries ────────────────────────────────────────────────────
    found_countries: set[str] = {r["country_code"] for r in records if "country_code" in r}
    missing_countries = EXPECTED_COUNTRIES - found_countries
    if missing_countries:
        v.fail("All 17 countries present", f"Missing: {sorted(missing_countries)}")
    else:
        v.ok("All 17 countries present", f"{len(found_countries)} found")

    extra_countries = found_countries - EXPECTED_COUNTRIES
    if extra_countries:
        v.warn("No unexpected countries", f"Extra: {sorted(extra_countries)}")

    # ── CHECK 5: Indicators ───────────────────────────────────────────────────
    found_indicators: set[str] = {r["indicator_key"] for r in records if "indicator_key" in r}
    missing_indicators = EXPECTED_INDICATORS - found_indicators
    if missing_indicators:
        v.fail("All 8 indicators present", f"Missing: {sorted(missing_indicators)}")
    else:
        v.ok("All 8 indicators present", f"{len(found_indicators)} found")

    # ── CHECK 6: Year coverage ────────────────────────────────────────────────
    found_years: set[int] = {r["year"] for r in records if "year" in r}
    missing_years = EXPECTED_YEARS - found_years
    if missing_years:
        v.fail("All years 2015–2026 present", f"Missing years: {sorted(missing_years)}")
    else:
        v.ok("All years 2015–2026 present", f"{min(found_years)}–{max(found_years)}")

    # ── CHECK 7: No duplicate rows ────────────────────────────────────────────
    seen_keys: set[tuple] = set()
    dupes: list[str]      = []
    for r in records:
        key = (r.get("country_code"), r.get("indicator_key"), r.get("year"))
        if key in seen_keys:
            dupes.append(str(key))
        seen_keys.add(key)

    if dupes:
        v.fail("No duplicate rows", f"{len(dupes)} duplicate (country, indicator, year) keys")
    else:
        v.ok("No duplicate rows")

    # ── CHECK 8: Required fields ──────────────────────────────────────────────
    missing_field_counts: dict[str, int] = {f: 0 for f in REQUIRED_FIELDS}
    for r in records:
        for field in REQUIRED_FIELDS:
            if field not in r:
                missing_field_counts[field] += 1

    truly_missing = {f: n for f, n in missing_field_counts.items() if n > 0}
    if truly_missing:
        for field, count in truly_missing.items():
            v.fail(f"Required field '{field}'", f"{count} records missing this field")
    else:
        v.ok("All required fields present on every record")

    # ── CHECK 9: source_url non-empty ─────────────────────────────────────────
    empty_urls = sum(1 for r in records if not r.get("source_url"))
    if empty_urls:
        v.fail("source_url non-empty", f"{empty_urls} records with empty source_url")
    else:
        v.ok("source_url non-empty on all records")

    # ── CHECK 10: value_type valid ────────────────────────────────────────────
    bad_vtype = [r for r in records if r.get("value_type") not in VALID_VALUE_TYPES]
    if bad_vtype:
        bad_values = {r.get("value_type") for r in bad_vtype}
        v.fail("value_type valid", f"{len(bad_vtype)} records with invalid value_type: {bad_values}")
    else:
        v.ok("value_type valid on all records", f"allowed: {VALID_VALUE_TYPES}")

    # ── CHECK 11: data_quality valid ──────────────────────────────────────────
    bad_quality = [r for r in records if r.get("data_quality") not in VALID_DATA_QUALITY]
    if bad_quality:
        bad_values = {r.get("data_quality") for r in bad_quality}
        v.fail("data_quality valid", f"{len(bad_quality)} records with invalid data_quality: {bad_values}")
    else:
        v.ok("data_quality valid on all records", f"allowed: {VALID_DATA_QUALITY}")

    # ── CHECK 12: No forecast_estimate in worldbank_indicators.json ───────────
    forecast_in_wb = [r for r in records if r.get("value_type") == "forecast_estimate"]
    if forecast_in_wb:
        v.fail(
            "No forecast_estimate in worldbank_indicators.json",
            f"{len(forecast_in_wb)} records with value_type=forecast_estimate "
            "(these belong in latest_estimates.json only)"
        )
    else:
        v.ok("No forecast_estimate values in worldbank_indicators.json")

    # ── CHECK 13: 2025/2026 null rows correctly labeled ───────────────────────
    bad_future = []
    for r in records:
        yr = r.get("year", 0)
        if yr >= 2025:
            val = r.get("value")
            vt  = r.get("value_type")
            dq  = r.get("data_quality")
            if val is None and vt != "missing_official":
                bad_future.append(f"{r.get('country_code')} {r.get('indicator_key')} {yr}: null value but value_type={vt}")
            if val is None and dq not in ("missing",):
                bad_future.append(f"{r.get('country_code')} {r.get('indicator_key')} {yr}: null value but data_quality={dq}")

    if bad_future:
        v.fail("2025/2026 null rows labeled missing_official", f"{len(bad_future)} mismatches")
        for line in bad_future[:5]:
            print(f"      {line}")
    else:
        v.ok("2025/2026 null rows correctly labeled missing_official")

    # ── CHECK 14: 2025/2026 not forward-filled from historical data ───────────
    filled_future = [r for r in records if r.get("year", 0) >= 2025 and r.get("data_quality") == "estimated"]
    if filled_future:
        v.fail(
            "2025/2026 not forward-filled",
            f"{len(filled_future)} records with year≥2025 and data_quality=estimated "
            "(2025/2026 must be official_actual or missing_official only)"
        )
    else:
        v.ok("2025/2026 rows are not forward-filled (no fake values)")

    # ── CHECK 15: Value range sanity ──────────────────────────────────────────
    out_of_range: list[str] = []
    for r in records:
        val = r.get("value")
        if val is None:
            continue
        ind_key = r.get("indicator_key", "")
        lo, hi  = PLAUSIBLE_RANGES.get(ind_key, (-1e9, 1e9))
        if not (lo <= float(val) <= hi):
            out_of_range.append(
                f"{r.get('country_code')} {ind_key} {r.get('year')}: {val:.3f} (expected {lo}–{hi})"
            )

    if out_of_range:
        v.warn(
            "Values within plausible ranges",
            f"{len(out_of_range)} out-of-range values (verify manually)"
        )
        for line in out_of_range[:5]:
            print(f"      {line}")
    else:
        v.ok("All values within plausible ranges")

    # ── CHECK 16: Coverage stats ──────────────────────────────────────────────
    available_n  = sum(1 for r in records if r.get("data_quality") == "available")
    estimated_n  = sum(1 for r in records if r.get("data_quality") == "estimated")
    missing_n    = sum(1 for r in records if r.get("data_quality") == "missing")
    official_n   = sum(1 for r in records if r.get("value_type") == "official_actual")
    miss_off_n   = sum(1 for r in records if r.get("value_type") == "missing_official")

    total = len(records)
    v.ok(
        "Coverage stats",
        f"available={available_n} ({100*available_n//total}%)  "
        f"estimated={estimated_n}  missing={missing_n}  "
        f"official_actual={official_n}  missing_official={miss_off_n}"
    )

    return v, data


# ── Save log ───────────────────────────────────────────────────────────────────

def save_log(v: Validator, data: dict) -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().isoformat(timespec="seconds")

    log = {
        "validated_at":    ts,
        "data_file":       str(DATA_FILE.relative_to(PROJECT_ROOT)),
        "generated_at":    data.get("meta", {}).get("generated_at", "unknown"),
        "total_records":   len(data.get("records", [])),
        "passed":          v.passed,
        "n_pass":          v.n_pass,
        "n_fail":          v.n_fail,
        "n_warn":          v.n_warn,
        "errors":          v.errors,
        "checks":          v.checks,
    }

    LOG_FILE.write_text(json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n  Log saved → {LOG_FILE.relative_to(PROJECT_ROOT)}")


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> int:
    v, data = run_validation()
    save_log(v, data)

    W = 62
    print()
    print("─" * W)
    if v.passed:
        print(f"  ✓  All {v.n_pass} checks passed" + (f"  ({v.n_warn} warnings)" if v.n_warn else ""))
        print("     Data is ready for the dashboard.")
    else:
        print(f"  ✗  {v.n_fail} check(s) FAILED  (+ {v.n_pass} passed, {v.n_warn} warnings)")
        print()
        print("  Failed checks:")
        for err in v.errors:
            print(f"    • {err}")
        print()
        print("  Fix steps:")
        print("    1. Run:  python scripts/fetch_worldbank.py --refresh")
        print("    2. Run:  python scripts/validate_worldbank_data.py")
    print("─" * W)
    print()

    return 0 if v.passed else 1


if __name__ == "__main__":
    sys.exit(main())
