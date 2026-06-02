/**
 * sample-data.ts
 * ──────────────
 * All static data for the SEA Change Intelligence Dashboard.
 * 5 countries · 8 indicators · 5 years of history
 * No real API needed — this file IS the database for the prototype.
 */

import type { RiskLevel, Severity, Sentiment } from "@/lib/utils";

// ─────────────────────────────────────────────────────────────────
// TYPES
// ─────────────────────────────────────────────────────────────────

export interface Country {
  id: string;          // ISO-3 code
  name: string;        // Full name
  shortName: string;   // Short display name
  flagEmoji: string;
  capital: string;
  currency: string;    // ISO-4217 code
  currencyName: string;
  region: "ASEAN" | "External Partner";
  riskLevel: RiskLevel;
  riskSummary: string; // One-line risk description
}

/** The 8 tracked indicators for each country (latest year: 2024) */
export interface CurrentIndicators {
  gdpGrowth:         number; // % YoY
  inflation:         number; // % CPI
  exports:           number; // USD billions
  imports:           number; // USD billions
  exchangeRate:      number; // local currency per USD
  fdi:               number; // USD billions (net inflows)
  politicalRiskNews: number; // news article count per month (risk-tagged)
  tradeNewsCount:    number; // news article count per month (trade-tagged)
}

/** A single data point for a trend chart */
export interface YearPoint { year: number; value: number; }

/** 5 years of history (2020-2024) for each indicator */
export interface CountryHistory {
  gdpGrowth:         YearPoint[];
  inflation:         YearPoint[];
  exports:           YearPoint[];
  imports:           YearPoint[];
  exchangeRate:      YearPoint[];
  fdi:               YearPoint[];
  politicalRiskNews: YearPoint[];
  tradeNewsCount:    YearPoint[];
}

export interface NewsEvent {
  id:                  number;
  countryId:           string;
  headline:            string;
  summary:             string;
  // Original 5 + GDELT categories (total 13)
  category:            "economy" | "politics" | "trade" | "security" | "disaster"
                     | "conflict" | "protest" | "policy" | "infrastructure" | "technology"
                     | "tariff" | "border" | "election";
  sentiment:           Sentiment;
  sentimentScore:      number;  // −1 to +1
  publishedAt:         string;  // "YYYY-MM-DD"
  sourceName:          string;
  impactLevel:         number;  // 1–5
  impactedIndicators:  string[];
  // Optional GDELT-specific fields (undefined on static sample events)
  gdeltUrl?:           string;
  gdeltTone?:          number;
  source?:             "sample" | "gdelt";
}

export interface PatternAlert {
  id:             number;
  countryId:      string;
  ruleName:       string;
  indicatorCode:  string;  // matches CurrentIndicators key
  indicatorLabel: string;
  triggerValue:   number;
  threshold:      number;
  unit:           string;
  severity:       Severity;
  message:        string;
  triggeredAt:    string;
  isActive:       boolean;
}

/** Row shape used by the comparison bar chart */
export interface CompareRow {
  countryId:   string;
  countryName: string;
  flagEmoji:   string;
  value:       number;
  riskLevel:   RiskLevel;
}

/** Keys for the comparison/metric selector */
export type MetricKey = keyof CurrentIndicators;

// ─────────────────────────────────────────────────────────────────
// COUNTRIES (5 ASEAN nations)
// ─────────────────────────────────────────────────────────────────

export const COUNTRIES: Country[] = [
  {
    id: "THA", name: "Thailand", shortName: "Thailand",
    flagEmoji: "🇹🇭", capital: "Bangkok", currency: "THB",
    currencyName: "Thai Baht", region: "ASEAN", riskLevel: "medium",
    riskSummary: "Stable economy, political tension watch",
  },
  {
    id: "VNM", name: "Vietnam", shortName: "Vietnam",
    flagEmoji: "🇻🇳", capital: "Hanoi", currency: "VND",
    currencyName: "Vietnamese Đồng", region: "ASEAN", riskLevel: "low",
    riskSummary: "Strong growth, export-led economy",
  },
  {
    id: "MMR", name: "Myanmar", shortName: "Myanmar",
    flagEmoji: "🇲🇲", capital: "Naypyidaw", currency: "MMK",
    currencyName: "Burmese Kyat", region: "ASEAN", riskLevel: "critical",
    riskSummary: "Post-coup crisis: GDP contraction, hyperinflation",
  },
  {
    id: "KHM", name: "Cambodia", shortName: "Cambodia",
    flagEmoji: "🇰🇭", capital: "Phnom Penh", currency: "KHR",
    currencyName: "Cambodian Riel", region: "ASEAN", riskLevel: "high",
    riskSummary: "Growth recovery, inflation and trade deficit pressures",
  },
  {
    id: "SGP", name: "Singapore", shortName: "Singapore",
    flagEmoji: "🇸🇬", capital: "Singapore", currency: "SGD",
    currencyName: "Singapore Dollar", region: "ASEAN", riskLevel: "low",
    riskSummary: "Hub economy, growth below long-run trend",
  },
];

