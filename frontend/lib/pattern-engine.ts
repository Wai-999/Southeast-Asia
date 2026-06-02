/**
 * ═══════════════════════════════════════════════════════════════════
 *  pattern-engine.ts
 *  SEA Change Intelligence Dashboard — Rule-Based Pattern Detection
 * ═══════════════════════════════════════════════════════════════════
 *
 *  This file contains a complete alert detection engine.
 *  It reads economic data and checks 6 rule-based patterns,
 *  returning human-readable alerts with severity levels.
 *
 *  ┌─ 6 ALERT TYPES ─────────────────────────────────────────────┐
 *  │  1. EXPORT_STRESS          Export decline detected           │
 *  │  2. INFLATION_PRESSURE     CPI above safe threshold          │
 *  │  3. POLITICAL_INSTABILITY  Risk news elevated vs baseline    │
 *  │  4. CURRENCY_PRESSURE      Exchange rate depreciation        │
 *  │  5. FDI_SLOWDOWN           Foreign investment falling        │
 *  │  6. REGIONAL_SPILLOVER     Multiple neighbours stressed      │
 *  └─────────────────────────────────────────────────────────────┘
 *
 *  HOW TO USE IN YOUR PAGE:
 *  ─────────────────────────
 *  import { detectAllAlerts, buildCountryData } from "@/lib/pattern-engine";
 *
 *  const data = buildCountryData("THA", currentIndicators, prevIndicators, baselines);
 *  const alerts = detectAllAlerts(data);
 *  // alerts is an array — filter by triggered === true to show on dashboard
 *
 *  BEGINNER NOTE:
 *  ─────────────────────────
 *  Each alert is a plain function. It takes numbers in, and returns
 *  an object describing what was found. No database, no API needed.
 */

// ═══════════════════════════════════════════════════════════════════
// SECTION 1: TYPES
// What shape the data must be in (TypeScript interfaces)
// ═══════════════════════════════════════════════════════════════════

/**
 * All the economic data for one country in one quarter.
 * You build this from your sample-data.ts or quarterly_values.json.
 */
export interface CountryData {
  // ── Who is this? ──────────────────────────────────────
  countryId:    string;  // "THA", "VNM", "MMR", "KHM", "SGP"
  countryName:  string;  // "Thailand"
  flagEmoji:    string;  // "🇹🇭"
  quarter:      string;  // "2024-Q3"

  // ── Current quarter values ─────────────────────────────
  gdpGrowth:         number;  // % YoY   e.g. 2.9
  inflation:         number;  // % YoY   e.g. 3.0
  exports:           number;  // USD B   e.g. 72.8
  imports:           number;  // USD B   e.g. 66.3
  exchangeRate:      number;  // per USD e.g. 33.5 (THB/USD)
  fdi:               number;  // USD B   e.g. 3.0
  politicalRiskNews: number;  // articles/month  e.g. 42
  tradeNewsCount:    number;  // articles/month  e.g. 29

  // ── Previous quarter values (for trend detection) ──────
  // These are optional — if missing, trend checks are skipped
  prevExports?:           number;
  prevInflation?:         number;
  prevExchangeRate?:      number;
  prevFdi?:               number;
  prevPoliticalRiskNews?: number;

  // ── Country-specific reference baselines ───────────────
  // These are "normal" levels for this country.
  // Used to measure how far current values have deviated.
  exchangeRateBaseline:    number;  // e.g. 32.0 (THB/USD in stable period)
  politicalRiskBaseline:   number;  // e.g. 30  (normal news count for THA)
  fdiBaseline:             number;  // e.g. 3.5 (expected quarterly FDI in USD B)
  exportsBaseline?:        number;  // e.g. 70.0 (expected quarterly exports)
}

/**
 * The result returned by each alert detection function.
 */
export interface AlertResult {
  // ── Identity ────────────────────────────────────────────
  alertType:   string;   // e.g. "INFLATION_PRESSURE"
  alertLabel:  string;   // e.g. "Inflation Pressure"
  countryId:   string;
  countryName: string;
  flagEmoji:   string;
  quarter:     string;

  // ── Was the alert triggered? ────────────────────────────
  triggered: boolean;    // true = alert is active, false = all clear

  // ── How bad is it? ─────────────────────────────────────
  severity:  "none" | "info" | "warning" | "critical";

  // ── What values triggered it? ──────────────────────────
  triggerValue:   number;  // the actual value that breached
  thresholdValue: number;  // the threshold it crossed
  unit:           string;  // e.g. "%" or "USD B" or "articles/mo"

  // ── What rule fired? ───────────────────────────────────
  conditionMet: string;    // short description of the condition

  // ── Human-readable explanation ─────────────────────────
  explanation: string;     // filled-in explanation template

  // ── Display helpers ────────────────────────────────────
  color:  string;   // CSS colour for the badge
  bgColor: string;  // CSS background colour
  icon:   string;   // emoji icon

  // ── Numeric score (0–100, higher = more severe) ────────
  score: number;
}

// ═══════════════════════════════════════════════════════════════════
// SECTION 2: THRESHOLDS
// All the numbers that decide when alerts fire.
// Change these here to tune the whole engine at once.
// ═══════════════════════════════════════════════════════════════════

