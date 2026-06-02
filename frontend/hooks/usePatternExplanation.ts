/**
 * frontend/hooks/usePatternExplanation.ts
 *
 * React hook for fetching structured AI explanations from the backend
 * POST /explain/pattern endpoint.
 *
 * USAGE
 * -----
 *   import { usePatternExplanation } from "@/hooks/usePatternExplanation";
 *
 *   const { explanation, loading, error, fetch: getExplanation } = usePatternExplanation();
 *
 *   // Trigger the request
 *   getExplanation(buildRequest(alertResult, currentIndicators));
 *
 * The hook caches the last response so clicking "Explain" twice
 * for the same alert doesn't make a second API call.
 *
 * BACKEND REQUIRED
 * ----------------
 *   cd backend && uvicorn server:app --reload --port 8000
 *
 * If the backend is unreachable, the hook returns an error message.
 * The Alert card should still display the static alert — explanation
 * is an enhancement, not a dependency.
 */

"use client";

import { useState, useCallback, useRef } from "react";
import type { AlertResult } from "@/lib/pattern-engine";
import type { CurrentIndicators } from "@/data/sample-data";

// ── Types matching the backend /explain/pattern response ──────────────────────

export interface ConnectedIndicator {
  key:          string;
  label:        string;
  value:        number;
  unit:         string;
  relationship: string;
  direction:    "amplifying" | "dampening" | "unclear";
}

export interface AffectedCountry {
  country_id:         string;
  country_name:       string;
  flag:               string;
  mechanism:          string;
  possible_impact:    "none" | "low" | "medium" | "high";
  indicators_at_risk: string[];
  confidence:         "low" | "medium" | "high";
}

export interface ConfidenceDetail {
  level:        "low" | "medium" | "high";
  label:        string;
  score:        number;       // 0–100
  rationale:    string;
  data_quality: "poor" | "fair" | "good" | "unknown";
  factors:      string[];
}

export interface PatternExplanation {
  // Identity
  alert_type:   string;
  country_id:   string;
  country_name: string;
  severity:     string;
  quarter:      string;

  // 6 sections
  what_changed:          string;    // Section 1
  why_it_matters:        string;    // Section 2
  connected_indicators:  ConnectedIndicator[];  // Section 3
  affected_countries:    AffectedCountry[];     // Section 4
  confidence:            ConfidenceDetail;      // Section 5
  limitations:           string[];              // Section 6

  // UI helpers
  summary_sentence: string;
  hedging_note:     string;

  // Metadata
  is_ai:        boolean;
  model_used:   string;
  generated_at: string;
}

// ── Request builder ───────────────────────────────────────────────────────────

const INDICATOR_META: Record<string, { unit: string; label: string }> = {
  gdpGrowth:         { unit: "% YoY",       label: "GDP Growth" },
  inflation:         { unit: "% YoY",       label: "Inflation (CPI)" },
  exports:           { unit: "USD Billion", label: "Exports" },
  imports:           { unit: "USD Billion", label: "Imports" },
  exchangeRate:      { unit: "per USD",     label: "Exchange Rate" },
  fdi:               { unit: "USD Billion", label: "FDI Net Inflows" },
  politicalRiskNews: { unit: "articles",    label: "Political Risk News" },
  tradeNewsCount:    { unit: "articles",    label: "Trade News Count" },
};

const NEIGHBOR_MAP: Record<string, string[]> = {
  THA: ["VNM", "MMR", "KHM", "SGP"],
  VNM: ["THA", "MMR", "KHM", "SGP"],
  MMR: ["THA", "VNM", "KHM", "SGP"],
  KHM: ["THA", "VNM", "MMR", "SGP"],
  SGP: ["THA", "VNM", "MMR", "KHM"],
};

const DATA_NOTES: Record<string, string> = {
  MMR: "Post-2021 coup data is from IMF estimates and secondary sources. Official statistics are unreliable.",
  KHM: "Standard World Bank / IMF data sources. Minor gaps in trade data.",
  SGP: "High-quality data from SingStat and MAS. Good coverage.",
  THA: "Standard World Bank / NESDC data. Good coverage.",
  VNM: "Standard World Bank / GSO data. Good coverage.",
};

/**
 * Build the request body for POST /explain/pattern
 * from a pattern engine AlertResult and the current indicator set.
 */