// ─────────────────────────────────────────────────────────────────
// CURRENT INDICATORS  (2024 values)
// ─────────────────────────────────────────────────────────────────

export const CURRENT_INDICATORS: Record<string, CurrentIndicators> = {
  THA: {
    gdpGrowth: 2.8, inflation: 3.2,
    exports: 285, imports: 262,
    exchangeRate: 33.5, fdi: 11.2,
    politicalRiskNews: 42, tradeNewsCount: 28,
  },
  VNM: {
    gdpGrowth: 6.1, inflation: 3.8,
    exports: 354, imports: 338,
    exchangeRate: 24500, fdi: 18.7,
    politicalRiskNews: 18, tradeNewsCount: 35,
  },
  MMR: {
    gdpGrowth: -2.1, inflation: 22.4,
    exports: 15, imports: 13,
    exchangeRate: 2100, fdi: 0.8,
    politicalRiskNews: 156, tradeNewsCount: 45,
  },
  KHM: {
    gdpGrowth: 5.4, inflation: 5.8,
    exports: 22, imports: 25,
    exchangeRate: 4100, fdi: 3.2,
    politicalRiskNews: 48, tradeNewsCount: 22,
  },
  SGP: {
    gdpGrowth: 1.2, inflation: 2.6,
    exports: 516, imports: 494,
    exchangeRate: 1.34, fdi: 139,
    politicalRiskNews: 5, tradeNewsCount: 18,
  },
};

// ─────────────────────────────────────────────────────────────────
// HISTORICAL DATA  (2020–2024)
// ─────────────────────────────────────────────────────────────────

