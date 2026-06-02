/**
 * frontend/components/ui/WorldBankNote.tsx
 * ────────────────────────────────────────
 * Reusable banner explaining the World Bank data limitations:
 *   - Annual data only (no quarterly)
 *   - 1–2 year publication lag
 *   - Data quality flags
 *
 * USAGE
 * ─────
 *   <WorldBankNote />               — default compact inline note
 *   <WorldBankNote expanded />      — full explanation with all caveats
 *   <WorldBankNote generatedAt="2026-06-02T10:00:00" />
 */

"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import { WB_META, WB_DATA_STATUS, QUALITY_DOT, QUALITY_LABEL } from "@/data/worldbank-data";
import type { WbDataQuality } from "@/data/worldbank-data";

interface WorldBankNoteProps {
  /** Show the full caveat list (default: false — compact one-liner) */
  expanded?:    boolean;
  /** Override the generated-at timestamp string */
  generatedAt?: string;
  className?:   string;
}

const QUALITY_ITEMS: { quality: WbDataQuality; desc: string }[] = [
  { quality: "available",  desc: "Real World Bank data, recently published" },
  { quality: "estimated",  desc: "Gap-filled from adjacent years (forward/backward fill, max 2 years)" },
  { quality: "old_data",   desc: "Real WB data, but most recent year for this series is 2+ years old" },
  { quality: "missing",    desc: "No data available — too large a gap to fill safely" },
];

export default function WorldBankNote({
  expanded    = false,
  generatedAt,
  className,
}: WorldBankNoteProps) {
  const [open, setOpen] = useState(expanded);

  const ts     = generatedAt ?? WB_META.generated_at;
  const isLive = WB_DATA_STATUS === "live";

  // Format timestamp: "2026-06-02T10:00:00" → "2 Jun 2026"
  let dateLabel = ts;
  if (ts && ts !== "placeholder") {
    try {
      dateLabel = new Date(ts).toLocaleDateString("en-GB", {
        day: "numeric", month: "short", year: "numeric",
      });
    } catch {
      dateLabel = ts;
    }
  }

  return (
    <div className={cn(
      "rounded-lg border text-xs",
      isLive
        ? "bg-sky-50 border-sky-200 text-sky-800"
        : "bg-amber-50 border-amber-200 text-amber-800",
      className,
    )}>

      {/* ── Compact header row ───────────────────────────── */}
      <div className="flex items-center gap-2 px-3 py-2">
        <span className="text-sm shrink-0">{isLive ? "📊" : "⚠️"}</span>

        <div className="flex-1 min-w-0">
          {isLive ? (
            <span>
              <span className="font-semibold">World Bank Open Data</span>
              {" · "}Annual data only — not real-time or quarterly
              {ts !== "placeholder" && (
                <span className="text-sky-500 ml-1">· fetched {dateLabel}</span>
              )}
            </span>
          ) : (
            <span>
              <span className="font-semibold">Sample data</span>
              {" — "}run{" "}
              <code className="font-mono bg-amber-100 px-1 rounded">
                python pipeline/fetch_worldbank.py
              </code>
              {" "}to load real World Bank data
            </span>
          )}
        </div>

        <button
          onClick={() => setOpen(p => !p)}
          className={cn(
            "shrink-0 text-[10px] font-semibold px-2 py-0.5 rounded border transition-colors",
            isLive
              ? "border-sky-300 text-sky-700 hover:bg-sky-100"
              : "border-amber-300 text-amber-700 hover:bg-amber-100",
          )}
        >
          {open ? "Less" : "Details"}
        </button>
      </div>

      {/* ── Expanded detail panel ────────────────────────── */}
      {open && (
        <div className={cn(
          "px-3 pb-3 pt-1 border-t",
          isLive ? "border-sky-200" : "border-amber-200",
        )}>

          {/* Caveat bullets */}
          <div className="space-y-1.5 mb-3">
            <p className="font-semibold text-[11px] uppercase tracking-wide opacity-70 mb-1">
              Limitations
            </p>
            {[
              "Annual data only — World Bank does not publish quarterly GDP, CPI, or trade.",
              `Publication lag: in ${new Date().getFullYear()}, most confirmed data is up to ${new Date().getFullYear() - 2} or ${new Date().getFullYear() - 1}.`,
              "Myanmar post-2022: post-coup disruption, estimates only.",
              "Timor-Leste: limited statistical capacity, significant data gaps.",
              "FDI (% of GDP): negative values = net capital outflow — this is valid.",
              "Exports/imports/GDP nominal: current USD — affected by dollar inflation over time.",
            ].map((line, i) => (
              <div key={i} className="flex items-start gap-1.5">
                <span className="opacity-40 mt-0.5">•</span>
                <span>{line}</span>
              </div>
            ))}
          </div>

          {/* Quality flag legend */}
          <p className="font-semibold text-[11px] uppercase tracking-wide opacity-70 mb-1.5">
            Data Quality Flags
          </p>
          <div className="grid grid-cols-2 gap-x-4 gap-y-1">
            {QUALITY_ITEMS.map(({ quality, desc }) => (
              <div key={quality} className="flex items-start gap-1.5">
                <span className={cn("w-2 h-2 rounded-full shrink-0 mt-0.5", QUALITY_DOT[quality])} />
                <span>
                  <span className="font-semibold">{QUALITY_LABEL[quality]}</span>
                  {" — "}{desc}
                </span>
              </div>
            ))}
          </div>

          {/* For quarterly data */}
          <p className="mt-2.5 opacity-60">
            For quarterly series:{" "}
            <span className="font-medium">NESDC</span> (Thailand) ·{" "}
            <span className="font-medium">GSO</span> (Vietnam) ·{" "}
            <span className="font-medium">SingStat</span> (Singapore) ·{" "}
            <span className="font-medium">BPS</span> (Indonesia) ·{" "}
            <span className="font-medium">DOSM</span> (Malaysia)
          </p>
        </div>
      )}
    </div>
  );
}
