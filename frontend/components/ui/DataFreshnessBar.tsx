"use client";

/**
 * DataFreshnessBar
 * ─────────────────────────────────────────────────────────────────────────────
 * Compact badge showing the last successful update time for each data source.
 * Replaces the static "Sample Data Mode" footer in the Sidebar.
 *
 * Each source shows:
 *   • Colour-coded dot  🟢 fresh  🟡 aging  🔴 stale  ⚪ unknown
 *   • Label             "News" / "Data" / "Trade"
 *   • Age               "2h ago" / "3d ago" / "never"
 *
 * Freshness thresholds:
 *   GDELT (news)     →  green <6h   amber <12h   red >12h
 *   World Bank data  →  green <7d   amber <14d   red >14d
 *   Comtrade trade   →  green <7d   amber <14d   red >14d
 *
 * Usage:
 *   import DataFreshnessBar from "@/components/ui/DataFreshnessBar";
 *   <DataFreshnessBar />
 *   <DataFreshnessBar compact />   ← single-line variant for tight spaces
 * ─────────────────────────────────────────────────────────────────────────────
 */

import { cn } from "@/lib/utils";
import {
  ALL_SOURCES,
  PIPELINE_STATUS,
  FRESHNESS_DOT,
  FRESHNESS_TEXT,
  fmtAge,
  type SourceStatus,
} from "@/data/refresh-status";


// ── Sub-component: one source row ─────────────────────────────────────────────

function SourceRow({ s, compact }: { s: SourceStatus; compact?: boolean }) {
  const dot  = FRESHNESS_DOT[s.freshnessLevel];
  const text = FRESHNESS_TEXT[s.freshnessLevel];
  const age  = fmtAge(s.ageHours);

  // Short label to fit in the sidebar
  const shortLabel: Record<string, string> = {
    "News Feed":      "News",
    "Official Data":  "Data",
    "Trade Data":     "Trade",
  };
  const label = shortLabel[s.label] ?? s.label;

  return (
    <div className={cn(
      "flex items-center gap-1.5",
      compact ? "gap-1" : "gap-1.5",
    )}>
      {/* Freshness dot */}
      <span className={cn("shrink-0 rounded-full", dot, compact ? "w-1.5 h-1.5" : "w-2 h-2")} />

      {/* Label */}
      <span className="text-slate-500 text-[9px] font-medium leading-none shrink-0">
        {label}
      </span>

      {/* Age */}
      <span className={cn("text-[9px] leading-none", text)}>
        {age}
      </span>
    </div>
  );
}


// ── Main component ────────────────────────────────────────────────────────────

interface DataFreshnessBarProps {
  /** If true, renders all three sources on one horizontal line */
  compact?: boolean;
  /** Additional Tailwind classes for the wrapper */
  className?: string;
}

export default function DataFreshnessBar({
  compact = false,
  className,
}: DataFreshnessBarProps) {

  const alerts    = PIPELINE_STATUS.alertsGenerated;
  const critical  = PIPELINE_STATUS.alertsCritical;

  return (
    <div className={cn("select-none", className)}>
      {/* ── Header row ───────────────────────────────────── */}
      <div className="flex items-center gap-1.5 mb-1.5">
        {/* Live indicator pulse */}
        <span className="relative flex items-center justify-center w-2 h-2 shrink-0">
          <span className="absolute inline-flex rounded-full bg-emerald-400 opacity-60
                           animate-ping w-full h-full" />
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 shrink-0" />
        </span>
        <p className="text-slate-400 text-[10px] font-semibold">Live Data</p>

        {/* Alert count badge */}
        {alerts !== null && alerts > 0 && (
          <span className={cn(
            "ml-auto text-[8px] font-bold px-1 py-0.5 rounded-full",
            critical && critical > 0
              ? "bg-red-900/60 text-red-300"
              : "bg-amber-900/50 text-amber-300",
          )}>
            {critical && critical > 0 ? `${critical} crit` : `${alerts} alerts`}
          </span>
        )}
      </div>

      {/* ── Source rows ──────────────────────────────────── */}
      {compact ? (
        // All three on one line
        <div className="flex items-center gap-3 flex-wrap">
          {ALL_SOURCES.map(s => (
            <SourceRow key={s.key} s={s} compact />
          ))}
        </div>
      ) : (
        // Stacked rows
        <div className="flex flex-col gap-1">
          {ALL_SOURCES.map(s => (
            <SourceRow key={s.key} s={s} />
          ))}
        </div>
      )}
    </div>
  );
}


// ── Tooltip variant: full detail card ─────────────────────────────────────────
// Use this in a popover/tooltip to show more detail on hover.

export function DataFreshnessDetail({ className }: { className?: string }) {
  return (
    <div className={cn(
      "rounded-lg border border-slate-700 bg-slate-800/90 p-3 text-[10px] space-y-2",
      className,
    )}>
      <p className="text-slate-300 font-semibold text-[11px] mb-2">Data Freshness</p>

      {ALL_SOURCES.map(s => {
        const dot  = FRESHNESS_DOT[s.freshnessLevel];
        const text = FRESHNESS_TEXT[s.freshnessLevel];
        const age  = fmtAge(s.ageHours);
        const cnt  = s.recordCount ? ` · ${s.recordCount.toLocaleString()} records` : "";

        return (
          <div key={s.key} className="flex items-start gap-2">
            <span className={cn("w-2 h-2 rounded-full shrink-0 mt-0.5", dot)} />
            <div>
              <p className="text-slate-200 font-medium">{s.label}</p>
              <p className={cn("text-[9px]", text)}>
                {age}{cnt}
              </p>
              {s.status === "rate_limited" && (
                <p className="text-amber-400 text-[8px]">Last refresh was rate-limited</p>
              )}
            </div>
          </div>
        );
      })}

      {PIPELINE_STATUS.alertsGenerated !== null && (
        <div className="pt-2 border-t border-slate-700">
          <p className="text-slate-500">
            {PIPELINE_STATUS.alertsGenerated} alerts
            {PIPELINE_STATUS.alertsCritical
              ? ` · ${PIPELINE_STATUS.alertsCritical} critical`
              : ""}
          </p>
        </div>
      )}

      <p className="text-slate-600 text-[8px] pt-1">
        Auto-refreshes: news every 6h · data weekly
      </p>
    </div>
  );
}
