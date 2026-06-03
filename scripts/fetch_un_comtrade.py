#!/usr/bin/env python3
"""
scripts/fetch_un_comtrade.py
────────────────────────────────────────────────────────────────────────────
Fetches trade flows: total exports/imports + bilateral partner breakdowns.

SOURCE STRATEGY
───────────────
COMTRADE_API_KEY in .env?
  YES  → UN Comtrade authenticated API (higher rate limit, multi-year batch)
  NO   → UN Comtrade public preview (no key, per-year queries, motCode=0 filter)
         + World Bank WDI for total trade and trade openness supplement

WHY TWO SOURCES?
  Comtrade preview (public/v1/preview/…) returns records grouped by mode-of-
  transport (motCode). Filter motCode=0 ("all transport modes") to get the true
  bilateral aggregate. Works reliably for bilateral partner queries.
  World Bank WDI is used for world-total exports/imports because the Comtrade
  preview for partnerCode=0 (World) returns partner2-level breakdowns that
  do not sum cleanly within the 500-record cap.

BILATERAL PARTNERS: CHN, USA, JPN, IND, KOR, AUS, EU

OUTPUTS
  pipeline/data/raw/comtrade/comtrade_{YYYYMMDD}.json
  pipeline/data/processed/comtrade_normalized.json
  pipeline/data/processed/trade_flows.json  (alias for dashboard)

USAGE
  python scripts/fetch_un_comtrade.py              # auto-detect key
  python scripts/fetch_un_comtrade.py --all-years  # 2019–2024
  python scripts/fetch_un_comtrade.py --reporter THA VNM MYS
  python scripts/fetch_un_comtrade.py --no-bilateral
"""

import json
import sys
import time
import argparse
import os
from pathlib import Path
from datetime import datetime, date
from collections import defaultdict

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    import httpx
    def _get(url, timeout=25, headers=None, params=None):
        with httpx.Client(timeout=timeout, follow_redirects=True) as c:
            # Pass params=None (not {}) so embedded query strings in url are preserved
            return c.get(url, headers=headers or {}, params=params)
