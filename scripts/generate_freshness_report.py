#!/usr/bin/env python3
"""
scripts/generate_freshness_report.py
────────────────────────────────────────────────────────────────────────────
Generates a per-country, per-sector freshness report from combined_indicators.json.

For each (country, sector):
  - latest_year:     most recent year with actual data
  - latest_quarter:  most recent quarter with actual data (if quarterly)
  - latest_month:    most recent month (if monthly)
  - source:          which source provided the freshest data
  - coverage_score:  0-100 (% of expected indicators present with actual data)
  - missing_indicators: list of expected indicators with no data
  - value_type_summary: breakdown by value_type

Also produces an overall freshness dashboard metric.

OUTPUT
  pipeline/data/processed/freshness_report.json
"""

import json
import sys
from pathlib import Path
from datetime import datetime, date
from collections import defaultdict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROC_DIR     = PROJECT_ROOT / "pipeline" / "data" / "processed"

COUNTRY_NAMES = {
    "THA":"Thailand","VNM":"Vietnam","MMR":"Myanmar","KHM":"Cambodia","LAO":"Laos",
    "MYS":"Malaysia","SGP":"Singapore","IDN":"Indonesia","PHL":"Philippines",
    "BRN":"Brunei","TLS":"Timor-Leste",
    "CHN":"China","USA":"United States","JPN":"Japan","IND":"India",
    "KOR":"South Korea","AUS":"Australia",
}

# Expected indicators per sector (minimum set for coverage calculation)
EXPECTED_BY_SECTOR = {
    "macro_economy":       ["GDP_GROWTH","GDP_NOMINAL_USD","CURRENT_ACCOUNT_GDP"],
    "prices_inflation":    ["CPI_INFLATION"],
    "labor":               ["UNEMPLOYMENT_RATE","LABOR_FORCE_PARTICIPATION"],
    "trade":               ["EXPORTS_USD","IMPORTS_USD","TRADE_BALANCE_USD"],
    "investment":          ["FDI_PCT_GDP","FDI_INFLOWS_USD"],
    "finance_monetary":    ["EXCHANGE_RATE_USD","FOREIGN_RESERVES"],
    "fiscal":              ["FISCAL_BALANCE_GDP","PUBLIC_DEBT_GDP","GOVT_REVENUE_GDP"],
    "tourism":             ["TOURIST_ARRIVALS","TOURISM_RECEIPTS_USD"],
    "industry_production": ["MANUFACTURING_PCT_GDP"],
    "agriculture":         ["AGRICULTURE_PCT_GDP"],
    "energy":              ["RENEWABLE_ENERGY_SHARE","ELECTRICITY_ACCESS","CO2_PER_CAPITA"],
    "technology_digital":  ["INTERNET_PENETRATION","MOBILE_SUBSCRIPTIONS"],
    "infrastructure":      ["LOGISTICS_PERFORMANCE"],
    "environment":         ["FOREST_AREA_PCT","CO2_TOTAL"],
    "politics_policy":     ["GOVERNANCE_EFFECTIVENESS","RULE_OF_LAW"],
    "security_conflict":   ["POLITICAL_STABILITY","CORRUPTION_PERCEPTION"],
    "social_indicators":   ["POPULATION","LIFE_EXPECTANCY","POVERTY_RATE_USD365"],
}

ACTUAL_VALUE_TYPES = {"official_actual","official_preliminary","official_partial_2026"}


