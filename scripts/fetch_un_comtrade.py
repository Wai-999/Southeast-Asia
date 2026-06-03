#!/usr/bin/env python3
"""
scripts/fetch_un_comtrade.py
────────────────────────────────────────────────────────────────────────────
Fetches total trade flows from World Bank WDI (merchandise + goods & services).

WHY NOT UN COMTRADE?
  The UN Comtrade Plus API (comtradeapi.un.org) now requires a paid subscription
  key for all endpoints including the former "free tier" — it returns HTTP 401.
  The legacy public API (comtrade.un.org/api/get) returns HTML (site redirect).
  WITS (World Bank bilateral trade) returns HTTP 403.
  IMF DOTS returns HTTP 403.
  → Bilateral partner flows are UNAVAILABLE via free public APIs as of 2026.

WHAT THIS SCRIPT DOES:
  Uses World Bank WDI (free, no key) for:
    TX.VAL.MRCH.CD.WT  — Merchandise exports (current US$)
    TM.VAL.MRCH.CD.WT  — Merchandise imports (current US$)
    NE.EXP.GNFS.CD     — Exports of goods & services (current US$)
    NE.IMP.GNFS.CD     — Imports of goods & services (current US$)
  Computes trade balance and trade openness.
  Bilateral/partner dependency marked as missing_official with limitation note.

REPORTER COUNTRIES: 11 SEA + 6 partner
PARTNER DEPENDENCY: Not available (requires paid UN Comtrade subscription)

OUTPUT
  pipeline/data/raw/comtrade/wb_trade_{YYYYMMDD}.json
  pipeline/data/processed/comtrade_normalized.json
  pipeline/data/processed/trade_flows.json          (alias, for dashboard charts)

USAGE
  python scripts/fetch_un_comtrade.py
  python scripts/fetch_un_comtrade.py --reporter THA VNM MYS
  python scripts/fetch_un_comtrade.py --year 2024
  python scripts/fetch_un_comtrade.py --all-years
"""

import json
import sys
import time
import argparse
import os
from pathlib import Path
from datetime import datetime, date

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    import httpx
    def _get(url, timeout=30, headers=None, params=None):
        with httpx.Client(timeout=timeout, follow_redirects=True) as c:
            return c.get(url, headers=headers or {}, params=params or {})
