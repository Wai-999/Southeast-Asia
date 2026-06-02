"""
services/claude_service.py — Claude API integration for AI-generated explanations.

Provides:
  generate_explanation(req)  →  ExplanationResponse
  generate_alert_explanation(country_name, alert_message, context)  →  str  (legacy)

Safety design:
  • Prompt contains explicit safety rules that Claude must follow
  • JSON output is validated and sanitised before returning
  • Data completeness is computed deterministically (never by Claude)
  • Fallback response returned when Claude is unavailable or returns malformed JSON
  • No prediction language, no named individuals, no investment advice
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Optional

import anthropic

from ..config import settings
from ..models import Indicator, IndicatorValue as IndicatorValueModel
from ..schemas.explanation import (
    ExplanationRequest,
    ExplanationResponse,
    DetailedExplanation,
    ConnectedIndicator,
    RegionalImpact,
    DataLimitation,
    ConfidenceAssessment,
    WARNING_DISPLAY,
)

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

MAX_TOKENS   = 1800    # enough for full structured JSON, not too expensive
TEMPERATURE  = 0.3     # low = more consistent, less hallucination risk

# Countries that share borders / trade lanes with each ASEAN member
# Used to validate / supplement regional_impact in the AI response
ASEAN_NEIGHBOURS: dict[str, list[str]] = {
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

# ─────────────────────────────────────────────────────────────────────────────
# PROMPT TEMPLATE
# The prompt is the primary safety mechanism.
# Rules are numbered and placed BEFORE the data so Claude encounters them first.
# ─────────────────────────────────────────────────────────────────────────────

PROMPT_TEMPLATE = """\
You are an economic analysis assistant embedded in a Southeast Asia Economic and Political \
Change Dashboard. Your role is to help analysts understand data patterns.

You are NOT a financial advisor, market forecaster, or policy prescriptor.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SAFETY RULES — YOU MUST FOLLOW ALL OF THESE EXACTLY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. DATA-ONLY CLAIMS: Only describe what the provided numbers show.
   Do not invent statistics, fabricate events, or cite facts not in the input.

2. HEDGED LANGUAGE: Use "suggests", "may indicate", "appears consistent with",
   "could reflect", "is associated with". Never write "will", "definitely",
   "certainly", "guaranteed", or "is going to".

3. NO NAMED INDIVIDUALS: Do not mention any politician, minister, CEO,
   central bank governor, or any specific person by name.

4. NO PRICE FORECASTS: Do not predict future exchange rates, stock levels,
   commodity prices, or any asset values.

5. CALIBRATED CONFIDENCE: If data is sparse, contradictory, or incomplete,
   say so. A "medium" confidence with clear caveats is more useful than
   false certainty. Do not claim confidence you don't have.

6. MANDATORY LIMITATIONS: You must include at least 2 specific, concrete
   data limitations relevant to THIS dataset. Generic disclaimers are not enough.

7. OBSERVATION vs INFERENCE: Clearly distinguish what the data directly shows
   from what you are inferring. Use phrases like "the data directly shows...
   one possible interpretation is...".

8. NO INVESTMENT ADVICE: This output is for analytical purposes only.
   Never suggest buying, selling, hedging, or any financial action.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INPUT DATA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

COUNTRY: {country_name} ({country_iso3})
ANALYSIS PERIOD: {period}

ECONOMIC INDICATORS:
{indicators_text}

ACTIVE PATTERN ALERTS:
{alerts_text}

NEWS SIGNALS (past 30 days, GDELT source):
{news_text}
{additional_context_block}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT INSTRUCTION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Return ONLY a valid JSON object. No markdown fences, no text before or after the JSON.
Use this exact schema (replace angle-bracket descriptions with your content):

