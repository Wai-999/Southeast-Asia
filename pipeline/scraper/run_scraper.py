#!/usr/bin/env python3
"""
pipeline/scraper/run_scraper.py
────────────────────────────────
CLI entry point for the SEA Dashboard web scraper.

COMMANDS
────────
  news    — Scrape regional news sites and merge into news_signals.json
  banks   — Scrape central bank press releases → central_bank_releases.json
  url     — Scrape any URL (auto-detects article / links / table)

EXAMPLES
────────
  # All countries, default settings
  python -m scraper.run_scraper news

  # Specific countries only
  python -m scraper.run_scraper news --countries THA VNM SGP IDN

  # Skip cache (force fresh fetch)
  python -m scraper.run_scraper news --no-cache

  # Use proxy pool
  python -m scraper.run_scraper news --proxies http://p1:8080 http://p2:8080

  # Central banks
  python -m scraper.run_scraper banks --countries THA IDN MYS SGP

  # Scrape a single URL (auto mode)
  python -m scraper.run_scraper url https://www.bangkokpost.com/business

  # Force article extraction
  python -m scraper.run_scraper url https://bangkokpost.com/article/123 --mode article

  # Force Playwright for a JS-heavy page
  python -m scraper.run_scraper url https://channelnewsasia.com --js

  # Extract HTML tables from a data page
  python -m scraper.run_scraper url https://www.bot.or.th/statistics --mode table

  # Save news to a custom output file
  python -m scraper.run_scraper news --output /tmp/my_news.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Allow  `python -m scraper.run_scraper`  from inside  pipeline/
sys.path.insert(0, str(Path(__file__).parent.parent))

from scraper.engine import ScraperEngine
from scraper.config import COUNTRY_NEWS_SOURCES, LISTING_URLS, SITE_CONFIGS, CENTRAL_BANK_URLS
from scraper.parser import extract_article, extract_links
from scraper.news.base import NewsArticle
from scraper.output import merge_articles
from scraper.general import scrape_url
from scraper.data.central_banks import scrape_central_banks

try:
    from utils.logger import (
        pipeline_banner, ok, fail, warn, info,
        section, progress, progress_done, step_elapsed,
    )
except ImportError:
    import time as _time

    def pipeline_banner(t: str = "") -> None:
        print(f"\n{'═'*62}\n  {t}\n{'═'*62}\n")

    def ok(m: str)   -> None: print(f"  ✓  {m}")
    def fail(m: str) -> None: print(f"  ✗  {m}", file=sys.stderr)
    def warn(m: str) -> None: print(f"  ⚠  {m}")
    def info(m: str) -> None: print(f"  •  {m}")

    def section(t: str) -> None:
        print(f"\n  {t}\n  {'─' * len(t)}")

    def progress(c: int, t: int, lbl: str = "") -> None:
        print(f"\r  [{c}/{t}] {lbl}", end="", flush=True)

    def progress_done() -> None:
        print()

    def step_elapsed(t0: float) -> None:
        print(f"  • Finished in {_time.time() - t0:.1f}s")


_ALL_COUNTRIES = list(COUNTRY_NEWS_SOURCES.keys())
_ALL_BANKS     = list(CENTRAL_BANK_URLS.keys())


# ── news command ───────────────────────────────────────────────────────────────

async def _run_news(args: argparse.Namespace) -> None:
    import time
    t0 = time.time()
    section("Scraping regional news sites")

    async with ScraperEngine(
        proxies=args.proxies or [],
        cache_dir=Path(__file__).parent.parent / "data" / "raw" / "scraper_cache",
    ) as engine:
        all_articles: list[NewsArticle] = []
        countries = args.countries

        for i, iso3 in enumerate(countries):
            domains = COUNTRY_NEWS_SOURCES.get(iso3, [])
            if not domains:
                warn(f"{iso3}: no scraper configured — skipping")
                continue

            progress(i + 1, len(countries), iso3)

            for domain in domains:
                listing_url = LISTING_URLS.get(domain)
                if not listing_url:
                    continue
                config = SITE_CONFIGS.get(domain, {})

                try:
                    listing_html = await engine.fetch(listing_url, no_cache=args.no_cache)
                    links = extract_links(listing_html, config, base_url=listing_url)

                    if not links:
                        warn(f"{domain}: no links found on listing page")
                        continue

                    info(f"{domain}: {len(links)} article links")

                    # Fetch up to 10 articles per domain
                    htmls = await engine.fetch_many(
                        links[:10], concurrency=3, no_cache=args.no_cache
                    )

                    for url, result in htmls.items():
                        if isinstance(result, Exception):
                            continue
                        parsed = extract_article(result, config, base_url=url)
                        if parsed.get("title"):
                            all_articles.append(NewsArticle.from_parsed(parsed, iso3, domain))

                except Exception as exc:
                    fail(f"{domain}: {exc}")

        progress_done()

    if not all_articles:
        warn("No articles scraped — check selectors or network access")
        return

    summary = merge_articles(all_articles, output_path=args.output)
    ok(
        f"Merged {summary['added']} new articles "
        f"({summary['skipped_duplicates']} duplicates skipped, "
        f"{summary['total']} total in file)"
    )
    step_elapsed(t0)


# ── banks command ──────────────────────────────────────────────────────────────

async def _run_banks(args: argparse.Namespace) -> None:
    import time
    t0 = time.time()
    section("Scraping central bank press releases")

    releases = await scrape_central_banks(
        args.countries,
        no_cache=args.no_cache,
        proxies=args.proxies or [],
        output_path=args.output,
    )

    ok(f"{len(releases)} press releases saved")
    step_elapsed(t0)


# ── url command ────────────────────────────────────────────────────────────────

async def _run_url(args: argparse.Namespace) -> None:
    section(f"Scraping: {args.url}")

    result = await scrape_url(
        args.url,
        mode=args.mode,
        force_js=args.js,
        no_cache=args.no_cache,
    )

    if result.error:
        fail(result.error)
        sys.exit(1)

    info(f"Mode: {result.mode}  |  Domain: {result.domain}")
    print()

    # Pretty-print: truncate body for readability
    data = result.data
    if result.mode == "article" and isinstance(data, dict) and len(data.get("body", "")) > 500:
        data = {**data, "body": data["body"][:500] + " …"}

    print(json.dumps(data, indent=2, ensure_ascii=False))


# ── arg parser ─────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m scraper.run_scraper",
        description="SEA Dashboard — production-grade web scraper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    # ── news ──
    np = sub.add_parser("news", help="Scrape regional news sites")
    np.add_argument(
        "--countries", nargs="+", default=_ALL_COUNTRIES, metavar="ISO3",
        help=f"Countries to scrape (default: all {len(_ALL_COUNTRIES)})",
    )
    np.add_argument("--no-cache", action="store_true", help="Ignore cached responses")
    np.add_argument("--proxies",  nargs="+", metavar="URL", help="Proxy URLs (round-robin)")
    np.add_argument("--output",   type=Path, metavar="FILE",
                    help="Output JSON path (default: data/processed/news_signals.json)")

    # ── banks ──
    bp = sub.add_parser("banks", help="Scrape central bank press releases")
    bp.add_argument(
        "--countries", nargs="+", default=_ALL_BANKS, metavar="ISO3",
        help=f"Countries (default: all {len(_ALL_BANKS)} configured banks)",
    )
    bp.add_argument("--no-cache", action="store_true")
    bp.add_argument("--proxies",  nargs="+", metavar="URL")
    bp.add_argument("--output",   type=Path, metavar="FILE",
                    help="Output path (default: data/processed/central_bank_releases.json)")

    # ── url ──
    up = sub.add_parser("url", help="Scrape a single URL")
    up.add_argument("url")
    up.add_argument(
        "--mode", choices=["auto", "article", "links", "table"], default="auto",
        help="Extraction mode (default: auto-detect)",
    )
    up.add_argument("--js",       dest="js", action="store_true",
                    help="Use Playwright (JS-rendered pages)")
    up.add_argument("--no-cache", action="store_true")

    return p


def main() -> None:
    pipeline_banner("SEA Dashboard — Web Scraper")
    args = _build_parser().parse_args()

    if args.cmd == "news":
        asyncio.run(_run_news(args))
    elif args.cmd == "banks":
        asyncio.run(_run_banks(args))
    elif args.cmd == "url":
        asyncio.run(_run_url(args))


if __name__ == "__main__":
    main()