export const HISTORICAL: Record<string, CountryHistory> = {
  THA: {
    gdpGrowth:         [{ year: 2020, value: -6.1 }, { year: 2021, value: 1.5  }, { year: 2022, value: 2.6 }, { year: 2023, value: 1.9  }, { year: 2024, value: 2.8  }],
    inflation:         [{ year: 2020, value: -0.8 }, { year: 2021, value: 1.2  }, { year: 2022, value: 6.1 }, { year: 2023, value: 1.2  }, { year: 2024, value: 3.2  }],
    exports:           [{ year: 2020, value: 231  }, { year: 2021, value: 271  }, { year: 2022, value: 287 }, { year: 2023, value: 284  }, { year: 2024, value: 285  }],
    imports:           [{ year: 2020, value: 202  }, { year: 2021, value: 233  }, { year: 2022, value: 265 }, { year: 2023, value: 261  }, { year: 2024, value: 262  }],
    exchangeRate:      [{ year: 2020, value: 31.3 }, { year: 2021, value: 31.9 }, { year: 2022, value: 35.0}, { year: 2023, value: 34.8 }, { year: 2024, value: 33.5 }],
    fdi:               [{ year: 2020, value: 6.1  }, { year: 2021, value: 9.2  }, { year: 2022, value: 11.0}, { year: 2023, value: 10.8 }, { year: 2024, value: 11.2 }],
    politicalRiskNews: [{ year: 2020, value: 28   }, { year: 2021, value: 35   }, { year: 2022, value: 42  }, { year: 2023, value: 38   }, { year: 2024, value: 42   }],
    tradeNewsCount:    [{ year: 2020, value: 18   }, { year: 2021, value: 22   }, { year: 2022, value: 31  }, { year: 2023, value: 27   }, { year: 2024, value: 28   }],
  },
  VNM: {
    gdpGrowth:         [{ year: 2020, value: 2.9  }, { year: 2021, value: 2.6  }, { year: 2022, value: 8.0 }, { year: 2023, value: 5.1  }, { year: 2024, value: 6.1  }],
    inflation:         [{ year: 2020, value: 3.2  }, { year: 2021, value: 1.8  }, { year: 2022, value: 3.2 }, { year: 2023, value: 3.5  }, { year: 2024, value: 3.8  }],
    exports:           [{ year: 2020, value: 282  }, { year: 2021, value: 336  }, { year: 2022, value: 371 }, { year: 2023, value: 355  }, { year: 2024, value: 354  }],
    imports:           [{ year: 2020, value: 262  }, { year: 2021, value: 332  }, { year: 2022, value: 360 }, { year: 2023, value: 328  }, { year: 2024, value: 338  }],
    exchangeRate:      [{ year: 2020, value: 23200}, { year: 2021, value: 23200}, { year: 2022, value: 23700}, { year: 2023, value: 24070}, { year: 2024, value: 24500}],
    fdi:               [{ year: 2020, value: 19.9 }, { year: 2021, value: 15.3 }, { year: 2022, value: 17.1}, { year: 2023, value: 18.5 }, { year: 2024, value: 18.7 }],
    politicalRiskNews: [{ year: 2020, value: 12   }, { year: 2021, value: 14   }, { year: 2022, value: 18  }, { year: 2023, value: 17   }, { year: 2024, value: 18   }],
    tradeNewsCount:    [{ year: 2020, value: 25   }, { year: 2021, value: 30   }, { year: 2022, value: 38  }, { year: 2023, value: 33   }, { year: 2024, value: 35   }],
  },
  MMR: {
    gdpGrowth:         [{ year: 2020, value: 3.2  }, { year: 2021, value: -17.9}, { year: 2022, value: 3.0 }, { year: 2023, value: -1.0 }, { year: 2024, value: -2.1 }],
    inflation:         [{ year: 2020, value: 5.7  }, { year: 2021, value: 3.5  }, { year: 2022, value: 18.0}, { year: 2023, value: 20.1 }, { year: 2024, value: 22.4 }],
    exports:           [{ year: 2020, value: 17.6 }, { year: 2021, value: 14.0 }, { year: 2022, value: 12.0}, { year: 2023, value: 14.5 }, { year: 2024, value: 15.0 }],
    imports:           [{ year: 2020, value: 17.1 }, { year: 2021, value: 11.0 }, { year: 2022, value: 10.5}, { year: 2023, value: 12.5 }, { year: 2024, value: 13.0 }],
    exchangeRate:      [{ year: 2020, value: 1330 }, { year: 2021, value: 1780 }, { year: 2022, value: 1780}, { year: 2023, value: 2100 }, { year: 2024, value: 2100 }],
    fdi:               [{ year: 2020, value: 2.5  }, { year: 2021, value: 0.9  }, { year: 2022, value: 1.4 }, { year: 2023, value: 1.0  }, { year: 2024, value: 0.8  }],
    politicalRiskNews: [{ year: 2020, value: 18   }, { year: 2021, value: 210  }, { year: 2022, value: 185 }, { year: 2023, value: 168  }, { year: 2024, value: 156  }],
    tradeNewsCount:    [{ year: 2020, value: 22   }, { year: 2021, value: 52   }, { year: 2022, value: 48  }, { year: 2023, value: 45   }, { year: 2024, value: 45   }],
  },
  KHM: {
    gdpGrowth:         [{ year: 2020, value: -3.1 }, { year: 2021, value: 3.0  }, { year: 2022, value: 5.2 }, { year: 2023, value: 5.5  }, { year: 2024, value: 5.4  }],
    inflation:         [{ year: 2020, value: 2.9  }, { year: 2021, value: 3.3  }, { year: 2022, value: 5.5 }, { year: 2023, value: 2.1  }, { year: 2024, value: 5.8  }],
    exports:           [{ year: 2020, value: 16.7 }, { year: 2021, value: 18.2 }, { year: 2022, value: 22.8}, { year: 2023, value: 21.5 }, { year: 2024, value: 22.0 }],
    imports:           [{ year: 2020, value: 18.4 }, { year: 2021, value: 20.1 }, { year: 2022, value: 25.2}, { year: 2023, value: 24.8 }, { year: 2024, value: 25.0 }],
    exchangeRate:      [{ year: 2020, value: 4050 }, { year: 2021, value: 4080 }, { year: 2022, value: 4098}, { year: 2023, value: 4110 }, { year: 2024, value: 4100 }],
    fdi:               [{ year: 2020, value: 3.6  }, { year: 2021, value: 3.4  }, { year: 2022, value: 3.8 }, { year: 2023, value: 3.5  }, { year: 2024, value: 3.2  }],
    politicalRiskNews: [{ year: 2020, value: 32   }, { year: 2021, value: 38   }, { year: 2022, value: 44  }, { year: 2023, value: 50   }, { year: 2024, value: 48   }],
    tradeNewsCount:    [{ year: 2020, value: 14   }, { year: 2021, value: 18   }, { year: 2022, value: 22  }, { year: 2023, value: 21   }, { year: 2024, value: 22   }],
  },
  SGP: {
    gdpGrowth:         [{ year: 2020, value: -3.9 }, { year: 2021, value: 8.9  }, { year: 2022, value: 3.6 }, { year: 2023, value: 1.1  }, { year: 2024, value: 1.2  }],
    inflation:         [{ year: 2020, value: -0.2 }, { year: 2021, value: 2.3  }, { year: 2022, value: 6.1 }, { year: 2023, value: 4.8  }, { year: 2024, value: 2.6  }],
    exports:           [{ year: 2020, value: 374  }, { year: 2021, value: 455  }, { year: 2022, value: 516 }, { year: 2023, value: 477  }, { year: 2024, value: 516  }],
    imports:           [{ year: 2020, value: 328  }, { year: 2021, value: 404  }, { year: 2022, value: 476 }, { year: 2023, value: 448  }, { year: 2024, value: 494  }],
    exchangeRate:      [{ year: 2020, value: 1.38 }, { year: 2021, value: 1.34 }, { year: 2022, value: 1.38}, { year: 2023, value: 1.34 }, { year: 2024, value: 1.34 }],
    fdi:               [{ year: 2020, value: 91.0 }, { year: 2021, value: 131.7}, { year: 2022, value: 140.2}, { year: 2023, value: 160.0}, { year: 2024, value: 139.0}],
    politicalRiskNews: [{ year: 2020, value: 3    }, { year: 2021, value: 4    }, { year: 2022, value: 5   }, { year: 2023, value: 6    }, { year: 2024, value: 5    }],
    tradeNewsCount:    [{ year: 2020, value: 12   }, { year: 2021, value: 15   }, { year: 2022, value: 20  }, { year: 2023, value: 18   }, { year: 2024, value: 18   }],
  },
};

