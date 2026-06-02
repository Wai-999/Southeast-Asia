#!/usr/bin/env python3
"""
==============================================================================
  schedule_local.py — SEA Change Intelligence Dashboard
==============================================================================

Local background scheduler. Keep this running in a terminal and it will
automatically refresh your dashboard data on the recommended schedule:

    • GDELT news        →  every 6 hours
    • World Bank data   →  every Monday at 04:00
    • Comtrade trade    →  every Monday at 04:30
    • Reprocess + alerts → immediately after each fetch

Press  Ctrl+C  to stop.

USAGE
─────
  cd pipeline
  python schedule_local.py           # start with default schedule
  python schedule_local.py --once    # run everything once now and exit
  python schedule_local.py --mode news   # run one mode now, then keep scheduling

REQUIREMENTS
────────────
  pip install schedule     (already in requirements.txt)

HOW IT WORKS
────────────
  This script uses the 'schedule' library to register timed jobs, then
  enters an infinite loop that checks every 30 seconds whether any job
  is due to run.  Each job calls run_pipeline.py with a --mode flag so
  only the relevant scripts are executed.

  All output from each run is logged to:
    pipeline/data/logs/schedule_YYYYMMDD.log

  The refresh_log.json is updated after each successful run, and the
  dashboard badge automatically reflects the new timestamps.

==============================================================================
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    import schedule
except ImportError:
    print()
    print("  ✗  The 'schedule' library is not installed.")
    print("     Run:  pip install schedule")
    print("     Or:   pip install -r requirements.txt")
    sys.exit(1)

SCRIPT_DIR = Path(__file__).parent
LOG_DIR    = SCRIPT_DIR / "data" / "logs"


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 1 — SCHEDULE CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

# How often each source refreshes
REFRESH_SCHEDULE = {
    "news":      "every 6 hours",
    "data":      "every Monday at 04:00",   # WB + Comtrade
}

# In code:
# schedule.every(6).hours.do(run_mode, "news")
# schedule.every().monday.at("04:00").do(run_mode, "data")


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 2 — LOGGING SETUP
# ══════════════════════════════════════════════════════════════════════════════

def setup_logging() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    today    = datetime.now().strftime("%Y%m%d")
    log_file = LOG_DIR / f"schedule_{today}.log"

    logger = logging.getLogger("sea_scheduler")
    logger.setLevel(logging.INFO)

    # File handler — detailed logs
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    logger.addHandler(fh)

    # Console handler — concise
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(logging.Formatter("  %(message)s"))
    logger.addHandler(ch)

    return logger


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 3 — JOB RUNNER
# ══════════════════════════════════════════════════════════════════════════════

def run_mode(mode: str, logger: logging.Logger) -> None:
    """
    Run one pipeline mode via subprocess and log the result.
    This is the function registered with schedule.every(...).do().
    """
    ts     = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    labels = {
        "news":      "GDELT news refresh",
        "data":      "WB + Comtrade data refresh",
        "worldbank": "World Bank refresh",
        "comtrade":  "Comtrade refresh",
        "all":       "Full pipeline",
        "process":   "Reprocess only",
    }
    label = labels.get(mode, mode)

    print()
    print(f"  ┌{'─' * 54}┐")
    print(f"  │  {ts}  ▶  {label:<30}  │")
    print(f"  └{'─' * 54}┘")
    logger.info(f"START  mode={mode}  ({label})")

    run_py     = SCRIPT_DIR / "run_pipeline.py"
    today      = datetime.now().strftime("%Y%m%d")
    log_file   = LOG_DIR / f"schedule_{today}.log"
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    try:
        with open(log_file, "a", encoding="utf-8") as lf:
            result = subprocess.run(
                [sys.executable, str(run_py), "--mode", mode],
                cwd=str(SCRIPT_DIR),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=1800,   # 30-minute timeout for the full job
            )
            # Write full output to the log file
            lf.write(f"\n{'=' * 60}\n")
            lf.write(f"  {ts}  --mode {mode}\n")
            lf.write(f"{'=' * 60}\n")
            lf.write(result.stdout or "")
            lf.write("\n")

        elapsed = round(time.time() - t0)
        m, s    = divmod(elapsed, 60)
        elapsed_str = f"{m}m {s}s" if m else f"{s}s"

        if result.returncode == 0:
            print(f"  ✓  {label} completed in {elapsed_str}")
            logger.info(f"OK     mode={mode}  elapsed={elapsed_str}")
        else:
            print(f"  ✗  {label} failed (exit {result.returncode}) — see {log_file.name}")
            logger.warning(f"FAIL   mode={mode}  exit={result.returncode}  elapsed={elapsed_str}")

    except subprocess.TimeoutExpired:
        print(f"  ✗  {label} timed out after 30 minutes")
        logger.error(f"TIMEOUT  mode={mode}")

    except Exception as exc:
        print(f"  ✗  {label} raised an exception: {exc}")
        logger.error(f"ERROR  mode={mode}  error={exc}")


def _print_next_runs() -> None:
    """Print a table of all scheduled jobs and when they next run."""
    jobs = schedule.get_jobs()
    if not jobs:
        return
    print()
    print("  Scheduled jobs:")
    print("  " + "─" * 52)
    for job in jobs:
        next_run = job.next_run
        if next_run:
            ts = next_run.strftime("%Y-%m-%d %H:%M")
            delta_secs = (next_run - datetime.now()).total_seconds()
            if delta_secs > 0:
                h, rem = divmod(int(delta_secs), 3600)
                m, _   = divmod(rem, 60)
                countdown = f"in {h}h {m}m" if h else f"in {m}m"
            else:
                countdown = "now"
            print(f"    {str(job.job_func.__name__ if hasattr(job.job_func, '__name__') else job):<20}  "
                  f"next: {ts}  ({countdown})")
    print()


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 4 — MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Local scheduler for SEA Dashboard data pipeline"
    )
    parser.add_argument(
        "--once", action="store_true",
        help="Run all jobs once immediately and exit (no daemon loop)",
    )
    parser.add_argument(
        "--mode", choices=["news", "data", "worldbank", "comtrade", "all", "process"],
        default=None,
        help="Run one specific mode once now (still enters daemon loop after)",
    )
    args = parser.parse_args()

    logger = setup_logging()
    today  = datetime.now().strftime("%Y%m%d")
    print()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║   SEA Dashboard — Local Refresh Scheduler                   ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()
    print(f"  Started        : {datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}")
    print(f"  Log file       : data/logs/schedule_{today}.log")
    print()
    print("  Refresh schedule:")
    for src, when in REFRESH_SCHEDULE.items():
        print(f"    • --mode {src:<12}  {when}")
    print()
    print("  Press  Ctrl+C  to stop the scheduler.")
    print()

    # ── Run one mode immediately if requested ─────────────────────────────
    if args.mode:
        print(f"  Running --mode {args.mode} now …")
        run_mode(args.mode, logger)

    # ── One-shot mode ─────────────────────────────────────────────────────
    if args.once:
        print("  Running all jobs once …")
        run_mode("news", logger)
        run_mode("data", logger)
        print()
        print("  ✓  One-shot run complete. Exiting.")
        return 0

    # ── Register scheduled jobs ───────────────────────────────────────────
    # GDELT news: every 6 hours
    schedule.every(6).hours.do(run_mode, "news", logger)

    # World Bank + Comtrade: every Monday at 04:00 / 04:30
    schedule.every().monday.at("04:00").do(run_mode, "worldbank", logger)
    schedule.every().monday.at("04:30").do(run_mode, "comtrade",  logger)

    # Full reprocess (no fetch): every day at 05:00 to refresh alerts
    schedule.every().day.at("05:00").do(run_mode, "process", logger)

    _print_next_runs()
    logger.info("Scheduler started — entering main loop")

    # ── Main loop ─────────────────────────────────────────────────────────
    tick = 0
    try:
        while True:
            schedule.run_pending()
            time.sleep(30)   # check every 30 seconds
            tick += 1

            # Print next-run table every 30 minutes
            if tick % 60 == 0:
                _print_next_runs()

    except KeyboardInterrupt:
        print()
        print("  Scheduler stopped by user (Ctrl+C).")
        logger.info("Scheduler stopped by user")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
