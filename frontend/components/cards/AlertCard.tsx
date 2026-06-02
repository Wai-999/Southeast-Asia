/**
 * AlertCard — displays a single pattern alert.
 * Static prototype version: no API calls, no AI button.
 */

import { cn, SEV_BORDER } from "@/lib/utils";
import { SeverityBadge } from "@/components/ui/Badge";
import { getCountry } from "@/data/sample-data";
import type { PatternAlert } from "@/data/sample-data";

interface Props {
  alert: PatternAlert;
  compact?: boolean;
}

function calcProgress(triggerValue: number, threshold: number): number {
  if (threshold === 0) return Math.min(100, Math.abs(triggerValue) * 10);
  return Math.min(100, (Math.abs(triggerValue) / Math.abs(threshold)) * 60);
}

export default function AlertCard({ alert, compact = false }: Props) {
  const country    = getCountry(alert.countryId);
  const progress   = calcProgress(alert.triggerValue, alert.threshold);
  const overThresh = Math.abs(alert.triggerValue) > Math.abs(alert.threshold);

  const barColor =
    alert.severity === "critical" ? "bg-red-500" :
    alert.severity === "warning"  ? "bg-amber-500" :
    "bg-sky-500";

  return (
    <div className={cn(
      "card border-l-4 p-4",
      SEV_BORDER[alert.severity],
      !alert.isActive && "opacity-55",
    )}>
      {/* Header */}
      <div className="flex items-start justify-between mb-2.5">
        <div className="flex items-center gap-2.5">
          <span className="text-xl leading-none">{country?.flagEmoji}</span>
          <div>
            <p className="font-semibold text-sm text-slate-900 leading-tight">{country?.name}</p>
            <p className="text-xs text-slate-400 mt-0.5">{alert.ruleName}</p>
          </div>
        </div>
        <div className="flex items-center gap-1.5 flex-shrink-0">
          <SeverityBadge severity={alert.severity} />
          {!alert.isActive && (
            <span className="text-[10px] px-2 py-0.5 bg-slate-100 text-slate-400 rounded-full">
              Resolved
            </span>
          )}
        </div>
      </div>

      {/* Message */}
      <p className="text-xs text-slate-600 leading-relaxed mb-3">{alert.message}</p>

      {/* Progress bar (hidden in compact mode) */}
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
    </div>
  );
}
