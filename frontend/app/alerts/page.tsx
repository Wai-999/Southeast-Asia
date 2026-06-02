"use client";

/**
 * app/alerts/page.tsx — Pattern Alert Centre
 *
 * All rule-based threshold alerts with filters.
 * Shows: summary stats · alert rules reference · filterable alert list
 */

import { useState, useMemo } from "react";
import Link from "next/link";
import AlertCard from "@/components/cards/AlertCard";
import { PATTERN_ALERTS, type PatternAlert } from "@/data/sample-data";
import CountryFilter, { type FilterMode } from "@/components/ui/CountryFilter";
import { getIso3ForMode, ALL_COUNTRIES } from "@/data/countries";
import type { Severity } from "@/lib/utils";
import { cn } from "@/lib/utils";
import {
  NS_DATA_STATUS, NS_NEWS_COUNTS, POLITICAL_RISK_COUNTS, TRADE_NEWS_COUNTS,
  CRITICAL_SIGNALS, NS_META, getHighRiskCountries, getHighTradeCountries,
  NS_CATEGORY_META, fmtNsGeneratedAt,
} from "@/data/news-signals";
import {
  ENRICHED_ALERTS, getAlertSourceMeta, PATTERN_ALERTS_META,
  type EnrichedAlert,
} from "@/data/pattern-alerts";

// ── Alert rule definitions (for the reference panel) ─────────────
const ALERT_RULES = [
  { name: "GDP Contraction",       trigger: "GDP Growth < 0%",              sev: "critical" as Severity, indicator: "gdpGrowth"         },
  { name: "Hyperinflation",        trigger: "Inflation > 10%",              sev: "critical" as Severity, indicator: "inflation"          },
  { name: "Political Crisis",      trigger: "Risk News > 100 articles/mo",  sev: "critical" as Severity, indicator: "politicalRiskNews"  },
  { name: "Inflation Pressure",    trigger: "Inflation 5–10%",              sev: "warning"  as Severity, indicator: "inflation"          },
  { name: "Investment Collapse",   trigger: "FDI < $2B",                    sev: "warning"  as Severity, indicator: "fdi"                },
  { name: "Trade Deficit Stress",  trigger: "Trade Deficit > $2B",          sev: "warning"  as Severity, indicator: "imports"            },
  { name: "Political Risk Watch",  trigger: "Risk News 40–100 articles/mo", sev: "info"     as Severity, indicator: "politicalRiskNews"  },
  { name: "Growth Below Trend",    trigger: "GDP Growth 0–2%",              sev: "info"     as Severity, indicator: "gdpGrowth"          },
];

