#!/usr/bin/env python3
"""
==============================================================================
  GDELT News Signal Fetcher — SEA Dashboard MVP
  pipeline/fetch_gdelt_mvp.py
==============================================================================

Fetches recent news from the GDELT 2.0 Document API for 5 SEA countries,
classifies each article into one of 9 categories, assigns an impact score,
connects each article to affected economic indicators, and saves output
in a format the frontend can consume directly.

No API key required — GDELT is completely free and open.

USAGE
-----
    cd pipeline
    python fetch_gdelt_mvp.py              # last 7 days, all 5 countries
    python fetch_gdelt_mvp.py --days 14    # last 14 days
    python fetch_gdelt_mvp.py --country VNM   # single country

OUTPUT FILES (saved to pipeline/output/)
-----------------------------------------
    gdelt_news_events.json          Dashboard-ready array (direct frontend import)
    gdelt_articles_YYYYMMDD.csv     Flat CSV, one row per article
    gdelt_summary_YYYYMMDD.csv      Per-country × per-category breakdown

WHAT GDELT IS
--------------
The Global Database of Events, Language and Tone (GDELT) monitors news from
nearly every country in 100+ languages and makes it searchable via a free API.
We use the GDELT 2.0 Document (Context) API:
  https://api.gdeltproject.org/api/v2/doc/doc

LIMITATIONS
-----------
1. TITLE-ONLY — API returns article titles (not full text). Category
   classification is ~70-80% accurate. Summaries are auto-generated.
2. MAX 250 articles per query — GDELT hard cap per request.
3. ENGLISH BIAS — Most results are English even with sourcelang=all.
4. MYANMAR COVERAGE — Post-2021 state media not indexed; skews to
   international sources (Irrawaddy, RFA, AP).
5. TONE SCOPE — GDELT tone is article-wide, not just the SEA passage.
6. RATE LIMIT — Respect REQUEST_DELAY (≥3s). GDELT will throttle you.
==============================================================================
"""

import csv
import json
import time
import sys
import argparse
import re
from pathlib import Path
from datetime import datetime, timezone

try:
    import httpx
    def _http_get(url: str, timeout: int = 30) -> str:
        r = httpx.get(url, timeout=timeout, follow_redirects=True)
        r.raise_for_status()
        return r.text, r.headers.get("content-type", "")
except ImportError:
    import urllib.request
    def _http_get(url: str, timeout: int = 30) -> str:  # type: ignore[misc]
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            ct = r.headers.get("Content-Type", "")
            return r.read().decode("utf-8"), ct


# ──────────────────────────────────────────────────────────────────────────────
#  SECTION 1 — CONFIGURATION
# ──────────────────────────────────────────────────────────────────────────────

GDELT_URL     = "https://api.gdeltproject.org/api/v2/doc/doc"
MAX_RECORDS   = 250    # GDELT hard cap per request
REQUEST_DELAY = 3.5    # seconds between country requests (do not reduce below 2)
MAX_RETRIES   = 4

OUT_DIR = Path(__file__).parent / "output"
OUT_DIR.mkdir(parents=True, exist_ok=True)


# ──────────────────────────────────────────────────────────────────────────────
#  SECTION 2 — COUNTRIES
# ──────────────────────────────────────────────────────────────────────────────

