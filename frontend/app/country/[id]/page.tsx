"use client";

/**
 * app/country/[id]/page.tsx — Country Profile
 *
 * Full profile for one country.
 * Shows: all 8 indicators · 5-year trend chart · exports vs imports ·
 *        news events · active alerts
 */

import { notFound, useParams } from "next/navigation";
import Link from "next/link";
import { useState } from "react";
import { RiskBadge } from "@/components/ui/Badge";
import IndicatorCard from "@/components/cards/IndicatorCard";
import NewsCard from "@/components/cards/NewsCard";
import AlertCard from "@/components/cards/AlertCard";
import TrendLineChart from "@/components/charts/TrendLineChart";
import CompareBarChart from "@/components/charts/CompareBarChart";
import {
  COUNTRIES, CURRENT_INDICATORS, HISTORICAL,
  NEWS_EVENTS, PATTERN_ALERTS, getYoYChange,
} from "@/data/sample-data";
import WorldBankNote from "@/components/ui/WorldBankNote";
import {
  WB_INDICATOR_KEYS, WB_INDICATORS, WB_INDICATOR_LABELS, WB_INDICATOR_UNITS,
  WB_COUNTRY_SUMMARIES, WB_DATA_STATUS,
  QUALITY_LABEL, QUALITY_COLOR, QUALITY_DOT,
  getWbHistory,
} from "@/data/worldbank-data";
import { cn } from "@/lib/utils";

// ── Chart tabs definition ──────────────────────────────────────────
const CHART_TABS = [
  { key: "gdpGrowth"         as const, label: "GDP Growth",      unit: "%",         color: "#3b82f6" },
  { key: "inflation"         as const, label: "Inflation",       unit: "%",         color: "#f59e0b" },
  { key: "exports"           as const, label: "Exports",         unit: "B USD",     color: "#10b981" },
  { key: "imports"           as const, label: "Imports",         unit: "B USD",     color: "#6366f1" },
  { key: "exchangeRate"      as const, label: "Exchange Rate",   unit: "per USD",   color: "#ec4899" },
  { key: "fdi"               as const, label: "FDI",             unit: "B USD",     color: "#14b8a6" },
  { key: "politicalRiskNews" as const, label: "Pol. Risk News",  unit: "art./mo",   color: "#ef4444" },
  { key: "tradeNewsCount"    as const, label: "Trade News",      unit: "art./mo",   color: "#8b5cf6" },
] as const;

type ChartKey = typeof CHART_TABS[number]["key"];

