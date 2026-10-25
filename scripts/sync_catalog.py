"""Refresh public CRUN model definitions without credentials or generation."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from crun.catalog import refresh_catalog


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "catalog.json")
    args = parser.parse_args()
    snapshot = refresh_catalog(destination=args.output)
    print(json.dumps({"output": str(args.output), "refreshed_at": snapshot["refreshed_at"], **snapshot["summary"], "errors": snapshot["errors"]}, indent=2))
