"""
pipeline/scraper/general.py
────────────────────────────
General-purpose config-driven scraper.

Given any URL (or list of URLs), auto-detects the page type and extracts:
  • "article"  — title, body text, date, author
  • "links"    — all article/listing URLs on the page
  • "table"    — all HTML tables as 2-D arrays

You can pass custom CSS selectors to override auto-detection for any site.

USAGE
─────
Single URL (standalone):

    from scraper.general import scrape_url, scrape_many
    import asyncio

    result = asyncio.run(scrape_url("https://bangkokpost.com/business"))
    print(result.mode, result.data)

Many URLs (shared engine, concurrent):

    results = asyncio.run(scrape_many([url1, url2, url3]))

Custom selectors:

    result = asyncio.run(scrape_url(
        "https://example.com/article/123",
        mode="article",
        selectors={
            "title_sel": "h1.headline",
            "body_sel":  "div.article-body",
            "date_sel":  "time[datetime]",
        }
    ))
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from .engine import ScraperEngine
from .parser import extract_article, extract_links, extract_tables, detect_page_type
from .config import SITE_CONFIGS


@dataclass
class ScrapeResult:
    url:    str
    mode:   str                      # "article" | "links" | "table"
    data:   "dict | list"
    domain: str
    cached: bool  = False
    error:  Optional[str] = None

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(
            {"url": self.url, "mode": self.mode, "domain": self.domain, "data": self.data},
            indent=indent,
            ensure_ascii=False,
        )


# ── Public API ─────────────────────────────────────────────────────────────────

async def scrape_url(
    url: str,
    *,
    engine:    Optional[ScraperEngine] = None,
    mode:      str = "auto",
    selectors: Optional[dict] = None,
    force_js:  bool = False,
    no_cache:  bool = False,
) -> ScrapeResult:
    """
    Scrape a single URL.

    Parameters
    ──────────
    url        The page to scrape.
    engine     Reuse an existing ScraperEngine (avoids re-creating browser/client).
               If None, a temporary engine is created and torn down after this call.
    mode       "auto" | "article" | "links" | "table"
    selectors  Dict of CSS selectors (title_sel, body_sel, date_sel, author_sel,
               listing_sel). Overrides per-domain SITE_CONFIGS.
    force_js   Always use Playwright even for non-JS domains.
    no_cache   Skip the file cache and fetch fresh.
    """
    domain  = urlparse(url).netloc.removeprefix("www.")
    config  = selectors or SITE_CONFIGS.get(domain, {})

    owns_engine = engine is None
    if owns_engine:
        engine = ScraperEngine()
        await engine.__aenter__()

    try:
        html = await engine.fetch(url, force_js=force_js, no_cache=no_cache)

        if mode == "auto":
            mode = detect_page_type(html)

        if mode == "article":
            data: "dict | list" = extract_article(html, config, base_url=url)
        elif mode == "links":
            data = extract_links(html, config, base_url=url)
        elif mode == "table":
            data = extract_tables(html)
        else:
            data = extract_article(html, config, base_url=url)

        return ScrapeResult(url=url, mode=mode, data=data, domain=domain)

    except Exception as exc:
        return ScrapeResult(url=url, mode=mode, data={}, domain=domain, error=str(exc))
    finally:
        if owns_engine:
            await engine.__aexit__(None, None, None)


async def scrape_many(
    urls: list[str],
    *,
    mode:        str  = "auto",
    selectors:   Optional[dict] = None,
    force_js:    bool = False,
    no_cache:    bool = False,
    concurrency: int  = 5,
) -> list[ScrapeResult]:
    """
    Scrape multiple URLs concurrently, sharing one engine.
    `concurrency` controls how many fetches run in parallel.
    """
    async with ScraperEngine() as engine:
        sem = asyncio.Semaphore(concurrency)

        async def _one(url: str) -> ScrapeResult:
            async with sem:
                return await scrape_url(
                    url,
                    engine=engine,
                    mode=mode,
                    selectors=selectors,
                    force_js=force_js,
                    no_cache=no_cache,
                )

        return list(await asyncio.gather(*[_one(u) for u in urls]))


def scrape_url_sync(url: str, **kwargs) -> ScrapeResult:
    """Synchronous wrapper around scrape_url for use in non-async code."""
    return asyncio.run(scrape_url(url, **kwargs))


def scrape_many_sync(urls: list[str], **kwargs) -> list[ScrapeResult]:
    """Synchronous wrapper around scrape_many."""
    return asyncio.run(scrape_many(urls, **kwargs))
