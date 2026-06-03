"""
pipeline/scraper/engine.py
──────────────────────────
Core scraping engine.

Features
────────
  • Async httpx client — connection pooling, keep-alive, follow redirects
  • Playwright fallback — auto-triggers for JS-heavy domains (CNA, ST, etc.)
  • Rotating user agents — picks a random UA per request
  • Per-domain token-bucket rate limiter — never hammers a site
  • Proxy pool — round-robin through your list; skipped if list is empty
  • Exponential backoff retry — 2ⁿ + jitter on network/HTTP errors
  • File-based response cache — TTL configurable, keyed by URL hash

Usage
─────
    async with ScraperEngine() as engine:
        html = await engine.fetch("https://bangkokpost.com/business")

    # or scrape many URLs concurrently
    async with ScraperEngine() as engine:
        results = await engine.fetch_many(urls, concurrency=5)
"""

from __future__ import annotations

import asyncio
import hashlib
import random
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import httpx

from .config import USER_AGENTS, RATE_LIMITS, JS_REQUIRED_DOMAINS

# ── Optional Playwright ────────────────────────────────────────────────────────

try:
    from playwright.async_api import async_playwright, Browser, BrowserContext, Playwright
    _PLAYWRIGHT_OK = True
except ImportError:
    _PLAYWRIGHT_OK = False


# ── Token-bucket rate limiter (per domain) ────────────────────────────────────

class _TokenBucket:
    """Asyncio-safe token bucket."""

    def __init__(self, rate: int, per: float) -> None:
        self._rate   = rate        # tokens per period
        self._per    = per         # period in seconds
        self._tokens = float(rate)
        self._last   = time.monotonic()
        self._lock   = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now     = time.monotonic()
            elapsed = now - self._last
            self._tokens = min(self._rate, self._tokens + elapsed * (self._rate / self._per))
            self._last   = now
            if self._tokens < 1.0:
                wait = (1.0 - self._tokens) * (self._per / self._rate)
                await asyncio.sleep(wait)
                self._tokens = 0.0
            else:
                self._tokens -= 1.0


class RateLimiter:
    def __init__(self) -> None:
        self._buckets: dict[str, _TokenBucket] = {}

    def _bucket(self, domain: str) -> _TokenBucket:
        if domain not in self._buckets:
            rate, per = RATE_LIMITS.get(domain, RATE_LIMITS["default"])
            self._buckets[domain] = _TokenBucket(rate, per)
        return self._buckets[domain]

    async def wait(self, url: str) -> None:
        domain = urlparse(url).netloc.removeprefix("www.")
        await self._bucket(domain).acquire()


# ── File-based response cache ─────────────────────────────────────────────────

class FileCache:
    def __init__(self, cache_dir: Path, ttl_hours: int = 6) -> None:
        self._dir = cache_dir
        self._ttl = ttl_hours * 3600
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, url: str) -> Path:
        key = hashlib.sha256(url.encode()).hexdigest()[:20]
        return self._dir / f"{key}.html"

    def get(self, url: str) -> Optional[str]:
        p = self._path(url)
        if p.exists() and (time.time() - p.stat().st_mtime) < self._ttl:
            return p.read_text(encoding="utf-8", errors="replace")
        return None

    def set(self, url: str, html: str) -> None:
        try:
            self._path(url).write_text(html, encoding="utf-8")
        except OSError:
            pass  # cache write failure is non-fatal


# ── Proxy pool (round-robin) ──────────────────────────────────────────────────

class ProxyPool:
    def __init__(self, proxies: list[str]) -> None:
        self._proxies = proxies
        self._idx     = 0

    def next(self) -> Optional[str]:
        if not self._proxies:
            return None
        p = self._proxies[self._idx % len(self._proxies)]
        self._idx += 1
        return p

    def has_proxies(self) -> bool:
        return bool(self._proxies)


# ── Core engine ───────────────────────────────────────────────────────────────

