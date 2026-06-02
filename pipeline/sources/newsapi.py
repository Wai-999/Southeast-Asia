"""
NewsAPI fetcher — retrieves top headlines per country.
Free tier: 100 requests/day, English only, 1 month history.
Get a key at: https://newsapi.org/register
"""
import httpx
import os
from datetime import datetime, timedelta

BASE = "https://newsapi.org/v2"

# Map ISO alpha-3 to NewsAPI country codes (2-letter)
COUNTRY_MAP = {
    "MMR": "mm", "THA": "th", "VNM": "vn", "KHM": None,  # Cambodia not supported
    "LAO": None,  # Laos not supported — use keyword search instead
    "MYS": "my", "SGP": "sg", "IDN": "id", "PHL": "ph", "BRN": None,
    "CHN": "cn", "IND": "in", "JPN": "jp", "USA": "us",
}

# Keywords for countries without direct NewsAPI support
COUNTRY_KEYWORDS = {
    "KHM": "Cambodia economy",
    "LAO": "Laos economy",
    "BRN": "Brunei economy",
}


def fetch_headlines(country_iso3: str, api_key: str, days_back: int = 7) -> list[dict]:
    """Fetch top headlines for a country. Returns list of article dicts."""
    headers = {"X-Api-Key": api_key}
    from_date = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")

    iso2 = COUNTRY_MAP.get(country_iso3)
    keyword = COUNTRY_KEYWORDS.get(country_iso3)

    articles = []
    with httpx.Client(timeout=15) as client:
        if iso2:
            resp = client.get(
                f"{BASE}/top-headlines",
                headers=headers,
                params={"country": iso2, "pageSize": 10, "category": "business"},
            )
        elif keyword:
            resp = client.get(
                f"{BASE}/everything",
                headers=headers,
                params={"q": keyword, "from": from_date, "sortBy": "relevancy", "pageSize": 10},
            )
        else:
            return []

        resp.raise_for_status()
        data = resp.json()
        for a in data.get("articles", []):
            articles.append({
                "country_id": country_iso3,
                "headline": a.get("title", ""),
                "summary": a.get("description"),
                "source_name": a.get("source", {}).get("name"),
                "source_url": a.get("url"),
                "published_at": a.get("publishedAt"),
            })

    return articles


def fetch_all(api_key: str | None = None) -> list[dict]:
    key = api_key or os.getenv("NEWSAPI_KEY", "")
    all_articles = []
    for iso3 in COUNTRY_MAP:
        print(f"  Fetching news: {iso3}…")
        all_articles.extend(fetch_headlines(iso3, key))
    return all_articles
