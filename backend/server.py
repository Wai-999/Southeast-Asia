"""
server.py — SEA Dashboard MVP Backend
Single-file FastAPI server.  No database required.

Run:
    cd backend
    pip install fastapi uvicorn python-dotenv anthropic
    uvicorn server:app --reload --port 8000

Docs:  http://localhost:8000/docs

ENDPOINTS
---------
  GET  /health                 — Server + AI status
  GET  /countries              — List all countries (filter: risk, region)
  GET  /countries/{iso3}       — Single country + indicators
  GET  /news                   — News events (filter: country, category, sentiment)
  GET  /alerts                 — Pattern alerts (filter: country, severity, active)
  POST /explain/alert          — Legacy: flat-text AI explanation
  POST /explain/pattern        — NEW: structured 6-section AI explanation
  GET  /explain/schema         — Returns input/output JSON schemas for reference
"""

import os
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Import the AI engine (all prompt/schema/logic lives there)
try:
    from ai_engine import (
        build_explanation,
        INPUT_JSON_SCHEMA,
        OUTPUT_JSON_SCHEMA,
        SYSTEM_PROMPT,
    )
    _AI_ENGINE_AVAILABLE = True
except ImportError:
    _AI_ENGINE_AVAILABLE = False

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL      = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5")

app = FastAPI(
    title       = "SEA Change Dashboard — MVP API",
    description = "Local dev server. No database required. Sample data only.",
    version     = "1.0.0-mvp",
    docs_url    = "/docs",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins     = ["*"],
    allow_credentials = False,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)

# ─────────────────────────────────────────────────────────────────────────────
# SAMPLE DATA  (mirrors frontend/data/sample-data.ts)
# ─────────────────────────────────────────────────────────────────────────────

COUNTRIES = [
    {"id":"MMR","name":"Myanmar",     "flagEmoji":"🇲🇲","capital":"Naypyidaw",           "currency":"MMK","riskLevel":"critical","region":"ASEAN"},
    {"id":"THA","name":"Thailand",    "flagEmoji":"🇹🇭","capital":"Bangkok",             "currency":"THB","riskLevel":"medium",  "region":"ASEAN"},
    {"id":"VNM","name":"Vietnam",     "flagEmoji":"🇻🇳","capital":"Hanoi",               "currency":"VND","riskLevel":"low",     "region":"ASEAN"},
    {"id":"KHM","name":"Cambodia",    "flagEmoji":"🇰🇭","capital":"Phnom Penh",         "currency":"KHR","riskLevel":"medium",  "region":"ASEAN"},
    {"id":"LAO","name":"Laos",        "flagEmoji":"🇱🇦","capital":"Vientiane",          "currency":"LAK","riskLevel":"high",    "region":"ASEAN"},
    {"id":"MYS","name":"Malaysia",    "flagEmoji":"🇲🇾","capital":"Kuala Lumpur",       "currency":"MYR","riskLevel":"low",     "region":"ASEAN"},
    {"id":"SGP","name":"Singapore",   "flagEmoji":"🇸🇬","capital":"Singapore",          "currency":"SGD","riskLevel":"low",     "region":"ASEAN"},
    {"id":"IDN","name":"Indonesia",   "flagEmoji":"🇮🇩","capital":"Jakarta",            "currency":"IDR","riskLevel":"medium",  "region":"ASEAN"},
    {"id":"PHL","name":"Philippines", "flagEmoji":"🇵🇭","capital":"Manila",             "currency":"PHP","riskLevel":"medium",  "region":"ASEAN"},
    {"id":"BRN","name":"Brunei",      "flagEmoji":"🇧🇳","capital":"Bandar Seri Begawan","currency":"BND","riskLevel":"low",     "region":"ASEAN"},
]

