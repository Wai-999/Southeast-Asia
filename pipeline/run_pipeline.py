#!/usr/bin/env python3
"""
==============================================================================
  run_pipeline.py — SEA Change Intelligence Dashboard
==============================================================================

Master orchestrator that runs the full data pipeline in the correct order.
This is the only script you need to run for a complete data refresh.

PIPELINE ORDER
──────────────
  [1/6] fetch_worldbank.py      World Bank annual indicators (17 countries)
  [2/6] fetch_gdelt_news.py     GDELT news signals (17 countries, 12 categories)
  [3/6] fetch_comtrade.py       UN Comtrade trade flows (10 SEA × 7 partners)
  [4/6] process_indicators.py   Merge & reshape indicators for dashboard
  [5/6] process_news.py         Reshape news feed, compute risk scores
  [6/6] generate_alerts.py      Run pattern engine, produce alerts.json

RESILIENCE DESIGN
──────────────────
  • If any step fails, the pipeline logs the error and continues to the next step.
  • Previously generated output files are never deleted on failure.
  • The final summary shows clearly which steps succeeded and which failed.
  • Exit code 0 means all steps succeeded.
  • Exit code 1 means at least one step failed (but others may be fine).

USAGE
─────
  cd pipeline

  # Full refresh (all 6 steps):
  python run_pipeline.py

  # Skip the slow fetch steps — reprocess only:
  python run_pipeline.py --skip-fetch

  # Run only one specific step (by number):
  python run_pipeline.py --step 4

  # Print the plan without running anything:
  python run_pipeline.py --dry-run

  # Combine flags:
  python run_pipeline.py --skip-fetch --dry-run

OUTPUT FILES  (all in pipeline/data/processed/)
────────────────────────────────────────────────
  worldbank_indicators.json     World Bank raw indicator records
  news_signals.json             GDELT article feed
  trade_flows.json              Bilateral trade data + dependency scores
  indicators_dashboard.json     Per-country indicator summaries   ← step 4
  news_dashboard.json           Processed news feed views         ← step 5
  alerts.json                   Pattern alert results             ← step 6

HOW LONG DOES IT TAKE?
───────────────────────
  Steps 1–3 (fetch) : 2–15 min each, depending on API speed and rate limits
  Step 4            : ~2 seconds
  Step 5            : ~1 second
  Step 6            : ~2 seconds
  Total (all steps) : roughly 10–30 minutes

  Use --skip-fetch to run just steps 4–6 in under 10 seconds when you
  already have fresh raw data from a previous run.

==============================================================================
"""

from __future__ import annotations

import argparse
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


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 1 — PIPELINE DEFINITION
# ══════════════════════════════════════════════════════════════════════════════

STEPS: list[dict] = [
    {
        "n":        1,
        "name":     "fetch_worldbank.py",
        "label":    "World Bank indicators",
        "is_fetch": True,
        "output":   "data/processed/worldbank_indicators.json",
        "depends_on": [],
    },
    {
        "n":        2,
        "name":     "fetch_gdelt_news.py",
        "label":    "GDELT news signals",
        "is_fetch": True,
        "output":   "data/processed/news_signals.json",
        "depends_on": [],
    },
    {
        "n":        3,
        "name":     "fetch_comtrade.py",
        "label":    "UN Comtrade trade flows",
        "is_fetch": True,
        "output":   "data/processed/trade_flows.json",
        "depends_on": [],
    },
    {
        "n":        4,
        "name":     "process_indicators.py",
        "label":    "Indicator processing",
        "is_fetch": False,
        "output":   "data/processed/indicators_dashboard.json",
        "depends_on": ["fetch_worldbank.py"],  # can warn if dependency failed
    },
    {
        "n":        5,
        "name":     "process_news.py",
        "label":    "News signal processing",
        "is_fetch": False,
        "output":   "data/processed/news_dashboard.json",
        "depends_on": ["fetch_gdelt_news.py"],
    },
    {
        "n":        6,
        "name":     "generate_alerts.py",
        "label":    "Alert generation",
        "is_fetch": False,
        "output":   "data/processed/alerts.json",
        "depends_on": ["process_indicators.py", "process_news.py"],
    },
]

TOTAL = len(STEPS)


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 2 — STEP RUNNER
# ══════════════════════════════════════════════════════════════════════════════