{{
  "short_summary": "<2-3 sentences. State the most significant patterns. Present tense. No predictions. Include at least one specific number from the data.>",

  "detailed_explanation": {{
    "what_changed": "<1-2 paragraphs. Walk through each indicator that changed, with the exact numbers. State direction and magnitude.>",
    "why_it_may_matter": "<1-2 paragraphs. Explain the economic significance using hedged language. Connect to broader SEA context if supported by data.>",
    "which_indicators_connected": "<1 paragraph. Identify which indicators are moving together or in opposing directions, and what that pattern suggests.>"
  }},

  "connected_indicators": [
    {{
      "name": "<indicator name, e.g. 'Exchange Rate'>",
      "relationship": "<one of: leads | lags | amplifies | dampens | correlates>",
      "explanation": "<one sentence — be specific about the direction and mechanism>"
    }}
  ],

  "regional_impact": {{
    "likely_affected_countries": ["<ISO3 — only list countries plausibly affected via trade or financial channels>"],
    "primary_channel": "<one of: trade | capital_flows | migration | sentiment | supply_chain>",
    "severity_assessment": "<one of: minor | moderate | significant>",
    "explanation": "<1 paragraph. Explain the mechanism, not just the conclusion. Use hedged language.>"
  }},

  "warning_level": "<one of: none | watch | caution | alert | critical>",
  "warning_reasoning": "<one sentence explaining why this level was chosen based on the data>",

  "confidence": {{
    "level": "<one of: low | medium | high>",
    "reasoning": "<one sentence — be specific about what limits or supports confidence>"
  }},

  "data_limitations": [
    {{
      "limitation": "<specific gap — e.g. 'No monthly CPI breakdown available, only annual average'>",
      "impact_on_analysis": "<how this affects the conclusions — be concrete>"
    }}
  ]
}}
"""

# ─────────────────────────────────────────────────────────────────────────────
# PROMPT BUILDERS
# ─────────────────────────────────────────────────────────────────────────────

def _fmt_indicator(label: str, ind, unit_override: str = "") -> str:
    """Format one IndicatorValue for the prompt."""
    if ind is None:
        return f"  {label}: [not available]"

    unit = unit_override or ind.unit or ""
    unit_str = f" {unit}" if unit else ""
    line = f"  {label}: {ind.value}{unit_str}"

    if ind.previous_value is not None:
        delta = ind.value - ind.previous_value
        pct   = ind.yoy_change
        direction = "▲" if delta > 0 else "▼" if delta < 0 else "→"
        pct_str = f"{abs(pct):.1f}%" if pct is not None else "n/a"
        line += f"  (prev: {ind.previous_value}{unit_str}  {direction}{pct_str} YoY)"

    return line


def _build_indicators_text(req: ExplanationRequest) -> str:
    lines = [
        _fmt_indicator("GDP Growth",       req.gdp_growth,    "%"),
        _fmt_indicator("Inflation (CPI)",  req.inflation,     "%"),
        _fmt_indicator("Exports",          req.exports,       "USD B"),
        _fmt_indicator("Imports",          req.imports,       "USD B"),
        _fmt_indicator("Exchange Rate",    req.exchange_rate, "local per USD"),
        _fmt_indicator("FDI Net Inflows",  req.fdi,           "USD B"),
        _fmt_indicator("Public Debt",      req.public_debt,   "% of GDP"),
    ]
    return "\n".join(lines)


def _build_news_text(req: ExplanationRequest) -> str:
    if not req.news_signals:
        return "  [No news signal data provided]"
    lines = []
    for ns in req.news_signals:
        base = f"  {ns.category.replace('_', ' ').title()}: {ns.article_count} articles"
        if ns.baseline_count and ns.baseline_count > 0:
            ratio = ns.article_count / ns.baseline_count
            base += f" ({ratio:.1f}× baseline of {ns.baseline_count})"
        if ns.change_vs_baseline_pct is not None:
            sign = "+" if ns.change_vs_baseline_pct > 0 else ""
            base += f" [{sign}{ns.change_vs_baseline_pct:.0f}% vs baseline]"
        if ns.sample_topics:
            topics = " | ".join(ns.sample_topics[:3])
            base += f"\n    Topics: {topics}"
        lines.append(base)
    return "\n".join(lines)


def _build_alerts_text(req: ExplanationRequest) -> str:
    if not req.active_alerts:
        return "  [No pattern alerts currently active]"
    lines = []
    for a in req.active_alerts:
        line = f"  [{a.severity.upper()}] {a.alert_label}  (score: {a.score:.0f}/100)"
        for cond in a.conditions_met:
            line += f"\n    • {cond}"
        lines.append(line)
    return "\n".join(lines)


def build_prompt(req: ExplanationRequest) -> str:
    """Assemble the full prompt string from a request."""
    additional = ""
    if req.additional_context:
        additional = f"\nADDITIONAL ANALYST CONTEXT:\n  {req.additional_context}\n"

    return PROMPT_TEMPLATE.format(
        country_name            = req.country_name,
        country_iso3            = req.country_iso3,
        period                  = req.period,
        indicators_text         = _build_indicators_text(req),
        alerts_text             = _build_alerts_text(req),
        news_text               = _build_news_text(req),
        additional_context_block = additional,
    )


# ─────────────────────────────────────────────────────────────────────────────
# DATA COMPLETENESS  (computed deterministically — not by Claude)
# ─────────────────────────────────────────────────────────────────────────────

def compute_data_completeness(req: ExplanationRequest) -> float:
    """
    Returns 0.0–1.0 based on how much data is present.
    Used to set confidence.data_completeness_score independently of Claude.
    """
    indicator_slots = [
        req.gdp_growth, req.inflation, req.exports,
        req.imports, req.exchange_rate, req.fdi, req.public_debt,
    ]
    total    = len(indicator_slots)
    present  = sum(1 for x in indicator_slots if x is not None)
    with_yoy = sum(
        1 for x in indicator_slots
        if x is not None and x.previous_value is not None
    )

    base        = present / total                         # 0–1
    yoy_bonus   = (with_yoy / total) * 0.10              # up to +0.10
    news_bonus  = 0.08 if req.news_signals else 0.0
    alert_bonus = 0.05 if req.active_alerts else 0.0

    return round(min(1.0, base * 0.77 + yoy_bonus + news_bonus + alert_bonus), 2)


# ─────────────────────────────────────────────────────────────────────────────
# JSON PARSER  (handles markdown fences + best-effort extraction)
# ─────────────────────────────────────────────────────────────────────────────

def _extract_json(text: str) -> dict:
    """Try multiple strategies to extract JSON from Claude's response."""
    text = text.strip()

    # Strategy 1: direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strategy 2: strip markdown fences
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except json.JSONDecodeError:
            pass

    # Strategy 3: find outermost JSON object
    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    raise ValueError("Could not extract valid JSON from Claude response")


