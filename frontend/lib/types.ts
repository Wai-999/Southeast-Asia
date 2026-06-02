// Shared TypeScript types — mirrors the PostgreSQL schema

export type Region = "ASEAN" | "External Partner";
export type Cadence = "annual" | "quarterly" | "monthly" | "daily";
export type Severity = "info" | "warning" | "critical";
export type Sentiment = "positive" | "neutral" | "negative";
export type Direction = "export" | "import";
export type ImpactDirection = "positive" | "negative" | "neutral";

export interface Country {
  id: string;          // ISO alpha-3
  name: string;
  region: Region;
  iso2: string;
  currency: string;
  capital: string;
  flagEmoji: string;
}

export interface Indicator {
  id: number;
  code: string;
  name: string;
  description: string;
  unit: string;
  cadence: Cadence;
  sourceName: string;
}

export interface IndicatorValue {
  id: number;
  countryId: string;
  indicatorId: number;
  indicatorCode: string;
  year: number;
  quarter: number | null;
  month: number | null;
  value: number;
}

export interface TradeFlow {
  id: number;
  reporterId: string;
  partnerId: string;
  partnerName: string;
  year: number;
  quarter: number | null;
  direction: Direction;
  valueUsdM: number;
  sharePct: number | null;
}

export interface EventCategory {
  id: number;
  code: string;
  name: string;
  colorHex: string;
}

export interface NewsEvent {
  id: number;
  countryId: string;
  category: EventCategory;
  headline: string;
  summary: string | null;
  sourceName: string | null;
  sourceUrl: string | null;
  publishedAt: string;
  sentiment: Sentiment;
  sentimentScore: number | null;
}

export interface AlertRule {
  id: number;
  indicatorId: number;
  name: string;
  condition: string;
  threshold: number;
  period: string;
  severity: Severity;
}

export interface PatternAlert {
  id: number;
  countryId: string;
  countryName: string;
  alertRuleName: string;
  indicatorCode: string;
  triggerValue: number;
  threshold: number;
  severity: Severity;
  message: string;
  triggeredAt: string;
  isActive: boolean;
}

export interface AiExplanation {
  id: number;
  countryId: string;
  explanationType: string;
  explanationText: string;
  generatedAt: string;
}

// API response wrappers
export interface ApiList<T> {
  data: T[];
  total: number;
}

export interface ApiError {
  detail: string;
}