COUNTRIES: dict[str, dict] = {
    "THA": {
        "name":      "Thailand",
        "shortName": "Thailand",
        "flag":      "🇹🇭",
        # Search terms — OR-joined. Quoted phrases match exactly.
        "keywords":  ['Thailand', 'Thai', '"Bangkok"', '"Chiang Mai"', 'NESDC'],
    },
    "VNM": {
        "name":      "Vietnam",
        "shortName": "Vietnam",
        "flag":      "🇻🇳",
        "keywords":  ['Vietnam', 'Vietnamese', '"Hanoi"', '"Ho Chi Minh"', '"Ha Noi"'],
    },
    "MMR": {
        "name":      "Myanmar",
        "shortName": "Myanmar",
        "flag":      "🇲🇲",
        "keywords":  ['Myanmar', 'Burma', 'Burmese', '"Yangon"', '"Naypyidaw"', 'SAC', '"NUG"'],
    },
    "KHM": {
        "name":      "Cambodia",
        "shortName": "Cambodia",
        "flag":      "🇰🇭",
        "keywords":  ['Cambodia', 'Cambodian', '"Phnom Penh"', 'Khmer'],
    },
    "SGP": {
        "name":      "Singapore",
        "shortName": "Singapore",
        "flag":      "🇸🇬",
        "keywords":  ['Singapore', 'Singaporean', 'MAS', '"Lee Hsien Loong"', '"Lawrence Wong"'],
    },
}


# ──────────────────────────────────────────────────────────────────────────────
#  SECTION 3 — THE 9 CATEGORIES
# ──────────────────────────────────────────────────────────────────────────────
# Categories are checked in ORDER — first match wins.
# Put the most SPECIFIC categories first (conflict, disaster) before
# broad ones (politics, economy) to avoid false-positive matches.
#
# Each entry:  (dashboard_category, [keyword_list])
# Keywords are checked against the lowercase article title.

CATEGORY_RULES: list[tuple[str, list[str]]] = [
    ("conflict", [
        "military", "coup", "airstrike", "troops", "armed conflict", "junta",
        "resistance", "killed", "massacre", "offensive", "ceasefire", "rebel",
        "insurgent", "militia", "war", "clashes", "artillery", "siege", "ambush",
        "fighting", "soldiers", "NUG", "SAC", "airstrikes", "bomb", "explosion",
        "IDP", "internally displaced", "refugees", "crackdown on dissent",
    ]),
    ("disaster", [
        "flood", "typhoon", "earthquake", "cyclone", "drought", "storm",
        "landslide", "tsunami", "eruption", "wildfire", "hurricane", "monsoon",
        "flash flood", "disaster relief", "evacuation", "rescue operation",
        "tropical storm", "heat wave", "air quality", "haze", "smog",
    ]),
    ("protest", [
        "protest", "demonstration", "rally", "march", "strike", "riot",
        "unrest", "demonstrators", "dissent", "activist", "civil disobedience",
        "sit-in", "arrested protesters", "student protest", "pro-democracy",
        "anti-government", "crowd gathered",
    ]),
    ("policy", [
        "central bank", "monetary policy", "interest rate", "rate hike", "rate cut",
        "bank rate", "quantitative easing", "reserve requirement", "devaluation",
        "currency peg", "fiscal policy", "government budget", "tax reform",
        "subsidy", "stimulus", "debt ceiling", "IMF", "World Bank loan",
        "government spending", "bank of thailand", "state bank of vietnam",
        "MAS", "monetary authority",
    ]),
    ("infrastructure", [
        "highway", "railway", "expressway", "port", "dam", "bridge",
        "power plant", "airport", "pipeline", "canal", "energy project",
        "infrastructure investment", "construction project", "megaproject",
        "BRI", "belt and road", "smart city", "grid", "power grid",
        "water treatment", "logistics hub",
    ]),
    ("technology", [
        "artificial intelligence", "AI", "semiconductor", "chip", "5G",
        "fintech", "e-commerce", "startup", "data center", "cybersecurity",
        "digital economy", "tech company", "software", "innovation",
        "digital transformation", "EV", "electric vehicle", "solar", "renewable",
        "tech investment", "fab", "microchip",
    ]),
    ("trade", [
        "trade deal", "trade agreement", "free trade", "bilateral trade",
        "export growth", "import surge", "supply chain", "FDI",
        "foreign investment", "manufacturing", "factory", "tariff",
        "trade volume", "trade war", "trade balance", "RCEP", "CPTPP",
        "customs", "anti-dumping", "embargo", "trade barrier", "sanctions",
    ]),
    ("economy", [
        "GDP", "economic growth", "recession", "debt", "budget deficit",
        "fiscal", "revenue", "poverty", "unemployment", "inflation",
        "CPI", "stock market", "bond market", "financial crisis",
        "economic outlook", "economic slowdown", "cost of living",
        "interest rate", "exchange rate", "currency depreciation",
        "economic reform", "investment climate",
    ]),
    ("politics", [
        "government", "president", "prime minister", "cabinet", "minister",
        "parliament", "senate", "diplomacy", "bilateral", "summit",
        "treaty", "foreign policy", "geopolitics", "election", "vote",
        "political", "coalition", "opposition", "ruling party",
        "constitution", "referendum", "by-election",
    ]),
]

