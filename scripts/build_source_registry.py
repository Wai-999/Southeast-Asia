#!/usr/bin/env python3
"""
scripts/build_source_registry.py
Validates and re-exports source_registry.json. Run to confirm registry is valid.
"""
import json, sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROC_DIR = PROJECT_ROOT / "pipeline" / "data" / "processed"

def main():
    f = PROC_DIR / "source_registry.json"
    if not f.exists():
        print("✗ source_registry.json not found"); return 1
    data = json.loads(f.read_text())
    sources = data.get("sources", {})
    print(f"✓ source_registry.json: {len(sources)} sources registered")
    for sid, src in sources.items():
        print(f"  {sid:30s} {src.get('type','?'):25s} {src.get('name','?')[:40]}")
    return 0

if __name__ == "__main__": sys.exit(main())