except ImportError:
    import urllib.request, urllib.parse
    class _R:
        def __init__(self, data, code):
            self._d = data; self.status_code = code
            self.text = data.decode() if isinstance(data, bytes) else str(data)
        def json(self): return json.loads(self.text)
    def _get(url, timeout=30, headers=None, params=None):
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers=headers or {"User-Agent": "SEA-Dashboard/2.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return _R(r.read(), r.status)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PIPELINE     = PROJECT_ROOT / "pipeline"
RAW_DIR      = PIPELINE / "data" / "raw" / "comtrade"
PROC_DIR     = PIPELINE / "data" / "processed"
RAW_DIR.mkdir(parents=True, exist_ok=True)

ts_now    = lambda: datetime.utcnow().isoformat() + "Z"
today_str = date.today().strftime("%Y%m%d")
today_iso = date.today().isoformat()
CURR_YEAR = date.today().year

# ─── Country Configuration ──────────────────────────────────────────────────

ALL_REPORTERS = [
    "THA", "VNM", "MMR", "KHM", "LAO", "MYS", "SGP", "IDN", "PHL", "BRN", "TLS",
    "CHN", "USA", "JPN", "IND", "KOR", "AUS",
]

REPORTER_NAMES = {
    "THA": "Thailand",     "VNM": "Vietnam",      "MMR": "Myanmar",
    "KHM": "Cambodia",     "LAO": "Laos",          "MYS": "Malaysia",
    "SGP": "Singapore",    "IDN": "Indonesia",     "PHL": "Philippines",
    "BRN": "Brunei",       "TLS": "Timor-Leste",
    "CHN": "China",        "USA": "United States", "JPN": "Japan",
    "IND": "India",        "KOR": "South Korea",   "AUS": "Australia",
}

# ISO3 → World Bank country code (same for most; exceptions below)
WB_CODE = {k: k for k in ALL_REPORTERS}
WB_CODE["TLS"] = "TMP"  # World Bank uses TMP for Timor-Leste

# WB API v2 returns 2-letter ISO2 codes in country.id — map back to ISO3
WB_ISO2_TO_ISO3 = {
    "TH": "THA", "VN": "VNM", "MM": "MMR", "KH": "KHM", "LA": "LAO",
    "MY": "MYS", "SG": "SGP", "ID": "IDN", "PH": "PHL", "BN": "BRN",
    "TP": "TLS",  # WB may use TP or TL for Timor-Leste
    "TL": "TLS",
    "CN": "CHN", "US": "USA", "JP": "JPN", "IN": "IND",
    "KR": "KOR", "AU": "AUS",
}

# ─── World Bank Trade Indicators ─────────────────────────────────────────────

WB_TRADE_INDICATORS = {
    "TX.VAL.MRCH.CD.WT": {
        "indicator_code": "EXPORTS_MERCH_USD",
        "indicator_name": "Merchandise Exports (USD Billion)",
        "unit":           "USD billion",
        "divisor":        1e9,
    },
    "TM.VAL.MRCH.CD.WT": {
        "indicator_code": "IMPORTS_MERCH_USD",
        "indicator_name": "Merchandise Imports (USD Billion)",
        "unit":           "USD billion",
        "divisor":        1e9,
    },
    "NE.EXP.GNFS.CD": {
        "indicator_code": "EXPORTS_USD",
        "indicator_name": "Exports of Goods & Services (USD Billion)",
        "unit":           "USD billion",
        "divisor":        1e9,
    },
    "NE.IMP.GNFS.CD": {
        "indicator_code": "IMPORTS_USD",
        "indicator_name": "Imports of Goods & Services (USD Billion)",
        "unit":           "USD billion",
        "divisor":        1e9,
    },
    "NE.TRD.GNFS.ZS": {
        "indicator_code": "TRADE_OPENNESS",
        "indicator_name": "Trade (% of GDP)",
        "unit":           "% of GDP",
        "divisor":        1.0,
    },
}

WB_BASE = "https://api.worldbank.org/v2"
REQUEST_DELAY = 1.5
MAX_RETRIES   = 3
START_YEAR    = 2019
END_YEAR      = 2024


def _fetch_wb_indicator(wb_code: str, iso3_list: list[str],
                        start: int, end: int) -> list[dict]:
    """Fetch a World Bank indicator for a list of countries."""
    wb_codes = ";".join(WB_CODE.get(c, c) for c in iso3_list)
    url = f"{WB_BASE}/country/{wb_codes}/indicator/{wb_code}"
    params = {
        "date":     f"{start}:{end}",
        "format":   "json",
        "per_page": "1000",
    }
    headers = {"User-Agent": "SEA-Dashboard/2.0", "Accept": "application/json"}

    for attempt in range(MAX_RETRIES):
        try:
            r = _get(url, headers=headers, params=params, timeout=25)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list) and len(data) > 1 and data[1]:
                    return data[1]
                return []
            elif r.status_code == 429:
                wait = 30 * (attempt + 1)
                print(f"    ⏸ Rate limited — waiting {wait}s", flush=True)
                time.sleep(wait)
            else:
                print(f"    ✗ HTTP {r.status_code}", flush=True)
                return []
        except Exception as e:
            print(f"    ⚠ attempt {attempt+1}: {e}", flush=True)
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
    return []


def _make_row(iso3: str, ind_code: str, ind_name: str, year: int,
              value, unit: str, source: str, source_url: str,
              note: str = "") -> dict:
    """Build a standard 22-field trade row."""
    if value is None:
        vtype    = "missing_official"
        quality  = "missing"
        conf     = "none"
    elif year >= CURR_YEAR:
        vtype    = "official_partial_2026"
        quality  = "partial"
        conf     = "medium"
    else:
        vtype    = "official_actual"
        quality  = "available"
        conf     = "high"

    return {
        "country_code":    iso3,
        "country_name":    REPORTER_NAMES.get(iso3, iso3),
        "sector":          "trade",
        "indicator_code":  ind_code,
        "indicator_name":  ind_name,
        "period":          str(year),
        "year":            year,
        "quarter":         None,
        "month":           None,
        "value":           value,
        "unit":            unit,
        "frequency":       "annual",
        "source":          source,
        "source_type":     "multilateral",
        "source_url":      source_url,
        "fetched_at":      ts_now(),
        "released_at":     None,
        "value_type":      vtype,
        "data_quality":    quality,
        "confidence":      conf,
        "extraction_method": "api",
        "limitation_note": note,
    }


