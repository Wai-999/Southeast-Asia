#!/usr/bin/env python3
"""
==============================================================================
  process_news.py — SEA Change Intelligence Dashboard
==============================================================================

Reads the raw GDELT news signal data and reshapes it into multiple
dashboard-ready views: a live feed, critical alerts, per-country groupings,
and per-category groupings.

INPUT FILE  (must exist before running):
  pipeline/data/processed/news_signals.json   ← from fetch_gdelt_news.py

OUTPUT FILE:
  pipeline/data/processed/news_dashboard.json

WHAT THIS SCRIPT DOES  (step by step)
──────────────────────────────────────
  1. Loads news_signals.json (72+ articles across 17 countries)
  2. Sorts articles newest first, then by highest impact score
  3. Extracts "critical" articles — those with an impact score of 4 or 5
  4. Groups articles by country (for per-country news widgets)
  5. Groups articles by category (for the category filter chips)
  6. Computes a simple risk signal per country: low / medium / high
  7. Counts articles by impact level, category, and sentiment
  8. Saves everything to news_dashboard.json

IMPACT SCORES (reminder)
────────────────────────
  5 — coup, war, major border crisis, central bank shock
  4 — large protest, trade restriction, supply-chain disaster
  3 — normal election news, economic forecast, investment announcement
  2 — local project update, company-level news
  1 — general background news

RISK SIGNAL THRESHOLDS
───────────────────────
  A country receives "high" risk signal if it has 5+ political-risk articles
  in the current 7-day window.  "Medium" if 2–4 political-risk articles
  or 4+ trade-news articles.  Otherwise "low".

HOW TO RUN
──────────
  cd pipeline
  python process_news.py           # normal run
  python process_news.py --refresh # force reprocess

==============================================================================
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from utils.logger import ok, fail, warn, info, section


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 1 — FILE PATHS
# ══════════════════════════════════════════════════════════════════════════════

PROC_DIR = SCRIPT_DIR / "data" / "processed"
NS_FILE  = PROC_DIR / "news_signals.json"
OUT_FILE = PROC_DIR / "news_dashboard.json"


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 2 — RISK SIGNAL THRESHOLDS
# ══════════════════════════════════════════════════════════════════════════════

# A country's political risk signal is "high" when it has this many
# political-category articles in the current window (7 days default)
POL_RISK_HIGH   = 5
POL_RISK_MEDIUM = 2

# Trade news thresholds
TRADE_NEWS_HIGH   = 4
TRADE_NEWS_MEDIUM = 2

# Articles with this score or above are flagged as "critical"
CRITICAL_IMPACT_MIN = 4


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 3 — HELPER FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

def _sort_key(article: dict) -> tuple:
    """
    Sorting key: newest date first, then highest impact score.
    (We negate impact_score because Python's sort is ascending.)
    """
    return (article.get("date", "1900-01-01"), article.get("impact_score", 0))


def _risk_signal(pol_count: int, trade_count: int, total: int) -> str:
    """
    Decide a country's risk signal based on article counts.

    Logic:
      "high"   — 5+ political risk articles in the window
      "medium" — 2–4 political risk articles  OR  4+ trade news articles
      "low"    — everything else
    """
    if pol_count >= POL_RISK_HIGH:
        return "high"
    if pol_count >= POL_RISK_MEDIUM or trade_count >= TRADE_NEWS_HIGH:
        return "medium"
    if trade_count >= TRADE_NEWS_MEDIUM:
        return "medium"
    return "low"


def _top_categories(articles: list[dict], n: int = 3) -> list[str]:
    """Return the top-N categories by article count for a list of articles."""
    counts: dict[str, int] = {}
    for art in articles:
        cat = art.get("category", "")
        if cat:
            counts[cat] = counts.get(cat, 0) + 1
    return sorted(counts, key=lambda c: -counts[c])[:n]


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 4 — CORE PROCESSING
# ══════════════════════════════════════════════════════════════════════════════

def process_news(ns_json: dict) -> dict:
    """
    Transform the raw news_signals.json data into dashboard-ready views.

    Returns a dict with keys:
      feed          — latest_20, critical, impact_5
      by_country    — { iso3: { articles, count, has_critical } }
      by_category   — { category: { articles, count } }
      risk_scores   — { iso3: { political_risk_count, trade_news_count, risk_signal, … } }
      stats         — aggregate counts for the header widgets

    This function never raises — missing fields become empty lists / zero counts.
    """
    articles      = ns_json.get("articles", [])
    news_counts   = ns_json.get("news_counts", {})

    # ── Sort: newest first, then highest impact ─────────────────────────────
    sorted_arts = sorted(articles, key=_sort_key, reverse=True)

    # ── Partition into fast-access slices ───────────────────────────────────
    latest_20 = sorted_arts[:20]
    critical  = [a for a in sorted_arts if a.get("impact_score", 0) >= CRITICAL_IMPACT_MIN]
    impact_5  = [a for a in sorted_arts if a.get("impact_score", 0) == 5]

    # ── Group by country ────────────────────────────────────────────────────
    by_country: dict[str, list[dict]] = {}
    for art in sorted_arts:
        iso3 = art.get("country_code", "UNK")
        by_country.setdefault(iso3, []).append(art)

    # ── Group by category ───────────────────────────────────────────────────
    by_category: dict[str, list[dict]] = {}
    for art in sorted_arts:
        cat = art.get("category", "politics")
        by_category.setdefault(cat, []).append(art)

    # ── Risk scores per country ─────────────────────────────────────────────
    risk_scores: dict[str, dict] = {}
    for iso3, counts in news_counts.items():
        pol    = counts.get("political_risk_count", 0)
        trade  = counts.get("trade_news_count", 0)
        total  = counts.get("total_articles", 0)
        signal = _risk_signal(pol, trade, total)

        country_arts = by_country.get(iso3, [])
        risk_scores[iso3] = {
            "political_risk_count": pol,
            "trade_news_count":     trade,
            "total_articles":       total,
            "risk_signal":          signal,
            "top_categories":       _top_categories(country_arts),
            "has_critical":         any(
                a.get("impact_score", 0) >= CRITICAL_IMPACT_MIN
                for a in country_arts
            ),
        }

    # ── Global statistics ───────────────────────────────────────────────────
    impact_dist: dict[str, int] = {str(i): 0 for i in range(1, 6)}
    cat_totals:  dict[str, int] = {}
    sentiment    = {"positive": 0, "negative": 0, "neutral": 0}

    for art in sorted_arts:
        # Impact distribution
        lvl = str(art.get("impact_score", 1))
        if lvl in impact_dist:
            impact_dist[lvl] += 1

        # Category counts
        cat = art.get("category", "politics")
        cat_totals[cat] = cat_totals.get(cat, 0) + 1

        # Sentiment distribution (derived from tone score)
        tone = art.get("tone", 0.0)
        if tone is None:
            tone = 0.0
        if tone > 0.1:
            sentiment["positive"] += 1
        elif tone < -0.1:
            sentiment["negative"] += 1
        else:
            sentiment["neutral"] += 1

    country_totals = {
        iso3: len(arts)
        for iso3, arts in sorted(by_country.items(), key=lambda x: -len(x[1]))
    }

    return {
        "feed": {
            "latest_20": latest_20,
            "critical":  critical,
            "impact_5":  impact_5,
        },
        "by_country": {
            iso3: {
                "articles":    arts,
                "count":       len(arts),
                "has_critical": any(
                    a.get("impact_score", 0) >= CRITICAL_IMPACT_MIN for a in arts
                ),
            }
            for iso3, arts in by_country.items()
        },
        "by_category": {
            cat: {"articles": arts, "count": len(arts)}
            for cat, arts in sorted(by_category.items(), key=lambda x: -len(x[1]))
        },
        "risk_scores": risk_scores,
        "stats": {
            "total":           len(sorted_arts),
            "critical_count":  len(critical),
            "impact_5_count":  len(impact_5),
            "by_impact":       impact_dist,
            "by_category":     dict(
                sorted(cat_totals.items(), key=lambda x: -x[1])
            ),
            "by_country":      country_totals,
            "sentiment":       sentiment,
        },
    }


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 5 — MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main() -> int:
    """
    Exit codes:
      0 — completed successfully
      1 — fatal error (missing input, can't write output)
    """
    parser = argparse.ArgumentParser(
        description="Process GDELT news signals for SEA Dashboard"
    )
    parser.add_argument("--refresh", action="store_true",
                        help="Force reprocess even if output already exists today")
    parser.parse_args()

    # ── Banner ──────────────────────────────────────────────────────────────
    print()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║   SEA Dashboard — Process News Signals                      ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()
    print(f"  Input  : {NS_FILE.relative_to(SCRIPT_DIR)}")
    print(f"  Output : {OUT_FILE.relative_to(SCRIPT_DIR)}")
    print()

    # ── Step 1: Load ────────────────────────────────────────────────────────
    section("Step 1 — Load news signals")
    if not NS_FILE.exists():
        fail(
            f"News signals file not found: {NS_FILE}\n"
            "  → Run this first:  python fetch_gdelt_news.py"
        )
        return 1

    with open(NS_FILE, encoding="utf-8") as f:
        ns_json = json.load(f)

    raw_meta = ns_json.get("meta", {})
    articles = ns_json.get("articles", [])

    ok(f"Loaded {len(articles)} articles (fetched {raw_meta.get('generated_at', '?')})")
    ok(f"GDELT window: {raw_meta.get('start_date', '?')} → {raw_meta.get('end_date', '?')}")

    # Warn if a rate-limited flag was set by the fetch script
    if raw_meta.get("rate_limited_at"):
        warn(
            f"Last refresh was rate-limited at {raw_meta['rate_limited_at']} "
            "— displaying cached articles"
        )

    if len(articles) == 0:
        warn("No articles in file — output will be empty but valid")

    # ── Step 2: Process ──────────────────────────────────────────────────────
    section("Step 2 — Process and reshape articles")
    try:
        processed = process_news(ns_json)
    except Exception as exc:
        fail(f"Processing failed unexpectedly: {exc}")
        return 1

    stats = processed["stats"]
    ok(f"Total articles  : {stats['total']}")
    ok(f"Critical (4–5)  : {stats['critical_count']}")
    ok(f"Impact 5 only   : {stats['impact_5_count']}")

    info("Impact distribution:")
    for lvl in range(5, 0, -1):
        n   = stats["by_impact"].get(str(lvl), 0)
        bar = "█" * min(n, 40)
        info(f"  Impact {lvl}: {n:3d}  {bar}")

    info("Top categories:")
    for cat, n in list(stats["by_category"].items())[:6]:
        info(f"  {cat:<16}: {n}")

    # ── Step 3: Risk signals ─────────────────────────────────────────────────
    section("Step 3 — Compute country risk signals")
    high_risk   = [iso3 for iso3, r in processed["risk_scores"].items()
                   if r["risk_signal"] == "high"]
    medium_risk = [iso3 for iso3, r in processed["risk_scores"].items()
                   if r["risk_signal"] == "medium"]

    if high_risk:
        warn(f"HIGH risk   : {', '.join(high_risk)}")
    if medium_risk:
        info(f"Medium risk : {', '.join(medium_risk)}")
    ok(f"Risk signals computed for {len(processed['risk_scores'])} countries")

    # ── Step 4: Save ─────────────────────────────────────────────────────────
    section("Step 4 — Save processed output")
    output = {
        "meta": {
            "generated_at":        datetime.now().isoformat(timespec="seconds"),
            "script":              "process_news.py",
            "source_url":          str(NS_FILE.relative_to(SCRIPT_DIR)),
            "fetched_at":          raw_meta.get("generated_at", ""),
            "gdelt_window_start":  raw_meta.get("start_date", ""),
            "gdelt_window_end":    raw_meta.get("end_date", ""),
            "total_articles":      len(articles),
            "critical_articles":   stats["critical_count"],
            "data_status":         raw_meta.get("data_status", "unknown"),
            "refresh_note": (
                "Run 'python fetch_gdelt_news.py && python process_news.py' "
                "to refresh with the latest GDELT news data."
            ),
        },
        **processed,
    }

    PROC_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with open(OUT_FILE, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        size_kb = OUT_FILE.stat().st_size // 1024
        ok(f"Saved → {OUT_FILE.relative_to(SCRIPT_DIR)}  ({size_kb} KB)")
    except Exception as exc:
        fail(f"Could not save output: {exc}")
        return 1

    # ── Final summary ────────────────────────────────────────────────────────
    print()
    print("━" * 62)
    ok("process_news.py complete")
    info(f"  {stats['total']} articles · {stats['critical_count']} critical · "
         f"{len(processed['risk_scores'])} country risk scores")
    info(f"  Output: {OUT_FILE}")
    print("━" * 62)
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
