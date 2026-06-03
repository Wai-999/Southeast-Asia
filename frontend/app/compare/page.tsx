"use client";

/**
 * app/compare/page.tsx — Country Comparison
 *
 * Side-by-side metric comparison for all 5 countries.
 * Pick any of the 8 indicators from the selector row.
 */

import { useState, useMemo } from "react";
import Link from "next/link";
import CompareBarChart from "@/components/charts/CompareBarChart";
import { RiskBadge } from "@/components/ui/Badge";
import {
  COUNTRIES, CURRENT_INDICATORS,
  METRIC_LABELS, METRIC_UNITS, METRIC_DESC, METRIC_HIGHER_IS_WORSE,
  getCompareData, type MetricKey,
} from "@/data/live-data";
import CountryFilter, { type FilterMode } from "@/components/ui/CountryFilter";
import { getIso3ForMode } from "@/data/countries";
import WorldBankNote from "@/components/ui/WorldBankNote";
import { cn } from "@/lib/utils";

const ALL_METRICS: MetricKey[] = [
  "gdpGrowth", "inflation", "exports", "imports",
  "exchangeRate", "fdi", "politicalRiskNews", "tradeNewsCount",
];

type SortDir = "desc" | "asc" | "risk";
const RISK_ORDER = { critical: 0, high: 1, medium: 2, low: 3 };

