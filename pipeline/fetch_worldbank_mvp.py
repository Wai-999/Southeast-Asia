#!/usr/bin/env python3
"""
==============================================================================
  World Bank Data Fetcher — SEA Dashboard MVP
  pipeline/fetch_worldbank_mvp.py
==============================================================================

Fetches 5 economic indicators from the World Bank Open Data API for
5 Southeast Asian countries and saves them as CSV + JSON files ready
for the dashboard.

No API key required — the World Bank API is completely free and open.

USAGE
-----
    cd pipeline
    python fetch_worldbank_mvp.py

OUTPUT FILES (saved to pipeline/output/)
-----------------------------------------
    worldbank_raw_YYYYMMDD.csv          Long-format: one row per country-indicator-year
    worldbank_dashboard_YYYYMMDD.csv    Wide-format: one row per country-year
    worldbank_missing_YYYYMMDD.csv      Which combinations are missing and why
    worldbank_dashboard.json            JSON array ready to load into the dashboard

WHY ANNUAL ONLY? — READ THIS FIRST
------------------------------------
The World Bank does NOT publish quarterly data. All data here is ANNUAL.
The dashboard shows quarterly charts — annual figures are assigned to Q4
of each year with the rest of the year's quarters left blank.

For genuine quarterly data you need national statistics offices:
  Thailand   → NESDC  https://www.nesdc.go.th  (quarterly GDP and CPI)
  Vietnam    → GSO    https://www.gso.gov.vn   (quarterly GDP and CPI)
  Singapore  → SingStat https://www.singstat.gov.sg
  Cambodia, Myanmar → no public quarterly data available

HOW MISSING VALUES ARE HANDLED
--------------------------------
1. The World Bank often publishes data 1-2 years late.
   e.g. In 2025, 2024 data may not exist yet.
2. Myanmar data is sparse after the 2021 coup.
3. Strategy: forward-fill (use previous year's value), then backward-fill
   (use next year's value). Filled values are flagged is_filled=true.
   Never fill more than 2 consecutive years — beyond that the gap is
   reported as missing rather than guessed.

==============================================================================
"""

import csv
import json
import time
import sys
from pathlib import Path
from datetime import datetime

# Use httpx if available, else fall back to urllib (httpx is in pipeline/requirements.txt)
try:
    import httpx
    _USE_HTTPX = True
except ImportError:
    import urllib.request
    import urllib.error
    _USE_HTTPX = False


# ──────────────────────────────────────────────────────────────────────────────
#  SECTION 1 — CONFIGURATION
# ──────────────────────────────────────────────────────────────────────────────

# Years to fetch
START_YEAR = 2015
END_YEAR   = 2024

# Folder where output files are written
OUT_DIR = Path(__file__).parent / "output"

# Polite delay between API calls (seconds). No hard rate limit but be considerate.
REQUEST_DELAY = 0.6

# Maximum retries per request before giving up
MAX_RETRIES = 3

# Maximum consecutive years we will forward/backward fill before giving up.
# e.g. if 2022 and 2023 are missing but 2024 exists → fill both (gap=2).
# if 2020, 2021, 2022 are all missing → do NOT fill, report as gap.
MAX_FILL_GAP = 2


# ──────────────────────────────────────────────────────────────────────────────
#  SECTION 2 — COUNTRY DEFINITIONS
# ──────────────────────────────────────────────────────────────────────────────
# World Bank API uses ISO 3166-1 alpha-2 (2-letter) codes in its URLs.
# The dashboard uses ISO alpha-3 (3-letter) codes. We store both.

COUNTRIES = {
    "TH": {"name": "Thailand",   "iso3": "THA", "flag": "🇹🇭"},
    "VN": {"name": "Vietnam",    "iso3": "VNM", "flag": "🇻🇳"},
    "MM": {"name": "Myanmar",    "iso3": "MMR", "flag": "🇲🇲"},
    "KH": {"name": "Cambodia",   "iso3": "KHM", "flag": "🇰🇭"},
    "SG": {"name": "Singapore",  "iso3": "SGP", "flag": "🇸🇬"},
}

# Reverse lookup: ISO3 → metadata (built once)
ISO3_META = {v["iso3"]: {**v, "iso2": k} for k, v in COUNTRIES.items()}


