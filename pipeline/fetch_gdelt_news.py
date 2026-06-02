#!/usr/bin/env python3
"""
==============================================================================
  GDELT News Signal Fetcher — SEA Change Intelligence Dashboard
  pipeline/fetch_gdelt_news.py
==============================================================================

Fetches real-time news for 17 countries from the GDELT 2.0 Document API,
classifies articles into 13 categories, scores impact 1–5, maps each article
to connected economic indicators, deduplicates by URL, and saves structured
output ready for the dashboard news feed and alert engine.

No API key required. GDELT is completely free and open.

USAGE
─────
    cd pipeline
    python fetch_gdelt_news.py                # fetch last 7 days, use cache
    python fetch_gdelt_news.py --days 14      # extend look-back window
    python fetch_gdelt_news.py --refresh      # ignore today's cached raw files
    python fetch_gdelt_news.py --country THA  # single country (for testing)

OUTPUT
──────
    data/raw/gdelt/
        raw_{iso3}_{YYYYMMDD}.json     Per-country raw GDELT response
        fetch_log_{YYYYMMDD}.csv       What was fetched, status, article counts

    data/processed/
        news_signals.json              Master file — frontend reads this

HOW GDELT IS QUERIED
─────────────────────
    • 1 API request per country (17 total) — all category keywords combined
    • Articles are then classified client-side based on title keywords
    • This avoids 221 per-category requests and GDELT rate limits
    • Up to 250 articles per country, last DAYS_BACK days, English preferred

IMPACT SCORING (1–5)
─────────────────────
    5 — tariff, sanction, border closure, coup, war, election crisis,
        central bank shock
    4 — large protest, trade restriction, major policy change,
        supply-chain disaster
    3 — normal election news, economic forecast, investment project,
        inflation concern
    2 — local project update, company-level news
    1 — general background news

RATE LIMITING
─────────────
    GDELT aggressively rate-limits repeated requests.
    This script uses a 4-second delay between requests (REQUEST_DELAY).
    On 429 responses it waits 60 s → 120 s → 180 s before giving up.
    If the first 3 countries all fail, the script detects a rate-limit storm
    and skips the rest immediately (saves ~30 min of pointless retries).
    When all fetches fail but a prior news_signals.json exists, the script
    preserves it, stamps a rate_limited_at field, and exits 0 (not 1).
    Today's raw files are cached: re-runs within the same day skip API calls.

==============================================================================
"""

import csv
import json
import sys
import time
import hashlib
import argparse
from pathlib import Path
from datetime import datetime, date, timedelta
from collections import defaultdict

try:
    import httpx
    _HTTP = "httpx"
except ImportError:
    import urllib.request
    import urllib.parse
    _HTTP = "urllib"


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 1 — CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

SCRIPT_DIR  = Path(__file__).parent
RAW_DIR     = SCRIPT_DIR / "data" / "raw" / "gdelt"
PROC_DIR    = SCRIPT_DIR / "data" / "processed"

GDELT_API   = "https://api.gdeltproject.org/api/v2/doc/doc"
DAYS_BACK   = 7          # default look-back window
MAX_RECORDS = 250        # GDELT API hard cap per request
REQUEST_DELAY = 6.0      # polite delay between requests (GDELT asks for 1/5s minimum)
MAX_RETRIES = 3          # retries before giving up on a country


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 2 — COUNTRY REGISTRY
# ══════════════════════════════════════════════════════════════════════════════
# query_names: additional search terms to catch alternate names / demonyms

