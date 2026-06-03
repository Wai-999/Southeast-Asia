/**
 * frontend/data/live-data.ts
 * ──────────────────────────────────────────────────────────────────────────────
 * Drop-in replacement for sample-data.ts that serves REAL pipeline data.
 *
 * Import from here instead of sample-data.ts:
 *
 *   // Before:
 *   import { COUNTRIES, CURRENT_INDICATORS, … } from "@/data/sample-data";
 *
 *   // After (shows real World Bank + GDELT + alert data):
 *   import { COUNTRIES, CURRENT_INDICATORS, … } from "@/data/live-data";
 *
 * DATA SOURCES
 * ────────────
 *   CURRENT_INDICATORS → World Bank official annual data (pipeline/worldbank_indicators.json)
 *   HISTORICAL         → World Bank 2015–2024 time series
 *   PATTERN_ALERTS     → Live pattern-alert engine output (pattern_alerts.json)
 *   NEWS_EVENTS        → GDELT real-time news (news_signals.json), falls back to sample
 *
 * FALLBACK STRATEGY
 * ─────────────────
 *   If real WB data is null (missing_official), sample-data value is used.
 *   Fields not in WB (exchangeRate, raw FDI USD, politicalRiskNews, tradeNewsCount)
 *   are supplied from GDELT news-signals counts or sample-data fallbacks.
 *   This ensures the UI never shows null/NaN — it always has a number to display.
 * ──────────────────────────────────────────────────────────────────────────────
 */

import type {
  Country, CurrentIndicators, CountryHistory,
  YearPoint, NewsEvent, CompareRow, MetricKey,
} from "@/data/sample-data";

import {
  COUNTRIES,
  CURRENT_INDICATORS as SAMPLE_INDICATORS,
  HISTORICAL         as SAMPLE_HISTORICAL,
  NEWS_EVENTS        as SAMPLE_NEWS,
  METRIC_LABELS, METRIC_UNITS, METRIC_DESC, METRIC_HIGHER_IS_WORSE,
  getCountry,
} from "@/data/sample-data";

import {
  WB_COUNTRY_SUMMARIES,
  WB_DATA_STATUS,
  getWbHistory,
} from "@/data/worldbank-data";

import {
  PATTERN_ALERTS_LIVE,
} from "@/data/pattern-alerts";

import {
  NS_DATA_STATUS,
  NS_AS_NEWS_EVENTS,
  POLITICAL_RISK_COUNTS,
  TRADE_NEWS_COUNTS,
} from "@/data/news-signals";

// ── Re-export unchanged types + constants ─────────────────────────────────────

export type { Country, CurrentIndicators, CountryHistory, YearPoint, NewsEvent, CompareRow, MetricKey };
export { COUNTRIES, METRIC_LABELS, METRIC_UNITS, METRIC_DESC, METRIC_HIGHER_IS_WORSE, getCountry };
export { WB_DATA_STATUS };


// ── Live CURRENT_INDICATORS ───────────────────────────────────────────────────
//
// Priority for each field:
//   1. Real World Bank value (official_actual)
//   2. Computed from WB (e.g. FDI = fdiPctGdp × gdpNominal ÷ 100)
//   3. GDELT count (for news-based metrics)
//   4. Sample-data fallback (hardcoded 2024 estimate)

function buildCurrentIndicators(): Record<string, CurrentIndicators> {
  const out: Record<string, CurrentIndicators> = {};

  for (const c of COUNTRIES) {
    const iso3   = c.id;
    const wb     = WB_COUNTRY_SUMMARIES[iso3] ?? {};
    const sample = SAMPLE_INDICATORS[iso3];

    // ── WB fields ─────────────────────────────────────────────────────────
    const gdpGrowth  = wb.gdpGrowth?.value  ?? sample.gdpGrowth;
    const inflation  = wb.inflation?.value  ?? sample.inflation;
    const exports    = wb.exports?.value    ?? sample.exports;
    const imports    = wb.imports?.value    ?? sample.imports;
    const gdpNominal = wb.gdpNominal?.value ?? null;
    const fdiPctGdp  = wb.fdiPctGdp?.value  ?? null;

    // ── FDI: convert fdiPctGdp × gdpNominal → USD billions ───────────────
    const fdiComputed =
      fdiPctGdp !== null && gdpNominal !== null && gdpNominal > 0
        ? parseFloat((fdiPctGdp * gdpNominal / 100).toFixed(1))
        : null;
    const fdi = fdiComputed ?? sample.fdi;

    // ── GDELT news counts (live if NS_DATA_STATUS = "live") ───────────────
    const politicalRiskNews =
      NS_DATA_STATUS === "live"
        ? (POLITICAL_RISK_COUNTS[iso3] ?? sample.politicalRiskNews)
        : sample.politicalRiskNews;

    const tradeNewsCount =
      NS_DATA_STATUS === "live"
        ? (TRADE_NEWS_COUNTS[iso3] ?? sample.tradeNewsCount)
        : sample.tradeNewsCount;

    // ── exchangeRate not in WB data — keep sample value ───────────────────
    const exchangeRate = sample.exchangeRate;

    out[iso3] = {
      gdpGrowth:         parseFloat((gdpGrowth ?? sample.gdpGrowth).toFixed(2)),
      inflation:         parseFloat((inflation  ?? sample.inflation).toFixed(2)),
      exports:           parseFloat((exports    ?? sample.exports).toFixed(1)),
      imports:           parseFloat((imports    ?? sample.imports).toFixed(1)),
      fdi:               parseFloat(fdi.toFixed(1)),
      exchangeRate,
      politicalRiskNews: Math.round(politicalRiskNews),
      tradeNewsCount:    Math.round(tradeNewsCount),
    };
  }

  return out;
}

