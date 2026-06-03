"""
pipeline/scraper/parser.py
──────────────────────────
HTML parsing utilities built on BeautifulSoup4 + lxml.

Three extraction modes
──────────────────────
  extract_article(html, config, base_url)
      → dict with title / body / date / author / url
      Uses site CSS selectors first, falls back to Open Graph / schema.org.

  extract_links(html, config, base_url)
      → list[str] of absolute article URLs from a listing page.
      Filters to same domain, deduplicates, caps at 30.

  extract_tables(html)
      → list of 2-D string arrays, one per <table> in the page.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag
from dateutil import parser as dateparser


# ── Soup helpers ───────────────────────────────────────────────────────────────

def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


def _text(el: Optional[Tag]) -> str:
    if not el:
        return ""
    return " ".join(el.get_text(" ", strip=True).split())


def _sel(soup: BeautifulSoup, selector: str) -> str:
    """Try each comma-separated selector; return text of first match."""
    for s in selector.split(","):
        s = s.strip()
        if not s:
            continue
        el = soup.select_one(s)
        if el:
            return _text(el)
    return ""


def _body_text(soup: BeautifulSoup, selector: str) -> str:
    """
    Like _sel but extracts clean paragraph text from the matched container.
    Removes script/style/nav/aside noise before extracting.
    """
    for s in selector.split(","):
        s = s.strip()
        if not s:
            continue
        el = soup.select_one(s)
        if not el:
            continue
        for noise in el(["script", "style", "aside", "nav", "footer", "figure", "figcaption"]):
            noise.decompose()
        paragraphs = el.find_all("p")
        if paragraphs:
            return " ".join(_text(p) for p in paragraphs if _text(p))
        return _text(el)
    return ""


# ── Open Graph / schema.org fallbacks ─────────────────────────────────────────

def _og(soup: BeautifulSoup, prop: str) -> str:
    el = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
    return (el.get("content") or "") if el else ""


def _schema(soup: BeautifulSoup, itemprop: str) -> str:
    el = soup.find(attrs={"itemprop": itemprop})
    if not el:
        return ""
    return el.get("content") or _text(el)


# ── Date normalization ─────────────────────────────────────────────────────────

def _parse_date(raw: str) -> str:
    """
    Normalise an arbitrary date string to ISO-8601 (YYYY-MM-DD).
    Returns today's date string if parsing fails.
    """
    if not raw:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")
    clean = re.sub(r"\s+", " ", raw).strip()
    try:
        dt = dateparser.parse(clean, fuzzy=True)
        return dt.strftime("%Y-%m-%d") if dt else datetime.now(timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ── Public API ─────────────────────────────────────────────────────────────────

def extract_article(html: str, config: dict, base_url: str = "") -> dict:
    """
    Extract a news article using site-specific CSS selectors with OG/schema fallbacks.

    Returns a dict with: title, body, date, author, url
    """
    soup = _soup(html)

    title = (
        _sel(soup, config.get("title_sel", ""))
        or _og(soup, "og:title")
        or _schema(soup, "headline")
        or _sel(soup, "h1")
    )

    body = (
        _body_text(soup, config.get("body_sel", ""))
        or _schema(soup, "articleBody")
    )

    raw_date = (
        _sel(soup, config.get("date_sel", ""))
        or _og(soup, "article:published_time")
        or _schema(soup, "datePublished")
    )

    # Also check datetime attribute directly on <time> tags
    if not raw_date:
        time_el = soup.find("time", attrs={"datetime": True})
        if time_el:
            raw_date = time_el["datetime"]

    author = (
        _sel(soup, config.get("author_sel", ""))
        or _schema(soup, "author")
        or _og(soup, "article:author")
    )

    return {
        "title":  title.strip(),
        "body":   body[:3000],  # cap body size
        "date":   _parse_date(raw_date),
        "author": author.strip(),
        "url":    base_url,
    }


def extract_links(html: str, config: dict, base_url: str) -> list[str]:
    """
    Extract article URLs from a listing/index page.

    Returns absolute, deduplicated URLs on the same domain, capped at 30.
    """
    soup   = _soup(html)
    sel    = config.get("listing_sel", "")
    links: list[str] = []

    if sel:
        for el in soup.select(sel):
            # The selector may target the <a> directly or a parent element
            if el.name == "a":
                href = el.get("href")
            else:
                a = el.find("a")
                href = a.get("href") if a else None

            if href and not href.startswith(("#", "javascript:", "mailto:")):
                links.append(urljoin(base_url, href))

    # Fallback: grab any <a> inside <article> or <h2>/<h3> tags
    if not links:
        for el in soup.select("article a, h2 a, h3 a"):
            href = el.get("href")
            if href and not href.startswith(("#", "javascript:", "mailto:")):
                links.append(urljoin(base_url, href))

    base_domain = urlparse(base_url).netloc
    seen: set[str] = set()
    clean: list[str] = []
    for u in links:
        parsed = urlparse(u)
        # Same domain, has a path longer than just "/"
        if parsed.netloc == base_domain and len(parsed.path) > 1 and u not in seen:
            seen.add(u)
            clean.append(u)

    return clean[:30]


def extract_tables(html: str) -> list[list[list[str]]]:
    """
    Extract all HTML tables as a list of 2-D string arrays.

    Return format: [ [ [cell, cell, ...], [cell, ...] ], ... ]
    Each outer list is one table; each inner list is one row.
    """
    soup   = _soup(html)
    result = []
    for table in soup.find_all("table"):
        rows = []
        for tr in table.find_all("tr"):
            cells = [_text(td) for td in tr.find_all(["td", "th"])]
            if any(cells):
                rows.append(cells)
        if rows:
            result.append(rows)
    return result


def detect_page_type(html: str) -> str:
    """
    Heuristic to detect whether a page is an article, a listing, or a data table.

    Returns "article" | "links" | "table"
    """
    soup   = _soup(html)
    tables = soup.find_all("table")
    links  = soup.select("article a, h2 a, h3 a, .article-list a")

    if len(tables) >= 3:
        return "table"
    if len(links) >= 8:
        return "links"
    return "article"
