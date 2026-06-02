#!/usr/bin/env python3
"""
==============================================================================
GDELT News Signal Fetcher — SEA Change Dashboard
==============================================================================
Fetches recent news articles from the GDELT 2.0 Document API for 10 ASEAN
countries, classifies each article into event categories, assigns an impact
score, and saves the results as CSV and JSON files.

No API key required. GDELT is completely free and open.

WHAT IS GDELT?
--------------
The Global Database of Events, Language and Tone (GDELT) monitors the world's
broadcast, print, and web news from nearly every corner of every country in
over 100 languages. It makes the full text of news articles searchable via
a free API.

API USED: GDELT 2.0 Document (Context) API
  Base URL: https://api.gdeltproject.org/api/v2/doc/doc
  Mode    : artlist  (returns article metadata + tone)
  No auth, no key, no cost.

USAGE
-----
    pip install httpx
    python pipeline/fetch_gdelt.py

    # Or for a specific number of days back:
    python pipeline/fetch_gdelt.py --days 14

OUTPUT (saved to pipeline/output/)
------------------------------------
    gdelt_articles_YYYYMMDD.csv     All articles, one row per article
    gdelt_articles_YYYYMMDD.json    Same data in JSON (for the dashboard API)
    gdelt_summary_YYYYMMDD.csv      Per-country category breakdown

LIMITATIONS
-----------
1. MAX 250 articles per query — GDELT API hard cap. For high-activity countries
   (Thailand, Vietnam) you may hit this limit within 7 days. Use shorter
   timespans or multiple filtered queries if needed.

2. TITLE-ONLY CLASSIFICATION — The API returns article titles, not full text.
   Classification is keyword-based on the title + URL domain. Accuracy is
   ~70–80%. Full-text classification requires scraping individual URLs.

3. TONE IS ARTICLE-LEVEL — The tone score is computed from the entire article,
   not just the passage about the country. A positive article about an
   economic deal may mention conflict in passing, affecting tone.

4. ENGLISH BIAS — GDELT indexes all languages but English sources dominate.
   Set sourcelang='all' (default) to include Thai, Burmese, Vietnamese sources,
   but expect most results to be English.

5. BRUNEI COVERAGE — Brunei generates very few GDELT-indexed articles.
   Fewer than 5–10 results per week is normal.

6. MYANMAR POST-2021 — Many Myanmar state media sources are no longer indexed.
   Coverage skews toward international/opposition sources.
==============================================================================
"""

import httpx
import csv
import json
import time
import sys
import re
import argparse
from pathlib import Path
from datetime import datetime, timedelta, timezone


# ── OUTPUT DIRECTORY ────────────────────────────────────────────────────────
OUT_DIR = Path(__file__).parent / "output"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── GDELT API CONFIG ────────────────────────────────────────────────────────
GDELT_DOC_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
MAX_RECORDS   = 250      # GDELT hard cap per request
REQUEST_DELAY = 3.0      # seconds between country requests — GDELT enforces rate limits;
                         # 3s is safe for 10 sequential requests. Do NOT reduce below 2s.
MAX_RETRIES   = 4        # includes exponential back-off on 429 Too Many Requests