# ──────────────────────────────────────────────────────────────────────────────
#  SECTION 3 — INDICATOR DEFINITIONS
# ──────────────────────────────────────────────────────────────────────────────
# Each entry:
#   wb_code     — exact World Bank indicator ID
#   label       — human-readable name
#   dashboard_code  — the code used in quarterly_values.json (uppercase)
#   unit        — display unit for charts
#   scale       — divide raw API value by this (1 = no change, 1e9 = billions)
#   csv_col     — column name in the CSV output
#   direction   — "higher_is_worse" or "lower_is_worse" (for alert colouring)
#   note        — important caveats about this indicator

INDICATORS = {
    "gdp_growth": {
        "wb_code":        "NY.GDP.MKTP.KD.ZG",
        "label":          "GDP Growth Rate",
        "dashboard_code": "GDP_GROWTH",
        "unit":           "% YoY",
        "scale":          1,
        "csv_col":        "gdp_growth_pct",
        "direction":      "lower_is_worse",
        "note": (
            "Annual GDP growth at constant prices. "
            "World Bank does not publish quarterly GDP. "
            "For quarterly data use national statistics offices (NESDC, GSO, SingStat)."
        ),
    },
    "inflation": {
        "wb_code":        "FP.CPI.TOTL.ZG",
        "label":          "Inflation (CPI)",
        "dashboard_code": "INFLATION",
        "unit":           "% YoY",
        "scale":          1,
        "csv_col":        "inflation_pct",
        "direction":      "higher_is_worse",
        "note": (
            "Annual average Consumer Price Index change. "
            "Monthly CPI is available from IMF IFS database. "
            "Myanmar figures post-2021 are IMF estimates only."
        ),
    },
    "exports": {
        "wb_code":        "NE.EXP.GNFS.CD",
        "label":          "Exports of Goods & Services",
        "dashboard_code": "EXPORTS",
        "unit":           "USD Billion",
        "scale":          1_000_000_000,   # raw value is USD, divide → billions
        "csv_col":        "exports_usd_b",
        "direction":      "lower_is_worse",
        "note": (
            "Exports of goods AND services in current USD, scaled to billions. "
            "For merchandise-only trade use WB code TX.VAL.MRCH.CD.WT. "
            "Annual only."
        ),
    },
    "imports": {
        "wb_code":        "NE.IMP.GNFS.CD",
        "label":          "Imports of Goods & Services",
        "dashboard_code": "IMPORTS",
        "unit":           "USD Billion",
        "scale":          1_000_000_000,
        "csv_col":        "imports_usd_b",
        "direction":      "lower_is_worse",
        "note": (
            "Imports of goods AND services in current USD, scaled to billions. "
            "Annual only."
        ),
    },
    "fdi_inflows": {
        "wb_code":        "BX.KLT.DINV.CD.WD",
        "label":          "FDI Net Inflows",
        "dashboard_code": "FDI",
        "unit":           "USD Billion",
        "scale":          1_000_000_000,
        "csv_col":        "fdi_inflows_usd_b",
        "direction":      "lower_is_worse",
        "note": (
            "Balance of Payments FDI net inflows, current USD, scaled to billions. "
            "NEGATIVE values mean net capital outflow (money leaving the country) — "
            "this is valid and expected for mature economies. "
            "Annual only. 1-2 year publication lag is common."
        ),
    },
}


# ──────────────────────────────────────────────────────────────────────────────
#  SECTION 4 — WORLD BANK API HELPERS
# ──────────────────────────────────────────────────────────────────────────────

def build_url(wb_code: str) -> str:
    """
    Build the World Bank API URL for all 5 countries and one indicator.

    We pass all 5 ISO2 codes separated by semicolons so we fetch everything
    in a single HTTP request per indicator (5 requests total).

    Example:
      https://api.worldbank.org/v2/country/TH;VN;MM;KH;SG
        /indicator/NY.GDP.MKTP.KD.ZG
        ?format=json&per_page=200&date=2015:2024
    """
    country_str = ";".join(COUNTRIES.keys())
    n_records   = len(COUNTRIES) * (END_YEAR - START_YEAR + 1)
    per_page    = max(200, n_records + 20)
    return (
        f"https://api.worldbank.org/v2/country/{country_str}"
        f"/indicator/{wb_code}"
        f"?format=json&per_page={per_page}&date={START_YEAR}:{END_YEAR}"
    )


