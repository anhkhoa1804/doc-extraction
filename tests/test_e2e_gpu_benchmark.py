from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).parents[1] / "benchmarks/scripts/e2e_gpu_benchmark.py"
SPEC = importlib.util.spec_from_file_location("e2e_gpu_benchmark_for_test", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
HARNESS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HARNESS)


def _manifest(tmp_path: Path) -> tuple[Path, list[dict[str, str]]]:
    samples = [
        {"page_id": f"page-{index}.png#0", "image_name": f"page-{index}.png", "sample_id": f"sample-{index}"}
        for index in range(22)
    ]
    for image_name, page_id in (
        ("page-affbb0cc-d616-481d-b493-80ed1ccb5a10.png", "page-affbb0cc-d616-481d-b493-80ed1ccb5a10.png#0"),
        ("newspaper_TheWashingtonPost-2025-01-08@magazinesclubnew_page_042.png",
         "newspaper_TheWashingtonPost-2025-01-08@magazinesclubnew_page_042.png#42"),
    ):
        samples.append({"page_id": page_id, "image_name": image_name, "sample_id": image_name})
    manifest = {"subset": {"actual_size": len(samples), "samples": samples}, "subset_identity": {"sha256": "identity"}}
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path, samples


def test_frozen_manifest_identity_and_determinism_selection(tmp_path: Path) -> None:
    manifest_path, samples = _manifest(tmp_path)
    file_hash, _, loaded_samples = HARNESS.manifest_identity(manifest_path)
    selected = [entry["page_id"] for entry in loaded_samples[:10]]
    det_path = tmp_path / "determinism.json"
    det_path.write_text(json.dumps({"status": "NOT_RUN", "manifest_sha256": file_hash,
                                   "selected_page_ids": selected}), encoding="utf-8")

    assert HARNESS.deterministic_ids(det_path, samples, file_hash) == selected
    assert HARNESS.resolve_named_pages(samples) == [samples[-2]["page_id"], samples[-1]["page_id"]]
    with pytest.raises(HARNESS.BenchmarkGateError, match="different manifest"):
        HARNESS.deterministic_ids(det_path, samples, "wrong")


def test_plan_has_explicit_frozen_smoke_diagnostics_preflight_and_full_run(tmp_path: Path) -> None:
    manifest_path, samples = _manifest(tmp_path)
    file_hash, _, _ = HARNESS.manifest_identity(manifest_path)
    det_path = tmp_path / "determinism.json"
    det_ids = [entry["page_id"] for entry in samples[:10]]
    det_path.write_text(json.dumps({"status": "NOT_RUN", "manifest_sha256": file_hash,
                                   "selected_page_ids": det_ids}), encoding="utf-8")

    plan = HARNESS.build_plan(manifest_path, det_path, tmp_path / "runs", tmp_path / "data",
                              tmp_path / "gpu.yaml", tmp_path / "runtime-python")

    assert [stage["name"] for stage in plan] == [
        "timing-diagnostic", "timeout-diagnostic-1", "timeout-diagnostic-2",
        "determinism-a", "determinism-b", "smoke-5", "preflight-20", "full-180",
    ]
    assert len(plan[0]["page_ids"]) == 1
    assert plan[1]["page_ids"] == [samples[-2]["page_id"]]
    assert plan[2]["page_ids"] == [samples[-1]["page_id"]]
    assert len(plan[3]["page_ids"]) == 10 == len(plan[4]["page_ids"])
    assert len(plan[5]["page_ids"]) == 5
    assert plan[6]["page_ids"] == [entry["page_id"] for entry in samples[:20]]
    assert plan[7]["page_ids"] == [entry["page_id"] for entry in samples]
    assert all("--page-ids" in stage["command"] for stage in plan)


