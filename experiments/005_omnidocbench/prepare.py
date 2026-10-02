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
import hashlib
import importlib.metadata
import json
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT))

from benchmarks.scripts.build_omnidocbench_manifest import verify_manifest
from doc_extraction.cli import collect_model_versions, process_file
from doc_extraction.config import load_config
from doc_extraction.evaluation import omnidocbench as odb
from doc_extraction.utils.hashing import sha256_file
from doc_extraction.utils.ids import document_id as make_document_id


def build_source_attestation() -> dict:
    """Hash the exact relevant working-tree files, not only the Git commit."""
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    tracked = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    ).stdout.decode().split("\0")
    selected = []
    for rel in tracked:
        if not rel:
            continue
        path = REPO_ROOT / rel
        relevant = (
            rel.startswith("src/doc_extraction/") and rel.endswith(".py")
            or rel in {"experiments/005_omnidocbench/prepare.py", "experiments/005_omnidocbench/evaluate.py"}
            or rel.startswith("benchmarks/scripts/") and rel.endswith(".py")
            or rel in {"pyproject.toml", "uv.lock"}
        )
        if relevant and path.is_file():
            selected.append((rel, path))
    import hashlib

    digest = hashlib.sha256()
    file_hashes = {}
    for rel, path in sorted(selected):
        data = path.read_bytes()
        file_hash = hashlib.sha256(data).hexdigest()
        file_hashes[rel] = file_hash
        digest.update(rel.encode("utf-8") + b"\0" + data + b"\0")
    return {
        "git_commit": head,
        "working_tree_clean": not status,
        "working_tree_status": status,
        "source_files": file_hashes,
        "source_snapshot_sha256": digest.hexdigest(),
        "source_snapshot_scope": "current working-tree bytes for doc_extraction Python sources, benchmark scripts, OmniDocBench prepare/evaluate scripts, pyproject.toml and uv.lock; evaluator revision is recorded separately",
        "root_uv_lock_sha256": hashlib.sha256((REPO_ROOT / "uv.lock").read_bytes()).hexdigest(),
    }


def build_runtime_attestation() -> dict:
    packages = sorted(
        f"{distribution.metadata.get('Name', 'unknown')}=={distribution.version}"
        for distribution in importlib.metadata.distributions()
    )
    package_inventory = "\n".join(packages) + "\n"
    critical_names = {
        "doc-extraction", "paddlepaddle-gpu", "paddlepaddle", "paddleocr", "paddlex",
        "numpy", "pillow", "safetensors", "opencv-contrib-python",
    }
    critical_packages = {}
    for name in sorted(critical_names):
        try:
            critical_packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            continue
    try:
        gpu = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip().splitlines()
    except (OSError, subprocess.SubprocessError):
        gpu = []
    return {
        "python": sys.version,
        "python_executable": Path(sys.executable).name,
        "platform": platform.platform(),
        "critical_packages": critical_packages,
        "package_inventory_count": len(packages),
        "package_inventory_sha256": hashlib.sha256(package_inventory.encode()).hexdigest(),
        "gpu_inventory": gpu,
    }


