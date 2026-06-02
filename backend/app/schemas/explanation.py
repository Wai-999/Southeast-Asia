"""
schemas/explanation.py — Pydantic input/output models for AI explanation endpoint.

Input:  ExplanationRequest — all indicators, alerts, and news signals for one country/period
Output: ExplanationResponse — 6 structured sections + confidence + limitations
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator


# ─────────────────────────────────────────────────────────────────────────────
# INPUT MODELS
# ─────────────────────────────────────────────────────────────────────────────

class IndicatorValue(BaseModel):
    """One economic indicator with current and optional prior-year value."""
    value: float
    previous_value: Optional[float] = None
    unit: str = ""                               # e.g. "%", "USD billions"
    source: str = "World Bank"                   # data provenance

    @property
    def yoy_change(self) -> Optional[float]:
        if self.previous_value is not None and self.previous_value != 0:
            return round((self.value - self.previous_value) / abs(self.previous_value) * 100, 1)
        return None

    @property
    def yoy_direction(self) -> str:
        yoy = self.yoy_change
        if yoy is None: return "unknown"
        if yoy > 0:     return "up"
        if yoy < 0:     return "down"
        return "flat"


class NewsSignal(BaseModel):
    """One GDELT news category signal for the last 30 days."""
    category: str                                # e.g. "conflict", "tariff", "election"
    article_count: int = 0
    baseline_count: Optional[int] = None        # normal monthly volume for this country
    change_vs_baseline_pct: Optional[float] = None  # positive = elevated
    sample_topics: list[str] = Field(
        default_factory=list,
        max_length=3,
        description="Up to 3 representative topic strings from article titles"
    )


class PatternAlert(BaseModel):
    """One triggered alert from pattern_engine.py."""
    alert_type: str                              # e.g. "export_stress"
    alert_label: str                             # e.g. "Export Stress"
    severity: Literal["info", "warning", "critical"]
    score: float = Field(ge=0, le=100)
    conditions_met: list[str] = Field(default_factory=list)


class ExplanationRequest(BaseModel):
    """
    Full input for one AI explanation request.

    Minimum viable request: country_iso3 + country_name + period + at least 2 indicators.
    The more indicators and signals provided, the higher the explanation quality.
    """

    # Identity
    country_iso3: str = Field(min_length=3, max_length=3, description="ISO 3166-1 alpha-3")
    country_name: str
    period: str = Field(
        description="Human-readable period string, e.g. 'Q2 2026', '2024', '2024-Q3'"
    )

    # Economic indicators (all optional — engine degrades gracefully on missing data)
    gdp_growth:    Optional[IndicatorValue] = None   # % annual
    inflation:     Optional[IndicatorValue] = None   # % CPI
    exports:       Optional[IndicatorValue] = None   # USD billions
    imports:       Optional[IndicatorValue] = None   # USD billions
    exchange_rate: Optional[IndicatorValue] = None   # local per USD
    fdi:           Optional[IndicatorValue] = None   # USD billions net inflows
    public_debt:   Optional[IndicatorValue] = None   # % of GDP

    # GDELT news signals (optional)
    news_signals: list[NewsSignal] = Field(default_factory=list)

    # Pattern engine alerts that are currently active (optional)
    active_alerts: list[PatternAlert] = Field(default_factory=list)

    # Free-text additional context (analyst notes, upcoming events, etc.)
    additional_context: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Optional analyst notes, e.g. 'Election scheduled Q3', 'New FTA with China signed'"
    )

    @field_validator("country_iso3")
    @classmethod
    def upper_iso3(cls, v: str) -> str:
        return v.upper()


# ─────────────────────────────────────────────────────────────────────────────
# OUTPUT MODELS
# ─────────────────────────────────────────────────────────────────────────────

class DetailedExplanation(BaseModel):
    """Three sub-sections of the detailed narrative."""
    what_changed: str       = Field(description="Specific indicator changes with numbers")
    why_it_may_matter: str  = Field(description="Economic significance (hedged language)")
    which_indicators_connected: str = Field(description="How indicators reinforce or contradict each other")


class ConnectedIndicator(BaseModel):
    """One indicator relationship identified by the AI."""
    name: str
    relationship: Literal["leads", "lags", "amplifies", "dampens", "correlates"]
    explanation: str        = Field(description="One sentence explaining the connection")


class RegionalImpact(BaseModel):
    """How this country's situation may affect its neighbours."""
    likely_affected_countries: list[str]    = Field(
        description="ISO3 codes of potentially affected countries (max 4)"
    )
    primary_channel: Literal[
        "trade", "capital_flows", "migration", "sentiment", "supply_chain"
    ]
    severity_assessment: Literal["minor", "moderate", "significant"]
    explanation: str        = Field(description="How this may affect neighbours")


