#!/usr/bin/env python3
"""
scripts/fetch_imf_weo.py
────────────────────────────────────────────────────────────────────────────
Fetches GDP growth, inflation, unemployment, fiscal balance, current account,
and government debt forecasts from the IMF World Economic Outlook DataMapper API.

No API key required. Biannual releases: April & October.

Data is labeled value_type="forecast_estimate" for 2025+.
For years where WB has actual data, value_type="official_actual".

OUTPUT
  pipeline/data/raw/imf/imf_weo_YYYYMMDD.json     — raw API response
  pipeline/data/processed/imf_weo_normalized.json  — normalized rows

USAGE
  cd <project_root>
  python scripts/fetch_imf_weo.py
  python scripts/fetch_imf_weo.py --years 2023 2024 2025 2026
"""

import json
import sys
import time
import argparse
from pathlib import Path
from datetime import datetime, date

try:
    import httpx
    def _get(url, timeout=30):
        with httpx.Client(timeout=timeout, follow_redirects=True) as c:
            r = c.get(url)
            r.raise_for_status()
            return r.json()
except ImportError:
    import urllib.request
    import urllib.error
    def _get(url, timeout=30):
        req = urllib.request.Request(url, headers={"User-Agent": "SEA-Dashboard/2.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())

# ─── Paths ────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PIPELINE     = PROJECT_ROOT / "pipeline"
RAW_DIR      = PIPELINE / "data" / "raw" / "imf"
PROC_DIR     = PIPELINE / "data" / "processed"
LOGS_DIR     = PIPELINE / "data" / "logs"
RAW_DIR.mkdir(parents=True, exist_ok=True)

# ─── Configuration ────────────────────────────────────────────────────────────
IMF_BASE       = "https://www.imf.org/external/datamapper/api/v1"
START_YEAR     = 2019
END_YEAR       = 2026
WB_ACTUALS_UNTIL = 2024   # After this year, label as forecast_estimate

# IMF uses ISO3 codes
ISO3_CODES = [
    "THA","VNM","MMR","KHM","LAO","MYS","SGP","IDN","PHL","BRN","TLS",
    "CHN","USA","JPN","IND","KOR","AUS",
]

# IMF WEO indicators to fetch
IMF_INDICATORS = {
    "NGDP_RPCH":      {"sector": "macro_economy",    "indicator_code": "GDP_GROWTH",         "name": "Real GDP Growth Rate",            "unit": "% YoY"},
    "PCPIPCH":        {"sector": "prices_inflation",  "indicator_code": "CPI_INFLATION",       "name": "Inflation CPI Annual Rate",       "unit": "% YoY"},
    "LUR":            {"sector": "labor",             "indicator_code": "UNEMPLOYMENT_RATE",   "name": "Unemployment Rate",               "unit": "%"},
    "GGXCNL_NGDP":    {"sector": "fiscal",            "indicator_code": "FISCAL_BALANCE_GDP",  "name": "Fiscal Balance (% GDP)",          "unit": "% of GDP"},
    "BCA_NGDPD":      {"sector": "macro_economy",     "indicator_code": "CURRENT_ACCOUNT_GDP", "name": "Current Account Balance (% GDP)", "unit": "% of GDP"},
    "NGDPDPC":        {"sector": "macro_economy",     "indicator_code": "GDP_PER_CAPITA_USD",  "name": "GDP Per Capita USD",              "unit": "USD"},
    "NGDPD":          {"sector": "macro_economy",     "indicator_code": "GDP_NOMINAL_USD",     "name": "GDP Nominal USD Billions",        "unit": "USD billion"},
    "GGXWDG_NGDP":    {"sector": "fiscal",            "indicator_code": "PUBLIC_DEBT_GDP",     "name": "Government Gross Debt (% GDP)",   "unit": "% of GDP"},
    "GGX_NGDP":       {"sector": "fiscal",            "indicator_code": "GOVT_EXPENDITURE_GDP","name": "Government Expenditure (% GDP)",  "unit": "% of GDP"},
}

REQUEST_DELAY = 1.0
MAX_RETRIES   = 3

# ─── Helpers ──────────────────────────────────────────────────────────────────

def _fetch_indicator(imf_code: str, iso3_list: list[str]) -> dict:
    """Fetch one IMF WEO indicator for all countries."""
    codes_str = ",".join(iso3_list)
    url = f"{IMF_BASE}/{imf_code}/{codes_str}"
    for attempt in range(MAX_RETRIES):
        try:
            data = _get(url, timeout=45)
            return data
        except Exception as e:
            print(f"    ⚠ attempt {attempt+1}/{MAX_RETRIES} failed for {imf_code}: {e}", flush=True)
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
    return {}


def _value_type(year: int) -> str:
    if year <= WB_ACTUALS_UNTIL:
        return "official_actual"
    return "forecast_estimate"


def _data_quality(val, year: int) -> str:
    if val is None:
        return "missing"
    if year > WB_ACTUALS_UNTIL:
        return "estimated"
    return "available"


def _limitation_note(imf_code: str, iso3: str, year: int, val) -> str:
    parts = []
    if val is None:
        parts.append("IMF WEO returned no value for this country/year")
    if year >= 2025:
        parts.append(f"IMF WEO forecast for {year}; not official national statistics")
    if iso3 == "MMR" and year >= 2022:
        parts.append("Myanmar: forecasts highly uncertain post-coup")
    if iso3 == "TLS":
        parts.append("Timor-Leste: limited statistical capacity; IMF estimate used")
    return "; ".join(parts) if parts else ""


def build_rows(raw_data: dict, imf_code: str, meta: dict, start: int, end: int) -> list[dict]:
    """Convert raw IMF API response to normalized rows."""
    rows = []
    ts = datetime.utcnow().isoformat() + "Z"
    today = date.today().isoformat()

    # IMF response structure: {"values": {"INDICATOR": {"ISO3": {"YEAR": value}}}}
    try:
        country_data = raw_data.get("values", {}).get(imf_code, {})
    except (AttributeError, KeyError):
        return rows

    for iso3 in ISO3_CODES:
        yr_data = country_data.get(iso3, {})
        for year in range(start, end + 1):
            yr_str = str(year)
            val_raw = yr_data.get(yr_str)
            try:
                val = float(val_raw) if val_raw is not None else None
                # IMF GDP nominal is in billions already for NGDPD
                if imf_code == "NGDPD" and val is not None:
                    val = round(val, 3)  # already in billions
            except (TypeError, ValueError):
                val = None

            rows.append({
                "country_code":    iso3,
                "sector":          meta["sector"],
                "indicator_code":  meta["indicator_code"],
                "indicator_name":  meta["name"],
                "period":          yr_str,
                "year":            year,
                "quarter":         None,
                "month":           None,
                "value":           val,
                "unit":            meta["unit"],
                "frequency":       "annual",
                "source":          "IMF World Economic Outlook DataMapper",
                "source_type":     "forecast_multilateral",
                "source_url":      f"{IMF_BASE}/{imf_code}/{iso3}",
                "fetched_at":      ts,
                "released_at":     None,
                "value_type":      _value_type(year),
                "data_quality":    _data_quality(val, year),
                "confidence":      "high" if val is not None else "none",
                "extraction_method": "api",
                "limitation_note": _limitation_note(imf_code, iso3, year, val),
            })

    return rows


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Fetch IMF WEO data")
    parser.add_argument("--years", nargs=2, type=int, default=[START_YEAR, END_YEAR],
                        metavar=("START", "END"), help="Year range to fetch (default 2019 2026)")
    parser.add_argument("--refresh", action="store_true", help="Re-fetch even if cached today")
    args = parser.parse_args()
    start, end = args.years[0], args.years[1]

    today_str = date.today().strftime("%Y%m%d")
    cache_file = RAW_DIR / f"imf_weo_{today_str}.json"
    out_file   = PROC_DIR / "imf_weo_normalized.json"

    print(f"\n{'═'*60}")
    print(f"  IMF WEO Fetcher — {today_str}")
    print(f"  Years: {start}–{end}  |  Countries: {len(ISO3_CODES)}")
    print(f"  Indicators: {len(IMF_INDICATORS)}")
    print(f"{'═'*60}\n")

    all_raw  = {}
    all_rows = []
    errors   = []

    for imf_code, meta in IMF_INDICATORS.items():
        print(f"  ▸ {imf_code:20s} {meta['name'][:40]}", flush=True)

        # Check cache
        if not args.refresh and cache_file.exists():
            try:
                cached = json.loads(cache_file.read_text())
                if imf_code in cached.get("raw", {}):
                    raw = cached["raw"][imf_code]
                    print(f"    ↳ from cache", flush=True)
                    all_raw[imf_code] = raw
                    all_rows.extend(build_rows(raw, imf_code, meta, start, end))
                    continue
            except Exception:
                pass

        raw = _fetch_indicator(imf_code, ISO3_CODES)
        if not raw:
            errors.append(f"Failed to fetch {imf_code}")
            print(f"    ✗ FAILED — skipping", flush=True)
            continue

        all_raw[imf_code] = raw
        rows = build_rows(raw, imf_code, meta, start, end)
        all_rows.extend(rows)

        non_null = sum(1 for r in rows if r["value"] is not None)
        total    = len(rows)
        print(f"    ✓ {non_null}/{total} values", flush=True)
        time.sleep(REQUEST_DELAY)

    # Save raw cache
    cache_data = {"fetched_at": datetime.utcnow().isoformat() + "Z", "raw": all_raw}
    cache_file.write_text(json.dumps(cache_data, indent=2))

    # Build summary stats
    actuals   = sum(1 for r in all_rows if r["value_type"] == "official_actual" and r["value"] is not None)
    forecasts = sum(1 for r in all_rows if r["value_type"] == "forecast_estimate" and r["value"] is not None)
    missing   = sum(1 for r in all_rows if r["value"] is None)

    result = {
        "source":        "IMF World Economic Outlook DataMapper API",
        "source_id":     "IMF_WEO",
        "fetched_at":    datetime.utcnow().isoformat() + "Z",
        "year_range":    [start, end],
        "countries":     ISO3_CODES,
        "indicators":    list(IMF_INDICATORS.keys()),
        "total_rows":    len(all_rows),
        "actuals":       actuals,
        "forecasts":     forecasts,
        "missing":       missing,
        "errors":        errors,
        "records":       all_rows,
    }

    out_file.write_text(json.dumps(result, indent=2))

    print(f"\n{'─'*60}")
    print(f"  ✓ Rows written : {len(all_rows)}")
    print(f"  ✓ Actuals      : {actuals}")
    print(f"  ✓ Forecasts    : {forecasts}")
    print(f"  ✗ Missing      : {missing}")
    if errors:
        print(f"  ⚠ Errors      : {len(errors)}")
        for e in errors:
            print(f"      {e}")
    print(f"  📄 Output: {out_file.relative_to(PROJECT_ROOT)}")
    print(f"{'─'*60}\n")

    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
