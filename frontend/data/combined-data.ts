/**
 * frontend/data/combined-data.ts
 * ──────────────────────────────────────────────────────────────────────────────
 * Reads pipeline/data/processed/combined_indicators.json — the merged file
 * that contains:
 *   • World Bank official annual actuals (value_type: official_actual)  2015–2024
 *   • IMF WEO forecasts for cells where WB hasn't published yet         2025–2026
 *     (value_type: forecast_estimate)
 *   • Null rows for truly missing data (value_type: missing_official)
 *
 * Use this file when you want the dashboard to show the most complete picture
 * possible, including labeled forecasts for recent years.
 *
 * IMPORTANT:
 *   • forecast_estimate values MUST be visually distinguished from official_actual.
 *   • Never display a forecast alongside an official value without a badge.
 *   • Use VALUE_TYPE_LABEL / VALUE_TYPE_COLOR from worldbank-data.ts for badges.
 *
 * HOW TO REFRESH:
 *   python scripts/fetch_worldbank.py
 *   python scripts/scrape_latest_estimates.py
 *   (restart the Next.js dev server)
 *
 * BADGE GUIDE (show on every displayed value):
 *   official_actual   → "Official"  (emerald)
 *   forecast_estimate → "Estimate"  (amber)
 *   missing_official  → "No data"   (slate / grey)
 * ──────────────────────────────────────────────────────────────────────────────
 */

// eslint-disable-next-line @typescript-eslint/no-require-imports
const _combined = require("../../pipeline/data/processed/combined_indicators.json") as CombinedJson;

import type { WbRecord, WbDataQuality, WbValueType, WbLatest } from "@/data/worldbank-data";
import {
  VALUE_TYPE_LABEL,
  VALUE_TYPE_COLOR,
  VALUE_TYPE_DOT,
  getValueType,
} from "@/data/worldbank-data";

export type { WbRecord, WbDataQuality, WbValueType, WbLatest };
export { VALUE_TYPE_LABEL, VALUE_TYPE_COLOR, VALUE_TYPE_DOT };


// ── Raw JSON type ─────────────────────────────────────────────────────────────

interface CombinedMeta {
  generated_at:       string;
  description:        string;
  total_records:      number;
  official_actual:    number;
  forecast_estimate:  number;
  missing:            number;
  source_files:       string[];
  badge_guide:        Record<WbValueType, string>;
  important_note:     string;
}

interface CombinedJson {
  meta:    CombinedMeta;
  records: WbRecord[];
}


// ── Exports ───────────────────────────────────────────────────────────────────

/** All records from combined_indicators.json (official + forecasts + missing) */
export const COMBINED_RECORDS: WbRecord[] = _combined.records;

/** Pipeline metadata */
export const COMBINED_META: CombinedMeta = _combined.meta;

/** Counts */
export const COMBINED_OFFICIAL_COUNT:  number = _combined.meta.official_actual;
export const COMBINED_ESTIMATE_COUNT:  number = _combined.meta.forecast_estimate;
export const COMBINED_MISSING_COUNT:   number = _combined.meta.missing;

/**
 * Note for UI banners — explains what "combined" means.
 * Show this on any page that uses forecast data.
 */
export const COMBINED_DATA_NOTE =
  "2025–2026 values may be unavailable in official annual datasets. " +
  "Forecasts (labeled 'Estimate') are sourced from the IMF World Economic Outlook " +
  "and should not be treated as confirmed actual data.";


// ── Lookup helpers ────────────────────────────────────────────────────────────

/**
 * Get the most recent non-missing value for a country-indicator from
 * combined data (official + estimates).
 *
 * Priority: official_actual > forecast_estimate
 * Returns null if no data exists.
 */
export function getCombinedLatest(
  iso3:         string,
  indicatorKey: string,
): WbLatest | null {
  const recs = COMBINED_RECORDS.filter(
    r =>
      r.country_code  === iso3 &&
      r.indicator_key === indicatorKey &&
      r.value !== null,
  ).sort((a, b) => b.year - a.year);

  if (recs.length === 0) return null;

  // Always prefer official_actual over forecast_estimate
  const official = recs.find(r => getValueType(r) === "official_actual");
  const best = official ?? recs[0];

  return {
    value:   best.value as number,
    year:    best.year,
    unit:    best.unit,
    quality: best.data_quality,
  };
}

/**
 * Get the full history for one country-indicator, including both
 * official actuals and forecasts. Sorted ascending by year.
 * Skips null values.
 */
export function getCombinedHistory(
  iso3:         string,
  indicatorKey: string,
): (WbLatest & { value_type: WbValueType })[] {
  return COMBINED_RECORDS
    .filter(
      r =>
        r.country_code  === iso3 &&
        r.indicator_key === indicatorKey &&
        r.value !== null,
    )
    .map(r => ({
      year:       r.year,
      value:      r.value as number,
      unit:       r.unit,
      quality:    r.data_quality,
      value_type: getValueType(r),
    }))
    .sort((a, b) => a.year - b.year);
}

/**
 * Get a specific record by country, indicator, and year.
 * Returns null if not found.
 */
export function getCombinedRecord(
  iso3:         string,
  indicatorKey: string,
  year:         number,
): WbRecord | null {
  return (
    COMBINED_RECORDS.find(
      r =>
        r.country_code  === iso3 &&
        r.indicator_key === indicatorKey &&
        r.year          === year,
    ) ?? null
  );
}

/**
 * Get all latest combined values for one country — all 8 indicators.
 * Returns a dict: { indicatorKey → WbLatest | null }
 */
export function getCombinedCountrySummary(
  iso3: string,
): Record<string, WbLatest | null> {
  const indicatorKeys = [
    "gdpGrowth", "gdpNominal", "inflation", "unemployment",
    "fdiPctGdp", "exports", "imports", "population",
  ];
  return Object.fromEntries(
    indicatorKeys.map(key => [key, getCombinedLatest(iso3, key)]),
  );
}

/**
 * Precomputed summaries for all 17 countries.
 * COMBINED_COUNTRY_SUMMARIES[iso3][indicatorKey] → WbLatest | null
 */
const _countrySet = new Set(COMBINED_RECORDS.map(r => r.country_code));
export const COMBINED_COUNTRY_SUMMARIES: Record<string, Record<string, WbLatest | null>> =
  Object.fromEntries(
    [..._countrySet].map(iso3 => [iso3, getCombinedCountrySummary(iso3)]),
  );


// ── Forecast-specific helpers ─────────────────────────────────────────────────

/** All 2025/2026 forecast_estimate records */
export const FORECAST_RECORDS: WbRecord[] = COMBINED_RECORDS.filter(
  r => getValueType(r) === "forecast_estimate",
);

/** Countries that have at least one forecast_estimate */
export const COUNTRIES_WITH_ESTIMATES: Set<string> = new Set(
  FORECAST_RECORDS.map(r => r.country_code),
);

/** Returns true if a record is a forecast/estimate (not confirmed actual) */
export function isForecast(record: WbRecord): boolean {
  return getValueType(record) === "forecast_estimate";
}

/** Returns true if a record has confirmed World Bank official data */
export function isOfficial(record: WbRecord): boolean {
  return getValueType(record) === "official_actual";
}

/** Returns true if this cell has no data at all */
export function isMissing(record: WbRecord): boolean {
  return record.value === null;
}