class DataLimitation(BaseModel):
    """One specific data quality caveat."""
    limitation: str         = Field(description="The specific data gap or caveat")
    impact_on_analysis: str = Field(description="How this limitation affects the conclusions")


class ConfidenceAssessment(BaseModel):
    """Calibrated confidence in the AI explanation."""
    level: Literal["low", "medium", "high"]
    data_completeness_score: float = Field(ge=0.0, le=1.0,
        description="Fraction of indicator slots that have data (computed deterministically)")
    reasoning: str          = Field(description="What supports or limits confidence")


WarningLevel = Literal["none", "watch", "caution", "alert", "critical"]

WARNING_DISPLAY: dict[str, dict] = {
    "none":     {"label": "No Alert",       "color": "#6B7280", "bg": "#F9FAFB"},
    "watch":    {"label": "Watch",          "color": "#2563EB", "bg": "#EFF6FF"},
    "caution":  {"label": "Caution",        "color": "#D97706", "bg": "#FFFBEB"},
    "alert":    {"label": "Alert",          "color": "#EA580C", "bg": "#FFF7ED"},
    "critical": {"label": "Critical",       "color": "#DC2626", "bg": "#FEF2F2"},
}


class ExplanationResponse(BaseModel):
    """
    Full AI explanation response — 6 structured sections.
    All sections are always present; some may contain caveats when data is limited.
    """

    # Metadata
    country_iso3:   str
    country_name:   str
    period:         str
    generated_at:   str     = Field(description="ISO 8601 timestamp")
    model_used:     str
    tokens_used:    Optional[int] = None

    # Section 1: Short summary (2-3 sentences)
    short_summary:  str

    # Section 2: Detailed explanation (3 sub-sections)
    detailed_explanation: DetailedExplanation

    # Section 3: Connected indicators
    connected_indicators: list[ConnectedIndicator]

    # Section 4: Regional impact
    regional_impact: RegionalImpact

    # Section 5: Warning level
    warning_level:    WarningLevel
    warning_reasoning: str
    warning_color:    str   = Field(description="Hex color for dashboard display")
    warning_bg:       str   = Field(description="Hex background color")
    warning_label:    str   = Field(description="Human-readable label")

    # Section 6: Confidence + limitations
    confidence: ConfidenceAssessment
    data_limitations: list[DataLimitation]

    # Error flag (true if Claude failed and response is fallback)
    is_fallback: bool = False


# ─────────────────────────────────────────────────────────────────────────────
# EXAMPLE — shown at GET /explain/example
# ─────────────────────────────────────────────────────────────────────────────

EXAMPLE_REQUEST = ExplanationRequest(
    country_iso3="THA",
    country_name="Thailand",
    period="Q2 2026",
    gdp_growth=IndicatorValue(value=1.5,  previous_value=2.6, unit="%"),
    inflation=IndicatorValue(value=3.8,   previous_value=1.2, unit="%"),
    exports=IndicatorValue(value=68.2,    previous_value=71.1, unit="USD billions"),
    imports=IndicatorValue(value=65.4,    previous_value=67.3, unit="USD billions"),
    exchange_rate=IndicatorValue(value=36.2, previous_value=34.8, unit="THB per USD"),
    fdi=IndicatorValue(value=1.9,         previous_value=2.1, unit="USD billions"),
    news_signals=[
        NewsSignal(
            category="tariff",
            article_count=18,
            baseline_count=7,
            change_vs_baseline_pct=157.0,
            sample_topics=["US tariff review on Thai goods", "border trade disruption", "ASEAN trade tensions"],
        ),
        NewsSignal(
            category="political_risk",
            article_count=22,
            baseline_count=7,
            change_vs_baseline_pct=214.0,
            sample_topics=["cabinet reshuffle", "budget dispute", "protest in Bangkok"],
        ),
    ],
    active_alerts=[
        PatternAlert(
            alert_type="export_stress",
            alert_label="Export Stress",
            severity="warning",
            score=44.2,
            conditions_met=["Exports fell 4.1% YoY ($71.1B → $68.2B)"],
        ),
        PatternAlert(
            alert_type="currency_pressure",
            alert_label="Currency Pressure",
            severity="info",
            score=28.1,
            conditions_met=["THB depreciated 15.7% vs 2020 reference"],
        ),
    ],
    additional_context="Election cycle underway. New tourism promotion campaign launched.",
)
