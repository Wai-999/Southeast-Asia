#!/usr/bin/env python3
"""
==============================================================================
  process_indicators.py — SEA Change Intelligence Dashboard
==============================================================================

Reads the raw World Bank indicator data and UN Comtrade trade flow data,
then combines them into a clean per-country summary JSON ready for the
dashboard to display.

INPUT FILES  (these must exist before running this script):
  pipeline/data/processed/worldbank_indicators.json   ← from fetch_worldbank.py
  pipeline/data/processed/trade_flows.json            ← from fetch_comtrade.py

OUTPUT FILE:
  pipeline/data/processed/indicators_dashboard.json

WHAT THIS SCRIPT DOES  (step by step)
──────────────────────────────────────
  1. Loads the World Bank indicator records (1,360 records × 17 countries)
  2. Groups them by country and by indicator
  3. Finds the LATEST available value for each indicator per country
  4. Computes trend direction: up / down / flat / unknown
  5. Builds a full history array (2015–2024) for sparkline charts
  6. Merges UN Comtrade trade dependency data for the 10 SEA reporter countries
  7. Calculates a data-completeness % for each country
  8. Saves everything to indicators_dashboard.json

HOW TO RUN
──────────
  cd pipeline
  python process_indicators.py           # normal run
  python process_indicators.py --refresh # force reprocess

IMPORTANT NOTES FOR BEGINNERS
──────────────────────────────
  • This script NEVER crashes the whole pipeline because one country failed.
    If a country's data is missing or broken, it is logged with a warning
    and a skeleton record is added so other scripts don't break.
  • All missing values are stored as null (None in Python / null in JSON).
    Downstream code must check for null before using values.
  • The "trend" field tells you if an indicator went up or down vs last year:
      "up"      — value increased >0.5%  relative to previous year
      "down"    — value decreased >0.5%  relative to previous year
      "flat"    — change was less than 0.5% relative
      "unknown" — we don't have two years to compare

==============================================================================
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# ── Make utils importable when run as a standalone script ──────────────────
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from utils.logger import ok, fail, warn, info, section


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 1 — FILE PATHS
# ══════════════════════════════════════════════════════════════════════════════

PROC_DIR = SCRIPT_DIR / "data" / "processed"
WB_FILE  = PROC_DIR / "worldbank_indicators.json"
TF_FILE  = PROC_DIR / "trade_flows.json"
OUT_FILE = PROC_DIR / "indicators_dashboard.json"


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 2 — COUNTRY & INDICATOR REGISTRY
# ══════════════════════════════════════════════════════════════════════════════

# All 17 countries tracked by the dashboard (11 SEA + 6 partners)
ALL_COUNTRIES: dict[str, dict] = {
    # ── Southeast Asia ───────────────────────────────────────────────────────
    "THA": {"name": "Thailand",      "flag": "🇹🇭", "region": "Southeast Asia",  "is_sea": True},
    "VNM": {"name": "Vietnam",       "flag": "🇻🇳", "region": "Southeast Asia",  "is_sea": True},
    "MMR": {"name": "Myanmar",       "flag": "🇲🇲", "region": "Southeast Asia",  "is_sea": True},
    "KHM": {"name": "Cambodia",      "flag": "🇰🇭", "region": "Southeast Asia",  "is_sea": True},
    "LAO": {"name": "Laos",          "flag": "🇱🇦", "region": "Southeast Asia",  "is_sea": True},
    "MYS": {"name": "Malaysia",      "flag": "🇲🇾", "region": "Southeast Asia",  "is_sea": True},
    "SGP": {"name": "Singapore",     "flag": "🇸🇬", "region": "Southeast Asia",  "is_sea": True},
    "IDN": {"name": "Indonesia",     "flag": "🇮🇩", "region": "Southeast Asia",  "is_sea": True},
    "PHL": {"name": "Philippines",   "flag": "🇵🇭", "region": "Southeast Asia",  "is_sea": True},
    "BRN": {"name": "Brunei",        "flag": "🇧🇳", "region": "Southeast Asia",  "is_sea": True},
    "TLS": {"name": "Timor-Leste",   "flag": "🇹🇱", "region": "Southeast Asia",  "is_sea": True},
    # ── Partner countries ────────────────────────────────────────────────────
    "CHN": {"name": "China",         "flag": "🇨🇳", "region": "East Asia",        "is_sea": False},
    "USA": {"name": "United States", "flag": "🇺🇸", "region": "North America",    "is_sea": False},
    "JPN": {"name": "Japan",         "flag": "🇯🇵", "region": "East Asia",        "is_sea": False},
    "IND": {"name": "India",         "flag": "🇮🇳", "region": "South Asia",       "is_sea": False},
    "KOR": {"name": "South Korea",   "flag": "🇰🇷", "region": "East Asia",        "is_sea": False},
    "AUS": {"name": "Australia",     "flag": "🇦🇺", "region": "Oceania",          "is_sea": False},
}

# The 8 indicators fetched from the World Bank
INDICATOR_KEYS: list[str] = [
    "gdpGrowth", "gdpNominal", "inflation", "unemployment",
    "fdiPctGdp", "exports", "imports", "population",
]

# Human-readable labels and display hints for each indicator
INDICATOR_META: dict[str, dict] = {
    "gdpGrowth":    {"label": "GDP Growth Rate",  "unit": "% YoY",      "higher_is": "good"},
    "gdpNominal":   {"label": "GDP (Nominal)",    "unit": "USD Billion", "higher_is": "good"},
    "inflation":    {"label": "Inflation (CPI)",  "unit": "% YoY",      "higher_is": "bad"},
    "unemployment": {"label": "Unemployment",     "unit": "%",           "higher_is": "bad"},
    "fdiPctGdp":    {"label": "FDI (% of GDP)",  "unit": "% of GDP",   "higher_is": "good"},
    "exports":      {"label": "Exports",          "unit": "USD Billion", "higher_is": "good"},
    "imports":      {"label": "Imports",          "unit": "USD Billion", "higher_is": "neutral"},
    "population":   {"label": "Population",       "unit": "Millions",    "higher_is": "neutral"},
}

# The 10 SEA countries for which we have UN Comtrade trade-dependency data
SEA_REPORTERS: set[str] = {"THA","VNM","MMR","KHM","LAO","MYS","SGP","IDN","PHL","BRN"}


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 3 — DATA LOADING
# ══════════════════════════════════════════════════════════════════════════════

def load_worldbank() -> dict:
    """
    Load and return the World Bank indicator JSON.
    Raises FileNotFoundError with a helpful message if the file doesn't exist.
    """
    info(f"Loading: {WB_FILE.relative_to(SCRIPT_DIR)}")
    if not WB_FILE.exists():
        raise FileNotFoundError(
            f"World Bank data not found: {WB_FILE}\n"
            "  → Run this first:  python fetch_worldbank.py"
        )
    with open(WB_FILE, encoding="utf-8") as f:
        return json.load(f)


def load_trade_flows() -> dict | None:
    """
    Load trade flow JSON. Returns None if missing — this is non-fatal;
    the script continues and trade fields will be set to null.
    """
    if not TF_FILE.exists():
        warn(f"Trade data not found ({TF_FILE.name}) — trade fields will be null")
        warn("  → Run first:  python fetch_comtrade.py")
        return None
    info(f"Loading: {TF_FILE.relative_to(SCRIPT_DIR)}")
    with open(TF_FILE, encoding="utf-8") as f:
        return json.load(f)


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 4 — RECORD GROUPING
# ══════════════════════════════════════════════════════════════════════════════

def group_records(records: list[dict]) -> dict[str, dict[str, dict[int, dict]]]:
    """
    Turn the flat list of WB records into a nested lookup:
      iso3 → indicator_key → year → record_dict

    This makes it fast to look up "Thailand's GDP growth in 2023" as:
      grouped["THA"]["gdpGrowth"][2023]

    Records with missing iso3, indicator_key, or year are silently skipped.
    """
    grouped: dict[str, dict[str, dict[int, dict]]] = {}

    for rec in records:
        iso3    = rec.get("country_code", "")
        ind_key = rec.get("indicator_key", "")
        year    = rec.get("year")

        if not iso3 or not ind_key or year is None:
            continue  # skip incomplete records without crashing

        grouped.setdefault(iso3, {}).setdefault(ind_key, {})[year] = rec

    return grouped


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 5 — PER-COUNTRY PROCESSING
# ══════════════════════════════════════════════════════════════════════════════

def _trend(current: float | None, previous: float | None) -> str:
    """
    Work out whether an indicator went up, down, or stayed flat.

    We use 0.5% relative change as the threshold for "flat" because
    many economic indicators fluctuate slightly even when nothing changed.

    Returns: "up" | "down" | "flat" | "unknown"
    """
    if current is None or previous is None:
        return "unknown"

    diff_pct = abs(current - previous) / max(abs(previous), 0.001) * 100

    if diff_pct < 0.5:
        return "flat"
    return "up" if current > previous else "down"


def process_country(
    iso3: str,
    meta: dict,
    by_indicator: dict[str, dict[int, dict]],
) -> dict:
    """
    Build the full indicator summary for one country.

    This function never raises an exception — it returns partial data
    with None for any fields it couldn't calculate.

    Parameters
    ──────────
    iso3          : ISO3 country code, e.g. "THA"
    meta          : country metadata from ALL_COUNTRIES
    by_indicator  : { indicator_key → { year → record } }

    Returns a dict ready to be saved directly into indicators_dashboard.json.
    """
    result: dict = {
        "iso3":                  iso3,
        "name":                  meta["name"],
        "flag":                  meta["flag"],
        "region":                meta["region"],
        "is_sea":                meta["is_sea"],
        "latest_year":           None,
        "data_completeness_pct": 0.0,
        "missing_indicators":    [],
        "indicators":            {},   # latest value + trend per indicator
        "history":               {},   # full time series per indicator
        "trade":                 None, # filled later by merge_trade_data()
    }

    available_count  = 0
    all_latest_years = []

    for ind_key in INDICATOR_KEYS:
        year_map = by_indicator.get(ind_key, {})
        ind_meta = INDICATOR_META.get(ind_key, {})

        # ── No data at all for this indicator ─────────────────────────────
        if not year_map:
            result["missing_indicators"].append(ind_key)
            result["indicators"][ind_key] = {
                "value":        None,
                "prev_value":   None,
                "trend":        "unknown",
                "unit":         ind_meta.get("unit", ""),
                "year":         None,
                "data_quality": "missing",
                "label":        ind_meta.get("label", ind_key),
                "higher_is":    ind_meta.get("higher_is", "neutral"),
            }
            result["history"][ind_key] = []
            continue

        # ── Find latest and second-latest non-null records ─────────────────
        # Sort years newest-first, then walk until we find two real values
        sorted_years = sorted(year_map.keys(), reverse=True)
        latest_rec   = None
        prev_rec     = None

        for yr in sorted_years:
            rec = year_map[yr]
            if rec.get("value") is not None:
                if latest_rec is None:
                    latest_rec = rec
                elif prev_rec is None:
                    prev_rec   = rec
                    break   # we have both; stop searching

        # ── Extract values safely ──────────────────────────────────────────
        curr_val = latest_rec["value"] if latest_rec else None
        prev_val = prev_rec["value"]   if prev_rec   else None

        if curr_val is not None:
            available_count += 1
            if latest_rec.get("year"):
                all_latest_years.append(latest_rec["year"])

        result["indicators"][ind_key] = {
            "value":        round(curr_val, 4) if curr_val is not None else None,
            "prev_value":   round(prev_val, 4) if prev_val is not None else None,
            "trend":        _trend(curr_val, prev_val),
            "unit":         ind_meta.get("unit", ""),
            "year":         latest_rec["year"] if latest_rec else None,
            "data_quality": latest_rec.get("data_quality", "missing") if latest_rec else "missing",
            "label":        ind_meta.get("label", ind_key),
            "higher_is":    ind_meta.get("higher_is", "neutral"),
        }

        # ── Build history array for sparklines ────────────────────────────
        # Include every year that has a real (non-null) value, sorted oldest→newest
        history = []
        for yr in sorted(year_map.keys()):
            rec = year_map[yr]
            v   = rec.get("value")
            if v is not None:
                history.append({
                    "year":         yr,
                    "value":        round(v, 4),
                    "data_quality": rec.get("data_quality", "available"),
                })
        result["history"][ind_key] = history

    # ── Data completeness score ────────────────────────────────────────────
    result["data_completeness_pct"] = round(
        available_count / len(INDICATOR_KEYS) * 100, 1
    )
    result["latest_year"] = max(all_latest_years) if all_latest_years else None

    return result


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 6 — TRADE DATA MERGE
# ══════════════════════════════════════════════════════════════════════════════

def merge_trade_data(country_data: dict, tf_json: dict) -> None:
    """
    Add trade-dependency information to the 10 SEA reporter countries.

    Modifies country_data in-place.
    Countries not in SEA_REPORTERS get trade = null.
    Countries in SEA_REPORTERS that are missing from trade_flows also get null.
    """
    dependency  = tf_json.get("dependency", {})
    years       = tf_json.get("meta", {}).get("years", [])
    latest_year = max(years) if years else None

    for iso3, cdata in country_data.items():
        # Partner countries and Timor-Leste don't have trade dependency data
        if iso3 not in SEA_REPORTERS or not latest_year:
            cdata["trade"] = None
            continue

        year_str = str(latest_year)
        dep_yr   = dependency.get(iso3, {}).get(year_str)

        if not dep_yr:
            cdata["trade"] = None
            warn(f"  {cdata['flag']} {cdata['name']}: no trade data for {latest_year}")
            continue

        # Build a clean trade summary for this country
        by_partner = dep_yr.get("by_partner", {})
        china_data = by_partner.get("CHN", {})

        cdata["trade"] = {
            "data_year":               latest_year,
            "total_exports_usd_b":     dep_yr.get("total_exports_usd_b"),
            "total_imports_usd_b":     dep_yr.get("total_imports_usd_b"),
            "trade_balance_usd_b":     dep_yr.get("trade_balance_usd_b"),
            "top_export_partner":      dep_yr.get("top_export_partner"),
            "top_export_share_pct":    dep_yr.get("top_export_share_pct"),
            "top_import_partner":      dep_yr.get("top_import_partner"),
            "top_import_share_pct":    dep_yr.get("top_import_share_pct"),
            "china_overall_risk":      china_data.get("dependency_risk"),
            "china_partner_share_pct": china_data.get("partner_share_pct"),
            "by_partner":              by_partner,
        }


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 7 — SAVE OUTPUT
# ══════════════════════════════════════════════════════════════════════════════

def save_output(country_data: dict, wb_meta: dict) -> None:
    """Write the final indicators_dashboard.json."""
    output = {
        "meta": {
            "generated_at":       datetime.now().isoformat(timespec="seconds"),
            "script":             "process_indicators.py",
            # source_url tells downstream scripts where this data came from
            "source_url":         str(WB_FILE.relative_to(SCRIPT_DIR)),
            # fetched_at tells you when the World Bank fetch happened
            "fetched_at":         wb_meta.get("generated_at", ""),
            "wb_data_status":     wb_meta.get("data_status", "unknown"),
            "countries":          len(country_data),
            "sea_countries":      sum(1 for c in country_data.values() if c["is_sea"]),
            "partner_countries":  sum(1 for c in country_data.values() if not c["is_sea"]),
            "indicators":         INDICATOR_KEYS,
            "refresh_note": (
                "Run 'python fetch_worldbank.py && python process_indicators.py' "
                "to refresh with the latest World Bank data."
            ),
        },
        "countries": country_data,
    }

    PROC_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 8 — MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main() -> int:
    """
    Orchestrates all processing steps.

    Exit codes:
      0  — completed (even if some individual countries had missing data)
      1  — fatal error (e.g. input file missing, can't write output)
    """
    parser = argparse.ArgumentParser(
        description="Process World Bank + Comtrade data for SEA Dashboard"
    )
    parser.add_argument(
        "--refresh", action="store_true",
        help="Force reprocess even if output already exists today",
    )
    parser.parse_args()

    # ── Banner ──────────────────────────────────────────────────────────────
    print()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║   SEA Dashboard — Process Indicators                        ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()
    print(f"  Input   (WB)    : {WB_FILE.relative_to(SCRIPT_DIR)}")
    print(f"  Input   (Trade) : {TF_FILE.relative_to(SCRIPT_DIR)}")
    print(f"  Output          : {OUT_FILE.relative_to(SCRIPT_DIR)}")
    print()

    # ── Step 1: Load ────────────────────────────────────────────────────────
    section("Step 1 — Load source files")
    try:
        wb_json = load_worldbank()
    except FileNotFoundError as exc:
        fail(str(exc))
        return 1

    tf_json = load_trade_flows()   # returns None if missing — non-fatal

    wb_records = wb_json.get("records", [])
    wb_meta    = wb_json.get("meta", {})

    ok(f"World Bank : {len(wb_records):,} records  (fetched {wb_meta.get('generated_at','?')})")
    if tf_json:
        ok(f"Trade flows: {len(tf_json.get('flows', [])):,} bilateral pairs")

    # ── Step 2: Group records ────────────────────────────────────────────────
    section("Step 2 — Group records by country × indicator")
    grouped = group_records(wb_records)
    ok(f"Organised into {len(grouped)} countries × {len(INDICATOR_KEYS)} indicators")

    # ── Step 3: Build per-country summaries ─────────────────────────────────
    section("Step 3 — Build per-country summaries")
    country_data: dict[str, dict] = {}
    country_errors = 0

    for iso3, meta in ALL_COUNTRIES.items():
        try:
            by_indicator = grouped.get(iso3, {})
            cdata = process_country(iso3, meta, by_indicator)
            country_data[iso3] = cdata

            completeness = cdata["data_completeness_pct"]
            flag         = meta["flag"]
            name         = meta["name"].ljust(16)
            yr           = cdata["latest_year"] or "n/a"
            missing      = cdata["missing_indicators"]

            if completeness == 100:
                info(f"{flag} {name}  ✓ complete      (latest year: {yr})")
            elif completeness >= 50:
                info(f"{flag} {name}  ~ {completeness:.0f}% complete  "
                     f"(missing: {', '.join(missing)})")
            else:
                warn(f"{flag} {name}  ⚠ {completeness:.0f}% complete  "
                     f"(missing: {', '.join(missing)})")

        except Exception as exc:
            # One country failing must NOT crash the whole pipeline.
            # We log the error and insert a skeleton so downstream scripts work.
            country_errors += 1
            fail(f"{iso3} ({meta['name']}): processing error — {exc}")
            country_data[iso3] = {
                "iso3": iso3, "name": meta["name"], "flag": meta["flag"],
                "region": meta["region"], "is_sea": meta["is_sea"],
                "latest_year": None, "data_completeness_pct": 0.0,
                "missing_indicators": list(INDICATOR_KEYS),
                "indicators": {}, "history": {}, "trade": None,
            }

    if country_errors:
        warn(f"{country_errors} country/countries had processing errors (see above)")

    # ── Step 4: Merge trade data ─────────────────────────────────────────────
    section("Step 4 — Merge trade dependency data")
    if tf_json:
        merge_trade_data(country_data, tf_json)
        with_trade = sum(
            1 for iso3, c in country_data.items()
            if iso3 in SEA_REPORTERS and c.get("trade") is not None
        )
        ok(f"Trade data merged for {with_trade}/{len(SEA_REPORTERS)} SEA reporter countries")
    else:
        warn("Trade data skipped — trade fields set to null")
        for cdata in country_data.values():
            cdata["trade"] = None

    # ── Step 5: Save ────────────────────────────────────────────────────────
    section("Step 5 — Save processed output")
    try:
        save_output(country_data, wb_meta)
        size_kb = OUT_FILE.stat().st_size // 1024
        ok(f"Saved → {OUT_FILE.relative_to(SCRIPT_DIR)}  ({size_kb} KB)")
    except Exception as exc:
        fail(f"Could not save output: {exc}")
        return 1

    # ── Final summary ────────────────────────────────────────────────────────
    n_sea_ok = sum(
        1 for iso3, c in country_data.items()
        if iso3 in SEA_REPORTERS and c["data_completeness_pct"] >= 50
    )
    print()
    print("━" * 62)
    ok(f"process_indicators.py complete")
    info(f"  {len(country_data)} countries processed  ({country_errors} errors)")
    info(f"  SEA countries with ≥50% data: {n_sea_ok}/{len(SEA_REPORTERS)}")
    info(f"  Output: {OUT_FILE}")
    print("━" * 62)
    print()

    # Return 0 even if some countries had errors — partial data is valid output
    return 0


if __name__ == "__main__":
    sys.exit(main())
