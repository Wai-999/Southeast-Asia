import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function fmt(n: number, decimals = 1): string {
  return n.toFixed(decimals);
}

export function fmtChange(n: number, unit = "%"): string {
  return `${n >= 0 ? "+" : ""}${fmt(n)}${unit}`;
}

export function fmtBillions(n: number): string {
  if (Math.abs(n) >= 1000) return `$${fmt(n / 1000, 1)}T`;
  return `$${fmt(Math.abs(n), 1)}B`;
}

export type RiskLevel = "low" | "medium" | "high" | "critical";

export const RISK_LABEL: Record<RiskLevel, string> = {
  low: "Low Risk",
  medium: "Medium Risk",
  high: "High Risk",
  critical: "Critical",
};

export const RISK_CLASS: Record<RiskLevel, string> = {
  low: "risk-low",
  medium: "risk-medium",
  high: "risk-high",
  critical: "risk-critical",
};

export const RISK_DOT: Record<RiskLevel, string> = {
  low: "bg-emerald-500",
  medium: "bg-amber-500",
  high: "bg-orange-500",
  critical: "bg-red-500",
};

export const RISK_BORDER: Record<RiskLevel, string> = {
  low: "border-l-emerald-500",
  medium: "border-l-amber-500",
  high: "border-l-orange-500",
  critical: "border-l-red-500",
};

export type Severity = "info" | "warning" | "critical";

export const SEV_CLASS: Record<Severity, string> = {
  info: "sev-info",
  warning: "sev-warning",
  critical: "sev-critical",
};

export const SEV_BORDER: Record<Severity, string> = {
  info: "border-l-blue-500",
  warning: "border-l-amber-500",
  critical: "border-l-red-500",
};

export type Sentiment = "positive" | "neutral" | "negative";

export const SENT_CLASS: Record<Sentiment, string> = {
  positive: "sent-positive",
  neutral: "sent-neutral",
  negative: "sent-negative",
};

export const SENT_EMOJI: Record<Sentiment, string> = {
  positive: "↑",
  neutral: "→",
  negative: "↓",
};

export const CATEGORY_COLOR: Record<string, string> = {
  // Original 5
  economy:        "bg-blue-100 text-blue-700",
  politics:       "bg-purple-100 text-purple-700",
  trade:          "bg-yellow-100 text-yellow-700",
  security:       "bg-red-100 text-red-700",
  disaster:       "bg-orange-100 text-orange-700",
  // GDELT categories (v1)
  conflict:       "bg-red-100 text-red-800",
  protest:        "bg-fuchsia-100 text-fuchsia-700",
  policy:         "bg-indigo-100 text-indigo-700",
  infrastructure: "bg-teal-100 text-teal-700",
  technology:     "bg-cyan-100 text-cyan-700",
  // 3 new GDELT v2 categories
  tariff:         "bg-red-50 text-red-700",
  border:         "bg-rose-100 text-rose-700",
  election:       "bg-violet-100 text-violet-700",
};

export const CHART_COLORS = [
  "#3b82f6", "#10b981", "#f59e0b", "#ef4444",
  "#8b5cf6", "#06b6d4", "#f97316", "#84cc16",
  "#ec4899", "#14b8a6",
];