COUNTRIES: dict[str, dict] = {
    # ── Southeast Asia ──────────────────────────────────────────────────
    "TH": {
        "iso3": "THA", "name": "Thailand",      "flag": "🇹🇭",
        "query_names": ["Thailand", "Thai"],
    },
    "VN": {
        "iso3": "VNM", "name": "Vietnam",       "flag": "🇻🇳",
        "query_names": ["Vietnam", "Vietnamese"],
    },
    "MM": {
        "iso3": "MMR", "name": "Myanmar",       "flag": "🇲🇲",
        "query_names": ["Myanmar", "Burma", "Burmese"],
    },
    "KH": {
        "iso3": "KHM", "name": "Cambodia",      "flag": "🇰🇭",
        "query_names": ["Cambodia", "Cambodian", "Khmer"],
    },
    "LA": {
        "iso3": "LAO", "name": "Laos",          "flag": "🇱🇦",
        "query_names": ["Laos", "Lao PDR", "Lao"],
    },
    "MY": {
        "iso3": "MYS", "name": "Malaysia",      "flag": "🇲🇾",
        "query_names": ["Malaysia", "Malaysian"],
    },
    "SG": {
        "iso3": "SGP", "name": "Singapore",     "flag": "🇸🇬",
        "query_names": ["Singapore", "Singaporean"],
    },
    "ID": {
        "iso3": "IDN", "name": "Indonesia",     "flag": "🇮🇩",
        "query_names": ["Indonesia", "Indonesian"],
    },
    "PH": {
        "iso3": "PHL", "name": "Philippines",   "flag": "🇵🇭",
        "query_names": ["Philippines", "Filipino", "Philippine"],
    },
    "BN": {
        "iso3": "BRN", "name": "Brunei",        "flag": "🇧🇳",
        "query_names": ["Brunei", "Bruneian"],
    },
    "TP": {
        "iso3": "TLS", "name": "Timor-Leste",   "flag": "🇹🇱",
        "query_names": ["Timor-Leste", "East Timor", "Timorese"],
    },
    # ── Partner nations ─────────────────────────────────────────────────
    "CN": {
        "iso3": "CHN", "name": "China",         "flag": "🇨🇳",
        "query_names": ["China", "Chinese"],
    },
    "US": {
        "iso3": "USA", "name": "United States", "flag": "🇺🇸",
        "query_names": ["United States", "US economy", "US trade"],
    },
    "JP": {
        "iso3": "JPN", "name": "Japan",         "flag": "🇯🇵",
        "query_names": ["Japan", "Japanese"],
    },
    "IN": {
        "iso3": "IND", "name": "India",         "flag": "🇮🇳",
        "query_names": ["India", "Indian economy"],
    },
    "KR": {
        "iso3": "KOR", "name": "South Korea",   "flag": "🇰🇷",
        "query_names": ["South Korea", "Republic of Korea", "Korean"],
    },
    "AU": {
        "iso3": "AUS", "name": "Australia",     "flag": "🇦🇺",
        "query_names": ["Australia", "Australian"],
    },
}

ISO3_META: dict[str, dict] = {v["iso3"]: {**v, "iso2": k} for k, v in COUNTRIES.items()}


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 3 — CATEGORY DEFINITIONS & KEYWORDS
# ══════════════════════════════════════════════════════════════════════════════

# Ordered list of categories — more specific ones checked FIRST
# so "tariff" beats "trade" when both match
CATEGORY_PRIORITY: list[str] = [
    "tariff",
    "conflict",
    "disaster",
    "border",
    "protest",
    "election",
    "policy",
    "trade",
    "technology",
    "infrastructure",
    "economy",
    "politics",
]

# Keywords to match in article titles (all lowercase)
CATEGORY_PATTERNS: dict[str, list[str]] = {
    "tariff": [
        "tariff", "tariffs", "sanction", "sanctions", "trade war", "trade ban",
        "import ban", "export ban", "customs duty", "embargo", "trade barrier",
        "trade restriction", "trade penalty", "levy on", "duties on",
        "banned goods", "blacklisted", "supply chain disruption",
    ],
    "conflict": [
        "coup", "military coup", "war", "armed conflict", "civil war", "airstrike",
        "missile", "bombing", "rebel", "insurgent", "militia", "ceasefire",
        "martial law", "military operation", "troop", "soldier killed",
        "clash", "gunfire", "explosion", "terrorist", "terrorism",
    ],
    "disaster": [
        "flood", "flooding", "earthquake", "typhoon", "tsunami", "cyclone",
        "hurricane", "wildfire", "forest fire", "drought", "landslide",
        "volcanic", "eruption", "disaster", "humanitarian crisis",
        "emergency declaration", "natural disaster",
    ],
    "border": [
        "border closure", "border crossing", "border dispute", "territorial dispute",
        "maritime border", "south china sea", "sea dispute", "immigration",
        "smuggling", "border tension", "frontier", "boundary",
    ],
    "protest": [
        "protest", "demonstration", "rally", "march", "strike", "workers strike",
        "general strike", "riot", "unrest", "crackdown", "tear gas",
        "arrested protesters", "sit-in", "occupy", "civil disobedience",
    ],
    "election": [
        "election", "general election", "parliamentary election", "vote",
        "ballot", "polling", "campaign", "candidate", "referendum",
        "electoral", "voter turnout", "election results", "inauguration",
    ],
    "policy": [
        "policy", "regulation", "law passed", "legislation", "new law",
        "executive order", "decree", "reform", "budget", "fiscal policy",
        "monetary policy", "interest rate", "central bank", "rate hike",
        "rate cut", "policy change",
    ],
    "trade": [
        "trade deal", "trade agreement", "trade deficit", "trade surplus",
        "bilateral trade", "free trade", "export growth", "import growth",
        "supply chain", "logistics", "shipping", "port congestion",
        "trade volume", "trade relations",
    ],
    "technology": [
        "technology", "semiconductor", "chip", "AI", "artificial intelligence",
        "digital", "tech hub", "startup", "fintech", "5G", "data center",
        "tech investment", "innovation", "e-commerce", "cloud",
    ],
    "infrastructure": [
        "infrastructure", "railway", "rail project", "port", "highway",
        "bridge", "dam", "power plant", "energy project", "road",
        "metro", "airport", "construction project", "belt and road",
    ],
    "economy": [
        "economy", "economic", "GDP", "growth rate", "recession",
        "inflation", "unemployment", "jobs", "manufacturing", "industry",
        "investment", "FDI", "foreign investment", "economic outlook",
        "economic forecast", "economic slowdown", "recovery",
    ],
    "politics": [
        "political", "politics", "government", "parliament", "cabinet",
        "minister", "prime minister", "president", "opposition",
        "coalition", "ruling party", "state visit", "diplomatic",
    ],
}

