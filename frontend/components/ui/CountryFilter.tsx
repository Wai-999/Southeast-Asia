"use client";

/**
 * frontend/components/ui/CountryFilter.tsx
 *
 * Reusable country filter with 4 modes:
 *   1. SEA Only      — All 11 Southeast Asian countries
 *   2. Partners      — All 7 partner/external entities
 *   3. All Countries — All 18 entries
 *   4. Custom        — Multi-select checkbox panel
 *
 * USAGE
 * ─────
 *   import CountryFilter from "@/components/ui/CountryFilter";
 *
 *   const [mode, setMode] = useState<FilterMode>("sea");
 *   const [custom, setCustom] = useState<string[]>([]);
 *   const activeIds = getIso3ForMode(mode, custom);
 *
 *   <CountryFilter
 *     mode={mode}
 *     onModeChange={setMode}
 *     customSelection={custom}
 *     onCustomChange={setCustom}
 *   />
 *
 * PROPS
 * ─────
 *   mode              – current filter mode
 *   onModeChange      – called when user clicks a mode button
 *   customSelection   – ISO3 array for custom mode
 *   onCustomChange    – called when checkboxes change in custom panel
 *   showActiveOnly    – if true, show "(data)" badge next to countries with indicator data
 *   compact           – if true, hide descriptions, smaller padding
 *   className         – additional class on the root element
 */

import { useState, useRef, useEffect } from "react";
import { cn } from "@/lib/utils";
import {
  SEA_COUNTRIES,
  PARTNER_COUNTRIES,
  ALL_COUNTRIES,
  MAINLAND_SEA,
  MARITIME_SEA,
  ASEAN_STATUS_LABEL,
  type DashboardCountry,
} from "@/data/countries";

// ── Types ─────────────────────────────────────────────────────────────────────

export type FilterMode = "sea" | "partners" | "all" | "custom";

interface CountryFilterProps {
  mode:              FilterMode;
  onModeChange:      (mode: FilterMode) => void;
  customSelection:   string[];   // ISO3 codes
  onCustomChange:    (ids: string[]) => void;
  showActiveOnly?:   boolean;
  compact?:          boolean;
  className?:        string;
}

// ── Mode button definitions ───────────────────────────────────────────────────

const MODE_BUTTONS: Array<{
  mode:    FilterMode;
  label:   string;
  icon:    string;
  count:   number;
  description: string;
}> = [
  {
    mode: "sea",
    label: "SEA Only",
    icon: "🌏",
    count: SEA_COUNTRIES.length,
    description: "All 11 Southeast Asian countries",
  },
  {
    mode: "partners",
    label: "Partners",
    icon: "🤝",
    count: PARTNER_COUNTRIES.length,
    description: "China, US, Japan, India, South Korea, Australia, EU",
  },
  {
    mode: "all",
    label: "All Countries",
    icon: "◎",
    count: ALL_COUNTRIES.length,
    description: "Full 18-country + partner registry",
  },
  {
    mode: "custom",
    label: "Custom",
    icon: "⊞",
    count: 0,   // set dynamically from customSelection.length
    description: "Pick any combination",
  },
];

// ── Sub-section definitions for the custom panel ──────────────────────────────

const CUSTOM_SECTIONS: Array<{
  title:     string;
  subtitle:  string;
  countries: DashboardCountry[];
}> = [
  {
    title:    "Mainland Southeast Asia",
    subtitle: "Thailand · Vietnam · Myanmar · Cambodia · Laos",
    countries: MAINLAND_SEA,
  },
  {
    title:    "Maritime Southeast Asia",
    subtitle: "Singapore · Indonesia · Malaysia · Philippines · Brunei · Timor-Leste",
    countries: MARITIME_SEA,
  },
  {
    title:    "Partner Countries & Blocs",
    subtitle: "China · United States · Japan · India · South Korea · Australia · EU",
    countries: PARTNER_COUNTRIES,
  },
];

// ── Active-data indicator ISO3 set ────────────────────────────────────────────
const ACTIVE_DATA_SET = new Set(
  ALL_COUNTRIES.filter(c => c.indicatorDataAvailable).map(c => c.iso3)
);

// ─────────────────────────────────────────────────────────────────────────────