def _get_json(url: str) -> list | None:
    """
    Perform the HTTP GET and return the parsed JSON list, or None on failure.
    Works with httpx (preferred) or stdlib urllib.
    """
    if _USE_HTTPX:
        resp = httpx.get(url, timeout=30)
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

            # World Bank always returns a 2-element list: [metadata, data_array]
            if not isinstance(payload, list) or len(payload) < 2:
                print(f"    ⚠  Unexpected format on attempt {attempt}")
                continue

            metadata   = payload[0]
            data_array = payload[1] or []

            if metadata.get("pages", 1) > 1:
                print(f"    ⚠  Response has {metadata['pages']} pages — "
                      "some data may be missing. Increase per_page.")

            return data_array

        except Exception as e:
            print(f"    ✗  Attempt {attempt}/{MAX_RETRIES}: {type(e).__name__}: {e}")
            if attempt < MAX_RETRIES:
                wait = 2 ** attempt   # 2s → 4s → 8s
                print(f"    ↻  Retrying in {wait}s …")
                time.sleep(wait)

    return None   # give up


# ──────────────────────────────────────────────────────────────────────────────
#  SECTION 5 — FETCH ALL INDICATORS
# ──────────────────────────────────────────────────────────────────────────────

def fetch_all() -> list[dict]:
    """
    Fetch all 5 indicators for all 5 countries from the World Bank API.
    Returns a flat list of clean dicts, one per data point.

    Each dict:
        iso2, iso3, country_name, year,
        indicator_key, dashboard_code, label, unit,
        raw_value, value   (value = raw_value / scale)
    """
    all_rows: list[dict] = []

    for i, (ind_key, ind_meta) in enumerate(INDICATORS.items(), 1):
        print(f"\n  [{i}/{len(INDICATORS)}] {ind_meta['label']}  ({ind_meta['wb_code']})")

        url  = build_url(ind_meta["wb_code"])
        data = fetch_with_retry(url)

        if data is None:
            print(f"    ✗  FAILED after {MAX_RETRIES} retries — skipping this indicator")
            continue

        parsed  = 0
        missing = 0
        for row in data:
            raw = row.get("value")
            if raw is None:
                missing += 1
                continue   # API-missing values — handled later by fill logic

            iso2 = row.get("country", {}).get("id", "")
            meta = COUNTRIES.get(iso2)
            if not meta:
                continue   # shouldn't happen since we only requested our 5 countries

            scale = ind_meta["scale"]
            all_rows.append({
                "iso2":           iso2,
                "iso3":           meta["iso3"],
                "country_name":   meta["name"],
                "year":           int(row["date"]),
                "indicator_key":  ind_key,
                "dashboard_code": ind_meta["dashboard_code"],
                "label":          ind_meta["label"],
                "unit":           ind_meta["unit"],
                "raw_value":      float(raw),
                "value":          round(float(raw) / scale, 4),
            })
            parsed += 1

        print(f"    ✓  {parsed} points fetched  |  {missing} null (missing at source)")
        time.sleep(REQUEST_DELAY)

    print(f"\n  {'─'*50}")
    print(f"  Total raw data points : {len(all_rows)}")
    return all_rows


# ──────────────────────────────────────────────────────────────────────────────
#  SECTION 6 — BUILD FULL GRID (5 countries × 5 indicators × N years)
# ──────────────────────────────────────────────────────────────────────────────

def build_grid(rows: list[dict]) -> dict:
    """
    Organise the fetched rows into a nested dict for easy access:
        grid[iso3][indicator_key][year] = {"value": ..., "is_filled": False}

    The grid covers ALL years in START_YEAR..END_YEAR.
    Missing cells start as None and are filled in the next step.
    """
    # Initialise every cell to None
    grid: dict[str, dict[str, dict[int, dict | None]]] = {}
    for iso2, meta in COUNTRIES.items():
        iso3 = meta["iso3"]
        grid[iso3] = {}
        for ind_key in INDICATORS:
            grid[iso3][ind_key] = {yr: None for yr in range(START_YEAR, END_YEAR + 1)}

    # Fill in fetched values
    for row in rows:
        iso3    = row["iso3"]
        ind_key = row["indicator_key"]
        year    = row["year"]
        if START_YEAR <= year <= END_YEAR:
            grid[iso3][ind_key][year] = {
                "value":     row["value"],
                "raw_value": row["raw_value"],
                "is_filled": False,
                "is_estimate": False,
            }

    return grid