INDICATORS = {
    "MMR": {"gdpGrowth":-2.1, "inflation":26.8,"unemployment":2.8, "tradeBalanceB":-2.4, "fdiInflowsB":0.4,  "govtDebt":60.2, "currentAccount":-3.8, "politicalStability":-2.3,"tourismArrivals":0.1},
    "THA": {"gdpGrowth": 2.5, "inflation": 1.0,"unemployment":1.0, "tradeBalanceB":14.8, "fdiInflowsB":9.1,  "govtDebt":62.3, "currentAccount": 2.5, "politicalStability":-0.2,"tourismArrivals":28.1},
    "VNM": {"gdpGrowth": 7.1, "inflation": 3.6,"unemployment":2.1, "tradeBalanceB":20.4, "fdiInflowsB":18.0, "govtDebt":36.5, "currentAccount": 5.2, "politicalStability": 0.4,"tourismArrivals":17.5},
    "KHM": {"gdpGrowth": 5.8, "inflation": 2.2,"unemployment":0.2, "tradeBalanceB":-4.8, "fdiInflowsB":3.4,  "govtDebt":32.4, "currentAccount":-8.1, "politicalStability":-0.8,"tourismArrivals":5.4},
    "LAO": {"gdpGrowth": 3.5, "inflation":21.1,"unemployment":1.4, "tradeBalanceB":-2.1, "fdiInflowsB":0.9,  "govtDebt":108.2,"currentAccount":-9.4, "politicalStability": 0.1,"tourismArrivals":1.4},
    "MYS": {"gdpGrowth": 4.4, "inflation": 2.0,"unemployment":3.4, "tradeBalanceB":42.1, "fdiInflowsB":13.5, "govtDebt":64.2, "currentAccount": 1.8, "politicalStability": 0.4,"tourismArrivals":26.1},
    "SGP": {"gdpGrowth": 3.6, "inflation": 2.4,"unemployment":2.0, "tradeBalanceB":82.0, "fdiInflowsB":60.2, "govtDebt":167.8,"currentAccount":17.6, "politicalStability": 1.3,"tourismArrivals":16.5},
    "IDN": {"gdpGrowth": 5.0, "inflation": 2.8,"unemployment":5.3, "tradeBalanceB":29.8, "fdiInflowsB":22.0, "govtDebt":39.4, "currentAccount":-0.9, "politicalStability":-0.4,"tourismArrivals":14.0},
    "PHL": {"gdpGrowth": 5.5, "inflation": 3.2,"unemployment":4.5, "tradeBalanceB":-50.1,"fdiInflowsB":9.8,  "govtDebt":60.2, "currentAccount":-2.6, "politicalStability":-1.0,"tourismArrivals":5.9},
    "BRN": {"gdpGrowth": 1.5, "inflation": 0.5,"unemployment":4.9, "tradeBalanceB": 5.2, "fdiInflowsB":0.5,  "govtDebt":2.3,  "currentAccount":17.4, "politicalStability": 0.6,"tourismArrivals":0.3},
}