except ImportError:
    import urllib.request, urllib.parse
    class _R:
        def __init__(self, data, code):
            self.status_code = code
            self.text = data.decode() if isinstance(data, bytes) else str(data)
        def json(self): return json.loads(self.text)
    def _get(url, timeout=25, headers=None, params=None):
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers=headers or {"User-Agent": "SEA-Dashboard/2.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return _R(r.read(), r.status)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR  = PROJECT_ROOT / "pipeline" / "data" / "raw" / "comtrade"
PROC_DIR = PROJECT_ROOT / "pipeline" / "data" / "processed"
RAW_DIR.mkdir(parents=True, exist_ok=True)

ts_now    = lambda: datetime.utcnow().isoformat() + "Z"
today_str = date.today().strftime("%Y%m%d")
CURR_YEAR = date.today().year

# ─── API-key detection ─────────────────────────────────────────────────────

COMTRADE_API_KEY = os.getenv("COMTRADE_API_KEY", "").strip()
COMTRADE_ENABLED = bool(COMTRADE_API_KEY)

# Log once (module-level so it shows before argparse output)
_KEY_MSG = (
    "  ✓ COMTRADE_API_KEY set — using authenticated UN Comtrade API." if COMTRADE_ENABLED else
    "  ℹ COMTRADE_API_KEY missing — skipping authenticated UN Comtrade.\n"
    "  ℹ Using fallback: Comtrade public preview (bilateral) + World Bank WDI (totals)."
)

# ─── Country & partner tables ──────────────────────────────────────────────

SEA_REPORTERS = {
    "THA": 764, "VNM": 704, "MMR": 104, "KHM": 116,
    "LAO": 418, "MYS": 458, "SGP": 702, "IDN": 360,
    "PHL": 608, "BRN":  96, "TLS": 626,
}
PARTNER_REPORTERS = {
    "CHN": 156, "USA": 842, "JPN": 392,
    "IND": 356, "KOR": 410, "AUS":  36,
}
ALL_REPORTERS = {**SEA_REPORTERS, **PARTNER_REPORTERS}

REPORTER_NAMES = {
    "THA": "Thailand",    "VNM": "Vietnam",     "MMR": "Myanmar",
    "KHM": "Cambodia",    "LAO": "Laos",         "MYS": "Malaysia",
    "SGP": "Singapore",   "IDN": "Indonesia",    "PHL": "Philippines",
    "BRN": "Brunei",      "TLS": "Timor-Leste",
    "CHN": "China",       "USA": "United States","JPN": "Japan",
    "IND": "India",       "KOR": "South Korea",  "AUS": "Australia",
}

PARTNERS = {
    "CHN": 156, "USA": 842, "JPN": 392, "IND": 356,
    "KOR": 410, "AUS":  36, "EU":  918,
}
PARTNER_NAMES = {
    "CHN": "China", "USA": "United States", "JPN": "Japan",
    "IND": "India", "KOR": "South Korea",   "AUS": "Australia",
    "EU":  "European Union",
}

WB_CODE_MAP = {k: k for k in ALL_REPORTERS}
WB_CODE_MAP["TLS"] = "TMP"
WB_ISO2_TO_ISO3 = {
    "TH": "THA", "VN": "VNM", "MM": "MMR", "KH": "KHM", "LA": "LAO",
    "MY": "MYS", "SG": "SGP", "ID": "IDN", "PH": "PHL", "BN": "BRN",
    "TP": "TLS", "TL": "TLS",
    "CN": "CHN", "US": "USA", "JP": "JPN", "IN": "IND",
    "KR": "KOR", "AU": "AUS",
}

CT_AUTH_BASE    = "https://comtradeapi.un.org/data/v1/get"
CT_PREVIEW_BASE = "https://comtradeapi.un.org/public/v1/preview"
WB_BASE         = "https://api.worldbank.org/v2"

START_YEAR  = 2019
MAX_RETRIES = 3


# ─── Row builder ──────────────────────────────────────────────────────────

def make_row(iso3: str, ind_code: str, ind_name: str, year: int,
             value, unit: str, source: str, source_url: str,
             source_type: str = "multilateral", note: str = "") -> dict:
    if value is None:
        vtype, quality, conf = "missing_official", "missing", "none"
    elif year >= CURR_YEAR:
        vtype, quality, conf = "official_partial_2026", "partial", "medium"
    else:
        vtype, quality, conf = "official_actual", "available", "high"
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
        "source_type":     source_type,
        "source_url":      source_url,
        "fetched_at":      ts_now(),
        "released_at":     None,
        "value_type":      vtype,
        "data_quality":    quality,
        "confidence":      conf,
        "extraction_method": "api",
        "limitation_note": note,
    }


# ─── Comtrade preview: bilateral fetcher ──────────────────────────────────

