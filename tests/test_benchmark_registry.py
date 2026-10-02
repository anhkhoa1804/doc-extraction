"""Regression tests for internal benchmark bookkeeping, not benchmark scores."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmarks.registry import (
    BenchmarkError,
    FieldRecord,
    build_result,
    deterministic_subset,
    exact_field_metrics,
    grouped_field_metrics,
    load_manifest,
    resolve_local_dataset,
    write_result,
)
from benchmarks.replay import load_replay_cases
from benchmarks.report import render_report
from benchmarks.scripts.record_omnidocbench import build_record
from doc_extraction.evaluation.omnidocbench import PredictionAlignmentError

ROOT = Path(__file__).resolve().parents[1]
MANIFESTS = ROOT / "benchmarks" / "manifests"


def test_all_registry_manifests_are_strict_and_deterministic():
    manifests = [load_manifest(path) for path in sorted(MANIFESTS.glob("*.yaml"))]
    assert [manifest.name for manifest in manifests] == [
        "Kleister Charity",
        "Kleister NDA",
        "LiveWeb-IE",
        "OmniDocBench",
        "SWDE Expanded",
    ]
    omnidoc = next(manifest for manifest in manifests if manifest.name == "OmniDocBench")
    dataset = resolve_local_dataset(omnidoc, ROOT)
    assert dataset is not None
    assert (dataset / "OmniDocBench_demo.json").is_file()


def test_manifest_rejects_unknown_or_invalid_values(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text("schema_version: benchmark-manifest/0\n", encoding="utf-8")
    with pytest.raises(BenchmarkError):
        load_manifest(path)


def test_subset_requires_unique_ids_and_sorts():
    assert deterministic_subset(["c", "a", "b"], 2) == ["a", "b"]
    with pytest.raises(BenchmarkError, match="unique"):
        deterministic_subset(["a", "a"])


def test_field_metrics_keep_task_specific_micro_macro_and_missing_samples():
    truth = [
        FieldRecord("a", {"party": "Acme", "date": "2025"}),
        FieldRecord("b", {"party": "Beta", "date": None}),
    ]
    predicted = [
        FieldRecord("a", {"party": " acme ", "date": "wrong"}),
        FieldRecord("extra", {"party": "ignored"}),
    ]
    metrics = exact_field_metrics(truth, predicted)
    assert metrics["sample_count"] == 2
    assert metrics["micro"]["true_positive"] == 1
    assert metrics["micro"]["false_positive"] == 1
    assert metrics["micro"]["false_negative"] == 2
    assert metrics["missing_prediction_samples"] == ["b"]
    assert set(metrics["per_field"]) == {"date", "party"}


def test_grouped_metrics_keep_site_and_vertical_results_separate():
    truth = [
        FieldRecord("a", {"name": "A"}, site="one", vertical="books"),
        FieldRecord("b", {"name": "B"}, site="two", vertical="books"),
    ]
    predicted = [FieldRecord("a", {"name": "A"}), FieldRecord("b", {"name": "wrong"})]
    assert grouped_field_metrics(truth, predicted, "site")["one"]["micro"]["f1"] == 1.0
    assert grouped_field_metrics(truth, predicted, "vertical")["books"]["micro"]["f1"] == 0.5


def test_result_serialization_is_deterministic_and_never_overwrites(tmp_path):
    manifest = load_manifest(MANIFESTS / "kleister-nda.yaml")
    result = build_result(
        manifest,
        component="semantic-evaluator",
        git_commit="deadbeef",
        config={"normalization": "exact"},
        sample_count=2,
        metrics={"micro_f1": 0.5},
        duration_seconds=1.0,
    )
    path = tmp_path / "result.json"
    write_result(path, result)
    assert path.read_text(encoding="utf-8") == result.canonical_json()
    with pytest.raises(BenchmarkError, match="overwrite"):
        write_result(path, result)
    assert "Kleister NDA" in render_report([path])


def test_replay_manifest_has_unique_deterministic_cases():
    cases = load_replay_cases(MANIFESTS / "web-acquisition-replay.json")
    assert [case.case_id for case in cases] == ["bfs-duplicate-content", "redirect-bounded-body"]
    assert cases[0].expected_acquired == ("/a", "/b", "/c", "/d")


def test_omnidocbench_record_requires_an_aligned_complete_run(tmp_path):
    dataset = tmp_path / "dataset"
    images = dataset / "images"
    images.mkdir(parents=True)
    (images / "page.jpg").write_bytes(b"not-decoded-by-dataset-loader")
    (dataset / "OmniDocBench_demo.json").write_text(
        json.dumps(
            [{"page_info": {"image_path": "images/page.jpg", "page_no": 0, "width": 10, "height": 20}}]
        ),
        encoding="utf-8",
    )
    run = tmp_path / "run"
    predictions = run / "predictions"
    predictions.mkdir(parents=True)
    (predictions / "page.md").write_text("prediction", encoding="utf-8")
    (run / "run_metadata.json").write_text(
        json.dumps({"subset": None, "seed": 0, "num_samples": 1, "config": {"device": "cpu"}, "device": "cpu", "python": "3.12", "model_versions": {}}),
        encoding="utf-8",
    )
    (run / "runtime.json").write_text(json.dumps({"wall_clock_seconds": 1.5, "failures": []}), encoding="utf-8")
    (run / "metrics.json").write_text(json.dumps({"text_block": {"all": {}}}), encoding="utf-8")
    (run / "run_summary.json").write_text(
        json.dumps({"page_denominators": {}, "stage_execution": {}}), encoding="utf-8"
    )

    result = build_record(
        manifest_path=MANIFESTS / "omnidocbench.yaml",
        dataset_root=dataset,
        run_directory=run,
        git_commit_override="deadbeef",
    )
    assert result.dataset["sample_count"] == 1
    assert result.dataset["sample_ids"] == [
        {
            "dataset_index": 0,
            "image_name": "page.jpg",
            "page_no": 0,
            "image_sha256": "274a94eeda390bda7d71fe9d5287c8623481681f87dc6cf2487991083fa2e9b9",
        }
    ]

    (predictions / "page.md").unlink()
    with pytest.raises(PredictionAlignmentError, match="missing 1 expected prediction"):
        build_record(
            manifest_path=MANIFESTS / "omnidocbench.yaml",
            dataset_root=dataset,
            run_directory=run,
            git_commit_override="deadbeef",
        )
