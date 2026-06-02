import { cn, RISK_CLASS, RISK_LABEL, SEV_CLASS, SENT_CLASS, CATEGORY_COLOR } from "@/lib/utils";
import type { RiskLevel, Severity, Sentiment } from "@/lib/utils";

interface BadgeProps { className?: string; children: React.ReactNode; }

export function Badge({ className, children }: BadgeProps) {
  return (
    <span className={cn("inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium", className)}>
      {children}
    </span>
  );
}

export function RiskBadge({ level }: { level: RiskLevel }) {
  return (
    <Badge className={cn("rounded-md", RISK_CLASS[level])}>
      {level === "critical" ? "⚠ " : ""}{RISK_LABEL[level]}
    </Badge>
  );
}

export function SeverityBadge({ severity }: { severity: Severity }) {
  const labels: Record<Severity, string> = { info: "Info", warning: "Warning", critical: "Critical" };
  const icons:  Record<Severity, string> = { info: "●", warning: "▲", critical: "⬛" };
  return (
    <Badge className={cn("rounded-md uppercase tracking-wide text-[10px]", SEV_CLASS[severity])}>
      {icons[severity]} {labels[severity]}
    </Badge>
  );
}

export function SentimentBadge({ sentiment }: { sentiment: Sentiment }) {
  const labels: Record<Sentiment, string> = { positive: "Positive", neutral: "Neutral", negative: "Negative" };
  const arrows: Record<Sentiment, string> = { positive: "↑", neutral: "→", negative: "↓" };
  return (
    <Badge className={cn("rounded-md", SENT_CLASS[sentiment])}>
      {arrows[sentiment]} {labels[sentiment]}
    </Badge>
  );
}

export function CategoryBadge({ category }: { category: string }) {
  const labels: Record<string, string> = {
    // Original 5
    economy:        "Economy",
    politics:       "Politics",
    trade:          "Trade",
    security:       "Security",
    disaster:       "Disaster",
    // GDELT v1 categories
    conflict:       "Conflict",
    protest:        "Protest",
    policy:         "Policy",
    infrastructure: "Infra",
    technology:     "Tech",
    // GDELT v2 categories (new)
    tariff:         "Tariff",
    border:         "Border",
    election:       "Election",
  };
  return (
    <Badge className={cn("rounded-md", CATEGORY_COLOR[category] ?? "bg-slate-100 text-slate-600")}>
      {labels[category] ?? category}
    </Badge>
  );
}

export function ImpactDots({ level }: { level: number }) {
  return (
    <div className="flex items-center gap-0.5">
      {[1,2,3,4,5].map(i => (
        <span
          key={i}
          className={cn(
            "w-2 h-2 rounded-full",
            i <= level
              ? level >= 5 ? "bg-red-500" : level >= 4 ? "bg-orange-500" : level >= 3 ? "bg-amber-500" : "bg-blue-400"
              : "bg-slate-200"
          )}
        />
      ))}
    </div>
  );
}