# ── COUNTRY DEFINITIONS ─────────────────────────────────────────────────────
# Each country has:
#   iso3      — used as the country_id in the dashboard
#   name      — display name
#   flag      — emoji flag
#   keywords  — search terms that identify articles about this country
#               Enclose multi-word phrases in quotes for GDELT's query syntax
COUNTRIES = {
    "MMR": {
        "name":     "Myanmar",
        "flag":     "🇲🇲",
        "keywords": ['Myanmar', 'Burma', 'Burmese', '"Yangon"', '"Naypyidaw"', 'SAC', '"NUG"'],
    },
    "THA": {
        "name":     "Thailand",
        "flag":     "🇹🇭",
        "keywords": ['Thailand', 'Thai', '"Bangkok"', '"Chiang Mai"'],
    },
    "VNM": {
        "name":     "Vietnam",
        "flag":     "🇻🇳",
        "keywords": ['Vietnam', 'Vietnamese', '"Hanoi"', '"Ho Chi Minh"'],
    },
    "KHM": {
        "name":     "Cambodia",
        "flag":     "🇰🇭",
        "keywords": ['Cambodia', 'Cambodian', '"Phnom Penh"', 'Khmer'],
    },
    "LAO": {
        "name":     "Laos",
        "flag":     "🇱🇦",
        "keywords": ['Laos', 'Laotian', '"Vientiane"', '"Lao PDR"'],
    },
    "MYS": {
        "name":     "Malaysia",
        "flag":     "🇲🇾",
        "keywords": ['Malaysia', 'Malaysian', '"Kuala Lumpur"'],
    },
    "SGP": {
        "name":     "Singapore",
        "flag":     "🇸🇬",
        "keywords": ['Singapore', 'Singaporean'],
    },
    "IDN": {
        "name":     "Indonesia",
        "flag":     "🇮🇩",
        "keywords": ['Indonesia', 'Indonesian', '"Jakarta"', 'Prabowo'],
    },
    "PHL": {
        "name":     "Philippines",
        "flag":     "🇵🇭",
        "keywords": ['Philippines', 'Filipino', '"Manila"', 'Marcos'],
    },
    "BRN": {
        "name":     "Brunei",
        "flag":     "🇧🇳",
        "keywords": ['Brunei', '"Bandar Seri Begawan"'],
    },
}


# ── CATEGORY KEYWORD MAP ────────────────────────────────────────────────────
# Categories listed in priority order — first match wins.
# Put more specific categories (tariff, election) BEFORE generic ones (trade, politics).
# All keywords are checked against the lowercase article title.
CATEGORIES: list[tuple[str, list[str]]] = [
    ("conflict", [
        "military", "coup", "airstrike", "troops", "armed conflict",
        "fighting", "soldiers", "junta", "resistance", "killed", "massacre",
        "offensive", "ceasefire", "rebel", "insurgent", "militia", "war",
        "attack", "clashes", "artillery", "siege", "ambush", "IDP",
        "internally displaced",
    ]),
    ("election", [
        "election", "vote", "voting", "ballot", "polling", "campaign",
        "candidate", "electoral", "referendum", "by-election", "general election",
        "voter", "polling day", "landslide", "poll results",
    ]),
    ("protest", [
        "protest", "demonstration", "rally", "march", "strike", "riot",
        "unrest", "demonstrators", "dissent", "crackdown", "activist",
        "civil disobedience", "sit-in", "crowd", "detain", "arrested protesters",
    ]),
    ("natural_disaster", [
        "flood", "typhoon", "earthquake", "cyclone", "drought", "storm",
        "landslide", "tsunami", "eruption", "wildfire", "hurricane",
        "flash flood", "disaster relief", "evacuation", "rescue operation",
        "tropical storm", "monsoon flooding",
    ]),
    ("tariff", [
        "tariff", "sanction", "trade war", "import ban", "export ban",
        "embargo", "trade barrier", "protectionism", "customs duty",
        "countervailing", "anti-dumping",
    ]),
    ("central_bank_policy", [
        "interest rate", "central bank", "monetary policy", "rate hike",
        "rate cut", "bank rate", "quantitative", "reserve requirement",
        "exchange rate", "devaluation", "currency peg", "bank negara",
        "bangko sentral", "bank of thailand",
    ]),
    ("border", [
        "border", "immigration", "asylum", "refugee", "crossing",
        "smuggling", "checkpoint", "migration", "illegal crossing",
        "border closure", "passport", "visa restriction", "port of entry",
    ]),
    ("infrastructure", [
        "highway", "railway", "expressway", "port", "dam", "bridge",
        "power plant", "airport", "pipeline", "canal", "energy project",
        "infrastructure investment", "construction project", "megaproject",
    ]),
    ("technology", [
        "artificial intelligence", "semiconductor", "chip", "5g",
        "fintech", "e-commerce", "startup", "data center", "cybersecurity",
        "digital economy", "tech company", "software", "innovation hub",
        "ai investment",
    ]),
    ("trade", [
        "trade deal", "trade agreement", "free trade", "bilateral trade",
        "export", "import", "supply chain", "fdi", "foreign investment",
        "manufacturing", "factory", "trade volume", "commerce",
    ]),
    ("economy", [
        "gdp", "economic growth", "recession", "debt", "budget deficit",
        "fiscal", "revenue", "poverty", "unemployment", "inflation",
        "stock market", "bond market", "financial crisis", "imf",
        "world bank loan",
    ]),
    ("politics", [
        "government", "president", "prime minister", "cabinet", "minister",
        "parliament", "senate", "diplomacy", "bilateral", "summit",
        "treaty", "foreign policy", "geopolitics", "sanctions",
        "political", "coalition",
    ]),
]