def _preview_bilateral_year(reporter_num: int, reporter_iso3: str,
                            partner_num: int, partner_iso3: str,
                            year: int) -> list[dict]:
    """
    Fetch one reporter × one partner × one year from the public preview endpoint.
    Uses motCode=0 (all transport modes) to extract the true bilateral aggregate.
    Returns at most 2 rows (X and M) per call.
    """
    url = (f"{CT_PREVIEW_BASE}/C/A/HS"
           f"?reporterCode={reporter_num}&partnerCode={partner_num}"
           f"&cmdCode=TOTAL&flowCode=X,M&period={year}")
    source = "UN Comtrade (public preview)"
    note   = ("UN Comtrade public preview, motCode=0 (all-mode aggregate). "
              "No API key — per-year, per-partner queries.")

    for attempt in range(MAX_RETRIES):
        try:
            r = _get(url, headers={"User-Agent": "SEA-Dashboard/2.0",
                                   "Accept": "application/json"})
            if r.status_code != 200:
                if r.status_code == 429:
                    time.sleep(30 * (attempt + 1))
                    continue
                return []

            recs = r.json().get("data", [])
            # Filter to all-modes aggregate (motCode == 0)
            mot0 = [x for x in recs if x.get("motCode") == 0]
            if not mot0:
                # Fallback: no motCode field → take max value per flow
                mot0 = recs

            # Best value per flow = max primaryValue among mot0 records
            best: dict[str, float] = {}
            for rec in mot0:
                flow = rec.get("flowCode", "")
                val  = rec.get("primaryValue")
                if flow and val is not None and val > 0:
                    if flow not in best or val > best[flow]:
                        best[flow] = val

            rows: list[dict] = []
            pname = PARTNER_NAMES.get(partner_iso3, partner_iso3)

            if not best:
                # No data from preview — emit missing_official for both directions
                missing_note = ("UN Comtrade public preview returned 0 records for this "
                                "bilateral pair. Requires authenticated API key.")
                for ind_code, ind_name in [
                    (f"EXPORTS_TO_{partner_iso3}",   f"Exports to {pname} (USD Billion)"),
                    (f"IMPORTS_FROM_{partner_iso3}", f"Imports from {pname} (USD Billion)"),
                ]:
                    r = make_row(reporter_iso3, ind_code, ind_name, year, None,
                                 "USD billion", "UN Comtrade (unavailable)",
                                 CT_PREVIEW_BASE, note=missing_note)
                    r["value_type"] = "missing_official"
                    r["data_quality"] = "missing"
                    r["confidence"] = "none"
                    rows.append(r)
                return rows

            for flow, val_raw in best.items():
                val_b = round(val_raw / 1e9, 3)
                if flow == "X":
                    rows.append(make_row(reporter_iso3, f"EXPORTS_TO_{partner_iso3}",
                        f"Exports to {pname} (USD Billion)", year, val_b,
                        "USD billion", source, url, note=note))
                elif flow == "M":
                    rows.append(make_row(reporter_iso3, f"IMPORTS_FROM_{partner_iso3}",
                        f"Imports from {pname} (USD Billion)", year, val_b,
                        "USD billion", source, url, note=note))
            return rows

        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(1.5 ** attempt)
            else:
                print(f"      ⚠ {partner_iso3}/{year}: {e}", flush=True)
    return []


# ─── Comtrade authenticated: bilateral + total ────────────────────────────

def _auth_fetch(reporter_num: int, reporter_iso3: str,
                partner_num: int, partner_iso3: str,
                start: int, end: int) -> list[dict]:
    """Authenticated Comtrade Plus API — batch years in one request."""
    periods = ",".join(str(y) for y in range(start, end + 1))
    params = {
        "typeCode": "C", "freqCode": "A", "clCode": "HS",
        "reporterCode": reporter_num,
        "period": periods,
        "cmdCode": "TOTAL", "flowCode": "X,M",
        "partnerCode": partner_num, "partner2Code": 0,
        "subscription-key": COMTRADE_API_KEY,
    }
    headers = {
        "User-Agent": "SEA-Dashboard/2.0",
        "Accept": "application/json",
        "Ocp-Apim-Subscription-Key": COMTRADE_API_KEY,
    }
    url = f"{CT_AUTH_BASE}/C/A/HS"
    source = "UN Comtrade Database"
    note   = "UN Comtrade Plus authenticated API."

    for attempt in range(MAX_RETRIES):
        try:
            r = _get(url, headers=headers, params=params, timeout=30)
            if r.status_code in (401, 403):
                print(f"      ✗ Auth error HTTP {r.status_code}", flush=True)
                return []
            if r.status_code == 429:
                time.sleep(60 * (attempt + 1))
                continue
            if r.status_code != 200:
                return []

            recs = r.json().get("data", [])
            mot0 = [x for x in recs if x.get("motCode") == 0] or recs

            rows: list[dict] = []
            is_total = (partner_num == 0)
            by_yf: dict = {}
            for rec in mot0:
                yr   = rec.get("refYear") or rec.get("period")
                flow = rec.get("flowCode", "")
                val  = rec.get("primaryValue")
                if yr and flow and val and val > 0:
                    k = (int(yr), flow)
                    if k not in by_yf or val > by_yf[k]:
                        by_yf[k] = val

            for (yr, flow), val_raw in by_yf.items():
                val_b = round(val_raw / 1e9, 3)
                pname = PARTNER_NAMES.get(partner_iso3, partner_iso3)
                if is_total:
                    code = "EXPORTS_USD" if flow == "X" else "IMPORTS_USD"
                    name = ("Total Exports (USD Billion)" if flow == "X"
                            else "Total Imports (USD Billion)")
                else:
                    code = (f"EXPORTS_TO_{partner_iso3}" if flow == "X"
                            else f"IMPORTS_FROM_{partner_iso3}")
                    name = (f"Exports to {pname} (USD Billion)" if flow == "X"
                            else f"Imports from {pname} (USD Billion)")
                rows.append(make_row(reporter_iso3, code, name, yr, val_b,
                                     "USD billion", source, url, note=note))
            return rows

        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
            else:
                print(f"      ⚠ auth error: {e}", flush=True)
    return []


