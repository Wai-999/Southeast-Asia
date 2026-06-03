#!/usr/bin/env python3
"""
scripts/fetch_infrastructure_projects.py
────────────────────────────────────────────────────────────────────────────
Fetches active infrastructure projects from World Bank and ADB APIs.

Collects:
  - Active WB project count and commitment value per country
  - Active ADB project count per country
  - Logistics Performance Index (from WB API)

OUTPUT  pipeline/data/processed/infrastructure_normalized.json
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
curr_year = date.today().year

ISO3_TO_WBNAME = {
    "THA":"Thailand","VNM":"Vietnam","MMR":"Myanmar","KHM":"Cambodia","LAO":"Lao PDR",
    "MYS":"Malaysia","SGP":"Singapore","IDN":"Indonesia","PHL":"Philippines",
    "BRN":"Brunei","TLS":"Timor-Leste","CHN":"China","IND":"India","KOR":"Korea","AUS":"Australia",
}

MAX_RETRIES = 3


def _fetch_wb_projects(country_name: str) -> dict:
    """Fetch active World Bank projects for a country."""
    url = "https://search.worldbank.org/api/v2/projects"
    params = {
        "format": "json",
        "countryshortname": country_name,
        "status": "Active",
        "rows": 100, "os": 0,
    }
    for i in range(MAX_RETRIES):
        try:
            r = _get(url, params=params, timeout=25)
            if r.status_code == 200:
                data = r.json()
                projects = data.get("projects", [])
                total_commitment = sum(
                    float(p.get("lendprojectcost") or p.get("curr_total_commitment") or 0)
                    for p in projects
                    if isinstance(p, dict)
                )
                return {
                    "count": len(projects),
                    "total_commitment_usd": total_commitment,
                }
        except Exception as e:
            if i < MAX_RETRIES - 1: time.sleep(2**i)
    return {"count": None, "total_commitment_usd": None}


def _fetch_adb_projects(iso3: str) -> dict:
    """Fetch active ADB projects for a country via ADB API."""
    url = "https://www.adb.org/api/projects/all.json"
    for i in range(MAX_RETRIES):
        try:
            r = _get(url, timeout=30)
            if r.status_code == 200:
                data = r.json()
                projects = data if isinstance(data, list) else data.get("data", data.get("projects", []))
                country_active = [
                    p for p in projects
                    if isinstance(p, dict)
                    and str(p.get("country_iso", "")).upper() == iso3.upper()
                    and str(p.get("status", "")).lower() in ("active", "implementation")
                ]
                return {"count": len(country_active)}
        except Exception as e:
            if i < MAX_RETRIES - 1: time.sleep(2**i)
    return {"count": None}


def _wb_lpi(iso3: str) -> float | None:
    """Fetch Logistics Performance Index from World Bank."""
    url = f"https://api.worldbank.org/v2/country/{iso3}/indicator/LP.LPI.OVRL.XQ?format=json&mrv=1"
    try:
        r = _get(url, timeout=20)
        if r.status_code == 200:
            d = r.json()
            records = d[1] if isinstance(d, list) and len(d) >= 2 else []
            for rec in records:
                v = rec.get("value")
                if v is not None:
                    return round(float(v), 2)
    except Exception:
        pass
    return None


def main():
    print(f"\n{'═'*60}\n  Infrastructure Projects Fetcher — {today_str}\n{'═'*60}\n")

    all_rows = []
    errors   = []

    for iso3, country_name in ISO3_TO_WBNAME.items():
        print(f"  ── {iso3} {country_name[:20]}", flush=True)

        # WB projects
        print(f"    [WB Projects]", end=" ", flush=True)
        try:
            wb = _fetch_wb_projects(country_name)
            if wb["count"] is not None:
                all_rows.append({
                    "country_code": iso3, "sector": "infrastructure",
                    "indicator_code": "ACTIVE_WB_PROJECTS", "indicator_name": "Active World Bank Projects",
                    "period": str(curr_year), "year": curr_year, "quarter": None, "month": None,
                    "value": float(wb["count"]), "unit": "count", "frequency": "annual",
                    "source": "World Bank Projects API", "source_type": "multilateral",
                    "source_url": "https://search.worldbank.org/api/v2/projects",
                    "fetched_at": ts_now(), "released_at": None,
                    "value_type": "official_actual", "data_quality": "available",
                    "confidence": "high", "extraction_method": "api", "limitation_note": "",
                })
                commit_b = round(wb["total_commitment_usd"] / 1e6, 1) if wb["total_commitment_usd"] else None
                if commit_b is not None:
                    all_rows.append({
                        "country_code": iso3, "sector": "infrastructure",
                        "indicator_code": "ACTIVE_WB_COMMITMENT",
                        "indicator_name": "WB Project Commitment (USD Million)",
                        "period": str(curr_year), "year": curr_year, "quarter": None, "month": None,
                        "value": commit_b, "unit": "USD million", "frequency": "annual",
                        "source": "World Bank Projects API", "source_type": "multilateral",
                        "source_url": "https://search.worldbank.org/api/v2/projects",
                        "fetched_at": ts_now(), "released_at": None,
                        "value_type": "official_actual", "data_quality": "available",
                        "confidence": "high", "extraction_method": "api", "limitation_note": "",
                    })
                print(f"{wb['count']} projects", flush=True)
            else:
                print("no data", flush=True)
        except Exception as e:
            errors.append(f"{iso3} WB: {e}")
            print(f"FAILED: {e}", flush=True)
        time.sleep(1.0)

        # LPI
        lpi = _wb_lpi(iso3)
        if lpi is not None:
            all_rows.append({
                "country_code": iso3, "sector": "infrastructure",
                "indicator_code": "LOGISTICS_PERFORMANCE",
                "indicator_name": "Logistics Performance Index",
                "period": "2023", "year": 2023, "quarter": None, "month": None,
                "value": lpi, "unit": "Score 1-5", "frequency": "biennial",
                "source": "World Bank LPI", "source_type": "multilateral",
                "source_url": "https://lpi.worldbank.org",
                "fetched_at": ts_now(), "released_at": None,
                "value_type": "official_actual", "data_quality": "available",
                "confidence": "high", "extraction_method": "api", "limitation_note": "LPI published every 2 years",
            })
        time.sleep(0.5)

    out_file = PROC_DIR / "infrastructure_normalized.json"
    result = {
        "source": "Infrastructure Projects (WB + ADB)",
        "source_id": "INFRASTRUCTURE",
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