# Default category if no keywords match
DEFAULT_CATEGORY = "general"


# ── IMPACT SCORING RULES ────────────────────────────────────────────────────
# Base score by category (1–5 scale)
CATEGORY_BASE_SCORE: dict[str, int] = {
    "conflict":            5,
    "natural_disaster":    4,
    "election":            4,
    "protest":             3,
    "tariff":              3,
    "central_bank_policy": 3,
    "border":              3,
    "trade":               2,
    "technology":          2,
    "infrastructure":      2,
    "economy":             2,
    "politics":            2,
    "general":             1,
}

# Words that boost impact score by +1 (regardless of category)
CRISIS_WORDS = [
    "crisis", "collapse", "coup", "explosion", "explosion",
    "death toll", "casualties", "killed", "emergency", "critical",
    "record high", "record low", "unprecedented",
]

# Words that reduce impact score by -1 (routine or positive low-urgency news)
ROUTINE_WORDS = [
    "opens", "inaugurates", "celebrates", "tourism", "culture",
    "award", "festival", "announces plan", "signs agreement",
]


# ── GDELT API FUNCTIONS ─────────────────────────────────────────────────────

def build_gdelt_query(country_iso3: str, days: int = 7) -> str:
    """
    Build the GDELT search query string for one country.

    GDELT query syntax:
      - Terms are OR'd by default if separated by spaces
      - Exact phrases in double quotes: "Kuala Lumpur"
      - AND operator: term1 AND term2
      - NOT operator: -term (minus prefix)

    Returns the full URL for the GDELT API request.
    """
    country = COUNTRIES[country_iso3]
    # Join keywords with OR — this finds articles mentioning ANY of these terms
    query_terms = " OR ".join(country["keywords"])

    params = {
        "query":      query_terms,
        "mode":       "artlist",        # return article list (not timeline)
        "maxrecords": MAX_RECORDS,
        "timespan":   f"{days}d",       # last N days
        "format":     "json",
        "sort":       "DateDesc",       # newest first
    }

    # Build URL query string manually for clarity
    param_str = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{GDELT_DOC_URL}?{param_str}"


def fetch_country_articles(country_iso3: str, days: int) -> list[dict]:
    """
    Fetch articles for one country from GDELT API.
    Returns a list of raw article dicts from the API.
    Retries up to MAX_RETRIES times on failure.
    """
    url = build_gdelt_query(country_iso3, days)
    country_name = COUNTRIES[country_iso3]["name"]

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = httpx.get(url, timeout=30, follow_redirects=True)
            response.raise_for_status()

            # GDELT sometimes returns HTML error pages instead of JSON
            content_type = response.headers.get("content-type", "")
            if "json" not in content_type and not response.text.startswith("{"):
                print(f"    ⚠  Non-JSON response for {country_name} (attempt {attempt})")
                time.sleep(2 ** attempt)
                continue

            data = response.json()
            articles = data.get("articles", [])
            return articles

        except httpx.HTTPStatusError as e:
            code = e.response.status_code
            if code == 429:
                # GDELT rate limit — wait longer before retrying
                wait = 30 * attempt   # 30s, 60s, 90s…
                print(f"    ⚠  Rate limited (429). Waiting {wait}s before retry {attempt}/{MAX_RETRIES}…")
                time.sleep(wait)
                continue
            print(f"    ✗  HTTP {code} for {country_name} (attempt {attempt})")
        except httpx.RequestError as e:
            print(f"    ✗  Connection error for {country_name}: {e} (attempt {attempt})")
        except json.JSONDecodeError:
            print(f"    ✗  Invalid JSON for {country_name} (attempt {attempt})")

        if attempt < MAX_RETRIES:
            wait = 2 ** attempt   # 2s, 4s, 8s for non-429 errors
            print(f"    ↻  Retry in {wait}s…")
            time.sleep(wait)

    return []   # all retries failed


# ── ARTICLE PARSING ─────────────────────────────────────────────────────────

