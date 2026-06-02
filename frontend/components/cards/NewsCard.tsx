import { cn } from "@/lib/utils";
import { SentimentBadge, CategoryBadge, ImpactDots } from "@/components/ui/Badge";
import { getCountry } from "@/data/sample-data";
import type { NewsEvent } from "@/data/sample-data";

interface Props { event: NewsEvent; compact?: boolean; }

export default function NewsCard({ event, compact = false }: Props) {
  const country = getCountry(event.countryId);
  const borderColor = event.sentiment === "positive"
    ? "border-l-emerald-400"
    : event.sentiment === "negative"
    ? "border-l-red-400"
    : "border-l-slate-300";

  return (
    <div className={cn("card border-l-4 p-4", borderColor)}>
      {/* Top row */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-1.5 text-xs text-slate-500">
          <span className="text-base">{country?.flagEmoji}</span>
          <span className="font-medium text-slate-700">{country?.shortName}</span>
          <span>·</span>
          <span>{event.sourceName}</span>
        </div>
        <CategoryBadge category={event.category} />
      </div>

      {/* Headline */}
      <h4 className="font-semibold text-slate-900 text-sm leading-snug mb-1.5">
        {event.headline}
      </h4>

      {/* Summary */}
      {!compact && (
        <p className="text-xs text-slate-500 leading-relaxed mb-3 line-clamp-2">
          {event.summary}
        </p>
      )}

      {/* Bottom row */}
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
    </div>
  );
}
