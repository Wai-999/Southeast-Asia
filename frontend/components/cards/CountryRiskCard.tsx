import Link from "next/link";
import { cn, RISK_DOT } from "@/lib/utils";
import { RiskBadge } from "@/components/ui/Badge";
import type { Country, CurrentIndicators } from "@/data/sample-data";

interface Props { country: Country; indicators: CurrentIndicators; }

export default function CountryRiskCard({ country, indicators }: Props) {
  const gdpColor = indicators.gdpGrowth >= 0 ? "text-emerald-600" : "text-red-500";
  const infColor = indicators.inflation > 5 ? "text-red-500" : "text-slate-700";

  return (
    <Link href={`/country/${country.id}`}>
      <div className={cn(
        "card p-4 hover:shadow-md hover:-translate-y-0.5 transition-all cursor-pointer",
        "border-t-4",
        country.riskLevel === "critical" && "border-t-red-500",
        country.riskLevel === "high"     && "border-t-orange-500",
        country.riskLevel === "medium"   && "border-t-amber-500",
        country.riskLevel === "low"      && "border-t-emerald-500",
      )}>
        <div className="flex items-start justify-between mb-3">
          <span className="text-3xl leading-none">{country.flagEmoji}</span>
          <span className={cn("w-2 h-2 rounded-full mt-1.5 flex-shrink-0", RISK_DOT[country.riskLevel])} />
        </div>
        <h3 className="font-semibold text-slate-900 text-sm leading-tight">{country.name}</h3>
        <p className="text-[10px] text-slate-400 mb-2">{country.capital}</p>
        <div className="grid grid-cols-2 gap-x-3 gap-y-1.5">
          <div>
            <p className="text-[10px] text-slate-400">GDP Growth</p>
            <p className={cn("text-sm font-bold tabular-nums", gdpColor)}>
              {indicators.gdpGrowth >= 0 ? "+" : ""}{indicators.gdpGrowth.toFixed(1)}%
            </p>
          </div>
          <div>
            <p className="text-[10px] text-slate-400">Inflation</p>
            <p className={cn("text-sm font-bold tabular-nums", infColor)}>
              {indicators.inflation.toFixed(1)}%
            </p>
          </div>
        </div>
        <div className="mt-3">
          <RiskBadge level={country.riskLevel} />
        </div>
      </div>
    </Link>
  );
}