def main():
    print(f"\n{'═'*60}")
    print(f"  Freshness Report Generator")
    print(f"  Date: {date.today().isoformat()}")
    print(f"{'═'*60}\n")

    combined_file = PROC_DIR / "combined_indicators.json"
    if not combined_file.exists():
        print("  ✗ combined_indicators.json not found")
        return 1

    data  = json.loads(combined_file.read_text())
    rows  = data.get("records", [])
    print(f"  Loaded {len(rows)} rows\n", flush=True)

    # Index: {(country, sector, indicator): [row, ...]}
    index = defaultdict(list)
    for r in rows:
        key = (r.get("country_code",""), r.get("sector",""), r.get("indicator_code",""))
        index[key].append(r)

    # Per-country-sector report
    country_sector_report = {}

    for iso3 in COUNTRY_NAMES:
        country_report = {}
        for sector, expected_inds in EXPECTED_BY_SECTOR.items():
            actual_rows = []
            for ind in expected_inds:
                key = (iso3, sector, ind)
                rows_for_ind = index.get(key, [])
                actual_rows.extend([r for r in rows_for_ind
                                     if r.get("value_type") in ACTUAL_VALUE_TYPES
                                     and r.get("value") is not None])

            if not actual_rows:
                country_report[sector] = {
                    "latest_year":    None,
                    "latest_quarter": None,
                    "latest_month":   None,
                    "source":         None,
                    "coverage_score": 0,
                    "missing_indicators": expected_inds,
                    "value_type_summary": {},
                    "status": "missing",
                }
                continue

            # Find freshest row
            actual_rows.sort(key=lambda r: (
                r.get("year",0),
                r.get("quarter") or 0,
                r.get("month") or 0,
            ), reverse=True)
            freshest = actual_rows[0]

            # Coverage score
            inds_with_data = set()
            for ind in expected_inds:
                key = (iso3, sector, ind)
                if any(r.get("value_type") in ACTUAL_VALUE_TYPES and r.get("value") is not None
                       for r in index.get(key, [])):
                    inds_with_data.add(ind)
            coverage = round(len(inds_with_data) / len(expected_inds) * 100, 1) if expected_inds else 0
            missing  = [ind for ind in expected_inds if ind not in inds_with_data]

            # Value type summary for this country/sector
            from collections import Counter
            vt_counts = Counter(
                r.get("value_type") for rows_for_key in
                [index.get((iso3, sector, ind), []) for ind in expected_inds]
                for r in rows_for_key
            )

            latest_year    = freshest.get("year")
            latest_quarter = freshest.get("quarter")
            latest_month   = freshest.get("month")
            source_name    = freshest.get("source","")

            # Determine status
            if latest_year == date.today().year:
                status = "current"
            elif latest_year == date.today().year - 1:
                status = "recent"
            elif latest_year and latest_year >= date.today().year - 2:
                status = "lagging"
            else:
                status = "stale"

            country_report[sector] = {
                "latest_year":    latest_year,
                "latest_quarter": latest_quarter,
                "latest_month":   latest_month,
                "source":         source_name,
                "coverage_score": coverage,
                "missing_indicators": missing,
                "value_type_summary": dict(vt_counts),
                "status": status,
            }

        country_sector_report[iso3] = {
            "country_name":    COUNTRY_NAMES[iso3],
            "overall_coverage": round(
                sum(country_report[s].get("coverage_score",0) for s in country_report)
                / max(len(country_report), 1), 1
            ),
            "sectors_with_data": sum(1 for s in country_report
                                     if country_report[s].get("coverage_score",0) > 0),
            "total_sectors": len(EXPECTED_BY_SECTOR),
            "sectors": country_report,
        }

    # Overall dashboard stats
    overall_coverage = round(
        sum(cr.get("overall_coverage",0) for cr in country_sector_report.values())
        / max(len(country_sector_report), 1), 1
    )

    # Warning note for dashboard
    warning_note = (
        "Latest 2025/2026 data availability differs by country and sector. "
        "Official actuals, forecasts, preliminary values, and real-time signals "
        "are labeled separately. Check the source badge before comparing values "
        "across countries or time periods."
    )

    report = {
        "generated_at":      datetime.utcnow().isoformat() + "Z",
        "total_rows_input":  len(rows),
        "countries_covered": len(country_sector_report),
        "sectors_covered":   len(EXPECTED_BY_SECTOR),
        "overall_coverage_pct": overall_coverage,
        "warning_note":      warning_note,
        "countries":         country_sector_report,
    }

    out_file = PROC_DIR / "freshness_report.json"
    out_file.write_text(json.dumps(report, indent=2))

    print(f"  Overall data coverage : {overall_coverage}%")
    print(f"\n  Per-country summary:")
    for iso3, cr in sorted(country_sector_report.items()):
        cov = cr.get("overall_coverage",0)
        sct = cr.get("sectors_with_data",0)
        bar = "█" * int(cov // 10) + "░" * (10 - int(cov // 10))
        print(f"    {iso3:6s} [{bar}] {cov:5.1f}% ({sct}/{cr['total_sectors']} sectors)")

    print(f"\n  📄 {out_file.relative_to(PROJECT_ROOT)}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
