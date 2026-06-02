#!/usr/bin/env python3
"""
==============================================================================
  run_pipeline.py — SEA Change Intelligence Dashboard
==============================================================================

Master orchestrator that runs the full data pipeline in the correct order.
Supports frequency-based modes so each data source can be refreshed on its
own schedule without running the entire pipeline every time.

PIPELINE STEPS
──────────────
  [1/7] fetch_worldbank.py           World Bank annual indicators (17 countries)
  [2/7] fetch_gdelt_news.py          GDELT news signals (17 countries, 12 categories)
  [3/7] fetch_comtrade.py            UN Comtrade trade flows (10 SEA × 7 partners)
  [4/7] process_indicators.py        Merge & reshape indicators for dashboard
  [5/7] process_news.py              Reshape news feed, compute risk scores
  [6/7] generate_alerts.py           Run pattern engine, produce alerts.json
  [7/7] generate_pattern_alerts.py   8-type alerts with confidence scoring, pattern_alerts.json

REFRESH MODES  (use --mode to run only what changed)
──────────────────────────────────────────────────────
  all        Full pipeline — fetches + processing  (default)
  news       GDELT only → process_news → alerts    (run every 6 hours)
  data       WB + Comtrade → process_indicators → alerts  (run weekly)
  worldbank  World Bank only → process_indicators → alerts
  comtrade   Comtrade only → process_indicators → alerts
  process    Reprocess only — no API calls  (instant, uses cached data)

USAGE
─────
  cd pipeline

  python run_pipeline.py                   # full refresh
  python run_pipeline.py --mode news       # GDELT + process + alerts
  python run_pipeline.py --mode data       # WB + Comtrade + process + alerts
  python run_pipeline.py --mode process    # reprocess only (no API calls)
  python run_pipeline.py --mode worldbank  # WB only
  python run_pipeline.py --step 4         # run only step 4
  python run_pipeline.py --dry-run        # print plan without running

RESILIENCE
──────────
  If any step fails, the pipeline continues. Previously generated files
  are never deleted. Exit code 0 = all OK, 1 = at least one step failed.

==============================================================================
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from utils.logger import (
    pipeline_banner,
    step_banner, step_elapsed,
    ok, fail, warn, info,
    pipeline_summary,
)

# Refresh log — safe to import; gracefully handles missing file
try:
    from refresh_log import record_run, record_pipeline_mode, record_alerts
    _LOG_AVAILABLE = True
except ImportError:
    _LOG_AVAILABLE = False
    def record_run(*a, **kw):      pass   # no-op stubs
    def record_pipeline_mode(*a):  pass
    def record_alerts(*a):         pass


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 1 — PIPELINE DEFINITION
# ══════════════════════════════════════════════════════════════════════════════

STEPS: list[dict] = [
    {
        "n":         1,
        "name":      "fetch_worldbank.py",
        "label":     "World Bank indicators",
        "is_fetch":  True,
        "log_source": "worldbank",
        "output":    "data/processed/worldbank_indicators.json",
        "depends_on": [],
    },
    {
        "n":         2,
        "name":      "fetch_gdelt_news.py",
        "label":     "GDELT news signals",
        "is_fetch":  True,
        "log_source": "gdelt",
        "output":    "data/processed/news_signals.json",
        "depends_on": [],
    },
    {
        "n":         3,
        "name":      "fetch_comtrade.py",
        "label":     "UN Comtrade trade flows",
        "is_fetch":  True,
        "log_source": "comtrade",
        "output":    "data/processed/trade_flows.json",
        "depends_on": [],
    },
    {
        "n":         4,
        "name":      "process_indicators.py",
        "label":     "Indicator processing",
        "is_fetch":  False,
        "log_source": "process_indicators",
        "output":    "data/processed/indicators_dashboard.json",
        "depends_on": ["fetch_worldbank.py"],
    },
    {
        "n":         5,
        "name":      "process_news.py",
        "label":     "News signal processing",
        "is_fetch":  False,
        "log_source": "process_news",
        "output":    "data/processed/news_dashboard.json",
        "depends_on": ["fetch_gdelt_news.py"],
    },
    {
        "n":         6,
        "name":      "generate_alerts.py",
        "label":     "Alert generation (indicators + news)",
        "is_fetch":  False,
        "log_source": "alerts",
        "output":    "data/processed/alerts.json",
        "depends_on": ["process_indicators.py", "process_news.py"],
    },
    {
        "n":         7,
        "name":      "generate_pattern_alerts.py",
        "label":     "Pattern alerts with confidence scoring",
        "is_fetch":  False,
        "log_source": "pattern_alerts",
        "output":    "data/processed/pattern_alerts.json",
        "depends_on": ["fetch_worldbank.py", "fetch_gdelt_news.py", "fetch_comtrade.py"],
    },
]

TOTAL = len(STEPS)

# ── Mode → step numbers ──────────────────────────────────────────────────────
# Each mode specifies which steps to run for frequency-based scheduling.
MODE_STEPS: dict[str, list[int]] = {
    "all":       [1, 2, 3, 4, 5, 6, 7],   # full pipeline
    "news":      [2, 5, 6, 7],             # GDELT every 6 h
    "data":      [1, 3, 4, 6, 7],          # WB + Comtrade weekly
    "worldbank": [1, 4, 6, 7],             # World Bank only
    "comtrade":  [3, 4, 6, 7],             # Comtrade only
    "process":   [4, 5, 6, 7],             # reprocess without API calls
}

MODE_DESCRIPTIONS: dict[str, str] = {
    "all":       "full pipeline (fetch + process + pattern alerts)",
    "news":      "GDELT news → process → alerts  (recommended: every 6 h)",
    "data":      "WB + Comtrade → process → alerts  (recommended: weekly)",
    "worldbank": "World Bank only → process → pattern alerts",
    "comtrade":  "Comtrade only → process → pattern alerts",
    "process":   "reprocess only — no API calls",
}


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 2 — STEP RUNNER
# ══════════════════════════════════════════════════════════════════════════════

def run_step(step: dict, dry_run: bool = False) -> dict:
    """
    Execute one pipeline step as a subprocess.
    Returns { name, status ("ok"|"skip"|"fail"), note, seconds }.
    Never raises — exceptions are caught and returned as status="fail".
    """
    name    = step["name"]
    script  = SCRIPT_DIR / name
    out_rel = step["output"]

    t0 = step_banner(step["n"], TOTAL, name)

    if dry_run:
        info(f"Would run : python {name}")
        info(f"Output    : {out_rel}")
        step_elapsed(t0)
        return {"name": name, "status": "skip", "note": "dry-run", "seconds": 0.0}

    if not script.exists():
        fail(f"Script not found: {script}")
        step_elapsed(t0)
        return {"name": name, "status": "fail", "note": "script missing", "seconds": 0.0}

    info(f"Running : python {name}")
    info(f"Output  : {out_rel}")
    print()

    try:
        result = subprocess.run(
            [sys.executable, str(script)],
            cwd=str(SCRIPT_DIR),
            capture_output=False,   # stream output directly to terminal
            text=True,
            timeout=600,            # 10-minute timeout per step
        )
        elapsed = round(time.time() - t0, 1)
        step_elapsed(t0)

        if result.returncode == 0:
            out_path = SCRIPT_DIR / out_rel
            if out_path.exists():
                size_kb = out_path.stat().st_size // 1024
                ok(f"Output ready: {out_rel}  ({size_kb} KB)")
                return {"name": name, "status": "ok",   "note": f"{size_kb} KB",      "seconds": elapsed}
            else:
                warn(f"Step exited 0 but output not found: {out_rel}")
                return {"name": name, "status": "ok",   "note": "no output file",     "seconds": elapsed}
        else:
            fail(f"{name} exited with code {result.returncode}")
            return    {"name": name, "status": "fail", "note": f"exit {result.returncode}", "seconds": elapsed}

    except subprocess.TimeoutExpired:
        fail(f"{name} timed out after 10 minutes")
        return {"name": name, "status": "fail", "note": "timeout", "seconds": 600.0}

    except Exception as exc:
        fail(f"{name} raised an exception: {exc}")
        return {"name": name, "status": "fail", "note": str(exc)[:50], "seconds": round(time.time() - t0, 1)}


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 3 — REFRESH LOG HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _count_from_output(out_rel: str) -> int | None:
    """Read a processed JSON file and return its record count from meta."""
    try:
        out_path = SCRIPT_DIR / out_rel
        with open(out_path, encoding="utf-8") as f:
            data = json.load(f)
        meta = data.get("meta", {})
        for key in ("unique_articles", "total_records", "triggered_alerts", "total"):
            if isinstance(meta.get(key), int):
                return meta[key]
    except Exception:
        pass
    return None


def _update_refresh_log(step: dict, result: dict, mode: str) -> None:
    """
    Update refresh_log.json after a step completes.
    Called for every step, success or failure.
    """
    if not _LOG_AVAILABLE:
        return
    log_src = step.get("log_source", "")
    if not log_src:
        return

    if result["status"] == "ok":
        records = _count_from_output(step["output"])
        # For alerts, also record the critical count
        if log_src == "alerts":
            try:
                out_path = SCRIPT_DIR / step["output"]
                with open(out_path, encoding="utf-8") as f:
                    d = json.load(f)
                n_total    = d.get("meta", {}).get("triggered_alerts", 0)
                n_critical = d.get("meta", {}).get("critical", 0)
                record_alerts(n_total, n_critical)
            except Exception:
                pass
        if log_src in ("worldbank", "gdelt", "comtrade"):
            record_run(log_src, "success", records=records, pipeline_mode=mode)
    else:
        if log_src in ("worldbank", "gdelt", "comtrade"):
            record_run(log_src, "failed", error=result["note"], pipeline_mode=mode)


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 4 — MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the SEA Dashboard data pipeline.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="\n".join(
            f"  --mode {m:<12} {d}" for m, d in MODE_DESCRIPTIONS.items()
        ),
    )
    parser.add_argument(
        "--mode",
        choices=list(MODE_STEPS.keys()),
        default=None,
        metavar="MODE",
        help=(
            "Which sources to refresh: "
            + " | ".join(MODE_STEPS.keys())
            + "  (default: all)"
        ),
    )
    parser.add_argument(
        "--skip-fetch", action="store_true",
        help="Alias for --mode process. Skips API fetch scripts.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print the plan without running anything.",
    )
    parser.add_argument(
        "--step", type=int, default=None, metavar="N",
        help="Run only step N (1–6). Example: --step 4",
    )
    args = parser.parse_args()

    # ── Resolve which steps to run ───────────────────────────────────────────
    if args.step is not None:
        steps_to_run = [s for s in STEPS if s["n"] == args.step]
        if not steps_to_run:
            print(f"  ✗  Unknown step {args.step}  (valid: 1–{TOTAL})")
            return 1
        effective_mode = "single"
        mode_label     = f"single step [{args.step}/{TOTAL}]"
    elif args.mode:
        step_nums    = MODE_STEPS[args.mode]
        steps_to_run = [s for s in STEPS if s["n"] in step_nums]
        effective_mode = args.mode
        mode_label     = f"--mode {args.mode}  ({MODE_DESCRIPTIONS[args.mode]})"
    elif args.skip_fetch:
        steps_to_run   = [s for s in STEPS if s["n"] in MODE_STEPS["process"]]
        effective_mode = "process"
        mode_label     = "--mode process  (fetch skipped)"
    else:
        steps_to_run   = STEPS.copy()
        effective_mode = "all"
        mode_label     = "all  (full pipeline)"

    # ── Banner ───────────────────────────────────────────────────────────────
    pipeline_banner("SEA Dashboard — Data Pipeline")
    print(f"  Mode          : {mode_label}")
    print(f"  Steps to run  : {len(steps_to_run)} of {TOTAL}")
    if args.dry_run:
        print(f"  DRY RUN       : plan only, nothing will execute")
    print()

    # ── Print execution plan ─────────────────────────────────────────────────
    info("Execution plan:")
    run_set = {s["n"] for s in steps_to_run}
    for step in STEPS:
        if step["n"] in run_set:
            print(f"    ▶  [{step['n']}/{TOTAL}] {step['name']:<28}  {step['label']}")
        else:
            print(f"    ○  [{step['n']}/{TOTAL}] {step['name']:<28}  (skipped)")
    print()

    # ── Run each step ────────────────────────────────────────────────────────
    results: list[dict] = []
    failed_names: set[str] = set()
    wall_start = time.time()

    for step in steps_to_run:
        # Warn if a dependency failed (but still attempt the step)
        for dep in step.get("depends_on", []):
            if dep in failed_names:
                warn(f"{step['name']} depends on {dep} (failed) — output may be stale")

        result = run_step(step, dry_run=args.dry_run)
        results.append(result)

        if result["status"] == "fail":
            failed_names.add(step["name"])

        # Update the refresh log after every fetch step
        if not args.dry_run:
            _update_refresh_log(step, result, effective_mode)

    # Record overall mode completion
    if not args.dry_run and _LOG_AVAILABLE:
        n_fail = sum(1 for r in results if r.get("status") == "fail")
        if n_fail == 0:
            record_pipeline_mode(effective_mode)

    # ── Summary ──────────────────────────────────────────────────────────────
    pipeline_summary(results)

    n_fail    = sum(1 for r in results if r.get("status") == "fail")
    wall_secs = time.time() - wall_start
    m, s      = divmod(int(wall_secs), 60)
    wall_str  = f"{m}m {s}s" if m else f"{s}s"
    print(f"  Wall clock: {wall_str}")
    print()

    if n_fail == 0:
        print("  Next steps:")
        print("    Hard-refresh the browser (Cmd+Shift+R) or restart the dev server:")
        print("      cd frontend && npm run dev")
        print()
        print("  Recommended schedule (cron examples):")
        print(f"    */6 * * * *   cd {SCRIPT_DIR} && python run_pipeline.py --mode news")
        print(f"    0 4 * * 1     cd {SCRIPT_DIR} && python run_pipeline.py --mode data")
        print()
    else:
        print(f"  ⚠  {n_fail} step(s) failed — see errors above.")
        print("     Existing output files are untouched.")
        print()
        print("  Common fixes:")
        print("    GDELT rate-limited?  → wait 15 min, then: python run_pipeline.py --mode news")
        print("    WB unreachable?      → check internet,  then: python run_pipeline.py --mode worldbank")
        print("    Comtrade key needed? → add COMTRADE_SUBSCRIPTION_KEY to .env")
        print()

    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