# Keywords used in the GDELT query to maximise coverage
# (client-side CATEGORY_PATTERNS above do the actual classification)
QUERY_KEYWORDS: list[str] = [
    "economy", "trade", "tariff", "sanctions", "election", "protest",
    "military", "coup", "conflict", "disaster", "flood", "earthquake",
    "policy", "reform", "inflation", "investment", "infrastructure",
    "technology", "semiconductor", "border", "maritime",
]

# Which dashboard indicators each category connects to
CATEGORY_INDICATORS: dict[str, list[str]] = {
    "tariff":         ["exports", "imports", "tradeNewsCount", "fdi"],
    "conflict":       ["politicalRiskNews", "fdi", "gdpGrowth"],
    "disaster":       ["gdpGrowth", "exports", "inflation"],
    "border":         ["exports", "imports", "politicalRiskNews"],
    "protest":        ["politicalRiskNews", "fdi", "exchangeRate"],
    "election":       ["politicalRiskNews", "fdi"],
    "policy":         ["gdpGrowth", "fdi", "inflation"],
    "trade":          ["exports", "imports", "tradeNewsCount"],
    "technology":     ["fdi", "tradeNewsCount", "gdpGrowth"],
    "infrastructure": ["fdi", "gdpGrowth", "exports"],
    "economy":        ["gdpGrowth", "inflation", "fdi"],
    "politics":       ["politicalRiskNews", "fdi"],
}


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 4 — IMPACT SCORING
# ══════════════════════════════════════════════════════════════════════════════

# Base impact score per category (before title-word adjustments)
CATEGORY_BASE_SCORE: dict[str, int] = {
    "tariff":         4,
    "conflict":       4,
    "disaster":       3,
    "border":         3,
    "protest":        3,
    "election":       2,
    "policy":         2,
    "trade":          2,
    "technology":     2,
    "infrastructure": 1,
    "economy":        2,
    "politics":       2,
}

# Title words that raise the score by +1 each (max +2 total)
IMPACT_BOOST_WORDS: list[str] = [
    "coup", "war", "sanctions", "sanction", "crisis", "major",
    "critical", "emergency", "collapse", "suspended", "banned",
    "rate hike", "central bank shock", "catastrophic", "historic",
    "unprecedented", "martial law", "mass", "large-scale", "sweeping",
    "record high", "record low", "all-time", "worst", "severe",
]

# Title words that lower the score by -1 (max -1 total)
IMPACT_REDUCE_WORDS: list[str] = [
    "routine", "minor", "local", "small", "annual", "scheduled",
    "regular", "background", "preview", "update", "ceremony",
    "reminder", "overview", "weekly", "roundup",
]

# Title words that push score to 5 regardless of base
IMPACT_5_TRIGGERS: list[str] = [
    "coup", "war declared", "state of war", "central bank shock",
    "nuclear", "border closure announced", "martial law declared",
    "mass casualty", "economic collapse",
]


def compute_impact(category: str, title: str) -> int:
    """
    Compute an impact score (1–5) based on the category and title.

    Rules:
      5 — headline contains an Impact-5 trigger word
      Base = CATEGORY_BASE_SCORE[category]
      +1 for each IMPACT_BOOST_WORDS hit (max +2)
      -1 if IMPACT_REDUCE_WORDS hit (max -1)
      Clamped to [1, 5]
    """
    t = title.lower()

    # Check impact-5 triggers first
    if any(trigger in t for trigger in IMPACT_5_TRIGGERS):
        return 5

    base   = CATEGORY_BASE_SCORE.get(category, 2)
    boost  = min(sum(1 for w in IMPACT_BOOST_WORDS  if w in t), 2)
    reduce = min(sum(1 for w in IMPACT_REDUCE_WORDS if w in t), 1)

    return max(1, min(5, base + boost - reduce))


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 5 — TONE / SENTIMENT COMPUTATION
# ══════════════════════════════════════════════════════════════════════════════
# GDELT ArtList mode does NOT return article-level tone.
# We compute a proxy from the article title using keyword lists.