export default function CountryFilter({
  mode,
  onModeChange,
  customSelection,
  onCustomChange,
  showActiveOnly = false,
  compact        = false,
  className,
}: CountryFilterProps) {

  const [customOpen, setCustomOpen] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);

  // Close custom panel on outside click
  useEffect(() => {
    if (!customOpen) return;
    function handleClick(e: MouseEvent) {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        setCustomOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [customOpen]);

  function handleModeClick(m: FilterMode) {
    onModeChange(m);
    if (m === "custom") setCustomOpen(prev => !prev);
    else                setCustomOpen(false);
  }

  function toggleCountry(iso3: string) {
    const next = customSelection.includes(iso3)
      ? customSelection.filter(id => id !== iso3)
      : [...customSelection, iso3];
    onCustomChange(next);
  }

  function toggleSection(countries: DashboardCountry[]) {
    const ids   = countries.map(c => c.iso3);
    const allOn = ids.every(id => customSelection.includes(id));
    if (allOn) {
      onCustomChange(customSelection.filter(id => !ids.includes(id)));
    } else {
      const added = new Set([...customSelection, ...ids]);
      onCustomChange([...added]);
    }
  }

  function selectAll()   { onCustomChange(ALL_COUNTRIES.map(c => c.iso3)); }
  function clearAll()    { onCustomChange([]); }

  const customCount = customSelection.length;

  return (
    <div className={cn("relative", className)} ref={panelRef}>

      {/* ── Mode buttons ─────────────────────────────────────────────────── */}
      <div className={cn("flex flex-wrap gap-1.5", compact ? "gap-1" : "gap-1.5")}>
        {MODE_BUTTONS.map(btn => {
          const isActive  = mode === btn.mode;
          const count     = btn.mode === "custom" ? customCount : btn.count;
          const showDot   = btn.mode === "custom" && customCount > 0 && mode !== "custom";

          return (
            <button
              key={btn.mode}
              onClick={() => handleModeClick(btn.mode)}
              title={btn.description}
              className={cn(
                "flex items-center gap-1.5 rounded-lg border text-xs font-medium transition-all",
                compact ? "px-2.5 py-1" : "px-3 py-1.5",
                isActive
                  ? "bg-slate-800 text-white border-slate-800 shadow-sm"
                  : "bg-white border-slate-200 text-slate-600 hover:bg-slate-50 hover:border-slate-300",
              )}
            >
              <span>{btn.icon}</span>
              <span>{btn.label}</span>
              <span className={cn(
                "px-1.5 py-0.5 rounded-full text-[10px] font-bold tabular-nums",
                isActive ? "bg-white/20 text-white" : "bg-slate-100 text-slate-500",
              )}>
                {count}
              </span>
              {showDot && (
                <span className="w-1.5 h-1.5 rounded-full bg-indigo-500 shrink-0" />
              )}
            </button>
          );
        })}
      </div>

      {/* ── Custom selection panel ────────────────────────────────────────── */}
      {mode === "custom" && customOpen && (
        <div className="absolute top-full left-0 mt-2 z-50 w-[520px] max-w-[95vw]
                        bg-white border border-slate-200 rounded-xl shadow-xl overflow-hidden">

          {/* Panel header */}
          <div className="flex items-center justify-between px-4 py-3
                          bg-slate-50 border-b border-slate-200">
            <div>
              <p className="text-xs font-semibold text-slate-800">
                Custom country selection
              </p>
              <p className="text-[10px] text-slate-500 mt-0.5">
                {customCount === 0
                  ? "No countries selected"
                  : `${customCount} countr${customCount === 1 ? "y" : "ies"} selected`}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={selectAll}
                className="text-[11px] text-indigo-600 hover:underline font-medium"
              >
                Select all
              </button>
              <span className="text-slate-300">|</span>
              <button
                onClick={clearAll}
                className="text-[11px] text-slate-500 hover:underline"
              >
                Clear
              </button>
              <button
                onClick={() => setCustomOpen(false)}
                className="text-slate-400 hover:text-slate-600 text-sm ml-1"
              >
                ✕
              </button>
            </div>
          </div>

          {/* Country sections */}
          <div className="max-h-[420px] overflow-y-auto divide-y divide-slate-100">
            {CUSTOM_SECTIONS.map(section => {
              const sectionIds  = section.countries.map(c => c.iso3);
              const allChecked  = sectionIds.every(id => customSelection.includes(id));
              const someChecked = sectionIds.some(id => customSelection.includes(id));

              return (
                <div key={section.title} className="px-4 py-3">
                  {/* Section header */}
                  <div className="flex items-center justify-between mb-2">
                    <div>
                      <p className="text-[11px] font-semibold text-slate-700">
                        {section.title}
                      </p>
                      <p className="text-[10px] text-slate-400">{section.subtitle}</p>
                    </div>
                    <button
                      onClick={() => toggleSection(section.countries)}
                      className={cn(
                        "text-[10px] font-medium px-2 py-0.5 rounded border transition-colors",
                        allChecked
                          ? "bg-slate-800 text-white border-slate-800"
                          : someChecked
                          ? "bg-indigo-50 text-indigo-700 border-indigo-200"
                          : "bg-white text-slate-500 border-slate-200 hover:bg-slate-50",
                      )}
                    >
                      {allChecked ? "✓ All" : someChecked ? "Some" : "Select all"}
                    </button>
                  </div>

                  {/* Country checkboxes */}
                  <div className="grid grid-cols-3 gap-1">
                    {section.countries.map(c => {
                      const checked  = customSelection.includes(c.iso3);
                      const hasData  = ACTIVE_DATA_SET.has(c.iso3);
                      const isCandidate = c.aseanStatus === "candidate";

                      return (
                        <button
                          key={c.iso3}
                          onClick={() => toggleCountry(c.iso3)}
                          className={cn(
                            "flex items-center gap-1.5 px-2 py-1.5 rounded-lg text-left",
                            "text-xs border transition-all",
                            checked
                              ? "bg-indigo-600 text-white border-indigo-600"
                              : "bg-white border-slate-200 text-slate-700 hover:bg-slate-50 hover:border-slate-300",
                          )}
                        >
                          {/* Checkbox indicator */}
                          <span className={cn(
                            "w-3.5 h-3.5 rounded border flex items-center justify-center shrink-0",
                            checked
                              ? "bg-white/20 border-white/50 text-white"
                              : "border-slate-300",
                          )}>
                            {checked && <span className="text-[8px] font-bold">✓</span>}
                          </span>

                          <span className="text-sm shrink-0">{c.flagEmoji}</span>

                          <span className="min-w-0 truncate font-medium">
                            {c.shortName}
                          </span>

                          {/* Badges */}
                          {showActiveOnly && hasData && (
                            <span className={cn(
                              "shrink-0 text-[8px] font-bold px-1 rounded ml-auto",
                              checked ? "bg-white/20 text-white" : "bg-blue-100 text-blue-700",
                            )}>
                              data
                            </span>
                          )}
                          {isCandidate && (
                            <span className={cn(
                              "shrink-0 text-[8px] font-bold px-1 rounded ml-auto",
                              checked ? "bg-white/20 text-white" : "bg-amber-100 text-amber-700",
                            )}>
                              cand.
                            </span>
                          )}
                        </button>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Panel footer */}
          {customCount > 0 && (
            <div className="px-4 py-2.5 bg-indigo-50 border-t border-indigo-100
                            flex items-center gap-2 flex-wrap">
              <span className="text-[10px] text-indigo-700 font-medium shrink-0">
                Selected:
              </span>
              {customSelection.slice(0, 12).map(iso3 => {
                const c = ALL_COUNTRIES.find(x => x.iso3 === iso3);
                return c ? (
                  <span key={iso3} className="text-sm" title={c.shortName}>
                    {c.flagEmoji}
                  </span>
                ) : null;
              })}
              {customSelection.length > 12 && (
                <span className="text-[10px] text-indigo-500">
                  +{customSelection.length - 12} more
                </span>
              )}
              <button
                onClick={() => setCustomOpen(false)}
                className="ml-auto text-[11px] font-semibold text-white
                           bg-indigo-600 hover:bg-indigo-700 px-2.5 py-1 rounded-lg"
              >
                Apply ✓
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}


// ─────────────────────────────────────────────────────────────────────────────
// UTILITY: compact country chips (used in filter result summary bars)
// ─────────────────────────────────────────────────────────────────────────────

interface CountryChipProps {
  iso3:      string;
  size?:     "xs" | "sm";
  showName?: boolean;
  onRemove?: () => void;
}

export function CountryChip({ iso3, size = "sm", showName = false, onRemove }: CountryChipProps) {
  const c = ALL_COUNTRIES.find(x => x.iso3 === iso3);
  if (!c) return null;

  return (
    <span className={cn(
      "inline-flex items-center gap-1 rounded-full bg-slate-100 text-slate-700",
      size === "xs" ? "px-1.5 py-0.5 text-[10px]" : "px-2 py-0.5 text-xs",
    )}>
      <span>{c.flagEmoji}</span>
      {showName && <span className="font-medium">{c.shortName}</span>}
      {onRemove && (
        <button
          onClick={onRemove}
          className="text-slate-400 hover:text-slate-700 ml-0.5"
        >
          ×
        </button>
      )}
    </span>
  );
}
