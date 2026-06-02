/**
 * AlertCard — displays a single pattern alert with optional source-details panel.
 */

import { cn, SEV_BORDER } from "@/lib/utils";
import { SeverityBadge } from "@/components/ui/Badge";
import SourceBadge from "@/components/ui/SourceBadge";
import { getCountry } from "@/data/sample-data";
import type { PatternAlert } from "@/data/sample-data";
import type { SourceMeta, SourceConfidence } from "@/lib/source-meta";
import { CONF_DOT, CONF_LABEL } from "@/lib/source-meta";

interface Props {
  alert:    PatternAlert;
  compact?: boolean;
  /** Optional enriched source metadata (from pattern-alerts.ts EnrichedAlert) */
  source?:  SourceMeta;
  /** Optional: conditions that triggered the alert */
  conditions?: string[];
  /** Optional: confidence level (overrides source.confidence if provided) */
  confidence?: SourceConfidence;
  /** Optional: how many of the 3 sources agreed */
  sourcesCount?: number;
}

function calcProgress(triggerValue: number, threshold: number): number {
  if (threshold === 0) return Math.min(100, Math.abs(triggerValue) * 10);
  return Math.min(100, (Math.abs(triggerValue) / Math.abs(threshold)) * 60);
}

export default function AlertCard({
  alert, compact = false,
  source, conditions, confidence, sourcesCount,
}: Props) {
  const country    = getCountry(alert.countryId);
  const progress   = calcProgress(alert.triggerValue, alert.threshold);
  const overThresh = Math.abs(alert.triggerValue) > Math.abs(alert.threshold);

  const barColor =
    alert.severity === "critical" ? "bg-red-500" :
    alert.severity === "warning"  ? "bg-amber-500" :
    "bg-sky-500";

  // Effective confidence — from prop override or source meta
  const conf: SourceConfidence | undefined = confidence ?? source?.confidence;

  return (
    <div className={cn(
      "card border-l-4 p-4",
      SEV_BORDER[alert.severity],
      !alert.isActive && "opacity-55",
    )}>

      {/* ── Header ──────────────────────────────────────────────────── */}
      <div className="flex items-start justify-between mb-2.5">
        <div className="flex items-center gap-2.5">
          <span className="text-xl leading-none">{country?.flagEmoji}</span>
          <div>
            <p className="font-semibold text-sm text-slate-900 leading-tight">
              {country?.name}
            </p>
            <p className="text-xs text-slate-400 mt-0.5">{alert.ruleName}</p>
          </div>
        </div>
        <div className="flex items-center gap-1.5 flex-shrink-0">
          {/* Confidence pips beside severity badge */}
          {conf && (
            <span className="flex items-center gap-0.5" title={CONF_LABEL[conf]}>
              {([0,1,2] as const).map(i => (
                <span
                  key={i}
                  className={cn(
                    "w-1.5 h-1.5 rounded-full",
                    i < (conf === "high" ? 3 : conf === "medium" ? 2 : 1)
                      ? CONF_DOT[conf]
                      : "bg-slate-200",
                  )}
                />
              ))}
            </span>
          )}
          <SeverityBadge severity={alert.severity} />
          {!alert.isActive && (
            <span className="text-[10px] px-2 py-0.5 bg-slate-100 text-slate-400 rounded-full">
              Resolved
            </span>
          )}
        </div>
      </div>

      {/* ── Message ─────────────────────────────────────────────────── */}
      <p className="text-xs text-slate-600 leading-relaxed mb-3">{alert.message}</p>

      {/* ── Triggered conditions (compact list) ─────────────────────── */}
      {!compact && conditions && conditions.length > 0 && (
        <ul className="mb-3 space-y-0.5">
          {conditions.slice(0, 3).map((c, i) => (
            <li key={i} className="flex items-start gap-1.5 text-[10px] text-slate-500">
              <span className="mt-0.5 text-slate-300 flex-shrink-0">•</span>
              {c}
            </li>
          ))}
          {conditions.length > 3 && (
            <li className="text-[10px] text-slate-400 pl-3.5">
              +{conditions.length - 3} more conditions
            </li>
          )}
        </ul>
      )}

      {/* ── Progress bar ────────────────────────────────────────────── */}
      {!compact && (
        <div>
          <div className="flex justify-between text-[10px] text-slate-400 mb-1">
            <span>{alert.indicatorLabel}</span>
            <span>Threshold: {alert.threshold}{alert.unit.startsWith("%") ? "%" : ""}</span>
          </div>
          <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
            <div
              className={cn("h-full rounded-full transition-all duration-500", barColor)}
              style={{ width: `${progress}%` }}
            />
          </div>
          <div className="flex justify-between mt-1.5">
            <span className={cn(
              "text-xs font-bold tabular-nums",
              overThresh
                ? alert.severity === "critical" ? "text-red-600" : "text-amber-600"
                : "text-slate-600",
            )}>
              {alert.triggerValue.toFixed(1)} {alert.unit} actual
            </span>
            <span className="text-[10px] text-slate-400">{alert.triggeredAt}</span>
          </div>
        </div>
      )}

      {compact && (
        <p className="text-[10px] text-slate-400">{alert.triggeredAt}</p>
      )}

      {/* ── Source details ───────────────────────────────────────────── */}
      {source && (
        <div className="pt-2.5 mt-2.5 border-t border-slate-100 flex items-center justify-between">
          <SourceBadge meta={source} />
          {sourcesCount !== undefined && (
            <span className="text-[9px] text-slate-400 font-medium">
              {sourcesCount}/3 sources agree
            </span>
          )}
        </div>
      )}
    </div>
  );
}
