#!/usr/bin/env python3
"""
scripts/run_universal_pipeline.py
────────────────────────────────────────────────────────────────────────────
Master orchestrator for the Universal Official Data Intelligence Pipeline.

Runs all fetchers, normalization, merge, validation, and freshness report
in the correct order. Each step is independent — failure in one source
does not stop the pipeline.

USAGE
  # Full pipeline
  python scripts/run_universal_pipeline.py

  # Skip slow scrapers (use cached/API only sources)
  python scripts/run_universal_pipeline.py --fast

  # Run only specific steps
  python scripts/run_universal_pipeline.py --steps wb imf merge validate

  # Run just forecasts
  python scripts/run_universal_pipeline.py --steps imf adb merge validate freshness

STEPS AVAILABLE
  registries   — validate source and indicator registries
  wb           — World Bank core 8 indicators (pipeline/fetch_worldbank.py)
  wb_ext       — World Bank extended indicators (governance, social, etc.)
  imf          — IMF WEO forecasts
  adb          — ADB ADO forecasts
  asean        — ASEANstats (via WB proxy)
  comtrade     — UN Comtrade trade flows
  nso          — National statistics offices
  cb           — Central banks
  ministries   — Ministries and customs
  tourism      — Tourism sources
  energy       — Energy and environment
  technology   — Technology and digital economy
  infra        — Infrastructure projects
  environment  — Agriculture and social (additional WB)
  press        — Official press releases and policy updates
  normalize    — Normalize all source files
  merge        — Merge all sources into combined_indicators.json
  validate     — Validate combined_indicators.json
  freshness    — Generate freshness report

OUTPUT
  pipeline/data/processed/combined_indicators.json
  pipeline/data/processed/source_audit_report.json
  pipeline/data/processed/freshness_report.json
  pipeline/data/logs/universal_pipeline_log.json
"""

import sys
import json
import time
import argparse
import subprocess
from pathlib import Path
from datetime import datetime, date

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR  = PROJECT_ROOT / "scripts"
PIPELINE_DIR = PROJECT_ROOT / "pipeline"
LOGS_DIR     = PIPELINE_DIR / "data" / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

ts_now     = lambda: datetime.utcnow().isoformat() + "Z"
today_str  = date.today().strftime("%Y%m%d")

# Step definitions: (step_id, script_path, description, is_slow)
STEPS = {
    "registries": (None,                                       "Validate registries",              False),
    "wb":         (PIPELINE_DIR / "fetch_worldbank.py",        "World Bank core indicators",       False),
    "wb_ext":     (SCRIPTS_DIR  / "fetch_worldbank_gep.py",    "World Bank extended indicators",   False),
    "imf":        (SCRIPTS_DIR  / "fetch_imf_weo.py",          "IMF WEO forecasts",               False),
    "adb":        (SCRIPTS_DIR  / "fetch_adb_ado.py",          "ADB ADO forecasts",               False),
    "asean":      (SCRIPTS_DIR  / "fetch_aseanstats.py",       "ASEANstats",                      False),
    "comtrade":   (SCRIPTS_DIR  / "fetch_un_comtrade.py",      "UN Comtrade trade flows",         False),
    "nso":        (SCRIPTS_DIR  / "fetch_national_statistics.py","National statistics offices",   True),
    "cb":         (SCRIPTS_DIR  / "fetch_central_banks.py",    "Central banks",                   True),
    "ministries": (SCRIPTS_DIR  / "fetch_ministries_customs.py","Ministries & customs",           True),
    "tourism":    (SCRIPTS_DIR  / "fetch_tourism_sources.py",  "Tourism",                         False),
    "energy":     (SCRIPTS_DIR  / "fetch_energy_sources.py",   "Energy & environment",            False),
    "technology": (SCRIPTS_DIR  / "fetch_technology_policy_sources.py","Technology & governance", False),
    "infra":      (SCRIPTS_DIR  / "fetch_infrastructure_projects.py","Infrastructure projects",   False),
    "environment":(SCRIPTS_DIR  / "fetch_environment_sources.py","Agriculture & social (WB)",    False),
    "press":      (SCRIPTS_DIR  / "fetch_official_press_releases.py","Official press releases",  True),
    "normalize":  (SCRIPTS_DIR  / "normalize_indicators.py",   "Normalize all sources",           False),
    "merge":      (SCRIPTS_DIR  / "merge_all_sources.py",      "Merge all sources",               False),
    "validate":   (SCRIPTS_DIR  / "validate_all_sources.py",   "Validate combined output",        False),
    "freshness":  (SCRIPTS_DIR  / "generate_freshness_report.py","Generate freshness report",     False),
}

FULL_PIPELINE_ORDER = [
    "registries",
    "wb", "wb_ext",
    "imf", "adb", "asean",
    "comtrade",
    "tourism", "energy", "technology", "environment",
    "nso", "cb", "ministries",
    "infra", "press",
    "normalize",
    "merge",
    "validate",
    "freshness",
]