NEGATIVE_TITLE_WORDS: list[str] = [
    "war", "crisis", "conflict", "collapse", "coup", "attack", "bomb",
    "killed", "death", "flood", "disaster", "protest", "riot", "sanction",
    "banned", "suspended", "recession", "hyperinflation", "unemployment",
    "corruption", "fraud", "detained", "arrested", "crackdown",
    "downturn", "contraction", "deficit", "debt", "default",
]

POSITIVE_TITLE_WORDS: list[str] = [
    "growth", "record", "investment", "deal", "agreement", "expansion",
    "recovery", "boost", "surge", "partnership", "cooperation",
    "milestone", "success", "improvement", "breakthrough", "approved",
    "signed", "strengthened", "increased", "highest ever",
]


def compute_sentiment(title: str) -> tuple[str, float]:
    """
    Returns (sentiment_label, sentiment_score).
      sentiment_label : "positive" | "negative" | "neutral"
      sentiment_score : float in [-1.0, +1.0]
    """
    t = title.lower()
    neg = sum(1 for w in NEGATIVE_TITLE_WORDS if w in t)
    pos = sum(1 for w in POSITIVE_TITLE_WORDS if w in t)
    total = neg + pos

    if total == 0:
        return "neutral", 0.0

    raw_score = (pos - neg) / total
    score     = round(max(-1.0, min(1.0, raw_score)), 2)

    if score > 0.1:
        label = "positive"
    elif score < -0.1:
        label = "negative"
    else:
        label = "neutral"

    return label, score


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 6 — CATEGORY CLASSIFICATION
# ══════════════════════════════════════════════════════════════════════════════

def classify_article(title: str) -> tuple[str, list[str]]:
    """
    Classify an article into one primary category + list of all matching categories.

    Checks categories in CATEGORY_PRIORITY order so more specific categories
    take precedence over general ones (e.g. 'tariff' beats 'trade').

    Returns (primary_category, all_categories).
    Falls back to 'politics' if no keywords match.
    """
    t            = title.lower()
    matched: list[str] = []

    for cat in CATEGORY_PRIORITY:
        patterns = CATEGORY_PATTERNS.get(cat, [])
        if any(p in t for p in patterns):
            matched.append(cat)

    if not matched:
        return "politics", ["politics"]

    # Primary = first match in priority order (most specific)
    return matched[0], matched


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 7 — GDELT API HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def build_query(country: dict, days_back: int) -> dict:
    """
    Build GDELT API query parameters for a country.

    Strategy: combine the country name(s) with a broad set of category
    keywords so the single request returns the most relevant articles.
    Classification happens client-side after fetching.
    """
    end_dt   = datetime.now()
    start_dt = end_dt - timedelta(days=days_back)

    # Country search terms: use primary name + alternates
    name_terms = " OR ".join(f'"{n}"' for n in country["query_names"])

    # Category keywords (OR-joined) to filter for relevant content
    kw_str = " OR ".join(f'"{k}"' for k in QUERY_KEYWORDS[:20])

    query = f"({name_terms}) ({kw_str}) sourcelang:english"

    return {
        "query":         query,
        "mode":          "artlist",
        "maxrecords":    MAX_RECORDS,
        "startdatetime": start_dt.strftime("%Y%m%d%H%M%S"),
        "enddatetime":   end_dt.strftime("%Y%m%d%H%M%S"),
        "format":        "json",
        "sort":          "DateDesc",
    }


def _fetch_url(url: str, params: dict) -> dict | None:
    """Perform the HTTP GET and return parsed JSON, or None on failure."""
    if _HTTP == "httpx":
        resp = httpx.get(url, params=params, timeout=30, follow_redirects=True)
        resp.raise_for_status()
        return resp.json()
    else:
        full = url + "?" + urllib.parse.urlencode(params)
        req  = urllib.request.Request(full, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))