# Fallback if nothing matches
DEFAULT_CATEGORY = "politics"


# ──────────────────────────────────────────────────────────────────────────────
#  SECTION 4 — INDICATOR CONNECTIONS
# ──────────────────────────────────────────────────────────────────────────────
# For each category, which economic indicators is the news likely to affect?
# Uses camelCase keys matching the frontend CurrentIndicators type.
#
# Logic:
#   conflict      → political risk rises; FDI flees; exchange rate weakens
#   disaster      → GDP hit; imports spike (relief goods); exports disrupted
#   protest       → political risk rises; minor GDP drag
#   policy        → inflation + exchange rate most directly affected
#   infrastructure → FDI inflows; GDP growth medium-term
#   technology    → FDI; exports (high-tech goods)
#   trade         → exports + imports + tradeNewsCount most directly
#   economy       → GDP + inflation + FDI (general macro)
#   politics      → political risk count; FDI sentiment

CATEGORY_INDICATORS: dict[str, list[str]] = {
    "conflict":       ["politicalRiskNews", "fdi", "exchangeRate", "gdpGrowth"],
    "disaster":       ["gdpGrowth", "exports", "imports"],
    "protest":        ["politicalRiskNews", "gdpGrowth"],
    "policy":         ["inflation", "exchangeRate", "gdpGrowth"],
    "infrastructure": ["fdi", "gdpGrowth"],
    "technology":     ["fdi", "exports"],
    "trade":          ["exports", "imports", "tradeNewsCount"],
    "economy":        ["gdpGrowth", "inflation", "fdi"],
    "politics":       ["politicalRiskNews", "fdi"],
}

# Optional: title-level keyword overrides that ADD extra indicators
# e.g. "inflation" in the title → always add "inflation" even if category is "politics"
TITLE_INDICATOR_KEYWORDS: list[tuple[str, str]] = [
    ("inflation",           "inflation"),
    ("exchange rate",       "exchangeRate"),
    ("fdi",                 "fdi"),
    ("foreign investment",  "fdi"),
    ("export",              "exports"),
    ("import",              "imports"),
    ("gdp",                 "gdpGrowth"),
    ("growth",              "gdpGrowth"),
    ("currency",            "exchangeRate"),
    ("baht",                "exchangeRate"),
    ("dong",                "exchangeRate"),
    ("kyat",                "exchangeRate"),
    ("riel",                "exchangeRate"),
    ("sgd",                 "exchangeRate"),
    ("trade",               "tradeNewsCount"),
    ("political",           "politicalRiskNews"),
    ("protest",             "politicalRiskNews"),
    ("coup",                "politicalRiskNews"),
    ("conflict",            "politicalRiskNews"),
]


# ──────────────────────────────────────────────────────────────────────────────
#  SECTION 5 — IMPACT SCORING
# ──────────────────────────────────────────────────────────────────────────────

# Base score by category
CATEGORY_BASE_SCORE: dict[str, int] = {
    "conflict":       5,
    "disaster":       4,
    "protest":        3,
    "policy":         3,
    "trade":          3,
    "economy":        2,
    "technology":     2,
    "infrastructure": 2,
    "politics":       2,
}

# Title keywords that boost impact by +1
BOOST_WORDS = [
    "crisis", "collapse", "record high", "record low", "unprecedented",
    "emergency", "death toll", "casualties", "killed", "critical",
    "shock", "surge", "plunge", "crash", "sanctions", "ban",
]

