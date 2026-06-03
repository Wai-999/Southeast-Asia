"""
pipeline/scraper/news/base.py
──────────────────────────────
NewsArticle dataclass and classification helpers.

The schema exactly matches the articles array in data/processed/news_signals.json
so scraped articles can be merged directly alongside GDELT results.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from ..config import COUNTRY_NAMES


# ── Category classification ────────────────────────────────────────────────────
# Mirrors the logic in fetch_gdelt_news.py so scraped articles get the same
# category labels as GDELT articles.

_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "tariff":       ["tariff", "customs duty", "import tax", "trade war", "wto dispute"],
    "trade":        ["trade", "export", "import", "fta", "rcep", "free trade", "comtrade", "trade deficit", "trade surplus"],
    "sanctions":    ["sanction", "embargo", "blacklist", "ban", "blocked", "restricted", "penalti"],
    "political":    ["election", "coup", "parliament", "minister", "president", "prime minister", "protest", "government", "vote"],
    "economic":     ["gdp", "inflation", "interest rate", "central bank", "recession", "fiscal", "budget", "debt", "currency"],
    "investment":   ["fdi", "investment", "infrastructure", "project", "factory", "fund", "bond", "stock market"],
    "energy":       ["oil", "gas", "lng", "energy", "power", "electricity", "coal", "renewable", "solar", "wind"],
    "natural":      ["flood", "typhoon", "cyclone", "earthquake", "drought", "disaster", "climate", "heatwave"],
    "security":     ["military", "conflict", "war", "bomb", "attack", "terrorist", "troops", "navy", "south china sea"],
    "tech":         ["technology", "digital", "ai", "semiconductor", "chip", "startup", "fintech", "5g"],
    "social":       ["poverty", "unemployment", "education", "healthcare", "wages", "labour", "workers"],
    "supply_chain": ["supply chain", "logistics", "port", "shipping", "freight", "container"],
}

_IMPACT_KEYWORDS: dict[int, list[str]] = {
    5: ["coup", "war", "sanction", "embargo", "crisis", "default", "collapse", "border clos",
        "state of emergency", "martial law", "central bank rate", "rate hike", "rate cut"],
    4: ["protest", "strike", "trade war", "supply chain disruption", "inflation spike",
        "ban on export", "ban on import", "trade restriction"],
    3: ["election", "economic forecast", "growth", "investment project", "reform", "policy change"],
    2: ["company", "local", "project announced", "plan", "proposal"],
}

_INDICATOR_MAP: dict[str, list[str]] = {
    "tariff":       ["exports", "imports", "tradeNewsCount", "fdi"],
    "trade":        ["exports", "imports", "tradeNewsCount"],
    "sanctions":    ["exports", "imports", "fdi"],
    "economic":     ["gdp_growth", "inflation", "interest_rate"],
    "investment":   ["fdi"],
    "energy":       ["gdp_growth"],
    "political":    [],
    "security":     [],
    "natural":      ["gdp_growth"],
    "supply_chain": ["exports", "imports"],
}


def classify_category(text: str) -> str:
    t = text.lower()
    for cat, kws in _CATEGORY_KEYWORDS.items():
        if any(kw in t for kw in kws):
            return cat
    return "general"


def score_impact(text: str) -> int:
    t = text.lower()
    for score in range(5, 1, -1):
        if any(kw in t for kw in _IMPACT_KEYWORDS.get(score, [])):
            return score
    return 1


def score_tone(text: str) -> float:
    """
    Rough sentiment score in [-1.0, 1.0].
    Positive words push toward +1, negative toward -1.
    """
    positive = ["growth", "increase", "rise", "gain", "improve", "surge", "boom",
                "record", "recovery", "expand", "investment", "agreement", "peace"]
    negative = ["fall", "decline", "crisis", "war", "conflict", "sanction", "coup",
                "default", "collapse", "ban", "restrict", "protest", "inflation",
                "shortage", "disruption", "attack"]
    t   = text.lower()
    pos = sum(1 for w in positive if w in t)
    neg = sum(1 for w in negative if w in t)
    total = pos + neg
    if total == 0:
        return 0.0
    return round((pos - neg) / total, 2)


def url_hash(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:12]


# ── Dataclass ──────────────────────────────────────────────────────────────────

@dataclass
class NewsArticle:
    """
    One scraped news article.  Schema matches news_signals.json exactly.
    """
    title:               str
    url:                 str
    country_code:        str                       # ISO3, e.g. "THA"
    source_domain:       str                       # e.g. "bangkokpost.com"
    date:                str                       # YYYY-MM-DD
    body:                str         = ""
    author:              str         = ""
    category:            str         = "general"
    all_categories:      list[str]   = field(default_factory=list)
    tone:                float       = 0.0
    language:            str         = "English"
    impact_score:        int         = 1
    connected_indicators: list[str]  = field(default_factory=list)

    @classmethod
    def from_parsed(
        cls,
        parsed: dict,
        country_code: str,
        domain: str,
    ) -> "NewsArticle":
        """Build a NewsArticle from the dict returned by parser.extract_article."""
        title    = parsed.get("title", "").strip()
        body     = parsed.get("body", "")
        combined = f"{title} {body}"

        cat  = classify_category(combined)
        cats = list({cat} | {
            c for c, kws in _CATEGORY_KEYWORDS.items()
            if any(kw in combined.lower() for kw in kws)
        })

        return cls(
            title                = title,
            url                  = parsed.get("url", ""),
            country_code         = country_code,
            source_domain        = domain,
            date                 = parsed.get("date", datetime.now(timezone.utc).strftime("%Y-%m-%d")),
            body                 = body,
            author               = parsed.get("author", ""),
            category             = cat,
            all_categories       = cats,
            tone                 = score_tone(combined),
            language             = "English",
            impact_score         = score_impact(combined),
            connected_indicators = _INDICATOR_MAP.get(cat, []),
        )

    def to_dict(self, article_id: int = 0) -> dict:
        """Serialize to the news_signals.json article format."""
        return {
            "id":                   article_id,
            "title":                self.title,
            "url":                  self.url,
            "source_domain":        self.source_domain,
            "date":                 self.date,
            "country_code":         self.country_code,
            "country_name":         COUNTRY_NAMES.get(self.country_code, self.country_code),
            "category":             self.category,
            "all_categories":       self.all_categories,
            "tone":                 self.tone,
            "language":             self.language,
            "impact_score":         self.impact_score,
            "connected_indicators": self.connected_indicators,
            "source":               "scraper",
            "gdelt_seendate":       None,
            "url_hash":             url_hash(self.url),
        }
