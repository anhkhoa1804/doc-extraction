"""No-network benchmark registry inspection and report rendering."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from benchmarks.registry import BenchmarkError, load_manifest, resolve_local_dataset
from benchmarks.report import render_report

BENCHMARK_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = BENCHMARK_ROOT.parent


def main() -> int:
    parser = argparse.ArgumentParser(prog="benchmark-registry")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list")
    inspect = commands.add_parser("inspect")
    inspect.add_argument("manifest", type=Path)
    report = commands.add_parser("report")
    report.add_argument("results", nargs="+", type=Path)
    live = commands.add_parser("live")
    live.add_argument("manifest", type=Path)
    live.add_argument("--allow-live", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "list":
            manifests = sorted((BENCHMARK_ROOT / "manifests").glob("*.yaml"))
            print(json.dumps([load_manifest(path).name for path in manifests]))
            return 0
        if args.command == "report":
            print(render_report(args.results))
            return 0
        manifest = load_manifest(args.manifest)
        if args.command == "live" and not (args.allow_live and manifest.live_evaluation):
            raise BenchmarkError("live evaluation requires --allow-live and a live manifest")
        print(
            json.dumps(
                {
                    "name": manifest.name,
                    "task": manifest.task,
                    "local_dataset": str(resolve_local_dataset(manifest, REPOSITORY_ROOT))
                    if resolve_local_dataset(manifest, REPOSITORY_ROOT)
                    else None,
                    "download_mode": manifest.download_mode,
                    "network_executed": False,
                },
                sort_keys=True,
            )
        )
        return 0
    except BenchmarkError as exc:
        print(json.dumps({"error": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