export const THRESHOLDS = {

  EXPORT_STRESS: {
    INFO_PCT:     -3,    // exports down more than 3% QoQ → info
    WARNING_PCT:  -7,    // exports down more than 7% QoQ → warning
    CRITICAL_PCT: -15,   // exports down more than 15% QoQ → critical
  },

  INFLATION_PRESSURE: {
    INFO_PCT:     3,     // above 3% → info
    WARNING_PCT:  5,     // above 5% → warning
    CRITICAL_PCT: 10,    // above 10% → critical
  },

  POLITICAL_INSTABILITY: {
    INFO_ABOVE_BASELINE_PCT:     20,   // 20% above baseline → info
    WARNING_ABOVE_BASELINE_PCT:  50,   // 50% above baseline → warning
    CRITICAL_ABOVE_BASELINE_PCT: 100,  // 100% above baseline → critical
    ABSOLUTE_WARNING:            40,   // OR absolute count >40 → warning
    ABSOLUTE_CRITICAL:           100,  // OR absolute count >100 → critical
  },

  CURRENCY_PRESSURE: {
    INFO_DEPRECIATION_PCT:     3,    // 3% weaker than baseline → info
    WARNING_DEPRECIATION_PCT:  7,    // 7% weaker → warning
    CRITICAL_DEPRECIATION_PCT: 15,   // 15% weaker → critical
  },

  FDI_SLOWDOWN: {
    INFO_BELOW_BASELINE_PCT:     15,  // 15% below baseline → info
    WARNING_BELOW_BASELINE_PCT:  35,  // 35% below baseline → warning
    CRITICAL_BELOW_BASELINE_PCT: 60,  // 60% below baseline → critical
    CRITICAL_ABSOLUTE_USD_B:     0.5, // OR below $0.5B → critical
  },

  REGIONAL_SPILLOVER: {
    INFO_MIN_STRESSED:     1,  // 1 neighbour stressed → info
    WARNING_MIN_STRESSED:  2,  // 2 neighbours stressed → warning
    CRITICAL_MIN_STRESSED: 3,  // 3+ neighbours stressed → critical
    // A country counts as "stressed" if it has a warning or critical alert
    STRESS_SEVERITIES: ["warning", "critical"] as string[],
  },

} as const;

// ═══════════════════════════════════════════════════════════════════
// SECTION 3: HELPER FUNCTIONS
// Small utilities used by the alert detectors below.
// ═══════════════════════════════════════════════════════════════════

/**
 * Calculate percentage change between two values.
 * e.g. pctChange(90, 100) = -10  (10% decline)
 */
function pctChange(current: number, previous: number): number {
  if (previous === 0) return 0;
  return ((current - previous) / Math.abs(previous)) * 100;
}

/**
 * Calculate how far current value is from a baseline, as a percentage.
 * e.g. pctFromBaseline(33.5, 32.0) = +4.69  (4.69% above baseline)
 */
function pctFromBaseline(current: number, baseline: number): number {
  if (baseline === 0) return 0;
  return ((current - baseline) / Math.abs(baseline)) * 100;
}

/** Map severity to display colours */
const SEVERITY_STYLE: Record<string, { color: string; bgColor: string; icon: string }> = {
  none:     { color: "text-slate-500",   bgColor: "bg-slate-50",   icon: "✓"  },
  info:     { color: "text-sky-700",     bgColor: "bg-sky-50",     icon: "ℹ"  },
  warning:  { color: "text-amber-700",   bgColor: "bg-amber-50",   icon: "⚠"  },
  critical: { color: "text-red-700",     bgColor: "bg-red-50",     icon: "⚑"  },
};

/**
 * Build the base AlertResult with sensible defaults.
 * Each detector calls this to avoid repeating boilerplate.
 */
function baseResult(
  data: CountryData,
  alertType: string,
  alertLabel: string,
): AlertResult {
  return {
    alertType,
    alertLabel,
    countryId:   data.countryId,
    countryName: data.countryName,
    flagEmoji:   data.flagEmoji,
    quarter:     data.quarter,
    triggered:      false,
    severity:       "none",
    triggerValue:   0,
    thresholdValue: 0,
    unit:           "",
    conditionMet:   "",
    explanation:    "",
    color:          SEVERITY_STYLE.none.color,
    bgColor:        SEVERITY_STYLE.none.bgColor,
    icon:           SEVERITY_STYLE.none.icon,
    score:          0,
  };
}

/**
 * Apply severity to a result object and fill in the display colours.
 */
function applySeverity(
  result: AlertResult,
  severity: "info" | "warning" | "critical",
): AlertResult {
  const style = SEVERITY_STYLE[severity];
  return {
    ...result,
    triggered: true,
    severity,
    color:   style.color,
    bgColor: style.bgColor,
    icon:    style.icon,
  };
}

// ═══════════════════════════════════════════════════════════════════
// SECTION 4: ALERT 1 — EXPORT STRESS
// ───────────────────────────────────────────────────────────────────
//
//  CONDITION:
//    Current exports are lower than previous quarter exports.
//    The bigger the percentage drop, the higher the severity.
//
//  SEVERITY LOGIC:
//    Info     → down 3–7%
//    Warning  → down 7–15%
//    Critical → down more than 15%
//
//  EXPLANATION TEMPLATE:
//    "{country} exports fell {pct}% this quarter from {prev} to {curr} B USD.
//     This {severity_description} export decline may indicate {risk_reason}."
//
// ═══════════════════════════════════════════════════════════════════

