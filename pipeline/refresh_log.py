"""
pipeline/refresh_log.py
────────────────────────────────────────────────────────────────────────────
Central log manager for the SEA Dashboard data pipeline.

Tracks the last successful and last attempted refresh for each data source,
writes a single JSON file that the frontend reads as a "freshness badge",
and exposes helpers used by run_pipeline.py and schedule_local.py.

OUTPUT FILE:
  pipeline/data/processed/refresh_log.json

PUBLIC API
──────────
  record_run(source, status, records=None, error=None)
      Call after each fetch or process step completes.
      source  : "worldbank" | "gdelt" | "comtrade"
              | "process_indicators" | "process_news" | "alerts"
      status  : "success" | "failed" | "rate_limited" | "cached"
      records : int, optional  (number of records/articles/alerts)
      error   : str, optional  (short error description on failure)

  read_log() → dict
      Return the current refresh_log.json as a dict.
      Returns an empty skeleton if the file doesn't exist yet.

  bootstrap_from_processed_files()
      Seed the log from timestamps already present in the processed JSON
      files. Call once if refresh_log.json doesn't exist yet.

  freshness_summary() → dict[str, str]
      Returns { source: "fresh" | "aging" | "stale" | "unknown" }
      using the thresholds defined in FRESHNESS_HOURS below.
────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Paths ──────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
PROC_DIR   = SCRIPT_DIR / "data" / "processed"
LOG_FILE   = PROC_DIR / "refresh_log.json"

# ── Source → processed file that contains its generated_at timestamp ──────
SOURCE_FILES = {
    "worldbank": PROC_DIR / "worldbank_indicators.json",
    "gdelt":     PROC_DIR / "news_signals.json",
    "comtrade":  PROC_DIR / "trade_flows.json",
}

PROCESS_FILES = {
    "process_indicators": PROC_DIR / "indicators_dashboard.json",
    "process_news":       PROC_DIR / "news_dashboard.json",
    "alerts":             PROC_DIR / "alerts.json",
}

# ── Freshness thresholds (hours) ──────────────────────────────────────────
# "fresh"  → age is within normal refresh window
# "aging"  → past the window, but only by up to 2× (mild warning)
# "stale"  → more than 2× overdue (red flag)
FRESHNESS_HOURS: dict[str, dict[str, float]] = {
    "gdelt":     {"fresh": 6,   "aging": 12},   # expect refresh every 6 h
    "worldbank": {"fresh": 168, "aging": 336},   # expect refresh weekly (168 h)
    "comtrade":  {"fresh": 168, "aging": 336},   # expect refresh weekly
}

# ── Source display labels ─────────────────────────────────────────────────
SOURCE_LABELS: dict[str, str] = {
    "gdelt":     "News Feed",
    "worldbank": "Official Data",
    "comtrade":  "Trade Data",
}


# ═══════════════════════════════════════════════════════════════════════════
# INTERNAL HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _empty_log() -> dict:
    """Return a clean empty log skeleton."""
    return {
        "schema_version": 1,
        "updated_at": _now_iso(),
        "sources": {
            src: {
                "label":                SOURCE_LABELS.get(src, src),
                "last_success_at":      None,
                "last_attempt_at":      None,
                "status":               "never_run",
                "record_count":         None,
                "error":                None,
                "refresh_interval_h":   FRESHNESS_HOURS.get(src, {}).get("fresh", 168),
            }
            for src in ("gdelt", "worldbank", "comtrade")
        },
        "pipeline": {
            "last_full_run_at":    None,
            "last_process_run_at": None,
            "last_news_run_at":    None,
            "last_data_run_at":    None,
            "alerts_generated":    None,
            "alerts_critical":     None,
        },
    }


def _load() -> dict:
    """Load the log file, or return an empty skeleton if it doesn't exist."""
    if LOG_FILE.exists():
        try:
            with open(LOG_FILE, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return _empty_log()


def _save(log: dict) -> None:
    """Write the log to disk atomically (write to temp, then rename)."""
    PROC_DIR.mkdir(parents=True, exist_ok=True)
    log["updated_at"] = _now_iso()
    tmp = LOG_FILE.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)
    tmp.replace(LOG_FILE)