# Title keywords that reduce impact by -1 (routine/positive low-urgency)
REDUCE_WORDS = [
    "inaugurat", "celebrat", "festival", "award", "tourism",
    "culture", "announces plan", "signs agreement", "opens new",
]


# ──────────────────────────────────────────────────────────────────────────────
#  SECTION 6 — GDELT API
# ──────────────────────────────────────────────────────────────────────────────

def build_gdelt_url(iso3: str, days: int) -> str:
    """
    Build GDELT 2.0 Doc API URL for one country.

    GDELT query syntax:
      - Words separated by space = OR
      - "quoted phrase" = exact match
      - GDELT returns newest articles first

    Example:
      .../doc?query=Thailand+OR+Thai+OR+"Bangkok"
              &mode=artlist&maxrecords=250&timespan=7d&format=json&sort=DateDesc
    """
    country = COUNTRIES[iso3]
    # URL-encode spaces as '+', keep quotes
    terms    = " OR ".join(country["keywords"])
    terms_enc = terms.replace('"', '%22').replace(' ', '+')

    return (
        f"{GDELT_URL}?query={terms_enc}"
        f"&mode=artlist"
        f"&maxrecords={MAX_RECORDS}"
        f"&timespan={days}d"
        f"&format=json"
        f"&sort=DateDesc"
    )


