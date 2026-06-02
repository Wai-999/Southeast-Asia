"""
pipeline/utils/logger.py
────────────────────────────────────────────────────────────────────
Shared terminal output helpers for every SEA Dashboard pipeline script.

All scripts import from here so the output looks consistent whether you
run one script on its own or the full pipeline via run_pipeline.py.

Colours are automatically turned off when output is piped to a file or
run inside CI (we detect this by checking if stdout is a terminal).
────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import sys
import time
from datetime import datetime

# ── Colour support ────────────────────────────────────────────────────────────
# isatty() returns True when running in a real terminal (colours work),
# False when piped to a file or run by another script (strip colour codes).
_COLOUR = sys.stdout.isatty()


def _c(code: str, text: str) -> str:
    """Wrap text in an ANSI escape sequence — no-op when colour is disabled."""
    return f"\033[{code}m{text}\033[0m" if _COLOUR else text


def green(t: str)  -> str: return _c("32", t)
def red(t: str)    -> str: return _c("31", t)
def yellow(t: str) -> str: return _c("33", t)
def cyan(t: str)   -> str: return _c("36", t)
def bold(t: str)   -> str: return _c("1",  t)
def dim(t: str)    -> str: return _c("2",  t)
def blue(t: str)   -> str: return _c("34", t)


# ── Pipeline-level banners ────────────────────────────────────────────────────

def pipeline_banner(title: str = "SEA Dashboard — Data Pipeline") -> None:
    """
    Print the large banner shown at the top of every pipeline run.

    Example:
    ╔══════════════════════════════════════════════════════════════╗
    ║  SEA Dashboard — Data Pipeline                               ║
    ╚══════════════════════════════════════════════════════════════╝
      Started: 2026-06-02  14:30:00
    """
    W = 62   # inner width of the box
    # Bold the title but keep the box the right width
    padded = bold(title) + " " * max(0, W - 2 - len(title))
    print()
    print("╔" + "═" * W + "╗")
    print("║  " + padded + "  ║")
    print("╚" + "═" * W + "╝")
    print(f"  {dim('Started: ' + datetime.now().strftime('%Y-%m-%d  %H:%M:%S'))}")
    print()


def step_banner(step: int, total: int, script: str) -> float:
    """
    Print a step header line and return the wall-clock start time.

    Call step_elapsed(t0) afterwards to print how long the step took.

    Example:
    [1/6] fetch_worldbank.py  ──────────────────────────────────
    """
    tag = f"[{step}/{total}]"
    bar = dim("─" * max(0, 54 - len(script)))
    print(f"\n{cyan(bold(tag))} {script}  {bar}")
    return time.time()


def step_elapsed(t0: float) -> None:
    """Print the time taken since t0 (returned by step_banner)."""
    secs = time.time() - t0
    if secs < 60:
        print(f"  {dim(f'Finished in {secs:.1f}s')}")
    else:
        m, s = divmod(int(secs), 60)
        print(f"  {dim(f'Finished in {m}m {s}s')}")


# ── Per-line helpers ──────────────────────────────────────────────────────────

def ok(msg: str) -> None:
    """Green checkmark — use when something succeeded."""
    print(f"  {green('✓')}  {msg}")


def fail(msg: str) -> None:
    """
    Red cross — use when something failed.
    Writes to stderr so it stands out even when stdout is redirected.
    """
    print(f"  {red('✗')}  {msg}", file=sys.stderr)


def warn(msg: str) -> None:
    """Yellow warning triangle — use for non-fatal issues."""
    print(f"  {yellow('⚠')}  {msg}")


def info(msg: str) -> None:
    """Dim bullet — use for general informational messages."""
    print(f"  {dim('•')}  {msg}")


def section(title: str) -> None:
    """
    Print a section header with an underline.

    Example:
      Step 1 — Load source files
      ──────────────────────────
    """
    print(f"\n  {bold(title)}")
    print("  " + dim("─" * len(title)))


def progress(current: int, total: int, label: str = "") -> None:
    """
    Print an inline progress bar (overwrites the current line).

    Call progress_done() to move to the next line when finished.

    Example:
      [████████░░░░░░░░░░░░]  40%  Thailand
    """
    pct  = int(current / total * 100) if total > 0 else 0
    done = int(pct / 5)
    bar  = "█" * done + "░" * (20 - done)
    suffix = f"  {label}" if label else ""
    print(f"\r  [{bar}] {pct:3d}%{suffix}", end="", flush=True)


def progress_done() -> None:
    """Move to a new line after a progress bar is complete."""
    print()


# ── Final summary table ───────────────────────────────────────────────────────

def pipeline_summary(results: list[dict]) -> None:
    """
    Print the final pipeline results table.

    Each dict in 'results' must have:
      name    (str)   — script filename, e.g. "fetch_worldbank.py"
      status  (str)   — "ok", "skip", or "fail"
      note    (str)   — short description shown in the table, e.g. "632 KB"
      seconds (float) — how long the step took

    Example output:
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
      PIPELINE SUMMARY
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
      ✓  fetch_worldbank.py           632 KB                    14s
      ✓  fetch_gdelt_news.py          53 KB                     42s
      ✓  fetch_comtrade.py            315 KB                    8s
      ✓  process_indicators.py        128 KB                    2s
      ✓  process_news.py              91 KB                     1s
      ✓  generate_alerts.py           44 KB                     1s

      6 succeeded · 0 failed · 0 skipped · 1m 8s total

      🎉  All scripts completed successfully!
    """
    ICON = {
        "ok":   green("✓"),
        "skip": yellow("~"),
        "fail": red("✗"),
    }

    print()
    print("━" * 64)
    print(bold("  PIPELINE SUMMARY"))
    print("━" * 64)

    total_seconds = 0.0
    for r in results:
        icon     = ICON.get(r.get("status", "fail"), "?")
        name     = r.get("name", "?").ljust(30)
        note     = r.get("note", "")
        secs     = float(r.get("seconds", 0))
        total_seconds += secs
        time_str = dim(f"{secs:.0f}s".rjust(5))
        print(f"  {icon}  {name}  {dim(note):<32}  {time_str}")

    n_ok   = sum(1 for r in results if r.get("status") == "ok")
    n_fail = sum(1 for r in results if r.get("status") == "fail")
    n_skip = sum(1 for r in results if r.get("status") == "skip")

    m, s = divmod(int(total_seconds), 60)
    total_label = f"{m}m {s}s" if m else f"{s}s"

    print()
    print(f"  {n_ok} succeeded · {n_fail} failed · {n_skip} skipped · {total_label} total")
    print()

    if n_fail == 0:
        print(bold(green("  🎉  All scripts completed successfully!")))
        print(f"  {dim('Dashboard data is ready.')}")
    else:
        print(bold(red(f"  ✗  {n_fail} script(s) failed — check the errors above")))
        print(f"  {dim('The pipeline continued past failures; other output files are still valid.')}")
    print()
