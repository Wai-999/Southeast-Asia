#!/usr/bin/env python3
"""
scripts/normalize_indicators.py
────────────────────────────────────────────────────────────────────────────
Normalizes all raw indicator files into a consistent schema.

Every output row MUST have these 22 fields:
  country_code, country_name, sector, indicator_code, indicator_name,
  period, year, quarter, month, value, unit, frequency,
  source, source_type, source_url, fetched_at, released_at,
  value_type, data_quality, confidence, extraction_method, limitation_note

VALUE TYPE RULES (enforced here):
  official_actual     — real published data from official body
  official_preliminary— marked preliminary/advance by official body
  official_partial_2026 — official 2026 partial year
  forecast_estimate   — IMF/WB/ADB projection
  missing_official    — checked official source; not yet published
  official_policy     — policy update / qualitative announcement
  realtime_signal     — GDELT news counts
  sample              — dev placeholder (removed from production output)

MERGE GUARD: Never overwrite official_actual with forecast_estimate.

OUTPUT
  pipeline/data/processed/all_sources_normalized.json   — all rows merged
"""

import json
import sys
from pathlib import Path
from datetime import datetime, date

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROC_DIR     = PROJECT_ROOT / "pipeline" / "data" / "processed"

# Country name lookup (ISO3 → display name)
COUNTRY_NAMES = {
    "THA":"Thailand","VNM":"Vietnam","MMR":"Myanmar","KHM":"Cambodia","LAO":"Laos",
    "MYS":"Malaysia","SGP":"Singapore","IDN":"Indonesia","PHL":"Philippines",
    "BRN":"Brunei","TLS":"Timor-Leste",
    "CHN":"China","USA":"United States","JPN":"Japan","IND":"India",
    "KOR":"South Korea","AUS":"Australia","EUU":"European Union",
}

VALID_VALUE_TYPES = {
    "official_actual", "official_preliminary", "official_partial_2026",
    "forecast_estimate", "missing_official", "official_policy",
    "realtime_signal", "sample",
}

VALID_DATA_QUALITY = {"available", "estimated", "old_data", "missing", "partial"}

REQUIRED_FIELDS = [
    "country_code","country_name","sector","indicator_code","indicator_name",
    "period","year","quarter","month","value","unit","frequency",
    "source","source_type","source_url","fetched_at","released_at",
    "value_type","data_quality","confidence","extraction_method","limitation_note",
]

# Source files to load (in merge priority order — later overrides earlier for same key)
SOURCE_FILES = [
    ("worldbank_indicators.json",         1),   # WB core 8 indicators
    ("worldbank_extended_normalized.json", 1),  # WB governance, social, etc.
    ("technology_normalized.json",         1),  # WB tech + extended
    ("energy_normalized.json",             1),  # WB energy + env
    ("environment_normalized.json",        1),  # WB agriculture + social
    ("tourism_normalized.json",            1),  # WB tourism
    ("aseanstats_normalized.json",         2),  # ASEAN regional
    ("comtrade_normalized.json",           2),  # UN Comtrade trade
    ("infrastructure_normalized.json",     2),  # WB/ADB projects
    ("adb_ado_normalized.json",            3),  # ADB forecasts
    ("imf_weo_normalized.json",            3),  # IMF WEO forecasts
    ("national_stats_normalized.json",     1),  # NSO (high priority)
    ("central_banks_normalized.json",      1),  # Central bank (high priority)
    ("ministries_normalized.json",         1),  # Ministries (high priority)
    ("press_releases_normalized.json",     4),  # Policy updates (no values)
]


# Map WB indicator_key to sector (for worldbank_indicators.json which lacks sector field)
WB_KEY_TO_SECTOR = {
    "gdpGrowth":    "macro_economy",
    "gdpNominal":   "macro_economy",
    "inflation":    "prices_inflation",
    "unemployment": "labor",
    "fdiPctGdp":    "investment",
    "exports":      "trade",
    "imports":      "trade",
    "population":   "social_indicators",
}

# Map WB indicator_key to standard indicator_code
WB_KEY_TO_CODE = {
    "gdpGrowth":    "GDP_GROWTH",
    "gdpNominal":   "GDP_NOMINAL_USD",
    "inflation":    "CPI_INFLATION",
    "unemployment": "UNEMPLOYMENT_RATE",
    "fdiPctGdp":    "FDI_PCT_GDP",
    "exports":      "EXPORTS_USD",
    "imports":      "IMPORTS_USD",
    "population":   "POPULATION",
}