// ─────────────────────────────────────────────────────────────────
// METRIC METADATA  (labels + units for charts and tables)
// ─────────────────────────────────────────────────────────────────

export const METRIC_LABELS: Record<MetricKey, string> = {
  gdpGrowth:         "GDP Growth",
  inflation:         "Inflation Rate",
  exports:           "Total Exports",
  imports:           "Total Imports",
  exchangeRate:      "Exchange Rate",
  fdi:               "FDI Inflows",
  politicalRiskNews: "Political Risk News",
  tradeNewsCount:    "Trade News Count",
};

export const METRIC_UNITS: Record<MetricKey, string> = {
  gdpGrowth:         "% YoY",
  inflation:         "% CPI",
  exports:           "B USD",
  imports:           "B USD",
  exchangeRate:      "per USD",
  fdi:               "B USD",
  politicalRiskNews: "articles/mo",
  tradeNewsCount:    "articles/mo",
};

export const METRIC_DESC: Record<MetricKey, string> = {
  gdpGrowth:         "Annual GDP growth rate (year-over-year %)",
  inflation:         "Consumer Price Index annual change",
  exports:           "Total goods and services exported (USD billions)",
  imports:           "Total goods and services imported (USD billions)",
  exchangeRate:      "Local currency units per 1 USD",
  fdi:               "Net foreign direct investment inflows (USD billions)",
  politicalRiskNews: "Monthly count of political-risk news articles",
  tradeNewsCount:    "Monthly count of trade-related news articles",
};

// Higher value = higher risk for each metric
export const METRIC_HIGHER_IS_WORSE: Record<MetricKey, boolean> = {
  gdpGrowth:         false, // higher growth is GOOD
  inflation:         true,  // higher inflation is BAD
  exports:           false, // higher exports is GOOD
  imports:           false, // higher imports is NEUTRAL
  exchangeRate:      true,  // higher rate = weaker currency (BAD)
  fdi:               false, // higher FDI is GOOD
  politicalRiskNews: true,  // more risk news = BAD
  tradeNewsCount:    false, // more trade news = NEUTRAL/GOOD
};

// ─────────────────────────────────────────────────────────────────
// NEWS EVENTS  (25 items across all 5 countries)
// ─────────────────────────────────────────────────────────────────