def _sanitise_warning_level(val: str) -> str:
    valid = {"none", "watch", "caution", "alert", "critical"}
    cleaned = str(val).strip().lower()
    return cleaned if cleaned in valid else "watch"


def _sanitise_severity(val: str) -> str:
    valid = {"minor", "moderate", "significant"}
    cleaned = str(val).strip().lower()
    return cleaned if cleaned in valid else "moderate"


def _sanitise_channel(val: str) -> str:
    valid = {"trade", "capital_flows", "migration", "sentiment", "supply_chain"}
    cleaned = str(val).strip().lower()
    return cleaned if cleaned in valid else "trade"


def _sanitise_relationship(val: str) -> str:
    valid = {"leads", "lags", "amplifies", "dampens", "correlates"}
    cleaned = str(val).strip().lower()
    return cleaned if cleaned in valid else "correlates"


def _sanitise_confidence_level(val: str) -> str:
    valid = {"low", "medium", "high"}
    cleaned = str(val).strip().lower()
    return cleaned if cleaned in valid else "medium"


def _build_response_from_json(
    raw: dict,
    req: ExplanationRequest,
    model: str,
    tokens_used: Optional[int],
    completeness: float,
) -> ExplanationResponse:
    """Convert parsed Claude JSON into a validated ExplanationResponse."""

    # Section 1
    short_summary = str(raw.get("short_summary", "Summary not available."))

    # Section 2
    det = raw.get("detailed_explanation", {})
    detailed = DetailedExplanation(
        what_changed               = str(det.get("what_changed", "—")),
        why_it_may_matter          = str(det.get("why_it_may_matter", "—")),
        which_indicators_connected = str(det.get("which_indicators_connected", "—")),
    )

    # Section 3
    connected = []
    for c in raw.get("connected_indicators", []):
        try:
            connected.append(ConnectedIndicator(
                name         = str(c.get("name", "Unknown")),
                relationship = _sanitise_relationship(c.get("relationship", "correlates")),
                explanation  = str(c.get("explanation", "—")),
            ))
        except Exception:
            continue

    # Section 4
    ri  = raw.get("regional_impact", {})
    # Validate that listed countries are real ASEAN neighbours (safety check)
    allowed_neighbours = ASEAN_NEIGHBOURS.get(req.country_iso3, []) + ["CHN", "IND", "JPN", "USA"]
    raw_countries = [str(c).upper() for c in ri.get("likely_affected_countries", [])]
    filtered_countries = [c for c in raw_countries if c in allowed_neighbours][:4]

    regional = RegionalImpact(
        likely_affected_countries = filtered_countries,
        primary_channel           = _sanitise_channel(ri.get("primary_channel", "trade")),
        severity_assessment       = _sanitise_severity(ri.get("severity_assessment", "moderate")),
        explanation               = str(ri.get("explanation", "—")),
    )

    # Section 5
    warning_level     = _sanitise_warning_level(raw.get("warning_level", "watch"))
    warning_reasoning = str(raw.get("warning_reasoning", "—"))
    wd = WARNING_DISPLAY[warning_level]

    # Section 6a: Confidence
    conf_raw = raw.get("confidence", {})
    confidence = ConfidenceAssessment(
        level                   = _sanitise_confidence_level(conf_raw.get("level", "medium")),
        data_completeness_score = completeness,   # always from our deterministic calc
        reasoning               = str(conf_raw.get("reasoning", "—")),
    )

    # Section 6b: Limitations
    limitations = []
    for lim in raw.get("data_limitations", []):
        try:
            limitations.append(DataLimitation(
                limitation          = str(lim.get("limitation", "—")),
                impact_on_analysis  = str(lim.get("impact_on_analysis", "—")),
            ))
        except Exception:
            continue

    # Guarantee at least 2 limitations
    if len(limitations) < 2:
        limitations.append(DataLimitation(
            limitation         = "Data completeness is limited for this period.",
            impact_on_analysis = "Some conclusions may be under-supported by available data.",
        ))

    return ExplanationResponse(
        country_iso3         = req.country_iso3,
        country_name         = req.country_name,
        period               = req.period,
        generated_at         = datetime.now(timezone.utc).isoformat(),
        model_used           = model,
        tokens_used          = tokens_used,
        short_summary        = short_summary,
        detailed_explanation = detailed,
        connected_indicators = connected,
        regional_impact      = regional,
        warning_level        = warning_level,
        warning_reasoning    = warning_reasoning,
        warning_color        = wd["color"],
        warning_bg           = wd["bg"],
        warning_label        = wd["label"],
        confidence           = confidence,
        data_limitations     = limitations,
        is_fallback          = False,
    )


