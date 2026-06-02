/**
 * frontend/data/gdelt-news.ts
 *
 * Imports the GDELT news JSON produced by pipeline/fetch_gdelt_mvp.py
 * and converts it into NewsEvent objects that the News Impact Feed can display.
 *
 * HOW IT WORKS
 * ------------
 * 1. `fetch_gdelt_mvp.py` writes to:
 *      pipeline/output/json/gdelt_news_events.json
 * 2. This file imports that JSON at build time (Next.js resolves the import).
 * 3. The News page merges GDELT_NEWS_EVENTS with the static NEWS_EVENTS.
 *
 * RE-RUNNING THE PIPELINE
 * -----------------------
 *    cd pipeline && python fetch_gdelt_mvp.py
 * Then refresh the Next.js dev server — it hot-reloads JSON imports.
 *
 * IF THE JSON FILE DOESN'T EXIST YET
 * ------------------------------------
 * The fallback at the bottom exports an empty array so the page still renders.
 * Run the pipeline script first to populate real data.
 */

import type { NewsEvent } from "@/data/sample-data";

// ── Type from the Python script's output ─────────────────────────────────────

interface GdeltArticle {
  id:                  number;
  countryId:           string;
  headline:            string;
  summary:             string;
  category:            string;
  sentiment:           "positive" | "neutral" | "negative";
  sentimentScore:      number;
  publishedAt:         string;
  sourceName:          string;
  impactLevel:         number;
  impactedIndicators:  string[];
  gdeltUrl?:           string;
  gdeltTone?:          number;
  gdeltArticleId?:     string;
  fetchedAt?:          string;
}

interface GdeltOutput {
  generated_at:    string;
  total_articles:  number;
  articles:        GdeltArticle[];
}

// ── Load JSON (Next.js resolves this at build/hot-reload time) ────────────────
// The path is relative to the project root. If the file does not exist yet,
// the catch block returns an empty placeholder.

let rawOutput: GdeltOutput = { generated_at: "", total_articles: 0, articles: [] };

try {
  // This import is resolved statically by Next.js bundler.
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const imported = require("../../pipeline/output/json/gdelt_news_events.json") as GdeltOutput;
  rawOutput = imported;
} catch {
  // File not yet generated — run: cd pipeline && python fetch_gdelt_mvp.py
  console.warn(
    "[gdelt-news] gdelt_news_events.json not found. " +
    "Run: cd pipeline && python fetch_gdelt_mvp.py"
  );
}

// ── Convert to NewsEvent (valid category union) ───────────────────────────────

const VALID_CATEGORIES = new Set([
  "economy", "politics", "trade", "security", "disaster",
  "conflict", "protest", "policy", "infrastructure", "technology",
]);

function toNewsEvent(a: GdeltArticle, offset: number): NewsEvent {
  // Clamp category to known values; fall back to "politics"
  const cat = VALID_CATEGORIES.has(a.category)
    ? (a.category as NewsEvent["category"])
    : "politics";

  return {
    id:                  a.id + offset,      // avoid ID clash with static data
    countryId:           a.countryId,
    headline:            a.headline,
    summary:             a.summary,
    category:            cat,
    sentiment:           a.sentiment,
    sentimentScore:      a.sentimentScore,
    publishedAt:         a.publishedAt,
    sourceName:          a.sourceName,
    impactLevel:         a.impactLevel,
    impactedIndicators:  a.impactedIndicators,
    gdeltUrl:            a.gdeltUrl,
    gdeltTone:           a.gdeltTone,
    source:              "gdelt",
  };
}

// ID offset so GDELT IDs don't clash with static sample data (which goes up to 25)
const ID_OFFSET = 1000;

/** All GDELT articles as NewsEvent objects, ready for the News page. */
export const GDELT_NEWS_EVENTS: NewsEvent[] =
  rawOutput.articles.map((a, i) => toNewsEvent(a, ID_OFFSET));

/** When the GDELT data was last fetched (ISO string, empty if not fetched yet). */
export const GDELT_GENERATED_AT: string = rawOutput.generated_at;

/** Total article count from GDELT (may differ from GDELT_NEWS_EVENTS.length after dedup). */
export const GDELT_TOTAL: number = rawOutput.total_articles;
