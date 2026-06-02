"""
Daily pipeline — run this script once a day (via cron or manually).
Fetches World Bank indicators, exchange rates, and news headlines,
then loads everything into PostgreSQL.

Usage:
    python pipeline/run_daily.py
"""
import os
import sys
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from pipeline.sources import worldbank, exchangerate, newsapi
from pipeline.loaders.db_loader import upsert_indicator_values, upsert_news_events, get_indicator_id

CURRENT_YEAR = datetime.utcnow().year


def run():
    print(f"\n=== SEA Dashboard — Daily Pipeline ({datetime.utcnow().isoformat()}) ===\n")

    # 1. World Bank economic indicators
    print("[1/3] Fetching World Bank indicators…")
    wb_data = worldbank.fetch_all(start_year=CURRENT_YEAR - 5, end_year=CURRENT_YEAR - 1)
    for code, rows in wb_data.items():
        indicator_id = get_indicator_id(code)
        if not indicator_id:
            print(f"  SKIP: indicator '{code}' not found in DB")
            continue
        n = upsert_indicator_values(rows, indicator_id)
        print(f"  {code}: {n} rows upserted")

    # 2. Exchange rates
    print("\n[2/3] Fetching exchange rates…")
    fx_rows = exchangerate.fetch_rates()
    fx_id = get_indicator_id("exchange_rate")
    if fx_id:
        n = upsert_indicator_values(fx_rows, fx_id)
        print(f"  exchange_rate: {n} rows upserted")

    # 3. News headlines
    print("\n[3/3] Fetching news headlines…")
    api_key = os.getenv("NEWSAPI_KEY", "")
    if not api_key:
        print("  SKIP: NEWSAPI_KEY not set in .env")
    else:
        articles = newsapi.fetch_all(api_key)
        n = upsert_news_events(articles)
        print(f"  news_events: {n} new articles inserted")

    print("\n=== Pipeline complete ===\n")


if __name__ == "__main__":
    run()
