"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { CURRENT_INDICATORS, PATTERN_ALERTS } from "@/data/sample-data";
import { SEA_COUNTRIES, PARTNER_COUNTRIES, type DashboardCountry } from "@/data/countries";
import DataFreshnessBar from "@/components/ui/DataFreshnessBar";

// ── Navigation items ──────────────────────────────────────────────
const NAV = [
  { href: "/",        label: "Overview",     icon: "⬡" },
  { href: "/compare", label: "Comparison",   icon: "⇌" },
  { href: "/trade",   label: "Trade Flows",  icon: "↔" },
  { href: "/news",    label: "News Feed",    icon: "◉" },
  { href: "/alerts",  label: "Alert Centre", icon: "⚑" },
];

// ── Risk dot colour ───────────────────────────────────────────────
const RISK_DOT: Record<string, string> = {
  low:      "bg-emerald-500",
  medium:   "bg-amber-400",
  high:     "bg-orange-500",
  critical: "bg-red-500",
};

const RISK_DOT_LABEL: Record<string, string> = {
  low: "Low", medium: "Medium", high: "High", critical: "Critical",
};

export default function Sidebar() {
  const path = usePathname();
  const [showPartners, setShowPartners] = useState(false);
  const [seaExpanded, setSeaExpanded]   = useState(true);

  const activeCount   = PATTERN_ALERTS.filter(a => a.isActive).length;
  const criticalCount = PATTERN_ALERTS.filter(a => a.isActive && a.severity === "critical").length;

  // Countries with full indicator data (active in dashboard)
  const activeSea     = SEA_COUNTRIES.filter(c => c.indicatorDataAvailable);
  // Remaining SEA countries — no indicator data yet
  const inactiveSea   = SEA_COUNTRIES.filter(c => !c.indicatorDataAvailable);

  return (
    <aside
      className="w-60 flex-shrink-0 flex flex-col h-screen overflow-hidden"
      style={{ backgroundColor: "#0f172a", borderRight: "1px solid #1e293b" }}
    >

      {/* ── Branding ──────────────────────────────────────────────── */}
      <div className="px-5 py-5" style={{ borderBottom: "1px solid #1e293b" }}>
        <div className="flex items-center gap-2 mb-1">
          <div className="w-7 h-7 rounded-lg bg-indigo-600 flex items-center
                          justify-center text-white text-xs font-bold">
            S
          </div>
          <p className="text-white font-bold text-sm">SEA Change</p>
        </div>
        <p className="text-slate-500 text-xs ml-9">Intelligence Dashboard · v2</p>
      </div>

      {/* ── Main navigation ───────────────────────────────────────── */}
      <nav className="px-3 pt-4">
        <p className="px-2 mb-1.5 text-[9px] font-semibold uppercase tracking-widest text-slate-600">
          Navigation
        </p>
        {NAV.map(({ href, label, icon }) => {
          const isActive  = path === href;
          const showBadge = href === "/alerts" && activeCount > 0;
          return (
            <Link key={href} href={href}
              className={cn(
                "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm mb-0.5 transition-all",
                isActive
                  ? "bg-indigo-600 text-white font-medium shadow-sm"
                  : "text-slate-400 hover:bg-slate-800 hover:text-slate-100",
              )}>
              <span className="text-base w-5 text-center leading-none shrink-0">{icon}</span>
              <span className="flex-1">{label}</span>
              {showBadge && !isActive && (
                <span className={cn(
                  "text-[10px] px-1.5 py-0.5 rounded-full font-bold",
                  criticalCount > 0 ? "bg-red-500 text-white" : "bg-amber-500 text-white",
                )}>
                  {activeCount}
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      {/* ── Country list ──────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto px-3 pt-4 pb-4"
           style={{ scrollbarWidth: "none" }}>

        {/* SEA section header */}
        <button
          onClick={() => setSeaExpanded(p => !p)}
          className="w-full flex items-center justify-between px-2 mb-1.5 group"
        >
          <p className="text-[9px] font-semibold uppercase tracking-widest text-slate-600
                        group-hover:text-slate-400 transition-colors">
            Southeast Asia ({SEA_COUNTRIES.length})
          </p>
          <span className="text-[9px] text-slate-600 group-hover:text-slate-400">
            {seaExpanded ? "▲" : "▼"}
          </span>
        </button>

        {seaExpanded && (
          <>
            {/* Active countries — have indicator data */}
            {activeSea.map(c => (
              <CountryRow key={c.iso3} country={c} path={path} />
            ))}

            {/* Inactive countries — registry only, no indicator data */}
            {inactiveSea.length > 0 && (
              <>
                <div className="mx-2 my-1.5 border-t border-dashed border-slate-800" />
                <p className="px-2 mb-1 text-[9px] text-slate-600 italic">
                  Registry only — no indicator data
                </p>
                {inactiveSea.map(c => (
                  <CountryRowInactive key={c.iso3} country={c} />
                ))}
              </>
            )}
          </>
        )}

        {/* Partner countries toggle */}
        <button
          onClick={() => setShowPartners(p => !p)}
          className="w-full flex items-center justify-between px-2 mt-4 mb-1.5 group"
        >
          <p className="text-[9px] font-semibold uppercase tracking-widest text-slate-600
                        group-hover:text-slate-400 transition-colors">
            Partner Countries ({PARTNER_COUNTRIES.length})
          </p>
          <span className="text-[9px] text-slate-600 group-hover:text-slate-400">
            {showPartners ? "▲" : "▼"}
          </span>
        </button>

        {showPartners && PARTNER_COUNTRIES.map(c => (
          <PartnerRow key={c.iso3} country={c} />
        ))}
      </div>

      {/* ── Footer — data freshness badge ────────────────────────── */}
      <div className="px-4 py-3.5" style={{ borderTop: "1px solid #1e293b" }}>
        <DataFreshnessBar />
        <p className="text-slate-700 text-[8px] mt-2 leading-relaxed">
          {activeSea.length} active · {SEA_COUNTRIES.length} SEA · {PARTNER_COUNTRIES.length} partners · 8 indicators
        </p>
      </div>
    </aside>
  );
}


// ── Active country row (links to country page) ────────────────────

function CountryRow({ country: c, path }: { country: DashboardCountry; path: string }) {
  const isActive   = path === `/country/${c.iso3}`;
  const indicators = CURRENT_INDICATORS[c.iso3];
  const alerts     = PATTERN_ALERTS.filter(a => a.countryId === c.iso3 && a.isActive).length;
  const riskLevel  = c.riskLevel ?? "low";

  return (
    <Link href={`/country/${c.iso3}`}
      className={cn(
        "flex items-center gap-2.5 px-3 py-2.5 rounded-lg mb-0.5 transition-all group",
        isActive
          ? "bg-slate-700 text-white"
          : "text-slate-400 hover:bg-slate-800 hover:text-slate-100",
      )}>
      <span className="text-base shrink-0 leading-none">{c.flagEmoji}</span>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium leading-tight truncate">{c.shortName}</p>
        {indicators && (
          <p className="text-[10px] text-slate-500 group-hover:text-slate-400">
            GDP {indicators.gdpGrowth >= 0 ? "+" : ""}{indicators.gdpGrowth.toFixed(1)}%
          </p>
        )}
      </div>
      <div className="flex items-center gap-1 shrink-0">
        {alerts > 0 && (
          <span className="text-[9px] text-slate-500 font-medium">{alerts}</span>
        )}
        <span
          className={cn("w-2 h-2 rounded-full", RISK_DOT[riskLevel])}
          title={RISK_DOT_LABEL[riskLevel]}
        />
      </div>
    </Link>
  );
}


// ── Inactive SEA country row (no link — registry only) ────────────

function CountryRowInactive({ country: c }: { country: DashboardCountry }) {
  const riskLevel = c.riskLevel ?? "medium";
  const isCritical = riskLevel === "critical";

  return (
    <div className="flex items-center gap-2.5 px-3 py-2 rounded-lg mb-0.5
                    text-slate-600 cursor-default select-none"
         title={`${c.name} — no indicator data yet`}
    >
      <span className="text-base shrink-0 leading-none opacity-70">{c.flagEmoji}</span>
      <div className="flex-1 min-w-0">
        <p className="text-xs leading-tight truncate text-slate-600">{c.shortName}</p>
        {c.aseanStatus === "candidate" && (
          <p className="text-[9px] text-amber-600/70">ASEAN candidate</p>
        )}
        {isCritical && (
          <p className="text-[9px] text-red-600/60">Critical risk</p>
        )}
      </div>
      <span className={cn("w-1.5 h-1.5 rounded-full opacity-50", RISK_DOT[riskLevel])} />
    </div>
  );
}


// ── Partner country row ───────────────────────────────────────────

function PartnerRow({ country: c }: { country: DashboardCountry }) {
  return (
    <div
      className="flex items-center gap-2.5 px-3 py-2 rounded-lg mb-0.5
                 text-slate-500 cursor-default select-none hover:bg-slate-800/50
                 transition-colors group"
      title={`${c.name} — partner country`}
    >
      <span className="text-sm shrink-0 leading-none">{c.flagEmoji}</span>
      <div className="flex-1 min-w-0">
        <p className="text-xs leading-tight truncate text-slate-500
                      group-hover:text-slate-400">
          {c.shortName}
        </p>
        <p className="text-[9px] text-slate-700">{c.regionGroup}</p>
      </div>
      {c.isBloc && (
        <span className="text-[8px] font-bold px-1 py-0.5 rounded bg-slate-700
                         text-slate-400 shrink-0">
          BLOC
        </span>
      )}
    </div>
  );
}