export function buildExplainRequest(
  alert:       AlertResult,
  indicators:  CurrentIndicators,
  recentNews?: Array<{ headline: string; category: string; sentiment: string; impactLevel: number; impactedIndicators: string[] }>,
): object {
  const indicatorsObj: Record<string, object> = {};
  for (const [key, meta] of Object.entries(INDICATOR_META)) {
    const val = (indicators as unknown as Record<string, number>)[key];
    if (val !== undefined) {
      indicatorsObj[key] = { value: val, ...meta };
    }
  }

  const news = (recentNews ?? []).slice(0, 5).map((n, i) => ({
    headline:             n.headline,
    category:             n.category,
    sentiment:            n.sentiment,
    impact_score:         n.impactLevel,
    days_ago:             i * 2,    // approximate
    connected_indicators: n.impactedIndicators,
  }));

  return {
    alert: {
      type:            alert.alertType,
      label:           alert.alertLabel,
      country_id:      alert.countryId,
      country_name:    alert.countryName,
      flag:            alert.flagEmoji,
      quarter:         alert.quarter,
      severity:        alert.severity,
      trigger_value:   alert.triggerValue,
      threshold_value: alert.thresholdValue,
      unit:            alert.unit,
      score:           alert.score,
      condition_met:   alert.conditionMet,
    },
    indicators: indicatorsObj,
    other_active_alerts: [],
    recent_news: news,
    context: {
      region:    "Southeast Asia",
      neighbors: NEIGHBOR_MAP[alert.countryId] ?? [],
      trade_links: {
        top_export_partners: [],
        top_import_partners: [],
      },
      data_source_notes: DATA_NOTES[alert.countryId] ?? "Standard World Bank / IMF data sources.",
    },
  };
}


// ── Cache key ─────────────────────────────────────────────────────────────────
function cacheKey(countryId: string, alertType: string, quarter: string): string {
  return `${countryId}::${alertType}::${quarter}`;
}


// ── The hook ──────────────────────────────────────────────────────────────────

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

interface UsePatternExplanationReturn {
  explanation:  PatternExplanation | null;
  loading:      boolean;
  error:        string | null;
  /** Fetch an explanation. Pass the result of buildExplainRequest(). */
  fetch:        (requestBody: object) => Promise<void>;
  /** Clear the current explanation */
  clear:        () => void;
}

export function usePatternExplanation(): UsePatternExplanationReturn {
  const [explanation, setExplanation] = useState<PatternExplanation | null>(null);
  const [loading,     setLoading]     = useState(false);
  const [error,       setError]       = useState<string | null>(null);

  // In-memory cache (lasts for the page session)
  const cache = useRef<Map<string, PatternExplanation>>(new Map());

  const fetchExplanation = useCallback(async (requestBody: object) => {
    // Derive cache key from the request
    const body = requestBody as Record<string, any>;
    const alert = body?.alert ?? {};
    const key   = cacheKey(alert.country_id ?? "", alert.type ?? "", alert.quarter ?? "");

    // Return cached result if available
    if (cache.current.has(key)) {
      setExplanation(cache.current.get(key)!);
      setError(null);
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const response = await fetch(`${BACKEND_URL}/explain/pattern`, {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify(requestBody),
        // 30s timeout — AI calls can be slow
        signal:  AbortSignal.timeout(30_000),
      });

      if (!response.ok) {
        const text = await response.text().catch(() => response.statusText);
        throw new Error(`Backend returned ${response.status}: ${text.slice(0, 200)}`);
      }

      const data: PatternExplanation = await response.json();
      cache.current.set(key, data);
      setExplanation(data);

    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);

      if (msg.includes("Failed to fetch") || msg.includes("NetworkError")) {
        setError(
          "Backend not reachable. Start it with: cd backend && uvicorn server:app --reload --port 8000"
        );
      } else if (msg.includes("AbortError") || msg.includes("timeout")) {
        setError("Request timed out after 30s. The AI may be slow — try again.");
      } else {
        setError(`Explanation failed: ${msg}`);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  const clear = useCallback(() => {
    setExplanation(null);
    setError(null);
  }, []);

  return { explanation, loading, error, fetch: fetchExplanation, clear };
}