NEWS = [
    {"id":1, "countryId":"MMR","headline":"Myanmar Resistance Forces Capture Third Border Town","summary":"Opposition forces advanced in Shan State, marking a strategic milestone in the ongoing conflict.","category":"security","sentiment":"negative","sentimentScore":-0.82,"publishedAt":"2024-12-01T08:30:00Z","sourceName":"The Irrawaddy","impactLevel":5,"impactedIndicators":["gdpGrowth","fdiInflowsB"]},
    {"id":2, "countryId":"LAO","headline":"Laos Kip Loses 8% in November as Reserves Near Critical Low","summary":"The kip continued its sharp decline amid warnings that reserves may cover less than 1 month of imports.","category":"economy","sentiment":"negative","sentimentScore":-0.91,"publishedAt":"2024-11-30T11:00:00Z","sourceName":"RFA","impactLevel":5,"impactedIndicators":["inflation","currentAccount"]},
    {"id":3, "countryId":"VNM","headline":"Vietnam FDI Hits Record $18B as Samsung Expands Hanoi Factories","summary":"Foreign direct investment surged as electronics firms diversified supply chains away from China.","category":"economy","sentiment":"positive","sentimentScore": 0.74,"publishedAt":"2024-12-01T09:15:00Z","sourceName":"VnExpress","impactLevel":4,"impactedIndicators":["fdiInflowsB","gdpGrowth"]},
    {"id":4, "countryId":"THA","headline":"BYD Opens Thailand EV Factory Creating 10,000 Jobs","summary":"China's BYD inaugurated Southeast Asia's first major EV manufacturing hub in the Eastern Seaboard.","category":"economy","sentiment":"positive","sentimentScore": 0.62,"publishedAt":"2024-12-01T07:30:00Z","sourceName":"Reuters","impactLevel":3,"impactedIndicators":["fdiInflowsB","gdpGrowth"]},
    {"id":5, "countryId":"SGP","headline":"Singapore Overtakes New York as World's Second Largest FDI Recipient","summary":"UNCTAD data confirmed Singapore received $60B+ in FDI, cementing its position as Asia's top investment hub.","category":"economy","sentiment":"positive","sentimentScore": 0.88,"publishedAt":"2024-12-01T10:30:00Z","sourceName":"Straits Times","impactLevel":4,"impactedIndicators":["fdiInflowsB"]},
    {"id":6, "countryId":"MYS","headline":"Malaysia Semiconductor Sector Attracts $5B from NVIDIA Expansion","summary":"NVIDIA's Penang expansion is part of Malaysia's push to become Southeast Asia's AI infrastructure hub.","category":"economy","sentiment":"positive","sentimentScore": 0.79,"publishedAt":"2024-12-01T07:00:00Z","sourceName":"The Star","impactLevel":4,"impactedIndicators":["fdiInflowsB","gdpGrowth"]},
    {"id":7, "countryId":"IDN","headline":"Mount Lewotobi Erupts Forcing 12,000 Evacuations in East Nusa Tenggara","summary":"Authorities raised the alert to the highest tier as ash clouds disrupted flights across eastern Indonesia.","category":"disaster","sentiment":"negative","sentimentScore":-0.86,"publishedAt":"2024-11-29T09:30:00Z","sourceName":"Jakarta Post","impactLevel":5,"impactedIndicators":["gdpGrowth","tourismArrivals"]},
    {"id":8, "countryId":"PHL","headline":"Typhoon Pepito Damage Assessment Reaches $4.2B","summary":"National disaster authorities revised damage estimates upward as agricultural losses continued to mount.","category":"disaster","sentiment":"negative","sentimentScore":-0.73,"publishedAt":"2024-11-30T11:30:00Z","sourceName":"ABS-CBN","impactLevel":5,"impactedIndicators":["gdpGrowth","tradeBalanceB"]},
    {"id":9, "countryId":"KHM","headline":"Cambodia Garment Exports Fall 12% as EU Withdraws Trade Preferences","summary":"The EU's suspension of EBA preferences continues to weigh on Cambodia's largest export sector.","category":"trade","sentiment":"negative","sentimentScore":-0.58,"publishedAt":"2024-11-30T12:00:00Z","sourceName":"Phnom Penh Post","impactLevel":3,"impactedIndicators":["tradeBalanceB","gdpGrowth"]},
    {"id":10,"countryId":"VNM","headline":"US Raises Vietnam Trade Deficit Concerns in New Tariff Review","summary":"Washington opened a formal review of Vietnam's $104B trade surplus, raising tariff escalation risks.","category":"trade","sentiment":"negative","sentimentScore":-0.32,"publishedAt":"2024-11-30T14:30:00Z","sourceName":"Reuters","impactLevel":3,"impactedIndicators":["tradeBalanceB"]},
    {"id":11,"countryId":"THA","headline":"Thailand Central Bank Holds Rate at 2.5% Citing Inflation Target Met","summary":"The Bank of Thailand surprised markets by keeping rates unchanged, citing softening domestic demand.","category":"economy","sentiment":"neutral","sentimentScore": 0.08,"publishedAt":"2024-11-30T16:20:00Z","sourceName":"Bangkok Post","impactLevel":3,"impactedIndicators":["inflation","gdpGrowth"]},
    {"id":12,"countryId":"MMR","headline":"UN Warns Myanmar Displaced Population Exceeds 3 Million","summary":"The UN OCHA report cited intensifying conflict across multiple regions as the primary driver.","category":"security","sentiment":"negative","sentimentScore":-0.94,"publishedAt":"2024-12-01T06:15:00Z","sourceName":"Reuters","impactLevel":5,"impactedIndicators":["politicalStability","fdiInflowsB"]},
]

