"use client";

/**
 * frontend/components/cards/ExplanationPanel.tsx
 *
 * Renders the structured 6-section AI explanation returned by
 * POST /explain/pattern.
 *
 * SECTIONS DISPLAYED
 * ------------------
 *   1. What changed           — Bold numbers, fact-first
 *   2. Why it matters         — Economic significance
 *   3. Connected indicators   — Chips with value + relationship tooltip
 *   4. Affected countries     — Flag + impact badge per neighbour
 *   5. Confidence level       — Progress bar + rationale
 *   6. Limitations            — Checklist of caveats
 *
 * USAGE
 * -----
 *   <ExplanationPanel
 *     explanation={explanation}
 *     loading={loading}
 *     error={error}
 *   />
 */

import { cn } from "@/lib/utils";
import type {
  PatternExplanation,
  ConnectedIndicator,
  AffectedCountry,
  ConfidenceDetail,
} from "@/hooks/usePatternExplanation";

// ── Sub-component props ───────────────────────────────────────────────────────

interface Props {
  explanation: PatternExplanation | null;
  loading:     boolean;
  error:       string | null;
  onClose?:    () => void;
}

// ── Confidence colours ────────────────────────────────────────────────────────

const CONF_COLOR: Record<string, { bar: string; badge: string; text: string }> = {
  high:   { bar: "bg-emerald-500", badge: "bg-emerald-100 text-emerald-800", text: "text-emerald-700" },
  medium: { bar: "bg-amber-500",   badge: "bg-amber-100 text-amber-800",     text: "text-amber-700"   },
  low:    { bar: "bg-red-500",     badge: "bg-red-100 text-red-800",         text: "text-red-700"     },
};

const IMPACT_COLOR: Record<string, string> = {
  none:   "bg-slate-100 text-slate-600",
  low:    "bg-blue-100 text-blue-700",
  medium: "bg-amber-100 text-amber-700",
  high:   "bg-red-100 text-red-700",
};

const DIRECTION_ICON: Record<string, string> = {
  amplifying: "↑ Amplifying",
  dampening:  "↓ Dampening",
  unclear:    "? Unclear",
};

const DIRECTION_COLOR: Record<string, string> = {
  amplifying: "text-red-600 bg-red-50",
  dampening:  "text-emerald-600 bg-emerald-50",
  unclear:    "text-slate-500 bg-slate-100",
};

// ── Main component ────────────────────────────────────────────────────────────