def _process_sample(image_path: Path, config, backend_name: str, runs_dir: Path) -> odb.ProcessedSample:
    """Adapts doc_extraction's whole-file `process_file` (which returns a
    full `Document`) to the single-page interface `write_predictions`
    expects. Every OmniDocBench sample is one page image, so the resulting
    Document always has exactly one page — asserted, not assumed, since a
    silent [0] on an empty list would be a confusing failure far from its
    cause."""
    try:
        document = process_file(image_path, config, output_root=runs_dir, backend_name=backend_name)
    except Exception as exc:
        try:
            failed_id = make_document_id(image_path, sha256_file(image_path))
            timing_path = runs_dir / failed_id / "diagnostics" / "backend_phase_timings.json"
            if timing_path.is_file():
                exc.backend_timings = json.loads(timing_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            pass
        raise
    if not document.pages:
        raise RuntimeError(f"backend produced zero pages for {image_path.name}")
    if len(document.pages) > 1:
        raise RuntimeError(
            f"backend produced {len(document.pages)} pages for a single-image input "
            f"{image_path.name} — expected exactly 1"
        )
    timing_path = runs_dir / document.document_id / "diagnostics" / "backend_phase_timings.json"
    backend_timings = json.loads(timing_path.read_text(encoding="utf-8")) if timing_path.is_file() else {}
    return odb.ProcessedSample(
        page=document.pages[0],
        route=document.metadata.route,
        runtime_seconds=document.metadata.runtime_seconds or 0.0,
        status=document.metadata.status.value,
        warnings=list(document.metadata.warnings),
        errors=list(document.metadata.errors),
        document_id=document.document_id,
        input_sha256=document.metadata.file_hash_sha256,
        backend_timings=backend_timings,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dataset", required=True, help="OmniDocBench dataset directory (ground-truth JSON + images/).")
    parser.add_argument("--backend", required=True, choices=["baseline", "docling", "paddleocr_vl"])
    parser.add_argument("--output", required=True, help="Result directory for this backend, e.g. results/baseline")
    parser.add_argument("--config", default=str(REPO_ROOT / "configs" / "cpu.yaml"), help="doc_extraction pipeline config.")
    parser.add_argument(
        "--subset", type=int, default=None,
        help="Evaluate only this many pages, deterministically spread across the dataset (not the first N).",
    )
    parser.add_argument("--manifest", type=Path, default=None,
                        help="Frozen representative-subset manifest; validates complete dataset identity.")
    parser.add_argument("--take", type=int, default=None,
                        help="Deterministic prefix of a frozen manifest (only for the preflight run).")
    parser.add_argument("--page-ids", nargs="+", default=None,
                        help="Explicit page_id values from a frozen manifest, for smoke/preflight only.")
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
    if output_root.exists():
        print(f"output directory already exists; refusing to overwrite: {output_root}", file=sys.stderr)
        return 1

    try:
        gt_path, samples = odb.load_dataset(dataset_root)
    except odb.DatasetError as exc:
        print(f"dataset error: {exc}", file=sys.stderr)
        return 1

    total_available = len(samples)
    raw_records = json.loads(gt_path.read_text(encoding="utf-8"))
    manifest = None
    if args.manifest:
        if args.subset is not None:
            print("--subset cannot be combined with --manifest", file=sys.stderr)
            return 2
        try:
            selected_indices, raw_records, manifest = verify_manifest(dataset_root, args.manifest)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"manifest validation error: {exc}", file=sys.stderr)
            return 1
        samples_by_index = {sample.index: sample for sample in samples}
        samples = [samples_by_index[index] for index in selected_indices]
        if args.take is not None:
            if args.page_ids:
                print("--take cannot be combined with --page-ids", file=sys.stderr)
                return 2
            if args.take <= 0 or args.take > len(samples):
                print(f"--take must be in 1..{len(samples)}", file=sys.stderr)
                return 2
            samples = samples[: args.take]
        if args.page_ids:
            if len(args.page_ids) != len(set(args.page_ids)):
                print("--page-ids contains duplicates", file=sys.stderr)
                return 2
            samples_by_page_id = {
                f"{sample.image_name}#{sample.page_no}": sample for sample in samples
            }
            missing = [page_id for page_id in args.page_ids if page_id not in samples_by_page_id]
            if missing:
                print(f"--page-ids are not in the frozen manifest: {missing}", file=sys.stderr)
                return 2
            samples = [samples_by_page_id[page_id] for page_id in args.page_ids]
    else:
        if args.take is not None:
            print("--take requires --manifest", file=sys.stderr)
            return 2
        samples = odb.select_subset(samples, args.subset, args.seed)
    print(f"dataset: {gt_path}")
    print(f"samples: {len(samples)} of {total_available} available (backend={args.backend})")

    config = load_config(args.config)
    if args.backend == "paddleocr_vl" and config.device != "cuda":
        print(
            "refusing PaddleOCR-VL benchmark on a non-CUDA config; use the explicit GPU profile "
            "(full E2E benchmark execution never falls back to CPU)",
            file=sys.stderr,
        )
        return 2
    source_attestation = build_source_attestation()
    runtime_attestation = build_runtime_attestation()
    pre_run_model_versions = collect_model_versions(args.backend)
    if args.backend == "paddleocr_vl":
        absent_hashes = [
            name for name in ("model_weights_sha256", "layout_weights_sha256")
            if not pre_run_model_versions.get(name)
        ]
        if absent_hashes:
            print(f"model artifact hash preflight failed: missing {absent_hashes}", file=sys.stderr)
            return 1
    output_root.mkdir(parents=True, exist_ok=False)
    (output_root / "source_attestation.json").write_text(
        json.dumps(source_attestation, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (output_root / "pre_run_model_versions.json").write_text(
        json.dumps(pre_run_model_versions, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (output_root / "runtime_attestation.json").write_text(
        json.dumps(runtime_attestation, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    if args.manifest:
        shutil.copy2(args.manifest, output_root / "sample_manifest.json")
    predictions_dir = output_root / f"predictions_{output_root.name}"
    runs_dir = output_root / "_doc_extraction_runs"

    def process_sample(image_path: Path):
        return _process_sample(image_path, config, args.backend, runs_dir)

    def log(msg: str) -> None:
        print(f"  {msg}")

    start = time.perf_counter()
    try:
        results = odb.write_predictions(samples, predictions_dir, process_sample, logger=log)
    finally:
        if args.backend == "paddleocr_vl":
            from doc_extraction.backends.paddleocr_vl_backend import (
                shutdown_paddleocr_vl_workers,
            )

            shutdown_paddleocr_vl_workers()
    wall_seconds = time.perf_counter() - start

    runtime_report = odb.write_runtime_report(results, output_root / "runtime.json")
    runtime_report["wall_clock_seconds"] = round(wall_seconds, 3)
    expected_page_ids = [f"{sample.image_name}#{sample.page_no}" for sample in samples]
    actual_page_ids = [result.page_id for result in results]
    runtime_report["coverage"] = {
        "expected": len(expected_page_ids),
        "attempted": len(actual_page_ids),
        "completed": sum(result.error is None for result in results),
        "failed": sum(result.error is not None for result in results),
        "missing_attempts": sorted(set(expected_page_ids) - set(actual_page_ids)),
        "unexpected_attempts": sorted(set(actual_page_ids) - set(expected_page_ids)),
        "attempt_ids_exact": len(actual_page_ids) == len(expected_page_ids)
        and set(actual_page_ids) == set(expected_page_ids)
        and len(actual_page_ids) == len(set(actual_page_ids)),
    }
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
    config_path = Path(args.config).resolve()
    metadata["config_file"] = odb.portable_path(config_path)
    metadata["config_sha256"] = hashlib.sha256(config_path.read_bytes()).hexdigest()
    metadata["subset"] = args.subset
    metadata["seed"] = args.seed
    metadata["total_available_samples"] = total_available
    metadata["sample_manifest"] = odb.portable_path(args.manifest.resolve()) if args.manifest else None
    metadata["sample_manifest_sha256"] = hashlib.sha256(args.manifest.resolve().read_bytes()).hexdigest() if args.manifest else None
    metadata["sample_manifest_identity"] = manifest["subset_identity"]["sha256"] if manifest else None
    metadata["manifest_selected_count"] = len(manifest["subset"]["samples"]) if manifest else None
    metadata["run_selected_count"] = len(samples)
    metadata["evaluation_ground_truth"] = "ground_truth_subset.json" if manifest else None
    metadata["prediction_directory"] = predictions_dir.name
    records_by_index = {index: raw_records[index] for index in range(len(raw_records))}
    results_by_page_id = {result.page_id: result for result in results}
    metadata["sample_ids"] = [
        {
            "dataset_index": sample.index,
            "sample_id": records_by_index[sample.index]["page_info"].get("sample_id"),
            "page_id": f"{sample.image_name}#{sample.page_no}",
            "image_name": sample.image_name,
            "page_no": sample.page_no,
            "image_sha256": hashlib.sha256(sample.image_path.read_bytes()).hexdigest(),
            "document_id": results_by_page_id[f"{sample.image_name}#{sample.page_no}"].document_id,
        }
        for sample in samples
    ]
    metadata["source_attestation"] = source_attestation
    metadata["runtime_attestation"] = runtime_attestation
    metadata["pre_run_model_versions"] = pre_run_model_versions
    metadata["run_attestation_version"] = 1
    ground_truth_subset = json.dumps(
        [records_by_index[sample.index] for sample in samples], ensure_ascii=False, indent=2
    ) + "\n"
    (output_root / "ground_truth_subset.json").write_text(ground_truth_subset, encoding="utf-8")
    metadata["ground_truth_subset_sha256"] = hashlib.sha256(ground_truth_subset.encode("utf-8")).hexdigest()
    metadata["selected_page_ids"] = expected_page_ids
    (output_root / "run_metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    if not args.keep_runs and runs_dir.exists():
        shutil.rmtree(runs_dir)

    print(
        f"done: {runtime_report['succeeded']}/{runtime_report['total_pages']} pages ok, "
        f"{runtime_report['failed']} failed, {wall_seconds:.1f}s wall clock "
        f"-> {predictions_dir}"
    )
    if runtime_report["failed"]:
        print("one or more samples failed; refusing to mark this as a valid baseline", file=sys.stderr)
        return 1
    if runtime_report["succeeded"] == 0:
        print("no predictions were written — nothing for evaluate.py to score", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