def fetch_country(
    wb2: str,
    country: dict,
    days_back: int,
    use_cached: bool = True,
) -> list[dict]:
    """
    Fetch news articles for one country from GDELT.

    Returns a list of raw article dicts from the GDELT response.
    On 429 uses exponential back-off (30s, 60s, 90s).
    """
    iso3     = country["iso3"]
    today    = date.today().strftime("%Y%m%d")
    raw_file = RAW_DIR / f"raw_{iso3}_{today}.json"

    # ── Cache hit ──────────────────────────────────────────────────────────
    if use_cached and raw_file.exists():
        with open(raw_file, encoding="utf-8") as f:
            data = json.load(f)
        print(f"  {country['flag']} {country['name']:<16} 📂 {len(data)} articles (cache)")
        return data

    # ── Live fetch ─────────────────────────────────────────────────────────
    params = build_query(country, days_back)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = _fetch_url(GDELT_API, params)

            if response is None:
                print(f"  {country['flag']} {country['name']:<16} ✗ empty response")
                return []

            # GDELT returns {"articles": [...]} or {} on no results
            articles = response.get("articles") or []
            print(
                f"  {country['flag']} {country['name']:<16} "
                f"✓ {len(articles):>3} articles fetched"
            )

            # Save raw file
            RAW_DIR.mkdir(parents=True, exist_ok=True)
            with open(raw_file, "w", encoding="utf-8") as f:
                json.dump(articles, f, indent=2, ensure_ascii=False)

            return articles

        except Exception as exc:
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            is_rate_limit = status_code == 429

            if is_rate_limit:
                wait = 60 * attempt  # 60s, 120s, 180s
                print(
                    f"  {country['flag']} {country['name']:<16} "
                    f"⚠ 429 rate-limited — waiting {wait}s (attempt {attempt}/{MAX_RETRIES})"
                )
                time.sleep(wait)
            else:
                wait = 2 ** attempt
                print(
                    f"  {country['flag']} {country['name']:<16} "
                    f"✗ Attempt {attempt}/{MAX_RETRIES}: {type(exc).__name__} — retry in {wait}s"
                )
                time.sleep(wait)

    print(f"  {country['flag']} {country['name']:<16} ✗ FAILED after {MAX_RETRIES} attempts")
    return []


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 8 — PARSE & ENRICH ARTICLES
# ══════════════════════════════════════════════════════════════════════════════

def parse_seendate(seendate: str) -> str:
    """Convert GDELT seendate '20260601T120000Z' → 'YYYY-MM-DD'."""
    try:
        return datetime.strptime(seendate[:8], "%Y%m%d").strftime("%Y-%m-%d")
    except Exception:
        return date.today().isoformat()


def url_hash(url: str) -> str:
    """Short MD5 hash of a URL for deduplication."""
    return hashlib.md5(url.encode("utf-8")).hexdigest()[:12]


def enrich_article(raw: dict, iso3: str, country_name: str, seq_id: int) -> dict | None:
    """
    Convert one raw GDELT article dict into a fully enriched news signal record.
    Returns None if the article is missing title or URL.
    """
    title = (raw.get("title") or "").strip()
    url   = (raw.get("url")   or "").strip()

    if not title or not url:
        return None

    seendate  = raw.get("seendate", "")
    domain    = raw.get("domain", "")
    language  = raw.get("language", "English")

    # Classification
    category, all_categories = classify_article(title)

    # Sentiment from title
    sentiment_label, sentiment_score = compute_sentiment(title)

    # Impact score
    impact = compute_impact(category, title)

    # Connected indicators
    indicators = CATEGORY_INDICATORS.get(category, ["politicalRiskNews"])

    return {
        "id":                  seq_id,
        "title":               title,
        "url":                 url,
        "source_domain":       domain,
        "date":                parse_seendate(seendate),
        "country_code":        iso3,
        "country_name":        country_name,
        "category":            category,
        "all_categories":      all_categories,
        "tone":                sentiment_score,   # proxy tone from title analysis
        "language":            language,
        "impact_score":        impact,
        "connected_indicators": indicators,
        "source":              "gdelt",
        "gdelt_seendate":      seendate,
        "url_hash":            url_hash(url),
    }


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 9 — DEDUPLICATION
# ══════════════════════════════════════════════════════════════════════════════

def deduplicate(articles: list[dict]) -> tuple[list[dict], int]:
    """
    Remove exact URL duplicates. Keeps the first occurrence.
    Also removes articles with near-identical titles (same first 60 chars).

    Returns (deduped_list, removed_count).
    """
    seen_hashes : set[str] = set()
    seen_titles : set[str] = set()
    result      : list[dict] = []
    removed     = 0

    for art in articles:
        h = art.get("url_hash", "")
        t = art.get("title", "")[:60].lower().strip()

        if h in seen_hashes or t in seen_titles:
            removed += 1
            continue

        seen_hashes.add(h)
        if t:
            seen_titles.add(t)
        result.append(art)

    return result, removed


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 10 — SOURCE TRACKING & STATISTICS
# ══════════════════════════════════════════════════════════════════════════════

def build_source_tracking(articles: list[dict]) -> dict:
    """
    Build per-country source tracking dict:
    { iso3 → { articles: N, sources: [domain, ...], top_domain: domain } }
    """
    tracking: dict[str, dict] = {}

    for art in articles:
        iso3 = art["country_code"]
        if iso3 not in tracking:
            tracking[iso3] = {"articles": 0, "sources": [], "domain_counts": {}}

        tracking[iso3]["articles"] += 1

        domain = art.get("source_domain", "")
        if domain:
            tracking[iso3]["domain_counts"][domain] = (
                tracking[iso3]["domain_counts"].get(domain, 0) + 1
            )

    # Finalise: top 5 sources per country, sorted by count
    result = {}
    for iso3, info in tracking.items():
        sorted_domains = sorted(
            info["domain_counts"].items(), key=lambda x: x[1], reverse=True
        )
        result[iso3] = {
            "articles":   info["articles"],
            "sources":    [d for d, _ in sorted_domains[:5]],
            "top_domain": sorted_domains[0][0] if sorted_domains else "",
        }

    return result