def fetch_wb_trade(reporters: list[str], years: list[int]) -> list[dict]:
    """Fetch all WB trade indicators for the given reporters and years."""
    rows = []
    year_min = min(years)
    year_max = max(years)

    for wb_code, meta in WB_TRADE_INDICATORS.items():
        print(f"  ▸ {meta['indicator_name']}...", end=" ", flush=True)
        raw = _fetch_wb_indicator(wb_code, reporters, year_min, year_max)
        time.sleep(REQUEST_DELAY)

        count = 0
        for rec in raw:
            if rec.get("value") is None:
                continue
            country_obj = rec.get("country", {})
            wb_id  = country_obj.get("id", "")
            # WB returns 2-letter ISO2 codes in country.id
            iso3   = WB_ISO2_TO_ISO3.get(wb_id, wb_id)
            if iso3 not in ALL_REPORTERS:
                continue
            try:
                year = int(rec["date"])
            except (KeyError, ValueError):
                continue
            if year not in years:
                continue

            raw_val = rec["value"]
            divisor = meta["divisor"]
            try:
                val = round(float(raw_val) / divisor, 3) if raw_val is not None else None
            except (TypeError, ValueError):
                val = None

            note = "World Bank WDI — 1-2 year publication lag typical"
            rows.append(_make_row(
                iso3=iso3,
                ind_code=meta["indicator_code"],
                ind_name=meta["indicator_name"],
                year=year,
                value=val,
                unit=meta["unit"],
                source="World Bank WDI",
                source_url=f"https://api.worldbank.org/v2/country/{WB_CODE.get(iso3,iso3)}/indicator/{wb_code}",
                note=note,
            ))
            count += 1

        print(f"{count} rows", flush=True)

    return rows


def compute_trade_balance(all_rows: list[dict]) -> list[dict]:
    """
    Compute trade balance (exports - imports) per country per year.
    Uses EXPORTS_USD and IMPORTS_USD (goods & services).
    """
    balance_rows = []
    by_cy = {}
    for r in all_rows:
        if r["indicator_code"] in ("EXPORTS_USD", "IMPORTS_USD") and r["value"] is not None:
            key = (r["country_code"], r["year"])
            by_cy.setdefault(key, {})[r["indicator_code"]] = r

    for (iso3, year), ind_map in by_cy.items():
        exp_row = ind_map.get("EXPORTS_USD")
        imp_row = ind_map.get("IMPORTS_USD")
        if exp_row and imp_row:
            bal = round(exp_row["value"] - imp_row["value"], 3)
            balance_rows.append(_make_row(
                iso3=iso3,
                ind_code="TRADE_BALANCE_USD",
                ind_name="Trade Balance (Exports − Imports, USD Billion)",
                year=year,
                value=bal,
                unit="USD billion",
                source="Computed from World Bank WDI",
                source_url="https://api.worldbank.org/v2/country",
                note="Computed: EXPORTS_USD minus IMPORTS_USD (goods & services)",
            ))

    return balance_rows


