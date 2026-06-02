#!/usr/bin/env python3
"""
==============================================================================
  generate_alerts.py — SEA Change Intelligence Dashboard
==============================================================================

Reads processed indicator data and news risk counts, builds a CountrySnapshot
for each SEA country, runs the 8-type pattern alert engine, and saves the
results to alerts.json.

INPUT FILES  (both must exist):
  pipeline/data/processed/indicators_dashboard.json  ← from process_indicators.py
  pipeline/data/processed/news_dashboard.json        ← from process_news.py  (optional)

OUTPUT FILE:
  pipeline/data/processed/alerts.json

WHAT THIS SCRIPT DOES  (step by step)
──────────────────────────────────────
  1. Loads indicators_dashboard.json (per-country indicator values + trade)
  2. Loads news_dashboard.json (per-country risk counts)  — optional
  3. Builds a "CountrySnapshot" data object for each of the 10 SEA countries
  4. Runs all 8 alert checks via the existing pattern_engine.py
  5. Filters to only "triggered" alerts (score ≥ 20 by default)
  6. Sorts: critical first, then by score descending
  7. Builds index views: by_country, by_type, by_severity
  8. Saves everything to alerts.json

THE 8 ALERT TYPES (from pattern_engine.py)
────────────────────────────────────────────
  1. export_stress          — exports falling, trade balance worsening
  2. inflation_pressure     — high or accelerating CPI
  3. political_instability  — conflict / protest news spike
  4. currency_pressure      — exchange rate depreciating + inflation
  5. investment_slowdown    — FDI declining + political uncertainty
  6. trade_dependency_risk  — over-concentrated export/import partner
  7. tourism_recovery       — arrivals still below 2019 baseline
  8. regional_spillover     — multiple neighbours under stress simultaneously

ALERT SCORES
────────────
  Each alert has a score from 0–100.
  • score ≥ 20  → alert "triggered" (shown in the dashboard)
  • score ≥ 38  → warning severity
  • score ≥ 62  → critical severity (exact thresholds vary per alert type)

HOW TO RUN
──────────
  cd pipeline
  python generate_alerts.py                    # normal run (min score = 20)
  python generate_alerts.py --min-score 30     # only alerts scoring ≥ 30
  python generate_alerts.py --country MMR      # single country (for testing)

==============================================================================
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from utils.logger import ok, fail, warn, info, section

# ── Import the existing pattern alert engine ──────────────────────────────────
# This file already exists at pipeline/pattern_engine.py and contains all
# 8 alert types plus the CountrySnapshot / AlertResult dataclasses.
try:
    from pattern_engine import (
        CountrySnapshot,
        AlertResult,
        run_all_countries,
        ALERT_TRIGGER_MIN,
    )
except ImportError as exc:
    print(f"  ✗  Cannot import pattern_engine.py: {exc}", file=sys.stderr)
    print("     Make sure pattern_engine.py is in the pipeline/ directory.", file=sys.stderr)
    sys.exit(1)


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 1 — FILE PATHS
# ══════════════════════════════════════════════════════════════════════════════

PROC_DIR   = SCRIPT_DIR / "data" / "processed"
IND_FILE   = PROC_DIR / "indicators_dashboard.json"
NEWS_FILE  = PROC_DIR / "news_dashboard.json"
OUT_FILE   = PROC_DIR / "alerts.json"

# Only these 10 SEA countries are checked for alerts
# (partner countries like China and the US are data inputs, not alert subjects)
SEA_REPORTERS: set[str] = {"THA","VNM","MMR","KHM","LAO","MYS","SGP","IDN","PHL","BRN"}


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 2 — BUILD COUNTRY SNAPSHOTS
# ══════════════════════════════════════════════════════════════════════════════

def _get(country_entry: dict, indicator_key: str, field: str = "value") -> float | None:
    """
    Safely retrieve one field from one indicator in a country entry.

    Example:
      _get(tha_entry, "gdpGrowth", "value")     → 2.02
      _get(tha_entry, "gdpGrowth", "prev_value") → 2.55
    Returns None if the indicator or field is missing.
    """
    return country_entry.get("indicators", {}).get(indicator_key, {}).get(field)


def build_snapshot(
    iso3: str,
    country_entry: dict,
    risk_scores: dict,
) -> CountrySnapshot:
    """
    Build a CountrySnapshot dataclass from processed indicator data.

    The CountrySnapshot is what the pattern_engine.py alert checks expect.
    All fields default to None when data is unavailable — the engine
    handles missing fields gracefully (it just skips those sub-checks).

    Parameters
    ──────────
    iso3          : ISO3 code, e.g. "THA"
    country_entry : entry from indicators_dashboard.json["countries"]["THA"]
    risk_scores   : from news_dashboard.json["risk_scores"]
    """
    year  = country_entry.get("latest_year") or 2023
    trade = country_entry.get("trade") or {}
    risk  = risk_scores.get(iso3, {})

    return CountrySnapshot(
        iso3 = iso3,
        name = country_entry.get("name", iso3),
        year = year,

        # ── Current-year economic indicators ──────────────────────────────
        gdp_growth    = _get(country_entry, "gdpGrowth"),
        inflation     = _get(country_entry, "inflation"),
        exports_usd_b = _get(country_entry, "exports"),
        imports_usd_b = _get(country_entry, "imports"),
        # Note: fdiPctGdp is % of GDP, not USD billions — used as a proxy for
        # relative FDI change direction. The engine uses it for trend detection,
        # not absolute values, so the unit difference is acceptable.
        fdi_usd_b     = _get(country_entry, "fdiPctGdp"),

        # ── Previous-year values (for year-over-year comparisons) ─────────
        prev_gdp_growth    = _get(country_entry, "gdpGrowth",  "prev_value"),
        prev_inflation     = _get(country_entry, "inflation",  "prev_value"),
        prev_exports_usd_b = _get(country_entry, "exports",   "prev_value"),
        prev_imports_usd_b = _get(country_entry, "imports",   "prev_value"),
        prev_fdi_usd_b     = _get(country_entry, "fdiPctGdp", "prev_value"),

        # ── News signal counts (from GDELT — 7-day window) ─────────────────
        political_risk_news_count   = risk.get("political_risk_count", 0),
        trade_news_count            = risk.get("trade_news_count", 0),
        # conflict_protest is a subset of political risk — use it as a proxy
        conflict_protest_news_count = risk.get("political_risk_count", 0),

        # ── Trade partner concentration (from UN Comtrade) ────────────────
        top_export_partner       = trade.get("top_export_partner"),
        top_export_partner_share = trade.get("top_export_share_pct"),
        top_import_partner       = trade.get("top_import_partner"),
        top_import_partner_share = trade.get("top_import_share_pct"),
    )


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 3 — OUTPUT SERIALISATION
# ══════════════════════════════════════════════════════════════════════════════

def alert_to_dict(alert: AlertResult, source_url: str) -> dict:
    """
    Convert an AlertResult dataclass to a plain dict that can be saved as JSON.
    Adds a generated_at timestamp and source_url for traceability.
    """
    d = asdict(alert)
    d["generated_at"] = datetime.now().isoformat(timespec="seconds")
    d["source_url"]   = source_url
    return d


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 4 — MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main() -> int:
    """
    Exit codes:
      0 — completed (even if some countries had errors)
      1 — fatal error (missing required input, can't write output)
    """
    parser = argparse.ArgumentParser(
        description="Run pattern alert engine and save alerts.json"
    )
    parser.add_argument(
        "--min-score", type=float, default=ALERT_TRIGGER_MIN,
        help=f"Only include alerts with score ≥ this value (default: {ALERT_TRIGGER_MIN})",
    )
    parser.add_argument(
        "--country", type=str, default=None,
        help="Only process one country, e.g. --country MMR  (useful for testing)",
    )
    args = parser.parse_args()
    only_iso3 = args.country.upper() if args.country else None

    # ── Banner ──────────────────────────────────────────────────────────────
    print()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║   SEA Dashboard — Generate Pattern Alerts                   ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()
    print(f"  Input   (ind)  : {IND_FILE.relative_to(SCRIPT_DIR)}")
    print(f"  Input   (news) : {NEWS_FILE.relative_to(SCRIPT_DIR)}")
    print(f"  Output         : {OUT_FILE.relative_to(SCRIPT_DIR)}")
    print(f"  Min score      : {args.min_score}")
    if only_iso3:
        print(f"  Country filter : {only_iso3} only")
    print()

    # ── Step 1: Load indicators ──────────────────────────────────────────────
    section("Step 1 — Load processed data")

    if not IND_FILE.exists():
        fail(
            f"Indicators file not found: {IND_FILE}\n"
            "  → Run this first:  python process_indicators.py"
        )
        return 1

    with open(IND_FILE, encoding="utf-8") as f:
        ind_json = json.load(f)
    ind_meta = ind_json.get("meta", {})
    ok(f"Indicators: {len(ind_json.get('countries', {}))} countries  "
       f"(processed {ind_meta.get('generated_at', '?')})")

    # News file is optional — alerts can still run without news counts
    risk_scores: dict[str, dict] = {}
    if NEWS_FILE.exists():
        with open(NEWS_FILE, encoding="utf-8") as f:
            news_json = json.load(f)
        risk_scores = news_json.get("risk_scores", {})
        ok(f"News risk scores: {len(risk_scores)} countries")
    else:
        warn(
            f"News dashboard file not found: {NEWS_FILE.name}\n"
            "  Political instability alerts will run without news signal data.\n"
            "  → Run:  python process_news.py"
        )

    # ── Step 2: Build snapshots ──────────────────────────────────────────────
    section("Step 2 — Build country snapshots")
    countries = ind_json.get("countries", {})
    targets = {
        iso3: entry
        for iso3, entry in countries.items()
        if iso3 in SEA_REPORTERS
        and (only_iso3 is None or iso3 == only_iso3)
    }

    snapshots: list[CountrySnapshot] = []
    snap_errors = 0

    for iso3, entry in targets.items():
        try:
            snap = build_snapshot(iso3, entry, risk_scores)
            snapshots.append(snap)

            flag = entry.get("flag", "")
            name = entry.get("name", iso3).ljust(16)
            yr   = snap.year
            gdp  = f"gdp={snap.gdp_growth:.1f}%"  if snap.gdp_growth  is not None else "gdp=n/a"
            cpi  = f"cpi={snap.inflation:.1f}%"   if snap.inflation   is not None else "cpi=n/a"
            pol  = f"pol={snap.political_risk_news_count}"
            info(f"{flag} {name}  yr={yr}  {gdp}  {cpi}  {pol}")

        except Exception as exc:
            # One country must never crash the whole pipeline.
            snap_errors += 1
            fail(f"{iso3}: snapshot build failed — {exc}")

    ok(f"Built {len(snapshots)} snapshots  ({snap_errors} errors)")

    if not snapshots:
        fail("No snapshots built — cannot run alert engine. Check indicator data.")
        return 1

    # ── Step 3: Run alert engine ─────────────────────────────────────────────
    section("Step 3 — Run 8-type pattern alert engine")
    n_checks = 8 * len(snapshots)
    info(f"Running {n_checks} checks  ({len(snapshots)} countries × 8 alert types) …")

    all_results: list[AlertResult] = []
    engine_error = False

    try:
        # run_all_countries handles peer-aware checks (e.g. regional_spillover)
        # by automatically building the peer map from the snapshot list
        all_results = run_all_countries(snapshots, min_score=0.0)
        ok(f"Engine complete: {len(all_results)} raw results")
    except Exception as exc:
        fail(f"Alert engine crashed: {exc}")
        engine_error = True

    # ── Step 4: Filter and report ────────────────────────────────────────────
    section("Step 4 — Filter and summarise")
    triggered = [
        a for a in all_results
        if a.score >= args.min_score and a.triggered
    ]
    info(f"Triggered alerts (score ≥ {args.min_score}): {len(triggered)}")

    # Tally by severity
    sev_counts: dict[str, list] = {"critical": [], "warning": [], "info": []}
    for a in triggered:
        if a.severity in sev_counts:
            sev_counts[a.severity].append(a)

    icons = {"critical": "🔴", "warning": "🟡", "info": "🔵"}
    for sev, alerts in sev_counts.items():
        if alerts:
            info(f"{icons[sev]} {sev.upper():<8}: {len(alerts)} alert(s)")
            for a in alerts[:3]:
                info(f"   {a.country_iso3} — {a.alert_label:<30}  score={a.score:.0f}")
            if len(alerts) > 3:
                info(f"   … and {len(alerts) - 3} more")

    # ── Step 5: Build output ──────────────────────────────────────────────────
    section("Step 5 — Build output structure")
    source_url = str(IND_FILE.relative_to(SCRIPT_DIR))

    alerts_list: list[dict] = [
        alert_to_dict(a, source_url) for a in triggered
    ]

    # Index views
    by_country: dict[str, list] = {}
    by_type:    dict[str, list] = {}
    by_severity: dict[str, list] = {"critical": [], "warning": [], "info": []}

    for a_dict in alerts_list:
        iso3  = a_dict["country_iso3"]
        atype = a_dict["alert_type"]
        sev   = a_dict["severity"]

        by_country.setdefault(iso3, []).append(a_dict)
        by_type.setdefault(atype, []).append(a_dict)
        if sev in by_severity:
            by_severity[sev].append(a_dict)

    output = {
        "meta": {
            "generated_at":      datetime.now().isoformat(timespec="seconds"),
            "script":            "generate_alerts.py",
            "source_url":        source_url,
            "fetched_at":        ind_meta.get("fetched_at", ""),
            "total_checks":      len(all_results),
            "triggered_alerts":  len(triggered),
            "critical":          len(by_severity["critical"]),
            "warnings":          len(by_severity["warning"]),
            "info_count":        len(by_severity["info"]),
            "countries_checked": len(snapshots),
            "min_score_filter":  args.min_score,
            "alert_types": [
                "export_stress", "inflation_pressure", "political_instability",
                "currency_pressure", "investment_slowdown", "trade_dependency_risk",
                "tourism_recovery", "regional_spillover",
            ],
            "refresh_note": (
                "Run 'python run_pipeline.py' to refresh all data and regenerate alerts."
            ),
        },
        "alerts":      alerts_list,
        "by_country":  by_country,
        "by_type":     by_type,
        "by_severity": by_severity,
    }

    # ── Step 6: Save ─────────────────────────────────────────────────────────
    PROC_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with open(OUT_FILE, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        size_kb = OUT_FILE.stat().st_size // 1024
        ok(f"Saved → {OUT_FILE.relative_to(SCRIPT_DIR)}  ({size_kb} KB)")
    except Exception as exc:
        fail(f"Could not save output: {exc}")
        return 1

    # ── Final summary ────────────────────────────────────────────────────────
    print()
    print("━" * 62)
    ok("generate_alerts.py complete")
    ok(f"  {len(triggered)} triggered alerts  "
       f"({len(by_severity['critical'])} critical, "
       f"{len(by_severity['warning'])} warnings, "
       f"{len(by_severity['info'])} info)")
    info(f"  Output: {OUT_FILE}")
    print("━" * 62)
    print()

    return 1 if engine_error else 0


if __name__ == "__main__":
    sys.exit(main())
