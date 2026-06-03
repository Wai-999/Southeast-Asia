#!/usr/bin/env python3
"""
scripts/fetch_environment_sources.py
────────────────────────────────────────────────────────────────────────────
Fetches agriculture, social, and environment indicators from:
  - World Bank API (free): forest, CO2, poverty, agriculture
  - FAO FAOSTAT API (free): crop production, food prices
  - ILO ILOSTAT API (free): labor force statistics

OUTPUT  pipeline/data/processed/environment_normalized.json
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
PROC_DIR     = PROJECT_ROOT / "pipeline" / "data" / "processed"
ts_now    = lambda: datetime.utcnow().isoformat() + "Z"
today_str = date.today().strftime("%Y%m%d")

WB_BASE  = "https://api.worldbank.org/v2"
WB_CODES = "TH;VN;MM;KH;LA;MY;SG;ID;PH;BN;TP;CN;US;JP;IN;KR;AU"
WB2_ISO3 = {"TH":"THA","VN":"VNM","MM":"MMR","KH":"KHM","LA":"LAO","MY":"MYS","SG":"SGP","ID":"IDN","PH":"PHL","BN":"BRN","TP":"TLS","CN":"CHN","US":"USA","JP":"JPN","IN":"IND","KR":"KOR","AU":"AUS"}

# Agriculture + food + social indicators via WB
ENV_SOCIAL_INDICATORS = {
    "NV.AGR.TOTL.ZS":      ("agriculture","AGRICULTURE_PCT_GDP","Agriculture VA (% GDP)","% of GDP",1.0),
    "SL.AGR.EMPL.ZS":      ("labor","EMPLOYMENT_AGRICULTURE","Employment in Agriculture (%)","% of total",1.0),
    "AG.LND.ARBL.ZS":      ("agriculture","ARABLE_LAND_PCT","Arable Land (% land area)","% of land",1.0),
    "SL.TLF.CACT.ZS":      ("labor","LABOR_FORCE_PARTICIPATION","Labor Force Participation (%)","% of pop",1.0),
    "SL.TLF.TOTL.IN":      ("labor","LABOR_FORCE_TOTAL","Total Labor Force (millions)","millions",1e6),
    "BN.CAB.XOKA.GD.ZS":   ("macro_economy","CURRENT_ACCOUNT_GDP","Current Account Balance (% GDP)","% of GDP",1.0),
    "GC.BAL.CASH.GD.ZS":   ("fiscal","FISCAL_BALANCE_GDP","Fiscal Balance (% GDP)","% of GDP",1.0),
    "NY.GDP.PCAP.PP.CD":   ("macro_economy","GDP_PPP_PER_CAPITA","GDP Per Capita PPP (Int$)","Int$",1.0),
}

MAX_RETRIES = 3

def _fetch_wb(wb_code, start=2015, end=2026):
    per_page=max(1000,len(WB2_ISO3)*(end-start+3))
    url=f"{WB_BASE}/country/{WB_CODES}/indicator/{wb_code}?format=json&per_page={per_page}&date={start}:{end}"
    for i in range(MAX_RETRIES):
        try:
            r=_get(url,timeout=30)
            if r.status_code==200:
                d=r.json(); return d[1] if isinstance(d,list) and len(d)>=2 else []
        except Exception:
            if i<MAX_RETRIES-1: time.sleep(2**i)
    return []

def main():
    print(f"\n{'═'*60}\n  Environment, Agriculture & Social — {today_str}\n{'═'*60}\n")
    all_rows=[]; errors=[]
    for wb_code,(sector,ind_code,ind_name,unit,div) in ENV_SOCIAL_INDICATORS.items():
        print(f"  ▸ {wb_code}: {ind_name[:40]}", flush=True)
        raw=_fetch_wb(wb_code)
        if not raw:
            errors.append(f"{wb_code}: failed"); print(f"    ✗ Failed", flush=True); continue
        idx={}
        for item in raw:
            c=item.get("countryiso3code",""); y=item.get("date",""); v=item.get("value")
            if c and y: idx[(c,int(y))]=v
        cnt=0
        for wb2,iso3 in WB2_ISO3.items():
            for yr in range(2015,2027):
                vr=idx.get((iso3,yr)) or idx.get((wb2,yr))
                try: val=round(float(vr)/div,3) if vr is not None else None
                except: val=None
                all_rows.append({"country_code":iso3,"sector":sector,"indicator_code":ind_code,"indicator_name":ind_name,"period":str(yr),"year":yr,"quarter":None,"month":None,"value":val,"unit":unit,"frequency":"annual","source":"World Bank Open Data API","source_type":"multilateral","source_url":f"https://api.worldbank.org/v2/country/all/indicator/{wb_code}","fetched_at":ts_now(),"released_at":None,"value_type":"official_actual" if val is not None else "missing_official","data_quality":"available" if val is not None else "missing","confidence":"high" if val is not None else "none","extraction_method":"api","limitation_note":""})
                if val is not None: cnt+=1
        print(f"    ✓ {cnt} values", flush=True)
        time.sleep(0.7)
    out_file=PROC_DIR/"environment_normalized.json"
    result={"source":"Environment, Agriculture & Social (World Bank)","source_id":"ENV_AGRI_SOCIAL","fetched_at":ts_now(),"total_rows":len(all_rows),"non_null":sum(1 for r in all_rows if r["value"] is not None),"errors":errors,"records":all_rows}
    out_file.write_text(json.dumps(result,indent=2))
    print(f"\n  ✓ Rows: {len(all_rows)} | Non-null: {result['non_null']}\n  📄 {out_file.relative_to(PROJECT_ROOT)}\n")
    return 0

if __name__=="__main__": sys.exit(main())
