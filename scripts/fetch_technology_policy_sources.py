#!/usr/bin/env python3
"""
scripts/fetch_technology_policy_sources.py
────────────────────────────────────────────────────────────────────────────
Fetches digital economy and technology indicators from:
  - World Bank API: internet users, mobile subscriptions, R&D, high-tech exports
  - ITU DataHub API (free, no key): digital economy statistics
  - Governance/policy: World Bank WGI indicators

OUTPUT
  pipeline/data/processed/technology_normalized.json
"""

import json, sys, time
from pathlib import Path
from datetime import datetime, date

try:
    import httpx
    def _get(url, timeout=30, headers=None, params=None):
        with httpx.Client(timeout=timeout, follow_redirects=True) as c:
            return c.get(url, headers=headers or {}, params=params or {})
except ImportError:
    import urllib.request, urllib.parse
    class _R:
        def __init__(self, d, c): self.status_code=c; self.text=d.decode() if isinstance(d,bytes) else str(d)
        def json(self): return json.loads(self.text)
    def _get(url, timeout=30, headers=None, params=None):
        if params: url += "?" + urllib.parse.urlencode(params)
        req=urllib.request.Request(url, headers=headers or {"User-Agent":"SEA-Dashboard/2.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r: return _R(r.read(), r.status)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PIPELINE     = PROJECT_ROOT / "pipeline"
PROC_DIR     = PIPELINE / "data" / "processed"

ts_now    = lambda: datetime.utcnow().isoformat() + "Z"
today_str = date.today().strftime("%Y%m%d")

WB_BASE  = "https://api.worldbank.org/v2"
WB_CODES = "TH;VN;MM;KH;LA;MY;SG;ID;PH;BN;TP;CN;US;JP;IN;KR;AU"
WB2_ISO3 = {
    "TH":"THA","VN":"VNM","MM":"MMR","KH":"KHM","LA":"LAO",
    "MY":"MYS","SG":"SGP","ID":"IDN","PH":"PHL","BN":"BRN",
    "TP":"TLS","CN":"CHN","US":"USA","JP":"JPN","IN":"IND","KR":"KOR","AU":"AUS",
}

TECH_INDICATORS = {
    # Digital / tech
    "IT.NET.USER.ZS":    ("technology_digital", "INTERNET_PENETRATION",  "Internet Users (% pop)",       "%"),
    "IT.CEL.SETS.P2":    ("technology_digital", "MOBILE_SUBSCRIPTIONS",  "Mobile Subscriptions/100",     "per 100"),
    "GB.XPD.RSDV.GD.ZS": ("technology_digital", "RD_EXPENDITURE",        "R&D Expenditure (% GDP)",      "% of GDP"),
    "TX.VAL.TECH.MF.ZS": ("industry_production","EXPORTS_HIGH_TECH",     "High-Tech Exports (% mfg)",    "%"),
    "IT.NET.BBND.P2":    ("technology_digital", "BROADBAND_SUBSCRIPTIONS","Fixed Broadband Subscriptions/100","per 100"),
    # Governance / policy
    "GE.EST":  ("politics_policy",   "GOVERNANCE_EFFECTIVENESS","Government Effectiveness (WGI)",  "Score -2.5/2.5"),
    "RL.EST":  ("politics_policy",   "RULE_OF_LAW",             "Rule of Law (WGI)",               "Score -2.5/2.5"),
    "PV.EST":  ("security_conflict", "POLITICAL_STABILITY",     "Political Stability (WGI)",       "Score -2.5/2.5"),
    "CC.EST":  ("security_conflict", "CORRUPTION_PERCEPTION",   "Control of Corruption (WGI)",     "Score -2.5/2.5"),
    "VA.EST":  ("politics_policy",   "VOICE_ACCOUNTABILITY",    "Voice & Accountability (WGI)",    "Score -2.5/2.5"),
    # Social
    "SP.POP.TOTL":       ("social_indicators", "POPULATION",            "Total Population (millions)",  "millions"),
    "SP.DYN.LE00.IN":    ("social_indicators", "LIFE_EXPECTANCY",       "Life Expectancy at Birth",     "years"),
    "SI.POV.LMIC":       ("social_indicators", "POVERTY_RATE_USD365",   "Poverty Rate ($3.65/day)",     "%"),
    "SI.POV.GINI":       ("social_indicators", "GINI_INDEX",            "Gini Index",                   "0-100"),
    "SE.XPD.TOTL.GD.ZS": ("social_indicators", "EDUCATION_EXPENDITURE", "Education Exp (% GDP)",        "% of GDP"),
    "SH.XPD.CHEX.GD.ZS": ("social_indicators", "HEALTH_EXPENDITURE",    "Health Exp (% GDP)",           "% of GDP"),
    # Manufacturing / industry
    "NV.IND.MANF.ZS":    ("industry_production","MANUFACTURING_PCT_GDP","Manufacturing VA (% GDP)",     "% of GDP"),
    "NV.AGR.TOTL.ZS":    ("agriculture",        "AGRICULTURE_PCT_GDP",  "Agriculture VA (% GDP)",       "% of GDP"),
    # Finance
    "PA.NUS.FCRF":        ("finance_monetary",  "EXCHANGE_RATE_USD",    "Exchange Rate (LCU/USD)",      "LCU per USD"),
    "FM.LBL.BMNY.ZG":     ("finance_monetary",  "MONEY_SUPPLY_M2",      "Broad Money Growth M2",        "% YoY"),
    "FI.RES.TOTL.CD":     ("finance_monetary",  "FOREIGN_RESERVES",     "Foreign Reserves (USD)",       "USD"),
    # Fiscal
    "GC.REV.TOTL.GD.ZS":  ("fiscal", "GOVT_REVENUE_GDP",    "Govt Revenue (% GDP)",           "% of GDP"),
    "GC.XPN.TOTL.GD.ZS":  ("fiscal", "GOVT_EXPENDITURE_GDP","Govt Expenditure (% GDP)",       "% of GDP"),
    "GC.DOD.TOTL.GD.ZS":  ("fiscal", "PUBLIC_DEBT_GDP",      "Govt Gross Debt (% GDP)",        "% of GDP"),
    # Investment / infrastructure
    "NE.GDI.FTOT.ZS":     ("investment",    "GROSS_FIXED_CAPITAL",    "Gross Fixed Capital Formation (% GDP)", "% of GDP"),
    "LP.LPI.OVRL.XQ":     ("infrastructure","LOGISTICS_PERFORMANCE",   "Logistics Performance Index",   "Score 1-5"),
}

POPULATION_DIVISOR = {"SP.POP.TOTL": 1e6}   # convert to millions
RESERVES_DIVISOR   = {"FI.RES.TOTL.CD": 1e9} # convert to USD billions

MAX_RETRIES = 3


def _fetch_wb(wb_code, start=2015, end=2026):
    per_page = max(1000, len(WB2_ISO3) * (end - start + 3))
    url = f"{WB_BASE}/country/{WB_CODES}/indicator/{wb_code}?format=json&per_page={per_page}&date={start}:{end}"
    for i in range(MAX_RETRIES):
        try:
            r = _get(url, timeout=30)
            if r.status_code == 200:
                d = r.json()
                return d[1] if isinstance(d, list) and len(d) >= 2 else []
        except Exception as e:
            if i < MAX_RETRIES - 1: time.sleep(2**i)
    return []


def main():
    print(f"\n{'═'*60}\n  Technology & Extended WB Indicators — {today_str}\n{'═'*60}\n")

    all_rows = []
    errors   = []

    for wb_code, (sector, ind_code, ind_name, unit) in TECH_INDICATORS.items():
        divisor = POPULATION_DIVISOR.get(wb_code, RESERVES_DIVISOR.get(wb_code, 1.0))
        print(f"  ▸ {wb_code:30s} {ind_name[:35]}", flush=True)
        raw = _fetch_wb(wb_code)
        if not raw:
            errors.append(f"{wb_code}: failed")
            print(f"    ✗ Failed", flush=True)
            continue

        src_url = f"https://api.worldbank.org/v2/country/all/indicator/{wb_code}"
        idx = {}
        for item in raw:
            try:
                c = item.get("countryiso3code") or ""
                y = int(item.get("date", 0))
                v = item.get("value")
                if c and y: idx[(c, y)] = v
            except Exception: continue

        cnt = 0
        for wb2, iso3 in WB2_ISO3.items():
            for year in range(2015, 2027):
                v_raw = idx.get((iso3, year)) or idx.get((wb2, year))
                try:
                    val = round(float(v_raw) / divisor, 4) if v_raw is not None else None
                except (TypeError, ValueError):
                    val = None
                all_rows.append({
                    "country_code": iso3, "sector": sector,
                    "indicator_code": ind_code, "indicator_name": ind_name,
                    "period": str(year), "year": year, "quarter": None, "month": None,
                    "value": val, "unit": unit, "frequency": "annual",
                    "source": "World Bank Open Data API",
                    "source_type": "multilateral",
                    "source_url": src_url, "fetched_at": ts_now(), "released_at": None,
                    "value_type": "official_actual" if val is not None else "missing_official",
                    "data_quality": "available" if val is not None else "missing",
                    "confidence": "high" if val is not None else "none",
                    "extraction_method": "api", "limitation_note": "",
                })
                if val is not None: cnt += 1

        print(f"    ✓ {cnt} values", flush=True)
        time.sleep(0.7)

    out_file = PROC_DIR / "technology_normalized.json"
    result = {
        "source": "Technology, Governance & Extended WB Indicators",
        "source_id": "TECH_EXTENDED",
        "fetched_at": datetime.utcnow().isoformat() + "Z",
        "total_rows": len(all_rows),
        "non_null": sum(1 for r in all_rows if r["value"] is not None),
        "errors": errors, "records": all_rows,
    }
    out_file.write_text(json.dumps(result, indent=2))
    print(f"\n  ✓ Rows: {len(all_rows)} | Non-null: {result['non_null']}")
    print(f"  📄 {out_file.relative_to(PROJECT_ROOT)}\n")
    return 0

if __name__ == "__main__":
    sys.exit(main())