def _age_hours(iso_ts: str | None) -> float | None:
    """Return hours since an ISO timestamp, or None if ts is missing."""
    if not iso_ts:
        return None
    try:
        ts = datetime.fromisoformat(iso_ts)
        now = datetime.now()
        return (now - ts).total_seconds() / 3600
    except (ValueError, TypeError):
        return None


# ═══════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════

def record_run(
    source: str,
    status: str,
    records: int | None = None,
    error: str | None = None,
    pipeline_mode: str | None = None,
) -> None:
    """
    Record the result of one pipeline run for a given source.

    Parameters
    ──────────
    source        : "worldbank" | "gdelt" | "comtrade"
                  | "process_indicators" | "process_news" | "alerts"
    status        : "success" | "failed" | "rate_limited" | "cached"
    records       : optional count of records / articles / alerts written
    error         : optional short error string when status != "success"
    pipeline_mode : optional mode string from run_pipeline.py (e.g. "news")

    Example
    ───────
    record_run("gdelt",     "success",      records=72)
    record_run("gdelt",     "rate_limited", error="HTTP 429")
    record_run("worldbank", "success",      records=1360)
    """
    log = _load()
    now = _now_iso()

    # ── Fetch-source entry (gdelt / worldbank / comtrade) ──────────────────
    if source in log["sources"]:
        entry = log["sources"][source]
        entry["last_attempt_at"] = now
        entry["status"]          = status
        if error:
            entry["error"] = error[:200]   # cap length
        else:
            entry["error"] = None
        if records is not None:
            entry["record_count"] = records
        if status in ("success", "cached"):
            entry["last_success_at"] = now

    # ── Pipeline-level metadata ────────────────────────────────────────────
    pl = log["pipeline"]
    if source == "alerts" and records is not None:
        pl["last_process_run_at"] = now
    if source in ("process_indicators", "process_news"):
        pl["last_process_run_at"] = now

    # Track mode-specific timestamps
    if pipeline_mode == "news":
        pl["last_news_run_at"] = now
    elif pipeline_mode in ("data", "worldbank", "comtrade"):
        pl["last_data_run_at"] = now
    elif pipeline_mode in ("all",):
        pl["last_full_run_at"] = now
        pl["last_news_run_at"] = now
        pl["last_data_run_at"] = now

    _save(log)


def record_alerts(n_total: int, n_critical: int) -> None:
    """Convenience wrapper to record alert generation results."""
    log = _load()
    log["pipeline"]["alerts_generated"] = n_total
    log["pipeline"]["alerts_critical"]  = n_critical
    log["pipeline"]["last_process_run_at"] = _now_iso()
    _save(log)


def record_pipeline_mode(mode: str) -> None:
    """Record which pipeline mode just completed."""
    log = _load()
    now = _now_iso()
    pl = log["pipeline"]
    if mode == "all":
        pl["last_full_run_at"] = now
        pl["last_news_run_at"] = now
        pl["last_data_run_at"] = now
    elif mode == "news":
        pl["last_news_run_at"] = now
    elif mode in ("data", "worldbank", "comtrade"):
        pl["last_data_run_at"] = now
    pl["last_process_run_at"] = now
    _save(log)


def read_log() -> dict:
    """
    Return the current refresh_log.json as a plain dict.
    Never raises — returns the empty skeleton if the file is missing.
    """
    return _load()


