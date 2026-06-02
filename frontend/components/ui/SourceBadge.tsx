"use client";

/**
 * SourceBadge — inline clickable chip that reveals a full source-details panel.
 *
 * Usage in any card:
 *   <SourceBadge meta={mySourceMeta} />
 *   <SourceBadge meta={mySourceMeta} align="right" />
 *
 * The chip shows:   [●] Source name · Frequency
 * The panel shows:  all 7 SourceMeta fields + a link to the source URL.
 *
 * Self-contained "use client" — parent cards do NOT need to be client components.
 */

import { useState, useRef, useEffect } from "react";
import { cn } from "@/lib/utils";
import {
  type SourceMeta,
  CONF_DOT,
  CONF_TEXT,
  CONF_LABEL,
  CONF_DESC,
  QUALITY_STYLE,
  FREQ_LABEL,
  fmtFetchedAt,
} from "@/lib/source-meta";


// ── Props ─────────────────────────────────────────────────────────────────────

interface Props {
  meta:       SourceMeta;
  /** "left" (default) or "right" — which side the details panel opens on */
  align?:     "left" | "right";
  className?: string;
}


// ── Component ─────────────────────────────────────────────────────────────────

export default function SourceBadge({ meta, align = "left", className }: Props) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  // Close when clicking outside
  useEffect(() => {
    if (!open) return;
    function handler(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const qualityStyle = QUALITY_STYLE[meta.data_quality];

  return (
    <div ref={rootRef} className={cn("relative", className)}>

      {/* ── Trigger chip ──────────────────────────────────────────────── */}
      <button
        type="button"
        onClick={() => setOpen(v => !v)}
        className={cn(
          "flex items-center gap-1 text-[10px] text-slate-400",
          "hover:text-slate-600 transition-colors select-none",
          open && "text-slate-600",
        )}
        aria-expanded={open}
        aria-label={`Source details for ${meta.source}`}
      >
        {/* Confidence dot */}
        <span className={cn("w-1.5 h-1.5 rounded-full flex-shrink-0", CONF_DOT[meta.confidence])} />
        {/* Source name */}
        <span className="font-medium truncate max-w-[140px]">{meta.source}</span>
        {/* Frequency */}
        <span className="text-slate-300">·</span>
        <span>{FREQ_LABEL[meta.frequency]}</span>
        {/* Toggle caret */}
        <svg
          className={cn("w-2.5 h-2.5 flex-shrink-0 transition-transform", open && "rotate-180")}
          viewBox="0 0 10 6" fill="none" stroke="currentColor" strokeWidth="1.5"
        >
          <path d="M1 1l4 4 4-4" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>

      {/* ── Details panel ─────────────────────────────────────────────── */}
      {open && (
        <div className={cn(
          "absolute top-full mt-1.5 z-50",
          "w-72 rounded-xl border border-slate-200 bg-white shadow-xl shadow-slate-200/60",
          "p-4 text-[11px] leading-relaxed",
          align === "right" ? "right-0" : "left-0",
        )}>

          {/* Panel header */}
          <div className="flex items-start justify-between mb-3">
            <div>
              <p className="font-semibold text-slate-800 text-xs">{meta.source}</p>
              <a
                href={meta.source_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-indigo-500 hover:text-indigo-700 hover:underline break-all line-clamp-1"
                onClick={e => e.stopPropagation()}
              >
                {meta.source_url}
              </a>
            </div>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="ml-2 flex-shrink-0 text-slate-300 hover:text-slate-500 p-0.5"
              aria-label="Close"
            >
              <svg viewBox="0 0 12 12" className="w-3 h-3" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M1 1l10 10M11 1L1 11" strokeLinecap="round" />
              </svg>
            </button>
          </div>

          {/* Divider */}
          <div className="border-t border-slate-100 mb-3" />

          {/* Metadata rows */}
          <div className="space-y-2">

            {/* Fetched at */}
            <Row label="Last fetched">
              <span className="text-slate-700">{fmtFetchedAt(meta.fetched_at)}</span>
            </Row>

            {/* Frequency */}
            <Row label="Update frequency">
              <span className="text-slate-700">{FREQ_LABEL[meta.frequency]}</span>
            </Row>

            {/* Confidence */}
            <Row label="Confidence">
              <div className="flex items-center gap-1.5">
                <span className={cn("w-2 h-2 rounded-full flex-shrink-0", CONF_DOT[meta.confidence])} />
                <span className={cn("font-medium", CONF_TEXT[meta.confidence])}>
                  {CONF_LABEL[meta.confidence]}
                </span>
              </div>
              <p className="text-slate-400 mt-0.5">{CONF_DESC[meta.confidence]}</p>
            </Row>

            {/* Data quality */}
            <Row label="Data quality">
              <span className={cn(
                "inline-block px-1.5 py-0.5 rounded font-medium",
                qualityStyle.bg,
                qualityStyle.text,
              )}>
                {qualityStyle.label}
              </span>
            </Row>

            {/* Limitation note */}
            <Row label="Limitation">
              <p className="text-slate-500 leading-snug">{meta.limitation_note}</p>
            </Row>

          </div>

          {/* Footer link */}
          <div className="mt-3 pt-3 border-t border-slate-100">
            <a
              href={meta.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-indigo-600 hover:text-indigo-800 font-medium text-[10px]"
              onClick={e => e.stopPropagation()}
            >
              View original source
              <svg className="w-2.5 h-2.5" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M1.5 8.5l7-7M4 1.5h4.5V6" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </a>
          </div>

        </div>
      )}
    </div>
  );
}


// ── Sub-component: labelled row ───────────────────────────────────────────────

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="text-[9px] font-semibold uppercase tracking-wider text-slate-400 mb-0.5">
        {label}
      </p>
      <div>{children}</div>
    </div>
  );
}
