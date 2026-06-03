"""
pipeline/scraper/output.py
──────────────────────────
Merge scraped articles into data/processed/news_signals.json.

Preserves all existing GDELT articles. Deduplicates by url_hash.
Updates meta counters so the dashboard reads correct totals.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .news.base import NewsArticle

_PROCESSED = Path(__file__).parent.parent / "data" / "processed"
_NEWS_FILE = _PROCESSED / "news_signals.json"


def _load() -> dict:
    if _NEWS_FILE.exists():
        try:
            return json.loads(_NEWS_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"meta": {}, "source_tracking": {}, "category_counts": {}, "news_counts": {}, "articles": []}


def merge_articles(
    new_articles: list[NewsArticle],
    *,
    output_path: Optional[Path] = None,
) -> dict:
    """
    Merge a list of NewsArticle objects into news_signals.json.

    Returns {"added": int, "total": int, "skipped_duplicates": int}.
    """
    data = _load()
    existing_articles: list[dict] = data.setdefault("articles", [])

    # Index existing by url_hash for O(1) dedup
    existing_hashes = {a.get("url_hash") for a in existing_articles if a.get("url_hash")}
    next_id         = max((a.get("id", 0) for a in existing_articles), default=0) + 1

    added      = 0
    duplicates = 0

    for article in new_articles:
        d = article.to_dict(article_id=next_id)
        if d["url_hash"] in existing_hashes:
            duplicates += 1
            continue
        existing_articles.append(d)
        existing_hashes.add(d["url_hash"])
        next_id += 1
        added   += 1

    # Refresh top-level meta
    data.setdefault("meta", {}).update({
        "last_scraper_run":      datetime.now(timezone.utc).isoformat(),
        "total_articles":        len(existing_articles),
        "scraper_total_added":   data["meta"].get("scraper_total_added", 0) + added,
        "scraper_last_added":    added,
    })

    # Refresh source_tracking with scraper domains
    st: dict = data.setdefault("source_tracking", {})
    for article in new_articles:
        entry = st.setdefault(article.country_code, {"articles": 0, "sources": [], "top_domain": ""})
        entry["articles"] = entry.get("articles", 0) + 1
        if article.source_domain not in entry["sources"]:
            entry["sources"].append(article.source_domain)

    # Refresh category_counts
    cc: dict = data.setdefault("category_counts", {})
    for article in new_articles:
        cc[article.category] = cc.get(article.category, 0) + 1

    out = output_path or _NEWS_FILE
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    return {"added": added, "total": len(existing_articles), "skipped_duplicates": duplicates}