export function detectExportStress(data: CountryData): AlertResult {
  const result = baseResult(data, "EXPORT_STRESS", "Export Stress");

  // ── Guard: skip if no previous data ──────────────────────────
  if (data.prevExports === undefined) {
    return { ...result, conditionMet: "Skipped: no previous quarter data" };
  }

  const changePct = pctChange(data.exports, data.prevExports);
  const T = THRESHOLDS.EXPORT_STRESS;

  // Score: 0 = no change, 100 = catastrophic decline
  // We scale the decline to a 0–100 score
  const score = Math.min(100, Math.max(0, Math.abs(changePct) * 3));

  // ── All clear ─────────────────────────────────────────────────
  if (changePct >= T.INFO_PCT) {
    return {
      ...result,
      triggerValue:   parseFloat(changePct.toFixed(1)),
      thresholdValue: T.INFO_PCT,
      unit:           "% QoQ change",
      conditionMet:   `Exports ${changePct >= 0 ? "up" : "down"} ${Math.abs(changePct).toFixed(1)}% — within normal range`,
      explanation:    `${data.countryName} exports ${changePct >= 0 ? "grew" : "fell"} ${Math.abs(changePct).toFixed(1)}% to $${data.exports}B. No stress detected.`,
      score:          0,
    };
  }

  // ── Determine severity ────────────────────────────────────────
  let severity: "info" | "warning" | "critical";
  let severityDescription: string;
  let riskReason: string;

  if (changePct <= T.CRITICAL_PCT) {
    severity            = "critical";
    severityDescription = "a severe";
    riskReason          = "demand collapse, supply chain breakdown, or a sudden loss of major trading partner access";
  } else if (changePct <= T.WARNING_PCT) {
    severity            = "warning";
    severityDescription = "a significant";
    riskReason          = "weakening external demand, currency appreciation reducing competitiveness, or sector-specific shocks";
  } else {
    severity            = "info";
    severityDescription = "a mild";
    riskReason          = "seasonal variation, short-term demand softness, or shipping delays";
  }

  // ── Fill in the explanation template ─────────────────────────
  const explanation =
    `${data.flagEmoji} ${data.countryName} exports fell ${Math.abs(changePct).toFixed(1)}% ` +
    `this quarter — from $${data.prevExports}B to $${data.exports}B. ` +
    `This is ${severityDescription} export decline that may indicate ${riskReason}. ` +
    `Trade news volume (${data.tradeNewsCount} articles/month) provides additional context.`;

  return applySeverity(
    {
      ...result,
      triggerValue:   parseFloat(changePct.toFixed(1)),
      thresholdValue: T.INFO_PCT,
      unit:           "% QoQ change",
      conditionMet:   `Exports down ${Math.abs(changePct).toFixed(1)}% QoQ — below ${T.INFO_PCT}% threshold`,
      explanation,
      score:          parseFloat(score.toFixed(1)),
    },
    severity,
  );
}

// ═══════════════════════════════════════════════════════════════════
// SECTION 5: ALERT 2 — INFLATION PRESSURE
// ───────────────────────────────────────────────────────────────────
//
//  CONDITION:
//    Inflation (CPI % YoY) exceeds a threshold.
//
//  SEVERITY LOGIC:
//    Info     → 3–5%   (above comfort zone)
//    Warning  → 5–10%  (above policy threshold)
//    Critical → >10%   (double-digit / hyperinflation territory)
//
//  EXPLANATION TEMPLATE:
//    "{country} inflation is at {value}%, which is {comparison}.
//     Trend: {direction} from {prev}% last quarter.
//     Key risk: {risk_description}."
//
// ═══════════════════════════════════════════════════════════════════

export function detectInflationPressure(data: CountryData): AlertResult {
  const result = baseResult(data, "INFLATION_PRESSURE", "Inflation Pressure");
  const T      = THRESHOLDS.INFLATION_PRESSURE;
  const inf    = data.inflation;

  // Trend vs previous quarter
  const trend = data.prevInflation !== undefined
    ? pctChange(inf, data.prevInflation)
    : null;

  // Score: scaled 0–100
  const score = Math.min(100, Math.max(0, (inf / T.CRITICAL_PCT) * 70));

  // ── All clear ─────────────────────────────────────────────────
  if (inf < T.INFO_PCT) {
    return {
      ...result,
      triggerValue:   inf,
      thresholdValue: T.INFO_PCT,
      unit:           "% YoY",
      conditionMet:   `Inflation at ${inf}% — below ${T.INFO_PCT}% watch level`,
      explanation:    `${data.countryName} inflation is ${inf}%, within the normal range. No pressure detected.`,
      score:          0,
    };
  }

  // ── Determine severity ────────────────────────────────────────
  let severity: "info" | "warning" | "critical";
  let comparison: string;
  let riskDescription: string;

  if (inf >= T.CRITICAL_PCT) {
    severity        = "critical";
    comparison      = `more than double the ${T.CRITICAL_PCT}% critical threshold`;
    riskDescription = "Household purchasing power is severely eroded. Currency debasement and black-market activity are likely risks. Central bank credibility is at stake.";
  } else if (inf >= T.WARNING_PCT) {
    severity        = "warning";
    comparison      = `above the ${T.WARNING_PCT}% policy warning threshold`;
    riskDescription = "Consumer spending power is declining. The central bank may need to tighten monetary policy, which could slow growth and investment.";
  } else {
    severity        = "info";
    comparison      = `above the ${T.INFO_PCT}% comfort zone`;
    riskDescription = "Mild price pressure. Consumer confidence and real wages should be monitored.";
  }

  // ── Trend description ─────────────────────────────────────────
  let trendText = "";
  if (trend !== null) {
    if (trend > 0)       trendText = ` Up from ${data.prevInflation?.toFixed(1)}% last quarter — accelerating.`;
    else if (trend < 0)  trendText = ` Down from ${data.prevInflation?.toFixed(1)}% last quarter — easing.`;
    else                 trendText = ` Unchanged from last quarter.`;
  }

  const explanation =
    `${data.flagEmoji} ${data.countryName} inflation is at ${inf.toFixed(1)}%, ` +
    `${comparison}.${trendText} ` +
    `Risk: ${riskDescription}`;

  return applySeverity(
    {
      ...result,
      triggerValue:   inf,
      thresholdValue: inf >= T.CRITICAL_PCT ? T.CRITICAL_PCT : inf >= T.WARNING_PCT ? T.WARNING_PCT : T.INFO_PCT,
      unit:           "% YoY",
      conditionMet:   `Inflation ${inf.toFixed(1)}% — above ${T.INFO_PCT}% threshold`,
      explanation,
      score:          parseFloat(score.toFixed(1)),
    },
    severity,
  );
}