def freshness_summary() -> dict[str, str]:
    """
    Returns the freshness status for each data source:
      { "gdelt": "fresh" | "aging" | "stale" | "unknown" }

    Uses FRESHNESS_HOURS thresholds defined at the top of this module.
    """
    log    = _load()
    result = {}

    for src, thresholds in FRESHNESS_HOURS.items():
        ts    = log.get("sources", {}).get(src, {}).get("last_success_at")
        age_h = _age_hours(ts)

        if age_h is None:
            result[src] = "unknown"
        elif age_h <= thresholds["fresh"]:
            result[src] = "fresh"
        elif age_h <= thresholds["aging"]:
            result[src] = "aging"
        else:
            result[src] = "stale"

    return result


def bootstrap_from_processed_files() -> None:
    """
    Seed the log from timestamps already present in existing processed files.

    Reads the 'generated_at' field from each source's JSON file and uses it
    as 'last_success_at'. Safe to call multiple times — only overwrites if
    the current log has no timestamp for that source.
    """
    log     = _load()
    changed = False

    for src, src_file in SOURCE_FILES.items():
        if not src_file.exists():
            continue
        try:
            with open(src_file, encoding="utf-8") as f:
                data = json.load(f)
            gen_at  = data.get("meta", {}).get("generated_at")
            records = _guess_record_count(data)
            status  = data.get("meta", {}).get("data_status", "unknown")

            entry = log["sources"].get(src, {})

            # Only backfill if we don't already have a value
            if not entry.get("last_success_at") and gen_at:
                entry["last_success_at"] = gen_at
                entry["last_attempt_at"] = gen_at
                entry["status"]          = "success" if status == "live" else status
                if records:
                    entry["record_count"] = records
                log["sources"][src] = entry
                changed = True

        except (json.JSONDecodeError, OSError, KeyError):
            pass  # silently skip broken files

    if changed:
        _save(log)
        print(f"  ✓  refresh_log.json bootstrapped from existing processed files")


def _guess_record_count(data: dict) -> int | None:
    """Try to extract a record count from a processed JSON file's meta."""
    meta = data.get("meta", {})
    for key in ("unique_articles", "total_records", "total"):
        if isinstance(meta.get(key), int):
            return meta[key]
    # Fallback: count top-level arrays
    for key in ("records", "articles", "flows"):
        if isinstance(data.get(key), list):
            return len(data[key])
    return None


# ═══════════════════════════════════════════════════════════════════════════
# STANDALONE — pretty-print current status
# ═══════════════════════════════════════════════════════════════════════════

def _fmt_age(iso_ts: str | None) -> str:
    """Return a human-readable age string like '2h ago' or '3d ago'."""
    age_h = _age_hours(iso_ts)
    if age_h is None:
        return "never"
    if age_h < 1:
        return f"{int(age_h * 60)}m ago"
    if age_h < 24:
        return f"{int(age_h)}h ago"
    return f"{int(age_h / 24)}d ago"


if __name__ == "__main__":
    import sys
    if "--bootstrap" in sys.argv:
        bootstrap_from_processed_files()

    log = read_log()
    fr  = freshness_summary()

    ICONS = {"fresh": "🟢", "aging": "🟡", "stale": "🔴", "unknown": "⚪"}
    print()
    print("  SEA Dashboard — Data Freshness")
    print("  " + "─" * 40)
    for src, entry in log["sources"].items():
        icon  = ICONS[fr.get(src, "unknown")]
        label = entry.get("label", src).ljust(18)
        ts    = entry.get("last_success_at")
        age   = _fmt_age(ts)
        n     = entry.get("record_count")
        cnt   = f"  ({n} records)" if n else ""
        print(f"  {icon} {label}  {age}{cnt}")
    print()
    pl = log.get("pipeline", {})
    if pl.get("last_full_run_at"):
        print(f"  Last full run : {_fmt_age(pl['last_full_run_at'])}")
    if pl.get("alerts_generated") is not None:
        crit = pl.get("alerts_critical", 0)
        print(f"  Alerts        : {pl['alerts_generated']} total  ({crit} critical)")
    print()