ALERTS = [
    {"id":1, "countryId":"MMR","ruleName":"Political Stability Critical","indicatorCode":"political_stability","indicatorLabel":"Political Stability Index","triggerValue":-2.3,"threshold":-2.0,"unit":"index","severity":"critical","message":"Myanmar's political stability index has fallen to -2.3, well below the critical threshold of -2.0, reflecting ongoing armed conflict and institutional breakdown.","triggeredAt":"2024-12-01","isActive":True},
    {"id":2, "countryId":"LAO","ruleName":"High Inflation Warning","indicatorCode":"inflation","indicatorLabel":"Inflation Rate","triggerValue":21.1,"threshold":5.0,"unit":"%","severity":"critical","message":"Laos inflation at 21.1% is more than 4× the warning threshold of 5%, driven by severe currency depreciation and import cost pressures.","triggeredAt":"2024-12-01","isActive":True},
    {"id":3, "countryId":"MMR","ruleName":"Negative GDP Growth","indicatorCode":"gdp_growth","indicatorLabel":"GDP Growth Rate","triggerValue":-2.1,"threshold":0.0,"unit":"%","severity":"critical","message":"Myanmar's economy contracted -2.1%, the fourth consecutive year of negative or near-zero growth, reflecting ongoing conflict and sanctions impact.","triggeredAt":"2024-11-28","isActive":True},
    {"id":4, "countryId":"LAO","ruleName":"Govt Debt Critical","indicatorCode":"govt_debt","indicatorLabel":"Government Debt","triggerValue":108.2,"threshold":60.0,"unit":"%","severity":"critical","message":"Laos government debt at 108% of GDP has entered debt distress territory. The IMF has flagged this as requiring urgent restructuring.","triggeredAt":"2024-11-25","isActive":True},
    {"id":5, "countryId":"KHM","ruleName":"Current Account Vulnerability","indicatorCode":"current_account","indicatorLabel":"Current Account Balance","triggerValue":-8.1,"threshold":-5.0,"unit":"%","severity":"warning","message":"Cambodia's current account deficit of -8.1% GDP significantly exceeds the vulnerability threshold of -5%, indicating high dependence on external financing.","triggeredAt":"2024-11-27","isActive":True},
    {"id":6, "countryId":"PHL","ruleName":"Govt Debt Critical","indicatorCode":"govt_debt","indicatorLabel":"Government Debt","triggerValue":60.2,"threshold":60.0,"unit":"%","severity":"warning","message":"Philippines government debt has crossed the 60% of GDP warning threshold, limiting fiscal policy space for future stimulus or emergency spending.","triggeredAt":"2024-11-26","isActive":True},
    {"id":7, "countryId":"MYS","ruleName":"Govt Debt Critical","indicatorCode":"govt_debt","indicatorLabel":"Government Debt","triggerValue":64.2,"threshold":60.0,"unit":"%","severity":"warning","message":"Malaysia's debt-to-GDP ratio of 64.2% is above the threshold. While manageable, continued spending could put pressure on sovereign credit ratings.","triggeredAt":"2024-11-20","isActive":True},
    {"id":8, "countryId":"MMR","ruleName":"FDI Collapse Warning","indicatorCode":"fdi_inflows","indicatorLabel":"FDI Net Inflows","triggerValue":0.4,"threshold":1.0,"unit":"$B","severity":"warning","message":"Myanmar FDI has fallen to $0.4B, well below the $1B minimum threshold. Investor confidence has collapsed amid conflict and sanctions.","triggeredAt":"2024-11-15","isActive":True},
    {"id":9, "countryId":"MMR","ruleName":"High Inflation Warning","indicatorCode":"inflation","indicatorLabel":"Inflation Rate","triggerValue":26.8,"threshold":5.0,"unit":"%","severity":"warning","message":"Myanmar inflation at 26.8% continues to erode purchasing power and reflects monetary system dysfunction since the military coup.","triggeredAt":"2024-11-10","isActive":True},
    {"id":10,"countryId":"LAO","ruleName":"FDI Collapse Warning","indicatorCode":"fdi_inflows","indicatorLabel":"FDI Net Inflows","triggerValue":0.9,"threshold":1.0,"unit":"$B","severity":"info","message":"Laos FDI inflows of $0.9B are slightly below the $1B threshold, partly reflecting investor concerns over debt sustainability and currency risk.","triggeredAt":"2024-11-05","isActive":True},
    {"id":11,"countryId":"THA","ruleName":"Govt Debt Critical","indicatorCode":"govt_debt","indicatorLabel":"Government Debt","triggerValue":62.3,"threshold":60.0,"unit":"%","severity":"info","message":"Thailand government debt has edged above 60% of GDP but remains manageable given strong institutional capacity and access to domestic financing.","triggeredAt":"2024-10-28","isActive":False},
    {"id":12,"countryId":"IDN","ruleName":"High Inflation Warning","indicatorCode":"inflation","indicatorLabel":"Inflation Rate","triggerValue":3.2,"threshold":5.0,"unit":"%","severity":"info","message":"Indonesia inflation at 3.2% is within normal range and has not breached the warning threshold. Resolved after successful monetary tightening.","triggeredAt":"2024-09-15","isActive":False},
]