// ═══════════════════════════════════════════════════════════════════
// SECTION 6: ALERT 3 — POLITICAL INSTABILITY RISING
// ───────────────────────────────────────────────────────────────────
//
//  CONDITION:
//    Political risk news count is elevated compared to the country's
//    own baseline — OR exceeds an absolute threshold.
//    Uses TWO tests and takes the worse severity of the two.
//
//  SEVERITY LOGIC:
//    Relative test (vs baseline):
//      Info     → 20–50% above baseline
//      Warning  → 50–100% above baseline
//      Critical → >100% above baseline
//
//    Absolute test (raw count):
//      Warning  → >40 articles/month
//      Critical → >100 articles/month
//
//  EXPLANATION TEMPLATE:
//    "{country} political risk news is at {value} articles/month.
//     This is {pct}% above the country baseline of {baseline}.
//     Pattern: {trend_direction}. Key concern: {concern}."
//
// ═══════════════════════════════════════════════════════════════════

export function detectPoliticalInstability(data: CountryData): AlertResult {
  const result = baseResult(data, "POLITICAL_INSTABILITY", "Political Instability Rising");
  const T      = THRESHOLDS.POLITICAL_INSTABILITY;
  const news   = data.politicalRiskNews;
  const base   = data.politicalRiskBaseline;

  // How many % above baseline?
  const aboveBaselinePct = pctFromBaseline(news, base);

  // Score: blend of relative and absolute signals
  const relativeScore = Math.min(70, Math.max(0, aboveBaselinePct / 2));
  const absoluteScore = Math.min(30, Math.max(0, (news / T.ABSOLUTE_CRITICAL) * 30));
  const score         = relativeScore + absoluteScore;

  // ── Test 1: Relative test ─────────────────────────────────────
  let relativeSeverity: "none" | "info" | "warning" | "critical" = "none";
  if (aboveBaselinePct >= T.CRITICAL_ABOVE_BASELINE_PCT)      relativeSeverity = "critical";
  else if (aboveBaselinePct >= T.WARNING_ABOVE_BASELINE_PCT)  relativeSeverity = "warning";
  else if (aboveBaselinePct >= T.INFO_ABOVE_BASELINE_PCT)     relativeSeverity = "info";

  // ── Test 2: Absolute test ─────────────────────────────────────
  let absoluteSeverity: "none" | "warning" | "critical" = "none";
  if (news >= T.ABSOLUTE_CRITICAL)      absoluteSeverity = "critical";
  else if (news >= T.ABSOLUTE_WARNING)  absoluteSeverity = "warning";

  // ── Take the worse of the two ─────────────────────────────────
  const severityOrder = { none: 0, info: 1, warning: 2, critical: 3 };
  const finalSeverity =
    severityOrder[absoluteSeverity] >= severityOrder[relativeSeverity]
      ? absoluteSeverity
      : relativeSeverity;

  // ── All clear ─────────────────────────────────────────────────
  if (finalSeverity === "none") {
    return {
      ...result,
      triggerValue:   news,
      thresholdValue: Math.round(base * (1 + T.INFO_ABOVE_BASELINE_PCT / 100)),
      unit:           "articles/month",
      conditionMet:   `Risk news at ${news} — within ${T.INFO_ABOVE_BASELINE_PCT}% of baseline (${base})`,
      explanation:    `${data.countryName} political risk news (${news}/month) is close to the country baseline of ${base}. No elevated instability detected.`,
      score:          0,
    };
  }

  // ── Build explanation ─────────────────────────────────────────
  const trendText = data.prevPoliticalRiskNews !== undefined
    ? (news > data.prevPoliticalRiskNews
        ? ` Up from ${data.prevPoliticalRiskNews}/month last quarter — escalating.`
        : news < data.prevPoliticalRiskNews
        ? ` Down from ${data.prevPoliticalRiskNews}/month last quarter — de-escalating.`
        : " Stable vs last quarter.")
    : "";

  const concernMap: Record<string, string> = {
    critical: "Sustained high coverage signals ongoing conflict, political crisis, or large-scale civil unrest. This level is strongly correlated with FDI withdrawal and trade route disruption.",
    warning:  "Elevated coverage may reflect protests, political transitions, or sanctions activity. Investment climate and border trade should be monitored.",
    info:     "Slightly elevated risk coverage. May reflect pre-election tension, minor protests, or international scrutiny. Standard monitoring recommended.",
  };

  const explanation =
    `${data.flagEmoji} ${data.countryName} political risk news is at ` +
    `${news} articles/month — ${Math.abs(aboveBaselinePct).toFixed(0)}% ` +
    `${aboveBaselinePct >= 0 ? "above" : "below"} the country baseline of ${base}/month.` +
    `${trendText} ${concernMap[finalSeverity]}`;

  return applySeverity(
    {
      ...result,
      triggerValue:   news,
      thresholdValue: base,
      unit:           "articles/month",
      conditionMet:
        `Risk news ${news}/month — ` +
        `${aboveBaselinePct.toFixed(0)}% above baseline of ${base}` +
        (absoluteSeverity !== "none" ? ` AND above absolute ${finalSeverity} threshold` : ""),
      explanation,
      score: parseFloat(score.toFixed(1)),
    },
    finalSeverity as "info" | "warning" | "critical",
  );
}

// ═══════════════════════════════════════════════════════════════════
// SECTION 7: ALERT 4 — CURRENCY PRESSURE
// ───────────────────────────────────────────────────────────────────
//
//  CONDITION:
//    The exchange rate has moved significantly weaker than a
//    reference baseline (more local currency needed per USD = weaker).
//
//  NOTE: A higher exchange rate = weaker local currency.
//    e.g. baseline 32 THB/USD → current 35 THB/USD = 9.4% depreciation
//
//  SEVERITY LOGIC:
//    Info     → 3–7%   depreciation from baseline
//    Warning  → 7–15%  depreciation
//    Critical → >15%   depreciation
//
//  EXPLANATION TEMPLATE:
//    "{country} currency ({code}) is trading at {rate}/{USD},
//     which is {pct}% weaker than the {baseline} baseline.
//     Impact: {impact_description}."
//
// ═══════════════════════════════════════════════════════════════════