export const NEWS_EVENTS: NewsEvent[] = [
  // ── Thailand ──────────────────────────────────────────────────
  {
    id: 1, countryId: "THA",
    headline: "Thailand Raises Tourism Target to 40 Million Visitors for 2025",
    summary: "The Tourism Authority of Thailand announced an ambitious target following strong Q3 2024 inflows. Hotel occupancy in Bangkok exceeded 85% in October, signalling continued post-pandemic recovery.",
    category: "economy", sentiment: "positive", sentimentScore: 0.72,
    publishedAt: "2024-11-28", sourceName: "Bangkok Post",
    impactLevel: 3, impactedIndicators: ["exports", "gdpGrowth"],
  },
  {
    id: 2, countryId: "THA",
    headline: "Thai Central Bank Holds Rate Steady Amid Inflation Concerns",
    summary: "The Bank of Thailand kept its benchmark rate at 2.5%, citing elevated core inflation and weaker-than-expected export growth in electronics and auto sectors.",
    category: "economy", sentiment: "neutral", sentimentScore: 0.02,
    publishedAt: "2024-11-20", sourceName: "Reuters",
    impactLevel: 4, impactedIndicators: ["inflation", "exchangeRate"],
  },
  {
    id: 3, countryId: "THA",
    headline: "Political Opposition Forms Coalition Ahead of Budget Vote",
    summary: "Opposition parties have consolidated their position in parliament in a challenge to the government's 2025 budget proposal, raising concerns over infrastructure spending timelines.",
    category: "politics", sentiment: "negative", sentimentScore: -0.38,
    publishedAt: "2024-11-15", sourceName: "The Nation Thailand",
    impactLevel: 3, impactedIndicators: ["politicalRiskNews", "fdi"],
  },
  {
    id: 4, countryId: "THA",
    headline: "EV Manufacturing Investment Surge: $3.2B in New Plant Commitments",
    summary: "Three major Chinese and Japanese automakers confirmed plans to establish electric vehicle assembly plants in the Eastern Economic Corridor, bringing $3.2B in committed capital.",
    category: "trade", sentiment: "positive", sentimentScore: 0.81,
    publishedAt: "2024-11-08", sourceName: "Financial Times",
    impactLevel: 5, impactedIndicators: ["fdi", "exports"],
  },
  {
    id: 5, countryId: "THA",
    headline: "Flash Floods Disrupt Supply Chains in Northern Industrial Zones",
    summary: "Severe flooding in Chiang Mai and Lamphun provinces disrupted automotive and electronics manufacturing, with insurers estimating losses exceeding $180M in business interruption claims.",
    category: "disaster", sentiment: "negative", sentimentScore: -0.65,
    publishedAt: "2024-10-22", sourceName: "Bloomberg",
    impactLevel: 4, impactedIndicators: ["exports", "gdpGrowth"],
  },

  // ── Vietnam ───────────────────────────────────────────────────
  {
    id: 6, countryId: "VNM",
    headline: "Vietnam Q3 GDP Surges 7.4%: Fastest in Three Years",
    summary: "Vietnam's economy expanded 7.4% in Q3 2024, driven by record electronics exports and a 22% rise in manufacturing FDI. Samsung and Apple supplier expansions underpin the momentum.",
    category: "economy", sentiment: "positive", sentimentScore: 0.88,
    publishedAt: "2024-11-29", sourceName: "Vietnam News Agency",
    impactLevel: 5, impactedIndicators: ["gdpGrowth", "exports", "fdi"],
  },
  {
    id: 7, countryId: "VNM",
    headline: "US-Vietnam Trade Volume Tops $132B for First Time",
    summary: "Bilateral trade between the US and Vietnam surpassed $132 billion in the first 10 months of 2024, cementing Vietnam's position as the US's third-largest import source in Asia.",
    category: "trade", sentiment: "positive", sentimentScore: 0.79,
    publishedAt: "2024-11-22", sourceName: "VN Express",
    impactLevel: 4, impactedIndicators: ["exports", "tradeNewsCount"],
  },
  {
    id: 8, countryId: "VNM",
    headline: "VND Weakens to Six-Month Low Against USD on Capital Outflow Concerns",
    summary: "The Vietnamese dong depreciated to 24,500 per dollar, its weakest level since April. The State Bank intervened, selling approximately $800M in reserves to stabilize the currency.",
    category: "economy", sentiment: "negative", sentimentScore: -0.44,
    publishedAt: "2024-11-18", sourceName: "Reuters",
    impactLevel: 3, impactedIndicators: ["exchangeRate", "imports"],
  },
  {
    id: 9, countryId: "VNM",
    headline: "Vietnam Fast-Tracks Semiconductor Zone to Attract Chip Makers",
    summary: "The government approved a $1.5B incentive package for a dedicated semiconductor industrial zone in Binh Duong, targeting investments from TSMC supply chain partners.",
    category: "economy", sentiment: "positive", sentimentScore: 0.76,
    publishedAt: "2024-11-05", sourceName: "Nikkei Asia",
    impactLevel: 4, impactedIndicators: ["fdi", "tradeNewsCount"],
  },
  {
    id: 10, countryId: "VNM",
    headline: "Anti-Corruption Drive: 12 Senior Officials Charged in Land Scandal",
    summary: "Vietnam's ongoing anti-graft campaign expanded with charges against 12 provincial officials involved in illegal land allocation, signalling continued government resolve.",
    category: "politics", sentiment: "neutral", sentimentScore: -0.12,
    publishedAt: "2024-10-30", sourceName: "Tuoi Tre News",
    impactLevel: 2, impactedIndicators: ["politicalRiskNews"],
  },

  // ── Myanmar ───────────────────────────────────────────────────
  {
    id: 11, countryId: "MMR",
    headline: "Myanmar Kyat Hits All-Time Low on Black Market at 6,500 per USD",
    summary: "The informal exchange rate for the Myanmar kyat plunged to 6,500 per USD, nearly triple the official rate of 2,100, reflecting capital flight and dwindling foreign exchange reserves.",
    category: "economy", sentiment: "negative", sentimentScore: -0.91,
    publishedAt: "2024-11-27", sourceName: "Irrawaddy",
    impactLevel: 5, impactedIndicators: ["exchangeRate", "inflation", "imports"],
  },
  {
    id: 12, countryId: "MMR",
    headline: "World Bank Slashes Myanmar 2024 Growth Forecast to −2.1%",
    summary: "The World Bank's latest update projects Myanmar's GDP will contract 2.1% in 2024 as conflict disrupts agriculture, manufacturing, and supply chains in border regions.",
    category: "economy", sentiment: "negative", sentimentScore: -0.87,
    publishedAt: "2024-11-20", sourceName: "World Bank",
    impactLevel: 5, impactedIndicators: ["gdpGrowth", "fdi"],
  },
  {
    id: 13, countryId: "MMR",
    headline: "Conflict Expands to Mandalay Region: 200,000 Displaced",
    summary: "Resistance forces gained significant territory in Mandalay and Sagaing regions during November, forcing approximately 200,000 civilians to flee in the largest displacement event this year.",
    category: "security", sentiment: "negative", sentimentScore: -0.95,
    publishedAt: "2024-11-25", sourceName: "AP",
    impactLevel: 5, impactedIndicators: ["politicalRiskNews", "gdpGrowth"],
  },
  {
    id: 14, countryId: "MMR",
    headline: "Myanmar Inflation Hits 22.4%: Fuel and Food Prices Spike",
    summary: "Consumer prices rose 22.4% year-on-year in October, driven by a 38% surge in fuel costs following import restrictions and a 28% increase in staple food prices in urban centres.",
    category: "economy", sentiment: "negative", sentimentScore: -0.82,
    publishedAt: "2024-11-10", sourceName: "Myanmar Economic Monitor",
    impactLevel: 5, impactedIndicators: ["inflation", "imports"],
  },
  {
    id: 15, countryId: "MMR",
    headline: "ASEAN Emergency Consultation on Myanmar Humanitarian Crisis",
    summary: "ASEAN foreign ministers convened an emergency session to discuss the worsening humanitarian situation, with Thailand and China calling for an immediate ceasefire.",
    category: "politics", sentiment: "neutral", sentimentScore: -0.15,
    publishedAt: "2024-11-02", sourceName: "Channel NewsAsia",
    impactLevel: 4, impactedIndicators: ["politicalRiskNews", "tradeNewsCount"],
  },

  // ── Cambodia ──────────────────────────────────────────────────
  {
    id: 16, countryId: "KHM",
    headline: "Cambodia's Trade Deficit Widens to $3.0B as Import Costs Surge",
    summary: "Cambodia's merchandise trade deficit expanded to $3 billion in January–September 2024, as energy and intermediate goods imports surged. Garment exports remain the sole bright spot.",
    category: "trade", sentiment: "negative", sentimentScore: -0.52,
    publishedAt: "2024-11-26", sourceName: "Khmer Times",
    impactLevel: 4, impactedIndicators: ["imports", "exports", "tradeNewsCount"],
  },
  {
    id: 17, countryId: "KHM",
    headline: "Inflation Jumps to 5.8% in Cambodia: Food and Transport Lead",
    summary: "Cambodia's CPI rose 5.8% in October, the highest since 2022, driven by fuel prices and food costs. The National Bank of Cambodia warned of persistent price pressures into 2025.",
    category: "economy", sentiment: "negative", sentimentScore: -0.58,
    publishedAt: "2024-11-18", sourceName: "Phnom Penh Post",
    impactLevel: 4, impactedIndicators: ["inflation", "imports"],
  },
  {
    id: 18, countryId: "KHM",
    headline: "EU EBA Trade Status Restored After Governance Reforms",
    summary: "The European Union announced a partial restoration of Cambodia's Everything But Arms trade preferences following judicial and labour reforms, benefiting the garment and footwear sectors.",
    category: "trade", sentiment: "positive", sentimentScore: 0.68,
    publishedAt: "2024-11-12", sourceName: "Reuters",
    impactLevel: 4, impactedIndicators: ["exports", "tradeNewsCount"],
  },
  {
    id: 19, countryId: "KHM",
    headline: "Opposition Leader Sentenced to 27 Years: Rights Groups React",
    summary: "A Phnom Penh court sentenced the leader of an unlicensed political party to 27 years imprisonment. International rights organisations criticised the verdict as politically motivated.",
    category: "politics", sentiment: "negative", sentimentScore: -0.71,
    publishedAt: "2024-11-06", sourceName: "Human Rights Watch",
    impactLevel: 4, impactedIndicators: ["politicalRiskNews", "fdi"],
  },
  {
    id: 20, countryId: "KHM",
    headline: "Cambodia Posts 5.4% GDP Growth, Driven by Tourism and Construction",
    summary: "Cambodia's economy grew 5.4% in 2024 according to preliminary ADB estimates, supported by a tourism rebound (3.2M international arrivals) and a construction boom in Phnom Penh.",
    category: "economy", sentiment: "positive", sentimentScore: 0.62,
    publishedAt: "2024-10-28", sourceName: "ADB Press Release",
    impactLevel: 3, impactedIndicators: ["gdpGrowth"],
  },

  // ── Singapore ─────────────────────────────────────────────────
  {
    id: 21, countryId: "SGP",
    headline: "Singapore Non-Oil Domestic Exports Rise 3.1% in October",
    summary: "Singapore's NODX grew 3.1% year-on-year in October, driven by pharmaceutical shipments (+12%) and precision engineering (+8%), reversing four consecutive months of decline.",
    category: "trade", sentiment: "positive", sentimentScore: 0.55,
    publishedAt: "2024-11-28", sourceName: "MAS",
    impactLevel: 3, impactedIndicators: ["exports", "tradeNewsCount"],
  },
  {
    id: 22, countryId: "SGP",
    headline: "MAS Eases Monetary Policy Slightly as Inflation Cools to 2.6%",
    summary: "The Monetary Authority of Singapore slightly reduced the slope of SGD appreciation band, reflecting easing inflation (2.6% core CPI) and a cautious growth outlook for 2025.",
    category: "economy", sentiment: "neutral", sentimentScore: 0.10,
    publishedAt: "2024-11-21", sourceName: "Straits Times",
    impactLevel: 4, impactedIndicators: ["inflation", "exchangeRate"],
  },
  {
    id: 23, countryId: "SGP",
    headline: "Singapore Launches $5B Green Finance Initiative for ASEAN",
    summary: "The Singapore government launched a new $5B green finance initiative aimed at channelling capital into ASEAN clean energy and infrastructure projects under the MAS sustainability framework.",
    category: "economy", sentiment: "positive", sentimentScore: 0.71,
    publishedAt: "2024-11-14", sourceName: "Channel NewsAsia",
    impactLevel: 3, impactedIndicators: ["fdi", "tradeNewsCount"],
  },
  {
    id: 24, countryId: "SGP",
    headline: "Data Centre Moratorium Lifted: $4.2B in New Investment Confirmed",
    summary: "Singapore lifted its data centre construction moratorium, immediately clearing $4.2B in backlogged investment from hyperscale operators. New sustainability requirements apply to all new builds.",
    category: "economy", sentiment: "positive", sentimentScore: 0.78,
    publishedAt: "2024-11-07", sourceName: "Business Times",
    impactLevel: 4, impactedIndicators: ["fdi", "gdpGrowth"],
  },
  {
    id: 25, countryId: "SGP",
    headline: "Singapore GDP Growth Remains Modest at 1.2% Amid Global Headwinds",
    summary: "MTI revised Singapore's 2024 growth forecast to 1.0–2.0%, citing subdued external demand, China slowdown spillovers, and muted regional trade volumes.",
    category: "economy", sentiment: "neutral", sentimentScore: -0.08,
    publishedAt: "2024-10-24", sourceName: "MTI Singapore",
    impactLevel: 3, impactedIndicators: ["gdpGrowth", "exports"],
  },
];

