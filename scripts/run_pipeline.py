#!/usr/bin/env python3
"""
==============================================================================
  scripts/run_pipeline.py — SEA Change Intelligence Dashboard
==============================================================================

Master pipeline runner.  Run from the project root:

    python scripts/run_pipeline.py

Steps (run in order, each isolated — one failure never stops the rest):

    [1/4]  fetch_worldbank.py           World Bank annual indicators
    [2/4]  fetch_gdelt_news.py          GDELT news signals (last 7 days)
    [3/4]  generate_pattern_alerts.py   9-type pattern alerts with confidence
    [4/4]  fetch_comtrade.py            UN Comtrade / IMF DOTS trade flows
                                         (skipped if --no-comtrade is passed)

Output files written to pipeline/data/processed/:
    worldbank_indicators.json
    news_signals.json
    trade_flows.json
    pattern_alerts.json

Run log written to:
    pipeline/data/logs/pipeline_log.json   (last 30 runs, last_run mirror)

USAGE
──────
    python scripts/run_pipeline.py                  # full pipeline
    python scripts/run_pipeline.py --no-comtrade    # skip Comtrade step
    python scripts/run_pipeline.py --dry-run        # print plan, no execution
    python scripts/run_pipeline.py --refresh        # bypass cache for all fetches

RESILIENCE
──────────
    A failed fetch step is logged and the pipeline continues.
    Previously generated output files are never deleted.
    Exit code 0 = all steps ok, 1 = at least one step failed.

==============================================================================
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# ── Path resolution ───────────────────────────────────────────────────────────
# This script lives at  <project_root>/scripts/run_pipeline.py
# Pipeline scripts live at  <project_root>/pipeline/
PROJECT_ROOT  = Path(__file__).resolve().parent.parent
PIPELINE_DIR  = PROJECT_ROOT / "pipeline"
PROC_DIR      = PIPELINE_DIR / "data" / "processed"
LOGS_DIR      = PIPELINE_DIR / "data" / "logs"
PIPELINE_LOG  = LOGS_DIR / "pipeline_log.json"

# .env file at project root (for COMTRADE_SUBSCRIPTION_KEY detection)
DOTENV_PATH   = PROJECT_ROOT / ".env"
PIPELINE_ENV  = PIPELINE_DIR / ".env"


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 1 — STEP DEFINITIONS
# ══════════════════════════════════════════════════════════════════════════════

STEPS: list[dict] = [
    {
        "n":         1,
        "key":       "worldbank",
        "script":    "fetch_worldbank.py",
        "label":     "World Bank indicators",
        "output":    PROC_DIR / "worldbank_indicators.json",
        "can_skip":  False,
        "timeout":   300,     # 5 min — WB API is fast
    },
    {
        "n":         2,
        "key":       "gdelt",
        "script":    "fetch_gdelt_news.py",
        "label":     "GDELT news signals",
        "output":    PROC_DIR / "news_signals.json",
        "can_skip":  False,
        "timeout":   1200,    # 20 min — GDELT makes many small calls; can be slow
    },
    {
        "n":         3,
        "key":       "alerts",
        "script":    "generate_pattern_alerts.py",
        "label":     "Pattern alert generation",
        "output":    PROC_DIR / "pattern_alerts.json",
        "can_skip":  False,
        "timeout":   120,     # 2 min — pure computation, no network calls
        # Runs after WB + GDELT so alerts always reflect the freshest data.
        # Runs BEFORE Comtrade so alerts are ready even if Comtrade is skipped/fails.
    },
    {
        "n":         4,
        "key":       "comtrade",
        "script":    "fetch_comtrade.py",
        "label":     "UN Comtrade trade flows",
        "output":    PROC_DIR / "trade_flows.json",
        "can_skip":  True,    # skipped with --no-comtrade
        "timeout":   600,     # 10 min — Comtrade free preview is paginated
    },
]

TOTAL = len(STEPS)


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 2 — DISPLAY HELPERS
# ══════════════════════════════════════════════════════════════════════════════

_W = 62   # line width

def _banner(title: str) -> None:
    inner_w = _W - 2          # characters between the two ║
    pad     = max(0, inner_w - 4 - len(title))  # 4 = "  " prefix + "  " suffix
    print()
    print("╔" + "═" * inner_w + "╗")
    print(f"║  {title}" + " " * pad + "  ║")
    print("╚" + "═" * inner_w + "╝")
    print()

def _rule(char: str = "─") -> None:
    print("  " + char * (_W - 4))

def _step_header(n: int, total: int, label: str, script: str) -> float:
    print()
    print(f"  ┌─ [{n}/{total}] {label} ({script})")
    return time.time()

def _step_footer(t0: float, status: str, note: str = "") -> None:
    elapsed = round(time.time() - t0, 1)
    icon = "✓" if status == "ok" else ("○" if status == "skip" else "✗")
    colour = ""   # no ANSI — keep output clean for log files
    suffix  = f"  ({note})" if note else ""
    print(f"  └─ {icon} {status.upper():<4}  {elapsed}s{suffix}")


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 3 — ENV / KEY DETECTION
# ══════════════════════════════════════════════════════════════════════════════

def _read_dotenv(path: Path) -> dict[str, str]:
    """Parse a .env file into {KEY: value}. Ignores comments and blank lines."""
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def _comtrade_key_available() -> bool:
    """Return True if a real COMTRADE_SUBSCRIPTION_KEY is found in any .env."""
    placeholder = ("your_comtrade_key_here", "", "none", "null", "false")
    for path in (DOTENV_PATH, PIPELINE_ENV):
        env = _read_dotenv(path)
        key = env.get("COMTRADE_SUBSCRIPTION_KEY", "").lower()
        if key and key not in placeholder:
            return True
    return False


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 4 — STEP RUNNER
# ══════════════════════════════════════════════════════════════════════════════

def run_step(
    step: dict,
    extra_args: list[str] | None = None,
    dry_run: bool = False,
) -> dict:
    """
    Run one pipeline step as a subprocess.
    Returns: { key, status ("ok"|"skip"|"fail"), note, seconds }.
    Never raises — all exceptions become status="fail".
    """
    script_path = PIPELINE_DIR / step["script"]
    key         = step["key"]
    t0          = _step_header(step["n"], TOTAL, step["label"], step["script"])

    if dry_run:
        cmd_str = f"python pipeline/{step['script']}"
        if extra_args:
            cmd_str += " " + " ".join(extra_args)
        print(f"    Would run:  {cmd_str}")
        print(f"    Output:     {step['output'].relative_to(PROJECT_ROOT)}")
        _step_footer(t0, "skip", "dry-run")
        return {"key": key, "status": "skip", "note": "dry-run", "seconds": 0.0}

    if not script_path.exists():
        _step_footer(t0, "fail", "script not found")
        return {"key": key, "status": "fail", "note": "script not found", "seconds": 0.0}

    cmd = [sys.executable, str(script_path)] + (extra_args or [])
    print(f"    Running: python pipeline/{step['script']}" +
          (f"  {' '.join(extra_args)}" if extra_args else ""))
    print()

    try:
        timeout_s = step.get("timeout", 600)
        result = subprocess.run(
            cmd,
            cwd=str(PIPELINE_DIR),   # run from pipeline/ so relative paths work
            capture_output=False,     # stream output directly to terminal
            text=True,
            timeout=timeout_s,
        )
        elapsed = round(time.time() - t0, 1)

        if result.returncode == 0:
            out_path: Path = step["output"]
            if out_path.exists():
                size_kb = out_path.stat().st_size // 1024
                note    = f"{out_path.name}  {size_kb} KB"
                _step_footer(t0, "ok", note)
                return {"key": key, "status": "ok", "note": note, "seconds": elapsed}
            else:
                _step_footer(t0, "ok", "output not found (check manually)")
                return {"key": key, "status": "ok", "note": "no output file", "seconds": elapsed}
        else:
            note = f"exit code {result.returncode}"
            _step_footer(t0, "fail", note)
            return {"key": key, "status": "fail", "note": note, "seconds": elapsed}

    except subprocess.TimeoutExpired:
        timeout_s = step.get("timeout", 600)
        note = f"timed out after {timeout_s // 60} min"
        _step_footer(t0, "fail", note)
        return {"key": key, "status": "fail", "note": note, "seconds": float(timeout_s)}

    except Exception as exc:
        note = str(exc)[:80]
        _step_footer(t0, "fail", note)
        return {"key": key, "status": "fail", "note": note,
                "seconds": round(time.time() - t0, 1)}


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 5 — STATISTICS READERS
# ══════════════════════════════════════════════════════════════════════════════

def _wb_stats() -> dict:
    """Read countries + records count from worldbank_indicators.json."""
    try:
        with open(PROC_DIR / "worldbank_indicators.json", encoding="utf-8") as f:
            d = json.load(f)
        meta = d.get("meta", {})
        countries = meta.get("countries_fetched", 0)
        records   = meta.get("total_records",    len(d.get("records", [])))
        return {"countries": countries, "records": records}
    except Exception:
        return {"countries": 0, "records": 0}


def _news_stats() -> dict:
    """Read article count + country count from news_signals.json."""
    try:
        with open(PROC_DIR / "news_signals.json", encoding="utf-8") as f:
            d = json.load(f)
        meta = d.get("meta", {})
        articles  = meta.get("unique_articles", meta.get("total_articles", 0))
        countries = meta.get("countries_fetched", len(d.get("news_counts", {})))
        return {"articles": articles, "countries": countries}
    except Exception:
        return {"articles": 0, "countries": 0}


def _trade_stats() -> dict:
    """Read reporters + flow count from trade_flows.json."""
    try:
        with open(PROC_DIR / "trade_flows.json", encoding="utf-8") as f:
            d = json.load(f)
        meta      = d.get("meta", {})
        reporters = meta.get("reporters", 0)
        flows     = len(d.get("flows", []))
        return {"reporters": reporters, "flows": flows}
    except Exception:
        return {"reporters": 0, "flows": 0}


def _alert_stats() -> dict:
    """Read alert counts from pattern_alerts.json."""
    try:
        with open(PROC_DIR / "pattern_alerts.json", encoding="utf-8") as f:
            d = json.load(f)
        meta = d.get("meta", {})
        return {
            "total":     meta.get("triggered_alerts", 0),
            "critical":  meta.get("critical", 0),
            "warnings":  meta.get("warnings", 0),
            "info":      meta.get("info_count", 0),
            "countries": meta.get("countries_checked", 0),
        }
    except Exception:
        return {"total": 0, "critical": 0, "warnings": 0, "info": 0, "countries": 0}


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 6 — PIPELINE LOG
# ══════════════════════════════════════════════════════════════════════════════

def _save_pipeline_log(
    run_results: dict[str, dict],
    summary: dict,
    started_at: str,
    finished_at: str,
    elapsed_seconds: float,
    mode: str,
    dry_run: bool,
) -> None:
    """
    Append to pipeline_log.json (rolling last-30 runs).

    Structure:
        _meta          → description, format
        last_run       → mirror of runs[-1]
        runs           → list of up to 30 run entries
    """
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    status = "success"
    if any(r.get("status") == "fail" for r in run_results.values()):
        all_failed = all(
            r.get("status") == "fail"
            for r in run_results.values()
            if r.get("status") != "skip"
        )
        status = "failed" if all_failed else "partial"
    if dry_run:
        status = "dry-run"

    run_id = started_at.replace(":", "").replace("-", "").replace("T", "")[:15]

    entry = {
        "run_id":          run_id,
        "started_at":      started_at,
        "finished_at":     finished_at,
        "elapsed_seconds": round(elapsed_seconds, 1),
        "status":          status,
        "mode":            mode,
        "dry_run":         dry_run,
        "steps": {
            key: {
                "status":  r.get("status", "skip"),
                "note":    r.get("note", ""),
                "seconds": r.get("seconds", 0.0),
            }
            for key, r in run_results.items()
        },
        "summary": summary,
    }

    # Load existing log (or start fresh)
    existing: dict = {}
    if PIPELINE_LOG.exists():
        try:
            existing = json.loads(PIPELINE_LOG.read_text(encoding="utf-8"))
        except Exception:
            existing = {}

    runs: list[dict] = existing.get("runs", [])
    runs.append(entry)
    runs = runs[-30:]   # keep last 30

    output = {
        "_meta": {
            "description": (
                "SEA Dashboard pipeline run log — "
                "tracks fetch + alert generation results"
            ),
            "pipeline":    "scripts/run_pipeline.py",
            "format":      "last_run mirrors runs[-1]; runs keeps last 30 entries",
        },
        "last_run": entry,
        "runs":     runs,
    }

    PIPELINE_LOG.write_text(
        json.dumps(output, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 7 — SUMMARY PRINTER
# ══════════════════════════════════════════════════════════════════════════════

def _print_summary(
    run_results:  dict[str, dict],
    wb_stats:     dict,
    news_stats:   dict,
    trade_stats:  dict,
    alert_stats:  dict,
    wall_secs:    float,
    dry_run:      bool,
) -> None:
    """Print the formatted final summary block."""

    def _yn(key: str) -> str:
        r = run_results.get(key, {})
        s = r.get("status", "skip")
        if s == "ok":
            return "✓  yes"
        if s == "skip":
            return "○  skipped"
        return "✗  FAILED"

    def _detail(key: str, text: str) -> str:
        r = run_results.get(key, {})
        if r.get("status") == "ok":
            return f"({text})"
        return ""

    wb_detail    = _detail("worldbank", f"{wb_stats['countries']} countries, {wb_stats['records']} records")
    news_detail  = _detail("gdelt",     f"{news_stats['articles']} articles, {news_stats['countries']} countries")
    alert_detail = _detail("alerts",    f"{alert_stats['total']} alerts — {alert_stats['critical']} critical, {alert_stats['warnings']} warnings")
    trade_detail = _detail("comtrade",  f"{trade_stats['reporters']} reporters, {trade_stats['flows']} flows")

    # Total counts
    total_countries  = max(wb_stats["countries"], news_stats["countries"])
    total_news       = news_stats["articles"]
    total_alerts     = alert_stats["total"]
    total_trade_flows = trade_stats["flows"]

    m, s   = divmod(int(wall_secs), 60)
    wall_str = f"{m}m {s}s" if m else f"{s}s"

    n_failed = sum(1 for r in run_results.values() if r.get("status") == "fail")

    print()
    _rule("═")
    print(f"  {'PIPELINE SUMMARY' + (' (DRY RUN)' if dry_run else '')}")
    _rule()
    # Summary order matches step execution order: WB → GDELT → Alerts → Comtrade
    print(f"  {'World Bank updated':<22}: {_yn('worldbank'):<12}  {wb_detail}")
    print(f"  {'GDELT updated':<22}: {_yn('gdelt'):<12}  {news_detail}")
    print(f"  {'Alerts generated':<22}: {_yn('alerts'):<12}  {alert_detail}")
    print(f"  {'Comtrade updated':<22}: {_yn('comtrade'):<12}  {trade_detail}")
    _rule()
    print(f"  {'Total countries updated':<22}: {total_countries}")
    print(f"  {'Total news items':<22}: {total_news}")
    print(f"  {'Total alerts':<22}: {total_alerts}")
    print(f"  {'Total trade flows':<22}: {total_trade_flows}")
    _rule()
    print(f"  Wall clock: {wall_str}")
    _rule("═")
    print()

    if n_failed == 0 and not dry_run:
        print("  ✓  All steps completed successfully.")
        print()
        print("  Next steps:")
        print("    • Hard-refresh the browser: Cmd+Shift+R (Mac) / Ctrl+Shift+R (Win)")
        print("    • Or restart Next.js dev server:")
        print("        cd frontend && npm run dev")
        print()
        print("  Recommended schedule (cron examples):")
        print("    # GDELT news every 6 hours:")
        print("    0 */6 * * *  cd <project_root> && python scripts/run_pipeline.py --no-comtrade")
        print("    # Full pipeline every Monday at 4am:")
        print("    0 4 * * 1   cd <project_root> && python scripts/run_pipeline.py")
        print()
    elif dry_run:
        print("  ○  Dry run complete — nothing was executed.")
        print()
    else:
        print(f"  ⚠  {n_failed} step(s) failed — see ✗ markers above.")
        print("     Existing output files were NOT modified.")
        print()
        print("  Common fixes:")
        if run_results.get("worldbank", {}).get("status") == "fail":
            print("    World Bank unreachable → check internet connection")
            print("      python pipeline/fetch_worldbank.py")
        if run_results.get("gdelt", {}).get("status") == "fail":
            print("    GDELT rate-limited → wait 15 min, then retry")
            print("      python pipeline/fetch_gdelt_news.py")
        if run_results.get("comtrade", {}).get("status") == "fail":
            print("    Comtrade failed → try free mode or add key to .env:")
            print("      COMTRADE_SUBSCRIPTION_KEY=your_key in .env")
            print("      python pipeline/fetch_comtrade.py --mode free")
        if run_results.get("alerts", {}).get("status") == "fail":
            print("    Alert engine failed → run individually:")
            print("      python pipeline/generate_pattern_alerts.py")
        print()

    print(f"  Log saved → {PIPELINE_LOG.relative_to(PROJECT_ROOT)}")
    print()


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 8 — MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the SEA Change Intelligence Dashboard data pipeline.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python scripts/run_pipeline.py                  # full pipeline\n"
            "  python scripts/run_pipeline.py --no-comtrade    # skip trade fetch\n"
            "  python scripts/run_pipeline.py --dry-run        # print plan only\n"
            "  python scripts/run_pipeline.py --refresh        # bypass cache\n"
        ),
    )
    parser.add_argument(
        "--no-comtrade", dest="no_comtrade", action="store_true",
        help="Skip the UN Comtrade fetch (step 3). Use for frequent news-only runs.",
    )
    parser.add_argument(
        "--dry-run", dest="dry_run", action="store_true",
        help="Print what would run without executing anything.",
    )
    parser.add_argument(
        "--refresh", action="store_true",
        help="Bypass cached data — forces fresh API calls for all fetch steps.",
    )
    args = parser.parse_args()

    mode = "no-comtrade" if args.no_comtrade else "full"

    # ── Auto-detect Comtrade key ──────────────────────────────────────────────
    has_comtrade_key = _comtrade_key_available()
    comtrade_extra   = []
    if has_comtrade_key:
        comtrade_extra = []   # key auto-detected by fetch_comtrade.py via .env
    else:
        comtrade_extra = ["--mode", "free"]   # free preview, no key needed

    # --refresh passes through to all fetch steps
    if args.refresh:
        comtrade_extra += ["--refresh"]

    # ── Banner ────────────────────────────────────────────────────────────────
    _banner("SEA Change Dashboard — Data Pipeline")
    print(f"  Mode      : {mode}")
    print(f"  Dry run   : {'yes — nothing will execute' if args.dry_run else 'no'}")
    print(f"  Refresh   : {'bypass cache' if args.refresh else 'use cache if available'}")
    print(f"  Comtrade  : {'API key detected ✓' if has_comtrade_key else 'free preview mode (no key)'}")
    print()
    print("  Steps:")
    for step in STEPS:
        skip_label = ""
        if step["key"] == "comtrade" and args.no_comtrade:
            skip_label = "  ← will be SKIPPED (--no-comtrade)"
        print(f"    [{step['n']}/{TOTAL}] {step['script']:<30}  {step['label']}{skip_label}")
    print()
    if not args.dry_run:
        print("  Output files → pipeline/data/processed/")
        print("  Run log      → pipeline/data/logs/pipeline_log.json")
        print()

    # ── Execute steps ─────────────────────────────────────────────────────────
    run_results: dict[str, dict] = {}
    wall_start  = time.time()
    started_at  = datetime.now().isoformat(timespec="seconds")

    for step in STEPS:
        key = step["key"]

        # Skip comtrade if --no-comtrade
        if key == "comtrade" and args.no_comtrade:
            print()
            print(f"  ┌─ [{step['n']}/{TOTAL}] {step['label']} ({step['script']})")
            print(f"  └─ ○ SKIP  (--no-comtrade passed)")
            run_results[key] = {
                "key":     key,
                "status":  "skip",
                "note":    "--no-comtrade",
                "seconds": 0.0,
            }
            continue

        # Build extra args per step
        extra: list[str] = []
        if key == "comtrade":
            extra = comtrade_extra.copy()
        elif key in ("worldbank", "gdelt") and args.refresh:
            extra = ["--refresh"]

        result = run_step(step, extra_args=extra, dry_run=args.dry_run)
        run_results[key] = result

        # Non-fetch steps (alerts) always run even if fetches failed
        # Already handled since we never abort the loop on failure

    wall_secs   = time.time() - wall_start
    finished_at = datetime.now().isoformat(timespec="seconds")

    # ── Read output statistics ────────────────────────────────────────────────
    wb_stats    = _wb_stats()
    news_stats  = _news_stats()
    trade_stats = _trade_stats()
    alert_stats = _alert_stats()

    summary = {
        "worldbank_updated":     run_results.get("worldbank", {}).get("status") == "ok",
        "gdelt_updated":         run_results.get("gdelt",     {}).get("status") == "ok",
        "comtrade_updated":      run_results.get("comtrade",  {}).get("status") == "ok",
        "alerts_generated":      run_results.get("alerts",    {}).get("status") == "ok",
        "total_countries_updated": max(wb_stats["countries"], news_stats["countries"]),
        "total_news_items":        news_stats["articles"],
        "total_alerts":            alert_stats["total"],
        "alert_critical":          alert_stats["critical"],
        "alert_warnings":          alert_stats["warnings"],
        "wb_records":              wb_stats["records"],
        "trade_reporters":         trade_stats["reporters"],
        "trade_flows":             trade_stats["flows"],
    }

    # ── Save pipeline log ─────────────────────────────────────────────────────
    if not args.dry_run:
        _save_pipeline_log(
            run_results    = run_results,
            summary        = summary,
            started_at     = started_at,
            finished_at    = finished_at,
            elapsed_seconds= wall_secs,
            mode           = mode,
            dry_run        = args.dry_run,
        )

    # ── Print summary ─────────────────────────────────────────────────────────
    _print_summary(
        run_results  = run_results,
        wb_stats     = wb_stats,
        news_stats   = news_stats,
        trade_stats  = trade_stats,
        alert_stats  = alert_stats,
        wall_secs    = wall_secs,
        dry_run      = args.dry_run,
    )

    n_failed = sum(1 for r in run_results.values() if r.get("status") == "fail")
    return 0 if n_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