export default function AlertsPage() {
  const [filterMode,    setFilterMode]   = useState<FilterMode>("sea");
  const [customIds,     setCustomIds]    = useState<string[]>([]);
  const [severity,      setSeverity]     = useState<Severity | "all">("all");
  const [showResolved,  setShowResolved] = useState(false);

  // Derive the set of ISO3 codes currently active in the filter
  const activeCountryIds = getIso3ForMode(filterMode, customIds);

  // Use real enriched alerts where available; fall back to sample for countries not in real data
  const liveAlerts    = ENRICHED_ALERTS;
  const activeAlerts  = liveAlerts.filter(a => a.isActive);
  const resolvedAlerts = liveAlerts.filter(a => !a.isActive);
  const criticalCount = activeAlerts.filter(a => a.severity === "critical").length;
  const warningCount  = activeAlerts.filter(a => a.severity === "warning").length;
  const infoCount     = activeAlerts.filter(a => a.severity === "info").length;

  const filtered = useMemo<EnrichedAlert[]>(() => {
    let list = showResolved ? liveAlerts : activeAlerts;
    list = list.filter(a => activeCountryIds.has(a.countryId));
    if (severity !== "all") list = list.filter(a => a.severity === severity);
    return [...list].sort((a, b) => {
      const order = { critical: 0, warning: 1, info: 2 };
      if (order[a.severity] !== order[b.severity])
        return order[a.severity] - order[b.severity];
      return b.triggeredAt.localeCompare(a.triggeredAt);
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeCountryIds, severity, showResolved]);

  return (
    <div className="p-7 max-w-7xl mx-auto">

      {/* ── Header ────────────────────────────────────────────── */}
      <div className="flex items-start justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
            Pattern Alert Centre
          </h1>
          <p className="text-slate-500 text-sm mt-0.5">
            Rule-based threshold alerts across all 8 economic indicators
          </p>
        </div>
        <Link href="/compare"
          className="text-xs text-indigo-600 hover:underline font-medium self-start mt-1">
          View full indicator comparison →
        </Link>
      </div>

      {/* ── Summary stat cards ────────────────────────────────── */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        <div
          className="card-p border-t-4 border-t-slate-400 cursor-pointer hover:shadow-md transition-shadow"
          onClick={() => setSeverity("all")}>
          <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500 mb-2">
            Total Active
          </p>
          <p className="text-3xl font-bold text-slate-900 tabular-nums">{activeAlerts.length}</p>
          <p className="text-xs text-slate-400 mt-1">
            across {new Set(activeAlerts.map(a => a.countryId)).size} countries
          </p>
        </div>
        <div
          className="card-p border-t-4 border-t-red-500 cursor-pointer hover:shadow-md transition-shadow"
          onClick={() => setSeverity(severity === "critical" ? "all" : "critical")}>
          <p className="text-[10px] font-semibold uppercase tracking-wide text-red-600 mb-2">
            Critical
          </p>
          <p className="text-3xl font-bold text-red-600 tabular-nums">{criticalCount}</p>
          <p className="text-xs text-slate-400 mt-1">require immediate attention</p>
        </div>
        <div
          className="card-p border-t-4 border-t-amber-500 cursor-pointer hover:shadow-md transition-shadow"
          onClick={() => setSeverity(severity === "warning" ? "all" : "warning")}>
          <p className="text-[10px] font-semibold uppercase tracking-wide text-amber-600 mb-2">
            Warnings
          </p>
          <p className="text-3xl font-bold text-amber-600 tabular-nums">{warningCount}</p>
          <p className="text-xs text-slate-400 mt-1">elevated risk indicators</p>
        </div>
        <div
          className="card-p border-t-4 border-t-sky-400 cursor-pointer hover:shadow-md transition-shadow"
          onClick={() => setSeverity(severity === "info" ? "all" : "info")}>
          <p className="text-[10px] font-semibold uppercase tracking-wide text-sky-600 mb-2">
            Info / Watch
          </p>
          <p className="text-3xl font-bold text-sky-600 tabular-nums">{infoCount}</p>
          <p className="text-xs text-slate-400 mt-1">monitoring threshold breaches</p>
        </div>
      </div>

      {/* ── Alert rules reference ─────────────────────────────── */}
      <div className="card-p mb-6 bg-slate-50/70">
        <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-400 mb-3">
          Pattern Detection Rules ({ALERT_RULES.length} active rules)
        </p>
        <div className="grid grid-cols-4 gap-2.5">
          {ALERT_RULES.map(r => (
            <div key={r.name}
              className="flex items-start gap-2.5 p-2.5 bg-white rounded-lg border border-slate-200">
              <span className={cn("w-2 h-2 rounded-full flex-shrink-0 mt-1", {
                critical: "bg-red-500",
                warning:  "bg-amber-500",
                info:     "bg-sky-500",
              }[r.sev])} />
              <div>
                <p className="text-xs font-semibold text-slate-800">{r.name}</p>
                <p className="text-[10px] text-slate-500 mt-0.5">{r.trigger}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ── Filters ──────────────────────────────────────────── */}
      <div className="card-p mb-6 flex flex-wrap items-start gap-5">

        {/* Country filter */}
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-400 mb-1.5">
            Countries
          </p>
          <CountryFilter
            mode={filterMode}
            onModeChange={setFilterMode}
            customSelection={customIds}
            onCustomChange={setCustomIds}
            compact
          />
        </div>

        {/* Severity */}
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-400 mb-1.5">
            Severity
          </p>
          <div className="flex gap-1.5">
            {(["all", "critical", "warning", "info"] as const).map(s => (
              <button key={s} onClick={() => setSeverity(s)}
                className={cn(
                  "text-xs px-3 py-1.5 rounded-lg border transition-colors capitalize",
                  severity === s
                    ? "bg-slate-800 text-white border-slate-800"
                    : "border-slate-200 text-slate-600 bg-white hover:bg-slate-50",
                )}>
                {s === "all" ? "All" : s}
              </button>
            ))}
          </div>
        </div>

        {/* Show resolved toggle */}
        <div className="ml-auto flex items-center gap-2">
          <input
            id="resolved"
            type="checkbox"
            checked={showResolved}
            onChange={e => setShowResolved(e.target.checked)}
            className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-300"
          />
          <label htmlFor="resolved" className="text-xs text-slate-600 cursor-pointer select-none">
            Include resolved alerts
            <span className="text-slate-400 ml-1">({resolvedAlerts.length})</span>
          </label>
        </div>
      </div>

      {/* ── GDELT Live News Signal Panel ─────────────────────── */}
      <GdeltSignalPanel activeCountryIds={activeCountryIds} />

      {/* ── Results count + confidence summary ───────────────── */}
      <div className="flex items-center justify-between mb-4">
        <p className="text-xs text-slate-400">
          {filtered.length} alert{filtered.length !== 1 ? "s" : ""} ·
          sorted critical → warning → info → score
        </p>
        <p className="text-[10px] text-slate-400">
          <span className="text-emerald-600 font-medium">{PATTERN_ALERTS_META.highConfidence}</span> high ·
          <span className="text-amber-600 font-medium ml-1">{PATTERN_ALERTS_META.mediumConfidence}</span> medium ·
          <span className="ml-1">{PATTERN_ALERTS_META.lowConfidence}</span> low confidence
        </p>
      </div>

      {/* ── Alert list ───────────────────────────────────────── */}
      {filtered.length > 0 ? (
        <div className="grid grid-cols-2 gap-4">
          {filtered.map(a => (
            <AlertCard
              key={a.id}
              alert={a}
              source={getAlertSourceMeta(a)}
              conditions={a.conditionsMet}
              confidence={a.confidence}
              sourcesCount={a.sourceSignals.sourcesCount}
            />
          ))}
        </div>
      ) : (
        <div className="card-p text-center py-24">
          <p className="text-4xl mb-3">✓</p>
          <p className="text-slate-600 font-medium">No alerts match your current filters</p>
          <p className="text-sm text-slate-400 mt-1">
            {showResolved
              ? "Try clearing country or severity filters"
              : "Toggle 'Include resolved' to see historical alerts"}
          </p>
          <button
            onClick={() => { setFilterMode("sea"); setCustomIds([]); setSeverity("all"); }}
            className="mt-4 text-xs text-indigo-600 hover:underline font-medium">
            Reset filters
          </button>
        </div>
      )}
    </div>
  );
}


// ══════════════════════════════════════════════════════════════════════════════
//  GDELT LIVE NEWS SIGNAL PANEL
//  Shows real article counts from fetch_gdelt_news.py and highlights countries
//  that are breaching the political-risk or trade-news thresholds.
// ══════════════════════════════════════════════════════════════════════════════

const POL_RISK_CRITICAL  = 15;  // articles/week → critical threshold
const POL_RISK_WARNING   = 7;   // articles/week → warning threshold
const TRADE_NEWS_WARNING = 5;   // articles/week → elevated threshold

function GdeltSignalPanel({ activeCountryIds }: { activeCountryIds: Set<string> }) {
  const isLive       = NS_DATA_STATUS === "live";
  const generatedAt  = fmtNsGeneratedAt();

  // Countries visible in the current filter
  const visibleCountries = ALL_COUNTRIES.filter(c => activeCountryIds.has(c.iso3));

  // High-risk countries (filtered to visible)
  const highRisk  = getHighRiskCountries(POL_RISK_WARNING).filter(iso3 => activeCountryIds.has(iso3));
  const highTrade = getHighTradeCountries(TRADE_NEWS_WARNING).filter(iso3 => activeCountryIds.has(iso3));

  // Critical signals visible in current filter
  const criticalVisible = CRITICAL_SIGNALS.filter(a => activeCountryIds.has(a.country_code));

  if (!isLive) {
    return (
      <div className="card-p mb-6 bg-amber-50 border border-amber-200">
        <div className="flex items-center gap-3">
          <span className="text-xl">📡</span>
          <div>
            <p className="text-sm font-semibold text-amber-800">
              GDELT live news signals not yet loaded
            </p>
            <p className="text-xs text-amber-600 mt-0.5">
              Run{" "}
              <code className="bg-white/60 px-1.5 py-0.5 rounded font-mono text-amber-700">
                cd pipeline && python fetch_gdelt_news.py
              </code>
              {" "}to populate real-time political risk and trade news counts.
              The panel below will show live article counts per country.
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="card overflow-hidden mb-6">
      {/* Panel header */}
      <div className="px-5 py-3.5 border-b border-slate-100 bg-emerald-50/60 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse shrink-0" />
          <h3 className="font-semibold text-slate-900 text-sm">
            GDELT Live News Signals
          </h3>
          <span className="text-xs text-slate-400">
            Last {NS_META.days_back} days
            {NS_META.unique_articles > 0 && ` · ${NS_META.unique_articles} articles`}
            {generatedAt && ` · fetched ${generatedAt}`}
          </span>
        </div>
        <a
          href="/news"
          className="text-xs text-indigo-600 hover:underline font-medium"
        >
          View full feed →
        </a>
      </div>

      <div className="p-5 space-y-5">

        {/* ── Critical signals ─────────────────────────────────────────── */}
        {criticalVisible.length > 0 && (
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-widest text-red-600 mb-2">
              ⚠ Critical Signals (Impact 4–5) — {criticalVisible.length} articles
            </p>
            <div className="space-y-1.5 max-h-36 overflow-y-auto">
              {criticalVisible.slice(0, 6).map(sig => {
                const catMeta = NS_CATEGORY_META[sig.category] ?? { icon: "◈", label: sig.category, color: "bg-slate-100 text-slate-600" };
                return (
                  <div
                    key={sig.id}
                    className="flex items-start gap-2.5 p-2.5 bg-red-50 border border-red-100 rounded-lg"
                  >
                    <span className={cn(
                      "text-[9px] font-bold px-1.5 py-0.5 rounded shrink-0 mt-0.5",
                      sig.impact_score === 5
                        ? "bg-red-500 text-white"
                        : "bg-orange-500 text-white",
                    )}>
                      {sig.impact_score}
                    </span>
                    <div className="flex-1 min-w-0">
                      <a
                        href={sig.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-xs font-medium text-slate-800 hover:text-indigo-700 hover:underline line-clamp-1"
                      >
                        {sig.title}
                      </a>
                      <div className="flex items-center gap-2 mt-0.5">
                        <span className="text-[9px] text-slate-400">{sig.country_name}</span>
                        <span className={cn("text-[9px] font-medium px-1 rounded", catMeta.color)}>
                          {catMeta.icon} {catMeta.label}
                        </span>
                        <span className="text-[9px] text-slate-400">{sig.date}</span>
                      </div>
                    </div>
                  </div>
                );
              })}
              {criticalVisible.length > 6 && (
                <p className="text-[10px] text-slate-400 text-center py-1">
                  +{criticalVisible.length - 6} more critical signals
                </p>
              )}
            </div>
          </div>
        )}

        {/* ── Per-country news count bars ──────────────────────────────── */}
        <div>
          <div className="grid grid-cols-2 gap-x-6 gap-y-0.5">
            {/* Political Risk column header */}
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-400 mb-2">
                Political Risk News Count
                <span className="font-normal ml-1">(articles/week)</span>
              </p>
            </div>
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-400 mb-2">
                Trade News Count
                <span className="font-normal ml-1">(articles/week)</span>
              </p>
            </div>

            {visibleCountries.map(c => {
              const polCount   = POLITICAL_RISK_COUNTS[c.iso3] ?? 0;
              const tradeCount = TRADE_NEWS_COUNTS[c.iso3] ?? 0;
              const nsInfo     = NS_NEWS_COUNTS[c.iso3];

              if (!nsInfo && polCount === 0 && tradeCount === 0) return null;

              const polMax     = 30;
              const tradeMax   = 20;
              const polPct     = Math.min(100, (polCount / polMax) * 100);
              const tradePct   = Math.min(100, (tradeCount / tradeMax) * 100);

              const polSev =
                polCount >= POL_RISK_CRITICAL ? "critical"
                : polCount >= POL_RISK_WARNING ? "warning"
                : "ok";
              const tradeSev =
                tradeCount >= TRADE_NEWS_WARNING ? "warning" : "ok";

              const polBarColor =
                polSev === "critical" ? "bg-red-500"
                : polSev === "warning" ? "bg-amber-500"
                : "bg-emerald-400";
              const tradeBarColor =
                tradeSev === "warning" ? "bg-amber-500" : "bg-sky-400";

              return (
                <>
                  {/* Political risk bar */}
                  <div key={`pol-${c.iso3}`} className="flex items-center gap-2 py-1 border-b border-slate-50">
                    <span className="text-sm shrink-0">{c.flagEmoji}</span>
                    <span className="text-xs text-slate-700 w-20 shrink-0">{c.shortName}</span>
                    <div className="flex-1 bg-slate-100 rounded-full h-2 overflow-hidden">
                      <div
                        className={cn("h-full rounded-full transition-all", polBarColor)}
                        style={{ width: `${polPct}%` }}
                      />
                    </div>
                    <span className={cn(
                      "text-xs font-bold tabular-nums w-6 text-right shrink-0",
                      polSev === "critical" ? "text-red-600"
                      : polSev === "warning" ? "text-amber-600"
                      : "text-slate-500",
                    )}>
                      {polCount}
                    </span>
                    {polSev === "critical" && (
                      <span className="text-[9px] font-bold text-red-600 shrink-0">CRIT</span>
                    )}
                    {polSev === "warning" && (
                      <span className="text-[9px] font-bold text-amber-600 shrink-0">WARN</span>
                    )}
                  </div>

                  {/* Trade news bar */}
                  <div key={`trade-${c.iso3}`} className="flex items-center gap-2 py-1 border-b border-slate-50">
                    <span className="text-sm shrink-0">{c.flagEmoji}</span>
                    <span className="text-xs text-slate-700 w-20 shrink-0">{c.shortName}</span>
                    <div className="flex-1 bg-slate-100 rounded-full h-2 overflow-hidden">
                      <div
                        className={cn("h-full rounded-full transition-all", tradeBarColor)}
                        style={{ width: `${tradePct}%` }}
                      />
                    </div>
                    <span className={cn(
                      "text-xs font-bold tabular-nums w-6 text-right shrink-0",
                      tradeSev === "warning" ? "text-amber-600" : "text-slate-500",
                    )}>
                      {tradeCount}
                    </span>
                    {tradeSev === "warning" && (
                      <span className="text-[9px] font-bold text-amber-600 shrink-0">HIGH</span>
                    )}
                  </div>
                </>
              );
            })}
          </div>
        </div>

        {/* ── Threshold legend ─────────────────────────────────────────── */}
        <div className="flex flex-wrap gap-4 text-[10px] text-slate-400 pt-2 border-t border-slate-100">
          <span>
            Political Risk:{" "}
            <span className="text-red-500 font-semibold">≥{POL_RISK_CRITICAL} = Critical</span>
            {" · "}
            <span className="text-amber-500 font-semibold">≥{POL_RISK_WARNING} = Warning</span>
          </span>
          <span>
            Trade News:{" "}
            <span className="text-amber-500 font-semibold">≥{TRADE_NEWS_WARNING} = Elevated</span>
          </span>
          <span className="ml-auto">
            Counts: politics + protest + conflict + election + border · trade + tariff
          </span>
        </div>
      </div>
    </div>
  );
}
