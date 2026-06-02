/**
 * frontend/data/pattern-alerts.ts
 * ─────────────────────────────────────────────────────────────────────────────
 * TypeScript adapter for pipeline/data/processed/pattern_alerts.json.
 *
 * Converts the 8-type pattern detection output into the PatternAlert shape
 * used by the dashboard, and adds enriched fields for the AI explanation panel.
 *
 * HOW TO REFRESH:
 *   cd pipeline && python generate_pattern_alerts.py
 *   (runs automatically via run_pipeline.py --mode process)
 * ─────────────────────────────────────────────────────────────────────────────
 */

// eslint-disable-next-line @typescript-eslint/no-require-imports
const _raw = require("../../pipeline/data/processed/pattern_alerts.json") as PatternAlertsJson;

import type { PatternAlert } from "@/data/sample-data";
import type { Severity } from "@/lib/utils";

// ── Raw JSON types ────────────────────────────────────────────────────────────

interface SourceSignals {
  official_data:  boolean;
  news_signal:    boolean;
  trade_signal:   boolean;
  sources_count:  number;
}

interface RawAlert {
  alert_id:             string;
  alert_type:           string;
  alert_label:          string;
  country_iso3:         string;
  country_name:         string;
  year:                 number;
  triggered:            boolean;
  score:                number;
  severity:             string;
  conditions_met:       string[];
  values_used:          Record<string, unknown>;
  explanation:          string;
  recommendation:       string;
  color:                string;
  bg_color:             string;
  icon:                 string;
  severity_class:       string;
  chart_hint:           string;
  metric_to_highlight:  string;
  confidence:           string;
  source_signals:       SourceSignals;
  confidence_rationale: string;
  ai_explanation:       string;
  data_sources_used:    string[];
  generated_at:         string;
}

interface PatternAlertsMeta {
  generated_at:          string;
  script:                string;
  total_checks:          number;
  triggered_alerts:      number;
  critical:              number;
  warnings:              number;
  info_count:            number;
  high_confidence:       number;
  medium_confidence:     number;
  low_confidence:        number;
  countries_checked:     number;
  regional_avg_growth:   number;
  min_score_filter:      number;
  news_window_days:      number;
  alert_types:           string[];
  confidence_methodology: string;
  refresh_note:          string;
}

interface PatternAlertsJson {
  meta:          PatternAlertsMeta;
  alerts:        RawAlert[];
  all_results:   RawAlert[];
  by_country:    Record<string, RawAlert[]>;
  by_type:       Record<string, RawAlert[]>;
  by_severity:   Record<string, RawAlert[]>;
  by_confidence: Record<string, RawAlert[]>;
}

// ── Public extended type ──────────────────────────────────────────────────────

/** Extends PatternAlert with confidence scoring and AI explanation fields. */
export interface EnrichedAlert extends PatternAlert {
  /** Composite alert score from the pattern engine (0–100). */
  score:                number;
  /** Multi-source confidence level: "high" | "medium" | "low" */
  confidence:           ConfidenceLevel;
  /** Which of the 3 data sources agree on this risk. */
  sourceSignals:        SourceSignalsPublic;
  /** Human-readable explanation of why the confidence level was assigned. */
  confidenceRationale:  string;
  /** Rich multi-source narrative for the AI explanation panel (Markdown). */
  aiExplanation:        string;
  /** Data sources used, e.g. ["World Bank 2024", "GDELT 7-day", ...] */
  dataSourcesUsed:      string[];
  /** List of specific conditions that triggered this alert. */
  conditionsMet:        string[];
  /** Recommended action for analysts. */
  recommendation:       string;
  /** Alert icon (emoji). */
  icon:                 string;
  /** Tailwind chart hint: "line" | "bar" | "gauge" | "heatmap" */
  chartHint:            string;
  /** The indicator key this alert most directly highlights. */
  metricToHighlight:    string;
  /** Tailwind colour class for the alert colour. */
  color:                string;
  /** Tailwind background colour class. */
  bgColor:              string;
}

