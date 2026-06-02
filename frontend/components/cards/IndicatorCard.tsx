"use client";
import { cn } from "@/lib/utils";
import MiniSparkline from "@/components/charts/MiniSparkline";
import type { YearPoint } from "@/data/sample-data";

interface Props {
  title: string;
  value: string;
  unit: string;
  change?: number;    // year-over-year change
  trend?: YearPoint[];
  positive?: boolean; // is higher value good?
  alert?: boolean;
}

export default function IndicatorCard({ title, value, unit, change, trend, positive = true, alert = false }: Props) {
  const isPositive = change !== undefined ? (positive ? change >= 0 : change <= 0) : true;

  return (
    <div className={cn(
      "card-p flex flex-col gap-2",
      alert && "border-red-200 bg-red-50/30"
    )}>
      <p className="text-xs text-slate-500 font-medium">{title}</p>
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
              : "bg-red-50 text-red-600"
          )}>
            {change >= 0 ? "+" : ""}{change.toFixed(1)}{unit.includes("%") ? "pp" : ""}
          </span>
        )}
      </div>
      {trend && (
        <div className="-mx-1">
          <MiniSparkline data={trend} positive={isPositive} />
        </div>
      )}
      {alert && (
        <p className="text-[10px] text-red-500 font-medium">⚑ Alert active</p>
      )}
    </div>
  );
}