# ─────────────────────────────────────────────────────────────────────────────
# MOCK EXPLANATIONS  (used when ANTHROPIC_API_KEY is not set)
# ─────────────────────────────────────────────────────────────────────────────

_MOCK: dict[str, str] = {
    "political_stability": (
        "The political stability indicator has deteriorated to a level associated with "
        "significant governance challenges. Research suggests that prolonged political "
        "instability of this magnitude is typically correlated with reduced foreign direct "
        "investment, capital outflows, and disruption to key economic sectors. The severity "
        "of this reading suggests the situation may require sustained attention across "
        "multiple quarters before stabilisation is observed."
    ),
    "inflation": (
        "Inflation at this level significantly exceeds the target band typical for emerging "
        "economies in Southeast Asia. This pattern is often associated with imported inflation "
        "through currency depreciation, supply-side disruptions, or loss of central bank "
        "credibility. Elevated inflation erodes household purchasing power, disproportionately "
        "affecting lower-income populations, and may suppress domestic consumption growth."
    ),
    "gdp_growth": (
        "Negative GDP growth indicates the economy contracted during this period. Economic "
        "contractions in this region are frequently driven by a combination of weakened "
        "export demand, reduced private investment, and disruptions to key sectors. Sustained "
        "contraction over multiple periods may indicate structural challenges that go beyond "
        "normal cyclical patterns and could require significant policy intervention."
    ),
    "govt_debt": (
        "Government debt above this threshold begins to constrain fiscal policy flexibility. "
        "High debt levels may limit the government's ability to respond to future shocks with "
        "stimulus spending and can raise borrowing costs if investor confidence declines. "
        "For countries with external debt denominated in foreign currencies, this also creates "
        "exchange rate vulnerability in debt servicing."
    ),
    "current_account": (
        "A current account deficit of this magnitude suggests the country is relying heavily "
        "on external financing to fund its trade and investment needs. While not automatically "
        "problematic if financed by stable FDI, large deficits financed by portfolio flows can "
        "be vulnerable to sudden reversals. This pattern warrants monitoring of foreign reserve "
        "levels and the composition of financing inflows."
    ),
    "fdi": (
        "FDI inflows below this threshold suggest deteriorating investor confidence in the "
        "business environment. Investment flows tend to respond to political stability, "
        "regulatory predictability, and macroeconomic conditions. A sustained decline may "
        "indicate structural competitiveness concerns that could affect medium-term growth "
        "potential and employment generation."
    ),
}


def _mock_explanation(country_name: str, indicator_code: str, alert_label: str) -> str:
    code = indicator_code.lower()
    for key, text in _MOCK.items():
        if key in code or key in alert_label.lower():
            return text + (
                f"\n\n⚠ Demo mode — showing pre-written explanation for {country_name}. "
                "Add ANTHROPIC_API_KEY to backend/.env for live AI-generated responses."
            )
    return (
        f"This alert indicates that {country_name}'s {alert_label.lower()} has breached "
        f"the defined monitoring threshold. Economic indicators of this type, when persistently "
        f"elevated, may signal broader structural vulnerabilities in the economy that warrant "
        f"detailed analysis of underlying drivers and regional spillover risks."
        f"\n\n⚠ Demo mode — add ANTHROPIC_API_KEY to backend/.env for AI-powered explanations."
    )