def test_gpu_process_guard_refuses_occupied_device_without_signaling_process(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(HARNESS, "query_gpu_processes", lambda: ["1234, python, 512 MiB"])
    with pytest.raises(HARNESS.BenchmarkGateError, match="without signaling it"):
        HARNESS.require_unoccupied_gpu()


def test_timing_page_inspection_requires_canonical_page_and_reports_serialization(tmp_path: Path) -> None:
    run = tmp_path / "run"
    document_dir = run / "_doc_extraction_runs" / "doc-one" / "final"
    prediction_dir = run / "predictions"
    document_dir.mkdir(parents=True)
    prediction_dir.mkdir()
    (document_dir / "document.json").write_text(json.dumps({
        "metadata": {"warnings": ["W1"], "errors": []},
        "pages": [{
            "elements": [{"id": "p0-e0", "type": "text", "text": "sample"}],
            "tables": [], "reading_order": ["p0-e0"],
        }],
    }), encoding="utf-8")
    (prediction_dir / "one.md").write_text("sample\n", encoding="utf-8")
    (run / "run_metadata.json").write_text(json.dumps({
        "sample_ids": [{"page_id": "one.png#0", "document_id": "doc-one", "image_name": "one.png"}],
        "prediction_directory": "predictions",
    }), encoding="utf-8")
    (run / "runtime.json").write_text(json.dumps({"per_page": [{
        "page_id": "one.png#0", "status": "success", "runtime_seconds": 1.0,
        "backend_timings": {"pipeline_predict_seconds": 0.5},
    }]}), encoding="utf-8")

    result = HARNESS.inspect_single_page_output(run, "one.png#0")
    assert result["canonical_document_valid"] is True
    assert result["text_bearing_element_count"] == 1
    assert result["reading_order_reference_count"] == 1
    assert result["warnings"] == ["W1"]
    assert result["prediction_utf8_valid"] is True


def test_evaluator_command_preserves_venv_python_symlink_path(tmp_path: Path) -> None:
    venv_python = tmp_path / ".venv-omnidoc" / "bin" / "python"
    command = HARNESS._evaluate_command(
        tmp_path / "runtime-python", venv_python, tmp_path / "evaluator",
        tmp_path / "dataset", tmp_path / "run",
    )
    assert command[0] == str(tmp_path / "runtime-python")
    assert command[command.index("--omnidoc-python") + 1] == str(venv_python)


def test_coverage_gate_distinguishes_missing_prediction_timeout_and_extras(tmp_path: Path) -> None:
    predictions = tmp_path / "predictions"
    predictions.mkdir()
    (predictions / "one.md").write_text("ok", encoding="utf-8")
    (predictions / "unexpected.md").write_text("extra", encoding="utf-8")
    runtime = {"per_page": [
        {"page_id": "one.png#0", "status": "success", "backend_timings": {}},
        {"page_id": "two.png#0", "status": "failed", "errors": ["ResourceLimitExceeded: max_runtime_seconds"],
         "backend_timings": {"timeout": "max_runtime_seconds", "worker_termination_and_cleanup_seconds": 0.2,
                             "worker_termination_verified": True, "scratch_cleanup_verified": True}},
    ]}
    report = HARNESS.coverage_report(["one.png#0", "two.png#0"], runtime, predictions)

    assert report["expected"] == 2
    assert report["timeouts"] == 1
    assert report["missing_predictions"] == ["two.md"]
    assert report["unexpected_predictions"] == ["unexpected.md"]
    assert report["valid_for_quality_evaluation"] is False
    assert HARNESS.failure_kind(runtime["per_page"][1]) == "timeout"
    assert HARNESS.timeout_isolated_safely(report) is True


def test_phase_timing_schema_requires_real_success_measurements() -> None:
    report = HARNESS.validate_phase_timing_records({"per_page": [
        {"page_id": "x.png#0", "status": "success", "backend_timings": {"pipeline_predict_seconds": 1.2}},
        {"page_id": "y.png#0", "status": "failed", "backend_timings": {"timeout": "max_runtime_seconds"}},
    ]})
    assert report["complete"] is False
    assert "y.png#0" not in report["pages_with_missing_timing_fields"]
    assert "worker-local phases are unavailable" in report["timeout_phases"]


def test_gpu_benchmark_config_refuses_cpu_fallback_and_changed_runtime_policy() -> None:
    limits = SimpleNamespace(max_runtime_seconds=300, max_image_pixels=40_000_000)
    with pytest.raises(HARNESS.BenchmarkGateError, match="device: cuda"):
        HARNESS.validate_benchmark_config(SimpleNamespace(device="cpu", limits=limits))
    with pytest.raises(HARNESS.BenchmarkGateError, match="300-second"):
        HARNESS.validate_benchmark_config(SimpleNamespace(
            device="cuda", limits=SimpleNamespace(max_runtime_seconds=301, max_image_pixels=40_000_000)
        ))


def test_model_identity_requires_exact_versions_and_weight_hashes() -> None:
    baseline = {"model": "family-v1", "model_revision": "v1", "model_weights_sha256": "a" * 64,
                "layout_weights_sha256": "b" * 64, "paddleocr": "3.7.0"}
    HARNESS.validate_model_identity(baseline, {**baseline, "doc_extraction": "0.1.0"})
    with pytest.raises(HARNESS.BenchmarkGateError, match="identity changed"):
        HARNESS.validate_model_identity(baseline, {**baseline, "model_revision": "latest"})
    with pytest.raises(HARNESS.BenchmarkGateError, match="weight hashes"):
        HARNESS.validate_model_identity({"model": "v1"}, {"model": "v1"})


def test_run_binding_requires_manifest_gt_prediction_and_attestation_exactness(tmp_path: Path) -> None:
    page_id, image_hash = "one.png#0", "c" * 64
    manifest = {
        "subset_identity": {"sha256": "subset-hash"},
        "subset": {"samples": [{"page_id": page_id, "image_name": "one.png", "image_sha256": image_hash}]},
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_bytes = json.dumps(manifest).encode()
    manifest_path.write_bytes(manifest_bytes)
    run = tmp_path / "run"
    run.mkdir()
    (run / "sample_manifest.json").write_bytes(manifest_bytes)
    source_attestation = {"source_snapshot_sha256": "source", "working_tree_status": []}
    gt_bytes = (json.dumps([{"page_info": {"page_no": 0, "image_path": "one.png"}}], indent=2) + "\n").encode()
    (run / "ground_truth_subset.json").write_bytes(gt_bytes)
    prediction_dir = run / "predictions"
    prediction_dir.mkdir()
    (prediction_dir / "one.md").write_text("body\n", encoding="utf-8")
    metadata = {
        "run_attestation_version": 1,
        "sample_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "sample_manifest_identity": "subset-hash",
        "upstream_commit": HARNESS.odb.PINNED_UPSTREAM_COMMIT,
        "config_sha256": "d" * 64,
        "source_attestation": source_attestation,
        "ground_truth_subset_sha256": hashlib.sha256(gt_bytes).hexdigest(),
        "selected_page_ids": [page_id],
        "sample_ids": [{"page_id": page_id, "image_name": "one.png", "image_sha256": image_hash}],
        "prediction_directory": "predictions",
    }
    (run / "run_metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    for name in ("source_attestation.json", "runtime_attestation.json", "pre_run_model_versions.json"):
        (run / name).write_text("{}", encoding="utf-8")
    timing_fields = HARNESS.validate_phase_timing_records({"per_page": []})["required_success_fields"]
    timings = {name: 0.1 for name in timing_fields}
    timings["worker_lifecycle_state"] = "completed"
    timings["worker_cleanup_status"] = "persistent_worker_reused"
    runtime = {"per_page": [{"page_id": page_id, "status": "success", "backend_timings": timings}]}
    (run / "runtime.json").write_text(json.dumps(runtime), encoding="utf-8")

    binding = HARNESS.verify_run_binding(run, manifest_path, [page_id])
    assert binding["coverage"]["valid_for_quality_evaluation"] is True

    (run / "ground_truth_subset.json").unlink()
    with pytest.raises(HARNESS.BenchmarkGateError, match="no run-scoped ground truth"):
        HARNESS.verify_run_binding(run, manifest_path, [page_id])

    (run / "ground_truth_subset.json").write_text("[]", encoding="utf-8")
    with pytest.raises(HARNESS.BenchmarkGateError, match="ground-truth hash"):
        HARNESS.verify_run_binding(run, manifest_path, [page_id])


def test_checked_in_representative_v2_has_exact_180_unique_pages() -> None:
    root = Path(__file__).parents[1]
    path = root / "benchmarks/manifests/omnidocbench-representative-v2.json"
    _, manifest, samples = HARNESS.manifest_identity(path)
    ids = [entry["page_id"] for entry in samples]
    assert manifest["subset"]["actual_size"] == 180
    assert len(ids) == 180
    assert len(set(ids)) == 180
    with pytest.raises(HARNESS.BenchmarkGateError, match="40M-pixel"):
        HARNESS.validate_benchmark_config(SimpleNamespace(
            device="cuda", limits=SimpleNamespace(max_runtime_seconds=300, max_image_pixels=50_000_000)
        ))


def test_determinism_compares_canonical_pages_and_markdown_but_ignores_run_metadata(tmp_path: Path) -> None:
    page_id = "same.png#0"
    runs = []
    for run_number in (1, 2):
        run = tmp_path / f"run-{run_number}"
        prediction_dir = run / "predictions"
        document_dir = run / "_doc_extraction_runs" / "doc-id" / "final"
        prediction_dir.mkdir(parents=True)
        document_dir.mkdir(parents=True)
        (prediction_dir / "same.md").write_text("body\n", encoding="utf-8")
        (document_dir / "document.json").write_text(json.dumps({
            "document_id": f"volatile-{run_number}",
            "metadata": {"timestamp": f"time-{run_number}", "runtime_seconds": run_number},
            "pages": [{"index": 0, "elements": [{"id": "e0", "text": "body"}], "reading_order": ["e0"]}],
        }), encoding="utf-8")
        (run / "run_metadata.json").write_text(json.dumps({
            "sample_ids": [{"page_id": page_id, "document_id": "doc-id", "image_name": "same.png"}],
            "prediction_directory": "predictions",
        }), encoding="utf-8")
        runs.append(run)

    report = HARNESS.compare_run_outputs(runs[0], runs[1], [page_id])
    assert report["canonical_page_content_identical"] is True
    assert report["serialized_markdown_identical"] is True