FAST_PIPELINE_ORDER = [
    "registries",
    "wb", "wb_ext",
    "imf", "adb", "asean",
    "comtrade",
    "tourism", "energy", "technology", "environment",
    "normalize",
    "merge",
    "validate",
    "freshness",
]


def run_registries():
    """Validate that registry files exist and are parseable."""
    proc_dir = PROJECT_ROOT / "pipeline" / "data" / "processed"
    ok = True
    for fname in ["source_registry.json", "indicator_registry.json", "country_registry.json"]:
        fpath = proc_dir / fname
        if not fpath.exists():
            print(f"  ✗ Missing: {fname}")
            ok = False
        else:
            try:
                data = json.loads(fpath.read_text())
                if fname == "source_registry.json":
                    print(f"  ✓ {fname}: {len(data.get('sources',{}))} sources")
                elif fname == "indicator_registry.json":
                    sectors = data.get("sectors",{})
                    total_inds = sum(len(s.get("indicators",{})) for s in sectors.values())
                    print(f"  ✓ {fname}: {len(sectors)} sectors, {total_inds} indicators")
                elif fname == "country_registry.json":
                    print(f"  ✓ {fname}: {len(data.get('countries',{}))} countries")
            except Exception as e:
                print(f"  ✗ {fname}: parse error: {e}")
                ok = False
    return 0 if ok else 1


def run_step(step_id: str) -> tuple[int, float]:
    """Run a single pipeline step. Returns (exit_code, duration_secs)."""
    script, desc, _ = STEPS[step_id]
    t0 = time.time()

    if step_id == "registries":
        rc = run_registries()
        return rc, time.time() - t0

    if script is None or not script.exists():
        print(f"  ⚠ Script not found: {script}")
        return 1, time.time() - t0

    # Per-step extra args
    extra_args: list[str] = []
    if step_id == "comtrade":
        extra_args = ["--all-years"]  # always fetch full 2019–present history

    result = subprocess.run(
        [sys.executable, str(script)] + extra_args,
        cwd=str(PROJECT_ROOT),
        capture_output=False,
    )
    return result.returncode, time.time() - t0


def main():
    parser = argparse.ArgumentParser(description="Universal Pipeline Orchestrator")
    parser.add_argument("--fast", action="store_true",
                        help="Skip slow scrapers (NSO, central banks, ministries)")
    parser.add_argument("--steps", nargs="+",
                        choices=list(STEPS.keys()),
                        help="Run only specific steps (overrides --fast)")
    args = parser.parse_args()

    # Determine steps to run
    if args.steps:
        steps_to_run = args.steps
    elif args.fast:
        steps_to_run = FAST_PIPELINE_ORDER
    else:
        steps_to_run = FULL_PIPELINE_ORDER

    print(f"\n{'═'*70}")
    print(f"  Universal Official Data Intelligence Pipeline")
    print(f"  Date: {date.today().isoformat()} | Steps: {len(steps_to_run)}")
    print(f"  Mode: {'fast (no scrapers)' if args.fast and not args.steps else 'full'}")
    print(f"{'═'*70}\n")

    pipeline_start = time.time()
    results = {}

    for step_id in steps_to_run:
        step_data = STEPS.get(step_id)
        if not step_data:
            print(f"\n  ⚠ Unknown step: {step_id}")
            continue

        _, desc, is_slow = step_data
        step_label = f"[{step_id.upper():12s}] {desc}"

        print(f"\n{'─'*70}")
        print(f"  ▸ {step_label}")
        print(f"{'─'*70}", flush=True)

        rc, duration = run_step(step_id)
        status = "✓ DONE" if rc == 0 else f"⚠ FAILED (exit {rc})"
        results[step_id] = {"status": "pass" if rc == 0 else "fail",
                            "exit_code": rc, "duration_secs": round(duration, 1)}
        print(f"\n  {status} — {duration:.1f}s", flush=True)

    total_secs = time.time() - pipeline_start
    passed = sum(1 for r in results.values() if r["status"] == "pass")
    failed = sum(1 for r in results.values() if r["status"] == "fail")

    print(f"\n{'═'*70}")
    print(f"  PIPELINE COMPLETE")
    print(f"  Total time  : {total_secs:.0f}s")
    print(f"  Steps passed: {passed}/{len(results)}")
    print(f"  Steps failed: {failed}/{len(results)}")
    if failed:
        print(f"\n  Failed steps:")
        for sid, r in results.items():
            if r["status"] == "fail":
                print(f"    ✗ {sid}")
    print(f"{'═'*70}\n")

    # Write pipeline log
    log = {
        "run_at":         ts_now(),
        "mode":           "fast" if args.fast else "full",
        "steps_run":      steps_to_run,
        "total_secs":     round(total_secs, 1),
        "steps_passed":   passed,
        "steps_failed":   failed,
        "step_results":   results,
    }
    log_file = LOGS_DIR / f"universal_pipeline_{today_str}.json"
    log_file.write_text(json.dumps(log, indent=2))
    print(f"  Log: {log_file.relative_to(PROJECT_ROOT)}\n")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