# ──────────────────────────────────────────────────────────────────────────────
#  SECTION 7 — FILL MISSING VALUES
# ──────────────────────────────────────────────────────────────────────────────

def fill_missing(grid: dict) -> tuple[dict, int]:
    """
    Fill gaps in the time series using forward-fill then backward-fill.

    Strategy:
    1. FORWARD-FILL: if a year is missing but the previous year has data,
       copy the previous year's value. Repeat for up to MAX_FILL_GAP years.
    2. BACKWARD-FILL: if early years are still missing but later years have
       data, fill backwards. Same MAX_FILL_GAP limit.
    3. Any gap larger than MAX_FILL_GAP or completely unknown stays as None.

    Filled values are flagged with is_filled=True so the dashboard can
    show them differently (e.g. dashed line, lighter colour).

    Returns (updated grid, total cells filled).
    """
    years     = list(range(START_YEAR, END_YEAR + 1))
    fill_count = 0

    for iso3 in grid:
        for ind_key in grid[iso3]:
            series = grid[iso3][ind_key]

            # ── FORWARD FILL ──────────────────────────────────────────────
            # Walk years left → right, propagate last known value.
            last_known    = None
            gap_length    = 0

            for yr in years:
                cell = series[yr]
                if cell is not None:
                    last_known = cell["value"]
                    gap_length = 0
                else:
                    if last_known is not None and gap_length < MAX_FILL_GAP:
                        series[yr] = {
                            "value":     last_known,
                            "raw_value": None,
                            "is_filled": True,
                            "is_estimate": True,   # filled = estimated
                        }
                        fill_count += 1
                        gap_length += 1
                    else:
                        gap_length += 1

            # ── BACKWARD FILL ─────────────────────────────────────────────
            # Walk years right → left, propagate first known value backwards.
            first_known = None
            gap_length  = 0

            for yr in reversed(years):
                cell = series[yr]
                if cell is not None:
                    first_known = cell["value"]
                    gap_length  = 0
                else:
                    if first_known is not None and gap_length < MAX_FILL_GAP:
                        series[yr] = {
                            "value":     first_known,
                            "raw_value": None,
                            "is_filled": True,
                            "is_estimate": True,
                        }
                        fill_count += 1
                        gap_length += 1
                    else:
                        gap_length += 1

    print(f"\n  Missing-value fills applied : {fill_count} cells")
    return grid, fill_count


# ──────────────────────────────────────────────────────────────────────────────
#  SECTION 8 — SAVE RAW LONG-FORMAT CSV
# ──────────────────────────────────────────────────────────────────────────────

def save_raw_csv(rows: list[dict], path: Path) -> None:
    """
    Save the RAW (pre-fill) data in LONG FORMAT.
    One row per country-indicator-year. Easiest for analysis, SQL loading,
    and cross-referencing individual data points.

    Columns:
        iso2, iso3, country_name, year,
        indicator_key, dashboard_code, label, unit,
        raw_value, value
    """
    if not rows:
        print(f"  ⚠  No rows to write to {path.name}")
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["iso2", "iso3", "country_name", "year",
              "indicator_key", "dashboard_code", "label", "unit",
              "raw_value", "value"]

    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for row in sorted(rows, key=lambda r: (r["iso3"], r["indicator_key"], r["year"])):
            w.writerow(row)

    print(f"  ✓  Raw CSV saved        →  {path.name}  ({len(rows)} rows)")


# ──────────────────────────────────────────────────────────────────────────────
#  SECTION 9 — SAVE DASHBOARD WIDE-FORMAT CSV
# ──────────────────────────────────────────────────────────────────────────────