export default function ExplanationPanel({ explanation, loading, error, onClose }: Props) {

  // Loading state
  if (loading) {
    return (
      <div className="card p-6 mt-3 border border-indigo-100 bg-indigo-50/30">
        <div className="flex items-center gap-3 mb-4">
          <span className="animate-spin text-indigo-500 text-lg">◌</span>
          <span className="text-sm font-medium text-indigo-700">
            Generating AI explanation…
          </span>
        </div>
        <div className="space-y-2">
          {[140, 100, 120, 80].map((w, i) => (
            <div key={i} className={`h-3 rounded bg-indigo-100 animate-pulse`}
              style={{ width: `${w}px` }} />
          ))}
        </div>
        <p className="text-xs text-indigo-400 mt-4">
          Using calibrated epistemic hedging · may take 5–10 seconds
        </p>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="card p-4 mt-3 border border-red-200 bg-red-50">
        <div className="flex items-start gap-2">
          <span className="text-red-500 mt-0.5">✗</span>
          <div>
            <p className="text-sm font-medium text-red-700">Could not load explanation</p>
            <p className="text-xs text-red-600 mt-1 leading-relaxed">{error}</p>
          </div>
        </div>
      </div>
    );
  }

  // Empty state
  if (!explanation) return null;

  const conf    = explanation.confidence;
  const confCfg = CONF_COLOR[conf.level] ?? CONF_COLOR.low;

  return (
    <div className="mt-3 border border-indigo-200 rounded-xl overflow-hidden shadow-sm">

      {/* ── Header bar ──────────────────────────────────────────────────── */}
      <div className="bg-gradient-to-r from-indigo-700 to-indigo-600 px-4 py-3
                      flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-white text-sm">✦</span>
          <span className="text-white text-sm font-semibold tracking-tight">
            AI Analysis
          </span>
          {explanation.is_ai ? (
            <span className="text-[10px] font-medium px-1.5 py-0.5 rounded
                             bg-white/20 text-white/90">
              {explanation.model_used}
            </span>
          ) : (
            <span className="text-[10px] font-medium px-1.5 py-0.5 rounded
                             bg-amber-400/30 text-amber-100">
              Demo Mode
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          <ConfidenceBadge conf={conf} cfg={confCfg} />
          {onClose && (
            <button
              onClick={onClose}
              className="text-white/60 hover:text-white text-sm ml-1"
            >
              ✕
            </button>
          )}
        </div>
      </div>

      {/* ── Summary sentence ────────────────────────────────────────────── */}
      {explanation.summary_sentence && (
        <div className="px-4 py-3 bg-indigo-50 border-b border-indigo-100">
          <p className="text-sm text-indigo-900 font-medium leading-relaxed">
            {explanation.summary_sentence}
          </p>
        </div>
      )}

      <div className="bg-white divide-y divide-slate-100">

        {/* ── Section 1: What changed ────────────────────────────────────── */}
        <Section icon="📊" title="What Changed">
          <p className="text-sm text-slate-700 leading-relaxed">
            {explanation.what_changed}
          </p>
        </Section>

        {/* ── Section 2: Why it matters ──────────────────────────────────── */}
        <Section icon="⚠️" title="Why It Matters">
          <p className="text-sm text-slate-700 leading-relaxed">
            {explanation.why_it_matters}
          </p>
        </Section>

        {/* ── Section 3: Connected indicators ───────────────────────────── */}
        {explanation.connected_indicators.length > 0 && (
          <Section icon="🔗" title="Connected Indicators">
            <div className="space-y-3">
              {explanation.connected_indicators.map((ind) => (
                <ConnectedIndicatorRow key={ind.key} ind={ind} />
              ))}
            </div>
          </Section>
        )}

        {/* ── Section 4: Affected countries ─────────────────────────────── */}
        {explanation.affected_countries.length > 0 && (
          <Section icon="🌏" title="Countries That May Be Affected">
            <div className="space-y-2.5">
              {explanation.affected_countries.map((c) => (
                <AffectedCountryRow key={c.country_id} country={c} />
              ))}
            </div>
          </Section>
        )}

        {/* ── Section 5: Confidence ─────────────────────────────────────── */}
        <Section icon="📐" title="Confidence Level">
          <ConfidenceSection conf={conf} cfg={confCfg} />
        </Section>

        {/* ── Section 6: Limitations ────────────────────────────────────── */}
        {explanation.limitations.length > 0 && (
          <Section icon="⚑" title="Limitations & Caveats">
            <ul className="space-y-1.5">
              {explanation.limitations.map((lim, i) => (
                <li key={i} className="flex items-start gap-2 text-xs text-slate-600">
                  <span className="text-amber-500 mt-0.5 shrink-0">◆</span>
                  <span className="leading-relaxed">{lim}</span>
                </li>
              ))}
            </ul>
          </Section>
        )}
      </div>

      {/* ── Footer: hedging note + metadata ──────────────────────────────── */}
      <div className="px-4 py-3 bg-slate-50 border-t border-slate-200">
        {explanation.hedging_note && (
          <p className="text-[11px] text-slate-500 italic leading-relaxed mb-2">
            {explanation.hedging_note}
          </p>
        )}
        <div className="flex items-center justify-between">
          <span className="text-[10px] text-slate-400">
            {explanation.is_ai
              ? `Generated by ${explanation.model_used}`
              : "Demo mode — set ANTHROPIC_API_KEY for live analysis"}
          </span>
          <span className="text-[10px] text-slate-400">
            {new Date(explanation.generated_at).toLocaleTimeString("en-GB", {
              hour: "2-digit", minute: "2-digit"
            })}
          </span>
        </div>
      </div>
    </div>
  );
}


// ── Section wrapper ───────────────────────────────────────────────────────────

function Section({
  icon, title, children,
}: {
  icon: string; title: string; children: React.ReactNode;
}) {
  return (
    <div className="px-4 py-4">
      <h4 className="flex items-center gap-1.5 text-xs font-semibold uppercase
                     tracking-widest text-slate-500 mb-2.5">
        <span>{icon}</span>
        <span>{title}</span>
      </h4>
      {children}
    </div>
  );
}


// ── Connected indicator row ───────────────────────────────────────────────────

function ConnectedIndicatorRow({ ind }: { ind: ConnectedIndicator }) {
  return (
    <div className="flex items-start gap-3">
      <div className="shrink-0 mt-0.5">
        <span className={cn(
          "inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold",
          DIRECTION_COLOR[ind.direction] ?? "text-slate-500 bg-slate-100",
        )}>
          {DIRECTION_ICON[ind.direction] ?? ind.direction}
        </span>
      </div>
      <div className="min-w-0">
        <div className="flex items-baseline gap-1.5">
          <span className="text-xs font-semibold text-slate-800">{ind.label}</span>
          <span className="text-xs text-slate-500">
            {ind.value} {ind.unit}
          </span>
        </div>
        <p className="text-xs text-slate-500 leading-relaxed mt-0.5">
          {ind.relationship}
        </p>
      </div>
    </div>
  );
}


// ── Affected country row ──────────────────────────────────────────────────────

function AffectedCountryRow({ country }: { country: AffectedCountry }) {
  return (
    <div className="flex items-start gap-3 p-2.5 rounded-lg bg-slate-50">
      <span className="text-xl shrink-0">{country.flag || "🌏"}</span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 mb-0.5">
          <span className="text-xs font-semibold text-slate-800">{country.country_name}</span>
          <span className={cn(
            "text-[10px] font-bold px-1.5 py-0.5 rounded",
            IMPACT_COLOR[country.possible_impact] ?? "bg-slate-100 text-slate-600",
          )}>
            {country.possible_impact.toUpperCase()} IMPACT
          </span>
          <span className="text-[10px] text-slate-400 ml-auto">
            conf: {country.confidence}
          </span>
        </div>
        <p className="text-xs text-slate-500 leading-relaxed">{country.mechanism}</p>
        {country.indicators_at_risk.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-1.5">
            <span className="text-[10px] text-slate-400 self-center">At risk:</span>
            {country.indicators_at_risk.map(ind => (
              <span key={ind}
                className="text-[10px] px-1.5 py-0.5 bg-slate-200 text-slate-600 rounded font-medium">
                {ind}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}


// ── Confidence badge (header) ─────────────────────────────────────────────────

function ConfidenceBadge({
  conf, cfg,
}: {
  conf: ConfidenceDetail;
  cfg: { badge: string; text: string };
}) {
  return (
    <span className={cn(
      "flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded",
      cfg.badge,
    )}>
      <span>{conf.level === "high" ? "●" : conf.level === "medium" ? "◐" : "○"}</span>
      {conf.label}
    </span>
  );
}


// ── Confidence section ────────────────────────────────────────────────────────

function ConfidenceSection({
  conf, cfg,
}: {
  conf: ConfidenceDetail;
  cfg: { bar: string; badge: string; text: string };
}) {
  return (
    <div className="space-y-2.5">
      {/* Progress bar */}
      <div>
        <div className="flex items-center justify-between mb-1">
          <span className={cn("text-xs font-semibold", cfg.text)}>
            {conf.label}
          </span>
          <span className="text-xs text-slate-500">
            {conf.score}/100 · Data: {conf.data_quality}
          </span>
        </div>
        <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
          <div
            className={cn("h-full rounded-full transition-all", cfg.bar)}
            style={{ width: `${conf.score}%` }}
          />
        </div>
      </div>

      {/* Rationale */}
      <p className="text-xs text-slate-600 leading-relaxed">{conf.rationale}</p>

      {/* Factor bullets */}
      {conf.factors.length > 0 && (
        <ul className="space-y-1">
          {conf.factors.map((f, i) => (
            <li key={i} className="flex items-start gap-1.5 text-xs text-slate-500">
              <span className="shrink-0 text-slate-400 mt-0.5">·</span>
              <span>{f}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