def build_category_counts(articles: list[dict]) -> dict:
    """
    Build per-country per-category article counts:
    { iso3 → { category → count } }
    """
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for art in articles:
        iso3 = art["country_code"]
        cat  = art["category"]
        counts[iso3][cat] += 1

    # Convert defaultdicts to plain dicts and fill zeros for all categories
    result = {}
    all_cats = list(CATEGORY_PRIORITY)
    for iso3 in counts:
        result[iso3] = {cat: counts[iso3].get(cat, 0) for cat in all_cats}

    return result


def build_news_counts(articles: list[dict]) -> dict:
    """
    Build political risk and trade news counts per country.
    Used by the Pattern Alert Centre to update real-time news indicators.

    Returns {
      iso3 → {
        political_risk_count:  N,   # politics + protest + conflict + election + border
        trade_news_count:      N,   # trade + tariff
        total_articles:        N,
      }
    }
    """
    POLITICAL_CATS = {"politics", "protest", "conflict", "election", "border"}
    TRADE_CATS     = {"trade", "tariff"}

    counts: dict[str, dict] = {}
    for art in articles:
        iso3 = art["country_code"]
        if iso3 not in counts:
            counts[iso3] = {"political_risk_count": 0, "trade_news_count": 0, "total_articles": 0}
        counts[iso3]["total_articles"] += 1
        if art["category"] in POLITICAL_CATS:
            counts[iso3]["political_risk_count"] += 1
        if art["category"] in TRADE_CATS:
            counts[iso3]["trade_news_count"] += 1

    return counts


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 11 — SAVE OUTPUTS
# ══════════════════════════════════════════════════════════════════════════════

