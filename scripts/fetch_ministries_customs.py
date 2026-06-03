#!/usr/bin/env python3
"""
scripts/fetch_ministries_customs.py
────────────────────────────────────────────────────────────────────────────
Fetches trade and economic data from official ministry/customs portals.

SOURCES:
  - Malaysia DOSM OpenDOSM API (trade statistics)
  - Singapore SingStat (merchandise trade)
  - Thailand Customs Department (trade stats)
  - Philippines BOC / PSA trade data
  - Indonesia MOT / BPS trade data

Falls back gracefully — one country failure does not stop others.

OUTPUT  pipeline/data/processed/ministries_normalized.json
"""

import json, sys, time, re
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

try:
    from bs4 import BeautifulSoup; BS4=True
except ImportError:
    BS4=False

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PIPELINE     = PROJECT_ROOT / "pipeline"
PROC_DIR     = PIPELINE / "data" / "processed"

ts_now    = lambda: datetime.utcnow().isoformat() + "Z"
today_str = date.today().strftime("%Y%m%d")


def _row(iso3, sector, code, name, yr, mo, val, unit, freq, src, url, method="api", note=""):
    period = f"{yr}-{mo:02d}" if mo else str(yr)
    return {
        "country_code": iso3, "sector": sector,
        "indicator_code": code, "indicator_name": name,
        "period": period, "year": yr, "quarter": None, "month": mo,
        "value": val, "unit": unit, "frequency": freq,
        "source": src, "source_type": "ministry_customs",
        "source_url": url, "fetched_at": ts_now(), "released_at": None,
        "value_type": "official_actual" if val is not None else "missing_official",
        "data_quality": "available" if val is not None else "missing",
        "confidence": "very_high" if val is not None else "none",
        "extraction_method": method, "limitation_note": note,
    }


def _safe_float(v):
    if v is None: return None
    try: return float(str(v).replace(",","").replace("%","").strip())
    except: return None


# ── Malaysia DOSM OpenDOSM: external trade ──────────────────────────────────

def fetch_malaysia_trade() -> list[dict]:
    rows = []
    base = "https://open.dosm.gov.my/api"
    ua   = {"User-Agent": "SEA-Dashboard/2.0", "Accept": "application/json"}
    print("    [MYS] DOSM: external trade...", flush=True)
    endpoints = [
        (f"{base}/data-catalogue?id=trade_monthly&lang=en", "monthly"),
        (f"{base}/data-catalogue?id=external_trade&lang=en", "monthly"),
    ]
    for ep, freq in endpoints:
        try:
            r = _get(ep, headers=ua, timeout=20)
            if r.status_code != 200: continue
            for item in r.json().get("data", []):
                try:
                    dt = str(item.get("date", item.get("period", "")))
                    yr = int(dt[:4])
                    mo_raw = dt[5:7] if len(dt) >= 7 else None
                    mo = int(mo_raw) if mo_raw and mo_raw.isdigit() else None
                    if yr < 2019: continue
                    x = _safe_float(item.get("exports", item.get("x")))
                    m = _safe_float(item.get("imports", item.get("m")))
                    if x is not None:
                        rows.append(_row("MYS","trade","EXPORTS_USD","Exports (MYR Billion)",yr,mo,x,"MYR billion",freq,"DOSM Malaysia",ep))
                    if m is not None:
                        rows.append(_row("MYS","trade","IMPORTS_USD","Imports (MYR Billion)",yr,mo,m,"MYR billion",freq,"DOSM Malaysia",ep))
                except Exception: continue
            if rows: break
        except Exception as e:
            print(f"      ⚠ DOSM trade: {e}", flush=True)
        time.sleep(0.5)
    print(f"    [MYS] DOSM trade: {len(rows)} rows", flush=True)
    return rows


# ── Singapore SingStat: merchandise trade ───────────────────────────────────

def fetch_singapore_trade() -> list[dict]:
    rows = []
    base = "https://tablebuilder.singstat.gov.sg/api/table/tabledata"
    ua   = {"User-Agent": "SEA-Dashboard/2.0"}
    trade_tables = ["M480501", "M480081", "14N"]  # Try several known IDs
    print("    [SGP] SingStat: merchandise trade...", flush=True)
    for tid in trade_tables:
        try:
            r = _get(f"{base}/{tid}", headers=ua, timeout=20)
            if r.status_code != 200: continue
            data = r.json()
            rows_raw = data.get("Data", {}).get("row", [])
            for row_obj in (rows_raw if isinstance(rows_raw, list) else [])[:100]:
                row_text = str(row_obj.get("rowText", ""))
                yr_m = re.match(r"(\d{4})\s*(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|\d+)?", row_text, re.I)
                if not yr_m: continue
                yr = int(yr_m.group(1))
                if yr < 2019: continue
                for col in row_obj.get("columns", [])[:4]:
                    val = _safe_float(col.get("value"))
                    if val is not None and val > 0:
                        key = col.get("key", "").lower()
                        ind_code = "EXPORTS_USD" if "export" in key or "x" == key else "IMPORTS_USD"
                        rows.append(_row("SGP","trade",ind_code,
                            f"{'Exports' if 'export' in ind_code else 'Imports'} (SGD Million)",
                            yr,None,val,"SGD million","monthly","SingStat Singapore",
                            f"https://tablebuilder.singstat.gov.sg/table/TS/{tid}"))
            if rows: break
        except Exception as e:
            print(f"      ⚠ SingStat trade {tid}: {e}", flush=True)
        time.sleep(0.5)
    print(f"    [SGP] SingStat trade: {len(rows)} rows", flush=True)
    return rows


COUNTRY_FETCHERS = {
    "MYS": fetch_malaysia_trade,
    "SGP": fetch_singapore_trade,
}


def main():
    print(f"\n{'═'*60}\n  Ministries & Customs Fetcher — {today_str}\n{'═'*60}\n")
    all_rows = []
    errors   = []

    for iso3, fn in COUNTRY_FETCHERS.items():
        print(f"\n  ── {iso3} ──", flush=True)
        try:
            rows = fn()
            all_rows.extend(rows)
        except Exception as e:
            errors.append(f"{iso3}: {e}")
            print(f"  ✗ {iso3}: {e}", flush=True)
        time.sleep(1.0)

    out_file = PROC_DIR / "ministries_normalized.json"
    result = {
        "source": "Ministries & Customs (Multi-country)", "source_id": "MIN_CUSTOMS",
        "fetched_at": datetime.utcnow().isoformat() + "Z",
        "total_rows": len(all_rows),
        "non_null": sum(1 for r in all_rows if r["value"] is not None),
        "errors": errors, "records": all_rows,
    }
    out_file.write_text(json.dumps(result, indent=2))
    print(f"\n  ✓ Rows: {len(all_rows)}")
    print(f"  📄 {out_file.relative_to(PROJECT_ROOT)}\n")
    return 0

if __name__ == "__main__":
    sys.exit(main())