# ─── World Bank WDI: total trade ──────────────────────────────────────────

WB_TOTAL_INDICATORS = {
    "TX.VAL.MRCH.CD.WT": ("EXPORTS_USD",     "Total Merchandise Exports (USD Billion)", "USD billion", 1e9),
    "TM.VAL.MRCH.CD.WT": ("IMPORTS_USD",     "Total Merchandise Imports (USD Billion)", "USD billion", 1e9),
    "NE.TRD.GNFS.ZS":    ("TRADE_OPENNESS",  "Trade (% of GDP)",                        "% of GDP",    1.0),
}


def fetch_wb_totals(iso3_list: list[str], start: int, end: int,
                    delay: float = 1.5) -> list[dict]:
    """Fetch total trade and trade openness from World Bank WDI."""
    rows: list[dict] = []
    wb_codes = ";".join(WB_CODE_MAP.get(c, c) for c in iso3_list)
    for wb_indicator, (code, name, unit, div) in WB_TOTAL_INDICATORS.items():
        # Embed params in URL — httpx encodes the date colon (%3A) and semicolons
        # differently when passed as a dict, causing WB to return 400.
        url = (f"{WB_BASE}/country/{wb_codes}/indicator/{wb_indicator}"
               f"?date={start}:{end}&format=json&per_page=1000")
        try:
            r = _get(url, headers={"User-Agent": "SEA-Dashboard/2.0"})
            if r.status_code == 200:
                data = r.json()
                for rec in (data[1] if isinstance(data, list) and len(data) > 1 else []):
                    if rec.get("value") is None:
                        continue
                    iso2 = rec.get("country", {}).get("id", "")
                    iso3 = WB_ISO2_TO_ISO3.get(iso2, iso2)
                    if iso3 not in ALL_REPORTERS:
                        continue
                    try:
                        yr = int(rec["date"])
                    except (KeyError, ValueError):
                        continue
                    val = round(float(rec["value"]) / div, 3)
                    rows.append(make_row(iso3, code, name, yr, val, unit,
                        "World Bank WDI",
                        f"https://api.worldbank.org/v2/country/{WB_CODE_MAP.get(iso3,iso3)}/indicator/{wb_indicator}",
                        note="World Bank WDI — 1-2 year publication lag."))
        except Exception as e:
            print(f"    ⚠ WB {wb_indicator}: {e}", flush=True)
        time.sleep(delay)
    return rows


# ─── Derived metrics ──────────────────────────────────────────────────────

def compute_trade_balance(all_rows: list[dict]) -> list[dict]:
    by_cy: dict = {}
    for r in all_rows:
        if r["indicator_code"] in ("EXPORTS_USD", "IMPORTS_USD") and r["value"] is not None:
            by_cy.setdefault((r["country_code"], r["year"]), {})[r["indicator_code"]] = r

    out = []
    for (iso3, year), imap in by_cy.items():
        exp = imap.get("EXPORTS_USD")
        imp = imap.get("IMPORTS_USD")
        if exp and imp:
            out.append(make_row(iso3, "TRADE_BALANCE_USD",
                "Trade Balance (Exports − Imports, USD Billion)", year,
                round(exp["value"] - imp["value"], 3), "USD billion",
                f"Computed ({exp['source']})", exp["source_url"],
                source_type="computed",
                note="Trade balance = exports minus imports."))
    return out