def add_missing_bilateral_rows(reporters: list[str], years: list[int]) -> list[dict]:
    """
    Placeholder rows for bilateral partner flows that require a paid Comtrade subscription.
    These are labeled missing_official so the dashboard shows a 'No data' badge
    rather than a gap.
    """
    BILATERAL_INDICATORS = [
        ("EXPORTS_TO_CHN",      "Exports to China (USD Billion)"),
        ("IMPORTS_FROM_CHN",    "Imports from China (USD Billion)"),
        ("EXPORTS_TO_USA",      "Exports to United States (USD Billion)"),
        ("IMPORTS_FROM_USA",    "Imports from United States (USD Billion)"),
        ("TRADE_DEPENDENCY_CHN","China Trade Dependency (% of total trade)"),
        ("TRADE_DEPENDENCY_USA","United States Trade Dependency (% of total trade)"),
        ("TOP_TRADE_PARTNER_SHARE", "Top Trade Partner Share (% of total trade)"),
    ]
    note = ("Bilateral partner data requires UN Comtrade Plus subscription (HTTP 401). "
            "Free WITS and IMF DOTS APIs also unavailable (HTTP 403). "
            "Set COMTRADE_API_KEY in .env to enable bilateral fetching.")

    SEA_REPORTERS = [r for r in reporters if r in {
        "THA","VNM","MMR","KHM","LAO","MYS","SGP","IDN","PHL","BRN","TLS"
    }]

    rows = []
    for iso3 in SEA_REPORTERS:
        for year in years:
            for ind_code, ind_name in BILATERAL_INDICATORS:
                unit = "% of total trade" if "DEPENDENCY" in ind_code or "SHARE" in ind_code else "USD billion"
                rows.append({
                    "country_code":    iso3,
                    "country_name":    REPORTER_NAMES.get(iso3, iso3),
                    "sector":          "trade",
                    "indicator_code":  ind_code,
                    "indicator_name":  ind_name,
                    "period":          str(year),
                    "year":            year,
                    "quarter":         None,
                    "month":           None,
                    "value":           None,
                    "unit":            unit,
                    "frequency":       "annual",
                    "source":          "UN Comtrade (subscription required)",
                    "source_type":     "multilateral",
                    "source_url":      "https://comtradeapi.un.org",
                    "fetched_at":      ts_now(),
                    "released_at":     None,
                    "value_type":      "missing_official",
                    "data_quality":    "missing",
                    "confidence":      "none",
                    "extraction_method": "api",
                    "limitation_note": note,
                })
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reporter", nargs="+", default=ALL_REPORTERS,
                        choices=ALL_REPORTERS, help="Reporter country ISO3 codes")
    parser.add_argument("--year", type=int, default=END_YEAR,
                        help=f"Latest year to fetch (default {END_YEAR})")
    parser.add_argument("--all-years", action="store_true",
                        help=f"Fetch all years {START_YEAR}–{END_YEAR}")
    parser.add_argument("--no-missing", action="store_true",
                        help="Skip bilateral missing_official placeholder rows")
    args = parser.parse_args()

    years = list(range(START_YEAR, args.year + 1)) if args.all_years else [args.year]
    comtrade_key = os.environ.get("COMTRADE_API_KEY", "")

    print(f"\n{'═'*60}")
    print(f"  Trade Flows Fetcher — {today_str}")
    print(f"  Reporters : {args.reporter}")
    print(f"  Years     : {years}")
    print(f"  Source    : World Bank WDI (Comtrade API: {'✓ key set' if comtrade_key else '✗ not set — using WB'})")
    print(f"{'═'*60}\n")

    all_rows = []

    # ── World Bank total trade ─────────────────────────────────────────────
    print("  ── World Bank WDI Trade Indicators ─────────────────")
    wb_rows = fetch_wb_trade(args.reporter, years)
    all_rows.extend(wb_rows)
    print(f"  → {len(wb_rows)} rows from World Bank\n")

    # ── Computed: trade balance ────────────────────────────────────────────
    print("  ── Computed Metrics ─────────────────────────────────")
    bal_rows = compute_trade_balance(all_rows)
    all_rows.extend(bal_rows)
    print(f"  ▸ Trade balance rows  : {len(bal_rows)}", flush=True)

    # ── Bilateral missing placeholders ────────────────────────────────────
    if not args.no_missing:
        miss_rows = add_missing_bilateral_rows(args.reporter, years)
        all_rows.extend(miss_rows)
        print(f"  ▸ Bilateral placeholders: {len(miss_rows)} (missing_official)", flush=True)

    # ── Save raw snapshot ─────────────────────────────────────────────────
    raw_f = RAW_DIR / f"wb_trade_{today_str}.json"
    raw_f.write_text(json.dumps({
        "fetched_at": ts_now(), "years": years,
        "reporters": args.reporter, "records": all_rows,
    }, indent=2))

    # ── Save normalized output ─────────────────────────────────────────────
    non_null = sum(1 for r in all_rows if r["value"] is not None)
    result = {
        "source":     "World Bank WDI (total trade) + UN Comtrade bilateral (unavailable - subscription required)",
        "source_id":  "WB_TRADE",
        "fetched_at": ts_now(),
        "years":      years,
        "reporters":  args.reporter,
        "total_rows": len(all_rows),
        "non_null":   non_null,
        "comtrade_api_available": bool(comtrade_key),
        "limitation": (
            "Bilateral partner flows (China/USA dependency) require UN Comtrade Plus subscription. "
            "Total trade and trade balance are from World Bank WDI (official, ~1yr lag). "
            "Bilateral rows are marked missing_official."
        ),
        "records": all_rows,
    }

    out_file = PROC_DIR / "comtrade_normalized.json"
    out_file.write_text(json.dumps(result, indent=2))

    trade_flows_file = PROC_DIR / "trade_flows.json"
    trade_flows_file.write_text(json.dumps(result, indent=2))

    print(f"\n{'─'*60}")
    print(f"  ✓ Total rows     : {len(all_rows)}")
    print(f"  ✓ Non-null       : {non_null}")
    print(f"  ✓ Missing (bilateral) : {len(all_rows) - non_null}")
    print(f"  📄 {out_file.relative_to(PROJECT_ROOT)}")
    print(f"  📄 pipeline/data/processed/trade_flows.json\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