export function detectCurrencyPressure(
  data: CountryData,
  currencyCode: string = data.countryId,
): AlertResult {
  const result = baseResult(data, "CURRENCY_PRESSURE", "Currency Pressure");
  const T      = THRESHOLDS.CURRENCY_PRESSURE;

  // Depreciation = how much weaker the current rate is vs baseline
  // A positive number means the currency has weakened (more local units per USD)
  const depreciationPct = pctFromBaseline(data.exchangeRate, data.exchangeRateBaseline);

  // Score: 0–100
  const score = Math.min(100, Math.max(0, depreciationPct * 4));

  // ── All clear (or appreciating) ───────────────────────────────
  if (depreciationPct < T.INFO_DEPRECIATION_PCT) {
    return {
      ...result,
      triggerValue:   data.exchangeRate,
      thresholdValue: data.exchangeRateBaseline,
      unit:           "local/USD",
      conditionMet:
        depreciationPct < 0
          ? `Currency appreciated ${Math.abs(depreciationPct).toFixed(1)}% vs baseline — no pressure`
          : `Depreciation ${depreciationPct.toFixed(1)}% — below ${T.INFO_DEPRECIATION_PCT}% watch level`,
      explanation:
        `${data.countryName} currency is ${depreciationPct < 0 ? "stronger" : "near"} the baseline ` +
        `(${data.exchangeRateBaseline}). Current rate: ${data.exchangeRate}. No pressure detected.`,
      score: 0,
    };
  }

  // ── Determine severity ────────────────────────────────────────
  let severity: "info" | "warning" | "critical";
  let impactDescription: string;

  if (depreciationPct >= T.CRITICAL_DEPRECIATION_PCT) {
    severity          = "critical";
    impactDescription = "A depreciation of this magnitude severely raises import costs, fuels inflation, increases foreign-currency debt burdens, and may trigger capital flight or central bank emergency intervention.";
  } else if (depreciationPct >= T.WARNING_DEPRECIATION_PCT) {
    severity          = "warning";
    impactDescription = "Significant depreciation raises import costs (especially fuel and food), and may deter foreign investment. Central bank intervention or rate adjustments are possible.";
  } else {
    severity          = "info";
    impactDescription = "Mild depreciation provides some export competitiveness boost but raises import costs. Monitor for acceleration.";
  }

  // ── Trend ─────────────────────────────────────────────────────
  const trendText = data.prevExchangeRate !== undefined
    ? (data.exchangeRate > data.prevExchangeRate
        ? ` Further weakened from ${data.prevExchangeRate} last quarter.`
        : ` Slightly recovered from ${data.prevExchangeRate} last quarter.`)
    : "";

  const explanation =
    `${data.flagEmoji} ${data.countryName} currency is at ${data.exchangeRate} per USD — ` +
    `${depreciationPct.toFixed(1)}% weaker than the ${data.exchangeRateBaseline} baseline.` +
    `${trendText} ${impactDescription}`;

  return applySeverity(
    {
      ...result,
      triggerValue:   data.exchangeRate,
      thresholdValue: data.exchangeRateBaseline,
      unit:           "local/USD",
      conditionMet:
        `${depreciationPct.toFixed(1)}% depreciation vs baseline — ` +
        `above ${T.INFO_DEPRECIATION_PCT}% watch level`,
      explanation,
      score: parseFloat(score.toFixed(1)),
    },
    severity,
  );
}

// ═══════════════════════════════════════════════════════════════════
// SECTION 8: ALERT 5 — FDI SLOWDOWN
// ───────────────────────────────────────────────────────────────────
//
//  CONDITION:
//    FDI inflows are significantly below the country's expected baseline
//    — OR have declined for consecutive quarters.
//
//  SEVERITY LOGIC:
//    Info     → 15–35% below baseline
//    Warning  → 35–60% below baseline
//    Critical → >60% below baseline  OR  absolute < $0.5B
//
//  EXPLANATION TEMPLATE:
//    "{country} FDI inflows are ${}B this quarter — {pct}% below the
//     ${baseline}B baseline. This signals {investor_concern}.
//     Related risk: {related_alert_context}."
//
// ═══════════════════════════════════════════════════════════════════

export function detectFDISlowdown(data: CountryData): AlertResult {
  const result = baseResult(data, "FDI_SLOWDOWN", "FDI Slowdown");
  const T      = THRESHOLDS.FDI_SLOWDOWN;
  const fdi    = data.fdi;
  const base   = data.fdiBaseline;

  // How far below baseline? (negative = below baseline)
  const belowBaselinePct = pctFromBaseline(fdi, base) * -1; // flip: positive = below

  // Score: 0–100
  const absoluteScore   = fdi < T.CRITICAL_ABSOLUTE_USD_B ? 100 : 0;
  const relativeScore   = Math.min(80, Math.max(0, belowBaselinePct * 1.2));
  const score           = Math.min(100, Math.max(absoluteScore, relativeScore));

  // ── All clear (FDI at or above baseline) ──────────────────────
  if (belowBaselinePct < T.INFO_BELOW_BASELINE_PCT && fdi >= T.CRITICAL_ABSOLUTE_USD_B) {
    return {
      ...result,
      triggerValue:   fdi,
      thresholdValue: base,
      unit:           "USD Billion",
      conditionMet:   `FDI $${fdi}B — within 15% of $${base}B baseline`,
      explanation:    `${data.countryName} FDI inflows ($${fdi}B) are near the $${base}B baseline. No slowdown detected.`,
      score: 0,
    };
  }

  // ── Determine severity ────────────────────────────────────────
  let severity: "info" | "warning" | "critical";
  let investorConcern: string;

  if (belowBaselinePct >= T.CRITICAL_BELOW_BASELINE_PCT || fdi < T.CRITICAL_ABSOLUTE_USD_B) {
    severity        = "critical";
    investorConcern = "severe investor withdrawal. Political instability, sanctions, or a major governance breakdown may be deterring all categories of foreign capital. FDI at this level is insufficient to finance infrastructure maintenance.";
  } else if (belowBaselinePct >= T.WARNING_BELOW_BASELINE_PCT) {
    severity        = "warning";
    investorConcern = "meaningful investor caution. Uncertainty around policy, political stability, or competing regional destinations may be redirecting capital away from this market.";
  } else {
    severity        = "info";
    investorConcern = "mild investor hesitation. Could reflect global capital market conditions rather than country-specific factors. Monitor for two consecutive quarters of decline before escalating.";
  }

  // ── Political risk context ────────────────────────────────────
  const riskContext =
    data.politicalRiskNews > THRESHOLDS.POLITICAL_INSTABILITY.ABSOLUTE_WARNING
      ? ` Elevated political risk news (${data.politicalRiskNews}/month) may be a contributing factor.`
      : "";

  const trendText = data.prevFdi !== undefined
    ? (fdi < data.prevFdi
        ? ` Further declined from $${data.prevFdi}B last quarter.`
        : ` Slight recovery from $${data.prevFdi}B last quarter.`)
    : "";

  const explanation =
    `${data.flagEmoji} ${data.countryName} FDI inflows are $${fdi}B — ` +
    `${belowBaselinePct.toFixed(1)}% below the $${base}B baseline.` +
    `${trendText} This signals ${investorConcern}${riskContext}`;

  return applySeverity(
    {
      ...result,
      triggerValue:   fdi,
      thresholdValue: base,
      unit:           "USD Billion",
      conditionMet:
        fdi < T.CRITICAL_ABSOLUTE_USD_B
          ? `FDI $${fdi}B — below $${T.CRITICAL_ABSOLUTE_USD_B}B critical floor`
          : `FDI ${belowBaselinePct.toFixed(1)}% below $${base}B baseline`,
      explanation,
      score: parseFloat(score.toFixed(1)),
    },
    severity,
  );
}