def compute_dependency_scores(all_rows: list[dict]) -> list[dict]:
    by_cy: dict = {}
    for r in all_rows:
        if r["value"] is None:
            continue
        by_cy.setdefault((r["country_code"], r["year"]), {})[r["indicator_code"]] = r["value"]

    out = []
    for (iso3, year), inds in by_cy.items():
        total_x = inds.get("EXPORTS_USD")
        total_m = inds.get("IMPORTS_USD")
        if total_x is None or total_m is None:
            continue
        total_trade = total_x + total_m
        if total_trade <= 0:
            continue
        for partner in PARTNERS:
            px = inds.get(f"EXPORTS_TO_{partner}")
            pm = inds.get(f"IMPORTS_FROM_{partner}")
            if px is None and pm is None:
                continue
            dep = round(((px or 0) + (pm or 0)) / total_trade * 100, 1)
            level = "high" if dep >= 40 else ("medium" if dep >= 20 else "low")
            out.append(make_row(iso3, f"TRADE_DEPENDENCY_{partner}",
                f"{PARTNER_NAMES[partner]} Trade Dependency", year, dep,
                "% of total trade", "Computed from UN Comtrade + WB WDI",
                CT_PREVIEW_BASE, source_type="computed",
                note=f"Bilateral / total trade × 100. Level: {level}."))
    return out


def compute_top_partner(dep_rows: list[dict]) -> list[dict]:
    by_cy: dict = {}
    for r in dep_rows:
        if r["value"] is None:
            continue
        code = r["indicator_code"]
        if not code.startswith("TRADE_DEPENDENCY_"):
            continue
        partner = code.replace("TRADE_DEPENDENCY_", "")
        by_cy.setdefault((r["country_code"], r["year"]), {})[partner] = r["value"]

    out = []
    for (iso3, year), pmap in by_cy.items():
        top = max(pmap, key=lambda p: pmap[p])
        val = pmap[top]
        level = "high" if val >= 40 else ("medium" if val >= 20 else "low")
        out.append(make_row(iso3, "TOP_TRADE_PARTNER_SHARE", "Top Trade Partner Share",
            year, val, "% of total trade", "Computed from UN Comtrade + WB WDI",
            CT_PREVIEW_BASE, source_type="computed",
            note=f"Top: {PARTNER_NAMES.get(top, top)} ({val:.1f}%, {level})."))
    return out


# ─── Main ─────────────────────────────────────────────────────────────────

