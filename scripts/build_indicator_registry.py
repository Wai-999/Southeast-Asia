#!/usr/bin/env python3
"""
scripts/build_indicator_registry.py
Validates indicator_registry.json and prints a summary. Run to confirm registry is valid.
"""
import json, sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROC_DIR = PROJECT_ROOT / "pipeline" / "data" / "processed"

def main():
    f = PROC_DIR / "indicator_registry.json"
    if not f.exists():
        print("✗ indicator_registry.json not found"); return 1
    data = json.loads(f.read_text())
    sectors = data.get("sectors", {})
    total_inds = sum(len(s.get("indicators",{})) for s in sectors.values())
    print(f"✓ indicator_registry.json: {len(sectors)} sectors, {total_inds} total indicators")
    for sid, sector in sectors.items():
        inds = sector.get("indicators",{})
        print(f"  {sid:30s} {len(inds):3d} indicators  — {sector.get('sector_name','')}")
    return 0

if __name__ == "__main__": sys.exit(main())