# ─────────────────────────────────────────────────────────────────────────────
# REQUEST / RESPONSE MODELS
# ─────────────────────────────────────────────────────────────────────────────

# ── Legacy flat-text endpoint ─────────────────────────────────────────────────
class AlertExplainRequest(BaseModel):
    country_iso3:   str
    country_name:   str
    alert_label:    str
    indicator_code: str
    severity:       str
    trigger_value:  float
    threshold:      float
    unit:           str
    message:        str
    period:         str = "2024"

class AlertExplainResponse(BaseModel):
    country_iso3: str
    country_name: str
    alert_label:  str
    severity:     str
    explanation:  str
    is_ai:        bool
    model_used:   str
    generated_at: str


# ── NEW: Structured pattern explanation ───────────────────────────────────────
# The full input schema is documented in ai_engine.INPUT_JSON_SCHEMA.
# This Pydantic model validates the incoming request body.

class AlertMeta(BaseModel):
    """The triggered alert details."""
    type:            str
    label:           str
    country_id:      str
    country_name:    str
    flag:            str = ""
    quarter:         str
    severity:        str                    # none|info|warning|critical
    trigger_value:   float
    threshold_value: float
    unit:            str
    score:           int = 0
    condition_met:   str = ""

class IndicatorValue(BaseModel):
    """One indicator's current value."""
    value: float
    unit:  str
    label: str

class OtherAlert(BaseModel):
    """A co-active alert for the same country."""
    type:     str
    severity: str
    label:    str

class NewsSignal(BaseModel):
    """A recent news article connected to this alert."""
    headline:             str
    category:             str
    sentiment:            str
    impact_score:         int = 3
    days_ago:             int = 0
    connected_indicators: list[str] = []

class TradeLinks(BaseModel):
    top_export_partners: list[str] = []
    top_import_partners: list[str] = []

class AlertContext(BaseModel):
    """Regional and data-source context."""
    region:             str = "Southeast Asia"
    neighbors:          list[str] = []
    trade_links:        TradeLinks = Field(default_factory=TradeLinks)
    data_source_notes:  str = ""

class PatternExplainRequest(BaseModel):
    """
    Full structured input for the /explain/pattern endpoint.
    See ai_engine.INPUT_JSON_SCHEMA for the complete documented example.
    """
    alert:               AlertMeta
    indicators:          dict[str, IndicatorValue] = {}
    other_active_alerts: list[OtherAlert] = []
    recent_news:         list[NewsSignal] = []
    context:             AlertContext = Field(default_factory=AlertContext)

class ConfidenceDetail(BaseModel):
    level:        str
    label:        str
    score:        int
    rationale:    str
    data_quality: str
    factors:      list[str] = []

class ConnectedIndicator(BaseModel):
    key:          str
    label:        str
    value:        float
    unit:         str
    relationship: str
    direction:    str

class AffectedCountry(BaseModel):
    country_id:         str
    country_name:       str
    flag:               str = ""
    mechanism:          str
    possible_impact:    str
    indicators_at_risk: list[str] = []
    confidence:         str

class PatternExplainResponse(BaseModel):
    """
    Structured 6-section AI explanation.
    See ai_engine.OUTPUT_JSON_SCHEMA for the complete documented example.
    """
    alert_type:             str
    country_id:             str
    country_name:           str
    severity:               str
    quarter:                str
    what_changed:           str
    why_it_matters:         str
    connected_indicators:   list[ConnectedIndicator] = []
    affected_countries:     list[AffectedCountry] = []
    confidence:             ConfidenceDetail
    limitations:            list[str] = []
    summary_sentence:       str
    hedging_note:           str
    is_ai:                  bool
    model_used:             str
    generated_at:           str

# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {
        "status":     "ok",
        "version":    "1.0.0-mvp",
        "mode":       "sample_data",
        "ai_enabled": bool(ANTHROPIC_API_KEY),
    }


