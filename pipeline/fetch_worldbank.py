#!/usr/bin/env python3
"""
==============================================================================
  World Bank Data Fetcher — SEA Change Intelligence Dashboard v2
  pipeline/fetch_worldbank.py
==============================================================================

Fetches 8 economic indicators from the World Bank Open Data API for
17 countries (11 SEA + 6 partner nations) and saves them in structured
raw and processed formats ready for the dashboard.

No API key required — the World Bank API is completely free and open.

USAGE
─────
    cd pipeline
    python fetch_worldbank.py

    # Force-refresh even if cached raw files exist (same day):
    python fetch_worldbank.py --refresh

OUTPUT DIRECTORIES
──────────────────
    data/raw/worldbank/
        raw_{indicator_key}_{YYYYMMDD}.json   One per indicator, all countries batched

    data/processed/
        worldbank_indicators.json             Master processed file (frontend reads this)

INDICATORS FETCHED
──────────────────
    NY.GDP.MKTP.KD.ZG  →  gdpGrowth     GDP Growth Rate          % YoY
    NY.GDP.MKTP.CD     →  gdpNominal    GDP Nominal              USD Billion
    FP.CPI.TOTL.ZG     →  inflation     Inflation (CPI)          % YoY
    SL.UEM.TOTL.ZS     →  unemployment  Unemployment Rate        % of labor force
    BX.KLT.DINV.WD.GD.ZS → fdiPctGdp  FDI Net Inflows          % of GDP
    NE.EXP.GNFS.CD     →  exports       Exports of G&S           USD Billion
    NE.IMP.GNFS.CD     →  imports       Imports of G&S           USD Billion
    SP.POP.TOTL        →  population    Total Population         Millions

COUNTRIES FETCHED
─────────────────
    11 SEA:  Thailand, Vietnam, Myanmar, Cambodia, Laos, Malaysia, Singapore,
             Indonesia, Philippines, Brunei, Timor-Leste
     6 Partners: China, United States, Japan, India, South Korea, Australia
    (EU is a bloc, not a WB country — excluded)

DATA QUALITY FLAGS
──────────────────
    available  — real WB data, recently published
    old_data   — real WB data, but most recent year for this series is
                 more than 2 years behind END_YEAR (stale series)
    estimated  — forward/backward gap-filled (max 2 consecutive years)
    missing    — no data available, gap too large to fill

WHY ANNUAL ONLY?
────────────────
    The World Bank does NOT publish quarterly GDP, CPI, or trade data.
    All data here is ANNUAL. For quarterly series use national sources:
      Thailand   → NESDC   https://www.nesdc.go.th
      Vietnam    → GSO     https://www.gso.gov.vn
      Singapore  → SingStat https://www.singstat.gov.sg
      Indonesia  → BPS     https://www.bps.go.id
      Malaysia   → DOSM    https://www.dosm.gov.my

MISSING VALUE STRATEGY
───────────────────────
    1. Forward-fill: copy previous year's value (max MAX_FILL_GAP years)
    2. Backward-fill: copy next year's value (max MAX_FILL_GAP years)
    3. Gaps wider than MAX_FILL_GAP are left as null (quality = "missing")
    Common gaps:
      Myanmar post-2022  — disrupted data collection after 2021 coup
      Brunei             — partial coverage for some indicators
      Timor-Leste        — limited statistical capacity
      All countries      — 1–2 year publication lag for latest year

==============================================================================
"""

import csv
import json
import sys
import time
import argparse
from pathlib import Path
from datetime import datetime, date

# Use httpx if installed; fall back to urllib (no extra dependency needed)
try:
    import httpx
    _HTTP = "httpx"
except ImportError:
    import urllib.request
    import urllib.error
    _HTTP = "urllib"


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 1 — CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

START_YEAR  = 2015
END_YEAR    = 2024

# Script is in pipeline/; output dirs are relative to it
SCRIPT_DIR  = Path(__file__).parent
RAW_DIR     = SCRIPT_DIR / "data" / "raw" / "worldbank"
PROC_DIR    = SCRIPT_DIR / "data" / "processed"
LOGS_DIR    = SCRIPT_DIR / "data" / "logs"

# Polite delay between API calls (seconds). WB has no hard rate limit.
REQUEST_DELAY = 0.8

# Maximum retries per request
MAX_RETRIES = 3

# Maximum consecutive years to forward- or backward-fill before giving up
MAX_FILL_GAP = 2

# Threshold: if most recent real data year is this many years behind END_YEAR,
# flag the series as "old_data" rather than "available"
OLD_DATA_THRESHOLD = 2   # e.g. latest year ≤ END_YEAR - 2  →  old_data


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 2 — COUNTRY REGISTRY
# ══════════════════════════════════════════════════════════════════════════════
# World Bank URL uses 2-letter WB country codes (mostly ISO2, but Timor-Leste
# is "TP" at the WB, not "TL" which is its ISO2).