def parse_gdelt_date(date_str: str) -> str:
    """
    Convert GDELT date format to ISO 8601.
    GDELT format: "20241201T120000Z"
    Output:       "2024-12-01T12:00:00Z"
    """
    try:
        dt = datetime.strptime(date_str, "%Y%m%dT%H%M%SZ")
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, TypeError):
        return date_str or ""


def parse_article(raw: dict, country_iso3: str) -> dict:
    """
    Parse a single raw GDELT article dict into a clean structured dict.
    Handles missing fields gracefully.
    """
    title       = raw.get("title", "").strip()
    url         = raw.get("url", "")
    domain      = raw.get("domain", "")
    language    = raw.get("language", "Unknown")
    sourcecountry = raw.get("sourcecountry", "")
    seen_date   = parse_gdelt_date(raw.get("seendate", ""))
    tone        = raw.get("tone")   # float or None

    return {
        "article_id":      _make_article_id(url),
        "country_iso3":    country_iso3,
        "country_name":    COUNTRIES[country_iso3]["name"],
        "title":           title,
        "url":             url,
        "domain":          domain,
        "source_country":  sourcecountry,
        "language":        language,
        "published_at":    seen_date,
        "tone":            round(float(tone), 3) if tone is not None else None,
        # These will be filled in by classify_article():
        "sentiment":       None,
        "category":        None,
        "impact_score":    None,
    }


def _make_article_id(url: str) -> str:
    """Create a short stable ID from the URL (for deduplication in PostgreSQL)."""
    import hashlib
    return hashlib.md5(url.encode()).hexdigest()[:16]


# ── CLASSIFICATION ───────────────────────────────────────────────────────────

def classify_article(article: dict) -> dict:
    """
    Classify an article into a category and compute its impact score.

    Strategy:
    1. Lowercase the title + domain for keyword matching.
    2. Walk through CATEGORIES in priority order — first match wins.
    3. Compute impact score from category base + tone intensity + crisis words.
    4. Derive sentiment from the tone float.

    Modifies the article dict in place and returns it.
    """
    search_text = (article["title"] + " " + article["domain"]).lower()

    # ── Category ────────────────────────────────────────────────────────────
    matched_category = DEFAULT_CATEGORY
    for category, keywords in CATEGORIES:
        if any(kw.lower() in search_text for kw in keywords):
            matched_category = category
            break
    article["category"] = matched_category

    # ── Sentiment from tone ──────────────────────────────────────────────────
    # GDELT tone: typically -10 to +10, negative = negative sentiment
    tone = article.get("tone")
    if tone is None:
        article["sentiment"] = "neutral"
    elif tone > 2.0:
        article["sentiment"] = "positive"
    elif tone < -2.0:
        article["sentiment"] = "negative"
    else:
        article["sentiment"] = "neutral"

    # ── Impact Score (1–5) ───────────────────────────────────────────────────
    base   = CATEGORY_BASE_SCORE.get(matched_category, 1)
    bonus  = 0
    title_lower = article["title"].lower()

    # +1 if tone is strongly negative/positive (high emotional intensity)
    if tone is not None and abs(tone) > 10:
        bonus += 1

    # +1 if a crisis keyword is in the title
    if any(w in title_lower for w in CRISIS_WORDS):
        bonus += 1

    # -1 if it's a routine announcement (not urgent)
    if any(w in title_lower for w in ROUTINE_WORDS):
        bonus -= 1

    article["impact_score"] = max(1, min(5, base + bonus))
    return article


# ── DEDUPLICATION ────────────────────────────────────────────────────────────

def deduplicate(articles: list[dict]) -> list[dict]:
    """
    Remove articles with duplicate URLs.
    GDELT can return the same article when it matches multiple country queries.
    """
    seen_urls: set[str] = set()
    unique: list[dict] = []
    for a in articles:
        if a["url"] not in seen_urls:
            seen_urls.add(a["url"])
            unique.append(a)
    return unique


# ── OUTPUT FUNCTIONS ─────────────────────────────────────────────────────────

CSV_FIELDS = [
    "article_id", "country_iso3", "country_name", "published_at",
    "title", "url", "domain", "source_country", "language",
    "tone", "sentiment", "category", "impact_score",
]


