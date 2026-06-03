#!/usr/bin/env python3
"""
scripts/merge_all_sources.py
────────────────────────────────────────────────────────────────────────────
Merges all normalized indicator rows from all sources into a single
combined_indicators.json with conflict resolution and source audit trail.

MERGE RULES (in order — earlier rule wins if match found):
  1. Official national actual (NSO, ministry, central bank)
  2. Official regional actual (ASEANstats, Comtrade)
  3. World Bank official actual
  4. IMF official actual (historical)
  5. Forecast estimate (IMF WEO, ADB ADO, WB GEP)  — only if actual missing
  6. Never replace official_actual with forecast_estimate

ANTI-RULES:
  - 2026 partial year: keep value but add "partial_2026" data_quality flag
  - Never fill 2025/2026 with forward-fill from 2024
  - Keep all source candidates in source_audit_report.json

OUTPUT
  pipeline/data/processed/combined_indicators.json
  pipeline/data/processed/source_audit_report.json
"""

import json
import sys
from pathlib import Path
from datetime import datetime, date
from collections import defaultdict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROC_DIR     = PROJECT_ROOT / "pipeline" / "data" / "processed"

# Merge priority (lower number = higher priority = preferred source)
VALUE_TYPE_PRIORITY = {
    "official_actual":        1,
    "official_preliminary":   2,
    "official_partial_2026":  3,
    "forecast_estimate":      4,
    "missing_official":       10,  # Never preferred — only if nothing better
    "official_policy":        99,  # No numeric value
    "realtime_signal":        99,
    "sample":                 999,
}

SOURCE_TYPE_PRIORITY = {
    "national_statistics": 1,
    "central_bank":        2,
    "ministry_customs":    3,
    "regional_official":   4,
    "multilateral":        5,
    "forecast_multilateral": 6,
    "computed":            5,
    "official_policy":     7,
    "realtime_signal":     8,
}

CURR_YEAR = date.today().year


def _merge_priority(row: dict) -> tuple:
    """Return (value_type_priority, source_type_priority) for sorting."""
    vt = row.get("value_type", "missing_official")
    st = row.get("source_type", "multilateral")
    # Rows with null value are always lower priority than rows with a value
    null_penalty = 0 if row.get("value") is not None else 5
    return (
        VALUE_TYPE_PRIORITY.get(vt, 10) + null_penalty,
        SOURCE_TYPE_PRIORITY.get(st, 5),
    )


def _row_key(row: dict) -> str:
    """Unique key for deduplication: country + indicator + period."""
    return f"{row.get('country_code','?')}|{row.get('indicator_code','?')}|{row.get('period','?')}"


def _flag_partial_2026(rows: list[dict]) -> list[dict]:
    """Flag 2026 rows as official_partial_2026 if we're still in 2026."""
    if CURR_YEAR != 2026:
        return rows
    out = []
    for r in rows:
        r = dict(r)
        if r.get("year") == 2026 and r.get("value_type") == "official_actual":
            r["value_type"] = "official_partial_2026"
            r["limitation_note"] = (
                "Partial 2026 data — year not yet complete. " +
                (r.get("limitation_note") or "")
            ).strip()
        out.append(r)
    return out


