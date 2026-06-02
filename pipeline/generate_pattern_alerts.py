#!/usr/bin/env python3
"""
==============================================================================
  generate_pattern_alerts.py — SEA Change Intelligence Dashboard
==============================================================================

Reads the three real processed data files and generates pattern_alerts.json
with 8 alert types, per-alert confidence scores, and AI-explanation fields.

INPUT FILES  (all in pipeline/data/processed/):
  worldbank_indicators.json  — official economic indicators (World Bank Open Data)
  news_signals.json          — GDELT news signals (last 7 days)
  trade_flows.json           — UN Comtrade bilateral trade + dependency scores

OUTPUT FILE:
  pipeline/data/processed/pattern_alerts.json

THE 8 ALERT TYPES
─────────────────
  1. export_stress         Exports declining year-over-year
  2. import_shock          Sudden import surge or collapse straining trade balance
  3. inflation_pressure    CPI high or accelerating
  4. political_risk_rising Conflict / protest / election news spike
  5. trade_dependency_risk Export or import over-concentrated on one partner
  6. regional_spillover    Multiple neighbouring economies under simultaneous stress
  7. fdi_weakness          FDI declining — investor confidence eroding
  8. growth_slowdown       GDP growth decelerating toward contraction

CONFIDENCE SCORING
──────────────────
  Each alert is independently verified against 3 data sources:
    • official_data — World Bank indicator confirms the risk
    • news_signal   — GDELT news coverage corroborates the risk
    • trade_signal  — UN Comtrade flows/dependency supports the risk

  high   = all 3 sources agree
  medium = 2 of 3 sources agree
  low    = only 1 source indicates risk

HOW TO RUN
──────────
  cd pipeline
  python generate_pattern_alerts.py                # normal run (min score = 20)
  python generate_pattern_alerts.py --min-score 30 # stricter threshold
  python generate_pattern_alerts.py --country LAO  # single country (testing)
==============================================================================
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from utils.logger import ok, fail, warn, info, section

# ── Import the existing pattern engine ───────────────────────────────────────
try:
    from pattern_engine import (
        CountrySnapshot,
        AlertResult,
        ALERT_TRIGGER_MIN,
        CONFLICT_NEWS_BASELINE,
        POLITICAL_NEWS_BASELINE,
        REGIONAL_NEIGHBOURS,
        _clip,
        _yoy_pct,
        _severity,
        _display,
        _make_result,
        check_export_stress,
        check_inflation_pressure,
        check_political_instability,
        check_trade_dependency_risk,
        check_regional_spillover,
        check_investment_slowdown,
    )
except ImportError as exc:
    print(f"  ✗  Cannot import pattern_engine.py: {exc}", file=sys.stderr)
    print("     Make sure pattern_engine.py is in the pipeline/ directory.", file=sys.stderr)
    sys.exit(1)


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 1 — FILE PATHS & CONSTANTS
# ══════════════════════════════════════════════════════════════════════════════

PROC_DIR  = SCRIPT_DIR / "data" / "processed"
WB_FILE   = PROC_DIR / "worldbank_indicators.json"
NEWS_FILE = PROC_DIR / "news_signals.json"
TRADE_FILE = PROC_DIR / "trade_flows.json"
OUT_FILE  = PROC_DIR / "pattern_alerts.json"

SEA_REPORTERS: set[str] = {"THA", "VNM", "MMR", "KHM", "LAO", "MYS", "SGP", "IDN", "PHL", "BRN"}

SEA_NAMES: dict[str, str] = {
    "THA": "Thailand",    "VNM": "Vietnam",     "MMR": "Myanmar",
    "KHM": "Cambodia",    "LAO": "Laos",         "MYS": "Malaysia",
    "SGP": "Singapore",   "IDN": "Indonesia",    "PHL": "Philippines",
    "BRN": "Brunei",
}

# Categories that signal political risk in GDELT articles
POLITICAL_RISK_CATS = {"conflict", "election", "politics", "border"}

# Categories that signal trade / economic stress
TRADE_RISK_CATS = {"trade", "tariff", "economy", "infrastructure"}

# Tone threshold: articles below this are considered negative-sentiment
NEGATIVE_TONE_THRESHOLD = -0.20

# News baseline: expected weekly article count per category group (low = benign)
POLITICAL_BASELINE: dict[str, float] = {
    "MMR": 4.0, "THA": 2.5, "PHL": 2.0, "IDN": 1.5, "KHM": 1.5,
    "VNM": 1.0, "MYS": 1.0, "LAO": 0.5, "SGP": 0.5, "BRN": 0.3,
}
TRADE_BASELINE: dict[str, float] = {
    "SGP": 3.0, "MYS": 2.0, "VNM": 2.0, "THA": 2.0, "IDN": 1.5,
    "PHL": 1.5, "KHM": 1.0, "MMR": 1.0, "LAO": 1.0, "BRN": 0.5,
}


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 2 — DATA LOADING
# ══════════════════════════════════════════════════════════════════════════════

def load_worldbank(path: Path) -> dict[str, dict[str, dict[int, float]]]:
    """
    Parse worldbank_indicators.json into a nested dict:
      {iso3: {indicator_key: {year: value}}}

    Only includes SEA reporter countries + partner countries needed for
    regional spillover analysis.
    """
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)

    data: dict[str, dict[str, dict[int, float]]] = {}
    for rec in raw.get("records", []):
        iso3 = rec.get("country_code")
        if not iso3:
            continue
        ind   = rec.get("indicator_key")
        year  = rec.get("year")
        value = rec.get("value")
        if None in (ind, year, value):
            continue
        data.setdefault(iso3, {}).setdefault(ind, {})[year] = value

    return data


def _latest_two(ind_data: dict[str, dict[int, float]], key: str) -> tuple[Optional[float], Optional[float], int]:
    """
    Return (current_value, prev_value, latest_year) for an indicator.
    Skips None / 0 years. Returns (None, None, 0) if not available.
    """
    years_vals = ind_data.get(key, {})
    # Filter to real data (non-None values)
    valid = {yr: v for yr, v in years_vals.items() if v is not None}
    if not valid:
        return None, None, 0
    sorted_years = sorted(valid.keys(), reverse=True)
    latest_year  = sorted_years[0]
    current      = valid[latest_year]
    prev         = valid[sorted_years[1]] if len(sorted_years) > 1 else None
    return current, prev, latest_year


def load_news_signals(
    path: Path,
    today: Optional[datetime] = None,
) -> dict[str, dict]:
    """
    Parse news_signals.json into per-country signal counts.

    Returns {iso3: {
        "7d_political":  int,   # articles in last 7 days tagged political risk
        "7d_trade":      int,   # articles in last 7 days tagged trade/economic
        "7d_conflict":   int,   # articles in last 7 days tagged conflict/border
        "7d_total":      int,   # all articles in last 7 days
        "7d_avg_tone":   float, # average sentiment (-1 to +1)
        "30d_political": int,   # 30-day window (equals 7d if fetch window ≤7d)
        "30d_trade":     int,
        "30d_total":     int,
        "top_categories": list[str],
        "impact_weighted_risk": float,  # sum(impact_score) for risk articles
    }}
    """
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)

    today = today or datetime.now()
    cutoff_7d  = (today - timedelta(days=7)).strftime("%Y-%m-%d")
    cutoff_30d = (today - timedelta(days=30)).strftime("%Y-%m-%d")

    articles = raw.get("articles", [])

    result: dict[str, dict] = {}
    for iso3 in SEA_REPORTERS:
        country_arts = [a for a in articles if a.get("country_code") == iso3]

        def _count(arts: list, cat_set: set, cutoff: str) -> tuple[int, float, float]:
            """Return (count, avg_tone, impact_sum) for articles after cutoff in cat_set."""
            filtered = [
                a for a in arts
                if a.get("date", "") >= cutoff and a.get("category") in cat_set
            ]
            if not filtered:
                return 0, 0.0, 0.0
            avg_tone = sum(a.get("tone", 0.0) for a in filtered) / len(filtered)
            impact   = sum(a.get("impact_score", 0) for a in filtered)
            return len(filtered), avg_tone, impact

        def _total(arts: list, cutoff: str) -> int:
            return sum(1 for a in arts if a.get("date", "") >= cutoff)

        p7, tone_p7, imp_p7 = _count(country_arts, POLITICAL_RISK_CATS, cutoff_7d)
        t7, tone_t7, imp_t7 = _count(country_arts, TRADE_RISK_CATS, cutoff_7d)
        p30, _, _           = _count(country_arts, POLITICAL_RISK_CATS, cutoff_30d)
        t30, _, _           = _count(country_arts, TRADE_RISK_CATS, cutoff_30d)

        conflict_7d = sum(
            1 for a in country_arts
            if a.get("date", "") >= cutoff_7d and a.get("category") in {"conflict", "border"}
        )

        all_7d_arts = [a for a in country_arts if a.get("date", "") >= cutoff_7d]
        avg_tone_overall = (
            sum(a.get("tone", 0.0) for a in all_7d_arts) / len(all_7d_arts)
            if all_7d_arts else 0.0
        )

        # Top categories in last 7 days
        cat_counts: dict[str, int] = {}
        for a in all_7d_arts:
            c = a.get("category", "unknown")
            cat_counts[c] = cat_counts.get(c, 0) + 1
        top_cats = [k for k, _ in sorted(cat_counts.items(), key=lambda x: -x[1])][:3]

        # Also use the pre-computed news_counts (total fetch window)
        nc = raw.get("news_counts", {}).get(iso3, {})

        result[iso3] = {
            "7d_political":        p7,
            "7d_trade":            t7,
            "7d_conflict":         conflict_7d,
            "7d_total":            _total(country_arts, cutoff_7d),
            "7d_avg_tone":         round(avg_tone_overall, 3),
            "7d_political_tone":   round(tone_p7, 3),
            "7d_trade_tone":       round(tone_t7, 3),
            "7d_political_impact": imp_p7,
            "7d_trade_impact":     imp_t7,
            "30d_political":       max(p30, nc.get("political_risk_count", 0)),
            "30d_trade":           max(t30, nc.get("trade_news_count", 0)),
            "30d_total":           max(_total(country_arts, cutoff_30d), nc.get("total_articles", 0)),
            "top_categories":      top_cats,
            "impact_weighted_risk": imp_p7 + imp_t7,
        }

    return result


def load_trade_flows(path: Path) -> dict[str, dict]:
    """
    Parse trade_flows.json into per-country dependency data.

    Returns {iso3: {
        "latest_year": int,
        "exports_b":   float,
        "imports_b":   float,
        "balance_b":   float,
        "prev_exports_b":  float | None,
        "prev_imports_b":  float | None,
        "prev_balance_b":  float | None,
        "top_export_partner":     str,
        "top_export_share_pct":   float,
        "top_import_partner":     str,
        "top_import_share_pct":   float,
        "by_partner":             dict,  # partner → shares
        "high_dependency_partners": list[str],  # partners with risk "high"
    }}
    """
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)

    dependency = raw.get("dependency", {})
    result: dict[str, dict] = {}

    for iso3, years_data in dependency.items():
        if iso3 not in SEA_REPORTERS:
            continue

        all_years = sorted(years_data.keys(), reverse=True)
        if not all_years:
            continue

        latest_yr = all_years[0]
        prev_yr   = all_years[1] if len(all_years) > 1 else None
        latest    = years_data[latest_yr]
        prev      = years_data[prev_yr] if prev_yr else {}

        high_dep = [
            p for p, pdata in latest.get("by_partner", {}).items()
            if pdata.get("dependency_risk") == "high"
        ]
        high_export_dep = [
            p for p, pdata in latest.get("by_partner", {}).items()
            if pdata.get("export_risk") == "high"
        ]
        high_import_dep = [
            p for p, pdata in latest.get("by_partner", {}).items()
            if pdata.get("import_risk") == "high"
        ]

        result[iso3] = {
            "latest_year":            int(latest_yr),
            "exports_b":              latest.get("total_exports_usd_b"),
            "imports_b":              latest.get("total_imports_usd_b"),
            "balance_b":              latest.get("trade_balance_usd_b"),
            "prev_exports_b":         prev.get("total_exports_usd_b"),
            "prev_imports_b":         prev.get("total_imports_usd_b"),
            "prev_balance_b":         prev.get("trade_balance_usd_b"),
            "top_export_partner":     latest.get("top_export_partner"),
            "top_export_share_pct":   latest.get("top_export_share_pct"),
            "top_import_partner":     latest.get("top_import_partner"),
            "top_import_share_pct":   latest.get("top_import_share_pct"),
            "by_partner":             latest.get("by_partner", {}),
            "high_dependency_partners":  high_dep,
            "high_export_dep_partners":  high_export_dep,
            "high_import_dep_partners":  high_import_dep,
        }

    return result


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 3 — SNAPSHOT BUILDER
# ══════════════════════════════════════════════════════════════════════════════

def build_snapshot(
    iso3: str,
    wb: dict[str, dict[int, float]],
    news: dict,
    trade: dict,
) -> CountrySnapshot:
    """
    Build a CountrySnapshot from the three real data sources.

    The CountrySnapshot feeds into pattern_engine.py's alert checks.
    All fields default to None if data is unavailable — the engine degrades
    gracefully and skips sub-checks with missing inputs.
    """
    name = SEA_NAMES.get(iso3, iso3)

    gdp_val,  gdp_prev,  gdp_yr  = _latest_two(wb, "gdpGrowth")
    infl_val, infl_prev, _       = _latest_two(wb, "inflation")
    exp_val,  exp_prev,  _       = _latest_two(wb, "exports")
    imp_val,  imp_prev,  _       = _latest_two(wb, "imports")
    fdi_val,  fdi_prev,  _       = _latest_two(wb, "fdiPctGdp")

    year = gdp_yr or 2023

    return CountrySnapshot(
        iso3 = iso3,
        name = name,
        year = year,

        # Current-year values (World Bank)
        gdp_growth    = gdp_val,
        inflation     = infl_val,
        exports_usd_b = exp_val,
        imports_usd_b = imp_val,
        fdi_usd_b     = fdi_val,

        # Prior-year values (World Bank)
        prev_gdp_growth    = gdp_prev,
        prev_inflation     = infl_prev,
        prev_exports_usd_b = exp_prev,
        prev_imports_usd_b = imp_prev,
        prev_fdi_usd_b     = fdi_prev,

        # News signal counts (GDELT — 7-day window)
        # Use 7d_political for political_risk, 7d_conflict for conflict proxy
        political_risk_news_count   = news.get("30d_political", 0),
        trade_news_count            = news.get("30d_trade", 0),
        conflict_protest_news_count = max(
            news.get("7d_conflict", 0),
            news.get("7d_political", 0),
        ),

        # Trade partner concentration (UN Comtrade)
        top_export_partner       = trade.get("top_export_partner"),
        top_export_partner_share = trade.get("top_export_share_pct"),
        top_import_partner       = trade.get("top_import_partner"),
        top_import_partner_share = trade.get("top_import_share_pct"),
    )


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 4 — NEW ALERT TYPE: IMPORT SHOCK
#
#  Fires when imports are surging or collapsing, creating trade balance stress.
#
#  Score components (0-100):
#    A) Import–export divergence  0-40 pts  (imports growing much faster than exports)
#    B) Trade balance worsening   0-30 pts  (balance moved toward deficit / deficit widened)
#    C) Supply concentration      0-20 pts  (single import partner share > 35%)
#    D) News corroboration        0-10 pts  (tariff/trade news with negative tone)
# ══════════════════════════════════════════════════════════════════════════════

def check_import_shock(
    snap: CountrySnapshot,
    trade: dict,
    news: dict,
) -> AlertResult:
    conditions: list[str] = []
    values: dict = {}
    score = 0.0

    imp_yoy = _yoy_pct(snap.imports_usd_b, snap.prev_imports_usd_b)
    exp_yoy = _yoy_pct(snap.exports_usd_b, snap.prev_exports_usd_b)

    if snap.imports_usd_b:
        values["imports_current_b"] = round(snap.imports_usd_b, 1)
    if snap.prev_imports_usd_b:
        values["imports_prev_b"]    = round(snap.prev_imports_usd_b, 1)
    if imp_yoy is not None:
        values["imports_yoy_pct"] = round(imp_yoy, 1)

    # A) Import–export divergence (0-40 pts)
    if imp_yoy is not None:
        if imp_yoy > 15:
            # Surge: imports outpacing economy
            pts_a = _clip(imp_yoy - 15, 0, 25) / 25 * 40
            score += pts_a
            conditions.append(
                f"Imports surged {imp_yoy:.1f}% YoY — rising faster than domestic production"
            )
        elif imp_yoy < -10:
            # Collapse: supply chain disruption or capital controls
            pts_a = _clip(-imp_yoy - 10, 0, 20) / 20 * 40
            score += pts_a
            conditions.append(
                f"Imports collapsed {abs(imp_yoy):.1f}% YoY — potential supply chain disruption"
            )

    if exp_yoy is not None and imp_yoy is not None:
        divergence = imp_yoy - exp_yoy   # positive = imports growing faster
        values["import_export_divergence_pp"] = round(divergence, 1)
        if divergence > 10 and imp_yoy > 0:
            pts_div = _clip(divergence - 10, 0, 20) / 20 * 15
            score += pts_div
            conditions.append(
                f"Import growth {divergence:.1f}pp faster than exports — trade balance pressure"
            )

    # B) Trade balance worsening (0-30 pts)
    bal_now  = trade.get("balance_b")
    bal_prev = trade.get("prev_balance_b")
    if bal_now is not None:
        values["trade_balance_b"] = round(bal_now, 1)
    if bal_now is not None and bal_prev is not None:
        values["prev_trade_balance_b"] = round(bal_prev, 1)
        delta = bal_now - bal_prev    # negative delta = balance worsened
        values["balance_change_b"] = round(delta, 1)
        if delta < -2:
            pts_b = _clip(-delta - 2, 0, 15) / 15 * 30
            score += pts_b
            conditions.append(
                f"Trade balance deteriorated by ${abs(delta):.1f}B "
                f"(${bal_prev:.1f}B → ${bal_now:.1f}B)"
            )
    elif bal_now is not None and bal_now < -5:
        score += 15
        conditions.append(
            f"Running a structural trade deficit of ${abs(bal_now):.1f}B"
        )

    # C) Single-partner import concentration (0-20 pts)
    imp_share = trade.get("top_import_share_pct")
    imp_partner = trade.get("top_import_partner")
    if imp_share and imp_share > 35:
        pts_c = _clip(imp_share - 35, 0, 25) / 25 * 20
        score += pts_c
        conditions.append(
            f"{imp_share:.0f}% of imports sourced from {imp_partner} "
            f"— supply chain concentration risk"
        )
        values["top_import_partner"] = imp_partner
        values["top_import_share_pct"] = round(imp_share, 1)

    # D) News corroboration (0-10 pts): tariff/trade articles with negative tone
    trade_tone = news.get("7d_trade_tone", 0.0)
    trade_count = news.get("7d_trade", 0)
    if trade_count > 0 and trade_tone < NEGATIVE_TONE_THRESHOLD:
        pts_d = _clip(-trade_tone - NEGATIVE_TONE_THRESHOLD, 0, 0.5) / 0.5 * 10
        score += pts_d
    values["trade_news_7d"] = trade_count
    values["trade_news_tone"] = round(trade_tone, 3)

    score = _clip(score, 0, 100)

    # Explanation
    name = snap.name
    if imp_yoy is not None and imp_yoy > 15:
        expl = (
            f"{name}'s imports jumped {imp_yoy:.1f}% year-over-year to "
            f"${snap.imports_usd_b:.1f}B, outpacing export growth"
        )
        if exp_yoy is not None:
            expl += f" ({exp_yoy:+.1f}% exports)"
        expl += ". This surge is widening the trade deficit and increasing foreign exchange demand."
    elif imp_yoy is not None and imp_yoy < -10:
        expl = (
            f"{name}'s imports fell sharply by {abs(imp_yoy):.1f}% YoY to "
            f"${snap.imports_usd_b:.1f}B, suggesting supply chain disruption, capital controls, "
            f"or a broader economic contraction reducing import demand."
        )
    elif bal_now is not None and bal_now < -5:
        expl = (
            f"{name} is running a persistent trade deficit of ${abs(bal_now):.1f}B, "
            f"creating ongoing foreign exchange demand and vulnerability to external shocks."
        )
    else:
        expl = f"Import trends in {name} warrant monitoring for trade balance pressure."

    if imp_share and imp_share > 35:
        expl += (
            f" With {imp_share:.0f}% of imports sourced from {imp_partner}, "
            f"any disruption to this relationship could create acute supply shortages."
        )

    rec = (
        "Track monthly trade statistics for early signs of balance deterioration. "
        "Monitor tariff announcements and FX reserve levels — a widening deficit requires "
        "more foreign currency to finance."
    )

    return _make_result(
        "import_shock", "Import Shock", "📦", "bar", "imports_usd_b",
        snap, score, conditions, values, expl, rec,
    )


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 5 — NEW ALERT TYPE: GROWTH SLOWDOWN
#
#  Fires when GDP growth is low, decelerating, or at risk of contraction.
#
#  Score components (0-100):
#    A) Absolute growth level     0-40 pts  (<4%→10, <2%→25, <0%→40)
#    B) Deceleration              0-40 pts  (growth fell >1.5pp from prior year)
#    C) Trade drag                0-20 pts  (exports also declining — external demand lost)
# ══════════════════════════════════════════════════════════════════════════════

def check_growth_slowdown(
    snap: CountrySnapshot,
    regional_avg_growth: float,
    news: dict,
) -> AlertResult:
    conditions: list[str] = []
    values: dict = {}
    score = 0.0

    if snap.gdp_growth is None:
        return _make_result(
            "growth_slowdown", "Growth Slowdown", "📉", "line", "gdp_growth_pct",
            snap, 0, [], {}, f"No GDP growth data available for {snap.name}.", "",
        )

    gdp = snap.gdp_growth
    values["gdp_growth_pct"]        = round(gdp, 2)
    values["regional_avg_growth_pct"] = round(regional_avg_growth, 2)

    # A) Absolute growth level (0-40 pts)
    if gdp < 0:
        pts_a = 40
        conditions.append(f"GDP contracted {gdp:.1f}% — economy in recession")
    elif gdp < 1:
        pts_a = 25
        conditions.append(f"GDP growth near stagnation at {gdp:.1f}%")
    elif gdp < 2:
        pts_a = 15
        conditions.append(f"GDP growth weak at {gdp:.1f}% (SEA average: {regional_avg_growth:.1f}%)")
    elif gdp < regional_avg_growth - 2:
        pts_a = 10
        conditions.append(
            f"GDP growth {gdp:.1f}% — underperforming regional average "
            f"by {regional_avg_growth - gdp:.1f}pp"
        )
    else:
        pts_a = 0
    score += pts_a

    # B) Deceleration (0-40 pts): growth rate declining significantly
    if snap.prev_gdp_growth is not None:
        decel = snap.prev_gdp_growth - gdp   # positive = slowing down
        values["gdp_growth_prev_pct"]  = round(snap.prev_gdp_growth, 2)
        values["gdp_deceleration_pp"]  = round(decel, 2)
        if decel > 1.5:
            pts_b = _clip(decel - 1.5, 0, 10.0) / 10.0 * 40
            score += pts_b
            conditions.append(
                f"Growth slowing: decelerated {decel:.1f}pp "
                f"({snap.prev_gdp_growth:.1f}% → {gdp:.1f}%)"
            )
        elif decel > 0.5 and gdp < 3:
            score += 10
            conditions.append(
                f"Moderate growth deceleration ({snap.prev_gdp_growth:.1f}% → {gdp:.1f}%)"
            )

    # C) Trade drag (0-20 pts): export decline signals external demand contraction
    exp_yoy = _yoy_pct(snap.exports_usd_b, snap.prev_exports_usd_b)
    if exp_yoy is not None and exp_yoy < -3:
        pts_c = _clip(-exp_yoy - 3, 0, 15) / 15 * 20
        score += pts_c
        conditions.append(
            f"Export decline ({exp_yoy:.1f}%) compounds growth headwinds — external demand contracting"
        )
        values["export_yoy_pct"] = round(exp_yoy, 1)

    # News corroboration: economy articles with negative tone
    econ_tone = news.get("7d_avg_tone", 0.0)
    econ_count = news.get("7d_total", 0)
    values["economy_news_7d"]   = econ_count
    values["economy_news_tone"] = round(econ_tone, 3)

    score = _clip(score, 0, 100)

    # Explanation
    name = snap.name
    if gdp < 0:
        expl = (
            f"{name}'s economy is contracting at {gdp:.1f}%, placing it in recession. "
            "Falling output reduces government revenue, business investment, and employment, "
            "creating a self-reinforcing cycle of declining demand."
        )
    elif gdp < 2:
        expl = (
            f"{name}'s GDP growth of {gdp:.1f}% is well below the SEA regional average "
            f"of {regional_avg_growth:.1f}%. "
        )
        if snap.prev_gdp_growth and snap.prev_gdp_growth > gdp + 1:
            expl += (
                f"Growth has decelerated sharply from {snap.prev_gdp_growth:.1f}% last year, "
                f"raising concern about a further slowdown or technical recession."
            )
    else:
        expl = (
            f"{name}'s growth of {gdp:.1f}% is slowing from {snap.prev_gdp_growth:.1f}% "
            f"in the prior year"
            if snap.prev_gdp_growth else
            f"{name}'s growth of {gdp:.1f}% is underperforming regional peers."
        )

    if exp_yoy is not None and exp_yoy < 0:
        expl += (
            f" Export contraction of {abs(exp_yoy):.1f}% is reducing the external demand "
            f"contribution to growth."
        )

    rec = (
        "Track high-frequency indicators: PMI, retail sales, industrial output. "
        "Watch for fiscal stimulus announcements — a government may attempt to offset "
        "private sector weakness through public spending."
    )

    return _make_result(
        "growth_slowdown", "Growth Slowdown", "📉", "line", "gdp_growth_pct",
        snap, score, conditions, values, expl, rec,
    )


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 6 — CONFIDENCE SCORING
#
#  For each alert type, evaluate whether each of the 3 data sources independently
#  signals the same risk. The confidence level is high/medium/low based on
#  how many sources agree.
# ══════════════════════════════════════════════════════════════════════════════

def compute_confidence(
    alert_type: str,
    snap: CountrySnapshot,
    wb: dict[str, dict[int, float]],
    news: dict,
    trade: dict,
) -> tuple[str, dict, str]:
    """
    Returns (confidence_level, source_signals, confidence_rationale).

    confidence_level: "high" | "medium" | "low"
    source_signals: {"official_data": bool, "news_signal": bool, "trade_signal": bool}
    confidence_rationale: human-readable explanation
    """

    gdp, gdp_prev, _  = _latest_two(wb, "gdpGrowth")
    infl, infl_prev, _ = _latest_two(wb, "inflation")
    exp, exp_prev, _  = _latest_two(wb, "exports")
    imp, imp_prev, _  = _latest_two(wb, "imports")
    fdi, fdi_prev, _  = _latest_two(wb, "fdiPctGdp")

    exp_yoy = _yoy_pct(exp, exp_prev)
    imp_yoy = _yoy_pct(imp, imp_prev)
    fdi_yoy = _yoy_pct(fdi, fdi_prev)

    pol_news_7d   = news.get("7d_political", 0)
    trade_news_7d = news.get("7d_trade", 0)
    conflict_7d   = news.get("7d_conflict", 0)
    avg_tone      = news.get("7d_avg_tone", 0.0)
    pol_tone      = news.get("7d_political_tone", 0.0)
    trade_tone    = news.get("7d_trade_tone", 0.0)

    top_exp_share = trade.get("top_export_share_pct", 0) or 0
    top_imp_share = trade.get("top_import_share_pct", 0) or 0
    bal           = trade.get("balance_b")
    prev_bal      = trade.get("prev_balance_b")
    high_dep      = trade.get("high_dependency_partners", [])

    official_agrees = False
    news_agrees     = False
    trade_agrees    = False
    rationale_parts: list[str] = []

    if alert_type == "export_stress":
        official_agrees = exp_yoy is not None and exp_yoy < -3
        news_agrees     = trade_news_7d > 0 and trade_tone < NEGATIVE_TONE_THRESHOLD
        trade_agrees    = (
            (trade.get("exports_b") or 0) < (trade.get("prev_exports_b") or float("inf"))
        )
        rationale_parts = [
            f"WB exports YoY: {exp_yoy:.1f}%" if exp_yoy is not None else "WB: no export data",
            f"Trade news 7d: {trade_news_7d} articles (tone {trade_tone:.2f})",
            f"Comtrade: exports {'declining' if trade_agrees else 'not declining'}",
        ]

    elif alert_type == "import_shock":
        official_agrees = imp_yoy is not None and (imp_yoy > 15 or imp_yoy < -10)
        news_agrees     = trade_news_7d > 0 and trade_tone < NEGATIVE_TONE_THRESHOLD
        trade_agrees    = (
            top_imp_share > 35 or
            (bal is not None and prev_bal is not None and bal < prev_bal - 2)
        )
        rationale_parts = [
            f"WB imports YoY: {imp_yoy:.1f}%" if imp_yoy is not None else "WB: no import data",
            f"Trade news 7d: {trade_news_7d} articles (tone {trade_tone:.2f})",
            f"Import concentration: {top_imp_share:.0f}% from {trade.get('top_import_partner', '?')}",
        ]

    elif alert_type == "inflation_pressure":
        official_agrees = (
            (infl is not None and infl > 5) or
            (infl is not None and infl_prev is not None and infl - infl_prev > 3)
        )
        news_agrees     = avg_tone < NEGATIVE_TONE_THRESHOLD and news.get("7d_total", 0) > 1
        trade_agrees    = imp_yoy is not None and imp_yoy > 10  # rising imports → input cost pressure
        rationale_parts = [
            f"WB inflation: {infl:.1f}%" if infl is not None else "WB: no inflation data",
            f"News avg tone 7d: {avg_tone:.2f}  (total: {news.get('7d_total',0)} articles)",
            f"Comtrade imports YoY: {imp_yoy:.1f}%" if imp_yoy is not None else "Comtrade: no data",
        ]

    elif alert_type == "political_risk_rising":
        official_agrees = gdp is not None and gdp < 1.5   # weak economy amplifies political risk
        news_agrees     = (
            pol_news_7d > POLITICAL_BASELINE.get(snap.iso3, 1) * 1.2 or
            conflict_7d > 0
        )
        trade_agrees    = fdi_yoy is not None and fdi_yoy < -5  # investors fleeing political risk
        rationale_parts = [
            f"WB GDP growth: {gdp:.1f}% (political amplifier: low growth)" if gdp is not None else "WB: no GDP data",
            f"Political/conflict news 7d: {pol_news_7d} political, {conflict_7d} conflict",
            f"WB FDI trend: {fdi_yoy:.1f}% YoY" if fdi_yoy is not None else "WB: no FDI data",
        ]

    elif alert_type == "trade_dependency_risk":
        official_agrees = fdi_yoy is not None and fdi_yoy < -5   # lock-in suppresses FDI from others
        news_agrees     = trade_news_7d > TRADE_BASELINE.get(snap.iso3, 1)
        trade_agrees    = top_exp_share > 30 or top_imp_share > 35 or len(high_dep) > 0
        rationale_parts = [
            f"WB FDI trend: {fdi_yoy:.1f}% YoY" if fdi_yoy is not None else "WB: no FDI trend",
            f"Trade news 7d: {trade_news_7d} articles",
            (
                f"Comtrade: exports {top_exp_share:.0f}% to {trade.get('top_export_partner','?')}, "
                f"imports {top_imp_share:.0f}% from {trade.get('top_import_partner','?')}"
            ),
        ]

    elif alert_type == "regional_spillover":
        official_agrees = gdp is not None and gdp < 2.0   # own weakness makes spillover worse
        news_agrees     = (pol_news_7d + trade_news_7d) > 2
        trade_agrees    = len(high_dep) > 0   # trade locked into a stressed partner
        rationale_parts = [
            f"WB GDP growth (own): {gdp:.1f}%" if gdp is not None else "WB: no GDP data",
            f"Regional news activity 7d: {pol_news_7d + trade_news_7d} risk articles",
            f"Comtrade: {len(high_dep)} high-dependency partner(s)",
        ]

    elif alert_type == "fdi_weakness":
        official_agrees = fdi_yoy is not None and fdi_yoy < -5
        news_agrees     = (pol_news_7d > 0 and pol_tone < NEGATIVE_TONE_THRESHOLD)
        trade_agrees    = (
            bal is not None and bal < -5  # structural deficit = less FDI-friendly
        )
        rationale_parts = [
            f"WB FDI % GDP trend: {fdi_yoy:.1f}% YoY" if fdi_yoy is not None else "WB: no FDI data",
            f"Political news 7d: {pol_news_7d} articles (tone {pol_tone:.2f})",
            f"Trade balance: ${bal:.1f}B" if bal is not None else "Comtrade: no balance data",
        ]

    elif alert_type == "growth_slowdown":
        official_agrees = (
            (gdp is not None and gdp < 2) or
            (gdp is not None and gdp_prev is not None and gdp_prev - gdp > 1.5)
        )
        news_agrees     = avg_tone < NEGATIVE_TONE_THRESHOLD and news.get("7d_total", 0) > 0
        trade_agrees    = exp_yoy is not None and exp_yoy < -3  # export decline drags growth
        rationale_parts = [
            f"WB GDP growth: {gdp:.1f}%" if gdp is not None else "WB: no GDP data",
            f"News avg tone: {avg_tone:.2f}",
            f"Comtrade exports YoY: {exp_yoy:.1f}%" if exp_yoy is not None else "Comtrade: no export data",
        ]

    else:
        # Fallback for any unrecognised type
        official_agrees = False
        news_agrees     = False
        trade_agrees    = False
        rationale_parts = ["No confidence logic defined for this alert type."]

    n_agree = sum([official_agrees, news_agrees, trade_agrees])
    level   = "high" if n_agree >= 3 else "medium" if n_agree >= 2 else "low"

    source_signals = {
        "official_data": official_agrees,
        "news_signal":   news_agrees,
        "trade_signal":  trade_agrees,
        "sources_count": n_agree,
    }

    rationale = (
        f"{'✓' if official_agrees else '✗'} Official data (WB): {rationale_parts[0]}. "
        f"{'✓' if news_agrees else '✗'} News signal (GDELT): {rationale_parts[1]}. "
        f"{'✓' if trade_agrees else '✗'} Trade data (Comtrade): {rationale_parts[2]}."
        if len(rationale_parts) == 3
        else " ".join(rationale_parts)
    )

    return level, source_signals, rationale


def build_ai_explanation(
    alert_label: str,
    country_name: str,
    explanation: str,
    confidence: str,
    source_signals: dict,
    confidence_rationale: str,
) -> str:
    """
    Build the 'ai_explanation' field — a rich, multi-source narrative ready
    to display in the dashboard's AI explanation panel.
    """
    agreed = []
    disputed = []
    for src, name in [("official_data", "World Bank data"),
                      ("news_signal", "GDELT news signals"),
                      ("trade_signal", "UN Comtrade flows")]:
        (agreed if source_signals.get(src) else disputed).append(name)

    confidence_phrase = {
        "high":   "HIGH CONFIDENCE — all three data sources agree.",
        "medium": "MEDIUM CONFIDENCE — two of three data sources agree.",
        "low":    "LOW CONFIDENCE — only one data source indicates this risk.",
    }[confidence]

    ai_expl = f"**{alert_label} — {country_name}**\n\n"
    ai_expl += explanation + "\n\n"
    ai_expl += f"**Confidence: {confidence_phrase}**\n"

    if agreed:
        ai_expl += f"Supporting sources: {', '.join(agreed)}. "
    if disputed:
        ai_expl += f"Not corroborated by: {', '.join(disputed)}."
    ai_expl += f"\n\n*Data cross-check:* {confidence_rationale}"

    return ai_expl


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 7 — MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate pattern_alerts.json from real processed data"
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
    print("║   SEA Dashboard — Generate Pattern Alerts (Real Data)       ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()

    # ── Step 1: Load all three data sources ──────────────────────────────────
    section("Step 1 — Load data sources")

    for label, path in [("WB indicators", WB_FILE), ("News signals", NEWS_FILE), ("Trade flows", TRADE_FILE)]:
        if not path.exists():
            fail(f"{label} file not found: {path}")
            fail("Run the full pipeline first: python run_pipeline.py")
            return 1

    wb_records = load_worldbank(WB_FILE)
    ok(f"World Bank: {len(wb_records)} countries  |  {WB_FILE.name}")

    today = datetime.now()
    news_by_country = load_news_signals(NEWS_FILE, today)
    n_articles = sum(v.get("7d_total", 0) for v in news_by_country.values())
    ok(f"News signals: {n_articles} articles (last 7d)  |  {NEWS_FILE.name}")

    trade_by_country = load_trade_flows(TRADE_FILE)
    ok(f"Trade flows:  {len(trade_by_country)} countries  |  {TRADE_FILE.name}")
    print()

    # ── Step 2: Build country snapshots ──────────────────────────────────────
    section("Step 2 — Build country snapshots from real data")

    snapshots: list[CountrySnapshot] = []
    wb_entries:    dict[str, dict] = {}   # iso3 → {indicator: {year: value}}
    news_entries:  dict[str, dict] = {}
    trade_entries: dict[str, dict] = {}
    snap_errors = 0

    targets = {
        iso3 for iso3 in SEA_REPORTERS
        if only_iso3 is None or iso3 == only_iso3
    }

    for iso3 in sorted(targets):
        try:
            wb    = wb_records.get(iso3, {})
            news  = news_by_country.get(iso3, {})
            trade = trade_by_country.get(iso3, {})

            snap = build_snapshot(iso3, wb, news, trade)
            snapshots.append(snap)

            wb_entries[iso3]    = wb
            news_entries[iso3]  = news
            trade_entries[iso3] = trade

            gdp_str = f"gdp={snap.gdp_growth:.1f}%"  if snap.gdp_growth  is not None else "gdp=n/a"
            cpi_str = f"cpi={snap.inflation:.1f}%"   if snap.inflation   is not None else "cpi=n/a"
            pol_str = f"news_pol={news.get('7d_political',0)}"
            trd_str = f"trade_dep={trade.get('top_export_share_pct',0):.0f}%"
            info(f"  {iso3:4s}  {snap.name:<14} yr={snap.year}  {gdp_str}  {cpi_str}  {pol_str}  {trd_str}")

        except Exception as exc:
            snap_errors += 1
            fail(f"  {iso3}: snapshot build failed — {exc}")

    ok(f"Built {len(snapshots)} snapshots  ({snap_errors} errors)")

    if not snapshots:
        fail("No snapshots built — cannot continue.")
        return 1

    # ── Step 3: Compute regional average growth (for growth_slowdown) ─────────
    growth_values = [s.gdp_growth for s in snapshots if s.gdp_growth is not None]
    regional_avg_growth = sum(growth_values) / len(growth_values) if growth_values else 3.5
    info(f"  Regional average GDP growth: {regional_avg_growth:.2f}%")
    print()

    # ── Step 4: Run all 8 alert checks ───────────────────────────────────────
    section("Step 4 — Run 8-type pattern alert engine")

    peer_map = {s.iso3: s for s in snapshots}
    all_results: list[dict] = []

    ALERT_RENAME = {
        "political_instability": "political_risk_rising",
        "investment_slowdown":   "fdi_weakness",
    }
    LABEL_RENAME = {
        "Political Instability Rising": "Political Risk Rising",
        "Investment Slowdown":          "FDI Weakness",
    }

    for snap in snapshots:
        wb    = wb_entries[snap.iso3]
        news  = news_entries[snap.iso3]
        trade = trade_entries[snap.iso3]

        # Run 6 existing checks + 2 new ones
        check_results: list[AlertResult] = [
            check_export_stress(snap),
            check_import_shock(snap, trade, news),
            check_inflation_pressure(snap),
            check_political_instability(snap),
            check_investment_slowdown(snap),
            check_trade_dependency_risk(snap),
            check_regional_spillover(snap, peer_map),
            check_growth_slowdown(snap, regional_avg_growth, news),
        ]

        for result in check_results:
            # Rename alert types and labels
            alert_type  = ALERT_RENAME.get(result.alert_type, result.alert_type)
            alert_label = LABEL_RENAME.get(result.alert_label, result.alert_label)

            # Compute confidence score
            confidence, source_signals, conf_rationale = compute_confidence(
                alert_type, snap, wb, news, trade,
            )

            # Build AI explanation
            ai_expl = build_ai_explanation(
                alert_label, snap.name,
                result.explanation, confidence,
                source_signals, conf_rationale,
            )

            # Convert to dict and enrich
            d = asdict(result)
            d["alert_type"]          = alert_type
            d["alert_label"]         = alert_label
            d["alert_id"]            = f"{alert_type}_{snap.iso3}_{snap.year}"
            d["confidence"]          = confidence
            d["source_signals"]      = source_signals
            d["confidence_rationale"] = conf_rationale
            d["ai_explanation"]      = ai_expl
            d["data_sources_used"]   = [
                f"World Bank {snap.year}",
                f"GDELT 7-day (as of {today.strftime('%Y-%m-%d')})",
                f"UN Comtrade {trade.get('latest_year', snap.year)}",
            ]
            d["generated_at"]        = today.isoformat(timespec="seconds")

            all_results.append(d)

    ok(f"Engine complete: {len(all_results)} raw results")
    print()

    # ── Step 5: Filter and sort ───────────────────────────────────────────────
    section("Step 5 — Filter and summarise")

    triggered = [
        r for r in all_results
        if r["triggered"] and r["score"] >= args.min_score
    ]

    sev_order = {"critical": 0, "warning": 1, "info": 2, "none": 3}
    triggered.sort(key=lambda r: (sev_order.get(r["severity"], 9), -r["score"]))

    info(f"Triggered alerts (score ≥ {args.min_score}): {len(triggered)}")

    icons = {"critical": "🔴", "warning": "🟡", "info": "🔵"}
    conf_icons = {"high": "●●●", "medium": "●●○", "low": "●○○"}
    sev_buckets: dict[str, list] = {"critical": [], "warning": [], "info": []}
    for r in triggered:
        s = r["severity"]
        if s in sev_buckets:
            sev_buckets[s].append(r)

    for sev, alerts in sev_buckets.items():
        if alerts:
            info(f"  {icons[sev]} {sev.upper():<8}: {len(alerts)} alert(s)")
            for r in alerts[:4]:
                conf = conf_icons.get(r.get("confidence", "low"), "●○○")
                info(
                    f"   {r['country_iso3']} — {r['alert_label']:<30} "
                    f"score={r['score']:5.1f}  conf={conf}"
                )
            if len(alerts) > 4:
                info(f"   … and {len(alerts) - 4} more")
    print()

    # ── Step 6: Build output with index views ─────────────────────────────────
    section("Step 6 — Build output structure")

    by_country:  dict[str, list] = {}
    by_type:     dict[str, list] = {}
    by_severity: dict[str, list] = {"critical": [], "warning": [], "info": []}
    by_confidence: dict[str, list] = {"high": [], "medium": [], "low": []}

    for r in triggered:
        iso3 = r["country_iso3"]
        atype = r["alert_type"]
        sev   = r["severity"]
        conf  = r.get("confidence", "low")

        by_country.setdefault(iso3, []).append(r)
        by_type.setdefault(atype, []).append(r)
        if sev in by_severity:
            by_severity[sev].append(r)
        if conf in by_confidence:
            by_confidence[conf].append(r)

    output = {
        "meta": {
            "generated_at":        today.isoformat(timespec="seconds"),
            "script":              "generate_pattern_alerts.py",
            "data_sources": {
                "official_data": f"World Bank Open Data  ({WB_FILE.name})",
                "news_signal":   f"GDELT 2.0 Document API  ({NEWS_FILE.name})",
                "trade_signal":  f"UN Comtrade / WTO Statistics  ({TRADE_FILE.name})",
            },
            "total_checks":       len(all_results),
            "triggered_alerts":   len(triggered),
            "critical":           len(by_severity["critical"]),
            "warnings":           len(by_severity["warning"]),
            "info_count":         len(by_severity["info"]),
            "high_confidence":    len(by_confidence["high"]),
            "medium_confidence":  len(by_confidence["medium"]),
            "low_confidence":     len(by_confidence["low"]),
            "countries_checked":  len(snapshots),
            "regional_avg_growth": round(regional_avg_growth, 2),
            "min_score_filter":   args.min_score,
            "news_window_days":   7,
            "alert_types": [
                "export_stress", "import_shock", "inflation_pressure",
                "political_risk_rising", "trade_dependency_risk",
                "regional_spillover", "fdi_weakness", "growth_slowdown",
            ],
            "confidence_methodology": (
                "Each alert is independently verified against 3 data sources: "
                "World Bank (official_data), GDELT (news_signal), UN Comtrade (trade_signal). "
                "high = all 3 agree, medium = 2 agree, low = 1 agrees."
            ),
            "refresh_note": (
                "Run 'python run_pipeline.py' to refresh all data and regenerate alerts."
            ),
        },
        "alerts":       triggered,
        "all_results":  [r for r in all_results if r["score"] >= 5],  # low-score shelf
        "by_country":   by_country,
        "by_type":      by_type,
        "by_severity":  by_severity,
        "by_confidence": by_confidence,
    }

    # ── Step 7: Save ──────────────────────────────────────────────────────────
    PROC_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with open(OUT_FILE, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        size_kb = OUT_FILE.stat().st_size // 1024
        ok(f"Saved → {OUT_FILE.name}  ({size_kb} KB)")
    except Exception as exc:
        fail(f"Could not save output: {exc}")
        return 1

    # ── Final summary ─────────────────────────────────────────────────────────
    print()
    print("━" * 62)
    ok("generate_pattern_alerts.py complete")
    ok(f"  {len(triggered)} triggered alerts  "
       f"({len(by_severity['critical'])} critical, "
       f"{len(by_severity['warning'])} warnings, "
       f"{len(by_severity['info'])} info)")
    ok(f"  Confidence: {len(by_confidence['high'])} high, "
       f"{len(by_confidence['medium'])} medium, "
       f"{len(by_confidence['low'])} low")
    info(f"  Output: {OUT_FILE}")
    print("━" * 62)
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