def save_csv(articles: list[dict], path: Path) -> None:
    """Save all articles to a CSV file (flat, one row per article)."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for a in sorted(articles, key=lambda x: (x["country_iso3"], x["published_at"] or "")):
            writer.writerow(a)
    print(f"  ✓  CSV  →  {path.name}  ({len(articles)} articles)")


def save_json(articles: list[dict], path: Path) -> None:
    """
    Save articles as JSON, grouped by country.
    This is the format the dashboard API consumes directly.

    Output structure:
    {
      "generated_at": "2024-12-01T12:00:00Z",
      "total_articles": 420,
      "countries": {
        "MMR": {
          "country_name": "Myanmar",
          "article_count": 87,
          "articles": [ { ... } ]
        },
        ...
      }
    }
    """
    # Group by country
    by_country: dict[str, list[dict]] = {}
    for a in articles:
        iso3 = a["country_iso3"]
        by_country.setdefault(iso3, []).append(a)

    output = {
        "generated_at":   datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total_articles": len(articles),
        "countries": {
            iso3: {
                "country_name":  COUNTRIES[iso3]["name"],
                "article_count": len(arts),
                "articles":      arts,
            }
            for iso3, arts in sorted(by_country.items())
        },
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"  ✓  JSON →  {path.name}  ({len(articles)} articles, {len(by_country)} countries)")


def save_summary_csv(articles: list[dict], path: Path) -> None:
    """
    Save a per-country category breakdown CSV.
    Useful for the dashboard's 'news signal' summary cards.
    """
    # Count articles per country × category
    counts: dict[tuple, int] = {}
    neg_counts: dict[tuple, int] = {}
    for a in articles:
        key = (a["country_iso3"], a["country_name"], a["category"])
        counts[key]     = counts.get(key, 0) + 1
        if a["sentiment"] == "negative":
            neg_counts[key] = neg_counts.get(key, 0) + 1

    rows = []
    for (iso3, name, cat), total in sorted(counts.items()):
        neg = neg_counts.get((iso3, name, cat), 0)
        rows.append({
            "country_iso3":       iso3,
            "country_name":       name,
            "category":           cat,
            "article_count":      total,
            "negative_count":     neg,
            "negative_share_pct": round(100 * neg / total, 1) if total else 0,
        })

    fields = ["country_iso3", "country_name", "category",
              "article_count", "negative_count", "negative_share_pct"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"  ✓  Summary CSV → {path.name}  ({len(rows)} country-category rows)")


def print_summary(articles: list[dict]) -> None:
    """Print a human-readable summary table to the console."""
    if not articles:
        print("  No articles fetched.")
        return

    print()
    print(f"  {'Country':<14} {'Articles':>9}  {'Neg%':>5}  Top Categories")
    print(f"  {'-'*65}")

    for iso3, meta in COUNTRIES.items():
        country_arts = [a for a in articles if a["country_iso3"] == iso3]
        if not country_arts:
            print(f"  {meta['flag']} {meta['name']:<12} {'0':>9}  {'–':>5}  (no results)")
            continue

        neg_count = sum(1 for a in country_arts if a["sentiment"] == "negative")
        neg_pct   = round(100 * neg_count / len(country_arts))

        # Top 3 categories by frequency
        cat_counts: dict[str, int] = {}
        for a in country_arts:
            cat_counts[a["category"]] = cat_counts.get(a["category"], 0) + 1
        top_cats = sorted(cat_counts, key=lambda c: -cat_counts[c])[:3]
        top_str  = ", ".join(f"{c}({cat_counts[c]})" for c in top_cats)

        print(f"  {meta['flag']} {meta['name']:<12} {len(country_arts):>9}  {neg_pct:>4}%  {top_str}")

    print()
    total        = len(articles)
    total_neg    = sum(1 for a in articles if a["sentiment"] == "negative")
    avg_impact   = sum(a["impact_score"] for a in articles) / total if total else 0
    high_impact  = sum(1 for a in articles if (a["impact_score"] or 0) >= 4)

    print(f"  Total articles : {total}")
    print(f"  Negative tone  : {total_neg} ({round(100*total_neg/total if total else 0)}%)")
    print(f"  High impact (≥4): {high_impact}")
    print(f"  Avg impact score: {avg_impact:.2f}")


# ── POSTGRESQL GUIDANCE ──────────────────────────────────────────────────────

POSTGRES_SCHEMA = """
-- ============================================================
-- HOW TO STORE GDELT ARTICLES IN POSTGRESQL
-- ============================================================
-- Run this SQL in your Supabase SQL editor or psql to create
-- the table, then use the Python loader below to insert data.

