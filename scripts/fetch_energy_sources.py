#!/usr/bin/env python3
"""
scripts/fetch_energy_sources.py
────────────────────────────────────────────────────────────────────────────
Fetches energy indicators from World Bank API (free, no key):
  - Renewable energy share (EG.FEC.RNEW.ZS)
  - Electricity access (EG.ELC.ACCS.ZS)
  - CO2 per capita (EN.ATM.CO2E.PC)
  - Energy intensity (EG.EGY.PRIM.PP.KD)
  - CO2 total (EN.ATM.CO2E.KT)

IEA API (requires key — loads from .env ENERGY_IEA_KEY if present).

OUTPUT
  pipeline/data/processed/energy_normalized.json
"""

import json, sys, time, os
from pathlib import Path
from datetime import datetime, date

try:
    from dotenv import load_dotenv; load_dotenv()
except ImportError: pass

try:
    import httpx
    def _get(url, timeout=30, headers=None):
        with httpx.Client(timeout=timeout, follow_redirects=True) as c:
            return c.get(url, headers=headers or {})
except ImportError:
    import urllib.request
    class _R:
        def __init__(self, d, c): self.status_code=c; self.text=d.decode() if isinstance(d,bytes) else str(d)
        def json(self): return json.loads(self.text)
    def _get(url, timeout=30, headers=None):
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

ENERGY_INDICATORS = {
    "EG.FEC.RNEW.ZS":   ("energy",      "RENEWABLE_ENERGY_SHARE", "Renewable Energy Share",           "%",             1.0),
    "EG.ELC.ACCS.ZS":   ("energy",      "ELECTRICITY_ACCESS",      "Access to Electricity (%)",        "%",             1.0),
    "EN.ATM.CO2E.PC":   ("environment", "CO2_PER_CAPITA",           "CO2 Emissions Per Capita",         "tonnes CO2",    1.0),
    "EN.ATM.CO2E.KT":   ("environment", "CO2_TOTAL",                "Total CO2 Emissions (kt)",         "kt CO2",        1.0),
    "EG.EGY.PRIM.PP.KD":("energy",      "ENERGY_INTENSITY",         "Energy Intensity",                 "MJ/$GDP PPP",   1.0),
    "AG.LND.FRST.ZS":   ("environment", "FOREST_AREA_PCT",          "Forest Area (% land)",             "%",             1.0),
    "AG.LND.TOTL.K2":   ("environment", "LAND_AREA",                "Land Area (sq km)",                "sq km",         1.0),
}

MAX_RETRIES = 3


def _fetch_wb(wb_code, start=2019, end=2026):
    per_page = max(1000, len(WB2_ISO3) * (end - start + 2))
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
    print(f"\n{'═'*60}\n  Energy & Environment Sources — {today_str}\n{'═'*60}\n")

    all_rows = []
    errors   = []

    for wb_code, (sector, ind_code, ind_name, unit, mult) in ENERGY_INDICATORS.items():
        print(f"  ▸ {wb_code}: {ind_name[:45]}...", flush=True)
        raw = _fetch_wb(wb_code)
        if not raw:
            errors.append(f"{wb_code}: fetch failed")
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
            for year in range(2019, 2027):
                v_raw = idx.get((iso3, year)) or idx.get((wb2, year))
                try:
                    val = round(float(v_raw) * mult, 3) if v_raw is not None else None
                except (TypeError, ValueError):
                    val = None
                all_rows.append({
                    "country_code": iso3, "sector": sector,
                    "indicator_code": ind_code, "indicator_name": ind_name,
                    "period": str(year), "year": year, "quarter": None, "month": None,
                    "value": val, "unit": unit, "frequency": "annual",
                    "source": "World Bank Open Data API (Energy/Environment)",
                    "source_type": "multilateral",
                    "source_url": src_url, "fetched_at": ts_now(), "released_at": None,
                    "value_type": "official_actual" if val is not None else "missing_official",
                    "data_quality": "available" if val is not None else "missing",
                    "confidence": "high" if val is not None else "none",
                    "extraction_method": "api", "limitation_note": "",
                })
                if val is not None: cnt += 1

        print(f"    ✓ {cnt} values", flush=True)
        time.sleep(0.8)

    out_file = PROC_DIR / "energy_normalized.json"
    result = {
        "source": "Energy & Environment (World Bank)", "source_id": "ENERGY_ENV",
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
