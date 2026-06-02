"""
==============================================================================
  backend/ai_engine.py — AI Explanation Engine
  SEA Change Intelligence Dashboard
==============================================================================

This module contains everything needed to generate structured AI explanations
for pattern alerts:

  1. INPUT_JSON_SCHEMA   — The format you send TO this engine
  2. OUTPUT_JSON_SCHEMA  — The format you get BACK
  3. PROMPT_TEMPLATE     — The exact prompt sent to Claude
  4. build_explanation() — Main function to call from the FastAPI endpoint

EPISTEMIC RULES (the most important section — read first)
----------------------------------------------------------
The AI MUST NOT:
  ✗  Predict future values with certainty
  ✗  Make specific forecasts ("X will reach Y by Z")
  ✗  Name individuals or political leaders
  ✗  Assign blame for outcomes
  ✗  State correlations as confirmed causation

The AI MUST use hedging language:
  ✓  "may suggest"
  ✓  "could indicate"
  ✓  "appears consistent with"
  ✓  "early warning signal"
  ✓  "possible impact"
  ✓  "needs more data"
  ✓  "this pattern is often associated with"
  ✓  "warrants monitoring"

CONFIDENCE LEVELS
-----------------
  HIGH   — Multiple corroborating data sources, well-established economic
           relationships, stable data reporting environment.
  MEDIUM — Some corroborating signals, standard economic relationships,
           reasonable data quality.
  LOW    — Single data source, disputed data quality, unusual macro environment,
           post-conflict/post-disaster conditions that break normal models.
==============================================================================
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

# ──────────────────────────────────────────────────────────────────────────────
#  SECTION 1 — INPUT JSON SCHEMA (documented with examples)
# ──────────────────────────────────────────────────────────────────────────────
#
# This is the shape of the object you send to build_explanation().
# All fields are described below. Required fields are marked *.

INPUT_JSON_SCHEMA: dict = {
    "$comment": "Input schema for the AI explanation engine",

    # * The triggered alert ────────────────────────────────────────────────────
    "alert": {
        "type":            "INFLATION_PRESSURE",     # * Pattern engine alert key
        "label":           "Inflation Pressure",     # * Human-readable name
        "country_id":      "MMR",                    # * ISO3 country code
        "country_name":    "Myanmar",                # * Display name
        "flag":            "🇲🇲",                    #   Emoji flag (optional)
        "quarter":         "2024-Q3",                # * Time period
        "severity":        "critical",               # * none|info|warning|critical
        "trigger_value":   22.4,                     # * Value that triggered alert
        "threshold_value": 10.0,                     # * The threshold it crossed
        "unit":            "% YoY",                  # * Unit of measurement
        "score":           100,                      #   0–100 numeric score
        "condition_met":   "Inflation 22.4% — above 10% threshold",  # * Human summary
    },

    # * All 8 current indicator values for this country ────────────────────────
    "indicators": {
        "gdpGrowth":         {"value": -2.1,    "unit": "% YoY",      "label": "GDP Growth"},
        "inflation":         {"value": 22.4,    "unit": "% YoY",      "label": "Inflation (CPI)"},
        "exports":           {"value": 4.2,     "unit": "USD Billion", "label": "Exports"},
        "imports":           {"value": 6.6,     "unit": "USD Billion", "label": "Imports"},
        "exchangeRate":      {"value": 2100.0,  "unit": "per USD",    "label": "Exchange Rate"},
        "fdi":               {"value": 0.8,     "unit": "USD Billion", "label": "FDI Net Inflows"},
        "politicalRiskNews": {"value": 156,     "unit": "articles",   "label": "Political Risk News"},
        "tradeNewsCount":    {"value": 34,      "unit": "articles",   "label": "Trade News Count"},
    },

    # * Other alerts active for the same country at the same time ──────────────
    # Helps the AI understand if this is an isolated signal or part of a cluster.
    "other_active_alerts": [
        {"type": "CURRENCY_PRESSURE", "severity": "critical", "label": "Currency Pressure"},
        {"type": "FDI_SLOWDOWN",      "severity": "critical", "label": "FDI Slowdown"},
    ],

    # * Recent news signals connected to this alert ────────────────────────────
    # From news_events.json or GDELT. Max 5, highest impact first.
    "recent_news": [
        {
            "headline":            "Myanmar Kyat Hits All-Time Low at 6,500 per USD on Black Market",
            "category":            "economy",
            "sentiment":           "negative",
            "impact_score":        5,
            "days_ago":            3,
            "connected_indicators": ["exchangeRate", "inflation", "imports"],
        }
    ],

    # * Regional context ────────────────────────────────────────────────────────
    "context": {
        "region":      "Southeast Asia",
        "neighbors":   ["THA", "VNM", "KHM", "SGP"],   # Other dashboard countries
        "trade_links": {
            "top_export_partners": ["China", "Thailand"],
            "top_import_partners": ["China", "Singapore"],
        },
        "data_source_notes": (
            "Post-2021 coup data for Myanmar is from IMF estimates and secondary sources. "
            "Official national statistics office data is unreliable since the 2021 coup."
        ),
    },
}


# ──────────────────────────────────────────────────────────────────────────────
#  SECTION 2 — OUTPUT JSON SCHEMA
# ──────────────────────────────────────────────────────────────────────────────
#
# This is the shape of the object returned by build_explanation().
# The frontend reads every field below.

OUTPUT_JSON_SCHEMA: dict = {
    "$comment": "Output schema from the AI explanation engine",

    # Identity fields ──────────────────────────────────────────────────────────
    "alert_type":   "INFLATION_PRESSURE",
    "country_id":   "MMR",
    "country_name": "Myanmar",
    "severity":     "critical",
    "quarter":      "2024-Q3",

    # Section 1 — What changed ─────────────────────────────────────────────────
    # 2–3 sentences: fact-first, then context.
    # Must include the actual numbers. Must use hedging language.
    "what_changed": (
        "Myanmar's inflation reached 22.4% in Q3 2024, more than double the 10% critical "
        "threshold. This may suggest accelerating price pressures beyond what official figures "
        "alone capture, given the known unreliability of post-coup statistics. The pattern "
        "appears consistent with severe import-cost pass-through following currency collapse."
    ),

    # Section 2 — Why it matters ───────────────────────────────────────────────
    # 2–3 sentences: economic significance, who is affected.
    # Must NOT predict — use "could", "may", "tends to".
    "why_it_matters": (
        "Inflation at this level erodes household purchasing power and could indicate a "
        "breakdown in monetary policy effectiveness. For an import-dependent economy like "
        "Myanmar, high inflation is often associated with currency depreciation feeding into "
        "the cost of basic goods. This may disproportionately affect lower-income households "
        "and could suppress domestic consumption if wages do not keep pace."
    ),

    # Section 3 — Connected indicators ────────────────────────────────────────
    # Array of indicators that are likely connected to this alert.
    "connected_indicators": [
        {
            "key":          "exchangeRate",
            "label":        "Exchange Rate",
            "value":        2100,
            "unit":         "per USD",
            "relationship": (
                "Currency depreciation is a likely driver of inflation through import costs. "
                "The two indicators appear to be reinforcing each other — needs more data "
                "to confirm the direction of causation."
            ),
            "direction":    "amplifying",  # amplifying | dampening | unclear
        },
        {
            "key":          "fdi",
            "label":        "FDI Net Inflows",
            "value":        0.8,
            "unit":         "USD Billion",
            "relationship": (
                "Low FDI may suggest reduced investor confidence, which could limit the "
                "availability of foreign currency and further amplify exchange rate pressure."
            ),
            "direction":    "amplifying",
        },
    ],

    # Section 4 — Which countries may be affected ──────────────────────────────
    # Array of possible spillover effects on neighbouring countries.
    "affected_countries": [
        {
            "country_id":         "THA",
            "country_name":       "Thailand",
            "flag":               "🇹🇭",
            "mechanism":          (
                "Cross-border trade disruption and informal refugee flows may create "
                "localised economic strain in Thai border provinces."
            ),
            "possible_impact":    "low",    # none | low | medium | high
            "indicators_at_risk": ["tradeNewsCount", "exports"],
            "confidence":         "low",
        },
    ],

    # Section 5 — Confidence level ─────────────────────────────────────────────
    "confidence": {
        "level":        "low",      # low | medium | high
        "label":        "Low Confidence",
        "score":        25,         # 0–100
        "rationale": (
            "Post-2021 Myanmar data is based on IMF estimates and secondary sources. "
            "Official statistics are unreliable. Multiple compounding crises make "
            "causal attribution difficult. Inflation figures may undercount black-market "
            "dynamics."
        ),
        "data_quality": "poor",     # poor | fair | good
        "factors": [
            "Data source reliability: poor (post-coup statistics disrupted)",
            "Economic model applicability: low (conflict economy breaks normal models)",
            "Corroborating signals: moderate (news and currency data aligned)",
        ],
    },

    # Section 6 — Limitations ──────────────────────────────────────────────────
    "limitations": [
        "Official Myanmar statistics are unreliable after the 2021 military coup",
        "Inflation figures may undercount black-market and informal-sector price dynamics",
        "Indicator relationships described here are correlational, not confirmed causal chains",
        "Regional spillover severity estimates are speculative without bilateral trade flow data",
        "This analysis reflects conditions as of the data period and may already be outdated",
    ],

    # Short summary sentence for UI cards ──────────────────────────────────────
    "summary_sentence": (
        "Myanmar inflation at 22.4% is an early warning signal that may suggest systemic "
        "monetary stress — interpret with caution given low data confidence."
    ),

    # Epistemic footer shown in the UI ─────────────────────────────────────────
    "hedging_note": (
        "This is an early warning signal analysis, not a forecast. All indicator "
        "relationships are correlational patterns observed in similar historical contexts. "
        "Nothing here constitutes a prediction of future outcomes."
    ),

    # Metadata ──────────────────────────────────────────────────────────────────
    "is_ai":        True,
    "model_used":   "claude-haiku-4-5",
    "generated_at": "2024-12-01T12:00:00Z",
}


# ──────────────────────────────────────────────────────────────────────────────
#  SECTION 3 — PROMPT TEMPLATE
# ──────────────────────────────────────────────────────────────────────────────
#
# The prompt is split into:
#   SYSTEM_PROMPT  — Persona, epistemic rules, forbidden phrases, output schema.
#                    Sent as the "system" parameter to Claude.
#   USER_TEMPLATE  — The actual alert data. Built at runtime from input.
#
# Why this design?
#   - System prompt establishes rules that can't be overridden by the data.
#   - User message contains only variable data — clean and predictable.
#   - Claude is asked to output ONLY valid JSON — no prose around it.
#   - Assistant prefill ( { ) ensures the response starts as JSON.

SYSTEM_PROMPT = """\
You are a careful, senior economic analyst specialising in Southeast Asian
emerging markets. You write structured explanations for a geopolitical and
economic intelligence dashboard.

