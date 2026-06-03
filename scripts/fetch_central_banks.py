#!/usr/bin/env python3
"""
scripts/fetch_central_banks.py
────────────────────────────────────────────────────────────────────────────
Fetches monetary policy rates, exchange rates, foreign reserves, and
monetary aggregates from SEA central banks.

BANKS COVERED:
  MAS Singapore      — open API, excellent coverage
  BNM Malaysia       — open API (bnm.gov.my/public)
  BOT Thailand       — API (key required for full; public endpoints exist)
  BSP Philippines    — HTML/JSON tables
  Bank Indonesia     — HTML scraping
  SBV Vietnam        — limited HTML
  NBC Cambodia       — quarterly bulletins
  AMBD Brunei        — limited

OUTPUT
  pipeline/data/raw/central_banks/{iso3}_{YYYYMMDD}.json
  pipeline/data/processed/central_banks_normalized.json

USAGE
  python scripts/fetch_central_banks.py
  python scripts/fetch_central_banks.py --bank MYS
"""

import json
import sys
import time
import argparse
import re
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

try:
    from bs4 import BeautifulSoup
    BS4 = True
except ImportError:
    BS4 = False

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PIPELINE     = PROJECT_ROOT / "pipeline"
RAW_DIR      = PIPELINE / "data" / "raw" / "central_banks"
PROC_DIR     = PIPELINE / "data" / "processed"
RAW_DIR.mkdir(parents=True, exist_ok=True)

ts_now    = lambda: datetime.utcnow().isoformat() + "Z"
today_str = date.today().strftime("%Y%m%d")
today_iso = date.today().isoformat()

MAX_RETRIES   = 3
REQUEST_DELAY = 1.0


def _safe_float(v) -> float | None:
    if v is None:
        return None
    try:
        return float(str(v).replace(",", "").replace("%", "").strip())
    except (ValueError, TypeError):
        return None


