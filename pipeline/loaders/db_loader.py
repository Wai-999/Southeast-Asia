"""
Database loader — upserts fetched data into PostgreSQL.
Uses ON CONFLICT DO UPDATE to avoid duplicates on re-runs.
"""
import os
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5432/sea_dashboard")


def get_conn():
    return psycopg2.connect(DATABASE_URL)


def upsert_indicator_values(rows: list[dict], indicator_db_id: int) -> int:
    """
    rows: list of {country_id (ISO3), year, value}
    Returns number of rows upserted.
    """
    if not rows:
        return 0

    data = [
        (r["country_id"], indicator_db_id, r["year"], None, None, r["value"])
        for r in rows
    ]

    with get_conn() as conn, conn.cursor() as cur:
        execute_values(
            cur,
            """
            INSERT INTO indicator_values (country_id, indicator_id, year, quarter, month, value)
            VALUES %s
            ON CONFLICT (country_id, indicator_id, year, quarter, month)
            DO UPDATE SET value = EXCLUDED.value, fetched_at = NOW()
            """,
            data,
        )
        conn.commit()
    return len(data)


def upsert_news_events(articles: list[dict]) -> int:
    """Insert news articles, skipping exact headline duplicates per country."""
    if not articles:
        return 0

    inserted = 0
    with get_conn() as conn, conn.cursor() as cur:
        for a in articles:
            cur.execute(
                """
                INSERT INTO news_events (country_id, headline, summary, source_name, source_url, published_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                (
                    a["country_id"], a["headline"], a.get("summary"),
                    a.get("source_name"), a.get("source_url"), a.get("published_at"),
                ),
            )
            inserted += cur.rowcount
        conn.commit()
    return inserted


def get_indicator_id(code: str) -> int | None:
    """Look up indicator ID by code."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM indicators WHERE code = %s", (code,))
        row = cur.fetchone()
        return row[0] if row else None