def fetch_country(iso3: str, days: int) -> list[dict]:
    """
    Fetch raw article list from GDELT for one country.
    Returns empty list on failure (not fatal — other countries still run).
    """
    url  = build_gdelt_url(iso3, days)
    name = COUNTRIES[iso3]["name"]

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            body, ctype = _http_get(url, timeout=35)

            # GDELT sometimes returns HTML error pages
            if not body.strip().startswith("{"):
                if attempt < MAX_RETRIES:
                    print(f"    ⚠  Non-JSON on attempt {attempt}, retrying…")
                    time.sleep(2 ** attempt)
                    continue
                return []

            data = json.loads(body)
            return data.get("articles") or []

        except Exception as e:
            code = getattr(getattr(e, "response", None), "status_code", None)
            if code == 429:
                wait = 30 * attempt
                print(f"    ⚠  Rate-limited (429) — waiting {wait}s…")
                time.sleep(wait)
                continue
            print(f"    ✗  {type(e).__name__} on attempt {attempt}/{MAX_RETRIES}: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(2 ** attempt)

    return []


# ──────────────────────────────────────────────────────────────────────────────
#  SECTION 7 — PARSING & CLASSIFICATION
# ──────────────────────────────────────────────────────────────────────────────

def _parse_gdelt_date(s: str) -> str:
    """
    GDELT date format: "20241201T120000Z"  →  "2024-12-01"
    Falls back to truncating if format is unexpected.
    """
    try:
        dt = datetime.strptime(s, "%Y%m%dT%H%M%SZ")
        return dt.strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        # Try just the date part
        s = (s or "")[:8]
        if len(s) == 8 and s.isdigit():
            return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
        return datetime.today().strftime("%Y-%m-%d")


def _classify_category(title: str) -> str:
    """First-match category from CATEGORY_RULES on lowercase title."""
    lower = title.lower()
    for cat, keywords in CATEGORY_RULES:
        if any(kw.lower() in lower for kw in keywords):
            return cat
    return DEFAULT_CATEGORY


def _tone_to_sentiment(tone: float | None) -> tuple[str, float]:
    """
    Convert GDELT's raw tone (typically −10 to +10) to:
      - sentiment: "positive" | "neutral" | "negative"
      - sentimentScore: clamped to −1 to +1

    Threshold: |tone| < 2 → neutral
    """
    if tone is None:
        return "neutral", 0.0
    score = max(-1.0, min(1.0, tone / 10.0))
    if tone > 2.0:
        return "positive", round(score, 3)
    elif tone < -2.0:
        return "negative", round(score, 3)
    return "neutral", round(score, 3)


def _connected_indicators(category: str, title: str) -> list[str]:
    """
    Return the list of camelCase indicator keys this article might affect.

    Start with the category-level defaults, then add any extras triggered
    by specific keywords in the title (e.g. title mentions "baht" → add "exchangeRate").
    """
    indicators = list(CATEGORY_INDICATORS.get(category, ["politicalRiskNews"]))
    lower = title.lower()

    for keyword, indicator in TITLE_INDICATOR_KEYWORDS:
        if keyword in lower and indicator not in indicators:
            indicators.append(indicator)

    # Keep a sensible max — frontend displays these as small chips
    return indicators[:5]


def _impact_score(category: str, title: str, tone: float | None) -> int:
    """
    Impact score 1–5:
      base (from category) + tone_bonus + boost_words − reduce_words
      clamped to [1, 5]
    """
    base  = CATEGORY_BASE_SCORE.get(category, 2)
    bonus = 0
    lower = title.lower()

    # Strong tone → +1
    if tone is not None and abs(tone) > 8:
        bonus += 1

    # Crisis words in title → +1
    if any(w in lower for w in BOOST_WORDS):
        bonus += 1

    # Routine announcement → -1
    if any(w in lower for w in REDUCE_WORDS):
        bonus -= 1

    return max(1, min(5, base + bonus))


def _generate_summary(title: str, category: str, country_name: str,
                      sentiment: str, domain: str) -> str:
    """
    Generate a one-sentence summary since GDELT only returns article titles.
    Keeps it informative and honest about the source.
    """
    tone_phrase = {
        "positive": "with a positive outlook",
        "negative": "reflecting concerns or deteriorating conditions",
        "neutral":  "with neutral reporting tone",
    }[sentiment]

    cat_context = {
        "conflict":       "Armed conflict and security developments",
        "disaster":       "Natural disaster or environmental event",
        "protest":        "Civil unrest or protest activity",
        "policy":         "Monetary or fiscal policy announcement",
        "infrastructure": "Infrastructure investment or development project",
        "technology":     "Technology sector development or digital economy news",
        "trade":          "Trade flows, agreements, or investment news",
        "economy":        "Macroeconomic development",
        "politics":       "Political or diplomatic development",
    }.get(category, "News event")

    return (
        f"{cat_context} in {country_name} {tone_phrase}. "
        f"Reported by {domain} and detected via GDELT real-time news monitoring."
    )


import hashlib

def _article_id_str(url: str, iso3: str) -> str:
    """Short stable ID for deduplication."""
    return hashlib.md5(url.encode()).hexdigest()[:16]


_NEXT_ID = [1]  # mutable int wrapper for a simple auto-increment

def parse_and_classify(raw: dict, iso3: str) -> dict | None:
    """
    Convert a raw GDELT article dict into a NewsEvent-compatible dict.
    Returns None if the article has no title (GDELT occasionally returns empty rows).
    """
    title  = (raw.get("title") or "").strip()
    if not title:
        return None

    url        = raw.get("url", "")
    domain     = raw.get("domain", url[:40] if url else "unknown")
    raw_tone   = raw.get("tone")
    tone       = float(raw_tone) if raw_tone is not None else None
    seen_date  = _parse_gdelt_date(raw.get("seendate", ""))

    category          = _classify_category(title)
    sentiment, score  = _tone_to_sentiment(tone)
    indicators        = _connected_indicators(category, title)
    impact            = _impact_score(category, title, tone)
    summary           = _generate_summary(title, category, COUNTRIES[iso3]["name"],
                                          sentiment, domain)

    article_id = _NEXT_ID[0]
    _NEXT_ID[0] += 1

    return {
        # ── Fields matching NewsEvent interface (frontend) ──────────────
        "id":                 article_id,
        "countryId":          iso3,
        "headline":           title,
        "summary":            summary,
        "category":           category,
        "sentiment":          sentiment,
        "sentimentScore":     score,
        "publishedAt":        seen_date,
        "sourceName":         domain,
        "impactLevel":        impact,
        "impactedIndicators": indicators,

        # ── GDELT-specific metadata (extra, frontend ignores these) ─────
        "gdeltUrl":           url,
        "gdeltTone":          round(tone, 3) if tone is not None else None,
        "gdeltArticleId":     _article_id_str(url, iso3),
        "fetchedAt":          datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


# ──────────────────────────────────────────────────────────────────────────────
#  SECTION 8 — DEDUPLICATION
# ──────────────────────────────────────────────────────────────────────────────

def deduplicate(articles: list[dict]) -> list[dict]:
    """
    Remove duplicate URLs. GDELT can return the same article
    for multiple country queries (e.g. a Thai-Vietnamese trade story).
    """
    seen_urls: set[str] = set()
    unique = []
    for a in articles:
        url = a.get("gdeltUrl", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique.append(a)
        elif not url:
            unique.append(a)   # keep items with no URL (shouldn't happen but be safe)
    return unique


# ──────────────────────────────────────────────────────────────────────────────
#  SECTION 9 — SAVE OUTPUTS
# ──────────────────────────────────────────────────────────────────────────────

def save_news_json(articles: list[dict], path: Path) -> None:
    """
    Save as JSON array directly importable by the frontend.

    Format matches the NewsEvent interface in sample-data.ts.
    Sorted: highest impact first, then newest first within same impact level.

    Also writes metadata at the end for debugging:
    {
      "_meta": {
        "generated_at": "...",
        "total": 123,
        "sources": ["gdelt"],
        "countries": ["THA", "VNM", ...]
      }
    }
    """
    sorted_articles = sorted(
        articles,
        key=lambda a: (-a["impactLevel"], a["publishedAt"]),
        reverse=False
    )
    # Reverse the publishedAt sort so newest comes first within same impact level
    sorted_articles = sorted(
        articles,
        key=lambda a: (-a["impactLevel"], a["publishedAt"][::-1])
    )

    output = {
        "generated_at":   datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total_articles": len(articles),
        "articles":       sorted_articles,
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"  ✓  Dashboard JSON  →  {path.name}  ({len(articles)} articles)")


def save_flat_csv(articles: list[dict], path: Path) -> None:
    """Save flat CSV — one article per row. Easy to open in Excel/Sheets."""
    if not articles:
        return

    fields = [
        "id", "countryId", "publishedAt", "category", "sentiment",
        "sentimentScore", "impactLevel", "headline", "sourceName",
        "impactedIndicators", "gdeltTone", "gdeltUrl",
    ]

    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        rows = []
        for a in sorted(articles, key=lambda x: (x["countryId"], x["publishedAt"])):
            row = dict(a)
            # Join list to string for CSV
            row["impactedIndicators"] = "|".join(a.get("impactedIndicators", []))
            rows.append(row)
        w.writerows(rows)

    print(f"  ✓  Flat CSV        →  {path.name}  ({len(articles)} rows)")


def save_summary_csv(articles: list[dict], path: Path) -> None:
    """
    Per-country × per-category breakdown.
    Shows how many articles each country has in each category, and negative share.
    """
    counts:     dict[tuple, int] = {}
    neg_counts: dict[tuple, int] = {}
    score_sums: dict[tuple, float] = {}

    for a in articles:
        key = (a["countryId"], a["category"])
        counts[key]      = counts.get(key, 0) + 1
        score_sums[key]  = score_sums.get(key, 0.0) + a["impactLevel"]
        if a["sentiment"] == "negative":
            neg_counts[key] = neg_counts.get(key, 0) + 1

    rows = []
    for (iso3, cat), total in sorted(counts.items()):
        neg = neg_counts.get((iso3, cat), 0)
        avg = round(score_sums.get((iso3, cat), 0) / total, 2)
        rows.append({
            "countryId":          iso3,
            "country_name":       COUNTRIES[iso3]["name"],
            "category":           cat,
            "article_count":      total,
            "negative_count":     neg,
            "negative_share_pct": round(100 * neg / total, 1),
            "avg_impact_score":   avg,
        })

    fields = ["countryId", "country_name", "category",
              "article_count", "negative_count", "negative_share_pct", "avg_impact_score"]

    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    print(f"  ✓  Summary CSV     →  {path.name}  ({len(rows)} country-category rows)")


# ──────────────────────────────────────────────────────────────────────────────
#  SECTION 10 — CONSOLE SUMMARY
# ──────────────────────────────────────────────────────────────────────────────

def print_summary(articles: list[dict]) -> None:
    """Print a human-readable summary table to the terminal."""
    if not articles:
        print("  No articles to summarise.")
        return

    print()
    print(f"  {'Country':<14} {'Articles':>9}  {'Neg%':>5}  {'AvgImpact':>9}  Top Categories")
    print(f"  {'─'*70}")

    for iso3, meta in COUNTRIES.items():
        arts = [a for a in articles if a["countryId"] == iso3]
        if not arts:
            print(f"  {meta['flag']} {meta['name']:<12}  {'0':>9}  {'–':>5}  {'–':>9}  (no results)")
            continue

        neg   = sum(1 for a in arts if a["sentiment"] == "negative")
        neg_p = round(100 * neg / len(arts))
        avg_i = round(sum(a["impactLevel"] for a in arts) / len(arts), 1)

        cat_counts: dict[str, int] = {}
        for a in arts:
            cat_counts[a["category"]] = cat_counts.get(a["category"], 0) + 1
        top = sorted(cat_counts, key=lambda c: -cat_counts[c])[:3]
        top_str = ", ".join(f"{c}({cat_counts[c]})" for c in top)

        print(f"  {meta['flag']} {meta['name']:<12} {len(arts):>9}  {neg_p:>4}%  {avg_i:>9}  {top_str}")

    print()
    total     = len(articles)
    neg_total = sum(1 for a in articles if a["sentiment"] == "negative")
    hi_impact = sum(1 for a in articles if a["impactLevel"] >= 4)
    avg_imp   = sum(a["impactLevel"] for a in articles) / total if total else 0

    print(f"  Total articles   : {total}")
    print(f"  Negative tone    : {neg_total} ({round(100*neg_total/total if total else 0)}%)")
    print(f"  High impact (≥4) : {hi_impact}")
    print(f"  Avg impact score : {avg_imp:.2f}")

    # Top signals
    high = [a for a in articles if a["impactLevel"] >= 4 and a["sentiment"] == "negative"]
    if high:
        print(f"\n  ⚑  TOP HIGH-IMPACT NEGATIVE SIGNALS:")
        for a in sorted(high, key=lambda x: -x["impactLevel"])[:6]:
            flag = COUNTRIES[a["countryId"]]["flag"]
            inds = ", ".join(a["impactedIndicators"][:3])
            print(f"     [{a['impactLevel']}★] {flag} {a['category']:<14} → {inds}")
            print(f"          {a['headline'][:80]}")


# ──────────────────────────────────────────────────────────────────────────────
#  MAIN
# ──────────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="GDELT news fetcher for SEA Dashboard MVP")
    p.add_argument("--days",    type=int,  default=7,
                   help="Days to look back (default 7; GDELT free tier works up to ~30)")
    p.add_argument("--country", type=str,  default=None,
                   help="Fetch one country only, e.g. --country VNM")
    return p.parse_args()


def main() -> None:
    args    = parse_args()
    ts      = datetime.today().strftime("%Y%m%d")
    _NEXT_ID[0] = 1   # reset ID counter each run

    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║   SEA Change Dashboard — GDELT News Fetcher (MVP)       ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print(f"  Countries   : {', '.join(COUNTRIES.keys())}")
    print(f"  Categories  : {', '.join(c for c,_ in CATEGORY_RULES)}")
    print(f"  Days back   : {args.days}")
    print(f"  Max/country : {MAX_RECORDS} articles")
    print(f"  Output      : {OUT_DIR}/")
    print()

    # ── Which countries to run ────────────────────────────────────────────
    if args.country:
        iso3 = args.country.upper()
        if iso3 not in COUNTRIES:
            print(f"  ✗  Unknown: {args.country}.  Valid: {', '.join(COUNTRIES)}")
            sys.exit(1)
        targets = [iso3]
    else:
        targets = list(COUNTRIES.keys())

    # ── STEP 1: Fetch ────────────────────────────────────────────────────
    print("[ STEP 1 ] Fetching from GDELT 2.0 Document API …")
    print(f"  {len(targets)} request(s) with {REQUEST_DELAY}s delay between them\n")

    all_articles: list[dict] = []

    for i, iso3 in enumerate(targets, 1):
        meta = COUNTRIES[iso3]
        print(f"  [{i}/{len(targets)}] {meta['flag']} {meta['name']} …", end="", flush=True)

        raw_list = fetch_country(iso3, args.days)
        parsed   = [r for raw in raw_list if (r := parse_and_classify(raw, iso3)) is not None]
        all_articles.extend(parsed)

        if parsed:
            neg = sum(1 for a in parsed if a["sentiment"] == "negative")
            print(f"  {len(parsed)} articles  ({neg} negative)")
        else:
            print(f"  0 articles  (API may be slow — try again in a minute)")

        if i < len(targets):
            time.sleep(REQUEST_DELAY)

    print(f"\n  Fetched : {len(all_articles)} total")

    # ── STEP 2: Deduplicate ───────────────────────────────────────────────
    before = len(all_articles)
    all_articles = deduplicate(all_articles)
    if before != len(all_articles):
        print(f"  Deduped : removed {before - len(all_articles)} duplicate URLs")

    if not all_articles:
        print("\n  ✗  No articles fetched.")
        print("     • Check internet connection")
        print("     • GDELT can be slow — wait 1–2 minutes and retry")
        print("     • Try: python fetch_gdelt_mvp.py --country THA")
        sys.exit(1)

    # Reassign sequential IDs after deduplication
    for i, a in enumerate(all_articles, 1):
        a["id"] = i

    # ── STEP 3: Classify distribution ────────────────────────────────────
    print("\n[ STEP 2 ] Category distribution:")
    cat_dist: dict[str, int] = {}
    for a in all_articles:
        cat_dist[a["category"]] = cat_dist.get(a["category"], 0) + 1
    for cat, count in sorted(cat_dist.items(), key=lambda x: -x[1]):
        bar = "█" * (count // 5)
        print(f"    {cat:<16} {count:>4}  {bar}")

    # ── STEP 4: Save outputs ──────────────────────────────────────────────
    print(f"\n[ STEP 3 ] Saving output files …")
    # Main file — frontend reads this
    save_news_json(all_articles,   OUT_DIR / "gdelt_news_events.json")
    # Also copy to json/ folder so it sits alongside other dashboard JSON files
    json_dir = OUT_DIR / "json"
    json_dir.mkdir(exist_ok=True)
    save_news_json(all_articles,   json_dir / "gdelt_news_events.json")

    save_flat_csv(all_articles,    OUT_DIR / f"gdelt_articles_{ts}.csv")
    save_summary_csv(all_articles, OUT_DIR / f"gdelt_summary_{ts}.csv")

    # ── STEP 5: Console summary ───────────────────────────────────────────
    print("\n[ STEP 4 ] Results summary:")
    print_summary(all_articles)

    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║  ✓  Done! Frontend-ready JSON:                          ║")
    print("║     pipeline/output/json/gdelt_news_events.json         ║")
    print("║                                                          ║")
    print("║  The News Impact Feed will auto-show GDELT articles.    ║")
    print("║                                                          ║")
    print("║  To refresh: python pipeline/fetch_gdelt_mvp.py         ║")
    print("║  Daily cron: add to run_daily.py                        ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print()


if __name__ == "__main__":
    main()
