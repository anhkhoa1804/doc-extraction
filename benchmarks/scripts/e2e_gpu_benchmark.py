"""Controlled, fail-closed runner for the frozen E2E GPU benchmark.

The default behavior is a dry plan.  Use ``all --execute`` only after the
dedicated Paddle runtime and expected L4 are available.  No model is loaded by
the GPU preflight.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from benchmarks.scripts.build_omnidocbench_manifest import verify_manifest
from doc_extraction.config import load_config
from doc_extraction.evaluation import omnidocbench as odb

DEFAULT_MANIFEST = ROOT / "benchmarks/manifests/omnidocbench-representative-v2.json"
DEFAULT_DETERMINISM = ROOT / "benchmarks/reports/omnidocbench/e2e-determinism-v1.json"
PREPARE = ROOT / "experiments/005_omnidocbench/prepare.py"
EVALUATE = ROOT / "experiments/005_omnidocbench/evaluate.py"
EXPECTED_RUNTIME_PACKAGES = {
    "paddlepaddle-gpu": "3.2.1",
    "paddleocr": "3.7.0",
    "paddlex": "3.7.2",
}
TIMEOUT_PAGE_NAMES = (
    "page-affbb0cc-d616-481d-b493-80ed1ccb5a10.png",
    "newspaper_TheWashingtonPost-2025-01-08@magazinesclubnew_page_042.png",
)


class BenchmarkGateError(RuntimeError):
    """An execution invariant required for trustworthy measurement failed."""


def validate_benchmark_config(config: Any) -> None:
    if config.device != "cuda":
        raise BenchmarkGateError(f"E2E benchmark requires device: cuda; config resolved to {config.device!r}")
    if config.limits.max_runtime_seconds != 300:
        raise BenchmarkGateError("E2E benchmark requires the existing 300-second max_runtime_seconds policy")
    if config.limits.max_image_pixels != 40_000_000:
        raise BenchmarkGateError("E2E benchmark config does not match the frozen 40M-pixel production eligibility policy")


def manifest_identity(path: Path) -> tuple[str, dict[str, Any], list[dict[str, Any]]]:
    raw = path.read_bytes()
    value = json.loads(raw)
    samples = value.get("subset", {}).get("samples")
    if not isinstance(samples, list) or not samples:
        raise BenchmarkGateError("frozen manifest has no selected samples")
    ids = [entry.get("page_id") for entry in samples]
    if any(not isinstance(page_id, str) for page_id in ids) or len(ids) != len(set(ids)):
        raise BenchmarkGateError("frozen manifest page IDs are missing or duplicated")
    return hashlib.sha256(raw).hexdigest(), value, samples


def deterministic_ids(determinism_path: Path, manifest_samples: list[dict[str, Any]], manifest_sha256: str) -> list[str]:
    plan = json.loads(determinism_path.read_text(encoding="utf-8"))
    if plan.get("status") != "NOT_RUN":
        raise BenchmarkGateError("determinism selection artifact is not a frozen NOT_RUN plan")
    if plan.get("manifest_sha256") != manifest_sha256:
        raise BenchmarkGateError("determinism page selection targets a different manifest")
    selected = plan.get("selected_page_ids")
    allowed = {entry["page_id"] for entry in manifest_samples}
    if not isinstance(selected, list) or len(selected) != 10 or len(set(selected)) != 10:
        raise BenchmarkGateError("determinism plan must contain exactly ten unique page IDs")
    if not set(selected) <= allowed:
        raise BenchmarkGateError("determinism plan contains a page outside representative-v2")
    return selected


def resolve_named_pages(samples: list[dict[str, Any]], names: tuple[str, ...] = TIMEOUT_PAGE_NAMES) -> list[str]:
    by_name: dict[str, list[str]] = {}
    for sample in samples:
        by_name.setdefault(sample.get("image_name", ""), []).append(sample["page_id"])
    result = []
    for name in names:
        matches = by_name.get(name, [])
        if len(matches) != 1:
            raise BenchmarkGateError(f"expected exactly one frozen manifest page named {name!r}; found {len(matches)}")
        result.append(matches[0])
    return result


def failure_kind(record: dict[str, Any]) -> str:
    details = " ".join(str(value) for value in [record.get("error", ""), *record.get("errors", [])])
    if "max_runtime_seconds" in details or record.get("backend_timings", {}).get("timeout") == "max_runtime_seconds":
        return "timeout"
    if record.get("status") in {"failed", "error"}:
        return "failure"
    return "completed"


def validate_phase_timing_records(runtime: dict[str, Any]) -> dict[str, Any]:
    required_success_phases = {
        "parent_model_artifact_attestation_seconds",
        "worker_startup_seconds",
        "model_initialization_seconds",
        "model_weight_attestation_seconds",
        "input_hash_seconds",
        "pipeline_predict_seconds",
        "result_json_decode_seconds",
        "table_parsing_seconds",
        "canonical_mapping_inclusive_seconds",
        "canonical_page_serialization_seconds",
        "worker_accounted_seconds",
        "parent_request_elapsed_seconds",
        "parent_canonical_validation_seconds",
        "parent_run_metadata_attestation_seconds",
        "worker_lifecycle_state",
        "worker_cleanup_status",
    }
    missing: dict[str, list[str]] = {}
    timeout_cleanup_failures = []
    pages = runtime.get("per_page", [])
    for record in pages:
        timings = record.get("backend_timings")
        if failure_kind(record) == "timeout":
            if not isinstance(timings, dict) or not (
                isinstance(timings.get("worker_termination_and_cleanup_seconds"), (int, float))
                and timings.get("worker_termination_verified") is True
                and timings.get("scratch_cleanup_verified") is True
            ):
                timeout_cleanup_failures.append(record.get("page_id", "unknown"))
            continue
        if record.get("status") not in {"success", "success_with_warnings"}:
            continue
        missing_fields = sorted(
            key for key in required_success_phases - {"worker_lifecycle_state", "worker_cleanup_status"}
            if not isinstance(timings, dict)
            or not isinstance(timings.get(key), (int, float))
            or timings[key] < 0
        )
        if not isinstance(timings, dict) or timings.get("worker_lifecycle_state") != "completed":
            missing_fields.append("worker_lifecycle_state")
        if not isinstance(timings, dict) or timings.get("worker_cleanup_status") != "persistent_worker_reused":
            missing_fields.append("worker_cleanup_status")
        if missing_fields:
            missing[record.get("page_id", "unknown")] = missing_fields
    return {
        "successful_pages_checked": sum(
            record.get("status") in {"success", "success_with_warnings"} for record in pages
        ),
        "pages_with_missing_timing_fields": missing,
        "timeout_cleanup_failures": timeout_cleanup_failures,
        "complete": not missing and not timeout_cleanup_failures,
        "required_success_fields": sorted(required_success_phases),
        "timeout_phases": "worker-local phases are unavailable after forced termination; parent timeout/cleanup timing is retained",
    }


def validate_model_identity(preflight_versions: dict[str, str], run_versions: dict[str, str]) -> None:
    expected = {key: value for key, value in preflight_versions.items() if key != "doc_extraction"}
    actual = {key: value for key, value in run_versions.items() if key != "doc_extraction"}
    if not expected.get("model_weights_sha256") or not expected.get("layout_weights_sha256"):
        raise BenchmarkGateError("preflight did not pin both E2E model and layout weight hashes")
    if actual != expected:
        raise BenchmarkGateError("model/package/version/weight identity changed between preflight and extraction run")


def coverage_report(expected_page_ids: list[str], runtime: dict[str, Any], predictions_dir: Path) -> dict[str, Any]:
    pages = runtime.get("per_page")
    if not isinstance(pages, list):
        raise BenchmarkGateError("runtime report has no per_page records")
    attempted = [str(page.get("page_id")) for page in pages]
    expected = set(expected_page_ids)
    actual = set(attempted)
    files = sorted(path.name for path in predictions_dir.glob("*.md") if path.is_file()) if predictions_dir.is_dir() else []
    prediction_names = [Path(page_id.rsplit("#", 1)[0]).with_suffix(".md").name for page_id in expected_page_ids]
    expected_predictions = set(prediction_names)
    actual_predictions = set(files)
    missing_pages = sorted(expected - actual)
    unexpected_pages = sorted(actual - expected)
    failed = [page for page in pages if failure_kind(page) != "completed"]
    timing = validate_phase_timing_records(runtime)
    return {
        "expected": len(expected_page_ids),
        "attempted": len(pages),
        "completed": len(pages) - len(failed),
        "failed": len(failed),
        "timeouts": sum(failure_kind(page) == "timeout" for page in failed),
        "non_timeout_failures": sum(failure_kind(page) == "failure" for page in failed),
        "missing_page_attempts": missing_pages,
        "unexpected_page_attempts": unexpected_pages,
        "duplicate_page_attempts": sorted(page_id for page_id in set(attempted) if attempted.count(page_id) > 1),
        "missing_predictions": sorted(expected_predictions - actual_predictions),
        "unexpected_predictions": sorted(actual_predictions - expected_predictions),
        "prediction_coverage": len(actual_predictions & expected_predictions),
        "exact_attempt_coverage": attempted == expected_page_ids and len(set(attempted)) == len(attempted),
        "exact_prediction_coverage": actual_predictions == expected_predictions and len(files) == len(expected_predictions),
        "valid_for_quality_evaluation": (
            attempted == expected_page_ids
            and len(set(attempted)) == len(attempted)
            and not failed
            and actual_predictions == expected_predictions
            and len(files) == len(expected_predictions)
            and timing["complete"]
        ),
        "phase_timing": timing,
    }


def timeout_isolated_safely(coverage: dict[str, Any]) -> bool:
    return (
        coverage.get("timeouts", 0) > 0
        and coverage.get("timeouts") == coverage.get("failed")
        and coverage.get("non_timeout_failures") == 0
        and coverage.get("exact_attempt_coverage") is True
        and not coverage.get("phase_timing", {}).get("timeout_cleanup_failures")
    )


def run_outcome_by_page(run_dir: Path) -> dict[str, dict[str, Any]]:
    runtime = json.loads((run_dir / "runtime.json").read_text(encoding="utf-8"))
    return {
        record["page_id"]: {
            "status": record.get("status"),
            "failure_kind": failure_kind(record),
            "runtime_seconds": record.get("runtime_seconds"),
        }
        for record in runtime.get("per_page", [])
    }


def stable_document_content(document: dict[str, Any]) -> dict[str, Any]:
    """Stable canonical content, excluding only timestamp/runtime/path fields."""
    metadata = document.get("metadata")
    metadata_fields = (
        "status", "warnings", "errors", "route", "pipeline", "backend", "file_hash_sha256",
        "file_type", "device", "model_versions", "route_reason", "text_profile",
    )
    stable_metadata = (
        {key: metadata.get(key) for key in metadata_fields if key in metadata}
        if isinstance(metadata, dict)
        else None
    )
    return {"metadata": stable_metadata, "pages": document.get("pages")}


def compare_run_outputs(first_run: Path, second_run: Path, expected_page_ids: list[str]) -> dict[str, Any]:
    def collect(run: Path) -> dict[str, tuple[dict[str, Any], bytes]]:
        metadata = json.loads((run / "run_metadata.json").read_text(encoding="utf-8"))
        by_id = {entry["page_id"]: entry for entry in metadata.get("sample_ids", [])}
        if set(by_id) != set(expected_page_ids):
            raise BenchmarkGateError(f"determinism run {run} does not contain the exact requested sample identities")
        results = {}
        for page_id in expected_page_ids:
            document_id = by_id[page_id].get("document_id")
            if not document_id:
                # Older runner metadata can omit this field; final document ID
                # is also the deterministic input-derived directory basename.
                raise BenchmarkGateError(f"run metadata has no document_id for {page_id}")
            document_path = run / "_doc_extraction_runs" / document_id / "final" / "document.json"
            if not document_path.is_file():
                raise BenchmarkGateError(f"kept canonical document is missing for {page_id}: {document_path}")
            doc = json.loads(document_path.read_text(encoding="utf-8"))
            entry = by_id[page_id]
            prediction_path = run / metadata["prediction_directory"] / Path(entry["image_name"]).with_suffix(".md").name
            results[page_id] = (stable_document_content(doc), prediction_path.read_bytes())
        return results

    left, right = collect(first_run), collect(second_run)
    canonical_differences = []
    markdown_differences = []
    for page_id in expected_page_ids:
        if left[page_id][0] != right[page_id][0]:
            canonical_differences.append(page_id)
        if left[page_id][1] != right[page_id][1]:
            markdown_differences.append(page_id)
    return {
        "page_count": len(expected_page_ids),
        "canonical_page_content_identical": not canonical_differences,
        "serialized_markdown_identical": not markdown_differences,
        "canonical_differing_page_ids": canonical_differences,
        "markdown_differing_page_ids": markdown_differences,
        "comparison_scope": [
            "canonical Document stable metadata (status, warnings/errors, route, backend, provenance and model versions)",
            "canonical pages (including IDs, order, reading order, text, tables, formulas, geometry, and page diagnostics)",
            "serialized Markdown bytes",
        ],
        "intentionally_ignored": ["document timestamp", "document runtime", "run directory", "worker process identity"],
        "not_compared": ["raw PaddleOCR-VL native result; the worker does not persist it"],
    }


def inspect_single_page_output(run_dir: Path, page_id: str) -> dict[str, Any]:
    """Capture bounded structural/text-presence facts for the timing page."""
    metadata = json.loads((run_dir / "run_metadata.json").read_text(encoding="utf-8"))
    runtime = json.loads((run_dir / "runtime.json").read_text(encoding="utf-8"))
    entries = [item for item in metadata.get("sample_ids", []) if item.get("page_id") == page_id]
    outcomes = [item for item in runtime.get("per_page", []) if item.get("page_id") == page_id]
    if len(entries) != 1 or len(outcomes) != 1:
        raise BenchmarkGateError("timing diagnostic must have exactly one matching input and runtime record")
    document_id = entries[0].get("document_id")
    if not document_id:
        raise BenchmarkGateError("timing diagnostic has no persisted canonical document identity")
    document_path = run_dir / "_doc_extraction_runs" / document_id / "final" / "document.json"
    if not document_path.is_file():
        raise BenchmarkGateError("timing diagnostic canonical Document was not retained")
    document = json.loads(document_path.read_text(encoding="utf-8"))
    pages = document.get("pages")
    if not isinstance(pages, list) or len(pages) != 1 or not isinstance(pages[0], dict):
        raise BenchmarkGateError("timing diagnostic did not produce one structurally valid canonical page")
    page = pages[0]
    elements = page.get("elements")
    tables = page.get("tables")
    reading_order = page.get("reading_order")
    if not isinstance(elements, list) or not isinstance(tables, list) or not isinstance(reading_order, list):
        raise BenchmarkGateError("timing diagnostic canonical page lacks elements/tables/reading_order arrays")
    element_ids = [item.get("id") for item in elements if isinstance(item, dict)]
    if len(element_ids) != len(elements) or len(element_ids) != len(set(element_ids)):
        raise BenchmarkGateError("timing diagnostic canonical elements are malformed or have duplicate IDs")
    prediction_path = run_dir / metadata["prediction_directory"] / Path(entries[0]["image_name"]).with_suffix(".md").name
    prediction_bytes = prediction_path.read_bytes()
    prediction_bytes.decode("utf-8")
    formula_count = sum(
        isinstance(item, dict) and str(item.get("type", "")).lower() in {"formula", "display_formula"}
        for item in elements
    )
    warnings = document.get("metadata", {}).get("warnings", [])
    errors = document.get("metadata", {}).get("errors", [])
    runtime_record = outcomes[0]
    return {
        "page_id": page_id,
        "status": runtime_record.get("status"),
        "runtime_seconds": runtime_record.get("runtime_seconds"),
        "canonical_document_valid": True,
        "canonical_page_count": len(pages),
        "element_count": len(elements),
        "text_bearing_element_count": sum(bool(item.get("text")) for item in elements if isinstance(item, dict)),
        "table_count": len(tables),
        "formula_element_count": formula_count,
        "reading_order_reference_count": len(reading_order),
        "warnings": warnings,
        "errors": errors,
        "runtime_warnings": runtime_record.get("warnings", []),
        "prediction_utf8_valid": True,
        "prediction_bytes": len(prediction_bytes),
        "prediction_sha256": hashlib.sha256(prediction_bytes).hexdigest(),
        "backend_timings": runtime_record.get("backend_timings", {}),
    }


def compare_official_metric_outputs(first_run: Path, second_run: Path) -> dict[str, Any]:
    def collect(run: Path) -> dict[str, Any]:
        metadata = json.loads((run / "run_metadata.json").read_text(encoding="utf-8"))
        prefix = metadata["prediction_directory"]
        files = sorted(run.glob(f"{prefix}_quick_match_*_per_page_edit.json"))
        files += sorted(run.glob(f"{prefix}_quick_match_*_per_table_TEDS.json"))
        if not files:
            raise BenchmarkGateError(f"official per-page evaluator artifacts are absent from {run}")
        return {path.name.removeprefix(prefix + "_quick_match_"): json.loads(path.read_text(encoding="utf-8"))
                for path in files}

    left, right = collect(first_run), collect(second_run)
    keys = sorted(set(left) | set(right))
    differing = [key for key in keys if left.get(key) != right.get(key)]
    return {
        "identical": not differing,
        "metric_files_compared": keys,
        "missing_from_first": sorted(set(right) - set(left)),
        "missing_from_second": sorted(set(left) - set(right)),
        "differing_metric_files": differing,
    }


def verify_run_binding(run_dir: Path, manifest_path: Path, expected_page_ids: list[str]) -> dict[str, Any]:
    metadata_path, runtime_path = run_dir / "run_metadata.json", run_dir / "runtime.json"
    if not metadata_path.is_file() or not runtime_path.is_file():
        raise BenchmarkGateError(f"run metadata/runtime missing in {run_dir}")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
    manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    if metadata.get("sample_manifest_sha256") != manifest_hash:
        raise BenchmarkGateError(f"run {run_dir} used a different frozen manifest file")
    copied_manifest = run_dir / "sample_manifest.json"
    if not copied_manifest.is_file() or hashlib.sha256(copied_manifest.read_bytes()).hexdigest() != manifest_hash:
        raise BenchmarkGateError(f"run {run_dir} did not preserve the exact frozen manifest bytes")
    manifest = json.loads(copied_manifest.read_text(encoding="utf-8"))
    if metadata.get("run_attestation_version") != 1:
        raise BenchmarkGateError(f"run {run_dir} predates the strict E2E run-attestation format")
    if manifest.get("subset_identity", {}).get("sha256") != metadata.get("sample_manifest_identity"):
        raise BenchmarkGateError(f"run {run_dir} manifest identity differs from run metadata")
    if metadata.get("upstream_commit") != odb.PINNED_UPSTREAM_COMMIT:
        raise BenchmarkGateError(f"run {run_dir} has an unsupported evaluator revision")
    if len(str(metadata.get("config_sha256", ""))) != 64:
        raise BenchmarkGateError(f"run {run_dir} config hash is missing or malformed")
    source_attestation = metadata.get("source_attestation", {})
    if not source_attestation.get("source_snapshot_sha256") or not isinstance(source_attestation.get("working_tree_status"), list):
        raise BenchmarkGateError(f"run {run_dir} source snapshot/working-tree status is incomplete")
    for filename in ("source_attestation.json", "runtime_attestation.json", "pre_run_model_versions.json"):
        if not (run_dir / filename).is_file():
            raise BenchmarkGateError(f"run {run_dir} lacks required attestation artifact {filename}")
    manifest_by_id = {entry["page_id"]: entry for entry in manifest["subset"]["samples"]}
    actual_ids = metadata.get("selected_page_ids")
    if actual_ids != expected_page_ids:
        raise BenchmarkGateError(f"run {run_dir} selected page IDs differ from the frozen requested order")
    if not set(expected_page_ids) <= set(manifest_by_id):
        raise BenchmarkGateError(f"run {run_dir} includes a page outside the frozen manifest")
    metadata_samples = metadata.get("sample_ids", [])
    if [entry.get("page_id") for entry in metadata_samples] != expected_page_ids:
        raise BenchmarkGateError(f"run {run_dir} per-sample metadata does not match selected page IDs")
    for entry in metadata_samples:
        if entry.get("image_sha256") != manifest_by_id[entry["page_id"]].get("image_sha256"):
            raise BenchmarkGateError(f"run {run_dir} input image identity differs for {entry['page_id']}")
    ground_truth_path = run_dir / "ground_truth_subset.json"
    if not ground_truth_path.is_file():
        raise BenchmarkGateError(f"run {run_dir} has no run-scoped ground truth")
    ground_truth_bytes = ground_truth_path.read_bytes()
    if hashlib.sha256(ground_truth_bytes).hexdigest() != metadata.get("ground_truth_subset_sha256"):
        raise BenchmarkGateError(f"run {run_dir} ground-truth hash differs from run metadata")
    ground_truth_rows = json.loads(ground_truth_bytes)
    gt_ids = [
        f"{Path(row['page_info']['image_path']).name}#{row['page_info'].get('page_no')}"
        for row in ground_truth_rows
    ]
    if gt_ids != expected_page_ids:
        raise BenchmarkGateError(f"run {run_dir} ground-truth page population/order differs from the requested pages")
    predictions_dir = run_dir / metadata.get("prediction_directory", "")
    coverage = coverage_report(expected_page_ids, runtime, predictions_dir)
    return {"metadata": metadata, "runtime": runtime, "coverage": coverage}


def gpu_preflight(config_path: Path, expected_gpu: str = "L4") -> dict[str, Any]:
    config = load_config(config_path)
    validate_benchmark_config(config)
    query = subprocess.run(
        ["nvidia-smi", "--query-gpu=name,memory.total,memory.free,driver_version", "--format=csv,noheader"],
        check=True, capture_output=True, text=True, timeout=10,
    ).stdout.strip().splitlines()
    if not query or not any(expected_gpu.lower() in row.lower() for row in query):
        raise BenchmarkGateError(f"expected GPU family {expected_gpu!r} not found in nvidia-smi inventory: {query}")
    processes = query_gpu_processes()
    if processes:
        raise BenchmarkGateError(f"GPU is occupied by an existing compute process; refusing benchmark: {processes}")
    try:
        import paddle
    except ImportError as exc:
        raise BenchmarkGateError("Paddle runtime is unavailable in the selected E2E Python environment") from exc
    if not paddle.is_compiled_with_cuda() or paddle.device.cuda.device_count() < 1:
        raise BenchmarkGateError("selected Paddle runtime has no usable CUDA device")
    paddle_gpu_name = paddle.device.cuda.get_device_name(0)
    if expected_gpu.lower() not in str(paddle_gpu_name).lower():
        raise BenchmarkGateError(f"Paddle CUDA device 0 is {paddle_gpu_name!r}, expected {expected_gpu!r}")
    if platform.python_version() != "3.12.14":
        raise BenchmarkGateError(f"E2E runtime Python pin mismatch: {platform.python_version()} != 3.12.14")
    versions = {}
    from importlib import metadata

    for package, expected in EXPECTED_RUNTIME_PACKAGES.items():
        try:
            actual = metadata.version(package)
        except metadata.PackageNotFoundError as exc:
            raise BenchmarkGateError(f"required package {package} is not installed") from exc
        versions[package] = actual
        if actual != expected:
            raise BenchmarkGateError(f"runtime package pin mismatch for {package}: {actual} != {expected}")
    cuda_version = getattr(getattr(paddle, "version", None), "cuda", None)
    cuda_version = cuda_version() if callable(cuda_version) else cuda_version
    if str(cuda_version) != "12.6":
        raise BenchmarkGateError(f"Paddle CUDA build mismatch: {cuda_version!r} != '12.6'")
    from doc_extraction.backends.paddleocr_vl_backend import PaddleOCRVLBackend

    model_versions = PaddleOCRVLBackend.model_versions()
    missing_hashes = [name for name in ("model_weights_sha256", "layout_weights_sha256") if not model_versions.get(name)]
    if missing_hashes:
        raise BenchmarkGateError(f"model cache identity preflight failed; missing hashes: {missing_hashes}")
    return {
        "python": platform.python_version(),
        "paddle": versions["paddlepaddle-gpu"],
        "paddle_cuda": str(cuda_version) if cuda_version else None,
        "packages": versions,
        "model_versions": model_versions,
        "device_name": str(paddle_gpu_name),
        "gpu_inventory": query,
        "gpu_processes": processes,
        "model_loaded": False,
        "model_weight_hashes_verified": True,
        "note": "cheap device/runtime check only; no model allocation and no calibrated minimum-free-memory threshold",
    }


def query_gpu_processes() -> list[str]:
    result = subprocess.run(
        ["nvidia-smi", "--query-compute-apps=pid,process_name,used_memory", "--format=csv,noheader"],
        check=True, capture_output=True, text=True, timeout=10,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def require_unoccupied_gpu() -> None:
    processes = query_gpu_processes()
    if processes:
        raise BenchmarkGateError(f"GPU acquired another compute process during benchmark; stopping without signaling it: {processes}")


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _run(command: list[str], *, allow_nonzero: bool = False) -> int:
    print("+", " ".join(command), flush=True)
    result = subprocess.run(command, cwd=ROOT, check=False)
    if result.returncode and not allow_nonzero:
        raise BenchmarkGateError(f"command failed ({result.returncode}): {command[0]}")
    return result.returncode


def _read_run_ids(run_dir: Path) -> list[str]:
    metadata = json.loads((run_dir / "run_metadata.json").read_text(encoding="utf-8"))
    return metadata.get("selected_page_ids", [])


def _write_execution_summary(output_root: Path, execution: dict[str, Any]) -> None:
    stages = execution.get("stages_completed", [])
    report = {
        "status": execution.get("status"),
        "failure": execution.get("failure"),
        "manifest_file_sha256": execution.get("manifest_file_sha256"),
        "subset_identity": execution.get("manifest_subset_identity"),
        "expected_pages": execution.get("expected_pages"),
        "evaluator_revision": execution.get("evaluator_revision"),
        "stages": [
            {"name": record.get("name"), "coverage": record.get("coverage"),
             "return_code": record.get("return_code"), "evaluation_status": record.get("evaluation_status")}
            for record in stages
        ],
    }
    (output_root / "execution_summary.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def _prepare_command(python: Path, dataset: Path, config: Path, manifest: Path, output: Path,
                     page_ids: list[str], keep_runs: bool) -> list[str]:
    command = [str(python), str(PREPARE), "--dataset", str(dataset), "--backend", "paddleocr_vl",
                "--output", str(output), "--config", str(config), "--manifest", str(manifest), "--page-ids", *page_ids]
    if keep_runs:
        command.append("--keep-runs")
    return command


def _evaluate_command(runtime_python: Path, evaluator_python: Path, evaluator_repo: Path,
                      dataset: Path, run_dir: Path) -> list[str]:
    return [str(runtime_python), str(EVALUATE), "--dataset", str(dataset), "--output", str(run_dir),
            "--ground-truth", str(run_dir / "ground_truth_subset.json"),
            "--omnidoc-repo", str(evaluator_repo), "--omnidoc-python", str(evaluator_python),
            "--match-method", "quick_match", "--match-workers", "1", "--teds-workers", "1",
            "--require-pinned-evaluator"]


def build_plan(manifest_path: Path, determinism_path: Path, run_root: Path, dataset: Path,
               config: Path, python: Path) -> list[dict[str, Any]]:
    manifest_sha, manifest, samples = manifest_identity(manifest_path)
    selected = [entry["page_id"] for entry in samples]
    det_ids = deterministic_ids(determinism_path, samples, manifest_sha)
    timeout_ids = resolve_named_pages(samples)
    timeout_id_set = set(timeout_ids)
    smoke_ids = [page_id for page_id in det_ids if page_id not in timeout_id_set][:5]
    if len(smoke_ids) != 5:
        raise BenchmarkGateError("frozen determinism selection cannot provide five non-timeout smoke pages")
    if len(selected) != manifest["subset"].get("actual_size"):
        raise BenchmarkGateError("manifest actual_size does not equal selected page count")
    stages = [
        {"name": "timing-diagnostic", "page_ids": [det_ids[2]], "repeat": 1, "keep_runs": True},
        *[{"name": f"timeout-diagnostic-{i + 1}", "page_ids": [page_id], "repeat": 1, "keep_runs": True}
          for i, page_id in enumerate(timeout_ids)],
        {"name": "determinism-a", "page_ids": det_ids, "repeat": 1, "keep_runs": True},
        {"name": "determinism-b", "page_ids": det_ids, "repeat": 1, "keep_runs": True},
        {"name": "smoke-5", "page_ids": smoke_ids, "repeat": 1, "keep_runs": True},
        {"name": "preflight-20", "page_ids": selected[:20], "repeat": 1, "keep_runs": False},
        {"name": "full-180", "page_ids": selected, "repeat": 1, "keep_runs": False},
    ]
    for index, stage in enumerate(stages):
        stage["output"] = str(run_root / f"{index + 1:02d}-{stage['name']}-{_timestamp()}")
        stage["command"] = _prepare_command(python, dataset, config, manifest_path,
                                             Path(stage["output"]), stage["page_ids"], stage["keep_runs"])
    return [{"manifest_sha256": manifest_sha, **stage} for stage in stages]


def _check_classic_run(classic_run: Path, dataset: Path, manifest_path: Path, expected_ids: list[str]) -> None:
    metadata_path = classic_run / "run_metadata.json"
    if not metadata_path.is_file():
        raise BenchmarkGateError(f"Classic comparison run metadata is missing: {classic_run}")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    expected_manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    if metadata.get("sample_manifest_sha256") != expected_manifest_sha:
        raise BenchmarkGateError("Classic run manifest file hash differs from the frozen current manifest")
    recorded_ids = metadata.get("selected_page_ids") or [entry.get("page_id") for entry in metadata.get("sample_ids", [])]
    if recorded_ids != expected_ids:
        raise BenchmarkGateError("Classic run page IDs/order differ from frozen representative-v2")
    if metadata.get("upstream_commit") != odb.PINNED_UPSTREAM_COMMIT:
        raise BenchmarkGateError("Classic run used a different OmniDocBench evaluator revision")
    classic_truth = json.loads((classic_run / "ground_truth_subset.json").read_text(encoding="utf-8"))
    classic_truth_ids = [
        f"{Path(row['page_info']['image_path']).name}#{row['page_info'].get('page_no')}"
        for row in classic_truth
    ]
    if classic_truth_ids != expected_ids:
        raise BenchmarkGateError("Classic run-scoped ground truth differs from frozen population/order")
    predictions = classic_run / metadata.get("prediction_directory", "")
    samples = odb.load_dataset(dataset, classic_run / "ground_truth_subset.json")[1]
    odb.validate_prediction_alignment(samples, predictions)
    if not (classic_run / "metrics.json").is_file() or not (classic_run / "run_summary.json").is_file():
        raise BenchmarkGateError("Classic comparison run lacks official metrics/run summary")


METRIC_SPECS = {
    "text_edit_distance": ("text_block", "Edit_dist", "lower", "text_block_per_page_edit.json"),
    "table_edit_distance": ("table", "Edit_dist", "lower", "table_per_page_edit.json"),
    "table_teds": ("table", "TEDS", "higher", "table_per_table_TEDS.json"),
    "table_structure_teds": ("table", "TEDS_structure_only", "higher", "table_per_table_TEDS.json"),
    "reading_order_edit_distance": ("reading_order", "Edit_dist", "lower", "reading_order_per_page_edit.json"),
    "formula_edit_distance": ("display_formula", "Edit_dist", "lower", "display_formula_per_page_edit.json"),
}


def build_paired_report(classic_run: Path, e2e_run: Path, expected_ids: list[str], output_dir: Path) -> dict[str, Any]:
    import yaml

    def load_bundle(run: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, dict[str, float]]]:
        metrics = json.loads((run / "metrics.json").read_text(encoding="utf-8"))
        summary = json.loads((run / "run_summary.json").read_text(encoding="utf-8"))
        metadata = json.loads((run / "run_metadata.json").read_text(encoding="utf-8"))
        eval_config = yaml.safe_load((run / "evaluator_config.yaml").read_text(encoding="utf-8"))
        try:
            settings = eval_config["end2end_eval"]
            dataset = settings["dataset"]
            matching = dataset["match_method"], dataset["match_workers"]
            metric_config = settings["metrics"]
        except (KeyError, TypeError) as exc:
            raise BenchmarkGateError(f"invalid evaluator config in {run}") from exc
        maps = {}
        prediction_dir = metadata["prediction_directory"]
        for key, (_, field, _, suffix) in METRIC_SPECS.items():
            matches = list(run.glob(f"{prediction_dir}_quick_match_{suffix}"))
            if len(matches) != 1:
                raise BenchmarkGateError(f"expected one official {suffix} output in {run}, got {len(matches)}")
            raw = json.loads(matches[0].read_text(encoding="utf-8"))
            maps[key] = {
                str(identity): float(value if isinstance(value, (int, float)) else value[field])
                for identity, value in raw.items()
            }
        return {"metrics": metrics, "summary": summary, "metadata": metadata,
                "evaluator_settings": {"matching": matching, "metric_config": metric_config}}, maps

    classic, classic_maps = load_bundle(classic_run)
    e2e, e2e_maps = load_bundle(e2e_run)
    if classic["metadata"].get("upstream_commit") != e2e["metadata"].get("upstream_commit"):
        raise BenchmarkGateError("Classic/E2E run metadata evaluator revisions differ")
    if classic["evaluator_settings"] != e2e["evaluator_settings"]:
        raise BenchmarkGateError("Classic/E2E evaluator match/metric configuration differs")
    if classic["summary"].get("page_denominators") != e2e["summary"].get("page_denominators"):
        raise BenchmarkGateError("Classic/E2E official page metric denominators differ")

    per_metric: dict[str, Any] = {}
    for key, (group, field, direction, _) in METRIC_SPECS.items():
        c_map, e_map = classic_maps[key], e2e_maps[key]
        if set(c_map) != set(e_map):
            raise BenchmarkGateError(f"Classic/E2E {key} per-instance keys differ")
        c_value = classic["metrics"][group]["page"][field]["ALL"]
        e_value = e2e["metrics"][group]["page"][field]["ALL"]
        denominator = classic["summary"].get("page_denominators", {}).get(group, {}).get(field, {}).get("ALL")
        deltas = {identity: e_map[identity] - c_map[identity] for identity in sorted(c_map)}
        better = (lambda delta: delta < 0) if direction == "lower" else (lambda delta: delta > 0)
        per_metric[key] = {
            "classic": c_value, "e2e": e_value, "delta_e2e_minus_classic": e_value - c_value,
            "n": denominator, "per_page_or_instance_n": len(deltas), "direction": direction,
            "e2e_better_count": sum(better(value) for value in deltas.values()),
            "classic_better_count": sum(not better(value) and value != 0 for value in deltas.values()),
            "tie_count": sum(value == 0 for value in deltas.values()),
            "paired_deltas": deltas,
        }
    classic_ids = [entry["page_id"] for entry in classic["metadata"]["sample_ids"]]
    e2e_ids = [entry["page_id"] for entry in e2e["metadata"]["sample_ids"]]
    report = {
        "schema": "internal-e2e-classic-paired-v3",
        "status": "MEASURED",
        "manifest_identity": classic["metadata"].get("sample_manifest_identity"),
        "evaluator_revision": classic["metadata"].get("upstream_commit"),
        "expected_page_ids": expected_ids,
        "classic_page_ids": classic_ids,
        "e2e_page_ids": e2e_ids,
        "common_pages": sorted(set(classic_ids) & set(e2e_ids)),
        "classic_only_pages": sorted(set(classic_ids) - set(e2e_ids)),
        "e2e_only_pages": sorted(set(e2e_ids) - set(classic_ids)),
        "failures": {"classic": classic["summary"].get("failed", []), "e2e": e2e["summary"].get("failed", [])},
        "runtime": {
            "classic": {key: json.loads((classic_run / "runtime.json").read_text()).get(key)
                        for key in ("total_runtime_seconds", "mean_seconds_per_page", "median_seconds_per_page",
                                    "p95_seconds_per_page", "failed", "warning_rate")},
            "e2e": {key: json.loads((e2e_run / "runtime.json").read_text()).get(key)
                    for key in ("total_runtime_seconds", "mean_seconds_per_page", "median_seconds_per_page",
                                "p95_seconds_per_page", "failed", "warning_rate")},
        },
        "metrics": per_metric,
        "note": "Aggregate and paired official evaluator outputs only; no composite score.",
    }
    if classic_ids != expected_ids or e2e_ids != expected_ids:
        raise BenchmarkGateError("paired runs do not both cover the exact frozen ordered page population")
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "classic-vs-e2e-v3.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    lines = ["# Classic vs E2E — representative-v2", "",
             f"Paired pages: {len(report['common_pages'])}/{len(expected_ids)}; evaluator: `{report['evaluator_revision']}`.",
             "", "| Metric | Classic | E2E | Delta | N | Direction |", "|---|---:|---:|---:|---:|---|"]
    for key, metric in per_metric.items():
        lines.append(f"| {key} | {metric['classic']} | {metric['e2e']} | {metric['delta_e2e_minus_classic']} | {metric['n']} | {metric['direction']} |")
    (output_dir / "classic-vs-e2e-v3.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def execute(args: argparse.Namespace) -> int:
    for attribute in ("manifest", "determinism_plan", "dataset", "config", "evaluator_repo",
                      "classic_run", "output_root"):
        value = getattr(args, attribute)
        if not value.is_absolute():
            setattr(args, attribute, (ROOT / value).resolve())
    # Venv interpreters are commonly symlinks. Preserve the lexical path so
    # exec uses the venv site-packages instead of resolving to its base Python.
    args.runtime_python = Path(os.path.abspath(args.runtime_python))
    args.evaluator_python = Path(os.path.abspath(args.evaluator_python))
    manifest_sha, manifest, samples = manifest_identity(args.manifest)
    selected_ids = [entry["page_id"] for entry in samples]
    if len(selected_ids) != manifest["subset"].get("actual_size"):
        raise BenchmarkGateError("manifest actual_size does not equal selected page count")
    if args.expected_pages is not None and len(selected_ids) != args.expected_pages:
        raise BenchmarkGateError(f"expected {args.expected_pages} frozen pages, manifest contains {len(selected_ids)}")
    # Rehash every referenced input and the entire dataset inventory before any
    # model process is started; the manifest is a gate, not a hint.
    selected_indices, _, verified = verify_manifest(args.dataset, args.manifest)
    if verified["subset_identity"]["sha256"] != manifest["subset_identity"]["sha256"] or len(selected_indices) != len(selected_ids):
        raise BenchmarkGateError("dataset verification returned a different frozen selection")
    _check_classic_run(args.classic_run, args.dataset, args.manifest, selected_ids)
    preflight = subprocess.run(
        [str(args.runtime_python), str(Path(__file__).resolve()), "--gpu-preflight-only", "--config", str(args.config)],
        cwd=ROOT, check=False, capture_output=True, text=True, timeout=60,
    )
    if preflight.returncode != 0:
        raise BenchmarkGateError(f"GPU/runtime preflight failed: {preflight.stderr.strip() or preflight.stdout.strip()}")
    gpu_record = json.loads(preflight.stdout)
    plan = build_plan(args.manifest, args.determinism_plan, args.output_root, args.dataset, args.config, args.runtime_python)
    args.output_root.mkdir(parents=True, exist_ok=False)
    run_manifest = {
        "schema": "internal-e2e-gpu-execution-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "manifest_path": str(args.manifest.relative_to(ROOT)),
        "manifest_file_sha256": manifest_sha,
        "manifest_subset_identity": manifest["subset_identity"]["sha256"],
        "dataset_identity": manifest.get("dataset_identity"),
        "expected_pages": len(selected_ids),
        "page_ids": selected_ids,
        "dataset": str(args.dataset.relative_to(ROOT) if args.dataset.is_relative_to(ROOT) else args.dataset),
        "config": str(args.config.relative_to(ROOT) if args.config.is_relative_to(ROOT) else args.config),
        "config_sha256": hashlib.sha256(args.config.read_bytes()).hexdigest(),
        "runtime_python": str(args.runtime_python),
        "evaluator_repo": str(args.evaluator_repo.relative_to(ROOT) if args.evaluator_repo.is_relative_to(ROOT) else args.evaluator_repo),
        "evaluator_revision": odb.PINNED_UPSTREAM_COMMIT,
        "gpu_preflight": gpu_record,
        "classic_run": str(args.classic_run.relative_to(ROOT) if args.classic_run.is_relative_to(ROOT) else args.classic_run),
        "stages": [{key: value for key, value in stage.items() if key != "command"} for stage in plan],
        "status": "running",
    }
    args.evaluator_repo = args.evaluator_repo.resolve()
    evaluator_revision = subprocess.run(["git", "-C", str(args.evaluator_repo), "rev-parse", "HEAD"],
                                        check=True, capture_output=True, text=True, timeout=10).stdout.strip()
    if evaluator_revision != odb.PINNED_UPSTREAM_COMMIT:
        raise BenchmarkGateError(f"evaluator checkout mismatch: {evaluator_revision}")
    (args.output_root / "execution_manifest.json").write_text(json.dumps(run_manifest, indent=2) + "\n")
    stage_records = []
    runtime_python = args.runtime_python
    dataset = args.dataset.resolve()
    config = args.config.resolve()
    manifest_path = args.manifest.resolve()
    for stage in plan:
        # Do not contend with workloads that appeared after the initial
        # preflight. This is an observation gate only; never signal processes.
        require_unoccupied_gpu()
        output = Path(stage["output"])
        run_manifest["current_stage"] = stage["name"]
        (args.output_root / "execution_manifest.json").write_text(json.dumps(run_manifest, indent=2) + "\n")
        command = _prepare_command(runtime_python, dataset, config, manifest_path, output,
                                  stage["page_ids"], stage["keep_runs"])
        return_code = _run(command, allow_nonzero=True)
        if not (output / "run_metadata.json").is_file() or not (output / "runtime.json").is_file():
            raise BenchmarkGateError(f"stage {stage['name']} terminated without run metadata")
        binding = verify_run_binding(output, manifest_path, stage["page_ids"])
        record = {"name": stage["name"], "run_dir": str(output), "return_code": return_code,
                  "coverage": binding["coverage"], "runtime": binding["runtime"]}
        try:
            validate_model_identity(gpu_record["model_versions"], binding["metadata"].get("pre_run_model_versions", {}))
        except BenchmarkGateError as exc:
            raise BenchmarkGateError(f"stage {stage['name']}: {exc}") from exc
        stage_records.append(record)
        run_manifest["stages_completed"] = stage_records
        (args.output_root / "execution_manifest.json").write_text(json.dumps(run_manifest, indent=2) + "\n")
        if stage["name"] == "smoke-5" and not binding["coverage"]["valid_for_quality_evaluation"]:
            raise BenchmarkGateError(f"{stage['name']} did not produce complete successful coverage")
        if stage["name"] == "timing-diagnostic" and not (
            binding["coverage"]["valid_for_quality_evaluation"]
            or timeout_isolated_safely(binding["coverage"])
        ):
            raise BenchmarkGateError("timing diagnostic failed without verified, safe timeout cleanup")
        if stage["name"] == "timing-diagnostic" and binding["coverage"]["valid_for_quality_evaluation"]:
            timing_page = inspect_single_page_output(output, stage["page_ids"][0])
            record["timing_page_inspection"] = timing_page
            (args.output_root / "timing-page-inspection.json").write_text(json.dumps(timing_page, indent=2) + "\n")
        if stage["name"].startswith("timeout-diagnostic-") and not (
            binding["coverage"]["valid_for_quality_evaluation"]
            or timeout_isolated_safely(binding["coverage"])
        ):
            raise BenchmarkGateError(f"{stage['name']} failed without verified, safe timeout cleanup")
        if stage["name"] == "timeout-diagnostic-2":
            timeout_records = [
                {
                    "page_id": item["runtime"].get("per_page", [{}])[0].get("page_id"),
                    "status": item["runtime"].get("per_page", [{}])[0].get("status"),
                    "failure_kind": failure_kind(item["runtime"].get("per_page", [{}])[0]),
                    "runtime_seconds": item["runtime"].get("per_page", [{}])[0].get("runtime_seconds"),
                    "backend_timings": item["runtime"].get("per_page", [{}])[0].get("backend_timings"),
                }
                for item in stage_records if item["name"].startswith("timeout-diagnostic-")
            ]
            timeout_analysis = {
                "status": "OBSERVED_PROFILES_RECORDED",
                "causal_conclusion": "NOT_ESTABLISHED_BY_RUNNER",
                "pages": timeout_records,
                "note": "Compare measured phases; do not infer a cause from timeout status alone.",
            }
            run_manifest["timeout_analysis"] = timeout_analysis
            (args.output_root / "timeout-analysis.json").write_text(json.dumps(timeout_analysis, indent=2) + "\n")
        if stage["name"] == "determinism-a":
            run_manifest["determinism_run_a"] = str(output)
            if binding["coverage"]["valid_for_quality_evaluation"]:
                record["evaluation_status"] = "running"
                (args.output_root / "execution_manifest.json").write_text(json.dumps(run_manifest, indent=2) + "\n")
                _run(_evaluate_command(runtime_python, args.evaluator_python, args.evaluator_repo,
                                       dataset, output))
                record["evaluation_status"] = "complete_exact_subset"
            elif not timeout_isolated_safely(binding["coverage"]):
                raise BenchmarkGateError("first determinism run failed without verified timeout-only cleanup")
        elif stage["name"] == "determinism-b":
            first_run = Path(run_manifest["determinism_run_a"])
            first_record = next(item for item in stage_records if item["name"] == "determinism-a")
            first_complete = first_record["coverage"]["valid_for_quality_evaluation"]
            second_complete = binding["coverage"]["valid_for_quality_evaluation"]
            if second_complete:
                record["evaluation_status"] = "running"
                (args.output_root / "execution_manifest.json").write_text(json.dumps(run_manifest, indent=2) + "\n")
                _run(_evaluate_command(runtime_python, args.evaluator_python, args.evaluator_repo,
                                       dataset, output))
                record["evaluation_status"] = "complete_exact_subset"
            elif not timeout_isolated_safely(binding["coverage"]):
                raise BenchmarkGateError("second determinism run failed without verified timeout-only cleanup")
            if first_complete and second_complete:
                comparison = compare_run_outputs(first_run, output, stage["page_ids"])
                metrics_a = json.loads((first_run / "metrics.json").read_text())
                metrics_b = json.loads((output / "metrics.json").read_text())
                comparison["official_aggregate_metrics_identical"] = metrics_a == metrics_b
                comparison["official_aggregate_metrics_a_sha256"] = hashlib.sha256(
                    json.dumps(metrics_a, sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest()
                comparison["official_aggregate_metrics_b_sha256"] = hashlib.sha256(
                    json.dumps(metrics_b, sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest()
                comparison["official_per_page_metrics"] = compare_official_metric_outputs(first_run, output)
            else:
                comparison = {
                    "status": "NOT_COMPARABLE_INCOMPLETE_COVERAGE",
                    "page_count": len(stage["page_ids"]),
                    "run_a": run_outcome_by_page(first_run),
                    "run_b": run_outcome_by_page(output),
                    "official_metrics": "not run because at least one prediction set is incomplete",
                }
            record["determinism"] = comparison
            (args.output_root / "determinism.json").write_text(json.dumps(comparison, indent=2) + "\n")
        elif stage["name"] == "preflight-20" and not binding["coverage"]["valid_for_quality_evaluation"]:
            run_manifest.update({"status": "stopped_at_preflight", "stages_completed": stage_records})
            (args.output_root / "execution_manifest.json").write_text(json.dumps(run_manifest, indent=2) + "\n")
            _write_execution_summary(args.output_root, run_manifest)
            return 1
        elif stage["name"] == "preflight-20":
            record["evaluation_status"] = "running"
            (args.output_root / "execution_manifest.json").write_text(json.dumps(run_manifest, indent=2) + "\n")
            _run(_evaluate_command(runtime_python, args.evaluator_python, args.evaluator_repo,
                                   dataset, output))
            record["evaluation_status"] = "complete_exact_subset"
        elif stage["name"] == "full-180":
            if not binding["coverage"]["valid_for_quality_evaluation"]:
                run_manifest.update({"status": "incomplete_full_run", "stages_completed": stage_records})
                (args.output_root / "execution_manifest.json").write_text(json.dumps(run_manifest, indent=2) + "\n")
                _write_execution_summary(args.output_root, run_manifest)
                return 1
            if (output / "ground_truth_subset.json").read_bytes() != (args.classic_run / "ground_truth_subset.json").read_bytes():
                raise BenchmarkGateError("full E2E run ground truth bytes differ from the paired Classic population")
            record["evaluation_status"] = "running"
            (args.output_root / "execution_manifest.json").write_text(json.dumps(run_manifest, indent=2) + "\n")
            _run(_evaluate_command(runtime_python, args.evaluator_python, args.evaluator_repo,
                                   dataset, output))
            record["evaluation_status"] = "complete_exact_subset"
            run_manifest["e2e_metrics"] = json.loads((output / "metrics.json").read_text())
            run_manifest["classic_metrics"] = json.loads((args.classic_run / "metrics.json").read_text())
            run_manifest["paired_report"] = build_paired_report(
                args.classic_run, output, selected_ids, args.output_root / "paired-report"
            )
            run_manifest["status"] = "completed_and_scored"
    run_manifest["stages_completed"] = stage_records
    (args.output_root / "execution_manifest.json").write_text(json.dumps(run_manifest, indent=2) + "\n")
    _write_execution_summary(args.output_root, run_manifest)
    return 0 if run_manifest["status"] == "completed_and_scored" else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--determinism-plan", type=Path, default=DEFAULT_DETERMINISM)
    parser.add_argument("--expected-pages", type=int, default=180)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--runtime-python", type=Path, required=True,
                        help="Pinned Paddle environment Python used for preflight and extraction subprocesses.")
    parser.add_argument("--evaluator-repo", type=Path, default=ROOT / ".external/OmniDocBench")
    parser.add_argument("--evaluator-python", type=Path, required=True)
    parser.add_argument("--classic-run", type=Path, required=True,
                        help="Existing complete Classic run on the exact same frozen representative-v2 manifest.")
    parser.add_argument("--output-root", type=Path, required=True,
                        help="New, non-existing output directory for this controlled GPU execution.")
    parser.add_argument("--plan", action="store_true", help="Print exact frozen page selections/commands; does not inspect GPU or run inference.")
    parser.add_argument("--execute", action="store_true", help="Run all gates and stages; without this flag the command refuses execution.")
    return parser


def main(argv: list[str] | None = None) -> int:
    actual_argv = list(sys.argv[1:] if argv is None else argv)
    if "--gpu-preflight-only" in actual_argv:
        preflight_parser = argparse.ArgumentParser(add_help=False)
        preflight_parser.add_argument("--gpu-preflight-only", action="store_true")
        preflight_parser.add_argument("--config", type=Path, required=True)
        preflight_args = preflight_parser.parse_args(actual_argv)
        try:
            print(json.dumps(gpu_preflight(preflight_args.config), sort_keys=True))
            return 0
        except (BenchmarkGateError, OSError, subprocess.SubprocessError) as exc:
            print(f"GPU preflight failed: {exc}", file=sys.stderr)
            return 2
    args = build_parser().parse_args(actual_argv)
    try:
        if args.plan:
            if args.expected_pages is not None:
                _, _manifest, samples = manifest_identity(args.manifest)
                if len(samples) != args.expected_pages:
                    raise BenchmarkGateError(f"expected {args.expected_pages} pages, manifest has {len(samples)}")
            plan = build_plan(args.manifest, args.determinism_plan, args.output_root,
                              args.dataset, args.config, args.runtime_python)
            print(json.dumps(plan, indent=2, ensure_ascii=False))
            return 0
        if not args.execute:
            raise BenchmarkGateError("execution requires explicit --execute; use --plan for a no-inference dry plan")
        return execute(args)
    except (BenchmarkGateError, OSError, ValueError, json.JSONDecodeError, subprocess.SubprocessError) as exc:
        output_root = getattr(args, "output_root", None)
        if isinstance(output_root, Path):
            execution_manifest_path = output_root / "execution_manifest.json"
            if execution_manifest_path.is_file():
                try:
                    execution = json.loads(execution_manifest_path.read_text(encoding="utf-8"))
                    execution["status"] = "failed"
                    execution["failure"] = {"type": type(exc).__name__, "message": str(exc)[:2000]}
                    execution_manifest_path.write_text(json.dumps(execution, indent=2) + "\n", encoding="utf-8")
                    _write_execution_summary(output_root, execution)
                except (OSError, ValueError, TypeError) as write_exc:
                    print(f"could not persist failed execution status: {write_exc}", file=sys.stderr)
        print(f"E2E benchmark gate failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