def run_step(step: dict, dry_run: bool = False) -> dict:
    """
    Execute one pipeline step as a subprocess.

    Returns a result dict:
      name    (str)   — script name
      status  (str)   — "ok", "skip", or "fail"
      note    (str)   — short description (e.g. "632 KB" or "exit code 1")
      seconds (float) — elapsed time

    IMPORTANT: this function never raises — it always returns a result dict.
    If the subprocess crashes, we catch the exception and return status="fail".
    """
    name    = step["name"]
    script  = SCRIPT_DIR / name
    out_rel = step["output"]

    t0 = step_banner(step["n"], TOTAL, name)

    # ── Dry run ──────────────────────────────────────────────────────────────
    if dry_run:
        info(f"Would run : python {name}")
        info(f"Output    : {out_rel}")
        step_elapsed(t0)
        return {"name": name, "status": "skip", "note": "dry-run", "seconds": 0.0}

    # ── Check script exists ──────────────────────────────────────────────────
    if not script.exists():
        fail(f"Script not found: {script}")
        fail(f"Expected at: {script}")
        return {
            "name": name, "status": "fail",
            "note": "script missing", "seconds": 0.0,
        }

    info(f"Running : python {name}")
    info(f"Output  : {out_rel}")
    print()

    # ── Run ──────────────────────────────────────────────────────────────────
    try:
        result = subprocess.run(
            [sys.executable, str(script)],
            cwd=str(SCRIPT_DIR),
            # capture_output=False → script output streams directly to terminal
            # This gives a much better experience for long-running fetch scripts
            capture_output=False,
            text=True,
            timeout=600,    # 10 minutes max per step
        )
        elapsed = time.time() - t0
        step_elapsed(t0)

        if result.returncode == 0:
            out_path = SCRIPT_DIR / out_rel
            if out_path.exists():
                size_kb = out_path.stat().st_size // 1024
                note = f"{size_kb} KB"
                ok(f"Output ready: {out_rel}  ({size_kb} KB)")
            else:
                note = "output file missing"
                warn(f"Step exited 0 but output not found: {out_rel}")

            return {
                "name":    name,
                "status":  "ok",
                "note":    note,
                "seconds": round(elapsed, 1),
            }
        else:
            fail(f"{name} exited with code {result.returncode}")
            return {
                "name":    name,
                "status":  "fail",
                "note":    f"exit code {result.returncode}",
                "seconds": round(time.time() - t0, 1),
            }

    except subprocess.TimeoutExpired:
        elapsed = time.time() - t0
        fail(f"{name} timed out after 10 minutes")
        warn("The script may still be running in the background — check manually.")
        return {
            "name": name, "status": "fail",
            "note": "timeout (10 min)", "seconds": round(elapsed, 1),
        }

    except Exception as exc:
        elapsed = time.time() - t0
        fail(f"{name} raised an unexpected exception: {exc}")
        return {
            "name": name, "status": "fail",
            "note": str(exc)[:50], "seconds": round(elapsed, 1),
        }


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 3 — MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the full SEA Dashboard data pipeline.\n"
            "Example: python run_pipeline.py --skip-fetch"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--skip-fetch", "--only-process", action="store_true",
        help="Skip the 3 fetch scripts (steps 1–3) and run processing only (steps 4–6). "
             "Use when you already have up-to-date raw data.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print the plan without actually running anything.",
    )
    parser.add_argument(
        "--step", type=int, default=None,
        metavar="N",
        help="Run only step N (1–6). Example: --step 4",
    )
    args = parser.parse_args()

    # ── Determine steps to run ───────────────────────────────────────────────
    if args.step is not None:
        steps_to_run = [s for s in STEPS if s["n"] == args.step]
        if not steps_to_run:
            print(f"  ✗  Unknown step: {args.step}  (valid: 1–{TOTAL})")
            return 1
        mode = f"single step [{args.step}/{TOTAL}]"
    elif args.skip_fetch:
        steps_to_run = [s for s in STEPS if not s["is_fetch"]]
        mode = "processing only (fetch skipped)"
    else:
        steps_to_run = STEPS.copy()
        mode = "full pipeline"

    # ── Banner ───────────────────────────────────────────────────────────────
    pipeline_banner("SEA Dashboard — Data Pipeline")

    print(f"  Mode          : {mode}")
    print(f"  Steps to run  : {len(steps_to_run)} of {TOTAL}")
    print(f"  Python        : {sys.executable}")
    print(f"  Working dir   : {SCRIPT_DIR}")
    if args.dry_run:
        print(f"  DRY RUN       : printing plan only, not executing")
    print()

    # ── Print execution plan ─────────────────────────────────────────────────
    info("Execution plan:")
    run_set = {s["n"] for s in steps_to_run}
    for step in STEPS:
        marker  = "▶" if step["n"] in run_set else "○"
        skipped = "" if step["n"] in run_set else "  (skipped)"
        print(f"    {marker}  [{step['n']}/{TOTAL}] {step['name']:<28}  {step['label']}{skipped}")
    print()

    # ── Run each step ────────────────────────────────────────────────────────
    results: list[dict] = []
    failed_names: set[str] = set()
    wall_start = time.time()

    for step in steps_to_run:
        # Dependency check: warn if a dependency failed (but still run the step)
        for dep in step.get("depends_on", []):
            if dep in failed_names:
                warn(f"{step['name']} depends on {dep} which failed — output may be stale")

        result = run_step(step, dry_run=args.dry_run)
        results.append(result)

        if result["status"] == "fail":
            failed_names.add(step["name"])

    # ── Summary table ────────────────────────────────────────────────────────
    pipeline_summary(results)

    # ── Next steps for the user ──────────────────────────────────────────────
    n_fail    = sum(1 for r in results if r.get("status") == "fail")
    wall_secs = time.time() - wall_start
    wall_m, wall_s = divmod(int(wall_secs), 60)
    wall_str = f"{wall_m}m {wall_s}s" if wall_m else f"{wall_s}s"

    print(f"  Wall clock time: {wall_str}")
    print()

    if n_fail == 0:
        print("  ✓  What to do next:")
        print("     Restart the Next.js dev server to load the new data:")
        print()
        print("       cd frontend")
        print("       npm run dev")
        print()
        print("     Or if already running, just hard-refresh the browser ( Cmd+Shift+R )")
        print()
        print("  ✓  To schedule a daily refresh, add this to your cron:")
        print(f"       0 6 * * *  cd {SCRIPT_DIR} && python run_pipeline.py --skip-fetch")
        print()
    else:
        print(f"  ⚠  {n_fail} step(s) failed.")
        print("     All other steps completed normally.")
        print("     Previously generated files are untouched and remain valid.")
        print()
        print("     Common fixes:")
        print("       GDELT rate-limited?  → Wait 15 min, then: python fetch_gdelt_news.py")
        print("       WB unreachable?      → Check internet, then: python fetch_worldbank.py")
        print("       Comtrade key needed? → Add COMTRADE_SUBSCRIPTION_KEY to .env")
        print()

    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