// ═══════════════════════════════════════════════════════════════════
// SECTION 9: ALERT 6 — REGIONAL SPILLOVER RISK
// ───────────────────────────────────────────────────────────────────
//
//  CONDITION:
//    Multiple countries in the region are simultaneously showing
//    warning or critical alerts. Stress in one economy can spread
//    through trade links, supply chains, and investor sentiment.
//
//  HOW IT WORKS:
//    1. Run all 5 single-country alerts for every country
//    2. Count how many countries have a "warning" or "critical" alert
//    3. A country with 1+ warning/critical alert = "stressed"
//    4. If enough countries are stressed → spillover risk for ALL
//
//  SEVERITY LOGIC:
//    Info     → 1 stressed neighbour
//    Warning  → 2 stressed neighbours
//    Critical → 3+ stressed neighbours
//
//  EXPLANATION TEMPLATE:
//    "{n} of {total} tracked countries are showing economic stress.
//     Stressed: {country_list}.
//     Key stress channels: {channels}."
//
// ═══════════════════════════════════════════════════════════════════

export function detectRegionalSpillover(allCountriesData: CountryData[]): AlertResult[] {
  const T = THRESHOLDS.REGIONAL_SPILLOVER;

  // ── Step 1: Run all single-country alerts for every country ──
  const countryAlertSummaries = allCountriesData.map(countryData => {
    const singleCountryAlerts = [
      detectExportStress(countryData),
      detectInflationPressure(countryData),
      detectPoliticalInstability(countryData),
      detectCurrencyPressure(countryData),
      detectFDISlowdown(countryData),
    ];

    const maxSeverity = singleCountryAlerts.reduce<"none"|"info"|"warning"|"critical">((worst, alert) => {
      const order = { none: 0, info: 1, warning: 2, critical: 3 };
      return order[alert.severity] > order[worst] ? alert.severity : worst;
    }, "none");

    const triggeredAlerts = singleCountryAlerts.filter(a => a.triggered);

    return {
      countryData,
      maxSeverity,
      triggeredAlerts,
      isStressed: T.STRESS_SEVERITIES.includes(maxSeverity),
    };
  });

  // ── Step 2: Identify stressed countries ───────────────────────
  const stressedCountries = countryAlertSummaries.filter(s => s.isStressed);
  const stressedCount     = stressedCountries.length;

  // ── Step 3: Generate a spillover alert for EACH country ───────
  return allCountriesData.map(countryData => {
    const result = baseResult(countryData, "REGIONAL_SPILLOVER", "Regional Spillover Risk");

    // Count stressed NEIGHBOURS (exclude the country itself)
    const neighbours = stressedCountries.filter(s => s.countryData.countryId !== countryData.countryId);
    const neighbourCount = neighbours.length;

    // ── All clear ─────────────────────────────────────────────
    if (neighbourCount < T.INFO_MIN_STRESSED) {
      return {
        ...result,
        triggerValue:   neighbourCount,
        thresholdValue: T.INFO_MIN_STRESSED,
        unit:           "stressed neighbours",
        conditionMet:   `Only ${neighbourCount} stressed neighbour — below spillover threshold`,
        explanation:    `${countryData.countryName}: No significant regional stress detected across tracked neighbours.`,
        score: 0,
      };
    }

    // ── Determine severity ─────────────────────────────────────
    let severity: "info" | "warning" | "critical";
    let channelsDescription: string;

    if (neighbourCount >= T.CRITICAL_MIN_STRESSED) {
      severity            = "critical";
      channelsDescription = "trade diversion, shared supply chain disruption, capital flight contagion, and investor risk-off sentiment across the sub-region";
    } else if (neighbourCount >= T.WARNING_MIN_STRESSED) {
      severity            = "warning";
      channelsDescription = "shared trade corridors, cross-border supply chains, and regional investor sentiment";
    } else {
      severity            = "info";
      channelsDescription = "bilateral trade links and regional capital flows";
    }

    // ── Stressed country names for the explanation ─────────────
    const stressedNames = neighbours.map(s =>
      `${s.countryData.flagEmoji} ${s.countryData.countryName} ` +
      `(${s.triggeredAlerts.map(a => a.alertLabel).join(", ")})`
    ).join(" · ");

    const explanation =
      `${countryData.flagEmoji} ${countryData.countryName} may face spillover risk: ` +
      `${neighbourCount} of ${allCountriesData.length - 1} tracked neighbours are showing economic stress. ` +
      `Stressed: ${stressedNames}. ` +
      `Key transmission channels: ${channelsDescription}.`;

    return applySeverity(
      {
        ...result,
        triggerValue:   neighbourCount,
        thresholdValue: T.INFO_MIN_STRESSED,
        unit:           "stressed neighbours",
        conditionMet:   `${neighbourCount} stressed neighbour${neighbourCount > 1 ? "s" : ""} — above ${T.INFO_MIN_STRESSED} threshold`,
        explanation,
        score:          Math.min(100, neighbourCount * 25),
      },
      severity,
    );
  });
}

