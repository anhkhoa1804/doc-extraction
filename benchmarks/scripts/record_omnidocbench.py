"""Convert one verified OmniDocBench run into benchmark-result/1 bookkeeping.

This does not score documents.  Prediction generation and scoring remain in
the existing adapter and the pinned upstream evaluator.  The command verifies
the selected sample-to-prediction pairing again before recording the result,
so an interrupted or mismatched run cannot become a baseline artifact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from benchmarks.registry import (
    BenchmarkError,
    BenchmarkResult,
    load_manifest,
    write_result,
)
from benchmarks.scripts.build_omnidocbench_manifest import verify_manifest
from doc_extraction.evaluation import omnidocbench as odb


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BenchmarkError(f"cannot read run artifact: {path}") from exc
    if not isinstance(value, dict):
        raise BenchmarkError(f"run artifact is not a JSON object: {path}")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _load_per_page_metrics(run_directory: Path) -> dict[str, dict[str, float]]:
    """Join upstream per-page/per-table outputs by their official image key."""
    output: dict[str, dict[str, float]] = {}
    for path in sorted(run_directory.glob("*_per_page_edit.json")):
        name = path.name
        task = next(
            (task for task in ("text_block", "table", "reading_order", "display_formula") if f"_{task}_per_page_edit.json" in name),
            None,
        )
        if task is None:
            continue
        values = _read_json(path)
        for image_name, value in values.items():
            output.setdefault(image_name, {})[f"{task}_Edit_dist"] = float(value)

    for path in sorted(run_directory.glob("*_per_table_TEDS.json")):
        values = _read_json(path)
        by_page: dict[str, dict[str, list[float]]] = {}
        for case_name, scores in values.items():
            image_name = case_name.rsplit("_[", 1)[0]
            if image_name == case_name or not isinstance(scores, dict):
                raise BenchmarkError(f"cannot map official TEDS case to a page: {case_name}")
            for metric in ("TEDS", "TEDS_structure_only"):
                if metric in scores:
                    by_page.setdefault(image_name, {}).setdefault(metric, []).append(float(scores[metric]))
        for image_name, metrics in by_page.items():
            for metric, scores in metrics.items():
                output.setdefault(image_name, {})[f"{metric}_per_page_mean_diagnostic"] = sum(scores) / len(scores)
                output[image_name][f"{metric}_table_count"] = float(len(scores))
    return {name: metrics for name, metrics in sorted(output.items())}


def _selected_samples(samples: list[odb.OmniDocSample], metadata: dict[str, Any]) -> list[odb.OmniDocSample]:
    subset = metadata.get("subset")
    if subset is not None and not isinstance(subset, int):
        raise BenchmarkError("run metadata has invalid subset")
    seed = metadata.get("seed", 0)
    if not isinstance(seed, int):
        raise BenchmarkError("run metadata has invalid seed")
    selected = odb.select_subset(samples, subset, seed)
    if metadata.get("num_samples") != len(selected):
        raise BenchmarkError("run metadata sample count does not match its deterministic subset")
    return selected


def build_record(
    *,
    manifest_path: Path,
    dataset_root: Path,
    run_directory: Path,
    predictions_directory: Path | None = None,
    git_commit_override: str | None = None,
) -> BenchmarkResult:
    manifest = load_manifest(manifest_path)
    if manifest.name != "OmniDocBench":
        raise BenchmarkError(f"expected an OmniDocBench manifest, got {manifest.name!r}")
    ground_truth, samples = odb.load_dataset(dataset_root)
    metadata = _read_json(run_directory / "run_metadata.json")
    runtime = _read_json(run_directory / "runtime.json")
    metrics = _read_json(run_directory / "metrics.json")
    summary = _read_json(run_directory / "run_summary.json")
    manifest_path = run_directory / "sample_manifest.json"
    subset_identity = None
    manifest_sha256 = None
    if metadata.get("sample_manifest_identity"):
        if not manifest_path.is_file():
            raise BenchmarkError("representative run is missing its copied sample manifest")
        manifest_sha256 = _sha256(manifest_path)
        if manifest_sha256 != metadata.get("sample_manifest_sha256"):
            raise BenchmarkError("copied sample manifest hash differs from run metadata")
        try:
            selected_indices, _raw, frozen_manifest = verify_manifest(dataset_root, manifest_path)
        except (OSError, ValueError) as exc:
            raise BenchmarkError(f"invalid representative sample manifest: {exc}") from exc
        subset_identity = frozen_manifest["subset_identity"]["sha256"]
        if subset_identity != metadata["sample_manifest_identity"]:
            raise BenchmarkError("sample manifest identity differs from run metadata")
        by_index = {sample.index: sample for sample in samples}
        selected = [by_index[index] for index in selected_indices]
        if metadata.get("run_selected_count") != len(selected):
            raise BenchmarkError("representative run did not execute the complete frozen subset")
    else:
        selected = _selected_samples(samples, metadata)
    recorded_ids = metadata.get("sample_ids")
    if recorded_ids is not None:
        if len(recorded_ids) != len(selected):
            raise BenchmarkError("run metadata sample count differs from selected pages")
        for recorded, sample in zip(recorded_ids, selected, strict=True):
            if (
                recorded.get("dataset_index") != sample.index
                or recorded.get("image_name") != sample.image_name
                or recorded.get("page_no") != sample.page_no
            ):
                raise BenchmarkError(f"run metadata page mapping differs at index {sample.index}")
            if recorded.get("image_sha256") and recorded["image_sha256"] != _sha256(sample.image_path):
                raise BenchmarkError(f"run metadata image hash differs at index {sample.index}")
    predictions_dir = predictions_directory or run_directory / metadata.get("prediction_directory", "predictions")
    odb.validate_prediction_alignment(selected, predictions_dir)

    git_commit = git_commit_override or metadata.get("git_commit")
    if not isinstance(git_commit, str) or not git_commit or git_commit == "unavailable":
        raise BenchmarkError("run has no source revision; pass --git-commit only for a documented legacy run")
    config = metadata.get("config")
    if not isinstance(config, dict):
        raise BenchmarkError("run metadata has no configuration snapshot")
    config_hash = hashlib.sha256(
        json.dumps(config, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    model_versions = metadata.get("model_versions", {})
    if not isinstance(model_versions, dict):
        raise BenchmarkError("run metadata has invalid model_versions")
    failures = runtime.get("failures", [])
    if not isinstance(failures, list):
        raise BenchmarkError("runtime report has invalid failures")

    warnings = []
    if git_commit_override is not None:
        warnings.append("git_commit supplied explicitly because legacy run metadata lacked a source revision")
    runtime_per_page = runtime.get("per_page")
    if not isinstance(runtime_per_page, list) or len(runtime_per_page) != len(selected):
        warnings.append("per-page status/warning/runtime records are incomplete")

    stage_execution = summary.get("stage_execution", {})
    table_status = (
        stage_execution.get("metrics", {}).get("table", {})
        if isinstance(stage_execution, dict)
        else {}
    )
    if isinstance(table_status, dict):
        failures.extend(
            {"sample_id": str(case.get("case_name", "unknown")), "error": str(case.get("reason", "table_evaluator_error"))}
            for case in table_status.get("error_cases", [])
        )
        failures.extend(
            {"sample_id": str(case.get("case_name", "unknown")), "error": "table_evaluator_timeout"}
            for case in table_status.get("timeout_cases", [])
        )
    per_page_metrics = _load_per_page_metrics(run_directory)
    unexpected_metric_pages = set(per_page_metrics) - {sample.image_name for sample in selected}
    if unexpected_metric_pages:
        raise BenchmarkError(
            "official evaluator returned per-page scores outside the frozen subset: "
            f"{sorted(unexpected_metric_pages)[:5]}"
        )

    return BenchmarkResult(
        benchmark={"name": manifest.name, "version": manifest.version, "subset": manifest.subset},
        system={
            "git_commit": git_commit,
            "component": "doc-extraction",
            "config_hash": config_hash,
            "config": config,
            "model_versions": model_versions,
            "evaluator": {
                "name": "OmniDocBench",
                "version": manifest.version,
                "upstream_commit": metadata.get("upstream_commit", "not_recorded"),
                "match_method": "quick_match",
                "match_workers": summary.get("stage_execution", {}).get("page_match", {}).get("workers"),
                "metrics": sorted(metrics),
                "formula_cdm_enabled": False,
                "bleu_meteor_enabled": False,
            },
        },
        runtime={
            "device": metadata.get("device", "not_recorded"),
            "started_at": metadata.get("timestamp", "not_recorded"),
            "duration_seconds": runtime.get("wall_clock_seconds"),
            "python": metadata.get("python", "not_recorded"),
            "evaluator_upstream_commit": metadata.get("upstream_commit", "not_recorded"),
        },
        dataset={
            "sample_count": len(selected),
            "total_available_samples": len(samples),
            "ground_truth_file": ground_truth.name,
            "ground_truth_sha256": odb.dataset_content_hash(ground_truth),
            "ground_truth_semantic_sha256": odb.dataset_semantic_hash(ground_truth),
            "sample_ids": [
                {
                    "dataset_index": sample.index,
                    "image_name": sample.image_name,
                    "page_no": sample.page_no,
                    "image_sha256": _sha256(sample.image_path),
                }
                for sample in selected
            ],
            "subset_identity": subset_identity,
            "subset_manifest_sha256": manifest_sha256,
        },
        metrics={
            "official_end2end": metrics,
            "page_denominators": summary.get("page_denominators", {}),
            "evaluator_stage_execution": stage_execution,
            "extraction_runtime": runtime,
            "per_page_metrics": per_page_metrics,
        },
        failures=failures,
        warnings=warnings,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--run-directory", required=True, type=Path)
    parser.add_argument("--predictions-directory", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--manifest", type=Path, default=Path("benchmarks/manifests/omnidocbench.yaml")
    )
    parser.add_argument("--git-commit", help="Required only for legacy run metadata without a revision.")
    args = parser.parse_args(argv)
    try:
        result = build_record(
            manifest_path=args.manifest,
            dataset_root=args.dataset,
            run_directory=args.run_directory,
            predictions_directory=args.predictions_directory,
            git_commit_override=args.git_commit,
        )
        write_result(args.output, result)
    except BenchmarkError as exc:
        parser.error(str(exc))
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
