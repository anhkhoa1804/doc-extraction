#!/usr/bin/env python
"""OmniDocBench experiment, step 1 of 2: validate the dataset and generate
predictions with a doc_extraction backend.

Runs under this project's main environment (.venv, Python 3.12) — no
OmniDocBench dependency is needed for this step, only doc_extraction itself.
Independently rerunnable: re-running only regenerates predictions, it never
invokes the evaluator. See evaluate.py for step 2.

    python experiments/005_omnidocbench/prepare.py \\
        --dataset experiments/005_omnidocbench/dataset/demo \\
        --backend baseline \\
        --output experiments/005_omnidocbench/results/baseline

Dataset paths are never assumed — pass any directory containing an
OmniDocBench-shaped ground-truth JSON + images/ (a Kaggle input mount, a
local HuggingFace download, or the small demo set bundled with this repo's
clone of the upstream evaluator).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from doc_extraction.cli import collect_model_versions, process_file  # noqa: E402
from doc_extraction.config import load_config  # noqa: E402
from doc_extraction.evaluation import omnidocbench as odb  # noqa: E402
from doc_extraction.schemas.page import Page  # noqa: E402


def _process_sample(image_path: Path, config, backend_name: str, runs_dir: Path) -> tuple[Page, str, float]:
    """Adapts doc_extraction's whole-file `process_file` (which returns a
    full `Document`) to the single-page interface `write_predictions`
    expects. Every OmniDocBench sample is one page image, so the resulting
    Document always has exactly one page — asserted, not assumed, since a
    silent [0] on an empty list would be a confusing failure far from its
    cause."""
    document = process_file(image_path, config, output_root=runs_dir, backend_name=backend_name)
    if not document.pages:
        raise RuntimeError(f"backend produced zero pages for {image_path.name}")
    if len(document.pages) > 1:
        raise RuntimeError(
            f"backend produced {len(document.pages)} pages for a single-image input "
            f"{image_path.name} — expected exactly 1"
        )
    return document.pages[0], document.metadata.route, document.metadata.runtime_seconds or 0.0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dataset", required=True, help="OmniDocBench dataset directory (ground-truth JSON + images/).")
    parser.add_argument("--backend", required=True, choices=["baseline", "docling"])
    parser.add_argument("--output", required=True, help="Result directory for this backend, e.g. results/baseline")
    parser.add_argument("--config", default=str(REPO_ROOT / "configs" / "cpu.yaml"), help="doc_extraction pipeline config.")
    parser.add_argument(
        "--subset", type=int, default=None,
        help="Evaluate only this many pages, deterministically spread across the dataset (not the first N).",
    )
    parser.add_argument("--seed", type=int, default=0, help="Shifts which pages --subset picks; same seed -> same pages.")
    parser.add_argument("--keep-runs", action="store_true",
                         help="Keep doc_extraction's own per-page stage outputs (rendered/, layout/, ocr/, tables/, inspection/) "
                              "under <output>/_doc_extraction_runs/ for later inspection. Off by default: for a benchmark-sized "
                              "run this can be a lot of files; use --subset with --keep-runs for spot-checking a handful of pages.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    dataset_root = Path(args.dataset).resolve()
    output_root = Path(args.output).resolve()

    try:
        gt_path, samples = odb.load_dataset(dataset_root)
    except odb.DatasetError as exc:
        print(f"dataset error: {exc}", file=sys.stderr)
        return 1

    total_available = len(samples)
    samples = odb.select_subset(samples, args.subset, args.seed)
    print(f"dataset: {gt_path}")
    print(f"samples: {len(samples)} of {total_available} available (backend={args.backend})")

    config = load_config(args.config)
    predictions_dir = output_root / "predictions"
    runs_dir = output_root / "_doc_extraction_runs"

    def process_sample(image_path: Path):
        return _process_sample(image_path, config, args.backend, runs_dir)

    def log(msg: str) -> None:
        print(f"  {msg}")

    start = time.perf_counter()
    results = odb.write_predictions(samples, predictions_dir, process_sample, logger=log)
    wall_seconds = time.perf_counter() - start

    runtime_report = odb.write_runtime_report(results, output_root / "runtime.json")
    runtime_report["wall_clock_seconds"] = round(wall_seconds, 3)
    (output_root / "runtime.json").write_text(
        json.dumps(runtime_report, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    metadata = odb.build_benchmark_metadata(
        backend=args.backend,
        device=config.device,
        ground_truth_path=gt_path,
        num_samples=len(samples),
        config_snapshot=config.to_snapshot(),
        model_versions=collect_model_versions(args.backend),
    )
    # Repo-relative (or bare leaf) so the committed result carries no
    # username or machine-specific layout — see odb.portable_path.
    metadata["dataset_root"] = odb.portable_path(dataset_root)
    metadata["subset"] = args.subset
    metadata["seed"] = args.seed
    metadata["total_available_samples"] = total_available
    (output_root / "run_metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    if not args.keep_runs and runs_dir.exists():
        import shutil

        shutil.rmtree(runs_dir)

    print(
        f"done: {runtime_report['succeeded']}/{runtime_report['total_pages']} pages ok, "
        f"{runtime_report['failed']} failed, {wall_seconds:.1f}s wall clock "
        f"-> {predictions_dir}"
    )
    if runtime_report["succeeded"] == 0:
        print("no predictions were written — nothing for evaluate.py to score", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