export type ConfidenceLevel = "high" | "medium" | "low";

export interface SourceSignalsPublic {
  officialData:  boolean;   // World Bank confirms the risk
  newsSignal:    boolean;   // GDELT news corroborates the risk
  tradeSignal:   boolean;   // UN Comtrade flows support the risk
  sourcesCount:  number;    // 0 | 1 | 2 | 3
}

// ── Indicator code mapping ────────────────────────────────────────────────────

const ALERT_TO_INDICATOR: Record<string, string> = {
  export_stress:         "exports",
  import_shock:          "imports",
  inflation_pressure:    "inflation",
  political_risk_rising: "politicalRiskNews",
  trade_dependency_risk: "imports",
  regional_spillover:    "gdpGrowth",
  fdi_weakness:          "fdi",
  growth_slowdown:       "gdpGrowth",
};

const ALERT_TO_INDICATOR_LABEL: Record<string, string> = {
  export_stress:         "Export Volume (USD B)",
  import_shock:          "Import Volume (USD B)",
  inflation_pressure:    "CPI Inflation (%)",
  political_risk_rising: "Political Risk News",
  trade_dependency_risk: "Partner Trade Share (%)",
  regional_spillover:    "GDP Growth (%)",
  fdi_weakness:          "FDI % of GDP",
  growth_slowdown:       "GDP Growth (%)",
};

// ── Auto-increment ID counter (stable across module loads since JSON is static) ─

let _nextId = 1;
function nextId() { return _nextId++; }

// ── Converters ────────────────────────────────────────────────────────────────

function toPatternAlert(r: RawAlert): PatternAlert {
  return {
    id:             nextId(),
    countryId:      r.country_iso3,
    ruleName:       r.alert_label,
    indicatorCode:  ALERT_TO_INDICATOR[r.alert_type] ?? "gdpGrowth",
    indicatorLabel: ALERT_TO_INDICATOR_LABEL[r.alert_type] ?? r.alert_label,
    triggerValue:   r.score,
    threshold:      20,   // ALERT_TRIGGER_MIN from pattern_engine.py
    unit:           "score",
    severity:       r.severity as Severity,
    message:        r.explanation,
    triggeredAt:    r.generated_at.slice(0, 10),  // ISO date only
    isActive:       r.triggered,
  };
}

function toEnrichedAlert(r: RawAlert): EnrichedAlert {
  const base = toPatternAlert(r);
  return {
    ...base,
    score:               r.score,
    confidence:          (r.confidence ?? "low") as ConfidenceLevel,
    sourceSignals: {
      officialData: r.source_signals?.official_data ?? false,
      newsSignal:   r.source_signals?.news_signal   ?? false,
      tradeSignal:  r.source_signals?.trade_signal  ?? false,
      sourcesCount: r.source_signals?.sources_count ?? 0,
    },
    confidenceRationale: r.confidence_rationale ?? "",
    aiExplanation:       r.ai_explanation       ?? r.explanation,
    dataSourcesUsed:     r.data_sources_used    ?? [],
    conditionsMet:       r.conditions_met       ?? [],
    recommendation:      r.recommendation       ?? "",
    icon:                r.icon                 ?? "📊",
    chartHint:           r.chart_hint           ?? "line",
    metricToHighlight:   r.metric_to_highlight  ?? "",
    color:               r.color                ?? "#6B7280",
    bgColor:             r.bg_color             ?? "#F9FAFB",
  };
}

// ── Exports ───────────────────────────────────────────────────────────────────

/** All triggered alerts, sorted critical → warning → info → score. */
export const ENRICHED_ALERTS: EnrichedAlert[] =
  _raw.alerts.map(toEnrichedAlert);

