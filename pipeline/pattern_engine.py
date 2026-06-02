#!/usr/bin/env python3
"""
pattern_engine.py — Rule-based economic & political pattern detection
SEA Economic & Political Change Dashboard

Detects 8 alert types from economic indicators + GDELT news signals.
Each alert computes a composite score (0-100), assigns a severity level,
lists which conditions were met, and produces a human-readable explanation
ready to display in the dashboard.

Alert types
───────────
  1. export_stress          Export volume falling + trade balance deteriorating
  2. inflation_pressure     CPI high or accelerating, real growth turning negative
  3. political_instability  Conflict/protest news spike, governance risk elevated
  4. currency_pressure      Exchange rate depreciating + inflation compounding risk
  5. investment_slowdown    FDI declining + high debt + political uncertainty
  6. trade_dependency_risk  Export or import over-concentrated on single partner
  7. tourism_recovery       Arrivals still below pre-COVID baseline or reversing
  8. regional_spillover     Multiple neighbours simultaneously under economic stress

Usage
─────
  python pipeline/pattern_engine.py                    # run on built-in sample data
  python pipeline/pattern_engine.py --country MMR      # single country
  python pipeline/pattern_engine.py --output json      # write alerts JSON
  python pipeline/pattern_engine.py --output csv       # write alerts CSV
  python pipeline/pattern_engine.py --threshold 40     # only show score >= 40

Import
──────
  from pipeline.pattern_engine import CountrySnapshot, run_all_alerts
  alerts = run_all_alerts(snapshot, peer_snapshots)
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass, field, asdict
from datetime import date
from pathlib import Path
from typing import Optional

OUTPUT_DIR = Path("pipeline/output")

# ─────────────────────────────────────────────────────────────────────────────
# COUNTRY BASELINES
# ─────────────────────────────────────────────────────────────────────────────

# Expected weekly conflict/protest article count under normal conditions
# Myanmar baseline is intentionally elevated — post-coup state is the new normal
CONFLICT_NEWS_BASELINE: dict[str, float] = {
    "MMR": 18.0,  "PHL": 7.0, "THA": 5.0, "IDN": 5.0, "KHM": 4.0,
    "VNM": 3.0,   "MYS": 3.0, "LAO": 2.0, "SGP": 1.0, "BRN": 0.5,
}

POLITICAL_NEWS_BASELINE: dict[str, float] = {
    "MMR": 12.0,  "THA": 7.0, "PHL": 6.0, "IDN": 5.0, "MYS": 4.0,
    "KHM": 4.0,   "VNM": 3.0, "SGP": 2.0, "LAO": 2.0, "BRN": 1.0,
}

# Reference exchange rate (local currency per USD, circa 2020 stable period)
# Positive depreciation_pct = local currency weakened (buys fewer USD)
EXCHANGE_RATE_BASELINE: dict[str, float] = {
    "THA": 31.3,   "VNM": 23200.0, "MMR": 1330.0, "KHM": 4070.0,
    "MYS": 4.20,   "SGP": 1.38,    "IDN": 14100.0, "PHL": 50.7,
    "LAO": 9400.0, "BRN": 1.38,
}

# Pre-COVID tourism arrivals, 2019 (millions of international visitors)
TOURISM_2019_BASELINE: dict[str, float] = {
    "THA": 39.8, "VNM": 18.0, "IDN": 16.1, "MYS": 26.1, "SGP": 19.1,
    "PHL": 8.3,  "KHM": 6.6,  "MMR": 4.4,  "LAO": 4.8,  "BRN": 0.3,
}

# Geographic neighbours for spillover analysis
REGIONAL_NEIGHBOURS: dict[str, list[str]] = {
    "THA": ["MMR", "LAO", "KHM", "MYS"],
    "VNM": ["LAO", "KHM"],
    "MMR": ["THA", "LAO"],
    "KHM": ["THA", "VNM", "LAO"],
    "LAO": ["THA", "VNM", "KHM", "MMR"],
    "MYS": ["THA", "IDN", "SGP"],
    "SGP": ["MYS", "IDN"],
    "IDN": ["SGP", "MYS", "PHL"],
    "PHL": ["IDN"],
    "BRN": ["MYS"],
}

# Severity thresholds per alert type (score ranges: info / warning / critical)
THRESHOLDS: dict[str, tuple[float, float]] = {
    # (warning_min, critical_min)
    "export_stress":         (40.0, 65.0),
    "inflation_pressure":    (38.0, 62.0),
    "political_instability": (35.0, 60.0),
    "currency_pressure":     (38.0, 65.0),
    "investment_slowdown":   (38.0, 62.0),
    "trade_dependency_risk": (40.0, 65.0),
    "tourism_recovery":      (30.0, 58.0),
    "regional_spillover":    (30.0, 55.0),
}

# Minimum score to fire any alert
ALERT_TRIGGER_MIN = 20.0

# ─────────────────────────────────────────────────────────────────────────────
# DATA STRUCTURES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CountrySnapshot:
    """
    All indicator values for one country in one year.
    Pass None for any field that is unavailable — the engine degrades gracefully.
    """
    iso3: str
    name: str
    year: int

    # Economic indicators (current year)
    gdp_growth: Optional[float]           = None   # % annual real growth
    inflation: Optional[float]            = None   # % annual CPI change
    exports_usd_b: Optional[float]        = None   # USD billions
    imports_usd_b: Optional[float]        = None   # USD billions
    exchange_rate: Optional[float]        = None   # local currency per 1 USD
    fdi_usd_b: Optional[float]           = None   # USD billions net inflows
    public_debt_pct_gdp: Optional[float]  = None   # % of GDP

    # Prior-year values (for YoY calculations)
    prev_gdp_growth: Optional[float]      = None
    prev_inflation: Optional[float]       = None
    prev_exports_usd_b: Optional[float]   = None
    prev_imports_usd_b: Optional[float]   = None
    prev_exchange_rate: Optional[float]   = None
    prev_fdi_usd_b: Optional[float]      = None

    # GDELT news signal counts (last 30 days)
    political_risk_news_count: int        = 0
    trade_news_count: int                 = 0
    conflict_protest_news_count: int      = 0

    # Trade partner concentration (from IMF DOTS / Comtrade module)
    top_export_partner: Optional[str]          = None   # ISO3
    top_export_partner_share: Optional[float]  = None   # % of total exports
    top_import_partner: Optional[str]          = None   # ISO3
    top_import_partner_share: Optional[float]  = None   # % of total imports

    # Tourism (optional — from World Bank / national stats)
    tourism_arrivals_m: Optional[float]    = None   # millions of arrivals
    prev_tourism_arrivals_m: Optional[float] = None


@dataclass
class AlertResult:
    """Output of a single alert check."""
    alert_id: str                # "{type}_{iso3}_{year}"
    alert_type: str              # snake_case identifier
    alert_label: str             # human-readable name
    country_iso3: str
    country_name: str
    year: int
    triggered: bool              # True if score >= ALERT_TRIGGER_MIN
    score: float                 # 0-100 composite score
    severity: str                # "none" | "info" | "warning" | "critical"
    conditions_met: list[str]    = field(default_factory=list)
    values_used: dict            = field(default_factory=dict)
    explanation: str             = ""
    recommendation: str          = ""
    # Dashboard display metadata
    color: str                   = "#6B7280"    # Tailwind slate-500
    bg_color: str                = "#F9FAFB"
    icon: str                    = "📊"
    severity_class: str          = "none"       # maps to CSS class
    chart_hint: str              = "line"       # "line"|"bar"|"gauge"|"heatmap"
    metric_to_highlight: str     = ""


# ─────────────────────────────────────────────────────────────────────────────
# HELPER FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def _clip(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))

def _yoy_pct(current: Optional[float], previous: Optional[float]) -> Optional[float]:
    """Return year-over-year % change, or None if either value is missing/zero."""
    if current is None or previous is None or previous == 0:
        return None
    return (current - previous) / abs(previous) * 100

def _severity(score: float, alert_type: str) -> str:
    warn_min, crit_min = THRESHOLDS.get(alert_type, (40.0, 65.0))
    if score >= crit_min:
        return "critical"
    if score >= warn_min:
        return "warning"
    if score >= ALERT_TRIGGER_MIN:
        return "info"
    return "none"

def _display(severity: str) -> tuple[str, str, str]:
    """Return (color, bg_color, severity_class) for a severity level."""
    return {
        "critical": ("#DC2626", "#FEF2F2", "sev-critical"),
        "warning":  ("#D97706", "#FFFBEB", "sev-warning"),
        "info":     ("#2563EB", "#EFF6FF", "sev-info"),
        "none":     ("#6B7280", "#F9FAFB", "sev-none"),
    }[severity]

def _make_result(
    alert_type: str,
    label: str,
    icon: str,
    chart_hint: str,
    metric: str,
    snap: CountrySnapshot,
    score: float,
    conditions: list[str],
    values: dict,
    explanation: str,
    recommendation: str,
) -> AlertResult:
    score   = round(_clip(score, 0.0, 100.0), 1)
    sev     = _severity(score, alert_type)
    color, bg, sev_class = _display(sev)
    return AlertResult(
        alert_id          = f"{alert_type}_{snap.iso3}_{snap.year}",
        alert_type        = alert_type,
        alert_label       = label,
        country_iso3      = snap.iso3,
        country_name      = snap.name,
        year              = snap.year,
        triggered         = score >= ALERT_TRIGGER_MIN,
        score             = score,
        severity          = sev,
        conditions_met    = conditions,
        values_used       = values,
        explanation       = explanation,
        recommendation    = recommendation,
        color             = color,
        bg_color          = bg,
        icon              = icon,
        severity_class    = sev_class,
        chart_hint        = chart_hint,
        metric_to_highlight = metric,
    )

# ─────────────────────────────────────────────────────────────────────────────
# ALERT 1 — EXPORT STRESS
#
# Fires when: exports are declining meaningfully year-over-year,
#             or the trade balance is deteriorating.
#
# Score components (0-100):
#   A) YoY export decline    0-60 pts  (-5%→15, -10%→30, -20%→60)
#   B) Balance worsening     0-25 pts  (deficit growing as % of prior exports)
#   C) Consecutive decline   0-15 pts  (each additional year adds 7.5 pts)
# ─────────────────────────────────────────────────────────────────────────────

def check_export_stress(snap: CountrySnapshot) -> AlertResult:
    conditions: list[str] = []
    values: dict = {}
    score = 0.0

    export_yoy  = _yoy_pct(snap.exports_usd_b, snap.prev_exports_usd_b)
    balance_now = (
        (snap.exports_usd_b or 0) - (snap.imports_usd_b or 0)
        if snap.exports_usd_b and snap.imports_usd_b else None
    )
    balance_prev = (
        (snap.prev_exports_usd_b or 0) - (snap.prev_imports_usd_b or 0)
        if snap.prev_exports_usd_b and snap.prev_imports_usd_b else None
    )

    # A) Export YoY decline (0-60 pts)
    if export_yoy is not None:
        values["export_yoy_pct"] = round(export_yoy, 1)
        if export_yoy < -3:
            pts_a = _clip(-export_yoy - 3, 0, 20) / 20 * 60
            score += pts_a
            conditions.append(
                f"Exports fell {abs(export_yoy):.1f}% YoY "
                f"(${snap.prev_exports_usd_b:.1f}B → ${snap.exports_usd_b:.1f}B)"
            )

    # B) Trade balance worsening (0-25 pts)
    if balance_now is not None and balance_prev is not None and snap.prev_exports_usd_b:
        balance_delta = balance_now - balance_prev
        delta_pct = -balance_delta / snap.prev_exports_usd_b * 100  # positive = worsening
        if delta_pct > 2:
            pts_b = _clip(delta_pct - 2, 0, 15) / 15 * 25
            score += pts_b
            direction = "deficit widened" if balance_delta < 0 else "surplus narrowed"
            conditions.append(
                f"Trade balance {direction} by ${abs(balance_delta):.1f}B"
            )
        values["trade_balance_usd_b"] = round(balance_now, 1)
        values["prev_trade_balance_usd_b"] = round(balance_prev, 1)

    # C) Consecutive decline years (0-15 pts): simple proxy — add 1 if prev also fell
    if export_yoy is not None and export_yoy < 0:
        prev_prev_yoy = _yoy_pct(snap.prev_exports_usd_b, snap.prev_imports_usd_b)
        # Can't truly compute multi-year without more history; flag single year as base
        consec = 1
        pts_c = min(consec * 7.5, 15)
        score += pts_c

    values["exports_current"] = snap.exports_usd_b
    values["exports_prev"]    = snap.prev_exports_usd_b

    # Explanation
    if export_yoy is not None and export_yoy < 0:
        cause = (
            "political disruptions impacting supply chains"
            if snap.conflict_protest_news_count > CONFLICT_NEWS_BASELINE.get(snap.iso3, 5) * 1.5
            else "weakening external demand"
        )
        expl = (
            f"{snap.name}'s exports declined {abs(export_yoy):.1f}% year-over-year "
            f"from ${snap.prev_exports_usd_b:.1f}B to ${snap.exports_usd_b:.1f}B, "
            f"consistent with {cause}."
        )
        if balance_now is not None and balance_now < 0:
            expl += f" The country is running a trade deficit of ${abs(balance_now):.1f}B."
    else:
        expl = f"{snap.name}'s export growth is slowing or data is limited."

    rec = (
        "Track Q1 forward export orders and shipping volumes. "
        "Check whether key export partners (especially China/USA) have reduced import demand."
    )

    return _make_result(
        "export_stress", "Export Stress", "📉", "line", "exports_usd_b",
        snap, score, conditions, values, expl, rec,
    )


# ─────────────────────────────────────────────────────────────────────────────
# ALERT 2 — INFLATION PRESSURE
#
# Fires when: CPI is high (>5%) and/or accelerating,
#             especially when real GDP growth turns negative.
#
# Score components (0-100):
#   A) Absolute CPI level     0-40 pts  (2%=0, 12%=20, 32%=40)
#   B) Acceleration           0-30 pts  (inflation rising >3pp YoY)
#   C) Real GDP negative      0-20 pts  (gdp_growth < inflation → +20)
#   D) Debt amplifier         0-10 pts  (debt >70% GDP → limited policy space)
# ─────────────────────────────────────────────────────────────────────────────

def check_inflation_pressure(snap: CountrySnapshot) -> AlertResult:
    conditions: list[str] = []
    values: dict = {}
    score = 0.0

    if snap.inflation is None:
        return _make_result(
            "inflation_pressure", "Inflation Pressure", "🔥", "line", "inflation_pct",
            snap, 0, [], {}, f"No inflation data available for {snap.name}.", "",
        )

    infl = snap.inflation
    values["inflation_pct"] = round(infl, 1)

    # A) Absolute level (0-40 pts): floor at 2%, ceiling at 32%
    pts_a = _clip(infl - 2.0, 0, 30) / 30 * 40
    score += pts_a
    if infl > 5:
        conditions.append(f"Inflation at {infl:.1f}% (target band: 2–4%)")

    # B) Acceleration (0-30 pts): rising >3pp vs prior year
    infl_yoy = _yoy_pct(snap.inflation, snap.prev_inflation)
    if snap.prev_inflation is not None:
        delta = infl - snap.prev_inflation
        values["inflation_change_pp"] = round(delta, 1)
        if delta > 2:
            pts_b = _clip(delta - 2, 0, 15) / 15 * 30
            score += pts_b
            conditions.append(f"Inflation accelerating (+{delta:.1f}pp vs prior year)")

    # C) Real GDP negative (0-20 pts): economy shrinking in real terms
    if snap.gdp_growth is not None:
        real_growth = snap.gdp_growth - infl
        values["real_gdp_growth_pct"] = round(real_growth, 1)
        if real_growth < 0:
            pts_c = _clip(-real_growth, 0, 20) / 20 * 20
            score += pts_c
            conditions.append(
                f"Real GDP growth negative ({snap.gdp_growth:.1f}% − {infl:.1f}% = {real_growth:.1f}%)"
            )

    # D) Debt amplifier (0-10 pts): high debt limits central bank options
    if snap.public_debt_pct_gdp is not None and snap.public_debt_pct_gdp > 70:
        pts_d = _clip(snap.public_debt_pct_gdp - 70, 0, 30) / 30 * 10
        score += pts_d
        conditions.append(
            f"Public debt {snap.public_debt_pct_gdp:.0f}% of GDP limits monetary policy space"
        )
        values["public_debt_pct_gdp"] = snap.public_debt_pct_gdp

    # Explanation
    level_word = (
        "hyperinflationary" if infl > 25
        else "severely elevated" if infl > 15
        else "high" if infl > 8
        else "above-target"
    )
    expl = (
        f"{snap.name} is experiencing {level_word} inflation at {infl:.1f}%. "
    )
    if snap.gdp_growth is not None and snap.gdp_growth < infl:
        expl += (
            f"With nominal GDP growth of {snap.gdp_growth:.1f}%, real purchasing power "
            f"is contracting by {snap.gdp_growth - infl:.1f}pp, squeezing households and businesses. "
        )
    if snap.prev_inflation and infl > snap.prev_inflation + 2:
        expl += f"Inflation has accelerated from {snap.prev_inflation:.1f}% last year, suggesting the trend is worsening."

    rec = (
        "Monitor central bank policy rate decisions and currency reserves. "
        "Check food/fuel price components — these are most likely driving the spike in SEA context."
    )

    return _make_result(
        "inflation_pressure", "Inflation Pressure", "🔥", "line", "inflation_pct",
        snap, score, conditions, values, expl, rec,
    )


# ─────────────────────────────────────────────────────────────────────────────
# ALERT 3 — POLITICAL INSTABILITY RISING
#
# Fires when: conflict/protest news has spiked above baseline,
#             or political risk news count is elevated.
#
# Score components (0-100):
#   A) Conflict news spike    0-50 pts  (ratio vs baseline: 1x=0, 2x=17, 4x=50)
#   B) Absolute volume        0-30 pts  (raw count regardless of baseline)
#   C) Economic amplifier     0-20 pts  (low GDP growth makes instability more damaging)
# ─────────────────────────────────────────────────────────────────────────────

def check_political_instability(snap: CountrySnapshot) -> AlertResult:
    conditions: list[str] = []
    values: dict = {}
    score = 0.0

    conflict_count = snap.conflict_protest_news_count
    political_count = snap.political_risk_news_count
    baseline_c = CONFLICT_NEWS_BASELINE.get(snap.iso3, 5.0)
    baseline_p = POLITICAL_NEWS_BASELINE.get(snap.iso3, 4.0)

    values["conflict_protest_news"] = conflict_count
    values["political_risk_news"]   = political_count
    values["conflict_baseline"]     = baseline_c

    # A) Conflict news spike ratio (0-50 pts)
    if conflict_count > 0:
        spike_ratio = conflict_count / baseline_c
        pts_a = _clip(spike_ratio - 1.0, 0, 3.0) / 3.0 * 50
        score += pts_a
        if spike_ratio > 1.3:
            conditions.append(
                f"Conflict/protest news at {conflict_count} articles "
                f"({spike_ratio:.1f}× baseline of {baseline_c:.0f})"
            )

    # Political risk news also contributes
    if political_count > 0:
        pol_spike = political_count / baseline_p
        pts_pol = _clip(pol_spike - 1.0, 0, 2.0) / 2.0 * 15
        score += pts_pol
        if pol_spike > 1.5:
            conditions.append(
                f"Political risk news elevated: {political_count} articles "
                f"({pol_spike:.1f}× baseline)"
            )

    # B) Absolute volume (0-30 pts): even at baseline ratio, very high volume matters
    pts_b = _clip(conflict_count, 0, 30) / 30 * 30
    score = max(score, pts_b)  # take max, not sum — avoid double-counting volume

    # C) Economic amplifier (0-20 pts): instability is more damaging in a weak economy
    if snap.gdp_growth is not None:
        if snap.gdp_growth < 0:
            pts_c = 20
            conditions.append(
                f"Economic contraction ({snap.gdp_growth:.1f}% GDP) amplifies instability risk"
            )
        elif snap.gdp_growth < 2:
            pts_c = 10
            conditions.append(
                f"Sluggish growth ({snap.gdp_growth:.1f}%) reduces resilience to political shocks"
            )
        else:
            pts_c = 0
        score += pts_c
        values["gdp_growth_pct"] = snap.gdp_growth

    score = _clip(score, 0, 100)

    # Explanation
    spike_word = (
        "extreme" if conflict_count > baseline_c * 3
        else "significant" if conflict_count > baseline_c * 2
        else "notable" if conflict_count > baseline_c * 1.3
        else "modest"
    )
    expl = (
        f"{snap.name} is showing a {spike_word} spike in conflict and protest-related news "
        f"({conflict_count} articles vs baseline of {baseline_c:.0f}). "
    )
    if snap.gdp_growth is not None and snap.gdp_growth < 1:
        expl += (
            f"With GDP growth at {snap.gdp_growth:.1f}%, the economy has limited buffer "
            f"to absorb political disruption. "
        )
    if snap.iso3 == "MMR":
        expl += "Note: Myanmar's baseline is already elevated post-coup; spikes above this indicate further escalation."

    rec = (
        "Cross-reference with specific event categories (election, coup, protest). "
        "Check whether economic zones or export corridors are in affected regions."
    )

    return _make_result(
        "political_instability", "Political Instability Rising", "⚡", "bar",
        "conflict_protest_news_count", snap, score, conditions, values, expl, rec,
    )


# ─────────────────────────────────────────────────────────────────────────────
# ALERT 4 — CURRENCY PRESSURE
#
# Fires when: local currency has depreciated significantly vs 2020 reference,
#             compounded by high inflation and/or a trade deficit.
#
# Score components (0-100):
#   A) Depreciation magnitude   0-50 pts  (+5%=12, +15%=37, +25%=50)
#   B) Inflation amplifier      0-25 pts  (high CPI → imported goods get costlier)
#   C) Import deficit exposure  0-25 pts  (deficit → more USD needed per period)
# ─────────────────────────────────────────────────────────────────────────────

def check_currency_pressure(snap: CountrySnapshot) -> AlertResult:
    conditions: list[str] = []
    values: dict = {}
    score = 0.0

    if snap.exchange_rate is None:
        return _make_result(
            "currency_pressure", "Currency Pressure", "💱", "line", "exchange_rate",
            snap, 0, [], {}, f"No exchange rate data for {snap.name}.", "",
        )

    ref_rate = EXCHANGE_RATE_BASELINE.get(snap.iso3)
    if ref_rate is None:
        return _make_result(
            "currency_pressure", "Currency Pressure", "💱", "line", "exchange_rate",
            snap, 0, [], {}, f"No baseline exchange rate configured for {snap.name}.", "",
        )

    # Depreciation: positive = local currency weakened (takes more units to buy 1 USD)
    depr_pct = (snap.exchange_rate - ref_rate) / ref_rate * 100
    values["exchange_rate"]         = snap.exchange_rate
    values["exchange_rate_baseline"] = ref_rate
    values["depreciation_pct"]      = round(depr_pct, 1)

    # YoY change if prior year available
    if snap.prev_exchange_rate:
        yoy_depr = (snap.exchange_rate - snap.prev_exchange_rate) / snap.prev_exchange_rate * 100
        values["depreciation_yoy_pct"] = round(yoy_depr, 1)

    # A) Depreciation magnitude (0-50 pts)
    if depr_pct > 5:
        pts_a = _clip(depr_pct - 5, 0, 25) / 25 * 50
        score += pts_a
        conditions.append(
            f"Currency depreciated {depr_pct:.1f}% vs 2020 reference "
            f"({ref_rate:.1f} → {snap.exchange_rate:.1f} per USD)"
        )

    # B) Inflation amplifier (0-25 pts): depreciation drives import price inflation
    if snap.inflation is not None:
        values["inflation_pct"] = snap.inflation
        if snap.inflation > 5:
            pts_b = _clip(snap.inflation - 5, 0, 25) / 25 * 25
            score += pts_b
            conditions.append(
                f"High inflation ({snap.inflation:.1f}%) compounds import cost pressure"
            )

    # C) Import deficit exposure (0-25 pts): deficit countries need more USD each cycle
    if snap.exports_usd_b is not None and snap.imports_usd_b is not None:
        trade_balance = snap.exports_usd_b - snap.imports_usd_b
        values["trade_balance_usd_b"] = round(trade_balance, 1)
        if trade_balance < 0:
            deficit_pct_imports = abs(trade_balance) / snap.imports_usd_b * 100
            pts_c = _clip(deficit_pct_imports, 0, 40) / 40 * 25
            score += pts_c
            conditions.append(
                f"Trade deficit of ${abs(trade_balance):.1f}B increases USD demand pressure"
            )

    # Explanation
    depr_word = (
        "collapsed" if depr_pct > 40
        else "severely depreciated" if depr_pct > 20
        else "significantly depreciated" if depr_pct > 10
        else "depreciated" if depr_pct > 5
        else "edged lower"
    )
    expl = (
        f"{snap.name}'s currency has {depr_word} by {depr_pct:.1f}% since 2020 "
        f"(now {snap.exchange_rate:.1f} per USD vs {ref_rate:.1f} reference). "
    )
    if snap.inflation and snap.inflation > 5:
        expl += (
            f"Combined with {snap.inflation:.1f}% inflation, this is eroding real import "
            f"purchasing power and raising the cost of dollar-denominated debt servicing. "
        )
    if snap.iso3 == "MMR":
        expl += (
            "Myanmar's kyat has effectively collapsed due to sanctions and capital flight "
            "post-coup. The official rate significantly understates the black-market depreciation."
        )
    elif snap.iso3 == "LAO":
        expl += (
            "Laos faces a compounding currency-inflation spiral driven by near-depleted "
            "foreign reserves and heavy USD-denominated debt obligations."
        )

    rec = (
        "Monitor central bank FX intervention and reserve levels. "
        "Check if foreign-currency debt service payments are coming due."
    )

    return _make_result(
        "currency_pressure", "Currency Pressure", "💱", "line", "exchange_rate",
        snap, score, conditions, values, expl, rec,
    )


# ─────────────────────────────────────────────────────────────────────────────
# ALERT 5 — INVESTMENT SLOWDOWN
#
# Fires when: FDI is declining, combined with high debt and political noise.
#
# Score components (0-100):
#   A) FDI YoY decline     0-50 pts  (-10%=10, -30%=30, -50%=50)
#   B) Consecutive decline 0-20 pts  (proxy: prev also negative)
#   C) Political noise     0-15 pts  (elevated news signals investor unease)
#   D) Debt overhang       0-15 pts  (public debt >70% crowds out private investment)
# ─────────────────────────────────────────────────────────────────────────────

def check_investment_slowdown(snap: CountrySnapshot) -> AlertResult:
    conditions: list[str] = []
    values: dict = {}
    score = 0.0

    fdi_yoy = _yoy_pct(snap.fdi_usd_b, snap.prev_fdi_usd_b)

    if snap.fdi_usd_b is not None:
        values["fdi_current_usd_b"] = snap.fdi_usd_b
    if snap.prev_fdi_usd_b is not None:
        values["fdi_prev_usd_b"] = snap.prev_fdi_usd_b

    # A) FDI YoY decline (0-50 pts)
    if fdi_yoy is not None:
        values["fdi_yoy_pct"] = round(fdi_yoy, 1)
        if fdi_yoy < -5:
            pts_a = _clip(-fdi_yoy - 5, 0, 45) / 45 * 50
            score += pts_a
            conditions.append(
                f"FDI fell {abs(fdi_yoy):.1f}% YoY "
                f"(${snap.prev_fdi_usd_b:.2f}B → ${snap.fdi_usd_b:.2f}B)"
            )

    # B) Consecutive decline (0-20 pts): proxy — both current and prev negative
    if snap.fdi_usd_b is not None and snap.prev_fdi_usd_b is not None:
        if fdi_yoy is not None and fdi_yoy < 0:
            # Simple proxy: if prev FDI also low vs two years prior (we don't have t-2)
            # Just award partial pts if current FDI is below 50% of a rough regional avg
            if snap.fdi_usd_b < snap.prev_fdi_usd_b * 0.85:
                score += 10
                conditions.append("FDI has declined significantly over the period")
            if snap.fdi_usd_b < snap.prev_fdi_usd_b * 0.70:
                score += 10
                conditions.append("FDI decline is accelerating")

    # C) Political noise amplifier (0-15 pts)
    pol_total = snap.political_risk_news_count + snap.conflict_protest_news_count
    pol_baseline = POLITICAL_NEWS_BASELINE.get(snap.iso3, 4) + CONFLICT_NEWS_BASELINE.get(snap.iso3, 5)
    if pol_total > pol_baseline * 1.3:
        pts_c = _clip(pol_total / pol_baseline - 1.0, 0, 2.0) / 2.0 * 15
        score += pts_c
        conditions.append(
            f"Political risk news elevated ({pol_total} articles), deterring foreign investors"
        )
    values["total_risk_news_count"] = pol_total

    # D) Public debt overhang (0-15 pts)
    if snap.public_debt_pct_gdp is not None:
        values["public_debt_pct_gdp"] = snap.public_debt_pct_gdp
        if snap.public_debt_pct_gdp > 70:
            pts_d = _clip(snap.public_debt_pct_gdp - 70, 0, 30) / 30 * 15
            score += pts_d
            conditions.append(
                f"Public debt at {snap.public_debt_pct_gdp:.0f}% of GDP signals fiscal stress to investors"
            )

    # Explanation
    if fdi_yoy is not None and fdi_yoy < 0:
        driver = (
            "political instability" if snap.conflict_protest_news_count > CONFLICT_NEWS_BASELINE.get(snap.iso3, 5) * 1.5
            else "regulatory uncertainty" if snap.political_risk_news_count > POLITICAL_NEWS_BASELINE.get(snap.iso3, 4) * 1.5
            else "deteriorating macroeconomic conditions"
        )
        expl = (
            f"FDI into {snap.name} declined {abs(fdi_yoy):.1f}% year-over-year "
            f"to ${snap.fdi_usd_b:.2f}B, consistent with investor concern over {driver}. "
        )
    else:
        expl = f"FDI trends in {snap.name} warrant monitoring."

    if snap.public_debt_pct_gdp and snap.public_debt_pct_gdp > 70:
        expl += (
            f"With public debt at {snap.public_debt_pct_gdp:.0f}% of GDP, "
            f"the government has limited fiscal capacity to offer competitive incentives."
        )

    rec = (
        "Track major investment announcements and project cancellations. "
        "Monitor Free Economic Zone occupancy rates and SEZ application pipeline."
    )

    return _make_result(
        "investment_slowdown", "Investment Slowdown", "📊", "bar", "fdi_usd_b",
        snap, score, conditions, values, expl, rec,
    )


# ─────────────────────────────────────────────────────────────────────────────
# ALERT 6 — TRADE DEPENDENCY RISK
#
# Fires when: a single partner dominates exports or imports,
#             especially if the same partner dominates both sides.
#
# Score components (0-100):
#   A) Export concentration    0-40 pts  (>20% starts scoring; >60% = 40pts)
#   B) Import concentration    0-40 pts  (>25% starts scoring; >65% = 40pts)
#   C) Same-partner overlap    0-20 pts  (same country tops both exports & imports)
# ─────────────────────────────────────────────────────────────────────────────

def check_trade_dependency_risk(snap: CountrySnapshot) -> AlertResult:
    conditions: list[str] = []
    values: dict = {}
    score = 0.0

    exp_share = snap.top_export_partner_share
    imp_share = snap.top_import_partner_share

    if exp_share is None and imp_share is None:
        return _make_result(
            "trade_dependency_risk", "Trade Dependency Risk", "🔗", "bar",
            "top_export_partner_share", snap, 0, [],
            {"note": "No bilateral trade data available"},
            f"No partner-level trade data available for {snap.name}.", "",
        )

    # A) Export concentration (0-40 pts): floor at 20%
    if exp_share is not None:
        values["top_export_partner"]       = snap.top_export_partner
        values["top_export_partner_share"] = round(exp_share, 1)
        if exp_share > 20:
            pts_a = _clip(exp_share - 20, 0, 40) / 40 * 40
            score += pts_a
            if exp_share > 30:
                conditions.append(
                    f"{exp_share:.0f}% of exports go to {snap.top_export_partner} "
                    f"(over-reliance threshold: 30%)"
                )

    # B) Import concentration (0-40 pts): floor at 25%
    if imp_share is not None:
        values["top_import_partner"]       = snap.top_import_partner
        values["top_import_partner_share"] = round(imp_share, 1)
        if imp_share > 25:
            pts_b = _clip(imp_share - 25, 0, 40) / 40 * 40
            score += pts_b
            if imp_share > 35:
                conditions.append(
                    f"{imp_share:.0f}% of imports sourced from {snap.top_import_partner} "
                    f"(over-reliance threshold: 35%)"
                )

    # C) Same-partner overlap (0-20 pts): bilateral lock-in
    if (snap.top_export_partner and snap.top_import_partner
            and snap.top_export_partner == snap.top_import_partner):
        score += 20
        conditions.append(
            f"{snap.top_export_partner} is both largest export market and import source "
            f"— bilateral lock-in risk"
        )

    # Scale check: don't let A+B+C exceed 100
    score = _clip(score, 0, 100)

    # Explanation
    parts = []
    if exp_share and exp_share > 30:
        parts.append(
            f"{exp_share:.0f}% of {snap.name}'s exports go to {snap.top_export_partner}"
        )
    if imp_share and imp_share > 35:
        parts.append(
            f"{imp_share:.0f}% of imports are sourced from {snap.top_import_partner}"
        )

    if parts:
        expl = (
            f"{snap.name} shows high trade concentration: {'. '.join(parts)}. "
            "This creates vulnerability to policy changes, sanctions, or economic slowdowns "
            "in the dominant partner."
        )
        if snap.top_export_partner == snap.top_import_partner:
            expl += (
                f" The fact that {snap.top_export_partner} dominates both sides of "
                f"{snap.name}'s trade ledger amplifies geopolitical exposure."
            )
    else:
        expl = f"Trade concentration for {snap.name} is within normal bounds."

    rec = (
        "Track diversification trends over 3-5 years. "
        "Watch for new FTA negotiations that may shift partner concentration."
    )

    return _make_result(
        "trade_dependency_risk", "Trade Dependency Risk", "🔗", "bar",
        "top_export_partner_share", snap, score, conditions, values, expl, rec,
    )


# ─────────────────────────────────────────────────────────────────────────────
# ALERT 7 — TOURISM RECOVERY
#
# Fires when: arrivals are still significantly below 2019 pre-COVID baseline,
#             or a recovery is reversing.
#
# Score components (0-100):
#   A) Gap from 2019 baseline  0-60 pts  (100% gap = 60pts, 0% gap = 0pts)
#   B) Recovery reversal       0-40 pts  (+40 if arrivals fell YoY while still <90% baseline)
# ─────────────────────────────────────────────────────────────────────────────

def check_tourism_recovery(snap: CountrySnapshot) -> AlertResult:
    conditions: list[str] = []
    values: dict = {}
    score = 0.0

    baseline_2019 = TOURISM_2019_BASELINE.get(snap.iso3)

    # If no tourism data available at all, skip this alert
    if snap.tourism_arrivals_m is None or baseline_2019 is None:
        return _make_result(
            "tourism_recovery", "Tourism Recovery", "✈️", "line", "tourism_arrivals_m",
            snap, 0, [], {},
            f"No tourism arrival data available for {snap.name}.", "",
        )

    arrivals     = snap.tourism_arrivals_m
    recovery_pct = arrivals / baseline_2019 * 100
    gap_pct      = max(0, 100 - recovery_pct)   # how far below 2019

    values["tourism_arrivals_m"]       = round(arrivals, 2)
    values["baseline_2019_m"]          = baseline_2019
    values["recovery_pct_of_2019"]     = round(recovery_pct, 1)

    # A) Gap from 2019 baseline (0-60 pts)
    if gap_pct > 10:
        pts_a = _clip(gap_pct - 10, 0, 80) / 80 * 60
        score += pts_a
        conditions.append(
            f"Tourism at {recovery_pct:.0f}% of 2019 baseline "
            f"({arrivals:.1f}M vs {baseline_2019:.1f}M)"
        )

    # B) Recovery reversal (0-40 pts): recovering then going back down
    if snap.prev_tourism_arrivals_m is not None:
        yoy_tourism = _yoy_pct(arrivals, snap.prev_tourism_arrivals_m)
        values["tourism_yoy_pct"] = round(yoy_tourism, 1) if yoy_tourism else None
        if yoy_tourism is not None and yoy_tourism < -5 and recovery_pct < 90:
            pts_b = _clip(-yoy_tourism - 5, 0, 35) / 35 * 40
            score += pts_b
            conditions.append(
                f"Tourism arrivals fell {abs(yoy_tourism):.1f}% YoY "
                f"({snap.prev_tourism_arrivals_m:.1f}M → {arrivals:.1f}M) — recovery reversing"
            )

    # Explanation
    if recovery_pct >= 100:
        expl = (
            f"{snap.name}'s tourism has fully recovered to {recovery_pct:.0f}% of 2019 levels "
            f"({arrivals:.1f}M arrivals). No alert required."
        )
    elif recovery_pct >= 70:
        expl = (
            f"{snap.name}'s tourism is recovering but remains {gap_pct:.0f}% below 2019 levels "
            f"({arrivals:.1f}M vs {baseline_2019:.1f}M pre-COVID baseline)."
        )
    else:
        expl = (
            f"{snap.name}'s tourism sector has not recovered: arrivals at {arrivals:.1f}M "
            f"are only {recovery_pct:.0f}% of the 2019 baseline ({baseline_2019:.1f}M). "
            f"For tourism-dependent economies, this represents a significant GDP drag."
        )

    rec = (
        "Track visa-on-arrival policy changes and airline route openings. "
        "Compare with regional peers — if neighbours are recovering faster, check for structural barriers."
    )

    return _make_result(
        "tourism_recovery", "Tourism Recovery", "✈️", "line", "tourism_arrivals_m",
        snap, score, conditions, values, expl, rec,
    )


# ─────────────────────────────────────────────────────────────────────────────
# ALERT 8 — REGIONAL SPILLOVER RISK
#
# Fires when: multiple neighbouring countries are simultaneously under stress,
#             increasing the probability of contagion via trade, capital, or
#             refugee/migration channels.
#
# Score components (0-100):
#   A) Neighbour stress count   0-60 pts  (each stressed neighbour adds weight)
#   B) Key partner stress       0-40 pts  (if top trading partner is stressed)
# ─────────────────────────────────────────────────────────────────────────────

def _peer_stress_score(snap: CountrySnapshot) -> float:
    """Quick stress proxy for a neighbouring country (0-100)."""
    s = 0.0
    if snap.gdp_growth is not None:
        if snap.gdp_growth < -5:  s += 30
        elif snap.gdp_growth < 0: s += 20
        elif snap.gdp_growth < 2: s += 8
    if snap.inflation is not None:
        if snap.inflation > 20:   s += 30
        elif snap.inflation > 10: s += 18
        elif snap.inflation > 5:  s += 8
    ref = EXCHANGE_RATE_BASELINE.get(snap.iso3)
    if ref and snap.exchange_rate:
        depr = (snap.exchange_rate - ref) / ref * 100
        if depr > 30:   s += 25
        elif depr > 15: s += 12
        elif depr > 5:  s += 5
    if snap.conflict_protest_news_count:
        baseline = CONFLICT_NEWS_BASELINE.get(snap.iso3, 5)
        ratio = snap.conflict_protest_news_count / baseline
        if ratio > 3:   s += 15
        elif ratio > 2: s += 8
        elif ratio > 1.5: s += 4
    return min(100.0, s)


def check_regional_spillover(
    snap: CountrySnapshot,
    peer_snapshots: dict[str, CountrySnapshot],
) -> AlertResult:
    conditions: list[str] = []
    values: dict = {}
    score = 0.0

    neighbours = REGIONAL_NEIGHBOURS.get(snap.iso3, [])
    stressed_neighbours: list[str] = []

    # A) Neighbour stress (0-60 pts)
    for nb_iso3 in neighbours:
        peer = peer_snapshots.get(nb_iso3)
        if peer is None:
            continue
        nb_stress = _peer_stress_score(peer)
        values[f"neighbour_{nb_iso3}_stress"] = round(nb_stress, 0)
        if nb_stress >= 50:
            stressed_neighbours.append(nb_iso3)
            score += 15   # each critically stressed neighbour: 15pts
            conditions.append(
                f"{peer.name} is under high economic/political stress "
                f"(stress score: {nb_stress:.0f}/100)"
            )
        elif nb_stress >= 25:
            stressed_neighbours.append(nb_iso3)
            score += 7
            conditions.append(f"{peer.name} is under moderate stress ({nb_stress:.0f}/100)")

    score = _clip(score, 0, 60)

    # B) Key trading partner stress (0-40 pts)
    if snap.top_export_partner and snap.top_export_partner in peer_snapshots:
        partner_peer = peer_snapshots[snap.top_export_partner]
        partner_stress = _peer_stress_score(partner_peer)
        values["top_export_partner_stress"] = round(partner_stress, 0)
        if partner_stress >= 40:
            pts_b = _clip(partner_stress - 40, 0, 60) / 60 * 40
            score += pts_b
            conditions.append(
                f"Top export partner {snap.top_export_partner} under stress "
                f"({partner_stress:.0f}/100) — export demand at risk"
            )

    score = _clip(score, 0, 100)

    # Explanation
    if stressed_neighbours:
        nb_names = [peer_snapshots[n].name for n in stressed_neighbours if n in peer_snapshots]
        expl = (
            f"{snap.name} faces elevated spillover risk from concurrent stress in "
            f"neighbouring economies: {', '.join(nb_names)}. "
            "Channels include: refugee/migration pressure, regional trade disruption, "
            "investor contagion, and cross-border conflict escalation."
        )
    else:
        expl = f"Neighbouring economies do not currently show significant stress signals for {snap.name}."

    rec = (
        "Monitor cross-border trade volumes and migration statistics. "
        "Watch for capital flow reversals if regional sentiment deteriorates."
    )

    return _make_result(
        "regional_spillover", "Regional Spillover Risk", "🌏", "heatmap",
        "neighbour_stress", snap, score, conditions, values, expl, rec,
    )


# ─────────────────────────────────────────────────────────────────────────────
# MAIN RUNNER
# ─────────────────────────────────────────────────────────────────────────────

def run_all_alerts(
    snap: CountrySnapshot,
    peer_snapshots: Optional[dict[str, CountrySnapshot]] = None,
) -> list[AlertResult]:
    """Run all 8 alert checks for a single country snapshot. Returns all results."""
    peers = peer_snapshots or {}
    return [
        check_export_stress(snap),
        check_inflation_pressure(snap),
        check_political_instability(snap),
        check_currency_pressure(snap),
        check_investment_slowdown(snap),
        check_trade_dependency_risk(snap),
        check_tourism_recovery(snap),
        check_regional_spillover(snap, peers),
    ]


def run_all_countries(
    snapshots: list[CountrySnapshot],
    min_score: float = 0.0,
) -> list[AlertResult]:
    """
    Run all alerts for all countries.
    Builds peer_snapshots map automatically from the input list.
    """
    peer_map = {s.iso3: s for s in snapshots}
    all_results: list[AlertResult] = []
    for snap in snapshots:
        results = run_all_alerts(snap, peer_map)
        for r in results:
            if r.score >= min_score:
                all_results.append(r)
    # Sort: critical first, then by score desc
    severity_order = {"critical": 0, "warning": 1, "info": 2, "none": 3}
    all_results.sort(key=lambda r: (severity_order.get(r.severity, 9), -r.score))
    return all_results


# ─────────────────────────────────────────────────────────────────────────────
# BUILT-IN SAMPLE DATA (for standalone testing)
# ─────────────────────────────────────────────────────────────────────────────

SAMPLE_SNAPSHOTS: list[CountrySnapshot] = [
    CountrySnapshot(
        iso3="MMR", name="Myanmar", year=2023,
        gdp_growth=-1.5,     prev_gdp_growth=-0.3,
        inflation=23.0,      prev_inflation=18.0,
        exports_usd_b=11.8,  prev_exports_usd_b=10.8,
        imports_usd_b=15.3,  prev_imports_usd_b=13.5,
        exchange_rate=2100.0, prev_exchange_rate=1800.0,  # vs 1330 baseline
        fdi_usd_b=0.50,      prev_fdi_usd_b=0.61,
        public_debt_pct_gdp=65.0,
        conflict_protest_news_count=24,
        political_risk_news_count=14,
        trade_news_count=4,
        top_export_partner="CHN", top_export_partner_share=34.8,
        top_import_partner="CHN", top_import_partner_share=41.8,
        tourism_arrivals_m=0.8, prev_tourism_arrivals_m=1.1,
    ),
    CountrySnapshot(
        iso3="LAO", name="Laos", year=2023,
        gdp_growth=4.0,       prev_gdp_growth=2.7,
        inflation=31.2,       prev_inflation=22.9,
        exports_usd_b=6.2,    prev_exports_usd_b=5.9,
        imports_usd_b=8.4,    prev_imports_usd_b=8.0,
        exchange_rate=21000.0, prev_exchange_rate=16500.0,  # vs 9400 baseline
        fdi_usd_b=0.90,       prev_fdi_usd_b=0.81,
        public_debt_pct_gdp=112.0,
        conflict_protest_news_count=4,
        political_risk_news_count=5,
        trade_news_count=6,
        top_export_partner="CHN", top_export_partner_share=28.0,
        top_import_partner="CHN", top_import_partner_share=42.0,
        tourism_arrivals_m=3.1, prev_tourism_arrivals_m=2.5,
    ),
    CountrySnapshot(
        iso3="VNM", name="Vietnam", year=2023,
        gdp_growth=5.1,        prev_gdp_growth=8.0,
        inflation=3.3,         prev_inflation=3.2,
        exports_usd_b=355.5,   prev_exports_usd_b=392.3,
        imports_usd_b=327.8,   prev_imports_usd_b=374.6,
        exchange_rate=24200.0, prev_exchange_rate=23400.0,  # vs 23200 baseline
        fdi_usd_b=16.1,        prev_fdi_usd_b=17.5,
        public_debt_pct_gdp=37.0,
        conflict_protest_news_count=4,
        political_risk_news_count=5,
        trade_news_count=8,
        top_export_partner="USA", top_export_partner_share=27.3,
        top_import_partner="CHN", top_import_partner_share=36.0,
        tourism_arrivals_m=12.6, prev_tourism_arrivals_m=3.7,
    ),
    CountrySnapshot(
        iso3="KHM", name="Cambodia", year=2023,
        gdp_growth=5.1,       prev_gdp_growth=5.2,
        inflation=2.1,        prev_inflation=5.3,
        exports_usd_b=23.4,   prev_exports_usd_b=22.1,
        imports_usd_b=27.6,   prev_imports_usd_b=26.9,
        exchange_rate=4120.0, prev_exchange_rate=4090.0,  # vs 4070 baseline
        fdi_usd_b=3.4,        prev_fdi_usd_b=3.8,
        public_debt_pct_gdp=38.0,
        conflict_protest_news_count=6,
        political_risk_news_count=7,
        trade_news_count=4,
        top_export_partner="USA", top_export_partner_share=32.1,
        top_import_partner="CHN", top_import_partner_share=39.9,
        tourism_arrivals_m=5.4, prev_tourism_arrivals_m=2.3,
    ),
    CountrySnapshot(
        iso3="THA", name="Thailand", year=2023,
        gdp_growth=1.9,        prev_gdp_growth=2.6,
        inflation=1.2,         prev_inflation=6.1,
        exports_usd_b=285.2,   prev_exports_usd_b=327.9,
        imports_usd_b=270.3,   prev_imports_usd_b=319.2,
        exchange_rate=34.8,    prev_exchange_rate=35.1,   # vs 31.3 baseline
        fdi_usd_b=8.0,         prev_fdi_usd_b=7.8,
        public_debt_pct_gdp=61.0,
        conflict_protest_news_count=8,
        political_risk_news_count=10,
        trade_news_count=7,
        top_export_partner="USA", top_export_partner_share=13.3,
        top_import_partner="CHN", top_import_partner_share=27.5,
        tourism_arrivals_m=28.2, prev_tourism_arrivals_m=11.2,
    ),
    CountrySnapshot(
        iso3="PHL", name="Philippines", year=2023,
        gdp_growth=5.5,        prev_gdp_growth=7.6,
        inflation=5.9,         prev_inflation=5.8,
        exports_usd_b=69.4,    prev_exports_usd_b=72.0,
        imports_usd_b=119.9,   prev_imports_usd_b=122.0,
        exchange_rate=56.0,    prev_exchange_rate=54.5,   # vs 50.7 baseline
        fdi_usd_b=9.1,         prev_fdi_usd_b=9.8,
        public_debt_pct_gdp=60.0,
        conflict_protest_news_count=9,
        political_risk_news_count=8,
        trade_news_count=5,
        top_export_partner="USA", top_export_partner_share=17.1,
        top_import_partner="CHN", top_import_partner_share=28.0,
        tourism_arrivals_m=5.5, prev_tourism_arrivals_m=2.1,
    ),
    CountrySnapshot(
        iso3="SGP", name="Singapore", year=2023,
        gdp_growth=1.1,        prev_gdp_growth=3.6,
        inflation=4.8,         prev_inflation=6.1,
        exports_usd_b=593.3,   prev_exports_usd_b=637.4,
        imports_usd_b=538.1,   prev_imports_usd_b=581.2,
        exchange_rate=1.34,    prev_exchange_rate=1.38,   # vs 1.38 baseline (appreciated)
        fdi_usd_b=58.0,        prev_fdi_usd_b=80.0,
        public_debt_pct_gdp=168.0,    # NOTE: Singapore's debt is mostly domestic savings bonds
        conflict_protest_news_count=1,
        political_risk_news_count=2,
        trade_news_count=9,
        top_export_partner="CHN", top_export_partner_share=13.8,
        top_import_partner="CHN", top_import_partner_share=21.2,
        tourism_arrivals_m=13.6, prev_tourism_arrivals_m=6.3,
    ),
    CountrySnapshot(
        iso3="IDN", name="Indonesia", year=2023,
        gdp_growth=5.1,        prev_gdp_growth=5.3,
        inflation=3.7,         prev_inflation=4.2,
        exports_usd_b=291.9,   prev_exports_usd_b=329.3,
        imports_usd_b=249.3,   prev_imports_usd_b=264.1,
        exchange_rate=15600.0, prev_exchange_rate=15300.0,  # vs 14100 baseline
        fdi_usd_b=22.0,        prev_fdi_usd_b=22.0,
        public_debt_pct_gdp=39.0,
        conflict_protest_news_count=6,
        political_risk_news_count=8,
        trade_news_count=5,
        top_export_partner="CHN", top_export_partner_share=22.6,
        top_import_partner="CHN", top_import_partner_share=29.0,
        tourism_arrivals_m=11.7, prev_tourism_arrivals_m=5.5,
    ),
]


# ─────────────────────────────────────────────────────────────────────────────
# OUTPUT WRITERS
# ─────────────────────────────────────────────────────────────────────────────

TODAY = date.today().strftime("%Y%m%d")

def save_json(alerts: list[AlertResult]) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / f"pattern_alerts_{TODAY}.json"
    path.write_text(json.dumps([asdict(a) for a in alerts], indent=2))
    return path

def save_csv(alerts: list[AlertResult]) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / f"pattern_alerts_{TODAY}.csv"
    if not alerts:
        return path
    fields = [
        "alert_id", "alert_type", "alert_label", "country_iso3", "country_name",
        "year", "triggered", "score", "severity",
        "explanation", "recommendation",
    ]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows([asdict(a) for a in alerts])
    return path

def print_summary(alerts: list[AlertResult], min_score: float = 0) -> None:
    SEV_EMOJI = {"critical": "🔴", "warning": "🟡", "info": "🔵", "none": "⚪"}
    print(f"\n{'═' * 70}")
    print(f"  PATTERN DETECTION RESULTS  —  {len([a for a in alerts if a.triggered])} alerts fired")
    print(f"{'═' * 70}\n")
    for a in alerts:
        if a.score < min_score:
            continue
        em = SEV_EMOJI.get(a.severity, "⚪")
        print(f"  {em} [{a.severity.upper():8s}] {a.country_name:12s} — {a.alert_label:28s} score={a.score:5.1f}")
        for cond in a.conditions_met:
            print(f"       • {cond}")
        if a.conditions_met:
            print(f"       ↳ {a.explanation[:100]}...")
        print()


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run SEA Dashboard pattern detection engine on sample data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--country",   type=str,   help="Filter to single ISO3 country (e.g. MMR)")
    parser.add_argument("--alert",     type=str,   help="Filter to single alert type (e.g. inflation_pressure)")
    parser.add_argument("--threshold", type=float, default=20.0, help="Minimum score to display (default: 20)")
    parser.add_argument("--output",    type=str,   choices=["json", "csv", "both"], help="Save output file(s)")
    args = parser.parse_args()

    snapshots = SAMPLE_SNAPSHOTS
    if args.country:
        snapshots = [s for s in snapshots if s.iso3 == args.country.upper()]
        if not snapshots:
            print(f"✗ Unknown country '{args.country}'. "
                  f"Available: {', '.join(s.iso3 for s in SAMPLE_SNAPSHOTS)}")
            return

    all_alerts = run_all_countries(snapshots, min_score=0)

    if args.alert:
        all_alerts = [a for a in all_alerts if a.alert_type == args.alert]

    print_summary(all_alerts, min_score=args.threshold)

    if args.output in ("json", "both"):
        path = save_json(all_alerts)
        print(f"✓ JSON saved → {path}")
    if args.output in ("csv", "both"):
        path = save_csv(all_alerts)
        print(f"✓ CSV  saved → {path}")


if __name__ == "__main__":
    main()