def _fix_row(row: dict, priority: int) -> dict | None:
    """Ensure row has all required fields and valid values."""
    # Skip sample data entirely
    if row.get("value_type") == "sample":
        return None

    # Handle worldbank_indicators.json format (uses indicator_key not sector)
    if not row.get("sector") and row.get("indicator_key"):
        ik = row["indicator_key"]
        row["sector"]           = WB_KEY_TO_SECTOR.get(ik, "macro_economy")
        row["indicator_code"]   = WB_KEY_TO_CODE.get(ik, ik.upper())
    elif not row.get("sector") and row.get("indicator_code"):
        # Try to infer sector from indicator_code
        code = row.get("indicator_code","")
        if "GDP" in code or "CURRENT_ACCOUNT" in code:
            row["sector"] = "macro_economy"
        elif "CPI" in code or "PPI" in code or "INFLATION" in code:
            row["sector"] = "prices_inflation"
        elif "UNEM" in code or "LABOR" in code or "EMPLOY" in code:
            row["sector"] = "labor"
        elif "EXPORT" in code or "IMPORT" in code or "TRADE" in code:
            row["sector"] = "trade"
        elif "FDI" in code or "INVEST" in code or "CAPITAL" in code:
            row["sector"] = "investment"
        elif "TOURIST" in code or "TOURISM" in code:
            row["sector"] = "tourism"
        elif "ENERGY" in code or "RENEW" in code or "ELECTRIC" in code:
            row["sector"] = "energy"
        elif "CO2" in code or "FOREST" in code or "LAND" in code:
            row["sector"] = "environment"
        elif "POPULATION" in code or "POVERTY" in code or "LIFE_EXP" in code or "GINI" in code:
            row["sector"] = "social_indicators"
        elif "EXCHANGE" in code or "RESERVE" in code or "MONEY" in code or "POLICY_RATE" in code:
            row["sector"] = "finance_monetary"
        elif "FISCAL" in code or "DEBT" in code or "GOVT_REV" in code or "GOVT_EXP" in code:
            row["sector"] = "fiscal"
        elif "GOVERN" in code or "RULE_OF_LAW" in code or "VOICE" in code:
            row["sector"] = "politics_policy"
        elif "STABILITY" in code or "CORRUPT" in code or "CONFLICT" in code:
            row["sector"] = "security_conflict"
        elif "INTERNET" in code or "MOBILE" in code or "BROADBAND" in code or "RD_EXP" in code:
            row["sector"] = "technology_digital"
        elif "LOGISTICS" in code or "WB_PROJ" in code or "INFRA" in code:
            row["sector"] = "infrastructure"
        elif "AGRI" in code or "RICE" in code or "FOOD" in code or "ARABLE" in code:
            row["sector"] = "agriculture"
        elif "MANUFACT" in code or "INDUSTRIAL" in code or "PMI" in code:
            row["sector"] = "industry_production"
        else:
            row["sector"] = "macro_economy"  # default fallback

    # Fill country_name if missing
    iso3 = str(row.get("country_code", "")).upper()
    if not iso3 or iso3 not in COUNTRY_NAMES:
        return None   # Skip unknown countries
    row["country_name"] = COUNTRY_NAMES[iso3]
    row["country_code"] = iso3

    # Ensure value_type is valid
    vt = row.get("value_type", "")
    if vt not in VALID_VALUE_TYPES:
        if row.get("value") is None:
            row["value_type"] = "missing_official"
        else:
            row["value_type"] = "official_actual"
    # RULE: null value must be labeled missing_official (except policy/signal)
    if row.get("value") is None and row.get("value_type") not in {
        "missing_official", "official_policy", "realtime_signal"
    }:
        row["value_type"] = "missing_official"

    # Ensure data_quality is valid
    dq = row.get("data_quality", "")
    if dq not in VALID_DATA_QUALITY:
        row["data_quality"] = "available" if row.get("value") is not None else "missing"

    # Year must be int
    try:
        row["year"] = int(row.get("year", 0))
        if row["year"] < 1990 or row["year"] > 2030:
            return None
    except (TypeError, ValueError):
        return None

    # Ensure period string
    if not row.get("period"):
        q = row.get("quarter")
        m = row.get("month")
        y = row["year"]
        if q:
            row["period"] = f"{y}Q{q}"
        elif m:
            row["period"] = f"{y}-{int(m):02d}"
        else:
            row["period"] = str(y)

    # Ensure all required fields exist (fill None for missing optional fields)
    for f in REQUIRED_FIELDS:
        if f not in row:
            row[f] = None

    # Add priority for merge decisions
    row["_source_priority"] = priority

    return row


def _load_file(fname: str, priority: int) -> list[dict]:
    fpath = PROC_DIR / fname
    if not fpath.exists():
        print(f"  ⚠ Missing: {fname}", flush=True)
        return []
    try:
        data = json.loads(fpath.read_text())
        records = data.get("records", data if isinstance(data, list) else [])
        rows = []
        for r in records:
            fixed = _fix_row(dict(r), priority)
            if fixed:
                rows.append(fixed)
        print(f"  ✓ {fname:50s} → {len(rows):6d} valid rows", flush=True)
        return rows
    except Exception as e:
        print(f"  ✗ {fname}: {e}", flush=True)
        return []


def main():
    print(f"\n{'═'*60}")
    print(f"  Normalize All Sources")
    print(f"  Date: {date.today().isoformat()}")
    print(f"{'═'*60}\n")

    all_rows = []
    for fname, priority in SOURCE_FILES:
        rows = _load_file(fname, priority)
        all_rows.extend(rows)

    # Remove internal priority field from output
    for r in all_rows:
        r.pop("_source_priority", None)

    print(f"\n  Total normalized rows: {len(all_rows)}")
    print(f"  Non-null values:       {sum(1 for r in all_rows if r.get('value') is not None)}")

    # Value type breakdown
    from collections import Counter
    vt_counts = Counter(r.get("value_type","?") for r in all_rows)
    print(f"\n  Value types:")
    for vt, cnt in sorted(vt_counts.items(), key=lambda x: -x[1]):
        print(f"    {vt:30s} {cnt:6d}")

    # Sector breakdown
    sector_counts = Counter(str(r.get("sector") or "?") for r in all_rows)
    print(f"\n  Sectors:")
    for s, cnt in sorted(sector_counts.items(), key=lambda x: -x[1]):
        print(f"    {str(s):30s} {cnt:6d}")

    out_file = PROC_DIR / "all_sources_normalized.json"
    result = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "total_rows": len(all_rows),
        "non_null": sum(1 for r in all_rows if r.get("value") is not None),
        "value_type_counts": dict(vt_counts),
        "sector_counts": dict(sector_counts),
        "records": all_rows,
    }
    out_file.write_text(json.dumps(result, indent=2))
    print(f"\n  📄 Output: {out_file.relative_to(PROJECT_ROOT)}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
