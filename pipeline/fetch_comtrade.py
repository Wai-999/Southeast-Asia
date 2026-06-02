#!/usr/bin/env python3
"""
==============================================================================
  UN Comtrade Trade Data Fetcher — SEA Change Intelligence Dashboard
  pipeline/fetch_comtrade.py
==============================================================================

Fetches bilateral goods trade data (exports + imports) for 10 SEA reporter
countries against 7 key partner entities from official trade statistics APIs.

REPORTER COUNTRIES (10 SEA):
    Thailand · Vietnam · Myanmar · Cambodia · Laos
    Malaysia · Singapore · Indonesia · Philippines · Brunei

PARTNER ENTITIES (7):
    China · United States · Japan · India · South Korea · Australia · EU

API STRATEGY
─────────────
    Mode A — UN Comtrade Plus API  (primary, requires API key)
        URL   : https://comtradeapi.un.org/data/v1/get/C/A/HS
        Auth  : Ocp-Apim-Subscription-Key: {COMTRADE_SUBSCRIPTION_KEY}
        Docs  : https://comtradeplus.un.org/TradeFlow
        Limit : 250 req/day (free subscription), 500 records/response
        Key   : Set COMTRADE_SUBSCRIPTION_KEY in .env  (or .env.example)

    Mode B — IMF Direction of Trade Statistics (fallback, no key needed)
        URL   : http://dataservices.imf.org/REST/SDMX_JSON.svc/CompactData/DOT
        Auth  : None
        Limit : ~10 req/s, 10,000/day — very permissive
        Key   : None required

    The script auto-detects which mode to use:
        COMTRADE_SUBSCRIPTION_KEY in .env → Mode A (UN Comtrade)
        No key                            → Mode B (IMF DOTS, free)

    Both modes produce IDENTICAL output format.

DEPENDENCY RISK SCORE
──────────────────────
    For each reporter-partner pair:
        partner_share = (exports_to + imports_from) / (total_exports + total_imports)

        partner_share >  40%  →  high dependency
        partner_share 20-40%  →  medium dependency
        partner_share <  20%  →  low dependency

    Separate export-only and import-only risk scores are also computed.

OUTPUT FILES
─────────────
    data/raw/comtrade/
        comtrade_{mode}_{date}.json    Raw API responses (for auditing)

    data/processed/
        trade_flows.json               Master file — frontend reads this

USAGE
──────
    cd pipeline
    python fetch_comtrade.py                    # all 10 reporters, latest years
    python fetch_comtrade.py --years 2021,2022,2023
    python fetch_comtrade.py --year 2023
    python fetch_comtrade.py --monthly 2023     # fetch monthly breakdown too
    python fetch_comtrade.py --reporter THA     # single country test
    python fetch_comtrade.py --refresh          # bypass cache
    python fetch_comtrade.py --dry-run          # print URLs, no fetch

LIMITATIONS
─────────────
    1. ANNUAL DATA ONLY by default. Monthly available from UN Comtrade Plus.
    2. Data lag: most countries publish 1-2 years after the reference period.
    3. Myanmar: data very sparse post-2021 coup. Use with caution.
    4. Brunei: partial coverage; some years missing.
    5. EU aggregate: only available in UN Comtrade mode. IMF DOTS covers
       individual EU members instead.
    6. FOB vs CIF: Exports are FOB; Imports are CIF (~5-10% higher).
       This affects trade balance calculation.

==============================================================================
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Optional

try:
    import httpx
    _HTTP = "httpx"
except ImportError:
    import urllib.request
    import urllib.parse
    _HTTP = "urllib"

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv optional


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 1 — CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

SCRIPT_DIR   = Path(__file__).parent
RAW_DIR      = SCRIPT_DIR / "data" / "raw" / "comtrade"
PROC_DIR     = SCRIPT_DIR / "data" / "processed"

REQUEST_DELAY = 1.5   # seconds between requests
MAX_RETRIES   = 3
ANNUAL_YEARS  = [2019, 2020, 2021, 2022, 2023]

# UN Comtrade Plus API
COMTRADE_URL  = "https://comtradeapi.un.org/data/v1/get/C/A/HS"
COMTRADE_KEY  = os.getenv("COMTRADE_SUBSCRIPTION_KEY", "")

# IMF DOTS API (free fallback)
IMF_DOTS_URL  = "http://dataservices.imf.org/REST/SDMX_JSON.svc/CompactData/DOT"


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 2 — COUNTRY / PARTNER REGISTRY
# ══════════════════════════════════════════════════════════════════════════════

# UN Comtrade uses M49 numeric codes
# IMF DOTS uses ISO2 codes (slightly different for some)

REPORTERS: dict[str, dict] = {
    "THA": {"name": "Thailand",     "flag": "🇹🇭", "comtrade_num": "764", "imf_iso2": "TH"},
    "VNM": {"name": "Vietnam",      "flag": "🇻🇳", "comtrade_num": "704", "imf_iso2": "VN"},
    "MMR": {"name": "Myanmar",      "flag": "🇲🇲", "comtrade_num": "104", "imf_iso2": "MM"},
    "KHM": {"name": "Cambodia",     "flag": "🇰🇭", "comtrade_num": "116", "imf_iso2": "KH"},
    "LAO": {"name": "Laos",         "flag": "🇱🇦", "comtrade_num": "418", "imf_iso2": "LA"},
    "MYS": {"name": "Malaysia",     "flag": "🇲🇾", "comtrade_num": "458", "imf_iso2": "MY"},
    "SGP": {"name": "Singapore",    "flag": "🇸🇬", "comtrade_num": "702", "imf_iso2": "SG"},
    "IDN": {"name": "Indonesia",    "flag": "🇮🇩", "comtrade_num": "360", "imf_iso2": "ID"},
    "PHL": {"name": "Philippines",  "flag": "🇵🇭", "comtrade_num": "608", "imf_iso2": "PH"},
    "BRN": {"name": "Brunei",       "flag": "🇧🇳", "comtrade_num": "096", "imf_iso2": "BN"},
}

PARTNERS: dict[str, dict] = {
    "WLD": {"name": "World (Total)", "flag": "🌐", "comtrade_num": "0",   "imf_iso2": "W00"},
    "CHN": {"name": "China",         "flag": "🇨🇳", "comtrade_num": "156", "imf_iso2": "CN"},
    "USA": {"name": "United States", "flag": "🇺🇸", "comtrade_num": "842", "imf_iso2": "US"},
    "JPN": {"name": "Japan",         "flag": "🇯🇵", "comtrade_num": "392", "imf_iso2": "JP"},
    "IND": {"name": "India",         "flag": "🇮🇳", "comtrade_num": "356", "imf_iso2": "IN"},
    "KOR": {"name": "South Korea",   "flag": "🇰🇷", "comtrade_num": "410", "imf_iso2": "KR"},
    "AUS": {"name": "Australia",     "flag": "🇦🇺", "comtrade_num": "036", "imf_iso2": "AU"},
    "EUU": {
        "name": "European Union",
        "flag": "🇪🇺",
        "comtrade_num": "97",
        "imf_iso2": "U2",   # IMF code for EU aggregate
        "note": "EU as bloc. Available in Comtrade mode; IMF DOTS uses U2 (Euro Area) as proxy."
    },
}

# Build reverse lookups
_COMTRADE_NUM_TO_ISO3: dict[str, str] = {
    **{v["comtrade_num"]: k for k, v in REPORTERS.items()},
    **{v["comtrade_num"]: k for k, v in PARTNERS.items()},
}
_IMF_ISO2_TO_ISO3: dict[str, str] = {
    **{v["imf_iso2"]: k for k, v in REPORTERS.items()},
    **{v["imf_iso2"]: k for k, v in PARTNERS.items()},
}


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 3 — DEPENDENCY RISK SCORING
# ══════════════════════════════════════════════════════════════════════════════

def partner_dependency_level(share: float) -> str:
    """
    Convert a partner share (0–1) to a dependency risk label.

    Formula (as specified):
        partner_share = trade_with_partner / total_trade
        > 40%  →  "high"
        20–40% →  "medium"
        < 20%  →  "low"
    """
    pct = share * 100
    if pct > 40:
        return "high"
    elif pct >= 20:
        return "medium"
    else:
        return "low"


def compute_dependency(
    exports_by_partner: dict[str, float],   # {iso3: USD billions}
    imports_by_partner: dict[str, float],
) -> dict:
    """
    Compute per-partner dependency risk for one reporter-year.

    Returns a dict of:
      total_exports_usd_b, total_imports_usd_b, trade_balance_usd_b,
      top_export_partner, top_import_partner,
      by_partner: {
          iso3: {
              exports_usd_b, imports_usd_b, total_bilateral_usd_b,
              partner_share, export_share, import_share,
              dependency_risk, export_risk, import_risk
          }
      }
    """
    total_exp = exports_by_partner.get("WLD", sum(
        v for k, v in exports_by_partner.items() if k != "WLD"
    ))
    total_imp = imports_by_partner.get("WLD", sum(
        v for k, v in imports_by_partner.items() if k != "WLD"
    ))
    total_trade = total_exp + total_imp

    # Per-partner breakdown (exclude WLD sentinel)
    by_partner: dict[str, dict] = {}
    for iso3 in PARTNERS:
        if iso3 == "WLD":
            continue
        exp_b  = exports_by_partner.get(iso3, 0.0)
        imp_b  = imports_by_partner.get(iso3, 0.0)
        bilat  = exp_b + imp_b

        if total_trade > 0:
            overall_share = bilat / total_trade
        else:
            overall_share = 0.0

        exp_share = (exp_b / total_exp)  if total_exp > 0 else 0.0
        imp_share = (imp_b / total_imp)  if total_imp > 0 else 0.0

        by_partner[iso3] = {
            "exports_usd_b":        round(exp_b,  3),
            "imports_usd_b":        round(imp_b,  3),
            "total_bilateral_usd_b": round(bilat, 3),
            "partner_share":        round(overall_share, 4),
            "partner_share_pct":    round(overall_share * 100, 1),
            "export_share":         round(exp_share, 4),
            "export_share_pct":     round(exp_share * 100, 1),
            "import_share":         round(imp_share, 4),
            "import_share_pct":     round(imp_share * 100, 1),
            "dependency_risk":      partner_dependency_level(overall_share),
            "export_risk":          partner_dependency_level(exp_share),
            "import_risk":          partner_dependency_level(imp_share),
        }

    # Top partners
    top_exp = max(
        ((k, v["export_share"]) for k, v in by_partner.items()),
        key=lambda x: x[1], default=("N/A", 0)
    )
    top_imp = max(
        ((k, v["import_share"]) for k, v in by_partner.items()),
        key=lambda x: x[1], default=("N/A", 0)
    )

    return {
        "total_exports_usd_b":    round(total_exp,   3),
        "total_imports_usd_b":    round(total_imp,   3),
        "trade_balance_usd_b":    round(total_exp - total_imp, 3),
        "top_export_partner":     top_exp[0],
        "top_export_share_pct":   round(top_exp[1] * 100, 1),
        "top_import_partner":     top_imp[0],
        "top_import_share_pct":   round(top_imp[1] * 100, 1),
        "by_partner":             by_partner,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 4 — HTTP HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _get_json(url: str, params: dict, headers: dict | None = None) -> dict | None:
    """Perform HTTP GET and return JSON, or None on failure."""
    if _HTTP == "httpx":
        resp = httpx.get(url, params=params, headers=headers or {}, timeout=30,
                         follow_redirects=True)
        resp.raise_for_status()
        return resp.json()
    else:
        full = url + "?" + urllib.parse.urlencode(params)
        req  = urllib.request.Request(full, headers={"Accept": "application/json",
                                                      **(headers or {})})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))


def fetch_with_retry(
    url: str,
    params: dict,
    headers: dict | None = None,
    cache_path: Path | None = None,
    use_cache: bool = True,
    dry_run: bool = False,
    label: str = "",
) -> dict | None:
    """
    Fetch a URL with retry and optional file cache.
    Exponential back-off: 2s → 4s → 8s.
    429 rate-limit: 30s → 60s → 90s.
    """
    # ── Cache hit ─────────────────────────────────────────────────────────
    if use_cache and cache_path and cache_path.exists():
        print(f"    [cache] {label or cache_path.name}")
        return json.loads(cache_path.read_text(encoding="utf-8"))

    if dry_run:
        import urllib.parse as up
        print(f"    [dry-run] GET {url}?{up.urlencode(params)}")
        return None

    # ── Live fetch ────────────────────────────────────────────────────────
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            data = _get_json(url, params, headers)
            if data is not None:
                if cache_path:
                    cache_path.parent.mkdir(parents=True, exist_ok=True)
                    cache_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
                return data

        except Exception as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            is_rl  = status == 429

            if is_rl:
                wait = 30 * attempt
                print(f"    ⚠ 429 Rate limit — waiting {wait}s (attempt {attempt})")
            else:
                wait = 2 ** attempt
                print(f"    ✗ {type(exc).__name__} (attempt {attempt}/{MAX_RETRIES}): {exc}")

            if attempt < MAX_RETRIES:
                time.sleep(wait)

    print(f"    ✗ All retries exhausted for: {label}")
    return None


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 5A — UN COMTRADE PLUS API  (Mode A)
# ══════════════════════════════════════════════════════════════════════════════

def _comtrade_reporter_str(iso3_list: list[str]) -> str:
    return ",".join(REPORTERS[c]["comtrade_num"] for c in iso3_list)

def _comtrade_partner_str() -> str:
    return ",".join(p["comtrade_num"] for p in PARTNERS.values())


def fetch_comtrade_annual(
    reporters: list[str],
    years: list[int],
    use_cache: bool,
    dry_run: bool,
) -> list[dict]:
    """
    Fetch annual export + import totals from UN Comtrade Plus API.

    Makes 2 requests:
      1. All reporters, all partners, exports (flowCode=X), cmdCode=TOTAL
      2. All reporters, all partners, imports (flowCode=M), cmdCode=TOTAL
    """
    rows: list[dict] = []
    headers = {"Ocp-Apim-Subscription-Key": COMTRADE_KEY}
    periods  = ",".join(str(y) for y in years)
    base_params = {
        "reporterCode": _comtrade_reporter_str(reporters),
        "partnerCode":  _comtrade_partner_str(),
        "period":       periods,
        "cmdCode":      "TOTAL",
        "format":       "JSON",
        "maxRecords":   500,
    }

    for flow_code, flow_label in [("X", "Export"), ("M", "Import")]:
        params      = {**base_params, "flowCode": flow_code}
        label       = f"comtrade_annual_{flow_code}_{periods}"
        cache_file  = RAW_DIR / f"{label}.json"

        print(f"  [{flow_label}] UN Comtrade Plus → {len(reporters)} countries × {len(years)} years …",
              end="  ", flush=True)

        raw = fetch_with_retry(
            COMTRADE_URL, params, headers,
            cache_path=cache_file, use_cache=use_cache, dry_run=dry_run,
            label=label,
        )

        if raw is None:
            print("→ failed")
            continue

        records = raw.get("data", [])
        print(f"→ {len(records)} records")

        for rec in records:
            reporter_num = str(rec.get("reporterCode", ""))
            partner_num  = str(rec.get("partnerCode", ""))
            reporter_iso3 = _COMTRADE_NUM_TO_ISO3.get(reporter_num)
            partner_iso3  = _COMTRADE_NUM_TO_ISO3.get(partner_num)

            if not reporter_iso3:
                continue

            # Use fobvalue for exports, cifvalue for imports
            raw_val = rec.get("fobvalue") if flow_code == "X" else rec.get("cifvalue")
            if raw_val is None:
                raw_val = rec.get("primaryValue")
            if raw_val is None:
                continue

            try:
                value_usd_b = round(float(raw_val) / 1_000, 3)  # USD thousands → billions
            except (ValueError, TypeError):
                continue

            rows.append({
                "reporter_code":   reporter_iso3,
                "reporter_name":   REPORTERS.get(reporter_iso3, {}).get("name", reporter_iso3),
                "partner_code":    partner_iso3 or partner_num,
                "partner_name":    PARTNERS.get(partner_iso3, {}).get("name", partner_num) if partner_iso3 else partner_num,
                "year":            int(rec.get("refYear", rec.get("period", 0))),
                "month":           None,
                "flow_code":       flow_code,
                "flow_label":      flow_label,
                "value_usd_b":     value_usd_b,
                "raw_value":       raw_val,
                "source":          "comtrade_plus",
                "source_url":      COMTRADE_URL,
                "last_updated":    date.today().isoformat(),
            })

        time.sleep(REQUEST_DELAY)

    return rows


def fetch_comtrade_monthly(
    reporters: list[str],
    year: int,
    use_cache: bool,
    dry_run: bool,
) -> list[dict]:
    """Fetch monthly totals from UN Comtrade Plus API for one year."""
    rows: list[dict] = []
    headers  = {"Ocp-Apim-Subscription-Key": COMTRADE_KEY}
    # Monthly periods: "202301,202302,...,202312"
    periods  = ",".join(f"{year}{m:02d}" for m in range(1, 13))

    # Use monthly endpoint
    url  = COMTRADE_URL.replace("/C/A/", "/C/M/")  # A→M (annual→monthly)
    base_params = {
        "reporterCode": _comtrade_reporter_str(reporters),
        "partnerCode":  PARTNERS["WLD"]["comtrade_num"],   # World total only for monthly
        "period":       periods,
        "cmdCode":      "TOTAL",
        "format":       "JSON",
        "maxRecords":   500,
    }

    for flow_code, flow_label in [("X", "Export"), ("M", "Import")]:
        params     = {**base_params, "flowCode": flow_code}
        label      = f"comtrade_monthly_{flow_code}_{year}"
        cache_file = RAW_DIR / f"{label}.json"

        print(f"  [Monthly {flow_label}] UN Comtrade {year} …", end="  ", flush=True)
        raw = fetch_with_retry(url, params, headers,
                               cache_path=cache_file, use_cache=use_cache,
                               dry_run=dry_run, label=label)
        if not raw:
            print("→ failed")
            continue

        records = raw.get("data", [])
        print(f"→ {len(records)} records")
        for rec in records:
            num = str(rec.get("reporterCode", ""))
            iso3 = _COMTRADE_NUM_TO_ISO3.get(num)
            if not iso3:
                continue
            raw_val = rec.get("fobvalue") if flow_code == "X" else rec.get("cifvalue")
            if raw_val is None:
                raw_val = rec.get("primaryValue")
            if raw_val is None:
                continue
            period = str(rec.get("period", ""))
            m = int(period[4:6]) if len(period) >= 6 else None
            rows.append({
                "reporter_code": iso3,
                "reporter_name": REPORTERS[iso3]["name"],
                "partner_code":  "WLD",
                "partner_name":  "World (Total)",
                "year":          year,
                "month":         m,
                "period_label":  f"{year}-{m:02d}" if m else str(year),
                "flow_code":     flow_code,
                "flow_label":    flow_label,
                "value_usd_b":   round(float(raw_val) / 1_000, 3),
                "source":        "comtrade_plus",
                "last_updated":  date.today().isoformat(),
            })
        time.sleep(REQUEST_DELAY)

    return rows


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 5C — UN COMTRADE FREE PREVIEW  (Mode C — no key needed)
# ══════════════════════════════════════════════════════════════════════════════
# Strategy: the free preview returns ≤500 records per request. For each
# (reporter, partner, period, flow) group, the max(fobvalue / cifvalue) is
# the aggregate trade value (verified against known figures).
# We batch one year at a time to stay within the 500-record limit.

COMTRADE_FREE_URL  = "https://comtradeapi.un.org/public/v1/preview/C/A/HS"
COMTRADE_FREE_DELAY = 8.0   # conservative: 1 request every 8s

def _ct_free_reporter_str() -> str:
    return ",".join(v["comtrade_num"] for v in REPORTERS.values())

def _ct_free_partner_str() -> str:
    return ",".join(v["comtrade_num"] for v in PARTNERS.values())


def fetch_comtrade_free_annual(
    reporters: list[str],
    years: list[int],
    use_cache: bool,
    dry_run: bool,
) -> list[dict]:
    """
    Fetch annual bilateral trade via UN Comtrade free preview API.
    One request per (year × flow). Takes max(fobvalue/cifvalue) per group.
    """
    rows: list[dict] = []
    reporter_str = ",".join(REPORTERS[r]["comtrade_num"] for r in reporters)
    partner_str  = _ct_free_partner_str()

    total_reqs = len(years) * 2
    req_n = 0

    for year in years:
        for flow_code, val_field, flow_label in [
            ("X", "fobvalue", "Export"),
            ("M", "cifvalue", "Import"),
        ]:
            req_n += 1
            params = {
                "reporterCode": reporter_str,
                "partnerCode":  partner_str,
                "period":       str(year),
                "flowCode":     flow_code,
                "cmdCode":      "TOTAL",
                "format":       "JSON",
            }
            label      = f"ct_free_{flow_code}_{year}"
            cache_file = RAW_DIR / f"{label}.json"

            print(f"  [{req_n}/{total_reqs}] UN Comtrade free  {year} {flow_label} …",
                  end="  ", flush=True)

            raw = fetch_with_retry(
                COMTRADE_FREE_URL, params, None,
                cache_path=cache_file, use_cache=use_cache,
                dry_run=dry_run, label=label,
            )

            if raw is None:
                print("→ failed")
                if not dry_run:
                    time.sleep(COMTRADE_FREE_DELAY)
                continue

            records = raw.get("data", [])

            # Group by (reporter, partner) → take max value (= aggregate)
            groups: dict[tuple, float] = {}
            for rec in records:
                r_code = str(rec.get("reporterCode", ""))
                p_code = str(rec.get("partnerCode", ""))
                val    = rec.get(val_field) or rec.get("primaryValue")
                if val is None:
                    continue
                k = (r_code, p_code)
                try:
                    v = float(val)
                except (ValueError, TypeError):
                    continue
                if k not in groups or v > groups[k]:
                    groups[k] = v   # keep the maximum per group

            print(f"→ {len(records)} raw → {len(groups)} bilateral pairs")

            for (r_code, p_code), max_val in groups.items():
                rep_iso3 = _COMTRADE_NUM_TO_ISO3.get(r_code)
                prt_iso3 = _COMTRADE_NUM_TO_ISO3.get(p_code)
                if rep_iso3 not in REPORTERS:
                    continue

                # UN Comtrade values in USD (not thousands)
                value_usd_b = round(max_val / 1_000_000_000, 3)

                rows.append({
                    "reporter_code": rep_iso3,
                    "reporter_name": REPORTERS[rep_iso3]["name"],
                    "partner_code":  prt_iso3 or p_code,
                    "partner_name":  PARTNERS.get(prt_iso3, {}).get("name", p_code) if prt_iso3 else p_code,
                    "year":          year,
                    "month":         None,
                    "period_label":  str(year),
                    "flow_code":     flow_code,
                    "flow_label":    flow_label,
                    "value_usd_b":   value_usd_b,
                    "raw_value":     max_val,
                    "source":        "comtrade_free",
                    "source_url":    COMTRADE_FREE_URL,
                    "last_updated":  date.today().isoformat(),
                })

            if req_n < total_reqs and not dry_run:
                time.sleep(COMTRADE_FREE_DELAY)

    return rows


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 5B — IMF DOTS API  (Mode B — free fallback)
# ══════════════════════════════════════════════════════════════════════════════

# IMF DOTS indicator codes
_IMF_EXP = "TXG_FOB_USD"   # Goods exports, FOB, USD millions
_IMF_IMP = "TMG_CIF_USD"   # Goods imports, CIF, USD millions


def _build_imf_url(
    reporters: list[str],
    indicator: str,
    freq: str,
    start: str,
    end: str,
) -> str:
    reporter_str  = "+".join(REPORTERS[c]["imf_iso2"] for c in reporters)
    partner_str   = "+".join(p["imf_iso2"] for p in PARTNERS.values())
    path_key      = f"{freq}.{reporter_str}.{indicator}.{partner_str}"
    return (
        f"{IMF_DOTS_URL}/{path_key}"
        f"?startPeriod={start}&endPeriod={end}"
    )


def _parse_imf_sdmx(raw: dict, flow_code: str) -> list[dict]:
    """Parse IMF DOTS SDMX-JSON response into flat row dicts."""
    rows: list[dict] = []
    if not raw:
        return rows

    try:
        dataset = raw["CompactData"]["DataSet"]
    except (KeyError, TypeError):
        return rows

    series_raw = dataset.get("Series", [])
    if isinstance(series_raw, dict):
        series_raw = [series_raw]

    for series in series_raw:
        reporter_iso2    = series.get("@REF_AREA", "")
        partner_iso2     = series.get("@COUNTERPART_AREA", "")
        unit_mult        = int(series.get("@UNIT_MULT", "6"))  # 6 = millions
        reporter_iso3    = _IMF_ISO2_TO_ISO3.get(reporter_iso2)
        partner_iso3     = _IMF_ISO2_TO_ISO3.get(partner_iso2, partner_iso2)

        if reporter_iso3 not in REPORTERS:
            continue

        obs_raw = series.get("Obs", [])
        if isinstance(obs_raw, dict):
            obs_raw = [obs_raw]

        for obs in obs_raw:
            time_str = obs.get("@TIME_PERIOD", "")
            raw_val  = obs.get("@OBS_VALUE")
            if raw_val is None:
                continue
            try:
                value_usd_m = float(raw_val)
            except (ValueError, TypeError):
                continue

            # Convert millions to billions
            value_usd_b = round(value_usd_m / 1_000, 3)

            if "-" in time_str:           # monthly "2023-01"
                parts  = time_str.split("-")
                year   = int(parts[0])
                month  = int(parts[1])
                period = time_str
            else:                         # annual "2023"
                year   = int(time_str)
                month  = None
                period = time_str

            rows.append({
                "reporter_code":  reporter_iso3,
                "reporter_name":  REPORTERS[reporter_iso3]["name"],
                "partner_code":   partner_iso3,
                "partner_name":   PARTNERS.get(partner_iso3, {}).get("name", partner_iso3),
                "year":           year,
                "month":          month,
                "period_label":   period,
                "flow_code":      flow_code,
                "flow_label":     "Export" if flow_code == "X" else "Import",
                "value_usd_b":    value_usd_b,
                "raw_value":      value_usd_m,
                "source":         "imf_dots",
                "source_url":     IMF_DOTS_URL,
                "last_updated":   date.today().isoformat(),
            })

    return rows


def fetch_imf_annual(
    reporters: list[str],
    years: list[int],
    use_cache: bool,
    dry_run: bool,
) -> list[dict]:
    """
    Fetch annual bilateral trade from IMF DOTS.
    Makes 2 requests (exports + imports) for all reporters + partners at once.
    """
    rows: list[dict] = []
    start_yr  = str(min(years))
    end_yr    = str(max(years))

    for indicator, flow_code, label in [
        (_IMF_EXP, "X", "exports"),
        (_IMF_IMP, "M", "imports"),
    ]:
        url        = _build_imf_url(reporters, indicator, "A", start_yr, end_yr)
        cache_file = RAW_DIR / f"imf_annual_{flow_code}_{start_yr}_{end_yr}.json"

        print(f"  [Annual {label}] IMF DOTS {start_yr}–{end_yr} …", end="  ", flush=True)
        raw = fetch_with_retry(
            url, {}, None,
            cache_path=cache_file, use_cache=use_cache, dry_run=dry_run,
            label=cache_file.name,
        )

        if raw:
            parsed = _parse_imf_sdmx(raw, flow_code)
            rows.extend(parsed)
            print(f"→ {len(parsed)} rows")
        else:
            print("→ failed / no data")

        if not dry_run:
            time.sleep(REQUEST_DELAY)

    return rows


def fetch_imf_monthly(
    reporters: list[str],
    year: int,
    use_cache: bool,
    dry_run: bool,
) -> list[dict]:
    """Fetch monthly World totals from IMF DOTS."""
    rows: list[dict] = []
    start_m = f"{year}-01"
    end_m   = f"{year}-12"

    for indicator, flow_code, label in [
        (_IMF_EXP, "X", "exports"),
        (_IMF_IMP, "M", "imports"),
    ]:
        url        = _build_imf_url(reporters, indicator, "M", start_m, end_m)
        cache_file = RAW_DIR / f"imf_monthly_{flow_code}_{year}.json"

        print(f"  [Monthly {label}] IMF DOTS {year} …", end="  ", flush=True)
        raw = fetch_with_retry(
            url, {}, None,
            cache_path=cache_file, use_cache=use_cache, dry_run=dry_run,
            label=cache_file.name,
        )
        if raw:
            parsed = _parse_imf_sdmx(raw, flow_code)
            # Monthly: keep only World partner rows
            world_rows = [r for r in parsed if r["partner_code"] == "WLD" and r["month"] is not None]
            rows.extend(world_rows)
            print(f"→ {len(world_rows)} monthly rows")
        else:
            print("→ failed")

        if not dry_run:
            time.sleep(REQUEST_DELAY)

    return rows


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 6 — AGGREGATION
# ══════════════════════════════════════════════════════════════════════════════

def compute_share_of_world(rows: list[dict]) -> list[dict]:
    """
    Add share_of_world_pct to each annual bilateral row.
    share = value / world_total_for_same_reporter_year_flow
    """
    # Build world total lookup
    world: dict[tuple, float] = {}
    for r in rows:
        if r["partner_code"] == "WLD" and r["month"] is None:
            k = (r["reporter_code"], r["year"], r["flow_code"])
            world[k] = r["value_usd_b"]

    result = []
    for r in rows:
        if r["month"] is not None:
            result.append(r)
            continue
        k     = (r["reporter_code"], r["year"], r["flow_code"])
        total = world.get(k, 0)
        share = round(r["value_usd_b"] / total * 100, 1) if total > 0 else None
        result.append({**r, "share_of_world_pct": share})

    return result


def build_dependency_matrix(
    rows: list[dict],
    years: list[int],
) -> dict:
    """
    Build the full dependency risk matrix:
      { reporter_iso3: { year: { totals + by_partner } } }
    """
    # Organise data: data[reporter][year][flow_code][partner] = value_usd_b
    data: dict = defaultdict(
        lambda: defaultdict(
            lambda: defaultdict(dict)
        )
    )
    for row in rows:
        if row.get("month") is not None:
            continue  # skip monthly for this step
        iso3    = row["reporter_code"]
        yr      = row["year"]
        flow    = row["flow_code"]
        partner = row["partner_code"]
        data[iso3][yr][flow][partner] = row["value_usd_b"]

    matrix: dict = {}
    for iso3 in sorted(data):
        matrix[iso3] = {}
        for yr in sorted(data[iso3]):
            exp = data[iso3][yr].get("X", {})
            imp = data[iso3][yr].get("M", {})
            dep = compute_dependency(exp, imp)
            matrix[iso3][str(yr)] = dep

    return matrix


def compute_monthly_yoy(rows: list[dict]) -> list[dict]:
    """Add yoy_change_pct to monthly World-total rows."""
    # Build prior year lookup
    prior: dict = defaultdict(dict)
    for r in rows:
        if r.get("month") and r["partner_code"] == "WLD":
            k = (r["reporter_code"], r["flow_code"], r["month"])
            prior[k][r["year"]] = r["value_usd_b"]

    result = []
    for r in rows:
        if r.get("month") and r["partner_code"] == "WLD":
            k    = (r["reporter_code"], r["flow_code"], r["month"])
            prev = prior[k].get(r["year"] - 1)
            yoy  = round((r["value_usd_b"] - prev) / prev * 100, 1) if prev and prev > 0 else None
            result.append({**r, "yoy_change_pct": yoy})
        else:
            result.append(r)
    return result


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 7 — OUTPUT WRITERS
# ══════════════════════════════════════════════════════════════════════════════

def save_raw_csv(rows: list[dict]) -> None:
    """Save all annual bilateral rows as a CSV for auditing."""
    ts   = date.today().strftime("%Y%m%d")
    path = RAW_DIR / f"trade_bilateral_{ts}.csv"

    fields = [
        "reporter_code", "reporter_name", "partner_code", "partner_name",
        "year", "flow_code", "flow_label", "value_usd_b",
        "share_of_world_pct", "source", "last_updated",
    ]
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        annual = sorted(
            [r for r in rows if r.get("month") is None],
            key=lambda r: (r["reporter_code"], r["year"], r["flow_code"], r["partner_code"])
        )
        w.writerows(annual)

    print(f"  ✓ Raw CSV   → {path.relative_to(SCRIPT_DIR)}  ({len(annual)} rows)")


def save_processed_json(
    rows:      list[dict],
    dep_matrix: dict,
    api_mode:  str,
    years:     list[int],
    monthly_rows: list[dict],
) -> None:
    """
    Save the master processed JSON at data/processed/trade_flows.json.
    Frontend reads this file.

    Structure:
    {
      "meta":        { generated_at, source, api_mode, reporters, partners, years, … },
      "flows":       [ { reporter_code, partner_code, year, flow_code, value_usd_b, … } ],
      "dependency":  { iso3: { year: { total_exports_usd_b, …, by_partner: { iso3: {…} } } } },
      "monthly":     [ { reporter_code, year, month, flow_code, value_usd_b, yoy_change_pct } ],
      "summary":     [ { reporter_code, year, exports, imports, balance, top_partner, risk } ]
    }
    """
    ts = datetime.now().isoformat(timespec="seconds")

    # Build flat summary table
    summary = []
    for iso3, years_data in dep_matrix.items():
        for yr_str, dep in years_data.items():
            top_exp = dep.get("top_export_partner", "N/A")
            summary.append({
                "reporter_code":          iso3,
                "reporter_name":          REPORTERS.get(iso3, {}).get("name", iso3),
                "year":                   int(yr_str),
                "total_exports_usd_b":    dep["total_exports_usd_b"],
                "total_imports_usd_b":    dep["total_imports_usd_b"],
                "trade_balance_usd_b":    dep["trade_balance_usd_b"],
                "top_export_partner":     top_exp,
                "top_export_share_pct":   dep.get("top_export_share_pct"),
                "top_import_partner":     dep.get("top_import_partner"),
                "top_import_share_pct":   dep.get("top_import_share_pct"),
                "china_export_risk":      dep["by_partner"].get("CHN", {}).get("export_risk"),
                "china_import_risk":      dep["by_partner"].get("CHN", {}).get("import_risk"),
                "china_overall_risk":     dep["by_partner"].get("CHN", {}).get("dependency_risk"),
                "china_partner_share_pct":dep["by_partner"].get("CHN", {}).get("partner_share_pct"),
            })
    summary.sort(key=lambda x: (x["reporter_code"], x["year"]))

    # Clean annual flows (exclude monthly and WLD sentinel)
    annual_flows = [
        {k: v for k, v in r.items() if k not in ("raw_value",)}
        for r in rows
        if r.get("month") is None and r["partner_code"] != "WLD"
    ]

    source_label = (
        "UN Comtrade Plus API (goods trade, HS total)"
        if api_mode == "comtrade"
        else "IMF Direction of Trade Statistics (DOTS) — goods trade, USD millions"
    )

    output = {
        "meta": {
            "generated_at":    ts,
            "source":          source_label,
            "api_mode":        api_mode,
            "reporters":       len(REPORTERS),
            "partners":        len([k for k in PARTNERS if k != "WLD"]),
            "years":           sorted(years),
            "has_monthly":     len(monthly_rows) > 0,
            "data_status":     "live",
            "limitations": [
                "Annual data only. Monthly available from UN Comtrade Plus.",
                "Data lag: most countries publish 1–2 years after reference period.",
                "Exports: FOB. Imports: CIF (~5-10% higher). Affects trade balance.",
                "Myanmar post-2021: sparse data, use with caution.",
                "Brunei: partial coverage.",
                "EU: available in Comtrade mode. IMF DOTS uses U2 (Euro Area) as proxy.",
                "Dependency risk uses combined (export+import) share against total bilateral trade.",
            ],
            "dependency_formula": (
                "partner_share = (exports_to + imports_from) / (total_exports + total_imports). "
                ">40% = high, 20-40% = medium, <20% = low."
            ),
            "refresh_note": (
                "Run 'cd pipeline && python fetch_comtrade.py' to refresh. "
                "Set COMTRADE_SUBSCRIPTION_KEY in .env for UN Comtrade Plus API. "
                "IMF DOTS (free, no key) is used when no key is set."
            ),
        },
        "flows":      annual_flows,
        "dependency": dep_matrix,
        "monthly":    monthly_rows,
        "summary":    summary,
    }

    PROC_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROC_DIR / "trade_flows.json"
    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")

    total_bilateral_pairs = len(annual_flows)
    print(f"  ✓ trade_flows.json → {out_path.relative_to(SCRIPT_DIR)}")
    print(f"    {total_bilateral_pairs} bilateral flow records, {len(summary)} country-year summaries")


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 8 — MAIN ORCHESTRATION
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch UN Comtrade / IMF DOTS trade data for SEA Dashboard",
    )
    parser.add_argument("--year",     type=int, help="Single year (e.g. 2023)")
    parser.add_argument("--years",    type=str, help="Comma-separated years (e.g. 2021,2022,2023)")
    parser.add_argument("--monthly",  type=int, help="Also fetch monthly data for this year")
    parser.add_argument("--reporter", type=str, help="Single ISO3 (e.g. THA)")
    parser.add_argument("--refresh",  action="store_true", help="Bypass cache")
    parser.add_argument("--dry-run",  dest="dry_run", action="store_true",
                        help="Print URLs only, no fetch")
    parser.add_argument("--mode",     choices=["comtrade", "imf", "free", "auto"], default="auto",
                        help="Force API mode (default: auto-detect from .env)")
    args = parser.parse_args()

    # ── Resolve parameters ────────────────────────────────────────────────
    if args.year:
        years = [args.year]
    elif args.years:
        years = [int(y.strip()) for y in args.years.split(",")]
    else:
        years = ANNUAL_YEARS

    reporters = [args.reporter.upper()] if args.reporter else list(REPORTERS.keys())
    for r in reporters:
        if r not in REPORTERS:
            print(f"✗  Unknown reporter: {r}. Valid: {', '.join(REPORTERS)}")
            sys.exit(1)

    use_cache = not args.refresh

    # ── Detect API mode ───────────────────────────────────────────────────
    if args.mode == "comtrade":
        api_mode = "comtrade"
    elif args.mode == "imf":
        api_mode = "imf_dots"
    elif args.mode == "free":
        api_mode = "comtrade_free"
    else:
        # Auto: Plus API if key available, else free preview
        if COMTRADE_KEY and COMTRADE_KEY != "your_comtrade_key_here":
            api_mode = "comtrade"
        else:
            api_mode = "comtrade_free"  # UN Comtrade free preview (no key, real data)

    # ── Banner ────────────────────────────────────────────────────────────
    print()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║   SEA Change Dashboard — Trade Data Fetcher                 ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print(f"  API mode    : {api_mode.upper().replace('_', ' ')}")
    mode_labels = {
        "comtrade":      "UN Comtrade Plus (API key found)",
        "comtrade_free": "UN Comtrade Free Preview (no key needed)",
        "imf_dots":      "IMF DOTS (no key needed)",
    }
    print(f"  Data source : {mode_labels.get(api_mode, api_mode)}")
    print(f"  Reporters   : {len(reporters)}  ({', '.join(reporters)})")
    print(f"  Partners    : {', '.join(k for k in PARTNERS if k != 'WLD')}")
    print(f"  Years       : {years}")
    print(f"  Monthly     : {args.monthly or 'no'}")
    print(f"  Cache       : {'bypass' if args.refresh else 'use if available'}")
    print(f"  Raw dir     : {RAW_DIR.relative_to(SCRIPT_DIR)}/")
    print(f"  Output      : {PROC_DIR.relative_to(SCRIPT_DIR)}/trade_flows.json")
    if api_mode == "imf_dots":
        print()
        print("  ℹ  EU data uses IMF U2 (Euro Area) as proxy — set COMTRADE_SUBSCRIPTION_KEY")
        print("     in .env for full EU aggregate via UN Comtrade Plus API.")

    RAW_DIR.mkdir(parents=True, exist_ok=True)

    # ── Fetch annual data ──────────────────────────────────────────────────
    print(f"\n[ STEP 1 ] Fetching annual bilateral trade ({min(years)}–{max(years)}) …")
    if api_mode == "comtrade":
        annual_rows = fetch_comtrade_annual(reporters, years, use_cache, args.dry_run)
    elif api_mode == "comtrade_free":
        annual_rows = fetch_comtrade_free_annual(reporters, years, use_cache, args.dry_run)
    else:
        annual_rows = fetch_imf_annual(reporters, years, use_cache, args.dry_run)

    if not annual_rows and not args.dry_run:
        print("\n✗  No data returned. Check network, API key, or try --mode imf")
        sys.exit(1)

    # ── Fetch monthly data (optional) ─────────────────────────────────────
    monthly_rows: list[dict] = []
    if args.monthly:
        print(f"\n[ STEP 2 ] Fetching monthly data for {args.monthly} …")
        if api_mode == "comtrade":
            monthly_rows = fetch_comtrade_monthly(reporters, args.monthly,
                                                   use_cache, args.dry_run)
        else:
            monthly_rows = fetch_imf_monthly(reporters, args.monthly,
                                              use_cache, args.dry_run)
        monthly_rows = compute_monthly_yoy(monthly_rows)
    else:
        print("\n[ STEP 2 ] Monthly data skipped (use --monthly YEAR to enable)")

    # ── Enrich: add world share ────────────────────────────────────────────
    print(f"\n[ STEP 3 ] Computing share-of-world and dependency risk scores …")
    all_rows = compute_share_of_world(annual_rows)

    # ── Build dependency matrix ────────────────────────────────────────────
    dep_matrix = build_dependency_matrix(all_rows, years)

    # ── Print dependency summary ───────────────────────────────────────────
    latest_yr = max(years)
    print(f"\n  Dependency risk matrix — {latest_yr} (partner_share of total bilateral trade)")
    print(f"  {'Reporter':<14}  {'CHN':>5}  {'USA':>5}  {'JPN':>5}  {'IND':>5}  {'KOR':>5}  {'AUS':>5}")
    print(f"  {'─'*14}  {'─'*5}  {'─'*5}  {'─'*5}  {'─'*5}  {'─'*5}  {'─'*5}")
    for iso3, r in REPORTERS.items():
        yr_data = dep_matrix.get(iso3, {}).get(str(latest_yr), {})
        bp = yr_data.get("by_partner", {})
        def risk_char(p: str) -> str:
            lvl = bp.get(p, {}).get("dependency_risk", "?")
            return {"high": "HIGH", "medium": " MED", "low": " low", "?": "  ?"}.get(lvl, lvl[:4])
        print(
            f"  {r['flag']} {r['name']:<12}  "
            f"{risk_char('CHN'):>5}  {risk_char('USA'):>5}  "
            f"{risk_char('JPN'):>5}  {risk_char('IND'):>5}  "
            f"{risk_char('KOR'):>5}  {risk_char('AUS'):>5}"
        )

    # ── Save outputs ───────────────────────────────────────────────────────
    print(f"\n[ STEP 4 ] Saving outputs …")
    save_raw_csv(all_rows)
    save_processed_json(all_rows, dep_matrix, api_mode, years, monthly_rows)

    # ── Done ───────────────────────────────────────────────────────────────
    print()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║  ✓  Done!                                                    ║")
    print("║                                                               ║")
    print("║  Frontend reads from:                                         ║")
    print("║    pipeline/data/processed/trade_flows.json                   ║")
    print("║                                                               ║")
    print("║  To use UN Comtrade Plus API:                                 ║")
    print("║    1. Register free at https://comtradeplus.un.org            ║")
    print("║    2. Add COMTRADE_SUBSCRIPTION_KEY=<key> to .env             ║")
    print("║    3. Re-run: python fetch_comtrade.py --refresh              ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()


if __name__ == "__main__":
    main()