def main():
    print(_KEY_MSG)

    parser = argparse.ArgumentParser()
    parser.add_argument("--reporter", nargs="+",
                        default=list(SEA_REPORTERS.keys()),
                        choices=list(ALL_REPORTERS.keys()))
    parser.add_argument("--year", type=int, default=2024,
                        help="Latest year to fetch (default 2024)")
    parser.add_argument("--all-years", action="store_true",
                        help=f"Fetch {START_YEAR}–2024 for each reporter")
    parser.add_argument("--no-bilateral", action="store_true",
                        help="Skip bilateral partner fetches")
    parser.add_argument("--no-wb", action="store_true",
                        help="Skip World Bank WDI supplement")
    args = parser.parse_args()

    years   = list(range(START_YEAR, args.year + 1)) if args.all_years else [args.year]
    delay_c = 1.2 if COMTRADE_ENABLED else 0.5   # auth needs more breathing room

    print(f"\n{'═'*62}")
    print(f"  Trade Flows Fetcher — {today_str}")
    print(f"  Mode     : {'authenticated Comtrade' if COMTRADE_ENABLED else 'public preview + WB WDI'}")
    print(f"  Reporters: {args.reporter}")
    print(f"  Years    : {years}")
    print(f"{'═'*62}\n")

    all_rows: list[dict] = []

    # ── Comtrade bilateral ─────────────────────────────────────────────────
    if not args.no_bilateral:
        print("  ── Comtrade bilateral flows ──────────────────────────")
        for iso3 in args.reporter:
            reporter_num = ALL_REPORTERS.get(iso3)
            if reporter_num is None:
                continue
            print(f"\n  {iso3} ({REPORTER_NAMES.get(iso3, iso3)})")
            country_bilateral_rows = 0

            for partner_iso3, partner_num in PARTNERS.items():
                partner_rows: list[dict] = []
                print(f"    → {partner_iso3}...", end=" ", flush=True)

                if COMTRADE_ENABLED:
                    partner_rows = _auth_fetch(reporter_num, iso3,
                                               partner_num, partner_iso3,
                                               years[0], years[-1])
                else:
                    # Public preview: one call per year
                    for year in years:
                        rows_y = _preview_bilateral_year(
                            reporter_num, iso3, partner_num, partner_iso3, year)
                        partner_rows.extend(rows_y)
                        time.sleep(delay_c)

                all_rows.extend(partner_rows)
                country_bilateral_rows += len(partner_rows)
                print(f"{len(partner_rows)} rows", flush=True)
                if COMTRADE_ENABLED:
                    time.sleep(delay_c)

            print(f"  → {iso3} bilateral total: {country_bilateral_rows} rows")

    # ── World Bank WDI total trade + openness ──────────────────────────────
    if not args.no_wb:
        print(f"\n  ── World Bank WDI (totals + openness) ───────────────")
        wb_rows = fetch_wb_totals(args.reporter, years[0], years[-1])
        all_rows.extend(wb_rows)
        from collections import Counter
        wb_by_ind = Counter(r["indicator_code"] for r in wb_rows)
        for ind, cnt in sorted(wb_by_ind.items()):
            print(f"  ▸ {ind}: {cnt} rows")

    # ── Comtrade authenticated: total trade ────────────────────────────────
    if COMTRADE_ENABLED:
        print(f"\n  ── Comtrade total trade (authenticated) ─────────────")
        for iso3 in args.reporter:
            reporter_num = ALL_REPORTERS.get(iso3)
            if reporter_num is None:
                continue
            print(f"  {iso3} total...", end=" ", flush=True)
            total_rows = _auth_fetch(reporter_num, iso3, 0, "ALL",
                                     years[0], years[-1])
            all_rows.extend(total_rows)
            print(f"{len(total_rows)} rows")
            time.sleep(delay_c)

    # ── Derived metrics ────────────────────────────────────────────────────
    print(f"\n  ── Computed metrics ─────────────────────────────────")
    bal_rows = compute_trade_balance(all_rows)
    all_rows.extend(bal_rows)
    print(f"  ▸ Trade balance     : {len(bal_rows)} rows")

    dep_rows = compute_dependency_scores(all_rows)
    all_rows.extend(dep_rows)
    print(f"  ▸ Dependency scores : {len(dep_rows)} rows")

    top_rows = compute_top_partner(dep_rows)
    all_rows.extend(top_rows)
    print(f"  ▸ Top-partner rows  : {len(top_rows)} rows")

    # ── Source coverage ────────────────────────────────────────────────────
    from collections import Counter
    by_src = Counter(r["source"] for r in all_rows if r["value"] is not None)
    print(f"\n  ── Source coverage (non-null rows) ──────────────────")
    for src, cnt in by_src.most_common():
        print(f"  ▸ {src[:55]:<55} {cnt:>4}")

    # ── Write outputs ──────────────────────────────────────────────────────
    non_null = sum(1 for r in all_rows if r["value"] is not None)
    result = {
        "source":     "UN Comtrade + World Bank WDI",
        "source_id":  "COMTRADE_WB",
        "mode":       "authenticated" if COMTRADE_ENABLED else "public_preview",
        "fetched_at": ts_now(),
        "years":      years,
        "reporters":  args.reporter,
        "total_rows": len(all_rows),
        "non_null":   non_null,
        "comtrade_api_available": COMTRADE_ENABLED,
        "records":    all_rows,
    }
    raw_path = RAW_DIR / f"comtrade_{today_str}.json"
    raw_path.write_text(json.dumps({"fetched_at": ts_now(), "rows": all_rows}, indent=2))
    (PROC_DIR / "comtrade_normalized.json").write_text(json.dumps(result, indent=2))
    (PROC_DIR / "trade_flows.json").write_text(json.dumps(result, indent=2))

    print(f"\n{'─'*62}")
    print(f"  ✓ Total rows : {len(all_rows)}")
    print(f"  ✓ Non-null   : {non_null}")
    print(f"  📄 pipeline/data/processed/comtrade_normalized.json")
    print(f"  📄 pipeline/data/processed/trade_flows.json\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