@app.get("/countries")
def get_countries(risk: Optional[str] = None, region: Optional[str] = None):
    data = COUNTRIES
    if risk:
        data = [c for c in data if c["riskLevel"] == risk]
    if region:
        data = [c for c in data if c["region"].lower() == region.lower()]
    return data


@app.get("/countries/{iso3}")
def get_country(iso3: str):
    c = next((c for c in COUNTRIES if c["id"] == iso3.upper()), None)
    if not c:
        raise HTTPException(404, f"Country '{iso3}' not found")
    ind = INDICATORS.get(iso3.upper(), {})
    return {**c, "indicators": ind}


@app.get("/news")
def get_news(
    country: Optional[str] = None,
    category: Optional[str] = None,
    sentiment: Optional[str] = None,
    limit: int = 20,
):
    items = NEWS
    if country:
        items = [n for n in items if n["countryId"] == country.upper()]
    if category:
        items = [n for n in items if n["category"] == category]
    if sentiment:
        items = [n for n in items if n["sentiment"] == sentiment]
    return sorted(items, key=lambda n: n["publishedAt"], reverse=True)[:limit]


@app.get("/alerts")
def get_alerts(
    country: Optional[str] = None,
    severity: Optional[str] = None,
    active_only: bool = True,
):
    items = [a for a in ALERTS if (not active_only or a["isActive"])]
    if country:
        items = [a for a in items if a["countryId"] == country.upper()]
    if severity:
        items = [a for a in items if a["severity"] == severity]
    order = {"critical": 0, "warning": 1, "info": 2}
    return sorted(items, key=lambda a: order.get(a["severity"], 9))


@app.post("/explain/alert", response_model=AlertExplainResponse)
def explain_alert(req: AlertExplainRequest):
    """
    Generate an AI explanation for a triggered pattern alert.

    If ANTHROPIC_API_KEY is set in backend/.env, calls Claude.
    Otherwise returns a pre-written contextual explanation (demo mode).
    """
    explanation: str
    is_ai        = False
    model_used   = "demo"

    if ANTHROPIC_API_KEY:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

            prompt = (
                f"You are an economic analyst for a Southeast Asia dashboard.\n\n"
                f"Country: {req.country_name}\n"
                f"Alert: {req.alert_label} (severity: {req.severity})\n"
                f"Indicator: {req.indicator_code}\n"
                f"Triggered value: {req.trigger_value}{req.unit} (threshold: {req.threshold}{req.unit})\n"
                f"Period: {req.period}\n"
                f"Alert message: {req.message}\n\n"
                "Write a clear 3-4 sentence explanation of what this alert means, "
                "why it matters for this country's economy, and what to watch next. "
                "Use hedged language (may suggest, appears to indicate). "
                "Do not name individuals. Do not make specific predictions."
            )

            response = client.messages.create(
                model      = CLAUDE_MODEL,
                max_tokens = 400,
                messages   = [{"role": "user", "content": prompt}],
            )
            explanation = response.content[0].text
            is_ai       = True
            model_used  = CLAUDE_MODEL

        except Exception as exc:
            explanation = _mock_explanation(req.country_name, req.indicator_code, req.alert_label)
            model_used  = f"demo (claude error: {type(exc).__name__})"
    else:
        explanation = _mock_explanation(req.country_name, req.indicator_code, req.alert_label)

    return AlertExplainResponse(
        country_iso3 = req.country_iso3,
        country_name = req.country_name,
        alert_label  = req.alert_label,
        severity     = req.severity,
        explanation  = explanation,
        is_ai        = is_ai,
        model_used   = model_used,
        generated_at = datetime.now(timezone.utc).isoformat(),
    )