def main():
    print(f"\n{'═'*60}")
    print(f"  Merge All Sources → combined_indicators.json")
    print(f"  Date: {date.today().isoformat()}")
    print(f"{'═'*60}\n")

    # Load normalized file
    norm_file = PROC_DIR / "all_sources_normalized.json"
    if not norm_file.exists():
        print("  ✗ all_sources_normalized.json not found — run normalize_indicators.py first")
        return 1

    data = json.loads(norm_file.read_text())
    all_rows = data.get("records", [])
    print(f"  Loaded {len(all_rows)} normalized rows\n", flush=True)

    # Group by unique key
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in all_rows:
        key = _row_key(row)
        groups[key].append(row)

    print(f"  Unique (country, indicator, period) keys: {len(groups)}", flush=True)

    merged_rows    = []
    audit_entries  = []
    conflict_count = 0
    forecast_used  = 0

    for key, candidates in groups.items():
        # Sort by merge priority
        sorted_candidates = sorted(candidates, key=_merge_priority)
        winner = sorted_candidates[0]

        # Safety check: never let forecast replace official actual
        best_actual = next((c for c in sorted_candidates if c.get("value_type") == "official_actual" and c.get("value") is not None), None)
        best_forecast = next((c for c in sorted_candidates if c.get("value_type") == "forecast_estimate" and c.get("value") is not None), None)

        if best_actual:
            winner = best_actual
        elif winner.get("value_type") == "forecast_estimate":
            forecast_used += 1

        if len(sorted_candidates) > 1:
            conflict_count += 1
            # Save audit trail
            audit_entries.append({
                "key":      key,
                "winner":   winner.get("source"),
                "winner_value_type": winner.get("value_type"),
                "winner_value": winner.get("value"),
                "candidates": [
                    {
                        "source":     c.get("source"),
                        "value_type": c.get("value_type"),
                        "value":      c.get("value"),
                        "priority":   list(_merge_priority(c)),
                    }
                    for c in sorted_candidates
                ],
            })

        # Clean row: remove internal fields
        final = {k: v for k, v in winner.items() if not k.startswith("_")}
        merged_rows.append(final)

    # Flag partial 2026
    merged_rows = _flag_partial_2026(merged_rows)

    # Sort output: by country, sector, indicator, year
    merged_rows.sort(key=lambda r: (
        r.get("country_code") or "",
        r.get("sector") or "",
        r.get("indicator_code") or "",
        r.get("year") or 0,
        r.get("period") or "",
    ))

    # Build stats
    from collections import Counter
    vt_counts   = Counter(r.get("value_type","?")   for r in merged_rows)
    sect_counts = Counter(r.get("sector","?")         for r in merged_rows)
    ctry_counts = Counter(r.get("country_code","?")   for r in merged_rows)
    non_null    = sum(1 for r in merged_rows if r.get("value") is not None)

    print(f"\n  ── Merge Results ──────────────────────────────")
    print(f"  Total merged rows     : {len(merged_rows)}")
    print(f"  Non-null values       : {non_null}")
    print(f"  Conflicts resolved    : {conflict_count}")
    print(f"  Forecast rows used    : {forecast_used}")
    print(f"\n  Value types:")
    for vt, cnt in sorted(vt_counts.items(), key=lambda x: -x[1]):
        print(f"    {vt:30s} {cnt:6d}")
    print(f"\n  Sectors:")
    for s, cnt in sorted(sect_counts.items(), key=lambda x: -x[1]):
        print(f"    {s:30s} {cnt:6d}")

    # Save combined_indicators.json
    combined = {
        "generated_at":      datetime.utcnow().isoformat() + "Z",
        "total_rows":        len(merged_rows),
        "non_null":          non_null,
        "conflicts_resolved": conflict_count,
        "forecasts_used":    forecast_used,
        "value_type_counts": dict(vt_counts),
        "sector_counts":     dict(sect_counts),
        "note": (
            "2025/2026 data availability differs by country and sector. "
            "Official actuals, forecasts, preliminary values, and real-time signals "
            "are labeled separately. Never compare across value_type categories without "
            "checking the source badge."
        ),
        "records": merged_rows,
    }

    out_file = PROC_DIR / "combined_indicators.json"
    out_file.write_text(json.dumps(combined, indent=2))
    print(f"\n  📄 combined_indicators.json written")

    # Save source audit report
    audit = {
        "generated_at":  datetime.utcnow().isoformat() + "Z",
        "total_conflicts": len(audit_entries),
        "entries": audit_entries[:5000],  # Cap at 5k entries for file size
    }
    audit_file = PROC_DIR / "source_audit_report.json"
    audit_file.write_text(json.dumps(audit, indent=2))
    print(f"  📄 source_audit_report.json written ({len(audit_entries)} conflicts)\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