class ScraperEngine:
    """
    Production-grade async scraping engine.

    Parameters
    ──────────
    cache_dir      Path for file-based HTML cache (default: pipeline/data/raw/scraper_cache)
    cache_ttl_hours  How long cached responses stay valid (default: 6 h)
    proxies        List of proxy URLs for round-robin rotation
    max_retries    Attempts per URL before giving up (default: 3)
    timeout        Per-request timeout in seconds (default: 20)
    headless       Whether Playwright browser runs headless (default: True)
    """

    def __init__(
        self,
        *,
        cache_dir: Optional[Path] = None,
        cache_ttl_hours: int = 6,
        proxies: Optional[list[str]] = None,
        max_retries: int = 3,
        timeout: float = 20.0,
        headless: bool = True,
    ) -> None:
        self._rate      = RateLimiter()
        self._cache     = FileCache(
            cache_dir or Path(__file__).parent.parent / "data" / "raw" / "scraper_cache",
            cache_ttl_hours,
        )
        self._proxies   = ProxyPool(proxies or [])
        self._retries   = max_retries
        self._timeout   = timeout
        self._headless  = headless
        self._client:   Optional[httpx.AsyncClient] = None
        self._browser:  Optional["Browser"]         = None
        self._pw:       Optional["Playwright"]       = None
        self._pw_ctx    = None

    # ── lifecycle ──────────────────────────────────────────────────────────────

    async def __aenter__(self) -> "ScraperEngine":
        self._client = httpx.AsyncClient(
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            timeout=httpx.Timeout(self._timeout),
            follow_redirects=True,
        )
        return self

    async def __aexit__(self, *_) -> None:
        if self._client:
            await self._client.aclose()
        await self._close_browser()

    # ── Playwright ─────────────────────────────────────────────────────────────

    async def _get_browser(self) -> "Browser":
        if self._browser:
            return self._browser
        if not _PLAYWRIGHT_OK:
            raise RuntimeError(
                "playwright not installed.\n"
                "  pip install playwright\n"
                "  playwright install chromium"
            )
        self._pw_ctx = async_playwright()
        self._pw     = await self._pw_ctx.__aenter__()
        self._browser = await self._pw.chromium.launch(headless=self._headless)
        return self._browser

    async def _close_browser(self) -> None:
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._pw_ctx:
            try:
                await self._pw_ctx.__aexit__(None, None, None)
            except Exception:
                pass
            self._pw_ctx = None

    # ── request helpers ────────────────────────────────────────────────────────

    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent":                random.choice(USER_AGENTS),
            "Accept":                    "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language":           "en-US,en;q=0.9",
            "Accept-Encoding":           "gzip, deflate, br",
            "DNT":                       "1",
            "Connection":                "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest":            "document",
            "Sec-Fetch-Mode":            "navigate",
            "Sec-Fetch-Site":            "none",
            "Cache-Control":             "max-age=0",
        }

    async def _fetch_httpx(self, url: str) -> str:
        proxy = self._proxies.next()
        kwargs: dict = {}
        if proxy:
            kwargs["proxy"] = proxy

        last_exc: Exception = RuntimeError("no attempts made")
        for attempt in range(self._retries):
            try:
                await self._rate.wait(url)
                resp = await self._client.get(url, headers=self._headers(), **kwargs)
                resp.raise_for_status()
                return resp.text
            except (httpx.HTTPStatusError, httpx.RequestError) as exc:
                last_exc = exc
                if attempt < self._retries - 1:
                    jitter = random.uniform(0.0, 1.0)
                    await asyncio.sleep(2 ** attempt + jitter)
        raise last_exc

    async def _fetch_playwright(self, url: str) -> str:
        browser = await self._get_browser()
        ua      = random.choice(USER_AGENTS)
        ctx_opts: dict = {"user_agent": ua}
        proxy = self._proxies.next()
        if proxy:
            ctx_opts["proxy"] = {"server": proxy}

        last_exc: Exception = RuntimeError("no attempts made")
        for attempt in range(self._retries):
            ctx: Optional["BrowserContext"] = None
            try:
                await self._rate.wait(url)
                ctx  = await browser.new_context(**ctx_opts)
                page = await ctx.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=int(self._timeout * 1000))
                try:
                    await page.wait_for_load_state("networkidle", timeout=5000)
                except Exception:
                    pass
                return await page.content()
            except Exception as exc:
                last_exc = exc
                if attempt < self._retries - 1:
                    jitter = random.uniform(0.0, 1.0)
                    await asyncio.sleep(2 ** attempt + jitter)
            finally:
                if ctx:
                    await ctx.close()
        raise last_exc

    # ── public API ─────────────────────────────────────────────────────────────

    async def fetch(
        self,
        url: str,
        *,
        force_js: bool = False,
        no_cache: bool = False,
    ) -> str:
        """
        Fetch a URL and return its HTML.

        • Checks file cache first (unless no_cache=True).
        • Uses Playwright for JS-heavy domains or when force_js=True.
        • Falls back from httpx → Playwright automatically on 403/JS walls.
        • Respects per-domain rate limits.
        """
        if not no_cache:
            cached = self._cache.get(url)
            if cached:
                return cached

        domain = urlparse(url).netloc.removeprefix("www.")
        use_js = force_js or (domain in JS_REQUIRED_DOMAINS)

        if use_js:
            html = await self._fetch_playwright(url)
        else:
            try:
                html = await self._fetch_httpx(url)
                # Auto-fallback: blank/suspiciously short page → probably JS-blocked
                if len(html.strip()) < 500 and _PLAYWRIGHT_OK:
                    html = await self._fetch_playwright(url)
            except Exception:
                if _PLAYWRIGHT_OK:
                    html = await self._fetch_playwright(url)
                else:
                    raise

        self._cache.set(url, html)
        return html

    async def fetch_many(
        self,
        urls: list[str],
        *,
        concurrency: int = 5,
        force_js: bool = False,
        no_cache: bool = False,
    ) -> dict[str, "str | Exception"]:
        """
        Fetch multiple URLs concurrently, up to `concurrency` at a time.
        Returns {url: html_string} or {url: Exception} on failure.
        """
        sem = asyncio.Semaphore(concurrency)

        async def _one(url: str) -> tuple[str, "str | Exception"]:
            async with sem:
                try:
                    return url, await self.fetch(url, force_js=force_js, no_cache=no_cache)
                except Exception as exc:
                    return url, exc

        pairs = await asyncio.gather(*[_one(u) for u in urls])
        return dict(pairs)