CREATE TABLE IF NOT EXISTS news_events_gdelt (
    article_id      TEXT         PRIMARY KEY,   -- MD5 hash of URL (deduplication key)
    country_iso3    CHAR(3)      NOT NULL REFERENCES countries(id),
    country_name    TEXT         NOT NULL,
    published_at    TIMESTAMPTZ,
    title           TEXT         NOT NULL,
    url             TEXT         UNIQUE NOT NULL,
    domain          TEXT,
    source_country  TEXT,
    language        TEXT,
    tone            NUMERIC(6,3),               -- GDELT tone float, -100 to +100
    sentiment       TEXT CHECK (sentiment IN ('positive','neutral','negative')),
    category        TEXT,
    impact_score    SMALLINT CHECK (impact_score BETWEEN 1 AND 5),
    fetched_at      TIMESTAMPTZ  DEFAULT NOW()
);

-- Indexes for common dashboard queries
CREATE INDEX IF NOT EXISTS idx_gdelt_country  ON news_events_gdelt (country_iso3);
CREATE INDEX IF NOT EXISTS idx_gdelt_date     ON news_events_gdelt (published_at DESC);
CREATE INDEX IF NOT EXISTS idx_gdelt_cat      ON news_events_gdelt (category);
CREATE INDEX IF NOT EXISTS idx_gdelt_impact   ON news_events_gdelt (impact_score DESC);

