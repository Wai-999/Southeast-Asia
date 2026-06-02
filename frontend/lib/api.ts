/**
 * api.ts — Backend API client
 *
 * All requests go through the Next.js proxy at /api/* → http://localhost:8000/*
 * (configured in next.config.mjs). No CORS issues, works in dev and prod.
 *
 * Pages that need real-time data should call these functions.
 * Pages that only need static sample data can continue using /data/sample-data.ts directly.
 */

const BASE = "/api";

// ── Generic fetcher ────────────────────────────────────────────────────────

async function get<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(`${BASE}${path}`, { cache: "no-store" });
    if (!res.ok) return null;
    return res.json() as Promise<T>;
  } catch {
    return null;
  }
}

// ── Health ─────────────────────────────────────────────────────────────────

export async function checkHealth(): Promise<{
  status: string;
  ai_enabled: boolean;
} | null> {
  return get("/health");
}

// ── Countries ──────────────────────────────────────────────────────────────

export async function getCountries() {
  return get<{ id: string; name: string; flagEmoji: string; riskLevel: string }[]>("/countries");
}

export async function getCountry(iso3: string) {
  return get<{ id: string; name: string; indicators: Record<string, number> }>(
    `/countries/${iso3.toUpperCase()}`
  );
}

// ── News ───────────────────────────────────────────────────────────────────

export async function getNews(params?: {
  country?: string;
  category?: string;
  sentiment?: string;
  limit?: number;
}) {
  const qs = new URLSearchParams();
  if (params?.country)   qs.set("country",   params.country);
  if (params?.category)  qs.set("category",  params.category);
  if (params?.sentiment) qs.set("sentiment", params.sentiment);
  if (params?.limit)     qs.set("limit",     String(params.limit));
  const query = qs.toString() ? `?${qs}` : "";
  return get<unknown[]>(`/news${query}`);
}

// ── Alerts ─────────────────────────────────────────────────────────────────

export async function getAlerts(params?: {
  country?: string;
  severity?: string;
  active_only?: boolean;
}) {
  const qs = new URLSearchParams();
  if (params?.country)               qs.set("country",     params.country);
  if (params?.severity)              qs.set("severity",    params.severity);
  if (params?.active_only === false) qs.set("active_only", "false");
  const query = qs.toString() ? `?${qs}` : "";
  return get<unknown[]>(`/alerts${query}`);
}

// ── AI Explanation ─────────────────────────────────────────────────────────

export interface AlertExplainPayload {
  country_iso3:   string;
  country_name:   string;
  alert_label:    string;
  indicator_code: string;
  severity:       string;
  trigger_value:  number;
  threshold:      number;
  unit:           string;
  message:        string;
  period?:        string;
}

export interface AlertExplanation {
  country_iso3: string;
  country_name: string;
  alert_label:  string;
  severity:     string;
  explanation:  string;
  is_ai:        boolean;
  model_used:   string;
  generated_at: string;
}

export async function getAlertExplanation(
  payload: AlertExplainPayload
): Promise<AlertExplanation | null> {
  try {
    const res = await fetch(`${BASE}/explain/alert`, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify(payload),
    });
    if (!res.ok) return null;
    return res.json() as Promise<AlertExplanation>;
  } catch {
    return null;
  }
}