═══════════════════════════════════════════════════════
 EPISTEMIC RULES — FOLLOW THESE STRICTLY
═══════════════════════════════════════════════════════

YOU MUST NOT:
  • Predict specific future values or timeframes
  • Use the words: "will", "shall", "definitely", "certainly", "guaranteed",
    "predicts", "forecast confirms", "proof that"
  • Name specific political leaders or individuals
  • State correlations as confirmed causal chains
  • Make strong claims about countries with poor data quality

YOU MUST:
  • Use hedged language throughout:
      "may suggest"          "could indicate"         "appears consistent with"
      "early warning signal" "possible impact"        "needs more data"
      "this pattern is often associated with"         "warrants monitoring"
      "tends to correlate with"                       "available data suggests"
  • Scale confidence level to data quality (post-conflict = LOW confidence)
  • Acknowledge data limitations explicitly
  • Separate correlation from causation

═══════════════════════════════════════════════════════
 OUTPUT FORMAT — RETURN ONLY VALID JSON
═══════════════════════════════════════════════════════

Return a single JSON object with EXACTLY these keys. No text before or after.
No markdown code fences. No comments inside the JSON.

{
  "what_changed":          string (2-3 sentences, must include actual numbers),
  "why_it_matters":        string (2-3 sentences, economic significance),
  "connected_indicators": [
    {
      "key":          string (camelCase indicator key),
      "label":        string (human label),
      "value":        number,
      "unit":         string,
      "relationship": string (1-2 sentences, hedged),
      "direction":    "amplifying" | "dampening" | "unclear"
    }
    ... include 2-4 indicators most relevant to this alert
  ],
  "affected_countries": [
    {
      "country_id":         string (ISO3),
      "country_name":       string,
      "flag":               string (emoji),
      "mechanism":          string (1-2 sentences, hedged),
      "possible_impact":    "none" | "low" | "medium" | "high",
      "indicators_at_risk": [string],
      "confidence":         "low" | "medium" | "high"
    }
    ... include 1-3 neighbours most plausibly affected. Empty array if none.
  ],
  "confidence": {
    "level":        "low" | "medium" | "high",
    "label":        string (e.g. "Low Confidence — Data Quality Concerns"),
    "score":        integer 0-100,
    "rationale":    string (1-2 sentences explaining the confidence level),
    "data_quality": "poor" | "fair" | "good",
    "factors":      [string] (2-4 bullet points)
  },
  "limitations": [string] (4-6 specific limitations for this context),
  "summary_sentence": string (single sentence for UI card, include confidence level),
  "hedging_note":     string (1 sentence epistemic disclaimer)
}