COUNTRIES: dict[str, dict] = {
    # ── Southeast Asia ──────────────────────────────────────────────
    "TH": {"name": "Thailand",      "iso3": "THA", "flag": "🇹🇭", "region": "Southeast Asia"},
    "VN": {"name": "Vietnam",       "iso3": "VNM", "flag": "🇻🇳", "region": "Southeast Asia"},
    "MM": {"name": "Myanmar",       "iso3": "MMR", "flag": "🇲🇲", "region": "Southeast Asia"},
    "KH": {"name": "Cambodia",      "iso3": "KHM", "flag": "🇰🇭", "region": "Southeast Asia"},
    "LA": {"name": "Laos",          "iso3": "LAO", "flag": "🇱🇦", "region": "Southeast Asia"},
    "MY": {"name": "Malaysia",      "iso3": "MYS", "flag": "🇲🇾", "region": "Southeast Asia"},
    "SG": {"name": "Singapore",     "iso3": "SGP", "flag": "🇸🇬", "region": "Southeast Asia"},
    "ID": {"name": "Indonesia",     "iso3": "IDN", "flag": "🇮🇩", "region": "Southeast Asia"},
    "PH": {"name": "Philippines",   "iso3": "PHL", "flag": "🇵🇭", "region": "Southeast Asia"},
    "BN": {"name": "Brunei",        "iso3": "BRN", "flag": "🇧🇳", "region": "Southeast Asia"},
    "TP": {"name": "Timor-Leste",   "iso3": "TLS", "flag": "🇹🇱", "region": "Southeast Asia"},
    # ── Partner nations ──────────────────────────────────────────────
    "CN": {"name": "China",         "iso3": "CHN", "flag": "🇨🇳", "region": "East Asia"},
    "US": {"name": "United States", "iso3": "USA", "flag": "🇺🇸", "region": "Americas"},
    "JP": {"name": "Japan",         "iso3": "JPN", "flag": "🇯🇵", "region": "East Asia"},
    "IN": {"name": "India",         "iso3": "IND", "flag": "🇮🇳", "region": "South Asia"},
    "KR": {"name": "South Korea",   "iso3": "KOR", "flag": "🇰🇷", "region": "East Asia"},
    "AU": {"name": "Australia",     "iso3": "AUS", "flag": "🇦🇺", "region": "Oceania"},
}

# Reverse lookup: iso3 → {name, iso2, flag, region}
ISO3_META: dict[str, dict] = {
    v["iso3"]: {**v, "iso2": k} for k, v in COUNTRIES.items()
}


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 3 — INDICATOR DEFINITIONS
# ══════════════════════════════════════════════════════════════════════════════

INDICATORS: dict[str, dict] = {
    "gdpGrowth": {
        "wb_code":   "NY.GDP.MKTP.KD.ZG",
        "label":     "GDP Growth Rate",
        "unit":      "% YoY",
        "scale":     1,
        "direction": "higher_is_better",
        "note": (
            "Annual GDP growth at constant prices. "
            "World Bank does NOT publish quarterly GDP. "
            "For quarterly data use national statistics offices."
        ),
    },
    "gdpNominal": {
        "wb_code":   "NY.GDP.MKTP.CD",
        "label":     "GDP (Current USD)",
        "unit":      "USD Billion",
        "scale":     1_000_000_000,
        "direction": "higher_is_better",
        "note": "GDP in current US dollars, divided by 1 billion. Not inflation-adjusted.",
    },
    "inflation": {
        "wb_code":   "FP.CPI.TOTL.ZG",
        "label":     "Inflation (CPI)",
        "unit":      "% YoY",
        "scale":     1,
        "direction": "higher_is_worse",
        "note": (
            "Annual average Consumer Price Index change. "
            "Myanmar post-2022 figures are IMF estimates. "
            "Monthly CPI available from IMF IFS database."
        ),
    },
    "unemployment": {
        "wb_code":   "SL.UEM.TOTL.ZS",
        "label":     "Unemployment Rate",
        "unit":      "% of labor force",
        "scale":     1,
        "direction": "higher_is_worse",
        "note": (
            "ILO modelled estimates — may differ from nationally reported figures. "
            "Brunei has partial coverage."
        ),
    },
    "fdiPctGdp": {
        "wb_code":   "BX.KLT.DINV.WD.GD.ZS",
        "label":     "FDI Net Inflows",
        "unit":      "% of GDP",
        "scale":     1,
        "direction": "higher_is_better",
        "note": (
            "Balance-of-payments FDI net inflows as % of GDP. "
            "Negative values mean net outflow. "
            "Singapore may show large swings due to round-tripping through holding companies."
        ),
    },
    "exports": {
        "wb_code":   "NE.EXP.GNFS.CD",
        "label":     "Exports of Goods & Services",
        "unit":      "USD Billion",
        "scale":     1_000_000_000,
        "direction": "higher_is_better",
        "note": (
            "Exports of goods AND services in current USD, scaled to billions. "
            "Singapore's figure includes massive re-export component — "
            "legitimately exceeds $900B in recent years."
        ),
    },
    "imports": {
        "wb_code":   "NE.IMP.GNFS.CD",
        "label":     "Imports of Goods & Services",
        "unit":      "USD Billion",
        "scale":     1_000_000_000,
        "direction": "lower_is_better",
        "note": "Imports of goods AND services in current USD, scaled to billions.",
    },
    "population": {
        "wb_code":   "SP.POP.TOTL",
        "label":     "Total Population",
        "unit":      "Millions",
        "scale":     1_000_000,
        "direction": "neutral",
        "note": "Mid-year total population estimate, scaled to millions.",
    },
}


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 4 — HTTP HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def build_url(wb_code: str) -> str:
    """
    Build the World Bank API URL for all 17 countries and one indicator.

    All country codes are batched with semicolons so we make 1 HTTP request
    per indicator (8 requests total for all indicators).

    Example URL:
      https://api.worldbank.org/v2/country/TH;VN;MM;KH;LA;MY;SG;ID;PH;BN;TP;CN;US;JP;IN;KR;AU
        /indicator/NY.GDP.MKTP.KD.ZG
        ?format=json&per_page=300&date=2015:2024
    """
    country_str = ";".join(COUNTRIES.keys())
    n_records   = len(COUNTRIES) * (END_YEAR - START_YEAR + 1)
    per_page    = max(500, n_records + 50)
    return (
        f"https://api.worldbank.org/v2/country/{country_str}"
        f"/indicator/{wb_code}"
        f"?format=json&per_page={per_page}&date={START_YEAR}:{END_YEAR}"
    )


