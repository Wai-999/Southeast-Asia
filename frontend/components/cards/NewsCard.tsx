import { cn } from "@/lib/utils";
import { SentimentBadge, CategoryBadge, ImpactDots } from "@/components/ui/Badge";
import SourceBadge from "@/components/ui/SourceBadge";
import { getCountry } from "@/data/sample-data";
import { NS_SOURCE_META } from "@/data/news-signals";
import type { NewsEvent } from "@/data/sample-data";

interface Props {
  event:    NewsEvent;
  compact?: boolean;
  /**
   * Override the source metadata (e.g. for sample/static news events).
   * Defaults to the live GDELT source when source === "gdelt".
   */
  sourceMeta?: ReturnType<typeof import("@/data/news-signals").getArticleSourceMeta>;
}

export default function NewsCard({ event, compact = false, sourceMeta }: Props) {
  const country = getCountry(event.countryId);

  const borderColor =
    event.sentiment === "positive" ? "border-l-emerald-400"
    : event.sentiment === "negative" ? "border-l-red-400"
    : "border-l-slate-300";

  // Use provided source meta, or default to the global GDELT source meta
  // for live GDELT articles (source === "gdelt")
  const meta = sourceMeta ?? (event.source === "gdelt" ? NS_SOURCE_META : undefined);

  return (
    <div className={cn("card border-l-4 p-4", borderColor)}>

      {/* ── Top row ─────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-1.5 text-xs text-slate-500">
          <span className="text-base">{country?.flagEmoji}</span>
          <span className="font-medium text-slate-700">{country?.shortName}</span>
          <span>·</span>
          <span>{event.sourceName}</span>
        </div>
        <CategoryBadge category={event.category} />
      </div>

      {/* ── Headline ────────────────────────────────────────────────── */}
      {event.gdeltUrl ? (
        <a
          href={event.gdeltUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="block font-semibold text-slate-900 text-sm leading-snug mb-1.5
                     hover:text-indigo-700 hover:underline"
        >
          {event.headline}
        </a>
      ) : (
        <h4 className="font-semibold text-slate-900 text-sm leading-snug mb-1.5">
          {event.headline}
        </h4>
      )}

      {/* ── Summary ─────────────────────────────────────────────────── */}
      {!compact && event.summary !== event.headline && (
        <p className="text-xs text-slate-500 leading-relaxed mb-3 line-clamp-2">
          {event.summary}
        </p>
      )}

      {/* ── Bottom row ──────────────────────────────────────────────── */}
      <div className="flex items-center justify-between mt-auto">
        <div className="flex items-center gap-2">
          <SentimentBadge sentiment={event.sentiment} />
          <span className="text-[10px] text-slate-400">{event.publishedAt}</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="text-[10px] text-slate-400">Impact</span>
          <ImpactDots level={event.impactLevel} />
        </div>
      </div>

      {/* ── Source details ───────────────────────────────────────────── */}
      {meta && (
        <div className="pt-2 mt-2 border-t border-slate-100">
          <SourceBadge meta={meta} />
        </div>
      )}
    </div>
  );
}
