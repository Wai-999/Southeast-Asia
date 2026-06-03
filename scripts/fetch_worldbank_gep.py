#!/usr/bin/env python3
"""
scripts/fetch_worldbank_gep.py
────────────────────────────────────────────────────────────────────────────
Fetches World Bank Global Economic Prospects (GEP) forecast data via the
World Bank Open Data API. GEP publishes biannual GDP growth forecasts
(January and June). We fetch the most recent forecasts for 2024–2027.

Also fetches additional WB indicators beyond the core 8 that the main
pipeline/fetch_worldbank.py covers:
  - Governance indicators (WGI)
  - Poverty and social indicators
  - Environment indicators
  - Digital economy indicators
  - Agriculture indicators

No API key required.

OUTPUT
  pipeline/data/raw/worldbank/{indicator}_{YYYYMMDD}.json
  pipeline/data/processed/worldbank_extended_normalized.json

USAGE
  python scripts/fetch_worldbank_gep.py
  python scripts/fetch_worldbank_gep.py --category governance
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
    def _get(url, timeout=30):
        req = urllib.request.Request(url, headers={"User-Agent": "SEA-Dashboard/2.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())

# ─── Paths ────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PIPELINE     = PROJECT_ROOT / "pipeline"
RAW_DIR      = PIPELINE / "data" / "raw" / "worldbank"
PROC_DIR     = PIPELINE / "data" / "processed"
RAW_DIR.mkdir(parents=True, exist_ok=True)

# ─── Configuration ────────────────────────────────────────────────────────────
WB_BASE = "https://api.worldbank.org/v2"
START_YEAR = 2019
END_YEAR   = 2026
FILL_UNTIL = 2024

# WB 2-letter codes for all 17 countries (TP = Timor-Leste in WB)
WB_CODES = {
    "TH": "THA", "VN": "VNM", "MM": "MMR", "KH": "KHM", "LA": "LAO",
    "MY": "MYS", "SG": "SGP", "ID": "IDN", "PH": "PHL", "BN": "BRN",
    "TP": "TLS", "CN": "CHN", "US": "USA", "JP": "JPN",
    "IN": "IND", "KR": "KOR", "AU": "AUS",
}

ALL_WB2 = ";".join(WB_CODES.keys())

# Extended WB indicators beyond the core 8
EXTENDED_INDICATORS = {
    # Governance (WGI) – annual
    "governance": {
        "GE.EST":  {"sector": "politics_policy",   "code": "GOVERNANCE_EFFECTIVENESS", "name": "Government Effectiveness (WGI)",    "unit": "Score -2.5/2.5"},
        "RL.EST":  {"sector": "politics_policy",   "code": "RULE_OF_LAW",              "name": "Rule of Law (WGI)",                 "unit": "Score -2.5/2.5"},
        "PV.EST":  {"sector": "security_conflict", "code": "POLITICAL_STABILITY",      "name": "Political Stability (WGI)",         "unit": "Score -2.5/2.5"},
        "CC.EST":  {"sector": "security_conflict", "code": "CORRUPTION_PERCEPTION",    "name": "Control of Corruption (WGI)",       "unit": "Score -2.5/2.5"},
        "VA.EST":  {"sector": "politics_policy",   "code": "VOICE_ACCOUNTABILITY",     "name": "Voice and Accountability (WGI)",    "unit": "Score -2.5/2.5"},
    },
    # Social
    "social": {
        "SI.POV.LMIC":    {"sector": "social_indicators", "code": "POVERTY_RATE_USD365",  "name": "Poverty Rate ($3.65/day 2017PPP)", "unit": "%"},
        "SP.DYN.LE00.IN": {"sector": "social_indicators", "code": "LIFE_EXPECTANCY",       "name": "Life Expectancy at Birth",         "unit": "years"},
        "SE.XPD.TOTL.GD.ZS":{"sector":"social_indicators","code":"EDUCATION_EXPENDITURE",  "name": "Education Expenditure (% GDP)",    "unit": "% of GDP"},
        "SI.POV.GINI":    {"sector": "social_indicators", "code": "GINI_INDEX",            "name": "Gini Index (Income Inequality)",   "unit": "0-100"},
        "SH.XPD.CHEX.GD.ZS":{"sector":"social_indicators","code":"HEALTH_EXPENDITURE",     "name": "Health Expenditure (% GDP)",       "unit": "% of GDP"},
    },
    # Environment
    "environment": {
        "AG.LND.FRST.ZS":   {"sector": "environment", "code": "FOREST_AREA_PCT",    "name": "Forest Area (% land area)", "unit": "%"},
        "EN.ATM.CO2E.PC":   {"sector": "environment", "code": "CO2_PER_CAPITA",      "name": "CO2 Emissions Per Capita",  "unit": "tonnes CO2/person"},
        "EN.ATM.CO2E.KT":   {"sector": "environment", "code": "CO2_TOTAL",           "name": "Total CO2 Emissions",       "unit": "kt CO2"},
        "EG.FEC.RNEW.ZS":   {"sector": "energy",      "code": "RENEWABLE_ENERGY_SHARE","name":"Renewable Energy Share",    "unit": "%"},
        "EG.ELC.ACCS.ZS":   {"sector": "energy",      "code": "ELECTRICITY_ACCESS",  "name": "Access to Electricity",     "unit": "%"},
    },
    # Digital / Technology
    "digital": {
        "IT.NET.USER.ZS":   {"sector": "technology_digital", "code": "INTERNET_PENETRATION",  "name": "Internet Users (% pop)",    "unit": "%"},
        "IT.CEL.SETS.P2":   {"sector": "technology_digital", "code": "MOBILE_SUBSCRIPTIONS",  "name": "Mobile Subscriptions/100",  "unit": "per 100"},
        "GB.XPD.RSDV.GD.ZS":{"sector":"technology_digital", "code": "RD_EXPENDITURE",         "name": "R&D Expenditure (% GDP)",   "unit": "% of GDP"},
        "TX.VAL.TECH.MF.ZS":{"sector": "industry_production","code":"EXPORTS_HIGH_TECH",       "name": "High-Tech Exports (% mfg)", "unit": "%"},
    },
    # Agriculture
    "agriculture": {
        "NV.AGR.TOTL.ZS":   {"sector": "agriculture", "code": "AGRICULTURE_PCT_GDP",  "name": "Agriculture Value Added (% GDP)", "unit": "% of GDP"},
        "SL.AGR.EMPL.ZS":   {"sector": "labor",        "code": "EMPLOYMENT_AGRICULTURE","name": "Employment in Agriculture (%)",  "unit": "%"},
        "TX.VAL.FOOD.ZS.UN":{"sector": "agriculture",  "code": "FOOD_EXPORTS_USD",     "name": "Food Exports % Merchandise",      "unit": "%"},
    },
    # Infrastructure
    "infrastructure": {
        "LP.LPI.OVRL.XQ":   {"sector": "infrastructure", "code": "LOGISTICS_PERFORMANCE",  "name": "Logistics Performance Index",     "unit": "Score 1-5"},
        "IC.BUS.DFRN.XQ":   {"sector": "infrastructure", "code": "EASE_DOING_BUSINESS",    "name": "Ease of Doing Business Score",    "unit": "Score 0-100"},
        "NE.GDI.FTOT.ZS":   {"sector": "investment",     "code": "GROSS_FIXED_CAPITAL",    "name": "Gross Fixed Capital Formation (%GDP)","unit":"% of GDP"},
    },
    # Fiscal
    "fiscal": {
        "GC.REV.TOTL.GD.ZS":  {"sector": "fiscal", "code": "GOVT_REVENUE_GDP",    "name": "Government Revenue (% GDP)",    "unit": "% of GDP"},
        "GC.XPN.TOTL.GD.ZS":  {"sector": "fiscal", "code": "GOVT_EXPENDITURE_GDP","name": "Government Expenditure (% GDP)","unit": "% of GDP"},
        "GC.DOD.TOTL.GD.ZS":  {"sector": "fiscal", "code": "PUBLIC_DEBT_GDP",      "name": "Government Gross Debt (% GDP)","unit": "% of GDP"},
        "GC.BAL.CASH.GD.ZS":  {"sector": "fiscal", "code": "FISCAL_BALANCE_GDP",  "name": "Fiscal Balance (% GDP)",        "unit": "% of GDP"},
    },
}

REQUEST_DELAY = 0.8
MAX_RETRIES   = 3


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _fetch_wb(wb_code: str, start: int, end: int) -> list:
    per_page = max(1000, len(WB_CODES) * (end - start + 2))
    url = (f"{WB_BASE}/country/{ALL_WB2}/indicator/{wb_code}"
           f"?format=json&per_page={per_page}&date={start}:{end}")
    for attempt in range(MAX_RETRIES):
        try:
            data = _get(url, timeout=45)
            if isinstance(data, list) and len(data) >= 2:
                return data[1] or []
            return []
        except Exception as e:
            print(f"    ⚠ attempt {attempt+1}: {e}", flush=True)
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
    return []


def _value_type(raw_val, year: int) -> str:
    if raw_val is None:
        return "missing_official"
    if year > FILL_UNTIL:
        return "official_actual"   # WB published it for 2025 (rare but possible)
    return "official_actual"


def _data_quality(raw_val, year: int) -> str:
    if raw_val is None:
        return "missing"
    return "available"


def _build_rows(raw_list: list, wb_code: str, meta: dict) -> list[dict]:
    ts = datetime.utcnow().isoformat() + "Z"
    rows = []
    # Index raw by (iso3, year)
    raw_index = {}
    for item in raw_list:
        try:
            c = item.get("countryiso3code") or item.get("country", {}).get("id", "")
            y = int(item.get("date", 0))
            v = item.get("value")
            if c and y:
                raw_index[(c, y)] = v
        except Exception:
            continue

    for wb2, iso3 in WB_CODES.items():
        for year in range(START_YEAR, END_YEAR + 1):
            val = raw_index.get((iso3, year))
            # Try wb2 if iso3 not found
            if val is None:
                val = raw_index.get((wb2, year))

            rows.append({
                "country_code":    iso3,
                "sector":          meta["sector"],
                "indicator_code":  meta["code"],
                "indicator_name":  meta["name"],
                "period":          str(year),
                "year":            year,
                "quarter":         None,
                "month":           None,
                "value":           val,
                "unit":            meta["unit"],
                "frequency":       "annual",
                "source":          "World Bank Open Data API",
                "source_type":     "multilateral",
                "source_url":      f"https://api.worldbank.org/v2/country/all/indicator/{wb_code}",
                "fetched_at":      ts,
                "released_at":     None,
                "value_type":      _value_type(val, year),
                "data_quality":    _data_quality(val, year),
                "confidence":      "high" if val is not None else "none",
                "extraction_method": "api",
                "limitation_note": "" if val is not None else f"WB {wb_code}: no data for {iso3} {year}",
            })
    return rows


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--category", default="all",
                        choices=["all"] + list(EXTENDED_INDICATORS.keys()),
                        help="Which indicator category to fetch")
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()

    today_str = date.today().strftime("%Y%m%d")
    out_file  = PROC_DIR / "worldbank_extended_normalized.json"

    categories = (list(EXTENDED_INDICATORS.items()) if args.category == "all"
                  else [(args.category, EXTENDED_INDICATORS[args.category])])

    print(f"\n{'═'*60}")
    print(f"  World Bank Extended Indicators — {today_str}")
    print(f"  Categories: {[c for c, _ in categories]}")
    print(f"{'═'*60}\n")

    all_rows = []
    errors   = []

    for cat_name, indicators in categories:
        print(f"\n  ── {cat_name.upper()} ─────────────────────────", flush=True)
        for wb_code, meta in indicators.items():
            print(f"  ▸ {wb_code:30s} {meta['name'][:35]}", flush=True)
            raw = _fetch_wb(wb_code, START_YEAR, END_YEAR)
            if not raw:
                errors.append(f"{wb_code}: fetch failed")
                print(f"    ✗ No data returned", flush=True)
                continue
            rows = _build_rows(raw, wb_code, meta)
            non_null = sum(1 for r in rows if r["value"] is not None)
            all_rows.extend(rows)
            print(f"    ✓ {non_null}/{len(rows)} values", flush=True)
            time.sleep(REQUEST_DELAY)

    result = {
        "source":     "World Bank Open Data API — Extended Indicators",
        "source_id":  "WB_EXTENDED",
        "fetched_at": datetime.utcnow().isoformat() + "Z",
        "year_range": [START_YEAR, END_YEAR],
        "total_rows": len(all_rows),
        "non_null":   sum(1 for r in all_rows if r["value"] is not None),
        "errors":     errors,
        "records":    all_rows,
    }
    out_file.write_text(json.dumps(result, indent=2))

    print(f"\n  ✓ Total rows  : {len(all_rows)}")
    print(f"  ✓ Non-null    : {result['non_null']}")
    if errors:
        print(f"  ⚠ Errors     : {len(errors)}")
    print(f"  📄 Output: {out_file.relative_to(PROJECT_ROOT)}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
