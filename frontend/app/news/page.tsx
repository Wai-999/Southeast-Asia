"use client";

/**
 * app/news/page.tsx — News Impact Feed
 *
 * Real-time GDELT news signals + static sample data.
 *
 * Sources (priority order):
 *   1. GDELT Live  — news_signals.json (fetch_gdelt_news.py)
 *   2. Sample Data — NEWS_EVENTS from sample-data.ts
 *
 * Categories (13): tariff · conflict · disaster · border · protest · election
 *                  policy · trade · technology · infrastructure · economy · politics
 *
 * Filters: source · country · category · sentiment · sort
 */

import { useState, useMemo } from "react";
import { NEWS_EVENTS, type NewsEvent } from "@/data/sample-data";
import WorldBankNote from "@/components/ui/WorldBankNote";
import CountryFilter, { type FilterMode } from "@/components/ui/CountryFilter";
import { getIso3ForMode } from "@/data/countries";
import {
  NS_AS_NEWS_EVENTS, NS_META, NS_DATA_STATUS,
  NS_CATEGORY_META, NS_CATEGORY_ORDER, fmtNsGeneratedAt,
  type NsCategory,
} from "@/data/news-signals";
import type { Sentiment } from "@/lib/utils";
import { cn } from "@/lib/utils";

// ── Indicator label map ───────────────────────────────────────────────────────
const INDICATOR_LABELS: Record<string, string> = {
  gdpGrowth:         "GDP",
  inflation:         "Inflation",
  exports:           "Exports",
  imports:           "Imports",
  exchangeRate:      "FX Rate",
  fdi:               "FDI",
  politicalRiskNews: "Pol. Risk",
  tradeNewsCount:    "Trade News",
};

// ── Static "security" category display (exists in sample-data only) ───────────
const SECURITY_META = {
  label: "Security", icon: "🛡",
  color: "bg-red-100 text-red-700",
};

// ── Merge & tag sources ───────────────────────────────────────────────────────
const GDELT_TAGGED:  NewsEvent[] = NS_AS_NEWS_EVENTS;
const SAMPLE_TAGGED: NewsEvent[] = NEWS_EVENTS.map(n => ({ ...n, source: "sample" as const }));
const ALL_EVENTS:    NewsEvent[] = [...GDELT_TAGGED, ...SAMPLE_TAGGED];

// ── Helpers ───────────────────────────────────────────────────────────────────
// Country flag lookup for all 17 countries + legacy 5
const FLAG_MAP: Record<string, string> = {
  THA:"🇹🇭", VNM:"🇻🇳", MMR:"🇲🇲", KHM:"🇰🇭", SGP:"🇸🇬",
  LAO:"🇱🇦", MYS:"🇲🇾", IDN:"🇮🇩", PHL:"🇵🇭", BRN:"🇧🇳", TLS:"🇹🇱",
  CHN:"🇨🇳", USA:"🇺🇸", JPN:"🇯🇵", IND:"🇮🇳", KOR:"🇰🇷", AUS:"🇦🇺",
};
const NAME_MAP: Record<string, string> = {
  THA:"Thailand", VNM:"Vietnam", MMR:"Myanmar", KHM:"Cambodia", SGP:"Singapore",
  LAO:"Laos", MYS:"Malaysia", IDN:"Indonesia", PHL:"Philippines",
  BRN:"Brunei", TLS:"Timor-Leste", CHN:"China", USA:"United States",
  JPN:"Japan", IND:"India", KOR:"South Korea", AUS:"Australia",
};