def save_dashboard_csv(grid: dict, path: Path) -> None:
    """
    Save data in WIDE FORMAT after gap-filling.
    One row per country-year, all 5 indicators as separate columns.
    Also includes trade_balance_usd_b = exports - imports.

    A '*' suffix in a column header means the value was forward/backward filled.
    The is_filled_* columns tell you which specific cells were estimated.

    Columns:
        iso3, country_name, year,
        gdp_growth_pct, inflation_pct, exports_usd_b, imports_usd_b, fdi_inflows_usd_b,
        trade_balance_usd_b,
        is_filled_gdp_growth, is_filled_inflation, is_filled_exports,
        is_filled_imports, is_filled_fdi_inflows
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    output_rows = []

    for iso3 in sorted(grid):
        country_name = ISO3_META[iso3]["name"]
        for year in range(START_YEAR, END_YEAR + 1):
            row: dict = {"iso3": iso3, "country_name": country_name, "year": year}

            for ind_key, ind_meta in INDICATORS.items():
                cell = grid[iso3][ind_key][year]
                col  = ind_meta["csv_col"]
                if cell is not None:
                    row[col]                       = cell["value"]
                    row[f"is_filled_{ind_key}"]    = cell["is_filled"]
                else:
                    row[col]                       = ""   # still missing after fill
                    row[f"is_filled_{ind_key}"]    = ""

            # Derived: trade balance
            exp = row.get("exports_usd_b")
            imp = row.get("imports_usd_b")
            if exp != "" and imp != "" and exp is not None and imp is not None:
                row["trade_balance_usd_b"] = round(float(exp) - float(imp), 4)
            else:
                row["trade_balance_usd_b"] = ""

            output_rows.append(row)

    fields = (
        ["iso3", "country_name", "year"] +
        [m["csv_col"] for m in INDICATORS.values()] +
        ["trade_balance_usd_b"] +
        [f"is_filled_{k}" for k in INDICATORS]
    )

    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(output_rows)

    print(f"  ✓  Dashboard CSV saved  →  {path.name}  ({len(output_rows)} rows)")


# ──────────────────────────────────────────────────────────────────────────────
#  SECTION 10 — SAVE DASHBOARD JSON
# ──────────────────────────────────────────────────────────────────────────────

def save_dashboard_json(grid: dict, path: Path) -> None:
    """
    Save data as a JSON array matching the quarterly_values.json format
    used by the frontend.

    Because World Bank data is ANNUAL (not quarterly), each record uses
    quarter=null and frequency="annual". The dashboard can use these as
    the Q4 anchor point for each year, showing the annual figure.

    Each record:
    {
      "country_id":     "THA",
      "indicator_code": "GDP_GROWTH",
      "year":           2023,
      "quarter":        null,
      "frequency":      "annual",
      "value":          1.9,
      "unit":           "% YoY",
      "is_estimate":    false,
      "is_filled":      false,
      "source":         "World Bank"
    }
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    records = []

    for iso3 in sorted(grid):
        for ind_key, ind_meta in INDICATORS.items():
            for year in range(START_YEAR, END_YEAR + 1):
                cell = grid[iso3][ind_key][year]
                if cell is None:
                    continue   # still missing after filling — skip

                records.append({
                    "country_id":     iso3,
                    "indicator_code": ind_meta["dashboard_code"],
                    "year":           year,
                    "quarter":        None,
                    "frequency":      "annual",
                    "value":          cell["value"],
                    "unit":           ind_meta["unit"],
                    "is_estimate":    cell["is_estimate"],
                    "is_filled":      cell["is_filled"],
                    "source":         "World Bank",
                })

    with open(path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)

    print(f"  ✓  Dashboard JSON saved →  {path.name}  ({len(records)} records)")


# ──────────────────────────────────────────────────────────────────────────────
#  SECTION 11 — MISSING DATA REPORT
# ──────────────────────────────────────────────────────────────────────────────

def explain_missing(iso3: str, year: int, ind_key: str) -> str:
    """Return a one-sentence explanation for why a data point is missing."""
    if iso3 == "MMR" and year >= 2022:
        return "Post-coup (2021+) data collection disrupted; World Bank estimates only"
    if year == END_YEAR:
        return f"{END_YEAR} not yet published (World Bank 1–2 year lag)"
    if year == END_YEAR - 1 and ind_key == "fdi_inflows":
        return f"{END_YEAR - 1} FDI data often delayed an extra year"
    return "Not available from World Bank for this country-year"


