"""
Export pre-computed predictions to docs/predictions.json for the static site.

Run from the project root:
    python scripts/export_json.py
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "model"))

# Importing `context` triggers build_context() exactly once at module level.
from app import context  # noqa: E402

OUT = ROOT / "docs" / "predictions.json"
OUT.parent.mkdir(exist_ok=True)

with OUT.open("w") as f:
    json.dump(context, f, indent=2)

groups_written = len(context["groups"])
matches_written = sum(len(g["fixtures"]) for g in context["groups"])
size_kb = OUT.stat().st_size / 1024

print(f"Written: {OUT}")
print(f"  Groups : {groups_written}")
print(f"  Matches: {matches_written}")
print(f"  Size   : {size_kb:.1f} KB")