export default function ComparePage() {
  const [metric,     setMetric]     = useState<MetricKey>("gdpGrowth");
  const [sort,       setSort]       = useState<SortDir>("desc");
  const [filterMode, setFilterMode] = useState<FilterMode>("sea");
  const [customIds,  setCustomIds]  = useState<string[]>([]);

  // ISO3 codes selected by the filter
  const activeCountryIds = getIso3ForMode(filterMode, customIds);

  // Only compare countries that have indicator data AND match the filter
  const activeDataIds = new Set(COUNTRIES.map(c => c.id));
  const visibleIds    = new Set([...activeCountryIds].filter(id => activeDataIds.has(id)));

  const raw    = getCompareData(metric).filter(row => visibleIds.has(row.countryId));
  const sorted = [...raw].sort((a, b) => {
    if (sort === "asc")  return a.value - b.value;
    if (sort === "desc") return b.value - a.value;
    return RISK_ORDER[a.riskLevel] - RISK_ORDER[b.riskLevel];
  });

  const unit   = METRIC_UNITS[metric];
  const isWorse = METRIC_HIGHER_IS_WORSE[metric];

  // Best / worst label (direction-aware)
  const ranked  = [...raw].sort((a, b) => b.value - a.value);
  const bestIdx = isWorse ? ranked.length - 1 : 0;
  const worstIdx= isWorse ? 0 : ranked.length - 1;
  const best    = ranked[bestIdx];
  const worst   = ranked[worstIdx];

  return (
    <div className="p-7 max-w-7xl mx-auto">

      {/* ── Header ──────────────────────────────────────────────── */}
      <div className="flex items-start justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
            Country Comparison
          </h1>
          <p className="text-slate-500 text-sm mt-0.5">
            Compare 8 economic indicators · {visibleIds.size} countr{visibleIds.size === 1 ? "y" : "ies"} shown · 2024 data
          </p>
        </div>

        {/* Country filter in header */}
        <div className="mt-3">
          <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-400 mb-1.5">
            Country Scope
          </p>
          <CountryFilter
            mode={filterMode}
            onModeChange={setFilterMode}
            customSelection={customIds}
            onCustomChange={setCustomIds}
            showActiveOnly
            compact
          />
          {visibleIds.size === 0 && (
            <p className="text-xs text-amber-600 mt-1.5">
              ⚠ None of the selected countries have indicator data yet.
              Switch to <button className="underline" onClick={() => setFilterMode("sea")}>SEA Only</button> to see countries with data.
            </p>
          )}
        </div>
      </div>

      {/* ── World Bank annual note ────────────────────────────── */}
      <WorldBankNote className="mb-5" />

      {/* ── Controls panel ────────────────────────────────────── */}
      <div className="card-p mb-6">
        <div className="flex flex-wrap items-start gap-6">

          {/* Metric picker */}
          <div className="flex-1 min-w-0">
            <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-400 mb-2">
              Select Indicator
            </p>
            <div className="flex flex-wrap gap-1.5">
              {ALL_METRICS.map(m => (
                <button key={m} onClick={() => setMetric(m)}
                  className={cn(
                    "text-xs px-3 py-1.5 rounded-lg border transition-colors",
                    metric === m
                      ? "bg-indigo-600 text-white border-indigo-600 font-medium"
                      : "border-slate-200 text-slate-600 hover:border-indigo-300 hover:text-indigo-700 bg-white",
                  )}>
                  {METRIC_LABELS[m]}
                </button>
              ))}
            </div>
            {/* Metric description */}
            <p className="text-xs text-slate-400 mt-2 italic">{METRIC_DESC[metric]}</p>
          </div>

          {/* Sort */}
          <div className="flex-shrink-0">
            <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-400 mb-2">
              Sort Order
            </p>
            <div className="flex gap-1.5">
              {(["desc", "asc", "risk"] as SortDir[]).map(s => (
                <button key={s} onClick={() => setSort(s)}
                  className={cn(
                    "text-xs px-3 py-1.5 rounded-lg border transition-colors",
                    sort === s
                      ? "bg-slate-800 text-white border-slate-800"
                      : "border-slate-200 text-slate-600 hover:bg-slate-50",
                  )}>
                  {s === "desc" ? "High → Low" : s === "asc" ? "Low → High" : "By Risk Level"}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* ── Best / Worst callouts ─────────────────────────────── */}
      <div className="grid grid-cols-2 gap-4 mb-6">
        <div className="card-p border-l-4 border-l-emerald-500 flex items-center gap-4">
          <span className="text-3xl">{best.flagEmoji}</span>
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-wide text-emerald-600">
              {isWorse ? "Lowest (Best)" : "Highest (Best)"}
            </p>
            <p className="font-bold text-slate-900">{best.countryName}</p>
            <p className="text-sm text-slate-500 tabular-nums">
              {best.value.toFixed(1)} {unit}
            </p>
          </div>
        </div>
        <div className="card-p border-l-4 border-l-red-500 flex items-center gap-4">
          <span className="text-3xl">{worst.flagEmoji}</span>
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-wide text-red-600">
              {isWorse ? "Highest (Worst)" : "Lowest (Worst)"}
            </p>
            <p className="font-bold text-slate-900">{worst.countryName}</p>
            <p className="text-sm text-slate-500 tabular-nums">
              {worst.value.toFixed(1)} {unit}
            </p>
          </div>
        </div>
      </div>

      {/* ── Bar chart ─────────────────────────────────────────── */}
      <div className="card-p mb-6">
        <div className="flex items-start justify-between mb-4">
          <div>
            <h2 className="font-semibold text-slate-900">{METRIC_LABELS[metric]}</h2>
            <p className="text-xs text-slate-400 mt-0.5">
              Unit: {unit} · 5 ASEAN countries · 2024 data
            </p>
          </div>
          <div className="flex items-center gap-4 text-xs text-slate-400">
            {(["low","medium","high","critical"] as const).map(r => (
              <span key={r} className="flex items-center gap-1.5">
                <span className={cn("w-2.5 h-2.5 rounded-full", {
                  low:      "bg-emerald-500",
                  medium:   "bg-amber-500",
                  high:     "bg-orange-500",
                  critical: "bg-red-500",
                }[r])} />
                {r.charAt(0).toUpperCase() + r.slice(1)}
              </span>
            ))}
          </div>
        </div>
        <CompareBarChart data={sorted} unit={unit.includes("%") ? "%" : ""} height={280} />
      </div>

      {/* ── Data table ────────────────────────────────────────── */}
      <div className="card overflow-hidden mb-6">
        <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
          <h3 className="font-semibold text-slate-900 text-sm">
            Full Data Table — {METRIC_LABELS[metric]}
          </h3>
          <span className="text-xs text-slate-400">Sorted by current selection</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100 bg-slate-50/60">
                <th className="px-5 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide text-left w-8">#</th>
                <th className="px-5 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide text-left">Country</th>
                <th className="px-5 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide text-right">
                  {METRIC_LABELS[metric]} ({unit})
                </th>
                <th className="px-5 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide text-left">Risk Level</th>
                <th className="px-5 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide text-right">GDP Growth</th>
                <th className="px-5 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide text-right">Inflation</th>
                <th className="px-5 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide text-right">FDI (B)</th>
                <th className="px-5 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide"></th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((row, i) => {
                const country  = COUNTRIES.find(c => c.id === row.countryId)!;
                const ind      = CURRENT_INDICATORS[row.countryId];
                const signedM  = ["gdpGrowth"].includes(metric);
                return (
                  <tr key={row.countryId}
                    className="border-b border-slate-50 hover:bg-slate-50/60 transition-colors">
                    <td className="px-5 py-3.5 text-slate-400 text-xs font-medium">{i + 1}</td>
                    <td className="px-5 py-3.5">
                      <div className="flex items-center gap-2.5">
                        <span className="text-xl">{row.flagEmoji}</span>
                        <span className="font-medium text-slate-900">{row.countryName}</span>
                      </div>
                    </td>
                    <td className="px-5 py-3.5 text-right">
                      <span className={cn(
                        "font-bold tabular-nums text-base",
                        signedM
                          ? row.value >= 0 ? "text-emerald-600" : "text-red-500"
                          : isWorse
                          ? row.value > ranked[0].value * 0.7 ? "text-red-500" : "text-slate-900"
                          : row.value < ranked[ranked.length-1].value * 1.3 ? "text-amber-600" : "text-emerald-600",
                      )}>
                        {signedM && row.value > 0 ? "+" : ""}
                        {row.value >= 1000 ? row.value.toLocaleString() : row.value.toFixed(1)}
                      </span>
                      <span className="text-xs text-slate-400 ml-1">{unit.split(" ")[0]}</span>
                    </td>
                    <td className="px-5 py-3.5">
                      <RiskBadge level={country.riskLevel} />
                    </td>
                    <td className="px-5 py-3.5 text-right">
                      <span className={cn(
                        "text-sm font-medium tabular-nums",
                        ind.gdpGrowth >= 0 ? "text-emerald-600" : "text-red-500",
                      )}>
                        {ind.gdpGrowth >= 0 ? "+" : ""}{ind.gdpGrowth.toFixed(1)}%
                      </span>
                    </td>
                    <td className="px-5 py-3.5 text-right">
                      <span className={cn(
                        "text-sm tabular-nums",
                        ind.inflation > 10 ? "text-red-600 font-bold" :
                        ind.inflation > 5  ? "text-amber-600" : "text-slate-700",
                      )}>
                        {ind.inflation.toFixed(1)}%
                      </span>
                    </td>
                    <td className="px-5 py-3.5 text-right">
                      <span className={cn(
                        "text-sm tabular-nums",
                        ind.fdi < 1 ? "text-red-600 font-bold" : "text-slate-700",
                      )}>
                        ${ind.fdi}B
                      </span>
                    </td>
                    <td className="px-5 py-3.5">
                      <Link href={`/country/${row.countryId}`}
                        className="text-xs text-indigo-600 hover:underline font-medium">
                        View profile →
                      </Link>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* ── All-metrics mini-grid ─────────────────────────────── */}
      <div className="card-p bg-slate-50/50">
        <h3 className="font-semibold text-slate-900 text-sm mb-4">
          All 8 Indicators — Quick Reference
        </h3>
        <div className="grid grid-cols-4 gap-3">
          {ALL_METRICS.map(m => {
            const vals = COUNTRIES.map(c => ({
              name: c.shortName,
              flag: c.flagEmoji,
              val:  CURRENT_INDICATORS[c.id][m],
            })).sort((a, b) => b.val - a.val);
            const leader = METRIC_HIGHER_IS_WORSE[m] ? vals[vals.length - 1] : vals[0];
            return (
              <button key={m} onClick={() => setMetric(m)}
                className={cn(
                  "text-left p-3 rounded-lg border transition-all",
                  metric === m
                    ? "border-indigo-300 bg-indigo-50 shadow-sm"
                    : "border-slate-200 bg-white hover:border-indigo-200 hover:bg-indigo-50/50",
                )}>
                <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-400 mb-1">
                  {METRIC_LABELS[m]}
                </p>
                <p className="text-sm font-bold text-slate-900 tabular-nums">
                  {leader.flag} {leader.name}
                </p>
                <p className="text-xs text-emerald-600">
                  {leader.val >= 1000 ? leader.val.toLocaleString() : leader.val.toFixed(1)} {METRIC_UNITS[m].split(" ")[0]}
                </p>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
