#!/usr/bin/env python3
"""
scripts/fetch_un_comtrade.py
────────────────────────────────────────────────────────────────────────────
Fetches bilateral trade data from UN Comtrade Plus API.

FREE TIER: 500 calls/hour without API key; 10,000/hour with key.
API key loaded from .env (COMTRADE_API_KEY) if available.

FETCHES:
  - Total exports and imports by reporter country
  - Bilateral trade with China, USA, Japan, India, Korea, Australia, EU
  - Annual data 2019–2024 (most recent available)
  - Computes: trade balance, dependency score per partner

REPORTER COUNTRIES: 11 SEA
PARTNER COUNTRIES: 7 (CHN, USA, JPN, IND, KOR, AUS, EU/EU27)

OUTPUT
  pipeline/data/raw/comtrade/comtrade_{reporter}_{YYYYMMDD}.json
  pipeline/data/processed/comtrade_normalized.json

USAGE
  python scripts/fetch_un_comtrade.py
  python scripts/fetch_un_comtrade.py --reporter THA VNM MYS
  python scripts/fetch_un_comtrade.py --year 2024
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

# ─── Comtrade Configuration ────────────────────────────────────────────────────

API_KEY = os.environ.get("COMTRADE_API_KEY", "")
BASE_URL = "https://comtradeapi.un.org/data/v1/get"

# Reporter = SEA countries (Comtrade M49/ISO3)
REPORTERS = {
    "THA": 764,  "VNM": 704,  "MMR": 104,  "KHM": 116,
    "LAO": 418,  "MYS": 458,  "SGP": 702,  "IDN": 360,
    "PHL": 608,  "BRN":  96,  "TLS": 626,
}

REPORTER_NAMES = {
    "THA": "Thailand",    "VNM": "Vietnam",     "MMR": "Myanmar",
    "KHM": "Cambodia",    "LAO": "Laos",         "MYS": "Malaysia",
    "SGP": "Singapore",   "IDN": "Indonesia",    "PHL": "Philippines",
    "BRN": "Brunei",      "TLS": "Timor-Leste",
}

# Partner countries
PARTNERS = {
    "CHN": 156,
    "USA": 842,
    "JPN": 392,
    "IND": 356,
    "KOR": 410,
    "AUS":  36,
    "EU":  918,   # EU27 aggregate in Comtrade
    "ALL":   0,   # World total
}

PARTNER_NAMES = {
    "CHN": "China", "USA": "United States", "JPN": "Japan",
    "IND": "India", "KOR": "South Korea", "AUS": "Australia",
    "EU": "European Union", "ALL": "World Total",
}

START_YEAR = 2019
END_YEAR   = 2024  # Comtrade typically has ~1 year lag

REQUEST_DELAY = 2.0  # Be polite with free tier
MAX_RETRIES   = 3


def _fetch_comtrade(reporter_code: int, partner_code: int, year: int,
                   flow: str = "X,M") -> dict | None:
    """
    Fetch Comtrade data for a reporter/partner/year.
    flow: "X" = exports, "M" = imports, "X,M" = both
    """
    params = {
        "typeCode": "C",        # Commodities
        "freqCode": "A",        # Annual
        "clCode":   "HS",       # Harmonized System
        "reporterCode": reporter_code,
        "period":   str(year),
        "cmdCode":  "TOTAL",    # Total trade
        "flowCode": flow,
        "partnerCode": partner_code,
        "partner2Code": 0,
    }
    if API_KEY:
        params["subscription-key"] = API_KEY

    headers = {"User-Agent": "SEA-Dashboard/2.0", "Accept": "application/json"}
    if API_KEY:
        headers["Ocp-Apim-Subscription-Key"] = API_KEY

    for attempt in range(MAX_RETRIES):
        try:
            r = _get(BASE_URL, headers=headers, params=params, timeout=30)
            if r.status_code == 200:
                return r.json()
            elif r.status_code == 429:
                # Rate limited
                wait = 60 * (attempt + 1)
                print(f"    ⏸ Rate limited — waiting {wait}s", flush=True)
                time.sleep(wait)
            elif r.status_code == 403:
                print(f"    ✗ API key required or exhausted", flush=True)
                return None
        except Exception as e:
            print(f"    ⚠ attempt {attempt+1}: {e}", flush=True)
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
    return None


def _parse_flows(raw: dict | None, reporter_iso3: str, partner_iso3: str, year: int,
                 source_url: str) -> list[dict]:
    if not raw or "data" not in raw:
        return []

    rows = []
    data = raw.get("data", [])

    exports_val = None
    imports_val = None

    for record in (data if isinstance(data, list) else []):
        flow_code = str(record.get("flowCode", record.get("flowDesc", ""))).upper()
        val_raw   = record.get("primaryValue", record.get("TradeValue"))
        try:
            val_usd = float(val_raw) if val_raw is not None else None
            # Convert to USD billions
            if val_usd is not None:
                val_b = round(val_usd / 1e9, 3)
            else:
                val_b = None
        except (TypeError, ValueError):
            val_b = None

        if val_b is None:
            continue

        if "X" in flow_code or "export" in flow_code.lower():
            exports_val = val_b
        elif "M" in flow_code or "import" in flow_code.lower():
            imports_val = val_b

    note_parts = []
    if not API_KEY:
        note_parts.append("Free tier (500 calls/hr limit)")
    note = "; ".join(note_parts)

    def add_row(ind_code, ind_name, val, unit="USD billion"):
        rows.append({
            "country_code":    reporter_iso3,
            "country_name":    REPORTER_NAMES.get(reporter_iso3, reporter_iso3),
            "sector":          "trade",
            "indicator_code":  ind_code,
            "indicator_name":  ind_name,
            "period":          str(year),
            "year":            year,
            "quarter":         None,
            "month":           None,
            "value":           val,
            "unit":            unit,
            "frequency":       "annual",
            "source":          "UN Comtrade Database",
            "source_type":     "multilateral",
            "source_url":      source_url,
            "fetched_at":      ts_now(),
            "released_at":     None,
            "value_type":      "official_actual" if val is not None else "missing_official",
            "data_quality":    "available" if val is not None else "missing",
            "confidence":      "high" if val is not None else "none",
            "extraction_method": "api",
            "limitation_note": note,
        })

    if partner_iso3 == "ALL":
        if exports_val is not None:
            add_row("EXPORTS_USD", "Total Exports (USD Billion)", exports_val)
        if imports_val is not None:
            add_row("IMPORTS_USD", "Total Imports (USD Billion)", imports_val)
        if exports_val is not None and imports_val is not None:
            add_row("TRADE_BALANCE_USD", "Trade Balance (USD Billion)",
                    round(exports_val - imports_val, 3))
    else:
        partner_name = PARTNER_NAMES.get(partner_iso3, partner_iso3)
        if exports_val is not None:
            add_row(f"EXPORTS_TO_{partner_iso3}",
                    f"Exports to {partner_name} (USD Billion)", exports_val)
        if imports_val is not None:
            add_row(f"IMPORTS_FROM_{partner_iso3}",
                    f"Imports from {partner_name} (USD Billion)", imports_val)

    return rows


def _compute_dependency_scores(all_rows: list[dict]) -> list[dict]:
    """
    Compute China/USA trade dependency scores.
    dependency_score = trade_with_partner / total_trade × 100
    """
    dep_rows = []
    ts = ts_now()

    by_country_year = {}
    for r in all_rows:
        key = (r["country_code"], r["year"])
        if key not in by_country_year:
            by_country_year[key] = {}
        by_country_year[key][r["indicator_code"]] = r["value"]

    for (iso3, year), inds in by_country_year.items():
        total_x = inds.get("EXPORTS_USD")
        total_m = inds.get("IMPORTS_USD")
        total_trade = None
        if total_x is not None and total_m is not None:
            total_trade = total_x + total_m

        for partner in ["CHN", "USA"]:
            px = inds.get(f"EXPORTS_TO_{partner}")
            pm = inds.get(f"IMPORTS_FROM_{partner}")
            if total_trade and total_trade > 0:
                partner_trade = 0
                if px is not None:
                    partner_trade += px
                if pm is not None:
                    partner_trade += pm
                if partner_trade > 0:
                    dep = round(partner_trade / total_trade * 100, 1)
                    level = "high" if dep >= 40 else ("medium" if dep >= 20 else "low")
                    dep_rows.append({
                        "country_code":    iso3,
                        "country_name":    REPORTER_NAMES.get(iso3, iso3),
                        "sector":          "trade",
                        "indicator_code":  f"TRADE_DEPENDENCY_{partner}",
                        "indicator_name":  f"{PARTNER_NAMES[partner]} Trade Dependency",
                        "period":          str(year),
                        "year":            year,
                        "quarter":         None,
                        "month":           None,
                        "value":           dep,
                        "unit":            "% of total trade",
                        "frequency":       "annual",
                        "source":          "Computed from UN Comtrade",
                        "source_type":     "computed",
                        "source_url":      BASE_URL,
                        "fetched_at":      ts,
                        "released_at":     None,
                        "value_type":      "official_actual",
                        "data_quality":    "available",
                        "confidence":      "high",
                        "extraction_method": "computed",
                        "limitation_note": f"Dependency level: {level}. "
                                          f"Computed from bilateral + total trade flows.",
                    })
    return dep_rows


def _compute_top_partner(all_rows: list[dict]) -> list[dict]:
    """
    For each country × year, find the partner with highest bilateral trade share.
    Emits TOP_TRADE_PARTNER rows (value = dependency %, limitation_note = partner name).
    """
    top_rows = []
    ts = ts_now()

    # Group dependency scores by country/year/partner
    by_cy = {}
    for r in all_rows:
        code = r.get("indicator_code", "")
        if not code.startswith("TRADE_DEPENDENCY_"):
            continue
        partner = code.replace("TRADE_DEPENDENCY_", "")
        key = (r["country_code"], r["year"])
        by_cy.setdefault(key, {})[partner] = r["value"]

    for (iso3, year), partner_deps in by_cy.items():
        if not partner_deps:
            continue
        top_partner = max(partner_deps, key=lambda p: partner_deps[p] or 0)
        top_val     = partner_deps[top_partner]
        if top_val is None:
            continue
        level = "high" if top_val >= 40 else ("medium" if top_val >= 20 else "low")
        top_rows.append({
            "country_code":    iso3,
            "country_name":    REPORTER_NAMES.get(iso3, iso3),
            "sector":          "trade",
            "indicator_code":  "TOP_TRADE_PARTNER_SHARE",
            "indicator_name":  "Top Trade Partner Share",
            "period":          str(year),
            "year":            year,
            "quarter":         None,
            "month":           None,
            "value":           top_val,
            "unit":            "% of total trade",
            "frequency":       "annual",
            "source":          "Computed from UN Comtrade",
            "source_type":     "computed",
            "source_url":      BASE_URL,
            "fetched_at":      ts,
            "released_at":     None,
            "value_type":      "official_actual",
            "data_quality":    "available",
            "confidence":      "high",
            "extraction_method": "computed",
            "limitation_note": f"Top partner: {PARTNER_NAMES.get(top_partner, top_partner)} "
                               f"({top_val:.1f}%, {level} dependency)",
        })
    return top_rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reporter", nargs="+", default=list(REPORTERS.keys()),
                        choices=list(REPORTERS.keys()),
                        help="Reporter country ISO3 codes")
    parser.add_argument("--year", type=int, default=END_YEAR,
                        help=f"Year to fetch (default {END_YEAR})")
    parser.add_argument("--all-years", action="store_true",
                        help=f"Fetch all years {START_YEAR}-{END_YEAR}")
    args = parser.parse_args()

    years = list(range(START_YEAR, args.year + 1)) if args.all_years else [args.year]

    print(f"\n{'═'*60}")
    print(f"  UN Comtrade Fetcher — {today_str}")
    print(f"  Reporters: {args.reporter}")
    print(f"  Years: {years}")
    print(f"  API key: {'✓ set' if API_KEY else '✗ not set (free tier)'}")
    print(f"{'═'*60}\n")

    all_rows = []
    errors   = []

    for iso3 in args.reporter:
        reporter_code = REPORTERS.get(iso3)
        if reporter_code is None:
            continue
        print(f"\n  ── {iso3} ──────────────────────────────────", flush=True)

        country_rows = []
        for year in years:
            # 1. Fetch total trade (partner = World)
            print(f"    {year}: total trade...", end=" ", flush=True)
            raw = _fetch_comtrade(reporter_code, PARTNERS["ALL"], year, "X,M")
            rows = _parse_flows(raw, iso3, "ALL", year,
                               f"{BASE_URL}/C/A/HS?reporterCode={reporter_code}&period={year}")
            country_rows.extend(rows)
            print(f"{len(rows)} rows", flush=True)
            time.sleep(REQUEST_DELAY)

            # 2. Fetch bilateral flows for all 7 key partners
            for partner_iso3, partner_code in PARTNERS.items():
                if partner_iso3 == "ALL":
                    continue
                print(f"    {year}: → {partner_iso3}...", end=" ", flush=True)
                try:
                    raw = _fetch_comtrade(reporter_code, partner_code, year, "X,M")
                    rows = _parse_flows(raw, iso3, partner_iso3, year,
                                       f"{BASE_URL}/C/A/HS?reporterCode={reporter_code}&partnerCode={partner_code}&period={year}")
                    country_rows.extend(rows)
                    print(f"{len(rows)} rows", flush=True)
                except Exception as e:
                    errors.append(f"{iso3}→{partner_iso3} {year}: {e}")
                    print(f"FAILED: {e}", flush=True)
                time.sleep(REQUEST_DELAY)

        # Save per-country raw
        raw_f = RAW_DIR / f"{iso3}_{today_str}.json"
        raw_f.write_text(json.dumps({"rows": country_rows}, indent=2))
        all_rows.extend(country_rows)
        print(f"  ✓ {iso3}: {len(country_rows)} rows total", flush=True)

    # Compute dependency scores + top-partner rows
    print("\n  ▸ Computing trade dependency scores...", flush=True)
    dep_rows = _compute_dependency_scores(all_rows)
    all_rows.extend(dep_rows)
    print(f"    ✓ {len(dep_rows)} dependency rows", flush=True)

    print("  ▸ Computing top-partner relationships...", flush=True)
    top_rows = _compute_top_partner(all_rows)
    all_rows.extend(top_rows)
    print(f"    ✓ {len(top_rows)} top-partner rows", flush=True)

    out_file = PROC_DIR / "comtrade_normalized.json"
    result = {
        "source":     "UN Comtrade Database",
        "source_id":  "UN_COMTRADE",
        "fetched_at": datetime.utcnow().isoformat() + "Z",
        "years":      years,
        "reporters":  args.reporter,
        "total_rows": len(all_rows),
        "non_null":   sum(1 for r in all_rows if r["value"] is not None),
        "errors":     errors,
        "records":    all_rows,
    }
    out_file.write_text(json.dumps(result, indent=2))
    # Also write trade_flows.json alias (used by dashboard trade charts)
    (PROC_DIR / "trade_flows.json").write_text(json.dumps(result, indent=2))

    print(f"\n{'─'*60}")
    print(f"  ✓ Total rows  : {len(all_rows)}")
    print(f"  ✓ Non-null    : {result['non_null']}")
    if dep_rows:
        print(f"  ✓ Dep scores  : {len(dep_rows)}")
    if top_rows:
        print(f"  ✓ Top-partner : {len(top_rows)}")
    if errors:
        print(f"  ⚠ Errors      : {len(errors)}")
        for e in errors[:5]:
            print(f"    · {e}")
    print(f"  📄 {out_file.relative_to(PROJECT_ROOT)}")
    print(f"  📄 pipeline/data/processed/trade_flows.json\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