// ─────────────────────────────────────────────────────────────────────────────
export default function NewsPage() {
  const [dataSource, setDataSource]  = useState<"all" | "gdelt" | "sample">("all");
  const [filterMode, setFilterMode]  = useState<FilterMode>("sea");
  const [customIds,  setCustomIds]   = useState<string[]>([]);
  const [category,   setCategory]    = useState("all");
  const [sentiment,  setSentiment]   = useState<Sentiment | "all">("all");
  const [sortBy,     setSortBy]      = useState<"date" | "impact">("date");

  const activeCountryIds = getIso3ForMode(filterMode, customIds);
  const isLive = NS_DATA_STATUS === "live";

  // ── Base pool by source ──────────────────────────────────────────────────
  const sourcePool = useMemo<NewsEvent[]>(() => {
    if (dataSource === "gdelt")  return GDELT_TAGGED;
    if (dataSource === "sample") return SAMPLE_TAGGED;
    return ALL_EVENTS;
  }, [dataSource]);

  // ── Apply filters ────────────────────────────────────────────────────────
  const filtered = useMemo<NewsEvent[]>(() => {
    let list = sourcePool.filter(n => activeCountryIds.has(n.countryId));
    if (category  !== "all") list = list.filter(n => n.category === category);
    if (sentiment !== "all") list = list.filter(n => n.sentiment === sentiment);
    return sortBy === "impact"
      ? [...list].sort((a, b) => b.impactLevel - a.impactLevel)
      : [...list].sort((a, b) => b.publishedAt.localeCompare(a.publishedAt));
  }, [sourcePool, activeCountryIds, category, sentiment, sortBy]);

  // ── Stats ────────────────────────────────────────────────────────────────
  const posCount = sourcePool.filter(n => n.sentiment === "positive").length;
  const negCount = sourcePool.filter(n => n.sentiment === "negative").length;
  const neuCount = sourcePool.filter(n => n.sentiment === "neutral").length;
  const impact5  = sourcePool.filter(n => n.impactLevel === 5).length;
  const impact4  = sourcePool.filter(n => n.impactLevel === 4).length;

  // Count per category from current pool
  const catCounts: Record<string, number> = {};
  for (const n of sourcePool) {
    catCounts[n.category] = (catCounts[n.category] ?? 0) + 1;
  }

  function clearFilters() {
    setFilterMode("sea"); setCustomIds([]); setCategory("all"); setSentiment("all");
  }
  const hasActiveFilters = filterMode !== "sea" || category !== "all" || sentiment !== "all";
  const generatedAt = fmtNsGeneratedAt();

  return (
    <div className="p-7 max-w-7xl mx-auto">

      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <div className="flex items-start justify-between mb-5">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
            News Impact Feed
          </h1>
          <p className="text-slate-500 text-sm mt-0.5">
            {sourcePool.length} signals ·{" "}
            {isLive
              ? <>
                  <span className="text-emerald-600 font-medium">GDELT live</span>
                  {" "}· {NS_META.days_back} days · {NS_META.start_date} → {NS_META.end_date}
                  {generatedAt && (
                    <span className="text-indigo-500"> · fetched {generatedAt}</span>
                  )}
                </>
              : <span className="text-amber-600">sample data · run fetch_gdelt_news.py</span>
            }
          </p>
        </div>

        {/* Sentiment + impact pills */}
        <div className="flex flex-col items-end gap-1.5 text-xs mt-1">
          <div className="flex items-center gap-3">
            <span className="flex items-center gap-1 text-emerald-600 font-medium">
              <span className="w-2 h-2 rounded-full bg-emerald-500" />{posCount} Positive
            </span>
            <span className="flex items-center gap-1 text-slate-500">
              <span className="w-2 h-2 rounded-full bg-slate-400" />{neuCount} Neutral
            </span>
            <span className="flex items-center gap-1 text-red-600 font-medium">
              <span className="w-2 h-2 rounded-full bg-red-500" />{negCount} Negative
            </span>
          </div>
          {(impact5 + impact4) > 0 && (
            <div className="flex items-center gap-2">
              {impact5 > 0 && (
                <span className="flex items-center gap-1 text-red-700 font-semibold bg-red-50 px-2 py-0.5 rounded-full border border-red-200">
                  🔴 {impact5} Critical (impact 5)
                </span>
              )}
              {impact4 > 0 && (
                <span className="flex items-center gap-1 text-orange-700 font-semibold bg-orange-50 px-2 py-0.5 rounded-full border border-orange-200">
                  🟠 {impact4} High (impact 4)
                </span>
              )}
            </div>
          )}
        </div>
      </div>

      {/* ── Data note ──────────────────────────────────────────────────────── */}
      <WorldBankNote className="mb-5" />

      {/* ── Source toggle ──────────────────────────────────────────────────── */}
      <div className="flex items-center gap-2 mb-5">
        <span className="text-[10px] font-semibold uppercase tracking-widest text-slate-400 mr-1">
          Source
        </span>
        {(["all", "gdelt", "sample"] as const).map(s => (
          <button
            key={s}
            onClick={() => setDataSource(s)}
            className={cn(
              "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs border transition-colors font-medium",
              dataSource === s
                ? "bg-slate-800 text-white border-slate-800"
                : "border-slate-200 text-slate-600 bg-white hover:bg-slate-50",
            )}
          >
            {s === "all"    && "◈  All Sources"}
            {s === "gdelt"  && (
              <>
                <span className={cn(
                  "w-1.5 h-1.5 rounded-full",
                  isLive ? "bg-emerald-400 animate-pulse" : "bg-slate-300",
                )} />
                GDELT Live
                {isLive
                  ? (
                    <span className={cn(
                      "px-1.5 py-0.5 rounded-full text-[10px] font-bold",
                      dataSource === "gdelt" ? "bg-white/20 text-white" : "bg-emerald-100 text-emerald-700",
                    )}>
                      {GDELT_TAGGED.length}
                    </span>
                  )
                  : <span className="text-[10px] text-slate-400">(not fetched)</span>
                }
              </>
            )}
            {s === "sample" && (
              <>
                📋 Sample
                <span className={cn(
                  "px-1.5 py-0.5 rounded-full text-[10px] font-bold",
                  dataSource === "sample" ? "bg-white/20 text-white" : "bg-slate-100 text-slate-500",
                )}>
                  {SAMPLE_TAGGED.length}
                </span>
              </>
            )}
          </button>
        ))}

        {!isLive && (
          <span className="text-xs text-amber-600 ml-2 flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
            Run{" "}
            <code className="bg-slate-100 px-1.5 py-0.5 rounded text-slate-600 font-mono text-[11px]">
              python pipeline/fetch_gdelt_news.py
            </code>{" "}
            to load real-time GDELT data
          </span>
        )}
      </div>

      {/* ── Category chips (13 categories) ────────────────────────────────── */}
      <div className="flex gap-1.5 mb-5 flex-wrap">
        {/* All chip */}
        <button
          onClick={() => setCategory("all")}
          className={cn(
            "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs border transition-colors",
            category === "all"
              ? "bg-slate-800 text-white border-slate-800"
              : "border-slate-200 text-slate-600 bg-white hover:bg-slate-50",
          )}
        >
          <span>◉</span>
          <span className="font-medium">All</span>
          <span className={cn(
            "px-1.5 py-0.5 rounded-full text-[10px] font-bold",
            category === "all" ? "bg-white/20 text-white" : "bg-slate-100 text-slate-500",
          )}>
            {sourcePool.length}
          </span>
        </button>

        {/* GDELT categories (priority order) */}
        {NS_CATEGORY_ORDER.map(cat => {
          const count = catCounts[cat] ?? 0;
          const meta  = NS_CATEGORY_META[cat];
          const isActive = category === cat;
          return (
            <button
              key={cat}
              onClick={() => setCategory(category === cat ? "all" : cat)}
              className={cn(
                "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs border transition-colors",
                isActive
                  ? "bg-slate-800 text-white border-slate-800"
                  : "border-slate-200 text-slate-600 bg-white hover:bg-slate-50",
                count === 0 && !isActive && "opacity-40",
              )}
            >
              <span>{meta.icon}</span>
              <span className="font-medium">{meta.label}</span>
              {count > 0 && (
                <span className={cn(
                  "px-1.5 py-0.5 rounded-full text-[10px] font-bold",
                  isActive ? "bg-white/20 text-white" : "bg-slate-100 text-slate-500",
                )}>
                  {count}
                </span>
              )}
            </button>
          );
        })}

        {/* "Security" chip — only for sample data */}
        {(catCounts["security"] ?? 0) > 0 && (
          <button
            onClick={() => setCategory(category === "security" ? "all" : "security")}
            className={cn(
              "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs border transition-colors",
              category === "security"
                ? "bg-slate-800 text-white border-slate-800"
                : "border-slate-200 text-slate-600 bg-white hover:bg-slate-50",
            )}
          >
            <span>{SECURITY_META.icon}</span>
            <span className="font-medium">{SECURITY_META.label}</span>
            <span className={cn(
              "px-1.5 py-0.5 rounded-full text-[10px] font-bold",
              category === "security" ? "bg-white/20 text-white" : "bg-slate-100 text-slate-500",
            )}>
              {catCounts["security"]}
            </span>
          </button>
        )}
      </div>

      {/* ── Filters bar ────────────────────────────────────────────────────── */}
      <div className="card-p mb-5 flex flex-wrap gap-6 items-start">

        {/* Country filter */}
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-400 mb-2">
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

        {/* Sentiment */}
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-400 mb-2">
            Sentiment
          </p>
          <div className="flex gap-1.5">
            {([
              { v: "all",      l: "All",        c: "text-slate-500" },
              { v: "positive", l: "↑ Positive", c: "text-emerald-600" },
              { v: "neutral",  l: "→ Neutral",  c: "text-slate-500" },
              { v: "negative", l: "↓ Negative", c: "text-red-600" },
            ] as const).map(s => (
              <button
                key={s.v}
                onClick={() => setSentiment(s.v as Sentiment | "all")}
                className={cn(
                  "text-xs px-3 py-1.5 rounded-lg border transition-colors",
                  sentiment === s.v
                    ? "bg-slate-800 text-white border-slate-800"
                    : `border-slate-200 bg-white hover:bg-slate-50 ${s.c}`,
                )}
              >
                {s.l}
              </button>
            ))}
          </div>
        </div>

        {/* Sort */}
        <div className="ml-auto">
          <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-400 mb-2">
            Sort By
          </p>
          <div className="flex gap-1.5">
            {(["date", "impact"] as const).map(s => (
              <button
                key={s}
                onClick={() => setSortBy(s)}
                className={cn(
                  "text-xs px-3 py-1.5 rounded-lg border transition-colors",
                  sortBy === s
                    ? "bg-indigo-600 text-white border-indigo-600"
                    : "border-slate-200 text-slate-600 bg-white hover:bg-slate-50",
                )}
              >
                {s === "date" ? "Latest First" : "Highest Impact"}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* ── Results count + clear ──────────────────────────────────────────── */}
      <div className="flex items-center justify-between mb-4">
        <p className="text-xs text-slate-400">
          {filtered.length} signal{filtered.length !== 1 ? "s" : ""} matching filters
          {hasActiveFilters && " — "}
          {[
            filterMode !== "sea" ? filterMode.toUpperCase() : null,
            category   !== "all" ? category   : null,
            sentiment  !== "all" ? sentiment  : null,
          ].filter(Boolean).join(" · ")}
        </p>
        {hasActiveFilters && (
          <button
            onClick={clearFilters}
            className="text-xs text-indigo-600 hover:underline font-medium"
          >
            Clear filters ×
          </button>
        )}
      </div>

      {/* ── News grid ──────────────────────────────────────────────────────── */}
      {filtered.length > 0 ? (
        <div className="grid grid-cols-2 gap-4">
          {filtered.map(n => <NewsCardExtended key={n.id} event={n} />)}
        </div>
      ) : (
        <div className="card-p text-center py-24">
          <p className="text-4xl mb-3">◎</p>
          <p className="text-slate-600 font-medium">No signals match your filters</p>
          <p className="text-sm text-slate-400 mt-1">
            {!isLive
              ? "Run fetch_gdelt_news.py to load real-time GDELT data"
              : "Try adjusting the country or category filters"}
          </p>
          <button
            onClick={clearFilters}
            className="mt-4 text-xs text-indigo-600 hover:underline font-medium"
          >
            Reset all filters
          </button>
        </div>
      )}
    </div>
  );
}


// ── Extended news card ────────────────────────────────────────────────────────

function NewsCardExtended({ event: n }: { event: NewsEvent }) {
  const isGdelt = n.source === "gdelt";
  const category = n.category as string;

  // Category metadata — check GDELT map first, then legacy
  const catMeta = NS_CATEGORY_META[category as NsCategory] ?? {
    label: category.charAt(0).toUpperCase() + category.slice(1),
    icon:  "◈",
    color: "bg-slate-100 text-slate-600",
  };

  const borderColor =
    n.sentiment === "positive" ? "border-l-emerald-400"
    : n.sentiment === "negative" ? "border-l-red-400"
    : "border-l-slate-300";

  const impactColor =
    n.impactLevel >= 5 ? "bg-red-500"
    : n.impactLevel >= 4 ? "bg-orange-500"
    : n.impactLevel >= 3 ? "bg-amber-500"
    : "bg-blue-400";

  return (
    <div className={cn(
      "card border-l-4 p-4 flex flex-col gap-2 hover:shadow-md transition-shadow",
      borderColor,
    )}>

      {/* Top row: flag · source domain · category badge · GDELT tag */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 text-xs text-slate-500 min-w-0">
          <span className="text-base shrink-0">
            {FLAG_MAP[n.countryId] ?? "🌐"}
          </span>
          <span className="font-medium text-slate-700 shrink-0">
            {NAME_MAP[n.countryId] ?? n.countryId}
          </span>
          <span className="text-slate-300">·</span>
          <span className="truncate max-w-[130px] text-slate-400">
            {n.sourceName}
          </span>
        </div>

        <div className="flex items-center gap-1.5 shrink-0">
          {isGdelt && (
            <span className="text-[9px] font-bold px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-700 uppercase tracking-wide">
              LIVE
            </span>
          )}
          {/* Category chip */}
          <span className={cn(
            "text-[10px] font-semibold px-2 py-0.5 rounded-full flex items-center gap-1",
            catMeta.color,
          )}>
            <span>{catMeta.icon}</span>
            {catMeta.label}
          </span>
        </div>
      </div>

      {/* Headline — clickable for GDELT, plain for sample */}
      <h4 className="font-semibold text-slate-900 text-sm leading-snug">
        {isGdelt && n.gdeltUrl ? (
          <a
            href={n.gdeltUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="hover:text-indigo-700 hover:underline transition-colors"
          >
            {n.headline}
          </a>
        ) : (
          n.headline
        )}
      </h4>

      {/* Summary (sample data only has a summary; GDELT repeats title) */}
      {n.summary !== n.headline && (
        <p className="text-xs text-slate-500 leading-relaxed line-clamp-2">
          {n.summary}
        </p>
      )}

      {/* Connected indicators */}
      {n.impactedIndicators.length > 0 && (
        <div className="flex flex-wrap gap-1 items-center">
          <span className="text-[10px] text-slate-400 mr-0.5">Affects:</span>
          {n.impactedIndicators.slice(0, 5).map(ind => (
            <span
              key={ind}
              className="text-[10px] px-1.5 py-0.5 bg-slate-100 text-slate-600 rounded font-medium"
            >
              {INDICATOR_LABELS[ind] ?? ind}
            </span>
          ))}
        </div>
      )}

      {/* Footer: sentiment · date · impact dots */}
      <div className="flex items-center justify-between mt-auto pt-1.5 border-t border-slate-50">
        <div className="flex items-center gap-2">
          <SentimentPill sentiment={n.sentiment} />
          <span className="text-[10px] text-slate-400">{n.publishedAt}</span>
        </div>

        <div className="flex items-center gap-1">
          <span className="text-[10px] text-slate-400 mr-0.5">Impact</span>
          {[1,2,3,4,5].map(i => (
            <span
              key={i}
              className={cn(
                "w-2 h-2 rounded-full transition-colors",
                i <= n.impactLevel ? impactColor : "bg-slate-200",
              )}
            />
          ))}
          <span className={cn(
            "ml-1 text-[10px] font-bold",
            n.impactLevel >= 5 ? "text-red-600"
            : n.impactLevel >= 4 ? "text-orange-600"
            : n.impactLevel >= 3 ? "text-amber-600"
            : "text-slate-400",
          )}>
            {n.impactLevel}
          </span>
        </div>
      </div>
    </div>
  );
}

// ── Mini sub-components ───────────────────────────────────────────────────────

function SentimentPill({ sentiment }: { sentiment: string }) {
  const cfg = {
    positive: { label: "↑ Positive", cls: "bg-emerald-50 text-emerald-700" },
    negative: { label: "↓ Negative", cls: "bg-red-50 text-red-700" },
    neutral:  { label: "→ Neutral",  cls: "bg-slate-100 text-slate-500" },
  }[sentiment] ?? { label: sentiment, cls: "bg-slate-100 text-slate-500" };

  return (
    <span className={cn("text-[10px] font-medium px-1.5 py-0.5 rounded", cfg.cls)}>
      {cfg.label}
    </span>
  );
}
