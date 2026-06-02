/**
 * app/page.tsx — Regional Overview (Home)
 *
 * Shows: alert ticker · KPI cards · 5-country risk grid ·
 *        GDP comparison bar chart · top alerts · recent news
 */

import Link from "next/link";
import CountryRiskCard from "@/components/cards/CountryRiskCard";
import NewsCard from "@/components/cards/NewsCard";
import AlertCard from "@/components/cards/AlertCard";
import CompareBarChart from "@/components/charts/CompareBarChart";
import {
  COUNTRIES, CURRENT_INDICATORS, PATTERN_ALERTS,
  NEWS_EVENTS, getCompareData, getCountry,
} from "@/data/sample-data";
import WorldBankNote from "@/components/ui/WorldBankNote";

export default function OverviewPage() {
  // ── Derived values ─────────────────────────────────────────────
  const activeAlerts   = PATTERN_ALERTS.filter(a => a.isActive);
  const criticalCount  = activeAlerts.filter(a => a.severity === "critical").length;
  const warningCount   = activeAlerts.filter(a => a.severity === "warning").length;

  const topGrowth    = [...COUNTRIES].sort((a, b) =>
    CURRENT_INDICATORS[b.id].gdpGrowth - CURRENT_INDICATORS[a.id].gdpGrowth)[0];
  const topInflation = [...COUNTRIES].sort((a, b) =>
    CURRENT_INDICATORS[b.id].inflation - CURRENT_INDICATORS[a.id].inflation)[0];
  const topExporter  = [...COUNTRIES].sort((a, b) =>
    CURRENT_INDICATORS[b.id].exports - CURRENT_INDICATORS[a.id].exports)[0];
  const highestFDI   = [...COUNTRIES].sort((a, b) =>
    CURRENT_INDICATORS[b.id].fdi - CURRENT_INDICATORS[a.id].fdi)[0];

  const gdpBarData    = getCompareData("gdpGrowth");
  const topCritical   = activeAlerts.filter(a => a.severity === "critical").slice(0, 3);
  const topWarning    = activeAlerts.filter(a => a.severity === "warning").slice(0, 2);
  const shownAlerts   = [...topCritical, ...topWarning].slice(0, 4);
  const recentNews    = NEWS_EVENTS.slice(0, 4);

  return (
    <div className="p-7 max-w-7xl mx-auto">

      {/* ── Page header ──────────────────────────────────────── */}
      <div className="flex items-start justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
            Regional Overview
          </h1>
          <p className="text-slate-500 text-sm mt-0.5">
            SEA Change Intelligence Dashboard · 5 countries · Dec 2024
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-emerald-500" />
          <span className="text-xs text-slate-400">Sample data · All indicators current</span>
        </div>
      </div>

      {/* ── World Bank data note ─────────────────────────────── */}
      <WorldBankNote className="mb-5" />

      {/* ── Alert ticker ─────────────────────────────────────── */}
      {activeAlerts.length > 0 && (
        <div className="flex items-center gap-3 rounded-xl px-4 py-3 mb-6 border border-red-200 bg-red-50">
          <span className="text-red-600 font-bold text-xs flex-shrink-0 flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
            {activeAlerts.length} Active Alerts
          </span>
          <div className="text-xs text-red-700 truncate flex-1">
            {activeAlerts.slice(0, 3).map(a =>
              `${getCountry(a.countryId)?.flagEmoji} ${a.ruleName}`
            ).join("  ·  ")}
          </div>
          <Link href="/alerts"
            className="ml-auto text-xs text-red-600 font-semibold hover:underline flex-shrink-0">
            View all alerts →
          </Link>
        </div>
      )}

      {/* ── KPI summary row ──────────────────────────────────── */}
      <div className="grid grid-cols-4 gap-4 mb-7">
        <KpiCard
          emoji="📈"
          label="Fastest Growing"
          value={`${topGrowth.flagEmoji} ${topGrowth.shortName}`}
          sub={`+${CURRENT_INDICATORS[topGrowth.id].gdpGrowth.toFixed(1)}% GDP 2024`}
          accent="emerald"
        />
        <KpiCard
          emoji="🌡"
          label="Inflation Hotspot"
          value={`${topInflation.flagEmoji} ${topInflation.shortName}`}
          sub={`${CURRENT_INDICATORS[topInflation.id].inflation.toFixed(1)}% CPI — highest`}
          accent="red"
        />
        <KpiCard
          emoji="🚢"
          label="Top Exporter"
          value={`${topExporter.flagEmoji} ${topExporter.shortName}`}
          sub={`$${CURRENT_INDICATORS[topExporter.id].exports}B exports`}
          accent="blue"
        />
        <KpiCard
          emoji="⚑"
          label="Active Alerts"
          value={`${criticalCount} Critical`}
          sub={`+${warningCount} Warnings · ${activeAlerts.length} total`}
          accent="amber"
        />
      </div>

      {/* ── Country risk grid ─────────────────────────────────── */}
      <div className="mb-7">
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-semibold text-slate-900 text-sm">Country Risk Overview</h2>
          <Link href="/compare" className="text-xs text-indigo-600 hover:underline font-medium">
            Compare all metrics →
          </Link>
        </div>
        <div className="grid grid-cols-5 gap-3">
          {COUNTRIES.map(c => (
            <CountryRiskCard
              key={c.id}
              country={c}
              indicators={CURRENT_INDICATORS[c.id]}
            />
          ))}
        </div>
      </div>

      {/* ── Charts + Alerts row ───────────────────────────────── */}
      <div className="grid grid-cols-5 gap-5 mb-7">

        {/* GDP comparison chart */}
        <div className="col-span-3 card-p">
          <div className="flex items-start justify-between mb-4">
            <div>
              <h3 className="font-semibold text-slate-900 text-sm">GDP Growth Rate — 2024</h3>
              <p className="text-xs text-slate-400 mt-0.5">
                Bars coloured by country risk level · % year-over-year
              </p>
            </div>
            <Link href="/compare"
              className="text-xs text-indigo-600 hover:underline font-medium flex-shrink-0">
              Full comparison →
            </Link>
          </div>
          <CompareBarChart data={gdpBarData} unit="%" height={230} />

          {/* Risk legend */}
          <div className="flex items-center gap-4 mt-3 pt-3 border-t border-slate-100">
            {(["low", "medium", "high", "critical"] as const).map(r => (
              <span key={r} className="flex items-center gap-1.5 text-xs text-slate-500">
                <span className={{
                  low: "w-2.5 h-2.5 rounded-full bg-emerald-500",
                  medium: "w-2.5 h-2.5 rounded-full bg-amber-500",
                  high: "w-2.5 h-2.5 rounded-full bg-orange-500",
                  critical: "w-2.5 h-2.5 rounded-full bg-red-500",
                }[r]} />
                {r.charAt(0).toUpperCase() + r.slice(1)}
              </span>
            ))}
          </div>
        </div>

        {/* Top alerts */}
        <div className="col-span-2 card-p">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-semibold text-slate-900 text-sm">Priority Alerts</h3>
            <Link href="/alerts"
              className="text-xs text-indigo-600 hover:underline font-medium">
              All {activeAlerts.length} alerts →
            </Link>
          </div>
          <div className="flex flex-col gap-3">
            {shownAlerts.length > 0
              ? shownAlerts.map(a => (
                  <AlertCard key={a.id} alert={a} compact />
                ))
              : <p className="text-sm text-slate-400 text-center py-10">No active alerts</p>
            }
          </div>
        </div>
      </div>

      {/* ── Indicator heat table ──────────────────────────────── */}
      <div className="card overflow-hidden mb-7">
        <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
          <h3 className="font-semibold text-slate-900 text-sm">
            Indicator Snapshot — All Countries · 2024
          </h3>
          <span className="text-xs text-slate-400">Click a country name to drill down</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100 bg-slate-50/60">
                {["Country", "GDP Growth", "Inflation", "Exports", "Imports",
                  "Exchange Rate", "FDI", "Pol. Risk News", "Trade News"].map(h => (
                  <th key={h}
                    className="px-4 py-3 text-[10px] font-semibold text-slate-500 uppercase tracking-wide text-left whitespace-nowrap">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {COUNTRIES.map(c => {
                const ind = CURRENT_INDICATORS[c.id];
                return (
                  <tr key={c.id}
                    className="border-b border-slate-50 hover:bg-slate-50/60 transition-colors">
                    <td className="px-4 py-3">
                      <Link href={`/country/${c.id}`}
                        className="flex items-center gap-2 hover:text-indigo-600 transition-colors">
                        <span className="text-lg">{c.flagEmoji}</span>
                        <span className="font-medium text-slate-900">{c.shortName}</span>
                      </Link>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`font-bold tabular-nums text-sm ${
                        ind.gdpGrowth < 0 ? "text-red-600" :
                        ind.gdpGrowth < 2 ? "text-amber-600" : "text-emerald-600"
                      }`}>
                        {ind.gdpGrowth >= 0 ? "+" : ""}{ind.gdpGrowth.toFixed(1)}%
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`tabular-nums text-sm ${
                        ind.inflation > 10 ? "text-red-600 font-bold" :
                        ind.inflation > 5  ? "text-amber-600 font-medium" : "text-slate-700"
                      }`}>
                        {ind.inflation.toFixed(1)}%
                      </span>
                    </td>
                    <td className="px-4 py-3 text-slate-700 tabular-nums text-sm">
                      ${ind.exports}B
                    </td>
                    <td className="px-4 py-3 text-slate-700 tabular-nums text-sm">
                      ${ind.imports}B
                    </td>
                    <td className="px-4 py-3 text-slate-500 text-sm">
                      {ind.exchangeRate >= 1000
                        ? ind.exchangeRate.toLocaleString()
                        : ind.exchangeRate.toFixed(2)}{" "}{c.currency}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`tabular-nums text-sm ${
                        ind.fdi < 1 ? "text-red-600 font-bold" :
                        ind.fdi < 3 ? "text-amber-600" : "text-slate-700"
                      }`}>
                        ${ind.fdi}B
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`tabular-nums text-sm font-medium ${
                        ind.politicalRiskNews > 100 ? "text-red-600" :
                        ind.politicalRiskNews > 40  ? "text-amber-600" : "text-emerald-600"
                      }`}>
                        {ind.politicalRiskNews}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-slate-600 tabular-nums text-sm">
                      {ind.tradeNewsCount}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* ── Recent news ───────────────────────────────────────── */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-semibold text-slate-900">Latest News & Events</h2>
          <Link href="/news"
            className="text-xs text-indigo-600 hover:underline font-medium">
            Full news feed ({NEWS_EVENTS.length} events) →
          </Link>
        </div>
        <div className="grid grid-cols-2 gap-4">
          {recentNews.map(n => (
            <NewsCard key={n.id} event={n} compact />
          ))}
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────
// Sub-component: KPI summary card
// ─────────────────────────────────────────────────────────────────
function KpiCard({ emoji, label, value, sub, accent }: {
  emoji: string;
  label: string;
  value: string;
  sub: string;
  accent: "emerald" | "red" | "amber" | "blue";
}) {
  const bg   = { emerald: "bg-emerald-50", red: "bg-red-50", amber: "bg-amber-50", blue: "bg-blue-50"   }[accent];
  const text = { emerald: "text-emerald-700", red: "text-red-700", amber: "text-amber-700", blue: "text-blue-700" }[accent];
  return (
    <div className="card-p">
      <div className={`inline-flex items-center justify-center w-9 h-9 rounded-xl ${bg} text-lg mb-3`}>
        {emoji}
      </div>
      <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-400 mb-1">
        {label}
      </p>
      <p className={`font-bold text-sm ${text}`}>{value}</p>
      <p className="text-xs text-slate-400 mt-0.5">{sub}</p>
    </div>
  );
}