-- ============================================================
-- PYTHON LOADER SNIPPET (add to pipeline/loaders/db_loader.py)
-- ============================================================
-- import psycopg2, csv
-- from psycopg2.extras import execute_values
--
-- def load_gdelt_articles(csv_path: str, db_url: str) -> int:
--     rows = []
--     with open(csv_path, newline='', encoding='utf-8') as f:
--         for row in csv.DictReader(f):
--             rows.append((
--                 row['article_id'], row['country_iso3'], row['country_name'],
--                 row['published_at'] or None, row['title'], row['url'],
--                 row['domain'], row['source_country'], row['language'],
--                 float(row['tone']) if row['tone'] else None,
--                 row['sentiment'], row['category'],
--                 int(row['impact_score']) if row['impact_score'] else None,
--             ))
--
--     with psycopg2.connect(db_url) as conn:
--         with conn.cursor() as cur:
--             execute_values(cur, '''
--                 INSERT INTO news_events_gdelt
--                     (article_id, country_iso3, country_name, published_at,
--                      title, url, domain, source_country, language,
--                      tone, sentiment, category, impact_score)
--                 VALUES %s
--                 ON CONFLICT (url) DO NOTHING   -- skip duplicates
--             ''', rows)
--         conn.commit()
--     return len(rows)
"""


def print_postgres_guide() -> None:
    """Print the PostgreSQL storage guide to the console."""
    print("\n" + "=" * 65)
    print("  POSTGRESQL STORAGE GUIDE")
    print("=" * 65)
    print(POSTGRES_SCHEMA)
    print("=" * 65)


# ── MAIN ─────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch GDELT news signals for ASEAN countries"
    )
    parser.add_argument(
        "--days", type=int, default=7,
        help="Number of days to look back (default: 7, max: 30 for free tier)"
    )
    parser.add_argument(
        "--country", type=str, default=None,
        help="Fetch only one country (e.g. --country VNM). Default: all 10."
    )
    parser.add_argument(
        "--postgres", action="store_true",
        help="Print PostgreSQL schema and loader guide"
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.postgres:
        print_postgres_guide()
        return

    today_str = datetime.today().strftime("%Y%m%d")

    print()
    print("╔══════════════════════════════════════════════════════╗")
    print("║   SEA Change Dashboard — GDELT News Fetcher          ║")
    print("╚══════════════════════════════════════════════════════╝")
    print(f"  Days back : {args.days}")
    print(f"  Countries : {len(COUNTRIES) if not args.country else 1}")
    print(f"  Max/query : {MAX_RECORDS} articles")
    print(f"  Output    : {OUT_DIR}/")
    print()

    # ── Which countries to fetch ──────────────────────────────────────────
    if args.country:
        target_iso3s = [args.country.upper()]
        if target_iso3s[0] not in COUNTRIES:
            print(f"  ✗  Unknown country: {args.country}")
            print(f"     Valid options: {', '.join(COUNTRIES.keys())}")
            sys.exit(1)
    else:
        target_iso3s = list(COUNTRIES.keys())

    # ── Step 1: Fetch ─────────────────────────────────────────────────────
    print("[ STEP 1 ] Fetching from GDELT 2.0 Doc API …")
    print(f"  URL: {GDELT_DOC_URL}?query=...&mode=artlist&maxrecords={MAX_RECORDS}\n")

    all_articles: list[dict] = []

    for i, iso3 in enumerate(target_iso3s, 1):
        meta = COUNTRIES[iso3]
        print(f"  [{i}/{len(target_iso3s)}] {meta['flag']} {meta['name']} …", end="", flush=True)

        raw_articles = fetch_country_articles(iso3, args.days)
        parsed = [parse_article(r, iso3) for r in raw_articles]

        print(f"  {len(parsed)} articles")
        all_articles.extend(parsed)

        if i < len(target_iso3s):
            time.sleep(REQUEST_DELAY)   # be polite to the API

    print(f"\n  Total fetched : {len(all_articles)}")

    # ── Step 2: Deduplicate ───────────────────────────────────────────────
    before = len(all_articles)
    all_articles = deduplicate(all_articles)
    dupes_removed = before - len(all_articles)
    if dupes_removed:
        print(f"  Duplicates removed: {dupes_removed}")

    if not all_articles:
        print("\n  ✗  No articles fetched. Check your internet connection.")
        print("     GDELT can also have temporary outages. Try again in a few minutes.")
        sys.exit(1)

    # ── Step 3: Classify ──────────────────────────────────────────────────
    print("\n[ STEP 2 ] Classifying articles …")
    for a in all_articles:
        classify_article(a)

    # Category distribution
    cat_dist: dict[str, int] = {}
    for a in all_articles:
        cat_dist[a["category"]] = cat_dist.get(a["category"], 0) + 1
    print("  Category distribution:")
    for cat, count in sorted(cat_dist.items(), key=lambda x: -x[1]):
        bar = "█" * (count // 3)
        print(f"    {cat:<24} {count:>4}  {bar}")

    # ── Step 4: Save outputs ──────────────────────────────────────────────
    print(f"\n[ STEP 3 ] Saving output files …")
    save_csv(all_articles,
             OUT_DIR / f"gdelt_articles_{today_str}.csv")
    save_json(all_articles,
              OUT_DIR / f"gdelt_articles_{today_str}.json")
    save_summary_csv(all_articles,
                     OUT_DIR / f"gdelt_summary_{today_str}.csv")

    # ── Step 5: Print summary ─────────────────────────────────────────────
    print("\n[ STEP 4 ] Results summary:")
    print_summary(all_articles)

    # ── High impact alerts ────────────────────────────────────────────────
    high_impact = [
        a for a in all_articles
        if (a["impact_score"] or 0) >= 4 and a["sentiment"] == "negative"
    ]
    if high_impact:
        print(f"  ⚑  TOP HIGH-IMPACT NEGATIVE SIGNALS:")
        for a in sorted(high_impact, key=lambda x: -(x["impact_score"] or 0))[:8]:
            flag = COUNTRIES[a["country_iso3"]]["flag"]
            print(f"     [{a['impact_score']}★] {flag} {a['country_name']} · {a['category']}")
            print(f"          {a['title'][:85]}")

    # ── Done ──────────────────────────────────────────────────────────────
    print()
    print("╔══════════════════════════════════════════════════════╗")
    print("║  ✓  Done. Useful next commands:                      ║")
    print("║                                                      ║")
    print("║  Load into PostgreSQL:                               ║")
    print("║    python fetch_gdelt.py --postgres                  ║")
    print("║                                                      ║")
    print("║  Fetch only one country:                             ║")
    print("║    python fetch_gdelt.py --country VNM               ║")
    print("║                                                      ║")
    print("║  Fetch last 14 days:                                 ║")
    print("║    python fetch_gdelt.py --days 14                   ║")
    print("╚══════════════════════════════════════════════════════╝")
    print()


if __name__ == "__main__":
    main()