Calibrate confidence:
  HIGH   (70-100) — stable government, reliable data, well-established patterns
  MEDIUM (35-70)  — normal emerging market uncertainty
  LOW    (0-35)   — conflict zone, data disruption, unusual macro environment,
                    or multiple compounding crises
"""

# User message template — filled in at runtime
USER_TEMPLATE = """\
Analyse this pattern alert and return the JSON explanation.

=== TRIGGERED ALERT ===
Country   : {country_name} ({country_id}) {flag}
Alert     : {alert_label}
Severity  : {severity}
Quarter   : {quarter}
Value     : {trigger_value} {unit}  (threshold: {threshold_value} {unit})
Condition : {condition_met}
Score     : {score}/100

=== ALL CURRENT INDICATORS (this country) ===
{indicators_table}

=== OTHER ALERTS ACTIVE FOR THIS COUNTRY ===
{other_alerts_text}

=== RECENT NEWS SIGNALS (last 7 days, connected to this alert) ===
{news_text}

=== REGIONAL CONTEXT ===
Neighbours on dashboard : {neighbors}
Top export partners     : {export_partners}
Top import partners     : {import_partners}
Data source note        : {data_source_notes}

Remember: output ONLY the JSON object. No markdown. No prose. Start with {{.
"""


# ──────────────────────────────────────────────────────────────────────────────
#  SECTION 4 — HELPER FUNCTIONS
# ──────────────────────────────────────────────────────────────────────────────

def _fmt_indicators_table(indicators: dict) -> str:
    """Format indicators dict as a plain-text table for the prompt."""
    lines = []
    for key, data in indicators.items():
        val   = data.get("value", "?")
        unit  = data.get("unit", "")
        label = data.get("label", key)
        lines.append(f"  {label:<26}: {val} {unit}")
    return "\n".join(lines) if lines else "  (no indicator data provided)"


def _fmt_other_alerts(alerts: list[dict]) -> str:
    """Format other active alerts as a short bullet list."""
    if not alerts:
        return "  (none — this is the only active alert)"
    lines = []
    for a in alerts[:5]:
        lines.append(f"  • {a.get('label', a.get('type', '?'))} [{a.get('severity', '?')}]")
    return "\n".join(lines)


def _fmt_news(news: list[dict]) -> str:
    """Format recent news items for the prompt."""
    if not news:
        return "  (no recent news signals provided)"
    lines = []
    for n in news[:5]:
        days  = n.get("days_ago", "?")
        inds  = ", ".join(n.get("connected_indicators", []))
        lines.append(
            f"  [{n.get('impact_score', '?')}★ | {n.get('sentiment', '?')} | {days}d ago]\n"
            f"  \"{n.get('headline', '')}\"\n"
            f"  Connected: {inds or 'none specified'}"
        )
    return "\n".join(lines)


def _build_user_message(inp: dict) -> str:
    """Build the user message from the input dict."""
    alert      = inp.get("alert", {})
    indicators = inp.get("indicators", {})
    context    = inp.get("context", {})
    trade      = context.get("trade_links", {})

    return USER_TEMPLATE.format(
        country_name      = alert.get("country_name", "Unknown"),
        country_id        = alert.get("country_id", "???"),
        flag              = alert.get("flag", ""),
        alert_label       = alert.get("label", alert.get("type", "Unknown Alert")),
        severity          = alert.get("severity", "?"),
        quarter           = alert.get("quarter", "?"),
        trigger_value     = alert.get("trigger_value", "?"),
        threshold_value   = alert.get("threshold_value", "?"),
        unit              = alert.get("unit", ""),
        condition_met     = alert.get("condition_met", "?"),
        score             = alert.get("score", "?"),
        indicators_table  = _fmt_indicators_table(indicators),
        other_alerts_text = _fmt_other_alerts(inp.get("other_active_alerts", [])),
        news_text         = _fmt_news(inp.get("recent_news", [])),
        neighbors         = ", ".join(context.get("neighbors", [])) or "none",
        export_partners   = ", ".join(trade.get("top_export_partners", [])) or "unknown",
        import_partners   = ", ".join(trade.get("top_import_partners", [])) or "unknown",
        data_source_notes = context.get("data_source_notes", "Standard World Bank / IMF data sources."),
    )


def _extract_json(raw: str) -> dict:
    """
    Robustly extract a JSON object from a Claude response.

    Claude should return pure JSON, but occasionally wraps it in markdown
    code fences or adds a brief prefix. This handles those cases.
    """
    # Strip markdown fences
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.MULTILINE)
    raw = re.sub(r"\s*```$", "", raw.strip(), flags=re.MULTILINE)
    raw = raw.strip()

    # Find first { and last }
    start = raw.find("{")
    end   = raw.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"No JSON object found in response: {raw[:200]}")

    return json.loads(raw[start : end + 1])


def _validate_output(data: dict) -> dict:
    """
    Validate and normalise the parsed output dict.
    Fills in defaults for any missing required fields so the frontend
    never crashes on a KeyError.
    """
    REQUIRED_STRINGS = [
        "what_changed", "why_it_matters", "summary_sentence", "hedging_note",
    ]
    for field in REQUIRED_STRINGS:
        if field not in data or not isinstance(data[field], str):
            data[field] = f"[{field} not available — model returned incomplete response]"

    if "connected_indicators" not in data or not isinstance(data["connected_indicators"], list):
        data["connected_indicators"] = []

    if "affected_countries" not in data or not isinstance(data["affected_countries"], list):
        data["affected_countries"] = []

    if "limitations" not in data or not isinstance(data["limitations"], list):
        data["limitations"] = ["Limitations not provided by model — treat analysis with caution."]

    if "confidence" not in data or not isinstance(data["confidence"], dict):
        data["confidence"] = {
            "level": "low", "label": "Low Confidence",
            "score": 25, "rationale": "Confidence level not returned by model.",
            "data_quality": "unknown", "factors": [],
        }

    return data


# ──────────────────────────────────────────────────────────────────────────────
#  SECTION 5 — MOCK RESPONSES (used when no API key is set)
# ──────────────────────────────────────────────────────────────────────────────

def _build_mock_response(inp: dict) -> dict:
    """
    Returns a realistic-looking pre-written explanation when ANTHROPIC_API_KEY
    is not set. Used in demo mode / local dev without an API key.

    The mock response follows the same structure as the real AI output so
    the frontend renders identically whether live or in demo mode.
    """
    alert      = inp.get("alert", {})
    indicators = inp.get("indicators", {})
    context    = inp.get("context", {})
    country    = alert.get("country_name", "this country")
    atype      = alert.get("type", "UNKNOWN")
    sev        = alert.get("severity", "info")
    val        = alert.get("trigger_value", "?")
    thr        = alert.get("threshold_value", "?")
    unit       = alert.get("unit", "")
    quarter    = alert.get("quarter", "?")
    neighbors  = context.get("neighbors", [])

    # Confidence defaults to LOW for critical alerts, MEDIUM otherwise
    conf_level = "low" if sev == "critical" else "medium"
    conf_score = 25 if sev == "critical" else 50
    data_qual  = "poor" if "MMR" in alert.get("country_id", "") else "fair"

    # Generic section texts keyed by alert type
    TEMPLATES: dict[str, dict] = {
        "INFLATION_PRESSURE": {
            "what_changed": (
                f"{country}'s inflation reached {val}{unit} in {quarter}, "
                f"crossing the {thr}{unit} threshold. This may suggest persistent "
                f"price pressures that could be linked to currency depreciation and "
                f"supply-side disruptions."
            ),
            "why_it_matters": (
                f"Inflation at this level could indicate erosion of household purchasing "
                f"power, particularly for basic goods and food imports. This pattern is "
                f"often associated with weakened domestic demand and possible monetary "
                f"policy credibility concerns. Needs more data to confirm the primary driver."
            ),
        },
        "EXPORT_STRESS": {
            "what_changed": (
                f"{country}'s exports fell to {val}{unit} in {quarter}, "
                f"below the {thr}{unit} threshold. This may suggest weakening external "
                f"demand or supply-side disruptions in key export sectors."
            ),
            "why_it_matters": (
                f"Export decline could indicate reduced foreign exchange earnings, which "
                f"may put pressure on the trade balance and currency. This pattern is often "
                f"associated with slowing regional trade activity and possible impact on "
                f"GDP growth if the manufacturing sector is affected."
            ),
        },
        "CURRENCY_PRESSURE": {
            "what_changed": (
                f"{country}'s exchange rate reached {val}{unit} in {quarter}, "
                f"indicating possible depreciation pressure beyond the {thr}{unit} baseline. "
                f"This may suggest capital outflow pressures or reduced foreign exchange "
                f"reserve support."
            ),
            "why_it_matters": (
                f"Currency depreciation at this level could indicate import cost increases "
                f"that feed into consumer prices. For economies with high import dependency, "
                f"this pattern is often associated with inflation acceleration. Possible "
                f"impact on debt servicing costs if external debt exists."
            ),
        },
        "POLITICAL_INSTABILITY": {
            "what_changed": (
                f"{country}'s political risk news count reached {val}{unit} in {quarter}, "
                f"an early warning signal that may suggest elevated governance or security "
                f"uncertainty. This exceeds the {thr}{unit} baseline by a meaningful margin."
            ),
            "why_it_matters": (
                f"Elevated political risk signals could indicate reduced investor confidence "
                f"and possible impact on FDI inflows. This pattern is often associated with "
                f"higher business environment uncertainty. Needs more data to determine "
                f"whether this reflects short-term events or a structural deterioration."
            ),
        },
        "FDI_SLOWDOWN": {
            "what_changed": (
                f"{country}'s FDI inflows reached {val}{unit} in {quarter}, "
                f"below the {thr}{unit} baseline. This may suggest declining investor "
                f"confidence or reallocation of investment to competing economies."
            ),
            "why_it_matters": (
                f"Reduced FDI could indicate slower capital formation and possible impact "
                f"on employment and technology transfer. This pattern is often associated "
                f"with medium-term growth moderation. Needs more data on sector composition "
                f"to assess whether this affects export-oriented industries."
            ),
        },
        "REGIONAL_SPILLOVER": {
            "what_changed": (
                f"{country} is showing possible regional spillover risk in {quarter}. "
                f"Multiple neighbouring countries appear to have elevated stress signals "
                f"that may suggest shared regional economic pressures."
            ),
            "why_it_matters": (
                f"Regional co-movement of economic stress could indicate shared exposure "
                f"to common shocks such as trade slowdowns, commodity price changes, or "
                f"currency pressure. This pattern warrants monitoring of bilateral trade "
                f"and financial flows across the region."
            ),
        },
    }

    tmpl = TEMPLATES.get(atype, {
        "what_changed": (
            f"{country}'s {alert.get('label', 'indicator')} reached {val}{unit} "
            f"in {quarter}, crossing the {thr}{unit} threshold. This may suggest "
            f"a developing risk condition that warrants monitoring."
        ),
        "why_it_matters": (
            f"This alert may indicate an economic stress condition that could affect "
            f"multiple sectors. The pattern is often associated with broader macro "
            f"vulnerabilities. Needs more data to confirm the scope of impact."
        ),
    })

    # Build connected indicators from top 3 by value divergence
    inds = []
    ind_data = indicators or {}
    for key, meta in list(ind_data.items())[:3]:
        inds.append({
            "key":          key,
            "label":        meta.get("label", key),
            "value":        meta.get("value", 0),
            "unit":         meta.get("unit", ""),
            "relationship": (
                f"This indicator appears consistent with the {alert.get('label', 'alert')} "
                f"signal. The relationship warrants monitoring but needs more data to "
                f"confirm direction of influence."
            ),
            "direction": "unclear",
        })

    # Build affected countries from neighbours
    affected = []
    for iso3 in (neighbors or [])[:2]:
        name_map = {
            "THA": ("Thailand", "🇹🇭"),
            "VNM": ("Vietnam",  "🇻🇳"),
            "MMR": ("Myanmar",  "🇲🇲"),
            "KHM": ("Cambodia", "🇰🇭"),
            "SGP": ("Singapore","🇸🇬"),
        }
        name, flag = name_map.get(iso3, (iso3, "🌏"))
        affected.append({
            "country_id":         iso3,
            "country_name":       name,
            "flag":               flag,
            "mechanism":          (
                f"Possible spillover through bilateral trade and shared regional financial "
                f"conditions. The impact is speculative and would require more bilateral "
                f"data to assess with confidence."
            ),
            "possible_impact":    "low",
            "indicators_at_risk": ["tradeNewsCount"],
            "confidence":         "low",
        })

    return {
        "alert_type":   atype,
        "country_id":   alert.get("country_id", "???"),
        "country_name": country,
        "severity":     sev,
        "quarter":      quarter,

        "what_changed":          tmpl["what_changed"],
        "why_it_matters":        tmpl["why_it_matters"],
        "connected_indicators":  inds,
        "affected_countries":    affected,
        "confidence": {
            "level":        conf_level,
            "label":        f"{'Low' if conf_level == 'low' else 'Medium'} Confidence — Demo Mode",
            "score":        conf_score,
            "rationale": (
                "Demo mode active — no ANTHROPIC_API_KEY set. "
                "Add ANTHROPIC_API_KEY to backend/.env for live AI analysis. "
                "Confidence level is approximate for the selected country/alert combination."
            ),
            "data_quality": data_qual,
            "factors": [
                "Demo mode: using pre-written template response",
                f"Severity level: {sev}",
                f"Data quality estimate: {data_qual}",
            ],
        },
        "limitations": [
            "This is a demo/template response — not a live AI analysis",
            "Add ANTHROPIC_API_KEY to backend/.env to enable real-time AI explanations",
            "Indicator relationships shown are generic defaults, not context-specific analysis",
            "Confidence scores and country spillover assessments require live AI to calibrate",
        ],
        "summary_sentence": (
            f"{country} {alert.get('label', 'alert')} is an early warning signal "
            f"({val}{unit} vs {thr}{unit} threshold). "
            f"[Demo mode — add API key for live analysis]"
        ),
        "hedging_note": (
            "This is a template response. For context-specific hedged analysis with "
            "calibrated confidence levels, add an Anthropic API key."
        ),
        "is_ai":        False,
        "model_used":   "demo",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# ──────────────────────────────────────────────────────────────────────────────
#  SECTION 6 — MAIN FUNCTION
# ──────────────────────────────────────────────────────────────────────────────

def build_explanation(
    inp: dict,
    api_key: str = "",
    model:   str = "claude-haiku-4-5",
) -> dict:
    """
    Generate a structured AI explanation for a pattern alert.

    Parameters
    ----------
    inp     : dict matching INPUT_JSON_SCHEMA
    api_key : Anthropic API key (empty → demo mode)
    model   : Claude model name

    Returns
    -------
    dict matching OUTPUT_JSON_SCHEMA, always — never raises to the caller.

    Error handling strategy:
      - No API key  → return mock response (is_ai=False)
      - Claude API error → return mock response with error note
      - JSON parse error → return mock response with raw text saved
      - Any other error  → return mock response with exception info

    The function NEVER raises — the endpoint always gets a usable response.
    """
    alert = inp.get("alert", {})

    if not api_key:
        result = _build_mock_response(inp)
        return result

    # ── Live AI path ──────────────────────────────────────────────────────────
    try:
        import anthropic   # imported here so the module works without the package

        client       = anthropic.Anthropic(api_key=api_key)
        user_message = _build_user_message(inp)

        response = client.messages.create(
            model      = model,
            max_tokens = 1500,
            system     = SYSTEM_PROMPT,
            messages   = [
                {"role": "user",      "content": user_message},
                # Assistant prefill: forces response to begin with { (JSON)
                {"role": "assistant", "content": "{"},
            ],
        )

        # The response starts from after our prefill "{" — prepend it back
        raw_text = "{" + response.content[0].text

        parsed   = _extract_json(raw_text)
        validated = _validate_output(parsed)

        # Inject metadata that Claude doesn't add itself
        validated["alert_type"]   = alert.get("type", "UNKNOWN")
        validated["country_id"]   = alert.get("country_id", "???")
        validated["country_name"] = alert.get("country_name", "Unknown")
        validated["severity"]     = alert.get("severity", "info")
        validated["quarter"]      = alert.get("quarter", "?")
        validated["is_ai"]        = True
        validated["model_used"]   = model
        validated["generated_at"] = datetime.now(timezone.utc).isoformat()

        return validated

    except Exception as exc:
        # Fallback: always return something useful
        fallback = _build_mock_response(inp)
        fallback["limitations"] = [
            f"Live AI call failed: {type(exc).__name__}: {str(exc)[:120]}",
            "Showing pre-written template response as fallback",
        ] + fallback.get("limitations", [])
        fallback["model_used"] = f"demo (ai error: {type(exc).__name__})"
        return fallback