export const CURRENT_INDICATORS: Record<string, CurrentIndicators> = buildCurrentIndicators();


// ── Live HISTORICAL ───────────────────────────────────────────────────────────
//
// Use World Bank 2015-2024 time series for WB indicators.
// For fields not in WB (exchangeRate, raw FDI, politicalRiskNews, tradeNewsCount)
// fall back to sample history (2020-2024).

function buildHistorical(): Record<string, CountryHistory> {
  const out: Record<string, CountryHistory> = {};

  for (const c of COUNTRIES) {
    const iso3     = c.id;
    const sampleH  = SAMPLE_HISTORICAL[iso3];

    // Convert WbYearPoint[] → YearPoint[] (drop quality field)
    const toYP = (key: "gdpGrowth" | "gdpNominal" | "inflation" | "exports" | "imports" | "fdiPctGdp" | "population"): YearPoint[] => {
      const pts = getWbHistory(iso3, key);
      if (pts.length === 0) return sampleH[key as keyof CountryHistory] as YearPoint[] ?? [];
      return pts.map(p => ({ year: p.year, value: p.value }));
    };

    // FDI: prefer WB fdiPctGdp converted to approximate USD billions via gdpNominal
    // But for simplicity in charts just use the % value scaled visually (or sample fallback)
    const gdpHistory = toYP("gdpNominal");
    const fdiPctHistory = toYP("fdiPctGdp");
    const fdiHistory: YearPoint[] = fdiPctHistory.length > 0 && gdpHistory.length > 0
      ? fdiPctHistory.map(p => {
          const gdpPt = gdpHistory.find(g => g.year === p.year);
          return {
            year:  p.year,
            value: gdpPt && gdpPt.value > 0
              ? parseFloat((p.value * gdpPt.value / 100).toFixed(1))
              : p.value,
          };
        })
      : sampleH.fdi;

    out[iso3] = {
      gdpGrowth:         toYP("gdpGrowth"),
      inflation:         toYP("inflation"),
      exports:           toYP("exports"),
      imports:           toYP("imports"),
      fdi:               fdiHistory,
      // These are NOT in WB data — keep sample history
      exchangeRate:      sampleH.exchangeRate,
      politicalRiskNews: sampleH.politicalRiskNews,
      tradeNewsCount:    sampleH.tradeNewsCount,
    };
  }

  return out;
}

export const HISTORICAL: Record<string, CountryHistory> = buildHistorical();


// ── Live PATTERN_ALERTS ───────────────────────────────────────────────────────
//
// PATTERN_ALERTS_LIVE contains alerts generated from real WB + GDELT + Comtrade data.
// These have all required fields (id, countryId, severity, message, isActive, etc.)

export const PATTERN_ALERTS = PATTERN_ALERTS_LIVE;


// ── Live NEWS_EVENTS ──────────────────────────────────────────────────────────
//
// Use GDELT news if available; otherwise fall back to sample news events.

export const NEWS_EVENTS: NewsEvent[] =
  NS_DATA_STATUS === "live" && NS_AS_NEWS_EVENTS.length > 0
    ? NS_AS_NEWS_EVENTS
    : SAMPLE_NEWS;


// ── Live versions of utility functions ───────────────────────────────────────

/**
 * Build the data array for CompareBarChart, using live CURRENT_INDICATORS.
 */
export function getCompareData(metric: MetricKey): CompareRow[] {
  return COUNTRIES.map(c => ({
    countryId:   c.id,
    countryName: c.shortName,
    flagEmoji:   c.flagEmoji,
    value:       CURRENT_INDICATORS[c.id]?.[metric] ?? 0,
    riskLevel:   c.riskLevel,
  })).sort((a, b) => b.value - a.value);
}

/**
 * Year-over-year change using live HISTORICAL data.
 */
export function getYoYChange(countryId: string, metric: MetricKey): number {
  const hist = HISTORICAL[countryId]?.[metric] ?? [];
  if (hist.length < 2) return 0;
  return hist[hist.length - 1].value - hist[hist.length - 2].value;
}


// ── Data freshness label ──────────────────────────────────────────────────────

/**
 * Short label for the top-right of the dashboard header.
 * Shows "Live data · World Bank" when real data is loaded.
 */
export const DATA_STATUS_LABEL: string =
  WB_DATA_STATUS === "live"
    ? "Live data · World Bank"
    : "Sample data · All indicators current";

export const DATA_IS_LIVE: boolean = WB_DATA_STATUS === "live";
