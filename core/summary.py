"""Committed crawl stats: one stats/{site}-{pass}.json per pass, never overwritten
across passes. The summarize job merges the shards' build_summary.json files
into the current pass's file once per workflow run.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path


def pass_label(pass_file: Path) -> str:
    """YYYY-MM of the current pass's start."""
    started = json.loads(pass_file.read_text())["started"]
    return datetime.fromisoformat(started).strftime("%Y-%m")


def merge(stats_dir: Path, site: str, label: str, build_files: list[Path]) -> dict:
    path = stats_dir / f"{site}-{label}.json"
    works: dict = json.loads(path.read_text())["works"] if path.exists() else {}
    now = datetime.now(UTC).isoformat(timespec="seconds")
    merged = 0
    for build_file in build_files:
        for entry in json.loads(build_file.read_text()):
            entry["updated"] = now
            works[entry["id"]] = entry
            merged += 1
    summary = {
        "pass": label,
        "updated": now,
        "totals": {
            "works": len(works),
            "sentences": sum(w["sentences"] for w in works.values()),
            "bytes": sum(w["bytes"] for w in works.values()),
        },
        "works": works,
    }
    stats_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=1, sort_keys=True))
    return {"merged": merged, **summary["totals"]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stats", required=True, help="stats directory")
    ap.add_argument("--site", required=True)
    ap.add_argument("--pass-file", required=True, help="state pass.json for the pass label")
    ap.add_argument("build_files", nargs="+", help="build_summary.json files")
    args = ap.parse_args()
    label = pass_label(Path(args.pass_file))
    result = merge(Path(args.stats), args.site, label, [Path(p) for p in args.build_files])
    print(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
