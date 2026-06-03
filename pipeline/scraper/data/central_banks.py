"""
pipeline/scraper/data/central_banks.py
──────────────────────────────────────
Scrape central bank press-release listing pages and extract
structured press-release records for ASEAN countries.

Outputs are saved to:
    data/processed/central_bank_releases.json

Each record:
    {
      "country_code": "THA",
      "bank_name":    "Bank of Thailand",
      "title":        "...",
      "url":          "https://...",
      "date":         "2026-05-28",
      "body":         "..."   (first 1000 chars of press release text)
    }

Usage (standalone):
    python -m scraper.data.central_banks
    python -m scraper.data.central_banks --countries THA IDN MYS
"""

from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse

# resolve imports when run as __main__
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scraper.engine import ScraperEngine
from scraper.parser import extract_article, extract_links
from scraper.config import CENTRAL_BANK_URLS

_OUT = Path(__file__).parent.parent / "data" / "processed" / "central_bank_releases.json"


# ── Data model ─────────────────────────────────────────────────────────────────

@dataclass
class PressRelease:
    country_code: str
    bank_name:    str
    title:        str
    url:          str
    date:         str
    body:         str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ── Scraper ────────────────────────────────────────────────────────────────────

async def scrape_central_banks(
    countries: Optional[list[str]] = None,
    *,
    no_cache: bool = False,
    proxies: Optional[list[str]] = None,
    output_path: Optional[Path] = None,
) -> list[PressRelease]:
    """
    Scrape press-release listing pages for each configured central bank.
    Follows up to 10 article links per bank to extract titles and dates.

    Returns a list of PressRelease objects and writes JSON to output_path.
    """
    targets = {
        k: v for k, v in CENTRAL_BANK_URLS.items()
        if countries is None or k in countries
    }

    releases: list[PressRelease] = []

    async with ScraperEngine(proxies=proxies or []) as engine:
        for iso3, cfg in targets.items():
            bank_name = cfg["name"]
            news_url  = cfg["news_url"]
            listing_cfg = {
                "listing_sel": cfg.get("listing_sel", ""),
                "title_sel":   cfg.get("title_sel", "h1"),
                "date_sel":    cfg.get("date_sel", "time[datetime]"),
                "body_sel":    cfg.get("body_sel", ""),
            }

            try:
                listing_html = await engine.fetch(news_url, no_cache=no_cache)
                links = extract_links(listing_html, listing_cfg, base_url=news_url)

                if not links:
                    # Try a looser fallback: any <a> with a long enough path
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(listing_html, "lxml")
                    base_domain = urlparse(news_url).netloc
                    links = [
                        urljoin(news_url, a["href"])
                        for a in soup.find_all("a", href=True)
                        if len(a.get("href", "")) > 10
                        and urlparse(urljoin(news_url, a["href"])).netloc == base_domain
                        and any(kw in a["href"].lower() for kw in
                                ["press", "news", "release", "statement", "publication", "announcement"])
                    ][:10]

                htmls = await engine.fetch_many(links[:10], concurrency=3, no_cache=no_cache)

                for url, result in htmls.items():
                    if isinstance(result, Exception):
                        continue
                    parsed = extract_article(result, listing_cfg, base_url=url)
                    title  = parsed.get("title", "").strip()
                    if not title:
                        continue
                    releases.append(PressRelease(
                        country_code = iso3,
                        bank_name    = bank_name,
                        title        = title,
                        url          = url,
                        date         = parsed.get("date", datetime.now(timezone.utc).strftime("%Y-%m-%d")),
                        body         = parsed.get("body", "")[:1000],
                    ))

            except Exception as exc:
                print(f"  ✗  {bank_name}: {exc}", file=sys.stderr)

    # Write output
    out = output_path or _OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "meta": {
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "total":        len(releases),
                    "countries":    list({r.country_code for r in releases}),
                },
                "releases": [r.to_dict() for r in releases],
            },
            indent=2,
            ensure_ascii=False,
        )
    )

    return releases


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Scrape central bank press releases")
    p.add_argument("--countries", nargs="+", default=None, metavar="ISO3")
    p.add_argument("--no-cache",  action="store_true")
    p.add_argument("--output",    type=Path, default=None)
    args = p.parse_args()

    results = asyncio.run(scrape_central_banks(
        args.countries,
        no_cache=args.no_cache,
        output_path=args.output,
    ))

    print(f"\n  ✓  {len(results)} press releases saved → {args.output or _OUT}")