export default function CountryPage() {
  const { id } = useParams<{ id: string }>();
  const countryId = (id ?? "").toUpperCase();

  const country = COUNTRIES.find(c => c.id === countryId);
  if (!country) return notFound();

  const ind          = CURRENT_INDICATORS[countryId];
  const hist         = HISTORICAL[countryId];
  const news         = NEWS_EVENTS.filter(n => n.countryId === countryId);
  const alerts       = PATTERN_ALERTS.filter(a => a.countryId === countryId && a.isActive);
  const allAlerts    = PATTERN_ALERTS.filter(a => a.countryId === countryId);

  const [activeChart, setActiveChart] = useState<ChartKey>("gdpGrowth");

  // World Bank official data for this country
  const wbSummary = WB_COUNTRY_SUMMARIES[countryId] ?? {};
  const selectedTab  = CHART_TABS.find(t => t.key === activeChart)!;

  // Exports vs Imports bar data (simple two-bar comparison)
  const tradeBarData = [
    { countryId: "exports", countryName: "Exports", flagEmoji: "📤", value: ind.exports, riskLevel: "low"    as const },
    { countryId: "imports", countryName: "Imports", flagEmoji: "📥", value: ind.imports, riskLevel: "medium" as const },
  ];

  // Other countries for "switch" nav
  const otherCountries = COUNTRIES.filter(c => c.id !== countryId);

  return (
    <div className="p-7 max-w-7xl mx-auto">

      {/* ── Country header ─────────────────────────────────────── */}
      <div className="flex items-start justify-between mb-6">
        <div className="flex items-center gap-4">
          <span className="text-5xl leading-none">{country.flagEmoji}</span>
          <div>
            <div className="flex items-center gap-3 flex-wrap">
              <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
                {country.name}
              </h1>
              <RiskBadge level={country.riskLevel} />
              {alerts.length > 0 && (
                <span className="text-xs bg-red-100 text-red-700 px-2.5 py-0.5 rounded-full font-semibold">
                  ⚑ {alerts.length} active alert{alerts.length > 1 ? "s" : ""}
                </span>
              )}
            </div>
            <p className="text-slate-500 text-sm mt-1">
              {country.capital} · {country.currencyName} ({country.currency}) · {country.region}
            </p>
            <p className="text-slate-400 text-xs mt-0.5 italic">{country.riskSummary}</p>
          </div>
        </div>

        {/* Switch country */}
        <div className="flex flex-col items-end gap-2">
          <span className="text-[10px] text-slate-400 uppercase tracking-wide">Switch country</span>
          <div className="flex gap-2">
            {otherCountries.map(c => (
              <Link key={c.id} href={`/country/${c.id}`}
                className="text-2xl hover:scale-125 transition-transform" title={c.name}>
                {c.flagEmoji}
              </Link>
            ))}
          </div>
        </div>
      </div>

      {/* ── World Bank data note ─────────────────────────────── */}
      <WorldBankNote className="mb-6" />

      {/* ── World Bank Official Data ──────────────────────────── */}
      {WB_DATA_STATUS === "live" && (
        <div className="card overflow-hidden mb-7">
          <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between bg-sky-50/60">
            <div>
              <h3 className="font-semibold text-slate-900 text-sm flex items-center gap-2">
                <span>📊</span> World Bank Official Data — {countryId}
              </h3>
              <p className="text-xs text-slate-400 mt-0.5">
                8 indicators · annual · 2015–2024 · source:{" "}
                <a
                  href="https://data.worldbank.org"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sky-600 hover:underline"
                >
                  data.worldbank.org
                </a>
              </p>
            </div>
            <span className="text-[10px] text-slate-400 font-medium">
              Annual data only — not quarterly
            </span>
          </div>

          <div className="grid grid-cols-4 divide-x divide-y divide-slate-100">
            {WB_INDICATOR_KEYS.map(key => {
              const latest   = wbSummary[key];
              const indMeta  = WB_INDICATORS[key];
              const history  = getWbHistory(countryId, key);
              const prevYear = history.length >= 2 ? history[history.length - 2] : null;
              const yoyDiff  = latest && prevYear
                ? latest.value - prevYear.value
                : null;
              const isGood =
                indMeta.direction === "higher_is_better"
                  ? (yoyDiff ?? 0) >= 0
                  : (yoyDiff ?? 0) <= 0;

              return (
                <div key={key} className="px-4 py-4 hover:bg-slate-50/50 transition-colors">
                  {/* Indicator name */}
                  <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-400 mb-1">
                    {WB_INDICATOR_LABELS[key]}
                  </p>

                  {/* Value */}
                  {latest ? (
                    <>
                      <p className="text-xl font-bold text-slate-900 tabular-nums leading-tight">
                        {latest.value >= 1_000
                          ? latest.value.toLocaleString(undefined, { maximumFractionDigits: 1 })
                          : latest.value.toFixed(
                              key === "population" || key === "gdpNominal" ? 1 : 2,
                            )}
                        <span className="text-xs font-normal text-slate-400 ml-1">
                          {WB_INDICATOR_UNITS[key]}
                        </span>
                      </p>

                      {/* YoY change */}
                      {yoyDiff !== null && (
                        <p className={cn(
                          "text-xs font-medium mt-0.5",
                          isGood ? "text-emerald-600" : "text-red-500",
                        )}>
                          {yoyDiff >= 0 ? "▲" : "▼"}
                          {" "}{Math.abs(yoyDiff).toFixed(key === "population" || key === "gdpNominal" ? 1 : 2)}
                          {" "}vs {prevYear!.year}
                        </p>
                      )}

                      {/* Year + quality */}
                      <div className="flex items-center gap-1.5 mt-1.5">
                        <span className="text-[10px] text-slate-400">{latest.year}</span>
                        <span className={cn(
                          "text-[9px] font-semibold px-1.5 py-0.5 rounded-full flex items-center gap-1",
                          QUALITY_COLOR[latest.quality],
                        )}>
                          <span className={cn("w-1.5 h-1.5 rounded-full", QUALITY_DOT[latest.quality])} />
                          {QUALITY_LABEL[latest.quality]}
                        </span>
                      </div>
                    </>
                  ) : (
                    <div>
                      <p className="text-lg font-bold text-slate-300">—</p>
                      <p className="text-[10px] text-slate-400 mt-0.5">No data available</p>
                    </div>
                  )}

                  {/* Mini sparkline — last 5 values */}
                  {history.length >= 2 && (
                    <div className="mt-2 flex items-end gap-0.5 h-6">
                      {history.slice(-8).map(pt => {
                        const allVals = history.map(h => h.value);
                        const min     = Math.min(...allVals);
                        const max     = Math.max(...allVals);
                        const range   = max - min || 1;
                        const pct     = ((pt.value - min) / range) * 100;
                        return (
                          <div
                            key={pt.year}
                            title={`${pt.year}: ${pt.value.toFixed(2)} ${WB_INDICATOR_UNITS[key]}`}
                            className={cn(
                              "flex-1 rounded-sm min-h-[2px] transition-all",
                              pt.quality === "estimated" ? "opacity-50" : "opacity-90",
                              indMeta.direction === "higher_is_worse"
                                ? "bg-red-300"
                                : "bg-sky-400",
                            )}
                            style={{ height: `${Math.max(8, pct)}%` }}
                          />
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          <div className="px-5 py-2.5 bg-slate-50/50 border-t border-slate-100 flex items-center gap-3 flex-wrap">
            <span className="text-[10px] text-slate-400">WB indicator codes:</span>
            {WB_INDICATOR_KEYS.map(key => (
              <span key={key} className="text-[9px] font-mono bg-slate-100 text-slate-500 px-1.5 py-0.5 rounded">
                {WB_INDICATORS[key].wb_code}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* ── 8 Indicator cards ─────────────────────────────────── */}
      <div className="grid grid-cols-4 gap-4 mb-7">
        <IndicatorCard
          title="GDP Growth Rate"
          value={`${ind.gdpGrowth >= 0 ? "+" : ""}${ind.gdpGrowth.toFixed(1)}`}
          unit="%"
          change={getYoYChange(countryId, "gdpGrowth")}
          trend={hist.gdpGrowth}
          positive={true}
          alert={alerts.some(a => a.indicatorCode === "gdpGrowth")}
        />
        <IndicatorCard
          title="Inflation Rate (CPI)"
          value={ind.inflation.toFixed(1)}
          unit="%"
          change={getYoYChange(countryId, "inflation")}
          trend={hist.inflation}
          positive={false}
          alert={alerts.some(a => a.indicatorCode === "inflation")}
        />
        <IndicatorCard
          title="Total Exports"
          value={`$${ind.exports}`}
          unit="B USD"
          change={getYoYChange(countryId, "exports")}
          trend={hist.exports}
          positive={true}
          alert={alerts.some(a => a.indicatorCode === "exports")}
        />
        <IndicatorCard
          title="Total Imports"
          value={`$${ind.imports}`}
          unit="B USD"
          change={getYoYChange(countryId, "imports")}
          trend={hist.imports}
          positive={false}
          alert={alerts.some(a => a.indicatorCode === "imports")}
        />
        <IndicatorCard
          title="Exchange Rate"
          value={
            ind.exchangeRate >= 1000
              ? ind.exchangeRate.toLocaleString()
              : ind.exchangeRate.toFixed(2)
          }
          unit={`${country.currency}/USD`}
          change={getYoYChange(countryId, "exchangeRate")}
          trend={hist.exchangeRate}
          positive={false}
          alert={alerts.some(a => a.indicatorCode === "exchangeRate")}
        />
        <IndicatorCard
          title="FDI Net Inflows"
          value={`$${ind.fdi}`}
          unit="B USD"
          change={getYoYChange(countryId, "fdi")}
          trend={hist.fdi}
          positive={true}
          alert={alerts.some(a => a.indicatorCode === "fdi")}
        />
        <IndicatorCard
          title="Political Risk News"
          value={String(ind.politicalRiskNews)}
          unit="articles/month"
          change={getYoYChange(countryId, "politicalRiskNews")}
          trend={hist.politicalRiskNews}
          positive={false}
          alert={alerts.some(a => a.indicatorCode === "politicalRiskNews")}
        />
        <IndicatorCard
          title="Trade News Count"
          value={String(ind.tradeNewsCount)}
          unit="articles/month"
          change={getYoYChange(countryId, "tradeNewsCount")}
          trend={hist.tradeNewsCount}
          positive={true}
        />
      </div>

      {/* ── Trend chart + Trade comparison ───────────────────── */}
      <div className="grid grid-cols-5 gap-5 mb-7">

        {/* Trend chart with tab switcher */}
        <div className="col-span-3 card-p">
          <div className="flex items-start justify-between mb-3">
            <div>
              <h3 className="font-semibold text-slate-900 text-sm">5-Year Trend (2020–2024)</h3>
              <p className="text-xs text-slate-400 mt-0.5">{selectedTab.label}</p>
            </div>
          </div>

          {/* Tab buttons — 2 rows of 4 */}
          <div className="flex flex-wrap gap-1 mb-4">
            {CHART_TABS.map(tab => (
              <button
                key={tab.key}
                onClick={() => setActiveChart(tab.key)}
                className={`text-xs px-2.5 py-1 rounded-lg transition-colors ${
                  activeChart === tab.key
                    ? "bg-indigo-600 text-white font-medium"
                    : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          <TrendLineChart
            data={hist[activeChart]}
            color={selectedTab.color}
            unit={selectedTab.unit.includes("%") ? "%" : ""}
            height={200}
            showZeroLine
          />
        </div>

        {/* Exports vs Imports */}
        <div className="col-span-2 card-p">
          <h3 className="font-semibold text-slate-900 text-sm mb-1">
            Exports vs Imports — 2024
          </h3>
          <p className="text-xs text-slate-400 mb-4">
            Trade balance:{" "}
            <span className={`font-semibold ${ind.exports >= ind.imports ? "text-emerald-600" : "text-red-600"}`}>
              {ind.exports >= ind.imports ? "+" : ""}${(ind.exports - ind.imports).toFixed(1)}B
            </span>
          </p>
          <CompareBarChart
            data={tradeBarData}
            unit="B USD"
            height={160}
            colorByRisk={false}
          />

          {/* 5-year history mini table */}
          <div className="mt-4 pt-3 border-t border-slate-100">
            <p className="section-title">Annual Trend</p>
            <div className="space-y-1">
              {hist.exports.map((pt, i) => {
                const imp = hist.imports[i]?.value ?? 0;
                const bal = pt.value - imp;
                return (
                  <div key={pt.year} className="flex items-center justify-between text-xs">
                    <span className="text-slate-500 w-10">{pt.year}</span>
                    <span className="text-emerald-600 w-14 text-right">↑${pt.value}B</span>
                    <span className="text-indigo-600 w-14 text-right">↓${imp}B</span>
                    <span className={`w-16 text-right font-medium ${bal >= 0 ? "text-emerald-600" : "text-red-500"}`}>
                      {bal >= 0 ? "+" : ""}${bal.toFixed(1)}B
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      {/* ── News + Alerts ─────────────────────────────────────── */}
      <div className="grid grid-cols-5 gap-5">

        {/* News */}
        <div className="col-span-3">
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-semibold text-slate-900">
              News Events ({news.length})
            </h3>
            <Link href="/news" className="text-xs text-indigo-600 hover:underline font-medium">
              All news →
            </Link>
          </div>
          {news.length > 0
            ? <div className="flex flex-col gap-3">
                {news.map(n => <NewsCard key={n.id} event={n} />)}
              </div>
            : <div className="card-p text-center py-12 text-sm text-slate-400">
                No news events for {country.name}
              </div>
          }
        </div>

        {/* Alerts */}
        <div className="col-span-2">
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-semibold text-slate-900">
              Alerts ({allAlerts.length})
            </h3>
            <Link href="/alerts" className="text-xs text-indigo-600 hover:underline font-medium">
              All alerts →
            </Link>
          </div>
          {allAlerts.length > 0
            ? <div className="flex flex-col gap-3">
                {allAlerts.map(a => <AlertCard key={a.id} alert={a} />)}
              </div>
            : <div className="card-p text-center py-12">
                <p className="text-2xl mb-2">✓</p>
                <p className="text-sm text-slate-500">No alerts for {country.name}</p>
              </div>
          }
        </div>
      </div>
    </div>
  );
}
