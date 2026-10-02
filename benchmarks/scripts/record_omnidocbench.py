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
from collections import defaultdict
from pathlib import Path
from statistics import mean, median
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


def _stratified_diagnostics(page_results: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize per-page scores by observed annotation metadata, without pooling tasks."""
    grouped: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    page_counts: dict[str, int] = defaultdict(int)
    for page in page_results:
        attrs = page.get("source_metadata", {})
        labels = {
            "data_source": [str(attrs.get("data_source", "unknown"))],
            "language": [str(attrs.get("language", "unknown"))],
            "layout": [str(attrs.get("layout", "unknown"))],
            "subset": [str(attrs.get("subset", "unknown"))],
            "special_issue": [str(value) for value in attrs.get("special_issue", [])]
            if attrs.get("special_issue") else ["none"],
        }
        for dimension, values in labels.items():
            for value in values:
                group = f"{dimension}:{value}"
                page_counts[group] += 1
                for metric, score in page.get("metrics", {}).items():
                    if metric.endswith("_table_count") or not isinstance(score, (int, float)):
                        continue
                    grouped[group][metric].append(float(score))
    summaries = []
    small_groups = []
    for group in sorted(page_counts):
        if page_counts[group] < 5:
            small_groups.append({"group": group, "page_count": page_counts[group]})
        for metric, scores in sorted(grouped[group].items()):
            if len(scores) < 5:
                continue
            summaries.append({
                "group": group,
                "metric": metric,
                "metric_page_denominator": len(scores),
                "mean_of_page_scores": mean(scores),
                "median_of_page_scores": median(scores),
                "aggregation_note": "diagnostic mean of upstream per-page scores; official aggregate remains in official_end2end",
            })
    return {"minimum_metric_n": 5, "summaries": summaries, "small_page_groups": small_groups}


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
    raw_records: list[dict[str, Any]] | None = None
    frozen_manifest: dict[str, Any] | None = None
    if metadata.get("sample_manifest_identity"):
        if not manifest_path.is_file():
            raise BenchmarkError("representative run is missing its copied sample manifest")
        manifest_sha256 = _sha256(manifest_path)
        if manifest_sha256 != metadata.get("sample_manifest_sha256"):
            raise BenchmarkError("copied sample manifest hash differs from run metadata")
        try:
            selected_indices, raw_records, frozen_manifest = verify_manifest(dataset_root, manifest_path)
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

    runtime_by_image = {
        str(row.get("image_name")): row
        for row in runtime_per_page or []
        if isinstance(row, dict) and row.get("image_name")
    }
    page_results = []
    for sample in selected:
        truth_record = raw_records[sample.index] if raw_records is not None else {}
        page_info = truth_record.get("page_info", {}) if isinstance(truth_record, dict) else {}
        page_results.append({
            "dataset_index": sample.index,
            "page_id": f"{sample.image_name}#{sample.page_no}",
            "sample_id": page_info.get("sample_id"),
            "image_name": sample.image_name,
            "page_no": sample.page_no,
            "image_sha256": _sha256(sample.image_path),
            "source_metadata": page_info.get("page_attribute", {}),
            "route_status_runtime": runtime_by_image.get(sample.image_name),
            "metrics": per_page_metrics.get(sample.image_name, {}),
        })

    table_metric_debug = table_status.get("TEDS", {}) if isinstance(table_status, dict) else {}
    extraction_failures = runtime.get("failures", [])
    evaluator_errors = table_metric_debug.get("error_cases", []) if isinstance(table_metric_debug, dict) else []
    evaluator_timeouts = table_metric_debug.get("timeout_cases", []) if isinstance(table_metric_debug, dict) else []
    current_population_valid = (
        len(selected) == (frozen_manifest or {}).get("subset", {}).get("actual_size", len(selected))
        and len(runtime_per_page or []) == len(selected)
        and all(row.get("status") in {"success", "success_with_warnings"} for row in runtime_per_page or [])
        and not extraction_failures
        and len(evaluator_errors) == 0
        and len(evaluator_timeouts) == 0
    )

    return BenchmarkResult(
        benchmark={"name": manifest.name, "version": manifest.version, "subset": manifest.subset},
        system={
            "git_commit": git_commit,
            "component": "doc-extraction",
            "config_hash": config_hash,
            "config": config,
            "config_file": metadata.get("config_file"),
            "config_file_sha256": metadata.get("config_sha256"),
            "model_versions": model_versions,
            "evaluator": {
                "name": "OmniDocBench",
                "version": manifest.version,
                "upstream_commit": metadata.get("upstream_commit", "not_recorded"),
                "match_method": "quick_match",
                "match_workers": summary.get("stage_execution", {}).get("page_match", {}).get("workers"),
                "metrics": sorted(metrics),
                "match_protocol": summary.get("stage_execution", {}).get("page_match", {}),
                "table_teds_execution": table_metric_debug,
                "formula_cdm_enabled": False,
                "bleu_meteor_enabled": False,
            },
        },
        runtime={
            "device": metadata.get("device", "not_recorded"),
            "run_id": run_directory.name,
            "metadata_recorded_at": metadata.get("timestamp", "not_recorded"),
            "duration_seconds": runtime.get("wall_clock_seconds"),
            "python": metadata.get("python", "not_recorded"),
            "platform": metadata.get("platform", "not_recorded"),
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
            "coverage_population": (frozen_manifest or {}).get("production_policy", {}),
            "dataset_integrity_exclusions": (frozen_manifest or {}).get("subset", {}).get("eligibility_exclusions", []),
        },
        metrics={
            "current_population_valid": current_population_valid,
            "official_end2end": metrics,
            "page_denominators": summary.get("page_denominators", {}),
            "evaluator_stage_execution": stage_execution,
            "extraction_runtime": runtime,
            "per_page_metrics": per_page_metrics,
            "page_results": page_results,
            "stratified_diagnostics": _stratified_diagnostics(page_results),
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