@app.post("/explain/pattern", response_model=PatternExplainResponse)
def explain_pattern(req: PatternExplainRequest):
    """
    Generate a STRUCTURED 6-section AI explanation for a pattern alert.

    Sections returned:
      1. what_changed           — What the indicator did, with numbers
      2. why_it_matters         — Economic significance, who is affected
      3. connected_indicators   — Which other indicators are likely linked
      4. affected_countries     — Which neighbours may see spillover effects
      5. confidence             — Level (low/medium/high) + rationale
      6. limitations            — Specific data and model limitations

    All text uses hedged language — no future-certainty claims.

    MODE A (ANTHROPIC_API_KEY set):
      Calls Claude claude-haiku-4-5 (or CLAUDE_MODEL env var).
      Returns is_ai=true with calibrated, context-specific analysis.

    MODE B (no API key):
      Returns a pre-written template response (is_ai=false, model_used="demo").
      The structure is identical so the frontend renders normally.
      Set ANTHROPIC_API_KEY in backend/.env to enable live AI.

    RATE LIMITING NOTE:
      Each call makes one Claude API request (~300–600 tokens input, ~600 output).
      Consider caching responses per (country_id, alert_type, quarter) key.
    """
    if not _AI_ENGINE_AVAILABLE:
        raise HTTPException(
            503,
            "ai_engine.py not found. Ensure backend/ai_engine.py is in the same directory as server.py."
        )

    # Convert Pydantic models → plain dicts for ai_engine.build_explanation()
    inp: dict[str, Any] = {
        "alert": req.alert.model_dump(),
        "indicators": {
            k: v.model_dump() for k, v in req.indicators.items()
        },
        "other_active_alerts": [a.model_dump() for a in req.other_active_alerts],
        "recent_news":         [n.model_dump() for n in req.recent_news],
        "context": {
            **req.context.model_dump(exclude={"trade_links"}),
            "trade_links": req.context.trade_links.model_dump(),
        },
    }

    result = build_explanation(inp, api_key=ANTHROPIC_API_KEY, model=CLAUDE_MODEL)

    # Ensure required fields exist (build_explanation never raises, but validate)
    return PatternExplainResponse(
        alert_type   = result.get("alert_type",   req.alert.type),
        country_id   = result.get("country_id",   req.alert.country_id),
        country_name = result.get("country_name", req.alert.country_name),
        severity     = result.get("severity",     req.alert.severity),
        quarter      = result.get("quarter",      req.alert.quarter),
        what_changed         = result.get("what_changed", "Not available"),
        why_it_matters       = result.get("why_it_matters", "Not available"),
        connected_indicators = [
            ConnectedIndicator(**c) for c in result.get("connected_indicators", [])
            if all(k in c for k in ["key","label","value","unit","relationship","direction"])
        ],
        affected_countries = [
            AffectedCountry(**c) for c in result.get("affected_countries", [])
            if all(k in c for k in ["country_id","country_name","mechanism","possible_impact","confidence"])
        ],
        confidence = ConfidenceDetail(
            level        = result["confidence"].get("level",        "low"),
            label        = result["confidence"].get("label",        "Unknown"),
            score        = result["confidence"].get("score",        0),
            rationale    = result["confidence"].get("rationale",    ""),
            data_quality = result["confidence"].get("data_quality", "unknown"),
            factors      = result["confidence"].get("factors",      []),
        ),
        limitations      = result.get("limitations",      []),
        summary_sentence = result.get("summary_sentence", ""),
        hedging_note     = result.get("hedging_note",     ""),
        is_ai        = result.get("is_ai",        False),
        model_used   = result.get("model_used",   "unknown"),
        generated_at = result.get("generated_at", datetime.now(timezone.utc).isoformat()),
    )


@app.get("/explain/schema")
def explain_schema():
    """
    Returns the documented input and output JSON schemas for the
    /explain/pattern endpoint.

    Use this as a reference when building the frontend request or
    when inspecting what the AI engine expects and returns.
    """
    if not _AI_ENGINE_AVAILABLE:
        return {"error": "ai_engine.py not found"}
    return {
        "endpoint":      "POST /explain/pattern",
        "description":   "Structured 6-section AI explanation for pattern alerts",
        "input_schema":  INPUT_JSON_SCHEMA,
        "output_schema": OUTPUT_JSON_SCHEMA,
        "prompt_preview": SYSTEM_PROMPT[:500] + "… (truncated)",
        "models_supported": [
            "claude-haiku-4-5",
            "claude-sonnet-4-5",
        ],
        "demo_mode_active": not bool(ANTHROPIC_API_KEY),
    }