def save_missing_report(grid: dict, path: Path) -> None:
    """
    Write a CSV listing every country-indicator-year cell that is STILL
    missing after the forward/backward fill step, with a likely reason.

    Use this to decide whether to supplement with IMF WEO or manual estimates.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    gaps   = []
    filled = []

    for iso3 in sorted(grid):
        for ind_key, ind_meta in INDICATORS.items():
            for year in range(START_YEAR, END_YEAR + 1):
                cell = grid[iso3][ind_key][year]
                if cell is None:
                    gaps.append({
                        "iso3":           iso3,
                        "country_name":   ISO3_META[iso3]["name"],
                        "year":           year,
                        "indicator":      ind_key,
                        "dashboard_code": ind_meta["dashboard_code"],
                        "likely_reason":  explain_missing(iso3, year, ind_key),
                    })
                elif cell["is_filled"]:
                    filled.append({
                        "iso3":      iso3,
                        "year":      year,
                        "indicator": ind_key,
                        "value":     cell["value"],
                    })

    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[
            "iso3", "country_name", "year", "indicator",
            "dashboard_code", "likely_reason"
        ])
        w.writeheader()
        w.writerows(gaps)

    total_cells = len(COUNTRIES) * len(INDICATORS) * (END_YEAR - START_YEAR + 1)
    pct_gap     = round(100 * len(gaps)   / total_cells, 1)
    pct_filled  = round(100 * len(filled) / total_cells, 1)
    pct_real    = round(100 - pct_gap - pct_filled, 1)

    print()
    print(f"  {'─'*50}")
    print(f"  Missing data summary ({total_cells} total cells):")
    print(f"    ✓  Real data   : {total_cells - len(gaps) - len(filled):4d}  ({pct_real}%)")
    print(f"    ~  Forward/back-filled : {len(filled):4d}  ({pct_filled}%)")
    print(f"    ✗  Still missing       : {len(gaps):4d}  ({pct_gap}%)")
    print()
    print(f"  Per-country gaps:")
    for iso3 in sorted(grid):
        n = sum(1 for g in gaps if g["iso3"] == iso3)
        flag = ISO3_META[iso3]["flag"]
        note = ""
        if iso3 == "MMR":
            note = "  ⚠ post-coup estimation issues"
        print(f"    {flag} {ISO3_META[iso3]['name']:<12}: {n:2d} gap(s){note}")

    print(f"\n  ✓  Missing report saved →  {path.name}  ({len(gaps)} gaps)")


# ──────────────────────────────────────────────────────────────────────────────
#  SECTION 12 — VALIDATION / SANITY CHECK
# ──────────────────────────────────────────────────────────────────────────────

EXPECTED_RANGES = {
    "gdp_growth":  (-30.0,   15.0),   # %
    "inflation":   ( -5.0,  100.0),   # %  (Myanmar can be very high)
    # Singapore exports include massive re-export component + financial services:
    # 2022 ≈ $947B, 2023 ≈ $918B, 2024 ≈ $979B — set ceiling to 1,200 to be safe.
    "exports":     (  0.0, 1_200.0),  # USD billion
    "imports":     (  0.0, 1_000.0),  # USD billion
    "fdi_inflows": (-50.0,   200.0),  # USD billion (negative = outflow)
}

def validate(rows: list[dict]) -> None:
    """
    Sanity-check all fetched values against plausible ranges.
    Prints any suspicious values but does not remove them —
    an out-of-range value might still be correct (e.g. hyperinflation).
    """
    issues = []
    for row in rows:
        lo, hi = EXPECTED_RANGES.get(row["indicator_key"], (-1e9, 1e9))
        v = row["value"]
        if not (lo <= v <= hi):
            issues.append(
                f"  {ISO3_META[row['iso3']]['flag']} {row['iso3']} {row['year']} "
                f"[{row['indicator_key']}] = {v}  (expected {lo}–{hi})"
            )

    if issues:
        print(f"\n  ⚠  {len(issues)} out-of-range value(s) — review manually:")
        for line in issues:
            print(line)
    else:
        print(f"  ✓  All values within expected ranges")


# ──────────────────────────────────────────────────────────────────────────────
#  SECTION 13 — INDICATOR REFERENCE TABLE
# ──────────────────────────────────────────────────────────────────────────────

def print_indicator_table() -> None:
    """Print a compact reference of indicator codes, units, and limitations."""
    W = 72
    print()
    print("=" * W)
    print("  WORLD BANK INDICATOR CODES USED IN THIS SCRIPT")
    print("=" * W)
    fmt = "  {:<16} {:<30} {}"
    print(fmt.format("KEY", "WORLD BANK CODE", "UNIT"))
    print("  " + "─" * (W - 2))
    for k, m in INDICATORS.items():
        print(fmt.format(k, m["wb_code"], m["unit"]))
    print()


def print_limitations() -> None:
    """Print the key limitations of World Bank data for this dashboard."""
    print()
    print("━" * 72)
    print("  ⚠  LIMITATIONS — PLEASE READ")
    print("━" * 72)
    lines = [
        ("ANNUAL ONLY",
         "World Bank data is annual. The dashboard shows quarterly charts.",
         "Annual values appear as Q4 anchors; Q1–Q3 will be blank unless",
         "you add a quarterly source (NESDC, GSO, SingStat)."),
        ("PUBLICATION LAG",
         "Most indicators have a 1–2 year publication delay.",
         f"In 2025, the newest confirmed data for most countries is 2023.",
         f"{END_YEAR} data is often preliminary or absent."),
        ("MYANMAR DATA",
         "Since the Feb 2021 coup, the World Bank has limited access to",
         "Myanmar's national statistics. Post-2022 values are IMF estimates",
         "or extrapolations — treat them with caution."),
        ("FDI SIGN",
         "Negative FDI values are valid — they mean net capital outflow.",
         "Singapore often shows large swings due to round-tripping through",
         "holding companies."),
        ("CURRENCY",
         "Exports, imports, FDI are all in CURRENT USD (not inflation-",
         "adjusted). This inflates growth comparisons over long periods."),
    ]
    for parts in lines:
        title = parts[0]
        print(f"\n  [{title}]")
        for line in parts[1:]:
            print(f"    {line}")
    print()
    print("━" * 72)


# ──────────────────────────────────────────────────────────────────────────────
#  MAIN
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    ts = datetime.today().strftime("%Y%m%d")

    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║   SEA Change Dashboard — World Bank Data Fetcher (MVP)  ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print(f"  Countries  : {', '.join(m['name'] for m in COUNTRIES.values())}")
    print(f"  Indicators : {', '.join(INDICATORS)}")
    print(f"  Years      : {START_YEAR}–{END_YEAR}")
    print(f"  HTTP lib   : {'httpx' if _USE_HTTPX else 'urllib (stdlib fallback)'}")
    print(f"  Output dir : {OUT_DIR}/")

    # Print reference table before fetching
    print_indicator_table()

    # ── STEP 1: Fetch ─────────────────────────────────────────────────────────
    print("[ STEP 1 ] Fetching from World Bank Open Data API …")
    print("  5 requests total (one per indicator; all countries batched)\n")
    raw_rows = fetch_all()

    if not raw_rows:
        print("\n✗  No data fetched. Check your internet connection and retry.")
        sys.exit(1)

    # ── STEP 2: Validate ──────────────────────────────────────────────────────
    print("\n[ STEP 2 ] Validating fetched values …")
    validate(raw_rows)

    # ── STEP 3: Build grid + fill missing values ───────────────────────────────
    print("\n[ STEP 3 ] Building full grid and filling missing values …")
    grid, _ = fill_missing(build_grid(raw_rows))

    # ── STEP 4: Save CSV files ─────────────────────────────────────────────────
    print("\n[ STEP 4 ] Saving CSV files …")
    save_raw_csv(raw_rows, OUT_DIR / f"worldbank_raw_{ts}.csv")
    save_dashboard_csv(grid,  OUT_DIR / f"worldbank_dashboard_{ts}.csv")

    # ── STEP 5: Save JSON for the frontend ────────────────────────────────────
    print("\n[ STEP 5 ] Saving JSON for the dashboard frontend …")
    save_dashboard_json(grid, OUT_DIR / "worldbank_dashboard.json")

    # ── STEP 6: Missing data report ───────────────────────────────────────────
    print("\n[ STEP 6 ] Generating missing data report …")
    save_missing_report(grid, OUT_DIR / f"worldbank_missing_{ts}.csv")

    # ── Limitations ───────────────────────────────────────────────────────────
    print_limitations()

    print("╔══════════════════════════════════════════════════════════╗")
    print("║  ✓  Done! Files saved to pipeline/output/               ║")
    print("║                                                          ║")
    print("║  Next steps:                                             ║")
    print("║  1. Review worldbank_missing_*.csv for remaining gaps   ║")
    print("║  2. Load worldbank_dashboard.json into the frontend:    ║")
    print("║       import data from '../pipeline/output/json/        ║")
    print("║       worldbank_dashboard.json'                         ║")
    print("║  3. For quarterly GDP/inflation, add NESDC/GSO scrapers ║")
    print("║  4. Cross-check Myanmar post-2022 values with IMF WEO  ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print()


if __name__ == "__main__":
    main()
