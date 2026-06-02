/**
 * frontend/data/refresh-status.ts
 * ─────────────────────────────────────────────────────────────────────────────
 * TypeScript adapter for pipeline/data/processed/refresh_log.json.
 *
 * Exposes the last-update timestamps for each data source so the
 * DataFreshnessBar component can show a live "data freshness" badge.
 *
 * HOW TO REFRESH:
 *   cd pipeline && python run_pipeline.py --mode news      (every 6 h)
 *   cd pipeline && python run_pipeline.py --mode data      (weekly)
 *   cd pipeline && python run_pipeline.py                  (full refresh)
 * ─────────────────────────────────────────────────────────────────────────────
 */

// eslint-disable-next-line @typescript-eslint/no-require-imports
const _raw = require("../../pipeline/data/processed/refresh_log.json") as RefreshLogJson;

// ── Raw JSON types ────────────────────────────────────────────────────────────

interface SourceEntry {
  label:               string;
  last_success_at:     string | null;
  last_attempt_at:     string | null;
  status:              string;
  record_count:        number | null;
  error:               string | null;
  refresh_interval_h:  number;
}

interface RefreshLogJson {
  schema_version: number;
  updated_at:     string;
  sources: {
    gdelt:     SourceEntry;
    worldbank: SourceEntry;
    comtrade:  SourceEntry;
  };
  pipeline: {
    last_full_run_at:    string | null;
    last_process_run_at: string | null;
    last_news_run_at:    string | null;
    last_data_run_at:    string | null;
    alerts_generated:    number | null;
    alerts_critical:     number | null;
  };
}

// ── Public types ──────────────────────────────────────────────────────────────

export type DataSource = "gdelt" | "worldbank" | "comtrade";
export type FreshnessLevel = "fresh" | "aging" | "stale" | "unknown";

export interface SourceStatus {
  key:               DataSource;
  label:             string;
  lastSuccessAt:     string | null;   // ISO string
  lastAttemptAt:     string | null;
  status:            string;          // "success" | "failed" | "rate_limited" | "cached" | "never_run"
  recordCount:       number | null;
  refreshIntervalH:  number;          // expected refresh window in hours
  freshnessLevel:    FreshnessLevel;  // computed
  ageHours:          number | null;   // hours since last successful refresh
  isLive:            boolean;         // status is success or cached
}

export interface PipelineStatus {
  lastFullRunAt:    string | null;
  lastProcessRunAt: string | null;
  lastNewsRunAt:    string | null;
  lastDataRunAt:    string | null;
  alertsGenerated:  number | null;
  alertsCritical:   number | null;
}

// ── Freshness thresholds (must match pipeline/refresh_log.py) ────────────────

const FRESHNESS_H: Record<DataSource, { fresh: number; aging: number }> = {
  gdelt:     { fresh: 6,   aging: 12  },
  worldbank: { fresh: 168, aging: 336 },
  comtrade:  { fresh: 168, aging: 336 },
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function ageHours(isoTs: string | null): number | null {
  if (!isoTs) return null;
  try {
    const ms = Date.now() - new Date(isoTs).getTime();
    return ms / (1000 * 3600);
  } catch {
    return null;
  }
}

function computeFreshness(key: DataSource, lastSuccessAt: string | null): FreshnessLevel {
  const h = ageHours(lastSuccessAt);
  if (h === null) return "unknown";
  const t = FRESHNESS_H[key];
  if (h <= t.fresh) return "fresh";
  if (h <= t.aging) return "aging";
  return "stale";
}

function mapSource(key: DataSource, entry: SourceEntry): SourceStatus {
  return {
    key,
    label:            entry.label,
    lastSuccessAt:    entry.last_success_at,
    lastAttemptAt:    entry.last_attempt_at,
    status:           entry.status,
    recordCount:      entry.record_count,
    refreshIntervalH: entry.refresh_interval_h,
    freshnessLevel:   computeFreshness(key, entry.last_success_at),
    ageHours:         ageHours(entry.last_success_at),
    isLive:           entry.status === "success" || entry.status === "cached",
  };
}

// ── Exports ───────────────────────────────────────────────────────────────────

/** Status for the GDELT news feed. */
export const NEWS_STATUS:  SourceStatus = mapSource("gdelt",     _raw.sources.gdelt);

/** Status for the World Bank indicator data. */
export const DATA_STATUS:  SourceStatus = mapSource("worldbank", _raw.sources.worldbank);

/** Status for the UN Comtrade trade flow data. */
export const TRADE_STATUS: SourceStatus = mapSource("comtrade",  _raw.sources.comtrade);

/** All three sources as an array for easy iteration. */
export const ALL_SOURCES: SourceStatus[] = [NEWS_STATUS, DATA_STATUS, TRADE_STATUS];

/** Pipeline-level metadata. */
export const PIPELINE_STATUS: PipelineStatus = {
  lastFullRunAt:    _raw.pipeline.last_full_run_at,
  lastProcessRunAt: _raw.pipeline.last_process_run_at,
  lastNewsRunAt:    _raw.pipeline.last_news_run_at,
  lastDataRunAt:    _raw.pipeline.last_data_run_at,
  alertsGenerated:  _raw.pipeline.alerts_generated,
  alertsCritical:   _raw.pipeline.alerts_critical,
};

// ── Formatting helpers (used by DataFreshnessBar) ─────────────────────────────

/**
 * Format an age in hours as a concise human-readable string.
 * Examples: "23m ago", "4h ago", "3d ago"
 */
export function fmtAge(ageH: number | null): string {
  if (ageH === null) return "never";
  if (ageH < 1 / 60)  return "just now";
  if (ageH < 1)        return `${Math.round(ageH * 60)}m ago`;
  if (ageH < 24)       return `${Math.round(ageH)}h ago`;
  const days = Math.floor(ageH / 24);
  return `${days}d ago`;
}

/**
 * Tailwind colour classes for each freshness level.
 */
export const FRESHNESS_DOT: Record<FreshnessLevel, string> = {
  fresh:   "bg-emerald-400",
  aging:   "bg-amber-400",
  stale:   "bg-red-500",
  unknown: "bg-slate-500",
};

export const FRESHNESS_TEXT: Record<FreshnessLevel, string> = {
  fresh:   "text-emerald-400",
  aging:   "text-amber-400",
  stale:   "text-red-400",
  unknown: "text-slate-500",
};

export const FRESHNESS_LABEL: Record<FreshnessLevel, string> = {
  fresh:   "Fresh",
  aging:   "Aging",
  stale:   "Stale",
  unknown: "Unknown",
};

/** Whether the overall data is considered live (all sources fresh or aging). */
export const OVERALL_LIVE: boolean =
  ALL_SOURCES.every(s => s.freshnessLevel !== "stale" && s.freshnessLevel !== "unknown");
