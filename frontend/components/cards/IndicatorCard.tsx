"use client";

import { cn } from "@/lib/utils";
import MiniSparkline from "@/components/charts/MiniSparkline";
import SourceBadge from "@/components/ui/SourceBadge";
import type { YearPoint } from "@/data/sample-data";
import type { SourceMeta } from "@/lib/source-meta";

interface Props {
  title:     string;
  value:     string;
  unit:      string;
  change?:   number;      // year-over-year change
  trend?:    YearPoint[];
  positive?: boolean;     // is higher value good?
  alert?:    boolean;
  /** Optional: source metadata for the "Source Details" badge */
  source?:   SourceMeta;
}

export default function IndicatorCard({
  title, value, unit, change, trend,
  positive = true, alert = false, source,
}: Props) {
  const isPositive = change !== undefined ? (positive ? change >= 0 : change <= 0) : true;

  return (
    <div className={cn(
      "card-p flex flex-col gap-2",
      alert && "border-red-200 bg-red-50/30",
    )}>

      {/* Title row */}
      <p className="text-xs text-slate-500 font-medium">{title}</p>

      {/* Value + change badge */}
      <div className="flex items-end justify-between">
        <div>
          <span className="text-2xl font-bold text-slate-900 tabular-nums">{value}</span>
          <span className="text-sm text-slate-500 ml-1">{unit}</span>
        </div>
        {change !== undefined && (
          <span className={cn(
            "text-xs font-semibold px-2 py-0.5 rounded-full",
            isPositive
              ? "bg-emerald-50 text-emerald-700"
              : "bg-red-50 text-red-600",
          )}>
            {change >= 0 ? "+" : ""}{change.toFixed(1)}{unit.includes("%") ? "pp" : ""}
          </span>
        )}
      </div>

      {/* Sparkline */}
      {trend && (
        <div className="-mx-1">
          <MiniSparkline data={trend} positive={isPositive} />
        </div>
      )}

      {/* Alert flag */}
      {alert && (
        <p className="text-[10px] text-red-500 font-medium">⚑ Alert active</p>
      )}

      {/* Source badge — shown only when source metadata is provided */}
      {source && (
        <div className="pt-1 border-t border-slate-100 mt-auto">
          <SourceBadge meta={source} />
        </div>
      )}
    </div>
  );
}
