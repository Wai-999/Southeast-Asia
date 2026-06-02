/**
 * frontend/lib/source-meta.ts
 * ─────────────────────────────────────────────────────────────────────────────
 * Shared SourceMeta type used across all data objects and UI components.
 *
 * Every indicator, news item, trade flow, and alert exposes a SourceMeta
 * record so the dashboard can render a "Source Details" panel anywhere.
 *
 * Fields
 * ──────
 *   source          Human-readable source name
 *   source_url      Canonical link to the data page / API docs
 *   fetched_at      ISO timestamp of when this record was last fetched
 *   frequency       How often the source publishes new data
 *   confidence      Reliability of this specific data point
 *   data_quality    Publication status of the underlying data
 *   limitation_note One-sentence caveat the analyst should know
 * ─────────────────────────────────────────────────────────────────────────────
 */

// ── Core types ────────────────────────────────────────────────────────────────

export type SourceConfidence = "high" | "medium" | "low";
export type SourceFrequency  = "realtime" | "daily" | "weekly" | "monthly" | "quarterly" | "annual";
export type SourceDataQuality =
  | "official"      // from national statistics bureau or central bank
  | "preliminary"   // released before final revision
  | "estimated"     // derived / modelled (not measured)
  | "sample";       // subset of full population (e.g. GDELT media sample)

export interface SourceMeta {
  /** Human-readable data provider name, e.g. "World Bank Open Data" */
  source:           string;
  /** Canonical URL to the data series, API docs, or methodology page */
  source_url:       string;
  /** ISO timestamp of when the pipeline last fetched this record */
  fetched_at:       string;
  /** How frequently the source publishes new data */
  frequency:        SourceFrequency;
  /** Overall reliability: high = official measured, medium = modelled/verified, low = automated/proxy */
  confidence:       SourceConfidence;
  /** Publication status of the underlying data point */
  data_quality:     SourceDataQuality;
  /** One-sentence caveat the analyst should know about this data point */
  limitation_note:  string;
}

// ── Display helpers ───────────────────────────────────────────────────────────

/** Tailwind colour for a confidence level (dot) */
export const CONF_DOT: Record<SourceConfidence, string> = {
  high:   "bg-emerald-500",
  medium: "bg-amber-400",
  low:    "bg-slate-400",
};

/** Tailwind text colour for a confidence level */
export const CONF_TEXT: Record<SourceConfidence, string> = {
  high:   "text-emerald-600",
  medium: "text-amber-600",
  low:    "text-slate-500",
};

/** Full label for each confidence level */
export const CONF_LABEL: Record<SourceConfidence, string> = {
  high:   "High confidence",
  medium: "Medium confidence",
  low:    "Low confidence",
};

/** Short description of what each confidence level means in this context */
export const CONF_DESC: Record<SourceConfidence, string> = {
  high:   "Data measured and published by an official statistical agency.",
  medium: "Data verified against official sources but may be modelled or curated.",
  low:    "Automated or proxy data — treat as signal, not measurement.",
};

/** Tailwind badge style for data quality */
export const QUALITY_STYLE: Record<SourceDataQuality, { bg: string; text: string; label: string }> = {
  official:    { bg: "bg-emerald-50", text: "text-emerald-700", label: "Official"    },
  preliminary: { bg: "bg-amber-50",   text: "text-amber-700",   label: "Preliminary" },
  estimated:   { bg: "bg-slate-100",  text: "text-slate-600",   label: "Estimated"   },
  sample:      { bg: "bg-violet-50",  text: "text-violet-700",  label: "Sample"      },
};

/** Short label for frequency */
export const FREQ_LABEL: Record<SourceFrequency, string> = {
  realtime:  "Real-time",
  daily:     "Daily",
  weekly:    "Weekly",
  monthly:   "Monthly",
  quarterly: "Quarterly",
  annual:    "Annual",
};

// ── Per-source base metadata ──────────────────────────────────────────────────
// These are the canonical source definitions; fetched_at is filled in at
// runtime by the data adapters from their respective JSON meta fields.

/**
 * World Bank Open Data — used for all WB indicator records.
 * Override `confidence` for "estimated" or "old_data" quality records.
 */
export const WB_SOURCE_BASE: Omit<SourceMeta, "fetched_at"> = {
  source:          "World Bank Open Data",
  source_url:      "https://data.worldbank.org",
  frequency:       "annual",
  confidence:      "high",
  data_quality:    "official",
  limitation_note:
    "Annual data with a 1–2 year publication lag. Not suitable for " +
    "tracking short-term changes. Estimated values (⚠) have wider uncertainty.",
};

/**
 * GDELT 2.0 Document API — used for all news signal records.
 */
export const GDELT_SOURCE_BASE: Omit<SourceMeta, "fetched_at"> = {
  source:          "GDELT 2.0 Document API",
  source_url:      "https://blog.gdeltproject.org/gdelt-2-0-our-global-world-in-realtime/",
  frequency:       "realtime",
  confidence:      "medium",
  data_quality:    "sample",
  limitation_note:
    "Automated English-language media monitoring. Article counts reflect " +
    "media attention, not ground-truth event frequency. Sentiment scores " +
    "are keyword estimates, not verified analysis.",
};

/**
 * UN Comtrade / WTO Statistics — used for all trade flow records.
 */
export const COMTRADE_SOURCE_BASE: Omit<SourceMeta, "fetched_at"> = {
  source:          "UN Comtrade / WTO Statistics",
  source_url:      "https://comtrade.un.org",
  frequency:       "annual",
  confidence:      "medium",
  data_quality:    "official",
  limitation_note:
    "Annual goods trade only (services excluded). Free-tier data uses " +
    "curated 2021–2023 values; quarterly data requires paid API. " +
    "Myanmar and Brunei figures are IMF/WB proxy estimates.",
};

/**
 * SEA Pattern Alert Engine — used for all generated alerts.
 */
export const ALERT_SOURCE_BASE: Omit<SourceMeta, "fetched_at"> = {
  source:          "SEA Pattern Alert Engine",
  source_url:      "https://github.com/Wai-999/Southeast-Asia",
  frequency:       "weekly",
  confidence:      "medium",    // overridden per alert from its confidence field
  data_quality:    "estimated",
  limitation_note:
    "Rule-based composite score derived from World Bank + GDELT + Comtrade. " +
    "Confidence reflects how many of the 3 input sources agree. " +
    "High-confidence alerts are corroborated by all 3 sources.",
};

// ── Helper: format fetched_at for display ─────────────────────────────────────

/**
 * Format a fetched_at ISO timestamp as a readable string.
 * e.g. "2026-06-02T14:56:32" → "Jun 2, 2026 2:56 PM"
 */
export function fmtFetchedAt(iso: string | null | undefined): string {
  if (!iso) return "unknown";
  try {
    return new Date(iso).toLocaleString("en-US", {
      month: "short", day: "numeric", year: "numeric",
      hour: "numeric", minute: "2-digit",
    });
  } catch {
    return iso ?? "unknown";
  }
}