def _get_json(url: str) -> list:
    """GET the URL and return parsed JSON. Works with httpx or stdlib urllib."""
    if _HTTP == "httpx":
        resp = httpx.get(url, timeout=30, follow_redirects=True)
        resp.raise_for_status()
        return resp.json()
    else:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))


def fetch_with_retry(url: str) -> list | None:
    """
    Fetch a URL and return the World Bank data array (payload[1]).
    Retries up to MAX_RETRIES times with exponential back-off.
    Returns None if all retries fail.
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            payload = _get_json(url)

            # WB always returns [metadata_dict, data_array]
            if not isinstance(payload, list) or len(payload) < 2:
                print(f"    ⚠  Unexpected API format on attempt {attempt}")
                continue

            meta_block  = payload[0]
            data_array  = payload[1] or []

            if meta_block.get("pages", 1) > 1:
                print(
                    f"    ⚠  Response has {meta_block['pages']} pages "
                    f"(per_page={meta_block.get('per_page')}, total={meta_block.get('total')}) "
                    "— some records may be cut off. Consider increasing per_page."
                )

            return data_array

        except Exception as exc:
            print(f"    ✗  Attempt {attempt}/{MAX_RETRIES}: {type(exc).__name__}: {exc}")
            if attempt < MAX_RETRIES:
                wait = 2 ** attempt  # 2s → 4s → 8s
                print(f"    ↻  Retrying in {wait}s …")
                time.sleep(wait)

    return None


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 5 — FETCH ALL INDICATORS
# ══════════════════════════════════════════════════════════════════════════════

def fetch_all(use_cached: bool = True) -> tuple[dict[str, list], dict[str, str]]:
    """
    Fetch all 8 indicators for all 17 countries from the World Bank API.

    Returns:
      raw_data:  { indicator_key → list of API row dicts }
      url_map:   { indicator_key → source URL }

    If use_cached=True (default), tries to load today's raw file first.
    Pass --refresh on the command line to bypass the cache.
    """
    today       = date.today().strftime("%Y%m%d")
    raw_data:   dict[str, list] = {}
    url_map:    dict[str, str]  = {}

    for i, (ind_key, ind_meta) in enumerate(INDICATORS.items(), 1):
        label   = ind_meta["label"]
        wb_code = ind_meta["wb_code"]
        url     = build_url(wb_code)
        url_map[ind_key] = url

        raw_file = RAW_DIR / f"raw_{ind_key}_{today}.json"

        # ── Try cache ─────────────────────────────────────────────────────────
        if use_cached and raw_file.exists():
            print(f"  [{i}/{len(INDICATORS)}] {label}  (📂 from cache: {raw_file.name})")
            with open(raw_file, encoding="utf-8") as f:
                raw_data[ind_key] = json.load(f)
            continue

        # ── Live fetch ────────────────────────────────────────────────────────
        print(f"\n  [{i}/{len(INDICATORS)}] {label}  ({wb_code})")
        print(f"    GET {url[:80]}…")
        data = fetch_with_retry(url)

        if data is None:
            print(f"    ✗  FAILED — skipping {label}")
            raw_data[ind_key] = []
        else:
            # Count non-null points
            valid = sum(1 for row in data if row.get("value") is not None)
            null  = sum(1 for row in data if row.get("value") is None)
            print(f"    ✓  {valid} data points  |  {null} null from API")

            # Save raw file
            RAW_DIR.mkdir(parents=True, exist_ok=True)
            with open(raw_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"    💾 Saved → {raw_file.name}")
            raw_data[ind_key] = data

        time.sleep(REQUEST_DELAY)

    return raw_data, url_map


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 6 — BUILD FULL GRID
# ══════════════════════════════════════════════════════════════════════════════

def build_grid(raw_data: dict[str, list]) -> dict:
    """
    Organise the fetched data into a 3-level nested dict:
        grid[iso3][ind_key][year] = {"value": float, "is_filled": bool, ...} | None

    Initialises all cells to None, then fills in real API values.
    """
    # Initialise every cell to None
    grid: dict[str, dict[str, dict[int, dict | None]]] = {}
    for wb2, meta in COUNTRIES.items():
        iso3 = meta["iso3"]
        grid[iso3] = {
            ind_key: {yr: None for yr in range(START_YEAR, END_YEAR + 1)}
            for ind_key in INDICATORS
        }

    # Populate with real API values
    for ind_key, data_rows in raw_data.items():
        ind_meta = INDICATORS[ind_key]
        scale    = ind_meta["scale"]

        for row in data_rows:
            raw_val = row.get("value")
            if raw_val is None:
                continue  # API null — will be handled by fill step

            wb_code_country = row.get("country", {}).get("id", "")
            c_meta = COUNTRIES.get(wb_code_country)
            if not c_meta:
                continue  # unexpected country (shouldn't happen)

            iso3 = c_meta["iso3"]
            year = int(row["date"])

            if START_YEAR <= year <= END_YEAR:
                grid[iso3][ind_key][year] = {
                    "value":      round(float(raw_val) / scale, 6),
                    "raw_value":  float(raw_val),
                    "is_filled":  False,
                    "is_estimate": False,
                }

    return grid


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 7 — FILL MISSING VALUES
# ══════════════════════════════════════════════════════════════════════════════

def fill_missing(grid: dict) -> tuple[dict, int]:
    """
    Fill gaps in each country-indicator time series.

    Strategy:
      1. FORWARD-FILL  (left → right): copy the previous year's value.
         Repeat for up to MAX_FILL_GAP consecutive missing years.
      2. BACKWARD-FILL (right → left): copy the next year's value.
         Same limit. Handles the case where the first few years are missing.

    Filled values are flagged is_filled=True so the frontend can display
    them differently (dashed line, lighter colour, asterisk).
    Returns (updated_grid, fill_count).
    """
    years      = list(range(START_YEAR, END_YEAR + 1))
    fill_count = 0

    for iso3 in grid:
        for ind_key in grid[iso3]:
            series = grid[iso3][ind_key]

            # ── Forward fill ────────────────────────────────────────────────
            last_known = None
            gap        = 0
            for yr in years:
                cell = series[yr]
                if cell is not None:
                    last_known = cell["value"]
                    gap = 0
                elif last_known is not None and gap < MAX_FILL_GAP:
                    series[yr] = {
                        "value":      last_known,
                        "raw_value":  None,
                        "is_filled":  True,
                        "is_estimate": True,
                    }
                    fill_count += 1
                    gap += 1
                else:
                    gap += 1

            # ── Backward fill ───────────────────────────────────────────────
            first_known = None
            gap         = 0
            for yr in reversed(years):
                cell = series[yr]
                if cell is not None:
                    first_known = cell["value"]
                    gap = 0
                elif first_known is not None and gap < MAX_FILL_GAP:
                    series[yr] = {
                        "value":      first_known,
                        "raw_value":  None,
                        "is_filled":  True,
                        "is_estimate": True,
                    }
                    fill_count += 1
                    gap += 1
                else:
                    gap += 1

    print(f"\n  Gap-fill cells applied : {fill_count}")
    return grid, fill_count


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 8 — ASSIGN DATA QUALITY FLAGS
# ══════════════════════════════════════════════════════════════════════════════

def assign_quality(grid: dict) -> dict:
    """
    Annotate each cell in the grid with a data_quality flag:

      available  — real WB data, series is up-to-date (latest real year ≥ END_YEAR - OLD_DATA_THRESHOLD)
      old_data   — real WB data, but most recent non-filled year is stale
                   (latest real year < END_YEAR - OLD_DATA_THRESHOLD)
      estimated  — forward/backward gap-filled value
      missing    — no data at all (cell is None after fill)

    The function also adds null-sentinel dicts for missing cells so the
    processed JSON can record the gap explicitly.
    """
    years = list(range(START_YEAR, END_YEAR + 1))

    for iso3 in grid:
        for ind_key in grid[iso3]:
            series = grid[iso3][ind_key]

            # Find the most recent real (non-filled) year for this series
            latest_real_yr = None
            for yr in years:
                cell = series[yr]
                if cell is not None and not cell.get("is_filled", False):
                    latest_real_yr = yr

            is_stale = (
                latest_real_yr is not None
                and latest_real_yr <= END_YEAR - OLD_DATA_THRESHOLD
            )

            for yr in years:
                cell = series[yr]
                if cell is None:
                    # Missing — add explicit null sentinel
                    series[yr] = {
                        "value":       None,
                        "raw_value":   None,
                        "is_filled":   False,
                        "is_estimate": False,
                        "data_quality": "missing",
                    }
                elif cell.get("is_filled"):
                    cell["data_quality"] = "estimated"
                elif is_stale:
                    cell["data_quality"] = "old_data"
                else:
                    cell["data_quality"] = "available"

    return grid


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 9 — VALIDATION / SANITY CHECK
# ══════════════════════════════════════════════════════════════════════════════

# Plausible value ranges for real (non-null) cells
EXPECTED_RANGES: dict[str, tuple[float, float]] = {
    "gdpGrowth":    (-35.0,   20.0),   # % (Myanmar coup drop was ~18%)
    "gdpNominal":   (  0.1, 30_000.0), # USD B (US is ~27 000B)
    "inflation":    (-10.0,  200.0),   # % (Myanmar 2023 was ~180%)
    "unemployment": (  0.0,   40.0),   # %
    "fdiPctGdp":    (-20.0,   60.0),   # % of GDP (Singapore can be high)
    "exports":      (  0.0, 5_000.0),  # USD B (US ~3 500B, China ~3 600B, Singapore re-exports ~970B)
    "imports":      (  0.0, 5_000.0),  # USD B (US imports exceeded $4 100B in 2024)
    "population":   (  0.1, 1_500.0),  # Millions (China/India ~1400M)
}


def validate(grid: dict) -> None:
    """Print any values outside expected ranges (doesn't remove them)."""
    issues = []
    for iso3 in grid:
        for ind_key in grid[iso3]:
            lo, hi = EXPECTED_RANGES.get(ind_key, (-1e9, 1e9))
            for yr in grid[iso3][ind_key]:
                cell = grid[iso3][ind_key][yr]
                if cell is None or cell["value"] is None:
                    continue
                v = cell["value"]
                if not (lo <= v <= hi):
                    meta = ISO3_META[iso3]
                    issues.append(
                        f"    {meta['flag']} {iso3} {yr} [{ind_key}] = {v:.3f}"
                        f"  (expected {lo} – {hi})"
                    )
    if issues:
        print(f"\n  ⚠  {len(issues)} out-of-range value(s) — verify manually:")
        for line in issues:
            print(line)
    else:
        print("  ✓  All fetched values within expected ranges")


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 10 — SAVE RAW CSV  (per-indicator, long format)
# ══════════════════════════════════════════════════════════════════════════════

def save_raw_csv(raw_data: dict[str, list], url_map: dict[str, str]) -> None:
    """
    Save raw API responses as a combined long-format CSV for auditability.
    One row per country-indicator-year. Includes raw (unscaled) values.
    """
    ts      = date.today().strftime("%Y%m%d")
    path    = RAW_DIR / f"raw_all_{ts}.csv"
    rows    = []

    for ind_key, data_rows in raw_data.items():
        ind_meta = INDICATORS[ind_key]
        for row in data_rows:
            wb2 = row.get("country", {}).get("id", "")
            c   = COUNTRIES.get(wb2)
            rows.append({
                "wb2":            wb2,
                "iso3":           c["iso3"]  if c else "",
                "country_name":   c["name"]  if c else row.get("country", {}).get("value", ""),
                "year":           row.get("date"),
                "indicator_key":  ind_key,
                "wb_code":        ind_meta["wb_code"],
                "label":          ind_meta["label"],
                "unit":           ind_meta["unit"],
                "raw_value":      row.get("value"),
                "source_url":     url_map.get(ind_key, ""),
            })

    fields = ["wb2", "iso3", "country_name", "year",
              "indicator_key", "wb_code", "label", "unit", "raw_value", "source_url"]

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in sorted(rows, key=lambda x: (x["iso3"], x["indicator_key"], x["year"] or "")):
            w.writerow(r)

    print(f"  ✓  Raw CSV    → {path.relative_to(SCRIPT_DIR)}  ({len(rows)} rows)")


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 11 — SAVE PROCESSED JSON  (frontend reads this)
# ══════════════════════════════════════════════════════════════════════════════

ANNUAL_DATA_NOTE = (
    "World Bank publishes ANNUAL data only — no quarterly breakdown available. "
    "Data typically has a 1–2 year publication lag "
    f"(in {date.today().year}, the most recent confirmed year for most countries is {END_YEAR - 1} or {END_YEAR - 2}). "
    "For quarterly GDP / CPI, use national statistics offices: "
    "Thailand → NESDC, Vietnam → GSO, Singapore → SingStat, Indonesia → BPS, Malaysia → DOSM."
)


def save_processed_json(
    grid: dict,
    url_map: dict[str, str],
    raw_data: dict[str, list],
) -> None:
    """
    Build and save the master processed JSON file at data/processed/worldbank_indicators.json.

    Structure:
    {
      "meta": { generated_at, source, annual_data_note, year_range,
                countries_fetched, indicators_fetched, data_status },
      "indicators": { key → { wb_code, label, unit, scale, direction, note } },
      "records": [
        { source_url, last_updated, country_code, country_name,
          indicator_code, indicator_key, year, value, unit, data_quality }
      ]
    }
    """
    today_str = date.today().isoformat()
    ts        = datetime.now().isoformat(timespec="seconds")

    # Count real (non-missing, non-estimated) records
    real_count = 0
    for iso3 in grid:
        for ind_key in grid[iso3]:
            for yr in grid[iso3][ind_key]:
                cell = grid[iso3][ind_key][yr]
                if cell and cell["value"] is not None and not cell.get("is_filled"):
                    real_count += 1

    # Build indicator meta (strip internal-only fields)
    ind_meta_clean = {
        k: {
            "wb_code":   v["wb_code"],
            "label":     v["label"],
            "unit":      v["unit"],
            "scale":     v["scale"],
            "direction": v["direction"],
            "note":      v["note"],
        }
        for k, v in INDICATORS.items()
    }

    # Build records list
    records = []
    years   = list(range(START_YEAR, END_YEAR + 1))

    for iso3 in sorted(grid):
        c_meta   = ISO3_META[iso3]
        for ind_key in INDICATORS:
            ind_meta = INDICATORS[ind_key]
            src_url  = url_map.get(ind_key, f"https://api.worldbank.org/v2/country/{c_meta['iso2']}/indicator/{ind_meta['wb_code']}?format=json")

            for yr in years:
                cell = grid[iso3][ind_key][yr]
                if cell is None:
                    continue  # shouldn't happen after assign_quality, but guard

                records.append({
                    "source_url":     src_url,
                    "last_updated":   today_str,
                    "country_code":   iso3,
                    "country_name":   c_meta["name"],
                    "indicator_code": ind_meta["wb_code"],
                    "indicator_key":  ind_key,
                    "year":           yr,
                    "value":          cell["value"],  # null if missing
                    "unit":           ind_meta["unit"],
                    "data_quality":   cell.get("data_quality", "available"),
                })

    output = {
        "meta": {
            "generated_at":        ts,
            "source":              "World Bank Open Data API",
            "api_base":            "https://api.worldbank.org/v2",
            "annual_data_note":    ANNUAL_DATA_NOTE,
            "year_range":          [START_YEAR, END_YEAR],
            "countries_fetched":   len(COUNTRIES),
            "indicators_fetched":  len(INDICATORS),
            "total_records":       len(records),
            "real_data_points":    real_count,
            "data_status":         "live",
        },
        "indicators": ind_meta_clean,
        "records":    records,
    }

    PROC_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROC_DIR / "worldbank_indicators.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"  ✓  Processed JSON → {out_path.relative_to(SCRIPT_DIR)}  ({len(records)} records)")


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 12 — MISSING DATA REPORT  (CSV)
# ══════════════════════════════════════════════════════════════════════════════

def explain_missing(iso3: str, year: int, ind_key: str) -> str:
    """Return a one-line explanation for why a particular cell is missing."""
    if iso3 == "MMR" and year >= 2022:
        return "Post-coup (2021+): World Bank data collection disrupted; IMF estimates only"
    if iso3 == "BRN" and ind_key == "unemployment":
        return "Brunei: partial unemployment coverage in World Bank database"
    if iso3 == "TLS":
        return "Timor-Leste: limited statistical capacity; data often unavailable"
    if year >= END_YEAR - 1:
        return f"{year} data not yet published (World Bank 1–2 year publication lag)"
    if ind_key == "fdiPctGdp" and year >= END_YEAR - 2:
        return f"FDI data often delayed an extra year beyond other indicators"
    return "Not available from World Bank for this country-year combination"


def save_missing_report(grid: dict) -> None:
    """Write a CSV reporting all missing and estimated cells after filling."""
    ts   = date.today().strftime("%Y%m%d")
    path = RAW_DIR / f"missing_report_{ts}.csv"
    gaps = []

    for iso3 in sorted(grid):
        for ind_key, ind_meta in INDICATORS.items():
            for yr, cell in grid[iso3][ind_key].items():
                q = cell.get("data_quality", "")
                if q in ("missing", "estimated"):
                    gaps.append({
                        "iso3":          iso3,
                        "country_name":  ISO3_META[iso3]["name"],
                        "year":          yr,
                        "indicator_key": ind_key,
                        "wb_code":       ind_meta["wb_code"],
                        "quality":       q,
                        "reason":        explain_missing(iso3, yr, ind_key) if q == "missing" else "Forward/backward filled from adjacent year",
                    })

    fields = ["iso3", "country_name", "year", "indicator_key", "wb_code", "quality", "reason"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(gaps)

    missing_n   = sum(1 for g in gaps if g["quality"] == "missing")
    estimated_n = sum(1 for g in gaps if g["quality"] == "estimated")
    total_cells = len(COUNTRIES) * len(INDICATORS) * (END_YEAR - START_YEAR + 1)

    print(f"\n  Data coverage  ({total_cells} total cells):")
    print(f"    ✓  Real data       : {total_cells - missing_n - estimated_n}  ({round(100*(total_cells - missing_n - estimated_n)/total_cells, 1)}%)")
    print(f"    ~  Estimated/filled: {estimated_n}  ({round(100*estimated_n/total_cells, 1)}%)")
    print(f"    ✗  Still missing   : {missing_n}  ({round(100*missing_n/total_cells, 1)}%)")

    if missing_n > 0:
        print(f"\n  Missing per country:")
        for iso3 in sorted(ISO3_META):
            n = sum(1 for g in gaps if g["iso3"] == iso3 and g["quality"] == "missing")
            if n > 0:
                flag = ISO3_META[iso3]["flag"]
                note = ""
                if iso3 == "MMR":
                    note = "  ← post-coup disruption"
                elif iso3 == "TLS":
                    note = "  ← limited statistical capacity"
                print(f"    {flag}  {ISO3_META[iso3]['name']:<16}: {n:3d} gap(s){note}")

    print(f"\n  ✓  Missing report → {path.relative_to(SCRIPT_DIR)}  ({len(gaps)} flagged cells)")


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 13 — CONSOLE SUMMARY
# ══════════════════════════════════════════════════════════════════════════════

def save_log_json(
    grid: dict,
    url_map: dict[str, str],
    errors: list[str],
    start_ts: str,
    used_cache: bool,
) -> None:
    """
    Write a structured run log to data/logs/worldbank_log.json.

    Records metadata about this specific pipeline run:
      - When it ran and how long
      - How many records were fetched
      - Per-country and per-indicator coverage stats
      - Any errors that occurred
      - Whether cache was used

    The log file keeps the last 30 runs as a history array so you can
    track data freshness and diagnose recurring gaps over time.
    """
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOGS_DIR / "worldbank_log.json"

    ts_now = datetime.now().isoformat(timespec="seconds")

    # ── Per-indicator counts ──────────────────────────────────────────────────
    by_indicator: dict[str, dict] = {}
    for ind_key in INDICATORS:
        available_n  = 0
        estimated_n  = 0
        old_data_n   = 0
        missing_n    = 0
        for iso3 in grid:
            for yr, cell in grid[iso3][ind_key].items():
                q = cell.get("data_quality", "missing")
                if q == "available":   available_n  += 1
                elif q == "estimated": estimated_n  += 1
                elif q == "old_data":  old_data_n   += 1
                else:                  missing_n    += 1
        by_indicator[ind_key] = {
            "wb_code":     INDICATORS[ind_key]["wb_code"],
            "label":       INDICATORS[ind_key]["label"],
            "available":   available_n,
            "estimated":   estimated_n,
            "old_data":    old_data_n,
            "missing":     missing_n,
            "source_url":  url_map.get(ind_key, ""),
        }

    # ── Per-country counts ────────────────────────────────────────────────────
    by_country: dict[str, dict] = {}
    for iso3 in sorted(grid):
        meta = ISO3_META[iso3]
        available_n  = 0
        estimated_n  = 0
        old_data_n   = 0
        missing_n    = 0
        for ind_key in grid[iso3]:
            for yr, cell in grid[iso3][ind_key].items():
                q = cell.get("data_quality", "missing")
                if q == "available":   available_n  += 1
                elif q == "estimated": estimated_n  += 1
                elif q == "old_data":  old_data_n   += 1
                else:                  missing_n    += 1
        total = available_n + estimated_n + old_data_n + missing_n
        by_country[iso3] = {
            "name":       meta["name"],
            "flag":       meta["flag"],
            "region":     meta["region"],
            "available":  available_n,
            "estimated":  estimated_n,
            "old_data":   old_data_n,
            "missing":    missing_n,
            "coverage_pct": round(100 * available_n / total, 1) if total else 0,
        }

    # ── Totals across all cells ───────────────────────────────────────────────
    total_cells   = len(COUNTRIES) * len(INDICATORS) * (END_YEAR - START_YEAR + 1)
    all_available = sum(v["available"] for v in by_country.values())
    all_estimated = sum(v["estimated"] for v in by_country.values())
    all_old_data  = sum(v["old_data"]  for v in by_country.values())
    all_missing   = sum(v["missing"]   for v in by_country.values())

    # ── Build the run entry ───────────────────────────────────────────────────
    run_entry = {
        "run_id":          ts_now,
        "fetched_at":      ts_now,
        "started_at":      start_ts,
        "status":          "success" if not errors else "partial",
        "used_cache":      used_cache,
        "countries":       len(COUNTRIES),
        "indicators":      len(INDICATORS),
        "year_range":      [START_YEAR, END_YEAR],
        "total_cells":     total_cells,
        "available":       all_available,
        "estimated":       all_estimated,
        "old_data":        all_old_data,
        "missing":         all_missing,
        "coverage_pct":    round(100 * all_available / total_cells, 1),
        "errors":          errors,
        "by_indicator":    by_indicator,
        "by_country":      by_country,
        "note": (
            "Official economic indicators may be annual and delayed, "
            "while news signals update faster. "
            "World Bank data has a 1–2 year publication lag."
        ),
    }

    # ── Append to history (keep last 30 runs) ────────────────────────────────
    history: list[dict] = []
    if log_path.exists():
        try:
            existing = json.loads(log_path.read_text(encoding="utf-8"))
            history  = existing.get("runs", [])
        except Exception:
            history  = []

    history.append(run_entry)
    if len(history) > 30:
        history = history[-30:]

    log_output = {
        "_meta": {
            "description": "World Bank fetch run log — SEA Change Intelligence Dashboard",
            "script":      "pipeline/fetch_worldbank.py",
            "log_version": "1.0",
            "max_history": 30,
        },
        "last_run": run_entry,
        "runs":     history,
    }

    log_path.write_text(json.dumps(log_output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  ✓  Run log      → {log_path.relative_to(SCRIPT_DIR)}")


def print_limitations() -> None:
    """Print the key limitations that should be communicated to dashboard users."""
    W = 72
    print()
    print("━" * W)
    print("  ⚠  KEY LIMITATIONS FOR DASHBOARD USERS")
    print("━" * W)
    sections = [
        (
            "ANNUAL DATA ONLY",
            [
                "World Bank publishes data annually — no quarterly breakdown exists.",
                f"Dashboard charts showing quarters will have annual figures as anchors.",
                "For true quarterly series: NESDC (Thailand), GSO (Vietnam),",
                "SingStat (Singapore), BPS (Indonesia), DOSM (Malaysia).",
            ],
        ),
        (
            "PUBLICATION LAG",
            [
                "Most indicators have a 1–2 year delay before publication.",
                f"In {date.today().year}, confirmed data for most countries is up to {END_YEAR - 1}.",
                f"{END_YEAR} data is often preliminary or entirely absent.",
            ],
        ),
        (
            "MYANMAR DATA",
            [
                "Since the Feb 2021 coup, WB access to Myanmar statistics is limited.",
                "Post-2022 values are IMF estimates — treat with caution.",
                "Exports and imports series have significant gaps.",
            ],
        ),
        (
            "FDI METRIC (% OF GDP)",
            [
                "BX.KLT.DINV.WD.GD.ZS is FDI as % of GDP, not absolute USD.",
                "Negative values mean net capital outflow — this is valid.",
                "Singapore often shows large swings due to holding-company flows.",
            ],
        ),
        (
            "CURRENT USD VALUES",
            [
                "Exports, imports, GDP nominal are all in CURRENT USD.",
                "Long-period comparisons are affected by USD inflation.",
                "Use GDP growth (constant prices) for real comparisons.",
            ],
        ),
    ]
    for title, lines in sections:
        print(f"\n  [{title}]")
        for line in lines:
            print(f"    {line}")
    print()
    print("━" * W)
    print()


def print_indicator_table() -> None:
    """Print a reference table of all 8 indicator codes."""
    W = 72
    print()
    print("=" * W)
    print("  WORLD BANK INDICATOR CODES USED IN THIS FETCH")
    print("=" * W)
    fmt = "  {:<14}  {:<28}  {}"
    print(fmt.format("KEY", "WB CODE", "UNIT"))
    print("  " + "─" * (W - 2))
    for k, m in INDICATORS.items():
        print(fmt.format(k, m["wb_code"], m["unit"]))
    print()


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch World Bank indicators for SEA dashboard")
    parser.add_argument("--refresh", action="store_true",
                        help="Ignore today's cached raw files and re-fetch from API")
    args = parser.parse_args()

    use_cached = not args.refresh
    start_ts   = datetime.now().isoformat(timespec="seconds")
    errors: list[str] = []

    print()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║   SEA Change Dashboard — World Bank Fetcher v2              ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print(f"  Countries  : {len(COUNTRIES)} ({sum(1 for c in COUNTRIES.values() if c['region'] == 'Southeast Asia')} SEA + {sum(1 for c in COUNTRIES.values() if c['region'] != 'Southeast Asia')} partners)")
    print(f"  Indicators : {len(INDICATORS)}  ({', '.join(INDICATORS.keys())})")
    print(f"  Years      : {START_YEAR}–{END_YEAR}  ({END_YEAR - START_YEAR + 1} years)")
    print(f"  HTTP lib   : {_HTTP}")
    cache_note = "skip — re-fetching all" if args.refresh else "use today's raw files if present"
    print(f"  Cache mode : {cache_note}")
    print(f"  Raw dir    : {RAW_DIR.relative_to(SCRIPT_DIR)}/")
    print(f"  Output     : {PROC_DIR.relative_to(SCRIPT_DIR)}/worldbank_indicators.json")

    print_indicator_table()

    # ── STEP 1: Fetch ─────────────────────────────────────────────────────────
    print("[ STEP 1 ] Fetching from World Bank Open Data API …")
    print(f"  8 requests total — all {len(COUNTRIES)} countries batched per indicator\n")
    raw_data, url_map = fetch_all(use_cached=use_cached)

    total_raw = sum(len(v) for v in raw_data.values())
    if total_raw == 0:
        errors.append("No data fetched — possible network failure")
        print("\n✗  No data fetched at all. Check your internet connection and retry.")
        sys.exit(1)

    # Track any indicators that came back empty
    for ind_key, rows in raw_data.items():
        if not rows:
            errors.append(f"Indicator '{ind_key}' returned 0 rows from API")

    # ── STEP 2: Build grid ────────────────────────────────────────────────────
    print("\n[ STEP 2 ] Building data grid …")
    grid = build_grid(raw_data)

    # ── STEP 3: Fill missing values ───────────────────────────────────────────
    print("\n[ STEP 3 ] Filling missing values (forward + backward fill, max 2 years) …")
    grid, _ = fill_missing(grid)

    # ── STEP 4: Assign quality flags ──────────────────────────────────────────
    print("\n[ STEP 4 ] Assigning data quality flags …")
    grid = assign_quality(grid)
    print("  ✓  Quality flags: available | estimated | old_data | missing")

    # ── STEP 5: Validate ──────────────────────────────────────────────────────
    print("\n[ STEP 5 ] Validating fetched values …")
    validate(grid)

    # ── STEP 6: Save raw CSV ──────────────────────────────────────────────────
    print("\n[ STEP 6 ] Saving raw CSV …")
    save_raw_csv(raw_data, url_map)

    # ── STEP 7: Save processed JSON ───────────────────────────────────────────
    print("\n[ STEP 7 ] Saving processed JSON for frontend …")
    save_processed_json(grid, url_map, raw_data)

    # ── STEP 8: Missing data report ───────────────────────────────────────────
    print("\n[ STEP 8 ] Generating missing data report …")
    save_missing_report(grid)

    # ── STEP 9: Write run log ─────────────────────────────────────────────────
    print("\n[ STEP 9 ] Writing run log …")
    save_log_json(grid, url_map, errors, start_ts, use_cached)

    # ── Summary ───────────────────────────────────────────────────────────────
    print_limitations()

    print("╔══════════════════════════════════════════════════════════════╗")
    print("║  ✓  Done!                                                    ║")
    print("║                                                               ║")
    print("║  Output files:                                                ║")
    print("║    data/processed/worldbank_indicators.json  ← frontend reads ║")
    print("║    data/raw/worldbank/raw_*.json              ← raw per-ind   ║")
    print("║    data/raw/worldbank/raw_all_*.csv           ← audit trail   ║")
    print("║    data/logs/worldbank_log.json               ← run history   ║")
    print("║                                                               ║")
    print("║  Note:                                                        ║")
    print("║    Official economic indicators may be annual and delayed,    ║")
    print("║    while news signals update faster.                          ║")
    print("║                                                               ║")
    print("║  Next steps:                                                  ║")
    print("║  1. Review data/raw/worldbank/missing_report_*.csv            ║")
    print("║  2. Rebuild the frontend (next build / next dev restart)      ║")
    print("║  3. Run again weekly — WB updates data on a rolling basis     ║")
    print("║  4. Add --refresh flag to bypass today's cache                ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()


if __name__ == "__main__":
    main()