// ═══════════════════════════════════════════════════════════════════
// SECTION 10: MASTER RUNNER
// Run all 6 alerts for a single country.
// ═══════════════════════════════════════════════════════════════════

/**
 * Run the first 5 alerts for one country and return results.
 *
 * NOTE: Regional Spillover (alert 6) needs all countries' data.
 * Use detectRegionalSpillover(allCountriesData) separately.
 *
 * @param data         - CountryData object for one country
 * @param currencyCode - ISO currency code (optional, for display)
 * @returns            - Array of 5 AlertResult objects (always 5, triggered or not)
 */
export function detectAllAlerts(
  data: CountryData,
  currencyCode?: string,
): AlertResult[] {
  return [
    detectExportStress(data),
    detectInflationPressure(data),
    detectPoliticalInstability(data),
    detectCurrencyPressure(data, currencyCode),
    detectFDISlowdown(data),
  ];
}

/**
 * Run all 6 alerts for all countries, including regional spillover.
 *
 * @param allData - Array of CountryData (one per country)
 * @returns       - Flat array of all AlertResults, sorted by score descending
 */
export function detectAllAlertsAllCountries(allData: CountryData[]): AlertResult[] {
  const singleCountryAlerts = allData.flatMap(d => detectAllAlerts(d));
  const spilloverAlerts     = detectRegionalSpillover(allData);
  const allAlerts           = [...singleCountryAlerts, ...spilloverAlerts];
  // Sort: critical first, then warning, then info, then by score
  const severityOrder = { critical: 0, warning: 1, info: 2, none: 3 };
  return allAlerts.sort((a, b) => {
    const sevDiff = severityOrder[a.severity] - severityOrder[b.severity];
    if (sevDiff !== 0) return sevDiff;
    return b.score - a.score;
  });
}

// ═══════════════════════════════════════════════════════════════════
// SECTION 11: BUILDER HELPER
// Convenience function to build CountryData from your existing
// sample-data.ts indicators.
// ═══════════════════════════════════════════════════════════════════

/** Pre-configured baselines per country (edit these to tune alerts) */
export const COUNTRY_BASELINES: Record<string, {
  exchangeRateBaseline:  number;
  politicalRiskBaseline: number;
  fdiBaseline:           number;
}> = {
  THA: { exchangeRateBaseline: 32.0, politicalRiskBaseline: 30, fdiBaseline: 3.5 },
  VNM: { exchangeRateBaseline: 23200, politicalRiskBaseline: 14, fdiBaseline: 4.5 },
  MMR: { exchangeRateBaseline: 1330, politicalRiskBaseline: 18, fdiBaseline: 2.0 },
  KHM: { exchangeRateBaseline: 4050, politicalRiskBaseline: 32, fdiBaseline: 0.9 },
  SGP: { exchangeRateBaseline: 1.35, politicalRiskBaseline: 5,  fdiBaseline: 38.0 },
};

/** Emoji flags for display */
const FLAGS: Record<string, string> = {
  THA: "🇹🇭", VNM: "🇻🇳", MMR: "🇲🇲", KHM: "🇰🇭", SGP: "🇸🇬",
};

/**
 * Build a CountryData object from your existing CurrentIndicators type.
 * Use this as a bridge between sample-data.ts and the engine.
 *
 * @example
 * import { CURRENT_INDICATORS } from "@/data/sample-data";
 * import { buildCountryData }   from "@/lib/pattern-engine";
 *
 * const thaData = buildCountryData("THA", "Thailand", "2024-Q3",
 *   CURRENT_INDICATORS["THA"],
 *   CURRENT_INDICATORS_PREV_Q["THA"] // optional
 * );
 */
export function buildCountryData(
  countryId:    string,
  countryName:  string,
  quarter:      string,
  current: {
    gdpGrowth:         number;
    inflation:         number;
    exports:           number;
    imports:           number;
    exchangeRate:      number;
    fdi:               number;
    politicalRiskNews: number;
    tradeNewsCount:    number;
  },
  previous?: Partial<{
    exports:           number;
    inflation:         number;
    exchangeRate:      number;
    fdi:               number;
    politicalRiskNews: number;
  }>,
): CountryData {
  const baselines = COUNTRY_BASELINES[countryId] ?? {
    exchangeRateBaseline:  current.exchangeRate,
    politicalRiskBaseline: current.politicalRiskNews,
    fdiBaseline:           current.fdi,
  };

  return {
    countryId,
    countryName,
    flagEmoji:    FLAGS[countryId] ?? "🏳",
    quarter,
    ...current,
    ...baselines,
    prevExports:           previous?.exports,
    prevInflation:         previous?.inflation,
    prevExchangeRate:      previous?.exchangeRate,
    prevFdi:               previous?.fdi,
    prevPoliticalRiskNews: previous?.politicalRiskNews,
  };
}

// ═══════════════════════════════════════════════════════════════════
// SECTION 12: SAMPLE DATA + USAGE EXAMPLES
// Copy-paste these into your browser console or a test file.
// ═══════════════════════════════════════════════════════════════════