// ─────────────────────────────────────────────────────────────────
// PATTERN ALERTS  (rule-based threshold alerts)
// ─────────────────────────────────────────────────────────────────

export const PATTERN_ALERTS: PatternAlert[] = [
  // ── Myanmar (Critical) ────────────────────────────────────────
  {
    id: 1, countryId: "MMR",
    ruleName: "GDP Contraction Alert",
    indicatorCode: "gdpGrowth", indicatorLabel: "GDP Growth Rate",
    triggerValue: -2.1, threshold: 0, unit: "%",
    severity: "critical",
    message: "GDP contracted −2.1% — second consecutive year of negative growth. Economic collapse risk elevated.",
    triggeredAt: "2024-11-01", isActive: true,
  },
  {
    id: 2, countryId: "MMR",
    ruleName: "Hyperinflation Warning",
    indicatorCode: "inflation", indicatorLabel: "Inflation Rate (CPI)",
    triggerValue: 22.4, threshold: 10, unit: "%",
    severity: "critical",
    message: "Inflation at 22.4%, more than double the 10% crisis threshold. Currency debasement accelerating.",
    triggeredAt: "2024-10-15", isActive: true,
  },
  {
    id: 3, countryId: "MMR",
    ruleName: "Political Instability Critical",
    indicatorCode: "politicalRiskNews", indicatorLabel: "Political Risk News",
    triggerValue: 156, threshold: 40, unit: "articles/mo",
    severity: "critical",
    message: "Political risk news at 156 articles/month — 3.9× the regional alert threshold of 40. Ongoing armed conflict.",
    triggeredAt: "2024-09-01", isActive: true,
  },
  {
    id: 4, countryId: "MMR",
    ruleName: "Investment Collapse Warning",
    indicatorCode: "fdi", indicatorLabel: "FDI Net Inflows",
    triggerValue: 0.8, threshold: 2.0, unit: "B USD",
    severity: "warning",
    message: "FDI inflows collapsed to $0.8B — below the $2B warning threshold. Investor confidence near historical lows.",
    triggeredAt: "2024-10-01", isActive: true,
  },

  // ── Cambodia (High Risk) ───────────────────────────────────────
  {
    id: 5, countryId: "KHM",
    ruleName: "Inflation Pressure Alert",
    indicatorCode: "inflation", indicatorLabel: "Inflation Rate (CPI)",
    triggerValue: 5.8, threshold: 5.0, unit: "%",
    severity: "warning",
    message: "Inflation rose to 5.8%, breaching the 5% warning threshold. Food and transport costs are primary drivers.",
    triggeredAt: "2024-11-01", isActive: true,
  },
  {
    id: 6, countryId: "KHM",
    ruleName: "Trade Deficit Stress",
    indicatorCode: "imports", indicatorLabel: "Trade Deficit (Imports − Exports)",
    triggerValue: 3.0, threshold: 2.0, unit: "B USD deficit",
    severity: "warning",
    message: "Trade deficit widened to $3.0B, exceeding the $2B warning threshold. Import dependency on fuel is key driver.",
    triggeredAt: "2024-10-20", isActive: true,
  },
  {
    id: 7, countryId: "KHM",
    ruleName: "Political Risk Elevated",
    indicatorCode: "politicalRiskNews", indicatorLabel: "Political Risk News",
    triggerValue: 48, threshold: 40, unit: "articles/mo",
    severity: "info",
    message: "Political risk news at 48/month, above the 40 watch threshold. Opposition crackdown coverage elevated.",
    triggeredAt: "2024-10-10", isActive: true,
  },
  {
    id: 8, countryId: "KHM",
    ruleName: "FDI Declining Trend",
    indicatorCode: "fdi", indicatorLabel: "FDI Net Inflows",
    triggerValue: 3.2, threshold: 3.5, unit: "B USD",
    severity: "info",
    message: "FDI slipped to $3.2B in 2024, below the $3.5B trend baseline. Governance perceptions may be weighing on investors.",
    triggeredAt: "2024-09-15", isActive: true,
  },

  // ── Thailand (Medium Risk) ─────────────────────────────────────
  {
    id: 9, countryId: "THA",
    ruleName: "Political Risk Watch",
    indicatorCode: "politicalRiskNews", indicatorLabel: "Political Risk News",
    triggerValue: 42, threshold: 40, unit: "articles/mo",
    severity: "info",
    message: "Political risk coverage at 42/month, just above the watch threshold. Parliamentary budget dispute is key driver.",
    triggeredAt: "2024-11-01", isActive: true,
  },
  {
    id: 10, countryId: "THA",
    ruleName: "Currency Weakness Watch",
    indicatorCode: "exchangeRate", indicatorLabel: "Exchange Rate (THB/USD)",
    triggerValue: 33.5, threshold: 32.0, unit: "THB/USD",
    severity: "info",
    message: "THB at 33.5/USD — 4.7% weaker than the 32.0 baseline. Monetary policy and export competitiveness implications.",
    triggeredAt: "2024-10-05", isActive: true,
  },

  // ── Vietnam (Low — resolved) ───────────────────────────────────
  {
    id: 11, countryId: "VNM",
    ruleName: "Currency Pressure Warning",
    indicatorCode: "exchangeRate", indicatorLabel: "Exchange Rate (VND/USD)",
    triggerValue: 24500, threshold: 24000, unit: "VND/USD",
    severity: "warning",
    message: "VND weakened to 24,500/USD, above the 24,000 threshold. State Bank intervention stabilised the rate.",
    triggeredAt: "2024-11-18", isActive: false,
  },
  {
    id: 12, countryId: "VNM",
    ruleName: "Import Surge Watch",
    indicatorCode: "imports", indicatorLabel: "Total Imports",
    triggerValue: 338, threshold: 320, unit: "B USD",
    severity: "info",
    message: "Imports rose to $338B, above the $320B watch level. Capital goods imports for manufacturing expansion are primary driver.",
    triggeredAt: "2024-10-15", isActive: true,
  },

  // ── Singapore (Low — info only) ───────────────────────────────
  {
    id: 13, countryId: "SGP",
    ruleName: "Growth Below Trend",
    indicatorCode: "gdpGrowth", indicatorLabel: "GDP Growth Rate",
    triggerValue: 1.2, threshold: 2.0, unit: "%",
    severity: "info",
    message: "GDP growth at 1.2%, below Singapore's long-run 2% trend. External demand weakness and China slowdown are noted risks.",
    triggeredAt: "2024-10-25", isActive: true,
  },
];

// ─────────────────────────────────────────────────────────────────
// HELPER FUNCTIONS
// ─────────────────────────────────────────────────────────────────

/** Look up a country by its ISO-3 id */
export function getCountry(id: string): Country | undefined {
  return COUNTRIES.find(c => c.id === id.toUpperCase());
}

/**
 * Build the data array used by CompareBarChart for a given metric.
 * Returns one row per country, sorted by the metric value descending.
 */
export function getCompareData(metric: MetricKey): CompareRow[] {
  return COUNTRIES.map(c => ({
    countryId:   c.id,
    countryName: c.shortName,
    flagEmoji:   c.flagEmoji,
    value:       CURRENT_INDICATORS[c.id][metric],
    riskLevel:   c.riskLevel,
  })).sort((a, b) => b.value - a.value);
}

/**
 * Returns the year-over-year change for an indicator.
 * Compares the last two points in the historical series.
 */
export function getYoYChange(countryId: string, metric: MetricKey): number {
  const hist = HISTORICAL[countryId]?.[metric] ?? [];
  if (hist.length < 2) return 0;
  return hist[hist.length - 1].value - hist[hist.length - 2].value;
}
