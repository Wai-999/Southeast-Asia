#!/usr/bin/env python3
"""
==============================================================================
  scripts/fetch_worldbank.py — SEA Change Intelligence Dashboard
==============================================================================

Convenience wrapper so you can run the World Bank fetcher from the project root.
All actual logic lives in pipeline/fetch_worldbank.py.

USAGE (run from project root):
    python scripts/fetch_worldbank.py
    python scripts/fetch_worldbank.py --refresh   # bypass today's cache

WHAT IT DOES:
    Fetches 8 economic indicators for 17 countries (11 SEA + 6 partners)
    from the World Bank Open Data API (free, no key required).

    Years fetched: 2015–2026
    — 2015–2024: official World Bank annual data
    — 2025–2026: rows are included; null if WB has not yet published
                 (forward-fill is disabled for 2025/2026 — no fake values)

OUTPUT (all written to pipeline/data/):
    pipeline/data/processed/worldbank_indicators.json   ← frontend reads this
    pipeline/data/raw/worldbank/raw_*.json              ← one per indicator
    pipeline/data/raw/worldbank/raw_all_*.csv           ← combined audit CSV
    pipeline/data/raw/worldbank/missing_report_*.csv    ← gap audit
    pipeline/data/logs/worldbank_log.json               ← run history

EVERY RECORD includes:
    source_url, source, last_updated, fetched_at, country_code, country_name,
    region_group, indicator_code, indicator_key, indicator_name, year, value,
    unit, frequency, data_quality, value_type, limitation_note

data_quality values:
    available       — real WB data, recently published
    old_data        — real WB data, but more than 2 years behind current year
    estimated       — forward/backward-filled from an adjacent year (historical only)
    missing         — no WB data and no fill possible

value_type values:
    official_actual   — value comes directly from the World Bank API
    missing_official  — World Bank returned null for this country/indicator/year

COMMON ERRORS:
    ConnectionError    → no internet; check connection and retry
    ReadTimeout        → WB API is slow; the script retries automatically (3×)
    "0 rows" warning   → one indicator failed; others continue normally
    2025/2026 = null   → expected; WB publishes with 1–2 year lag

After running this, run:
    python scripts/scrape_latest_estimates.py    # adds 2025/2026 IMF forecasts
    python scripts/validate_worldbank_data.py    # verifies everything is correct
==============================================================================
"""

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT  = Path(__file__).resolve().parent.parent
PIPELINE_DIR  = PROJECT_ROOT / "pipeline"
PIPELINE_SCRIPT = PIPELINE_DIR / "fetch_worldbank.py"


def main() -> int:
    if not PIPELINE_SCRIPT.exists():
        print(f"ERROR: pipeline script not found at {PIPELINE_SCRIPT}")
        print("  Expected location: pipeline/fetch_worldbank.py")
        return 1

    # Pass all args through to the pipeline script
    extra_args = sys.argv[1:]

    print(f"  → Running pipeline/fetch_worldbank.py from project root …")
    print(f"  → Output: pipeline/data/processed/worldbank_indicators.json")
    print()

    result = subprocess.run(
        [sys.executable, str(PIPELINE_SCRIPT)] + extra_args,
        cwd=str(PIPELINE_DIR),   # run from pipeline/ so relative paths work
    )
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
