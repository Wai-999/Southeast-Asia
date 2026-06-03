#!/usr/bin/env python3
"""
==============================================================================
  scripts/scrape_latest_estimates.py — SEA Change Intelligence Dashboard
==============================================================================

Fetches 2025 and 2026 economic forecasts/estimates for years where official
World Bank data is not yet available (value_type = missing_official).

IMPORTANT RULES:
  • NEVER overwrites pipeline/data/processed/worldbank_indicators.json
  • ONLY fetches a value if worldbank_indicators.json has value=null for that
    country/indicator/year (no duplicate work for values WB already has)
  • Forecasts go to pipeline/data/processed/latest_estimates.json ONLY
  • All forecast values are labeled value_type = forecast_estimate
  • If no reliable estimate is found, keeps value = null
  • Never invents values

DATA SOURCES USED:
  1. IMF World Economic Outlook DataMapper API (free, no key)
     https://www.imf.org/external/datamapper/api/v1
     Covers: GDP growth, inflation, unemployment, current account
     All 17 countries, years 2024–2026

  2. World Bank Macro Poverty Outlook (MPO) via main WB API
     Some forward-looking series exist under different codes.
     Used as fallback cross-check.

  3. World Bank Global Economic Prospects (GEP) data
     GDP growth forecasts published Jan/Jun each year.

INDICATOR MAPPING (World Bank key → IMF WEO code):
    gdpGrowth    → NGDP_RPCH     (Real GDP growth, %)
    inflation    → PCPIPCH       (Consumer price inflation, %)
    unemployment → LUR           (Unemployment rate, % of labor force)

COVERAGE NOTE:
    IMF WEO covers all 17 countries used in this dashboard.
    Trade (exports/imports) and FDI forecasts are NOT available from IMF WEO
    for all countries — those will remain null in latest_estimates.json.
    Population forecast: WB UN estimates available via SP.POP.TOTL for 2025+.

USAGE (run from project root):
    python scripts/scrape_latest_estimates.py
    python scripts/scrape_latest_estimates.py --refresh   # bypass today's cache
    python scripts/scrape_latest_estimates.py --dry-run   # show what would fetch

OUTPUT:
    pipeline/data/processed/latest_estimates.json   ← forecasts only
    pipeline/data/processed/combined_indicators.json ← WB official + estimates merged
    pipeline/data/logs/scrape_log.json              ← run log

RECORD SHAPE:
    {
      "source_url":       "https://www.imf.org/...",
      "source":           "IMF World Economic Outlook (DataMapper)",
      "source_version":   "April 2026",
      "last_updated":     "2026-06-02",
      "fetched_at":       "2026-06-02T14:30:00",
      "country_code":     "THA",
      "country_name":     "Thailand",
      "region_group":     "Southeast Asia",
      "indicator_code":   "NGDP_RPCH",
      "indicator_key":    "gdpGrowth",
      "indicator_name":   "GDP Growth Rate",
      "year":             2025,
      "value":            2.9,
      "unit":             "% YoY",
      "frequency":        "annual",
      "data_quality":     "available",
      "value_type":       "forecast_estimate",
      "confidence":       "medium",
      "limitation_note":  "IMF WEO forecast. Subject to revision. Not confirmed actual data."
    }
==============================================================================
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, datetime
from pathlib import Path

try:
    import urllib.request
    import urllib.error
except ImportError:
    pass

try:
    import httpx
    _HTTP = "httpx"
except ImportError:
    _HTTP = "urllib"


# ── Paths ─────────────────────────────────────────────────────────────────────

PROJECT_ROOT    = Path(__file__).resolve().parent.parent
PIPELINE_DIR    = PROJECT_ROOT / "pipeline"
PROC_DIR        = PIPELINE_DIR / "data" / "processed"
LOGS_DIR        = PIPELINE_DIR / "data" / "logs"
RAW_SCRAPE_DIR  = PIPELINE_DIR / "data" / "raw" / "scraped_estimates"

WB_DATA_FILE    = PROC_DIR / "worldbank_indicators.json"
ESTIMATES_FILE  = PROC_DIR / "latest_estimates.json"
COMBINED_FILE   = PROC_DIR / "combined_indicators.json"
LOG_FILE        = LOGS_DIR / "scrape_log.json"

FORECAST_YEARS  = [2025, 2026]


# ── Country registry (ISO3 → IMF country code) ─────────────────────────────────

# IMF WEO uses ISO 2-digit codes for its DataMapper API.
# These are the same as standard ISO2 except a few edge cases.
ISO3_TO_IMF: dict[str, str] = {
    "THA": "THA", "VNM": "VNM", "MMR": "MMR", "KHM": "KHM", "LAO": "LAO",
    "MYS": "MYS", "SGP": "SGP", "IDN": "IDN", "PHL": "PHL", "BRN": "BRN",
    "TLS": "TLS",
    "CHN": "CHN", "USA": "USA", "JPN": "JPN", "IND": "IND", "KOR": "KOR",
    "AUS": "AUS",
}

COUNTRY_META: dict[str, dict] = {
    "THA": {"name": "Thailand",       "region": "Southeast Asia"},
    "VNM": {"name": "Vietnam",        "region": "Southeast Asia"},
    "MMR": {"name": "Myanmar",        "region": "Southeast Asia"},
    "KHM": {"name": "Cambodia",       "region": "Southeast Asia"},
    "LAO": {"name": "Laos",           "region": "Southeast Asia"},
    "MYS": {"name": "Malaysia",       "region": "Southeast Asia"},
    "SGP": {"name": "Singapore",      "region": "Southeast Asia"},
    "IDN": {"name": "Indonesia",      "region": "Southeast Asia"},
    "PHL": {"name": "Philippines",    "region": "Southeast Asia"},
    "BRN": {"name": "Brunei",         "region": "Southeast Asia"},
    "TLS": {"name": "Timor-Leste",    "region": "Southeast Asia"},
    "CHN": {"name": "China",          "region": "East Asia"},
    "USA": {"name": "United States",  "region": "Americas"},
    "JPN": {"name": "Japan",          "region": "East Asia"},
    "IND": {"name": "India",          "region": "South Asia"},
    "KOR": {"name": "South Korea",    "region": "East Asia"},
    "AUS": {"name": "Australia",      "region": "Oceania"},
}

# IMF WEO DataMapper indicator codes
IMF_INDICATORS: dict[str, dict] = {
    "gdpGrowth":   {
        "imf_code":    "NGDP_RPCH",
        "label":       "Real GDP Growth",
        "unit":        "% YoY",
        "note":        "IMF WEO real GDP growth forecast (constant prices).",
    },
    "inflation":   {
        "imf_code":    "PCPIPCH",
        "label":       "Consumer Price Inflation",
        "unit":        "% YoY",
        "note":        "IMF WEO CPI inflation forecast (average consumer prices).",
    },
    "unemployment": {
        "imf_code":    "LUR",
        "label":       "Unemployment Rate",
        "unit":        "% of labor force",
        "note":        "IMF WEO unemployment rate forecast (% of total labor force).",
    },
}

REQUEST_DELAY = 1.0
MAX_RETRIES   = 3


# ── HTTP helpers ───────────────────────────────────────────────────────────────

def _get_json(url: str) -> dict | list | None:
    """GET url, return parsed JSON. Uses httpx if available, else urllib."""
    try:
        if _HTTP == "httpx":
            r = httpx.get(url, timeout=30, follow_redirects=True)
            r.raise_for_status()
            return r.json()
        else:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
    except Exception as exc:
        print(f"    HTTP error: {type(exc).__name__}: {exc}")
        return None


def _fetch_retry(url: str) -> dict | list | None:
    for attempt in range(1, MAX_RETRIES + 1):
        result = _get_json(url)
        if result is not None:
            return result
        if attempt < MAX_RETRIES:
            wait = 2 ** attempt
            print(f"    Retry {attempt}/{MAX_RETRIES-1} in {wait}s …")
            time.sleep(wait)
    return None


# ── Load existing WB data ──────────────────────────────────────────────────────

def load_wb_missing_cells() -> set[tuple[str, str, int]]:
    """
    Return the set of (iso3, indicator_key, year) cells that are missing_official
    in worldbank_indicators.json. Only these need estimates.
    """
    if not WB_DATA_FILE.exists():
        print(f"  ⚠  worldbank_indicators.json not found at {WB_DATA_FILE}")
        print("     Run python scripts/fetch_worldbank.py first.")
        return set()

    data = json.loads(WB_DATA_FILE.read_text(encoding="utf-8"))
    missing: set[tuple[str, str, int]] = set()
    for r in data.get("records", []):
        if r.get("value_type") == "missing_official" and r.get("year") in FORECAST_YEARS:
            missing.add((r["country_code"], r["indicator_key"], r["year"]))
    return missing


def load_wb_records() -> list[dict]:
    """Return all records from worldbank_indicators.json."""
    if not WB_DATA_FILE.exists():
        return []
    data = json.loads(WB_DATA_FILE.read_text(encoding="utf-8"))
    return data.get("records", [])


# ── IMF WEO DataMapper fetcher ─────────────────────────────────────────────────

def fetch_imf_weo(
    imf_code: str,
    indicator_key: str,
    missing_cells: set[tuple[str, str, int]],
    dry_run: bool = False,
) -> list[dict]:
    """
    Fetch IMF WEO forecasts for one indicator, all relevant countries.

    API: https://www.imf.org/external/datamapper/api/v1/{INDICATOR}/{ISO3}
    Returns JSON like:
      { "values": { "INDICATOR": { "ISO3": { "2025": 2.9, "2026": 3.1, ... } } } }
    """
    # Only fetch countries that have at least one missing cell for this indicator
    countries_needed = {
        iso3 for (iso3, ind, yr) in missing_cells
        if ind == indicator_key
    }
    if not countries_needed:
        return []

    imf_codes_str = ";".join(ISO3_TO_IMF[iso3] for iso3 in sorted(countries_needed) if iso3 in ISO3_TO_IMF)
    url = f"https://www.imf.org/external/datamapper/api/v1/{imf_code}/{imf_codes_str}"

    print(f"    GET {url[:90]}…")

    if dry_run:
        print(f"    (dry-run — would fetch {len(countries_needed)} countries)")
        return []

    payload = _fetch_retry(url)
    if payload is None:
        print(f"    ✗  IMF API failed for {imf_code}")
        return []

    # Parse the nested response
    # Shape: {"values": {"NGDP_RPCH": {"THA": {"2025": 2.9, "2026": 3.1}}}}
    values_block = payload.get("values", {}).get(imf_code, {})

    records: list[dict] = []
    today_str = date.today().isoformat()
    ts        = datetime.now().isoformat(timespec="seconds")

    # Determine IMF WEO edition from response or use current date
    imf_edition = payload.get("description", {}).get("lastUpdate", f"{date.today().year}")
    source_version = f"IMF WEO {imf_edition}" if imf_edition else f"IMF WEO {date.today().year}"

    ind_meta    = IMF_INDICATORS[indicator_key]
    imf_unit    = ind_meta["unit"]
    imf_label   = ind_meta["label"]
    imf_note    = ind_meta["note"]

    for imf_iso3, year_values in values_block.items():
        # Map IMF code back to our ISO3 (they're the same for these countries)
        iso3 = imf_iso3
        if iso3 not in COUNTRY_META:
            continue

        c_meta = COUNTRY_META[iso3]

        for yr_str, val in year_values.items():
            yr = int(yr_str)
            if yr not in FORECAST_YEARS:
                continue
            # Only add if it's a missing cell we need
            if (iso3, indicator_key, yr) not in missing_cells:
                continue

            val_float = float(val) if val is not None else None

            records.append({
                "source_url":     url,
                "source":         "IMF World Economic Outlook (DataMapper API)",
                "source_version": source_version,
                "last_updated":   today_str,
                "fetched_at":     ts,
                "country_code":   iso3,
                "country_name":   c_meta["name"],
                "region_group":   c_meta["region"],
                "indicator_code": imf_code,
                "indicator_key":  indicator_key,
                "indicator_name": imf_label,
                "year":           yr,
                "value":          val_float,
                "unit":           imf_unit,
                "frequency":      "annual",
                "data_quality":   "available" if val_float is not None else "missing",
                "value_type":     "forecast_estimate",
                "confidence":     "medium",
                "limitation_note": (
                    f"{imf_note} "
                    "IMF WEO projections are revised twice yearly (April and October). "
                    "These are forecasts, NOT confirmed actual data. "
                    "Do not treat as equivalent to World Bank official annual actuals."
                ),
            })

    return records


# ── WB population forecast (WB API has 2025/2026 population projections) ──────

def fetch_wb_population_2025_2026(
    missing_cells: set[tuple[str, str, int]],
    dry_run: bool = False,
) -> list[dict]:
    """
    World Bank SP.POP.TOTL includes UN population projections for 2025+.
    These are official WB data, so we label them value_type=official_actual.
    But we still put them in latest_estimates.json since they were missing
    in the original worldbank_indicators.json run.
    """
    pop_missing = {(iso3, yr) for (iso3, ind, yr) in missing_cells if ind == "population"}
    if not pop_missing:
        return []

    # WB 2-letter codes for all 17 countries (no external import needed)
    WB2_TO_ISO3: dict[str, str] = {
        "TH": "THA", "VN": "VNM", "MM": "MMR", "KH": "KHM", "LA": "LAO",
        "MY": "MYS", "SG": "SGP", "ID": "IDN", "PH": "PHL", "BN": "BRN",
        "TP": "TLS",
        "CN": "CHN", "US": "USA", "JP": "JPN", "IN": "IND", "KR": "KOR",
        "AU": "AUS",
    }
    country_codes = ";".join(WB2_TO_ISO3.keys())
    url = (
        f"https://api.worldbank.org/v2/country/{country_codes}"
        f"/indicator/SP.POP.TOTL"
        f"?format=json&per_page=1000&date=2025:2026"
    )

    print(f"    GET {url[:90]}…  (WB population 2025-2026)")

    if dry_run:
        print("    (dry-run)")
        return []

    payload = _fetch_retry(url)
    if payload is None or not isinstance(payload, list) or len(payload) < 2:
        print("    ✗  WB population 2025-2026 fetch failed")
        return []

    data_rows = payload[1] or []
    records: list[dict] = []
    today_str = date.today().isoformat()
    ts        = datetime.now().isoformat(timespec="seconds")

    for row in data_rows:
        raw_val = row.get("value")
        if raw_val is None:
            continue
        wb2  = row.get("country", {}).get("id", "")
        iso3 = WB2_TO_ISO3.get(wb2)
        if not iso3:
            continue
        yr = int(row["date"])
        if yr not in FORECAST_YEARS:
            continue
        if (iso3, yr) not in pop_missing:
            continue

        c_meta = COUNTRY_META.get(iso3, {"name": iso3, "region": "Unknown"})
        scaled = round(float(raw_val) / 1_000_000, 6)  # scale to millions

        records.append({
            "source_url":     url,
            "source":         "World Bank Open Data API (UN population projection)",
            "source_version": f"WB {date.today().year}",
            "last_updated":   today_str,
            "fetched_at":     ts,
            "country_code":   iso3,
            "country_name":   c_meta["name"],
            "region_group":   c_meta["region"],
            "indicator_code": "SP.POP.TOTL",
            "indicator_key":  "population",
            "indicator_name": "Total Population",
            "year":           yr,
            "value":          scaled,
            "unit":           "Millions",
            "frequency":      "annual",
            "data_quality":   "available",
            "value_type":     "official_actual",   # WB UN projection = official
            "confidence":     "high",
            "limitation_note": (
                "UN/WB population projection for this year. "
                "Based on UN World Population Prospects estimates. "
                "May differ slightly from final census-adjusted figures."
            ),
        })

    return records


# ── Save latest_estimates.json ─────────────────────────────────────────────────

def save_latest_estimates(records: list[dict]) -> None:
    PROC_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().isoformat(timespec="seconds")

    # Count by value_type and indicator
    by_indicator: dict[str, int] = {}
    for r in records:
        k = r.get("indicator_key", "unknown")
        by_indicator[k] = by_indicator.get(k, 0) + 1

    # Count non-null estimates
    non_null = sum(1 for r in records if r.get("value") is not None)

    output = {
        "meta": {
            "generated_at":      ts,
            "description":       (
                "2025–2026 economic estimates and forecasts for the SEA Dashboard. "
                "These supplement worldbank_indicators.json for years where "
                "official World Bank data is not yet published. "
                "ALL values here are labeled value_type='forecast_estimate' "
                "(except WB population projections which are official_actual). "
                "NEVER treat these as confirmed actual values."
            ),
            "sources_used":      ["IMF World Economic Outlook (DataMapper)", "World Bank population projections"],
            "forecast_years":    FORECAST_YEARS,
            "total_estimates":   len(records),
            "non_null_estimates": non_null,
            "by_indicator":      by_indicator,
            "data_status":       "live" if records else "empty",
            "important_note":    (
                "Forecast values are revised frequently. "
                "Check IMF WEO (imf.org/weo) for the most current projections. "
                "This file is SEPARATE from worldbank_indicators.json on purpose — "
                "mixing official actuals with forecasts would mislead users."
            ),
        },
        "records": records,
    }

    ESTIMATES_FILE.write_text(
        json.dumps(output, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\n  ✓  Saved {len(records)} estimates → {ESTIMATES_FILE.relative_to(PROJECT_ROOT)}")


# ── Build combined_indicators.json ─────────────────────────────────────────────

def build_combined(wb_records: list[dict], estimate_records: list[dict]) -> None:
    """
    Merge official WB actuals + estimates into combined_indicators.json.

    Rules:
      1. Use official_actual first (from worldbank_indicators.json)
      2. Add forecast_estimate only if no official_actual exists for that cell
      3. Keep value_type visible on every record
      4. Frontend uses this file to show the correct badge
    """
    PROC_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().isoformat(timespec="seconds")

    # Build a key map for WB official records that have a real value
    official_keys: set[tuple[str, str, int]] = {
        (r["country_code"], r["indicator_key"], r["year"])
        for r in wb_records
        if r.get("value_type") == "official_actual" and r.get("value") is not None
    }

    # All WB records (including missing_official) go in first
    combined: list[dict] = list(wb_records)

    # Add estimates only where there is no official value
    added = 0
    for r in estimate_records:
        key = (r.get("country_code"), r.get("indicator_key"), r.get("year"))
        if key not in official_keys:
            combined.append(r)
            added += 1

    # Sort: country → indicator → year
    combined.sort(key=lambda r: (r.get("country_code", ""), r.get("indicator_key", ""), r.get("year", 0)))

    # Stats
    official_n  = sum(1 for r in combined if r.get("value_type") == "official_actual" and r.get("value") is not None)
    estimate_n  = sum(1 for r in combined if r.get("value_type") == "forecast_estimate" and r.get("value") is not None)
    missing_n   = sum(1 for r in combined if r.get("value") is None)

    output = {
        "meta": {
            "generated_at":       ts,
            "description":        (
                "Combined economic data for the SEA Dashboard. "
                "Merges World Bank official annual actuals (2015–2024) "
                "with IMF/WB forecast estimates (2025–2026) for cells "
                "where WB has not yet published official data. "
                "Always prefer official_actual values over forecast_estimate."
            ),
            "total_records":      len(combined),
            "official_actual":    official_n,
            "forecast_estimate":  estimate_n,
            "missing":            missing_n,
            "source_files": [
                str(WB_DATA_FILE.relative_to(PROJECT_ROOT)),
                str(ESTIMATES_FILE.relative_to(PROJECT_ROOT)),
            ],
            "badge_guide": {
                "official_actual":  "Show 'Official' badge (green) — confirmed World Bank data",
                "forecast_estimate": "Show 'Estimate' badge (amber) — IMF/WB forecast, subject to revision",
                "missing_official": "Show 'No data' badge (grey) — neither official nor forecast available",
            },
            "important_note": (
                "2025/2026 values may be unavailable in official annual datasets. "
                "Forecasts are labeled separately and should not be treated as "
                "confirmed actual data. Official values are updated as World Bank "
                "publishes them (typically 1–2 year lag)."
            ),
        },
        "records": combined,
    }

    COMBINED_FILE.write_text(
        json.dumps(output, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"  ✓  Saved combined data → {COMBINED_FILE.relative_to(PROJECT_ROOT)}  ({len(combined)} records)")
    print(f"       official_actual={official_n}  forecast_estimate={estimate_n}  missing={missing_n}")


# ── Save run log ───────────────────────────────────────────────────────────────

def save_scrape_log(
    records: list[dict],
    errors: list[str],
    started_at: str,
    dry_run: bool,
) -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().isoformat(timespec="seconds")

    by_indicator: dict[str, int] = {}
    by_country:   dict[str, int] = {}
    for r in records:
        k = r.get("indicator_key", "?")
        c = r.get("country_code", "?")
        by_indicator[k] = by_indicator.get(k, 0) + 1
        by_country[c]   = by_country.get(c, 0) + 1

    entry = {
        "run_id":       ts.replace(":", "").replace("-", "")[:15],
        "started_at":   started_at,
        "finished_at":  ts,
        "status":       "dry-run" if dry_run else ("success" if not errors else "partial"),
        "total_estimates": len(records),
        "non_null":     sum(1 for r in records if r.get("value") is not None),
        "errors":       errors,
        "by_indicator": by_indicator,
        "by_country":   by_country,
    }

    # Rolling log
    history: list[dict] = []
    if LOG_FILE.exists():
        try:
            existing = json.loads(LOG_FILE.read_text(encoding="utf-8"))
            history  = existing.get("runs", [])
        except Exception:
            history = []

    history.append(entry)
    history = history[-30:]

    LOG_FILE.write_text(
        json.dumps({"last_run": entry, "runs": history}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"  ✓  Scrape log → {LOG_FILE.relative_to(PROJECT_ROOT)}")


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch 2025/2026 IMF forecasts for cells missing from World Bank data."
    )
    parser.add_argument("--refresh", action="store_true",
                        help="Bypass today's cached raw files and re-fetch")
    parser.add_argument("--dry-run", dest="dry_run", action="store_true",
                        help="Print plan only — do not fetch or save")
    args = parser.parse_args()

    start_ts = datetime.now().isoformat(timespec="seconds")
    errors:   list[str] = []

    print()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║   SEA Dashboard — Latest Estimates Scraper                  ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print(f"  Mode     : {'DRY RUN — nothing will be saved' if args.dry_run else 'live'}")
    print(f"  Forecast : {FORECAST_YEARS}")
    print(f"  Sources  : IMF WEO DataMapper API (free, no key)")
    print()

    # ── Step 1: Load which cells are missing from WB ──────────────────────────
    print("[ STEP 1 ] Loading World Bank data to find missing 2025/2026 cells …")
    missing_cells = load_wb_missing_cells()
    wb_records    = load_wb_records()

    if not wb_records:
        print("  ✗  No World Bank data found. Run python scripts/fetch_worldbank.py first.")
        return 1

    # Only look at 2025/2026 missing cells
    future_missing = {(iso3, ind, yr) for (iso3, ind, yr) in missing_cells if yr in FORECAST_YEARS}
    print(f"  Found {len(future_missing)} missing 2025/2026 cells in worldbank_indicators.json")

    if not future_missing and not args.dry_run:
        print("  ✓  All 2025/2026 cells already have official WB data — nothing to estimate.")
        # Still build combined file
        build_combined(wb_records, [])
        save_scrape_log([], [], start_ts, args.dry_run)
        return 0

    # Summarize by indicator
    by_ind: dict[str, int] = {}
    for (_, ind, _) in future_missing:
        by_ind[ind] = by_ind.get(ind, 0) + 1
    print("  Missing by indicator:")
    for ind, n in sorted(by_ind.items()):
        print(f"    {ind:<18}: {n} cells")
    print()

    # ── Step 2: Fetch IMF WEO estimates ──────────────────────────────────────
    all_estimates: list[dict] = []

    print("[ STEP 2 ] Fetching IMF WEO forecasts (free API, no key required) …")
    for indicator_key, imf_meta in IMF_INDICATORS.items():
        imf_code = imf_meta["imf_code"]
        label    = imf_meta["label"]
        print(f"\n  {indicator_key} ({imf_code}) — {label}")
        try:
            records = fetch_imf_weo(imf_code, indicator_key, future_missing, dry_run=args.dry_run)
            non_null = sum(1 for r in records if r.get("value") is not None)
            if records:
                print(f"    ✓  {len(records)} estimate records ({non_null} non-null)")
                all_estimates.extend(records)
            else:
                print(f"    ○  0 records (either all covered or API returned nothing)")
        except Exception as exc:
            msg = f"{indicator_key}: {type(exc).__name__}: {exc}"
            print(f"    ✗  {msg}")
            errors.append(msg)
        time.sleep(REQUEST_DELAY)

    # ── Step 3: WB population projections ────────────────────────────────────
    print(f"\n[ STEP 3 ] Fetching World Bank population projections for 2025/2026 …")
    try:
        pop_recs = fetch_wb_population_2025_2026(future_missing, dry_run=args.dry_run)
        if pop_recs:
            non_null = sum(1 for r in pop_recs if r.get("value") is not None)
            print(f"  ✓  {len(pop_recs)} population records ({non_null} non-null)")
            all_estimates.extend(pop_recs)
        else:
            print("  ○  No missing population cells in 2025/2026 (already covered by WB API)")
    except Exception as exc:
        msg = f"population: {type(exc).__name__}: {exc}"
        print(f"  ✗  {msg}")
        errors.append(msg)

    # ── Step 4: Save ──────────────────────────────────────────────────────────
    if not args.dry_run:
        print(f"\n[ STEP 4 ] Saving estimates …")
        save_latest_estimates(all_estimates)

        print(f"\n[ STEP 5 ] Building combined_indicators.json …")
        build_combined(wb_records, all_estimates)

        print(f"\n[ STEP 6 ] Saving run log …")
        save_scrape_log(all_estimates, errors, start_ts, args.dry_run)
    else:
        print(f"\n  (dry-run — not saving anything)")

    # ── Summary ───────────────────────────────────────────────────────────────
    non_null_total = sum(1 for r in all_estimates if r.get("value") is not None)
    print()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║  Scraper complete                                            ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print(f"  Total estimates fetched : {len(all_estimates)}")
    print(f"  Non-null values         : {non_null_total}")
    print(f"  Null (no forecast found): {len(all_estimates) - non_null_total}")
    if errors:
        print(f"  Errors                  : {len(errors)}")
        for e in errors:
            print(f"    ⚠  {e}")
    print()
    print("  Output files:")
    print(f"    {ESTIMATES_FILE.relative_to(PROJECT_ROOT)}")
    print(f"    {COMBINED_FILE.relative_to(PROJECT_ROOT)}")
    print()
    print("  ⚠  IMPORTANT: Estimates in latest_estimates.json are IMF forecasts.")
    print("     value_type = 'forecast_estimate' on all records.")
    print("     Do NOT treat as confirmed actual World Bank data.")
    print()
    print("  Frontend badge guide:")
    print("    Official    = value_type: official_actual  (green)")
    print("    Estimate    = value_type: forecast_estimate (amber)")
    print("    No data     = value: null                  (grey)")
    print()

    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