# ─────────────────────────────────────────────────────────────────────────────
# FALLBACK RESPONSE  (returned when Claude fails)
# ─────────────────────────────────────────────────────────────────────────────

def _fallback_response(req: ExplanationRequest, error_msg: str) -> ExplanationResponse:
    """
    Structured response returned when Claude is unavailable or returns malformed output.
    The fallback is honest about its status — it never pretends to be AI-generated.
    """
    completeness = compute_data_completeness(req)
    wd = WARNING_DISPLAY["watch"]

    # Build a minimal rule-based summary from alert data
    if req.active_alerts:
        worst = max(req.active_alerts, key=lambda a: a.score)
        summary = (
            f"{req.country_name} has {len(req.active_alerts)} active pattern alert(s) "
            f"for {req.period}. Most significant: {worst.alert_label} "
            f"(severity: {worst.severity}, score: {worst.score:.0f}/100). "
            f"AI explanation is temporarily unavailable — please review the raw indicators."
        )
    else:
        summary = (
            f"Indicator data for {req.country_name} ({req.period}) has been received. "
            f"AI explanation is temporarily unavailable. Please review the raw indicators directly."
        )

    return ExplanationResponse(
        country_iso3  = req.country_iso3,
        country_name  = req.country_name,
        period        = req.period,
        generated_at  = datetime.now(timezone.utc).isoformat(),
        model_used    = "fallback",
        tokens_used   = None,
        short_summary = summary,
        detailed_explanation = DetailedExplanation(
            what_changed               = "AI explanation unavailable. Raw data is present above.",
            why_it_may_matter          = "Please review the indicator values and active alerts directly.",
            which_indicators_connected = "—",
        ),
        connected_indicators = [],
        regional_impact      = RegionalImpact(
            likely_affected_countries = ASEAN_NEIGHBOURS.get(req.country_iso3, [])[:3],
            primary_channel           = "trade",
            severity_assessment       = "moderate",
            explanation               = "Regional impact analysis unavailable in fallback mode.",
        ),
        warning_level     = "watch",
        warning_reasoning = "Default level assigned — AI analysis unavailable.",
        warning_color     = wd["color"],
        warning_bg        = wd["bg"],
        warning_label     = wd["label"],
        confidence        = ConfidenceAssessment(
            level                   = "low",
            data_completeness_score = completeness,
            reasoning               = f"AI service error: {error_msg[:120]}",
        ),
        data_limitations  = [
            DataLimitation(
                limitation         = "AI explanation service unavailable.",
                impact_on_analysis = "Full narrative analysis cannot be generated at this time.",
            )
        ],
        is_fallback = True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# MAIN SERVICE FUNCTION
# ─────────────────────────────────────────────────────────────────────────────

def generate_explanation(req: ExplanationRequest) -> ExplanationResponse:
    """
    Generate a structured AI explanation for a country snapshot.

    Calls Claude synchronously, parses the JSON response,
    validates all fields, and returns an ExplanationResponse.

    Falls back gracefully if Claude is unavailable or returns malformed output.
    """
    completeness = compute_data_completeness(req)
    model        = getattr(settings, "claude_model", "claude-haiku-4-5")
    prompt       = build_prompt(req)

    logger.info(
        "Explanation requested: %s / %s  (completeness=%.2f, model=%s)",
        req.country_iso3, req.period, completeness, model,
    )

    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

        message = client.messages.create(
            model       = model,
            max_tokens  = MAX_TOKENS,
            temperature = TEMPERATURE,
            system      = (
                "You are an economic analysis assistant for a Southeast Asia dashboard. "
                "You always return valid JSON only — no prose, no markdown fences."
            ),
            messages    = [{"role": "user", "content": prompt}],
        )

        raw_text   = message.content[0].text
        tokens     = message.usage.input_tokens + message.usage.output_tokens
        parsed     = _extract_json(raw_text)

        logger.info("Claude responded: %d tokens, JSON parsed OK", tokens)

        return _build_response_from_json(parsed, req, model, tokens, completeness)

    except anthropic.APIConnectionError as e:
        logger.error("Claude API connection error: %s", e)
        return _fallback_response(req, f"Connection error: {e}")

    except anthropic.AuthenticationError as e:
        logger.error("Claude API auth error — check ANTHROPIC_API_KEY")
        return _fallback_response(req, "Authentication error — API key may be invalid or missing")

    except anthropic.RateLimitError as e:
        logger.warning("Claude rate limit hit")
        return _fallback_response(req, "Rate limit reached — please retry in a moment")

    except anthropic.APIStatusError as e:
        logger.error("Claude API status error %d: %s", e.status_code, e.message)
        return _fallback_response(req, f"API error {e.status_code}")

    except ValueError as e:
        logger.error("JSON parse failed: %s", e)
        return _fallback_response(req, f"Response parse error: {e}")

    except Exception as e:
        logger.exception("Unexpected error in generate_explanation")
        return _fallback_response(req, f"Unexpected error: {type(e).__name__}")


# ─────────────────────────────────────────────────────────────────────────────
# LEGACY FUNCTIONS  (kept for backward compatibility with existing router)
# ─────────────────────────────────────────────────────────────────────────────

def generate_alert_explanation(
    country_name: str,
    alert_message: str,
    context: str,
) -> str:
    """
    Legacy function — returns a plain-text alert explanation.
    New code should use generate_explanation() with full ExplanationRequest.
    """
    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        model  = getattr(settings, "claude_model", "claude-haiku-4-5")

        prompt = (
            f"Country: {country_name}\n"
            f"Alert: {alert_message}\n"
            f"Context: {context}\n\n"
            "In 2-3 sentences, explain what this alert means for this country's economy "
            "and what the underlying data suggests. Use hedged language ('may indicate', "
            "'suggests', 'consistent with'). Do not make predictions or name individuals."
        )

        message = client.messages.create(
            model     = model,
            max_tokens = 300,
            messages  = [{"role": "user", "content": prompt}],
        )
        return message.content[0].text

    except Exception as e:
        logger.error("Legacy alert explanation error: %s", e)
        return (
            f"AI explanation temporarily unavailable. "
            f"Alert: {alert_message} — please review raw indicator data."
        )