def save_fetch_log(log_rows: list[dict]) -> None:
    """Save a CSV log of what was fetched (country, status, article count)."""
    ts   = date.today().strftime("%Y%m%d")
    path = RAW_DIR / f"fetch_log_{ts}.csv"

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    fields = ["iso3", "country", "status", "raw_articles", "enriched", "fetch_time_s"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(log_rows)

    print(f"  ✓  Fetch log → {path.relative_to(SCRIPT_DIR)}")


def save_processed_json(
    articles:         list[dict],
    source_tracking:  dict,
    category_counts:  dict,
    news_counts:      dict,
    days_back:        int,
    duplicates_removed: int,
) -> None:
    """
    Save the master processed JSON at data/processed/news_signals.json.

    This is the file the frontend reads. Structure:
    {
      meta:            {...},
      source_tracking: { iso3 → {articles, sources, top_domain} },
      category_counts: { iso3 → { category → count } },
      news_counts:     { iso3 → {political_risk_count, trade_news_count, total_articles} },
      articles:        [{id, title, url, source_domain, date, country_code, ...}]
    }
    """
    today_str = date.today().isoformat()
    ts        = datetime.now().isoformat(timespec="seconds")
    end_date  = date.today()
    start_date = end_date - timedelta(days=days_back)

    output = {
        "meta": {
            "generated_at":       ts,
            "source":             "GDELT 2.0 Document API",
            "api_url":            GDELT_API,
            "days_back":          days_back,
            "start_date":         start_date.isoformat(),
            "end_date":           end_date.isoformat(),
            "total_articles":     len(articles) + duplicates_removed,
            "unique_articles":    len(articles),
            "duplicates_removed": duplicates_removed,
            "countries_fetched":  len(source_tracking),
            "categories":         len(CATEGORY_PRIORITY),
            "data_status":        "live",
            "refresh_note":       (
                f"Run 'python fetch_gdelt_news.py' to refresh. "
                f"Data covers {start_date} – {end_date} (last {days_back} days)."
            ),
        },
        "source_tracking":  source_tracking,
        "category_counts":  category_counts,
        "news_counts":       news_counts,
        "articles":          articles,
    }

    PROC_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROC_DIR / "news_signals.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(
        f"  ✓  Processed JSON → {out_path.relative_to(SCRIPT_DIR)}"
        f"  ({len(articles)} articles, {len(source_tracking)} countries)"
    )


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 12 — MAIN ORCHESTRATION
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch GDELT news signals for SEA Dashboard"
    )
    parser.add_argument(
        "--days", type=int, default=DAYS_BACK,
        help=f"Look-back window in days (default: {DAYS_BACK})",
    )
    parser.add_argument(
        "--refresh", action="store_true",
        help="Ignore today's cached raw files and re-fetch from API",
    )
    parser.add_argument(
        "--country", type=str, default=None,
        help="Fetch only one country ISO3 code (e.g. THA) — for testing",
    )
    args = parser.parse_args()

    use_cached  = not args.refresh
    days_back   = args.days
    only_iso3   = args.country.upper() if args.country else None

    # ── Banner ──────────────────────────────────────────────────────────────
    print()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║   SEA Change Dashboard — GDELT News Signal Fetcher          ║")
    print("╚══════════════════════════════════════════════════════════════╝")

    end_date   = date.today()
    start_date = end_date - timedelta(days=days_back)

    target_countries = {
        k: v for k, v in COUNTRIES.items()
        if (only_iso3 is None or v["iso3"] == only_iso3)
    }

    print(f"  Countries    : {len(target_countries)}")
    print(f"  Categories   : {len(CATEGORY_PRIORITY)}")
    print(f"  Date range   : {start_date} → {end_date} ({days_back} days)")
    print(f"  Max/country  : {MAX_RECORDS} articles")
    print(f"  HTTP lib     : {_HTTP}")
    cache_note = "skip — re-fetching all" if args.refresh else "use today's raw files if present"
    print(f"  Cache mode   : {cache_note}")
    print(f"  Raw dir      : {RAW_DIR.relative_to(SCRIPT_DIR)}/")
    print(f"  Output       : {PROC_DIR.relative_to(SCRIPT_DIR)}/news_signals.json")
    print()
    print(f"[ STEP 1 ] Fetching from GDELT API …")
    print(f"  {len(target_countries)} requests total\n")

    # ── Fetch all countries ─────────────────────────────────────────────────
    all_raw_articles: dict[str, list[dict]] = {}
    log_rows: list[dict] = []

    # Storm detection: if the first STORM_THRESHOLD live fetches all return
    # zero articles (no cached fallback), GDELT is actively blocking this IP.
    # Skip all remaining countries to avoid wasting 30+ minutes on retries.
    STORM_THRESHOLD    = 3
    consecutive_fails  = 0
    storm_detected     = False

    for i, (wb2, country) in enumerate(target_countries.items(), 1):
        iso3 = country["iso3"]

        # Skip immediately once a storm is detected
        if storm_detected:
            all_raw_articles[iso3] = []
            log_rows.append({
                "iso3": iso3, "country": country["name"],
                "status": "skipped", "raw_articles": 0,
                "enriched": 0, "fetch_time_s": 0,
            })
            print(f"  {country['flag']} {country['name']:<16} ⏭ skipped (rate-limit storm active)")
            continue

        t0 = time.time()
        raw = fetch_country(wb2, country, days_back, use_cached)
        elapsed = round(time.time() - t0, 1)

        all_raw_articles[iso3] = raw
        log_rows.append({
            "iso3":         iso3,
            "country":      country["name"],
            "status":       "ok" if raw else "empty",
            "raw_articles": len(raw),
            "enriched":     0,  # filled below
            "fetch_time_s": elapsed,
        })

        # Track consecutive live failures (cached hits reset the counter)
        if not raw:
            consecutive_fails += 1
            if consecutive_fails >= STORM_THRESHOLD and not storm_detected:
                storm_detected = True
                print(
                    f"\n  ⚡ Rate-limit storm detected after {STORM_THRESHOLD} "
                    f"consecutive failures — skipping remaining countries."
                )
        else:
            consecutive_fails = 0

        # Polite delay (skip on last item and when storm is active)
        if i < len(target_countries) and not storm_detected:
            time.sleep(REQUEST_DELAY)

    total_raw = sum(len(v) for v in all_raw_articles.values())
    print(f"\n  Total raw articles fetched : {total_raw}")

    if total_raw == 0:
        existing_json = PROC_DIR / "news_signals.json"
        if existing_json.exists():
            print(
                "\n⚠  No articles fetched — GDELT is rate-limiting this IP.\n"
                "   Existing news_signals.json is untouched (no overwrite).\n"
                "   Retry in 10–15 min:  python fetch_gdelt_news.py\n"
                "   Force re-fetch:      python fetch_gdelt_news.py --refresh"
            )
            # Stamp the rate-limit event into the existing file so the
            # frontend / operator knows when the last live refresh failed.
            try:
                with open(existing_json, encoding="utf-8") as fh:
                    cached = json.load(fh)
                cached["meta"]["rate_limited_at"] = datetime.now().isoformat(timespec="seconds")
                cached["meta"]["rate_limit_note"] = (
                    "Last live refresh was blocked by GDELT rate-limit. "
                    "Dashboard is showing previously fetched data."
                )
                with open(existing_json, "w", encoding="utf-8") as fh:
                    json.dump(cached, fh, indent=2, ensure_ascii=False)
                print("  ✓  Stamped rate_limited_at in existing JSON.")
            except Exception as stamp_err:
                print(f"  ⚠  Could not stamp existing JSON: {stamp_err}")
            sys.exit(0)   # exit 0 — background task shows "success", not "failed"
        else:
            print(
                "\n✗  No articles fetched and no fallback JSON exists.\n"
                "   This usually means GDELT is rate-limiting.\n"
                "   Wait 10 minutes and retry: python fetch_gdelt_news.py"
            )
            sys.exit(1)

    # ── Enrich all articles ─────────────────────────────────────────────────
    print(f"\n[ STEP 2 ] Enriching articles (classify · score · sentiment) …")
    enriched: list[dict] = []
    seq_id = 1

    for iso3, raw_list in all_raw_articles.items():
        c_meta       = ISO3_META[iso3]
        country_name = c_meta["name"]
        country_enriched = 0

        for raw in raw_list:
            art = enrich_article(raw, iso3, country_name, seq_id)
            if art:
                enriched.append(art)
                seq_id += 1
                country_enriched += 1

        # Update log
        for row in log_rows:
            if row["iso3"] == iso3:
                row["enriched"] = country_enriched
                break

    print(f"  ✓  {len(enriched)} articles enriched")

    # ── Deduplicate ─────────────────────────────────────────────────────────
    print(f"\n[ STEP 3 ] Deduplicating …")
    unique, removed = deduplicate(enriched)
    print(f"  ✓  {removed} duplicates removed  →  {len(unique)} unique articles")

    # Re-number IDs after dedup
    for i, art in enumerate(unique, 1):
        art["id"] = i

    # ── Build stats ─────────────────────────────────────────────────────────
    print(f"\n[ STEP 4 ] Building source tracking & category counts …")
    source_tracking = build_source_tracking(unique)
    category_counts = build_category_counts(unique)
    news_counts     = build_news_counts(unique)

    # Print per-country summary
    for iso3 in sorted(source_tracking, key=lambda k: source_tracking[k]["articles"], reverse=True):
        meta     = ISO3_META.get(iso3, {})
        flag     = meta.get("flag", "🌐")
        name     = meta.get("name", iso3)
        n        = source_tracking[iso3]["articles"]
        top_cats = sorted(
            (category_counts.get(iso3, {})).items(),
            key=lambda x: x[1], reverse=True
        )[:3]
        cat_str  = " · ".join(f"{k}({v})" for k, v in top_cats if v > 0)
        pol_risk = news_counts.get(iso3, {}).get("political_risk_count", 0)
        trade_n  = news_counts.get(iso3, {}).get("trade_news_count", 0)
        print(
            f"  {flag} {name:<16}: {n:3d} articles  "
            f"| top: {cat_str}  "
            f"| polRisk={pol_risk} tradeCnt={trade_n}"
        )

    # ── Save outputs ─────────────────────────────────────────────────────────
    print(f"\n[ STEP 5 ] Saving outputs …")
    save_fetch_log(log_rows)
    save_processed_json(
        unique, source_tracking, category_counts, news_counts,
        days_back, removed,
    )

    # ── Final summary ─────────────────────────────────────────────────────────
    impact_dist = {i: sum(1 for a in unique if a["impact_score"] == i) for i in range(1, 6)}
    cat_total   = {}
    for art in unique:
        cat_total[art["category"]] = cat_total.get(art["category"], 0) + 1

    print()
    print("━" * 62)
    print("  SUMMARY")
    print("━" * 62)
    print(f"  Unique articles  : {len(unique)}")
    print(f"  Countries active : {len(source_tracking)}")
    print()
    print("  By impact score:")
    for lvl in range(5, 0, -1):
        bar = "█" * impact_dist.get(lvl, 0)
        print(f"    Impact {lvl} : {impact_dist.get(lvl,0):4d}  {bar[:40]}")
    print()
    print("  By category:")
    for cat in CATEGORY_PRIORITY:
        n = cat_total.get(cat, 0)
        print(f"    {cat:<16}: {n:4d}")

    print()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║  ✓  Done!                                                    ║")
    print("║                                                               ║")
    print("║  Frontend reads from:                                         ║")
    print("║    pipeline/data/processed/news_signals.json                  ║")
    print("║                                                               ║")
    print("║  Next steps:                                                  ║")
    print("║  1. Restart or rebuild the Next.js dev server                 ║")
    print("║  2. Run again daily — GDELT updates in near real-time         ║")
    print("║  3. Use --days 14 to extend look-back window                  ║")
    print("║  4. Use --refresh to bypass today's cache                     ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()


if __name__ == "__main__":
    main()