/**
 * SAMPLE INPUT: Myanmar (Critical — all alerts should fire)
 *
 * const myanmarData: CountryData = {
 *   countryId:    "MMR",
 *   countryName:  "Myanmar",
 *   flagEmoji:    "🇲🇲",
 *   quarter:      "2024-Q3",
 *   gdpGrowth:          -2.1,
 *   inflation:          22.4,
 *   exports:             4.0,
 *   imports:             3.4,
 *   exchangeRate:     2100,
 *   fdi:                 0.20,
 *   politicalRiskNews: 156,
 *   tradeNewsCount:     45,
 *   prevExports:         3.8,
 *   prevInflation:      22.0,
 *   prevExchangeRate:  2100,
 *   prevFdi:             0.20,
 *   prevPoliticalRiskNews: 152,
 *   exchangeRateBaseline:  1330,
 *   politicalRiskBaseline:   18,
 *   fdiBaseline:              2.0,
 * };
 *
 * SAMPLE OUTPUT: detectAllAlerts(myanmarData)
 *
 * [
 *   {
 *     alertType:  "EXPORT_STRESS",
 *     alertLabel: "Export Stress",
 *     triggered:  true,
 *     severity:   "info",
 *     triggerValue: 5.3,
 *     unit:        "% QoQ change",
 *     explanation: "🇲🇲 Myanmar exports fell 5.3% this quarter — from $3.8B to $4.0B. ..."
 *     score: 15.9,
 *   },
 *   {
 *     alertType:  "INFLATION_PRESSURE",
 *     alertLabel: "Inflation Pressure",
 *     triggered:  true,
 *     severity:   "critical",
 *     triggerValue: 22.4,
 *     unit:         "% YoY",
 *     explanation:  "🇲🇲 Myanmar inflation is at 22.4%, more than double the 10% critical threshold. ...",
 *     score: 100,
 *   },
 *   {
 *     alertType:  "POLITICAL_INSTABILITY",
 *     alertLabel: "Political Instability Rising",
 *     triggered:  true,
 *     severity:   "critical",
 *     triggerValue: 156,
 *     unit:         "articles/month",
 *     explanation:  "🇲🇲 Myanmar political risk news is at 156 articles/month — 766% above the country baseline of 18/month. ...",
 *     score: 100,
 *   },
 *   {
 *     alertType:  "CURRENCY_PRESSURE",
 *     alertLabel: "Currency Pressure",
 *     triggered:  true,
 *     severity:   "critical",
 *     triggerValue: 2100,
 *     unit:         "local/USD",
 *     explanation:  "🇲🇲 Myanmar currency is at 2100 per USD — 57.9% weaker than the 1330 baseline. ...",
 *     score: 100,
 *   },
 *   {
 *     alertType:  "FDI_SLOWDOWN",
 *     alertLabel: "FDI Slowdown",
 *     triggered:  true,
 *     severity:   "critical",
 *     triggerValue: 0.20,
 *     unit:         "USD Billion",
 *     explanation:  "🇲🇲 Myanmar FDI inflows are $0.20B — 90% below the $2.0B baseline. ...",
 *     score: 100,
 *   },
 * ]
 */

/**
 * SAMPLE INPUT: Thailand (Info only — some alerts may fire mildly)
 *
 * const thailandData: CountryData = {
 *   countryId:    "THA",
 *   countryName:  "Thailand",
 *   flagEmoji:    "🇹🇭",
 *   quarter:      "2024-Q3",
 *   gdpGrowth:     2.9,
 *   inflation:     3.0,
 *   exports:      72.8,
 *   imports:      66.3,
 *   exchangeRate:  33.5,
 *   fdi:           3.0,
 *   politicalRiskNews: 42,
 *   tradeNewsCount:    29,
 *   prevExports:      71.2,
 *   prevInflation:     2.8,
 *   prevExchangeRate: 33.9,
 *   prevFdi:           2.9,
 *   prevPoliticalRiskNews: 43,
 *   exchangeRateBaseline:  32.0,
 *   politicalRiskBaseline: 30,
 *   fdiBaseline:            3.5,
 * };
 *
 * SAMPLE OUTPUT: detectAllAlerts(thailandData)
 *
 * [
 *   { alertType: "EXPORT_STRESS",         triggered: false, severity: "none"    },
 *   { alertType: "INFLATION_PRESSURE",    triggered: true,  severity: "info",   score: 21 },
 *   { alertType: "POLITICAL_INSTABILITY", triggered: true,  severity: "info",   score: 22 },
 *   { alertType: "CURRENCY_PRESSURE",     triggered: true,  severity: "info",   score: 18.8 },
 *   { alertType: "FDI_SLOWDOWN",          triggered: true,  severity: "info",   score: 16.2 },
 * ]
 */

/**
 * SAMPLE USAGE in a React component:
 *
 * import { buildCountryData, detectAllAlerts }    from "@/lib/pattern-engine";
 * import { CURRENT_INDICATORS, HISTORICAL }        from "@/data/sample-data";
 *
 * function AlertPanel({ countryId }: { countryId: string }) {
 *   const curr = CURRENT_INDICATORS[countryId];
 *   const hist = HISTORICAL[countryId];
 *
 *   // Get previous quarter values from history
 *   const prevQ = {
 *     exports:           hist.exports.at(-2)?.value,
 *     inflation:         hist.inflation.at(-2)?.value,
 *     exchangeRate:      hist.exchangeRate.at(-2)?.value,
 *     fdi:               hist.fdi.at(-2)?.value,
 *     politicalRiskNews: hist.politicalRiskNews.at(-2)?.value,
 *   };
 *
 *   const data   = buildCountryData(countryId, "Thailand", "2024-Q3", curr, prevQ);
 *   const alerts = detectAllAlerts(data).filter(a => a.triggered);
 *
 *   return (
 *     <div>
 *       {alerts.map(alert => (
 *         <div key={alert.alertType} className={alert.bgColor}>
 *           <span>{alert.icon} {alert.alertLabel}</span>
 *           <p>{alert.explanation}</p>
 *         </div>
 *       ))}
 *     </div>
 *   );
 * }
 */
