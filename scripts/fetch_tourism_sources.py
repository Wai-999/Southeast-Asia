#!/usr/bin/env python3
"""
scripts/fetch_tourism_sources.py
────────────────────────────────────────────────────────────────────────────
Fetches tourist arrivals and tourism receipts from:
  1. World Bank API (annual, no key)
  2. UNWTO (scraping)
  3. National tourism offices where accessible

OUTPUT
  pipeline/data/raw/tourism/tourism_{YYYYMMDD}.json
  pipeline/data/processed/tourism_normalized.json
"""

import json, sys, time
from pathlib import Path
from datetime import datetime, date

try:
    import httpx
    def _get(url, timeout=30, headers=None):
        with httpx.Client(timeout=timeout, follow_redirects=True) as c:
            return c.get(url, headers=headers or {})
except ImportError:
    import urllib.request
    class _R:
        def __init__(self, d, c): self._d=d; self.status_code=c; self.text=d.decode() if isinstance(d,bytes) else str(d)
        def json(self): return json.loads(self.text)
    def _get(url, timeout=30, headers=None):
        req=urllib.request.Request(url, headers=headers or {"User-Agent":"SEA-Dashboard/2.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r: return _R(r.read(), r.status)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PIPELINE     = PROJECT_ROOT / "pipeline"
RAW_DIR      = PIPELINE / "data" / "raw" / "tourism"
PROC_DIR     = PIPELINE / "data" / "processed"
RAW_DIR.mkdir(parents=True, exist_ok=True)

ts_now    = lambda: datetime.utcnow().isoformat() + "Z"
today_str = date.today().strftime("%Y%m%d")

WB_BASE = "https://api.worldbank.org/v2"
WB_CODES = "TH;VN;MM;KH;LA;MY;SG;ID;PH;BN;TP;CN;US;JP;IN;KR;AU"
WB2_ISO3 = {
    "TH":"THA","VN":"VNM","MM":"MMR","KH":"KHM","LA":"LAO",
    "MY":"MYS","SG":"SGP","ID":"IDN","PH":"PHL","BN":"BRN",
    "TP":"TLS","CN":"CHN","US":"USA","JP":"JPN","IN":"IND","KR":"KOR","AU":"AUS",
}

WB_TOURISM_INDICATORS = {
    "ST.INT.ARVL":   ("TOURIST_ARRIVALS",     "International Tourist Arrivals", "millions", 1e6),
    "ST.INT.RCPT.CD":("TOURISM_RECEIPTS_USD", "Tourism Receipts (USD Billion)",  "USD billion", 1e9),
}

MAX_RETRIES = 3


def _fetch_wb_indicator(wb_code: str, start=2019, end=2026) -> list:
    per_page = max(1000, len(WB2_ISO3) * (end - start + 2))
    url = f"{WB_BASE}/country/{WB_CODES}/indicator/{wb_code}?format=json&per_page={per_page}&date={start}:{end}"
    for i in range(MAX_RETRIES):
        try:
            r = _get(url, timeout=30)
            if r.status_code == 200:
                data = r.json()
                return data[1] if isinstance(data, list) and len(data) >= 2 else []
        except Exception as e:
            print(f"      ⚠ attempt {i+1}: {e}", flush=True)
            if i < MAX_RETRIES - 1: time.sleep(2**i)
    return []


def _build_row(iso3, ind_code, ind_name, year, val, unit, source_url):
    return {
        "country_code": iso3, "sector": "tourism",
        "indicator_code": ind_code, "indicator_name": ind_name,
        "period": str(year), "year": year, "quarter": None, "month": None,
        "value": val, "unit": unit, "frequency": "annual",
        "source": "World Bank Open Data API (Tourism)", "source_type": "multilateral",
        "source_url": source_url, "fetched_at": ts_now(), "released_at": None,
        "value_type": "official_actual" if val is not None else "missing_official",
        "data_quality": "available" if val is not None else "missing",
        "confidence": "high" if val is not None else "none",
        "extraction_method": "api", "limitation_note": "",
    }


def main():
    print(f"\n{'═'*60}\n  Tourism Sources Fetcher — {today_str}\n{'═'*60}\n")

    all_rows = []
    errors = []

    for wb_code, (ind_code, ind_name, unit, divisor) in WB_TOURISM_INDICATORS.items():
        print(f"  ▸ WB {wb_code}: {ind_name}...", flush=True)
        raw = _fetch_wb_indicator(wb_code)
        if not raw:
            errors.append(f"WB {wb_code}: no data")
            print(f"    ✗ Failed", flush=True)
            continue

        src_url = f"https://api.worldbank.org/v2/country/all/indicator/{wb_code}"
        raw_idx = {}
        for item in raw:
            try:
                c = item.get("countryiso3code") or ""
                y = int(item.get("date", 0))
                v = item.get("value")
                if c and y: raw_idx[(c, y)] = v
            except Exception: continue

        rows_added = 0
        for wb2, iso3 in WB2_ISO3.items():
            for year in range(2019, 2027):
                val_raw = raw_idx.get((iso3, year)) or raw_idx.get((wb2, year))
                try:
                    val = round(float(val_raw) / divisor, 3) if val_raw is not None else None
                except (TypeError, ValueError):
                    val = None
                all_rows.append(_build_row(iso3, ind_code, ind_name, year, val, unit, src_url))
                if val is not None: rows_added += 1

        print(f"    ✓ {rows_added} values", flush=True)
        time.sleep(0.8)

    raw_f = RAW_DIR / f"tourism_{today_str}.json"
    raw_f.write_text(json.dumps({"rows": all_rows}, indent=2))

    out_file = PROC_DIR / "tourism_normalized.json"
    result = {
        "source": "Tourism Data (World Bank + national)", "source_id": "TOURISM",
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