/**
 * Drop-in replacement for PATTERN_ALERTS from sample-data.ts.
 * Sourced from real pattern detection run on World Bank + GDELT + Comtrade data.
 */
export const PATTERN_ALERTS_LIVE: PatternAlert[] =
  _raw.alerts.map(toPatternAlert);

/** Alerts grouped by country ISO3. */
export const ALERTS_BY_COUNTRY: Record<string, EnrichedAlert[]> = {};
for (const r of _raw.alerts) {
  ALERTS_BY_COUNTRY[r.country_iso3] ??= [];
  ALERTS_BY_COUNTRY[r.country_iso3].push(toEnrichedAlert(r));
}

/** Alerts grouped by alert type. */
export const ALERTS_BY_TYPE: Record<string, EnrichedAlert[]> = {};
for (const r of _raw.alerts) {
  ALERTS_BY_TYPE[r.alert_type] ??= [];
  ALERTS_BY_TYPE[r.alert_type].push(toEnrichedAlert(r));
}

/** High-confidence alerts only (all 3 sources agree). */
export const HIGH_CONFIDENCE_ALERTS: EnrichedAlert[] =
  ENRICHED_ALERTS.filter(a => a.confidence === "high");

/** Pipeline-level metadata. */
export const PATTERN_ALERTS_META = {
  generatedAt:       _raw.meta.generated_at,
  totalChecks:       _raw.meta.total_checks,
  triggeredAlerts:   _raw.meta.triggered_alerts,
  critical:          _raw.meta.critical,
  warnings:          _raw.meta.warnings,
  infoCount:         _raw.meta.info_count,
  highConfidence:    _raw.meta.high_confidence,
  mediumConfidence:  _raw.meta.medium_confidence,
  lowConfidence:     _raw.meta.low_confidence,
  countriesChecked:  _raw.meta.countries_checked,
  regionalAvgGrowth: _raw.meta.regional_avg_growth,
  newsWindowDays:    _raw.meta.news_window_days,
  alertTypes:        _raw.meta.alert_types,
  confidenceMethodology: _raw.meta.confidence_methodology,
  refreshNote:       _raw.meta.refresh_note,
};

// ── Formatting helpers ────────────────────────────────────────────────────────

/** Tailwind dot colour for a confidence level. */
export const CONFIDENCE_DOT: Record<ConfidenceLevel, string> = {
  high:   "bg-emerald-500",
  medium: "bg-amber-400",
  low:    "bg-slate-400",
};

/** Tailwind text colour for a confidence level. */
export const CONFIDENCE_TEXT: Record<ConfidenceLevel, string> = {
  high:   "text-emerald-600",
  medium: "text-amber-600",
  low:    "text-slate-500",
};

/** Human-readable confidence label. */
export const CONFIDENCE_LABEL: Record<ConfidenceLevel, string> = {
  high:   "High confidence",
  medium: "Medium confidence",
  low:    "Low confidence",
};

/** Pip indicators: ●●● / ●●○ / ●○○ */
export const CONFIDENCE_PIPS: Record<ConfidenceLevel, string> = {
  high:   "●●●",
  medium: "●●○",
  low:    "●○○",
};

/**
 * Format a generated_at ISO timestamp as a friendly string.
 * e.g. "2026-06-02T14:56:32" → "Jun 2, 2026, 2:56 PM"
 */
export function fmtGeneratedAt(iso?: string | null): string {
  if (!iso) return "unknown";
  try {
    return new Date(iso).toLocaleString("en-US", {
      month: "short", day: "numeric", year: "numeric",
      hour: "numeric", minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

/** Get all triggered alerts for a given country ISO3 code. */
export function getAlertsForCountry(iso3: string): EnrichedAlert[] {
  return ALERTS_BY_COUNTRY[iso3] ?? [];
}

/** Get alerts of a specific type. */
export function getAlertsByType(alertType: string): EnrichedAlert[] {
  return ALERTS_BY_TYPE[alertType] ?? [];
}