def _row(iso3, sector, code, name, yr, qtr, mo, val, unit, freq, source, url, vtype="official_actual", method="api", note=""):
    period = str(yr)
    if qtr:
        period = f"{yr}Q{qtr}"
    elif mo:
        period = f"{yr}-{mo:02d}"
    return {
        "country_code": iso3, "sector": sector,
        "indicator_code": code, "indicator_name": name,
        "period": period, "year": yr, "quarter": qtr, "month": mo,
        "value": val, "unit": unit, "frequency": freq,
        "source": source, "source_type": "central_bank",
        "source_url": url, "fetched_at": ts_now(),
        "released_at": today_iso,
        "value_type": vtype, "data_quality": "available" if val is not None else "missing",
        "confidence": "very_high" if val is not None else "none",
        "extraction_method": method, "limitation_note": note,
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  SINGAPORE — MAS Open API
# ═══════════════════════════════════════════════════════════════════════════════

def fetch_mas_singapore() -> list[dict]:
    """Fetch Singapore monetary data from MAS open API."""
    rows = []
    base = "https://eservices.mas.gov.sg/api/action/datastore/search.json"
    ua   = {"User-Agent": "SEA-Dashboard/2.0"}

    print("    [SGP] MAS: Exchange rates...", flush=True)
    # SGD/USD exchange rate
    try:
        params = {"resource_id": "5f2b18a8-0883-4769-a635-879c63d3caac",
                  "limit": 200, "filters": json.dumps({"end_of_month": "1"})}
        r = _get(base, headers=ua, params=params, timeout=20)
        if r.status_code == 200:
            records = r.json().get("result", {}).get("records", [])
            for rec in records:
                try:
                    dt = str(rec.get("end_of_month", rec.get("date", "")))
                    yr = int(dt[:4])
                    mo = int(dt[5:7]) if len(dt) >= 7 else None
                    # SGD per USD
                    val = _safe_float(rec.get("usd_sgd", rec.get("USD")))
                    if yr >= 2019 and val is not None:
                        rows.append(_row(
                            "SGP", "finance_monetary", "EXCHANGE_RATE_USD",
                            "SGD per USD", yr, None, mo, val,
                            "SGD per USD", "monthly",
                            "Monetary Authority of Singapore", base
                        ))
                except Exception:
                    continue
    except Exception as e:
        print(f"      ⚠ MAS exchange rate: {e}", flush=True)

    # MAS policy rate (Interbank overnight rate as proxy)
    print("    [SGP] MAS: Interest rates...", flush=True)
    try:
        params = {"resource_id": "9a0bf149-308c-4bd2-832d-76c8e6cb47ed", "limit": 200}
        r = _get(base, headers=ua, params=params, timeout=20)
        if r.status_code == 200:
            for rec in r.json().get("result", {}).get("records", []):
                try:
                    dt = str(rec.get("end_of_month", ""))
                    yr = int(dt[:4])
                    mo = int(dt[5:7]) if len(dt) >= 7 else None
                    val = _safe_float(rec.get("sora") or rec.get("comp_sora_1m") or rec.get("sor_overnight"))
                    if yr >= 2019 and val is not None:
                        rows.append(_row(
                            "SGP", "finance_monetary", "POLICY_INTEREST_RATE",
                            "SORA / Interbank Rate", yr, None, mo, val,
                            "%", "monthly", "MAS Singapore", base
                        ))
                except Exception:
                    continue
    except Exception as e:
        print(f"      ⚠ MAS interest rate: {e}", flush=True)

    print(f"    [SGP] MAS: {len(rows)} rows", flush=True)
    return rows


# ═══════════════════════════════════════════════════════════════════════════════
#  MALAYSIA — BNM Open API
# ═══════════════════════════════════════════════════════════════════════════════

def fetch_bnm_malaysia() -> list[dict]:
    """Fetch Malaysia monetary data from BNM public API."""
    rows = []
    base = "https://api.bnm.gov.my/public"
    ua   = {"User-Agent": "SEA-Dashboard/2.0", "Accept": "application/vnd.BNM.API.v1+json"}

    # Policy rate (OPR)
    print("    [MYS] BNM: OPR (policy rate)...", flush=True)
    try:
        r = _get(f"{base}/opr", headers=ua, timeout=20)
        if r.status_code == 200:
            data = r.json().get("data", {})
            # BNM OPR endpoint returns latest rate
            val = _safe_float(data.get("rate") or data.get("opr_rate"))
            if val is not None:
                rows.append(_row(
                    "MYS", "finance_monetary", "POLICY_INTEREST_RATE",
                    "Overnight Policy Rate (OPR)", date.today().year, None,
                    date.today().month, val, "%", "monthly",
                    "Bank Negara Malaysia", f"{base}/opr"
                ))
    except Exception as e:
        print(f"      ⚠ BNM OPR: {e}", flush=True)

    # Exchange rate MYR/USD
    print("    [MYS] BNM: Exchange rates...", flush=True)
    try:
        r = _get(f"{base}/exchange-rate", headers=ua, timeout=20)
        if r.status_code == 200:
            data = r.json().get("data", [])
            if isinstance(data, list):
                for item in data:
                    if str(item.get("currency_code", "")).upper() == "USD":
                        val = _safe_float(item.get("rate") or item.get("selling"))
                        if val is not None:
                            rows.append(_row(
                                "MYS", "finance_monetary", "EXCHANGE_RATE_USD",
                                "MYR per USD", date.today().year, None,
                                date.today().month, val, "MYR per USD", "daily",
                                "Bank Negara Malaysia", f"{base}/exchange-rate"
                            ))
                        break
    except Exception as e:
        print(f"      ⚠ BNM exchange rate: {e}", flush=True)

    # Foreign reserves
    print("    [MYS] BNM: Foreign reserves...", flush=True)
    try:
        r = _get(f"{base}/reserves", headers=ua, timeout=20)
        if r.status_code == 200:
            data = r.json().get("data", {})
            val = _safe_float(data.get("total_reserves"))
            if val is not None:
                # BNM reports in USD billion
                rows.append(_row(
                    "MYS", "finance_monetary", "FOREIGN_RESERVES",
                    "Foreign Reserves (USD Billion)", date.today().year, None,
                    date.today().month, val, "USD billion", "biweekly",
                    "Bank Negara Malaysia", f"{base}/reserves"
                ))
    except Exception as e:
        print(f"      ⚠ BNM reserves: {e}", flush=True)

    print(f"    [MYS] BNM: {len(rows)} rows", flush=True)
    return rows


# ═══════════════════════════════════════════════════════════════════════════════
#  THAILAND — BOT (public scraping endpoint)
# ═══════════════════════════════════════════════════════════════════════════════

def fetch_bot_thailand() -> list[dict]:
    """Fetch Thailand central bank data from BOT."""
    rows = []
    ua   = {"User-Agent": "Mozilla/5.0 SEA-Dashboard/2.0"}

    print("    [THA] BOT: Policy rate...", flush=True)
    # BOT API for policy rate (public endpoint)
    bot_url = "https://www.bot.or.th/en/monetary-policy/monetary-policy-committee/mpc-decisions.html"
    try:
        r = _get(bot_url, headers=ua, timeout=25)
        if r.status_code == 200 and BS4:
            soup = BeautifulSoup(r.text, "html.parser")
            # Look for rate table
            for tbl in soup.find_all("table")[:5]:
                for tr in tbl.find_all("tr")[1:5]:
                    tds = tr.find_all(["td", "th"])
                    if len(tds) >= 2:
                        rate_text = tds[-1].get_text(strip=True)
                        val = _safe_float(rate_text.replace("per cent", "").strip())
                        if val is not None and 0 < val < 20:
                            rows.append(_row(
                                "THA", "finance_monetary", "POLICY_INTEREST_RATE",
                                "BOT Policy Rate", date.today().year, None, None,
                                val, "%", "quarterly",
                                "Bank of Thailand", bot_url,
                                method="scrape"
                            ))
                            break
    except Exception as e:
        print(f"      ⚠ BOT policy rate: {e}", flush=True)

    print(f"    [THA] BOT: {len(rows)} rows", flush=True)
    return rows


# ═══════════════════════════════════════════════════════════════════════════════
#  PHILIPPINES — BSP
# ═══════════════════════════════════════════════════════════════════════════════

def fetch_bsp_philippines() -> list[dict]:
    """Fetch Philippines central bank data."""
    rows = []
    ua   = {"User-Agent": "Mozilla/5.0 SEA-Dashboard/2.0"}

    print("    [PHL] BSP: Policy rate...", flush=True)
    # BSP policy rate JSON endpoint
    bsp_url = "https://www.bsp.gov.ph/Statistics/Monetary_Sector/statistics_keyrates.aspx"
    try:
        r = _get("https://www.bsp.gov.ph/statistics/keyrates.aspx", headers=ua, timeout=20)
        if r.status_code == 200 and BS4:
            soup = BeautifulSoup(r.text, "html.parser")
            for tbl in soup.find_all("table")[:3]:
                tds = tbl.find_all("td")
                for i, td in enumerate(tds):
                    if "overnight" in td.get_text(strip=True).lower() or "rp" in td.get_text(strip=True).lower():
                        if i + 1 < len(tds):
                            val = _safe_float(tds[i+1].get_text(strip=True))
                            if val is not None and 0 < val < 30:
                                rows.append(_row(
                                    "PHL", "finance_monetary", "POLICY_INTEREST_RATE",
                                    "BSP Overnight Rate", date.today().year, None,
                                    date.today().month, val, "%", "monthly",
                                    "Bangko Sentral ng Pilipinas", bsp_url,
                                    method="scrape"
                                ))
                                break
    except Exception as e:
        print(f"      ⚠ BSP rate: {e}", flush=True)

    print(f"    [PHL] BSP: {len(rows)} rows", flush=True)
    return rows


# ═══════════════════════════════════════════════════════════════════════════════
#  ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════════════════════

BANK_FETCHERS = {
    "SGP": fetch_mas_singapore,
    "MYS": fetch_bnm_malaysia,
    "THA": fetch_bot_thailand,
    "PHL": fetch_bsp_philippines,
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bank", default="all",
                        choices=["all"] + list(BANK_FETCHERS.keys()))
    args = parser.parse_args()

    print(f"\n{'═'*60}")
    print(f"  Central Bank Fetcher — {today_str}")
    print(f"{'═'*60}\n")

    banks = (list(BANK_FETCHERS.items()) if args.bank == "all"
             else [(args.bank, BANK_FETCHERS.get(args.bank))])

    all_rows = []
    errors   = []

    for iso3, fn in banks:
        if fn is None:
            continue
        print(f"\n  ── {iso3} ──", flush=True)
        try:
            rows = fn()
            all_rows.extend(rows)
            raw_f = RAW_DIR / f"{iso3}_{today_str}.json"
            raw_f.write_text(json.dumps({"rows": rows}, indent=2))
        except Exception as e:
            errors.append(f"{iso3}: {e}")
            print(f"  ✗ {iso3}: {e}", flush=True)
        time.sleep(REQUEST_DELAY)

    out_file = PROC_DIR / "central_banks_normalized.json"
    result = {
        "source": "Central Banks (Multi-country)",
        "source_id": "CB_NATIONAL",
        "fetched_at": datetime.utcnow().isoformat() + "Z",
        "total_rows": len(all_rows),
        "non_null": sum(1 for r in all_rows if r["value"] is not None),
        "errors": errors,
        "records": all_rows,
    }
    out_file.write_text(json.dumps(result, indent=2))

    print(f"\n  ✓ Total rows : {len(all_rows)}")
    if errors:
        print(f"  ⚠ Errors    : {len(errors)}")
    print(f"  📄 Output: {out_file.relative_to(PROJECT_ROOT)}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
