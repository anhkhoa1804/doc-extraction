from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path

from doc_extraction.backends.paddleocr_vl_backend import PaddleOCRVLBackend

PREPARE_PATH = Path(__file__).parents[1] / "experiments/005_omnidocbench/prepare.py"
SPEC = importlib.util.spec_from_file_location("omnidocbench_prepare_for_test", PREPARE_PATH)
assert SPEC is not None and SPEC.loader is not None
PREPARE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREPARE)


def test_source_attestation_hashes_working_bytes_and_records_dirty_state(
    tmp_path: Path, monkeypatch
) -> None:
    source_paths = [
        "src/doc_extraction/example.py",
        "benchmarks/scripts/example.py",
        "experiments/005_omnidocbench/prepare.py",
        "pyproject.toml",
        "uv.lock",
    ]
    contents = {path: f"fixture:{path}\n".encode() for path in source_paths}
    for path, content in contents.items():
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    monkeypatch.setattr(PREPARE, "REPO_ROOT", tmp_path)

    calls = iter(
        [
            subprocess.CompletedProcess([], 0, stdout="fixture-head\n", stderr=""),
            subprocess.CompletedProcess([], 0, stdout=" M example.py\n", stderr=""),
            subprocess.CompletedProcess([], 0, stdout=("\0".join(source_paths) + "\0").encode(), stderr=b""),
        ]
    )
    monkeypatch.setattr(PREPARE.subprocess, "run", lambda *args, **kwargs: next(calls))

    result = PREPARE.build_source_attestation()
    expected = hashlib.sha256()
    for path, content in sorted(contents.items()):
        expected.update(path.encode() + b"\0" + content + b"\0")
    assert result["source_snapshot_sha256"] == expected.hexdigest()
    assert result["source_files"] == {
        path: hashlib.sha256(content).hexdigest() for path, content in sorted(contents.items())
    }
    assert result["git_commit"] == "fixture-head"
    assert result["working_tree_clean"] is False
    assert result["working_tree_status"] == [" M example.py"]


def test_model_version_attestation_hashes_both_checkpoint_files(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    model = tmp_path / ".paddlex/official_models/PaddleOCR-VL-1.6/model.safetensors"
    layout = tmp_path / ".paddlex/official_models/PP-DocLayoutV3/inference.pdiparams"
    model.parent.mkdir(parents=True)
    layout.parent.mkdir(parents=True)
    model.write_bytes(b"model fixture")
    layout.write_bytes(b"layout fixture")

    versions = PaddleOCRVLBackend.model_versions()
    assert versions["model_weights_sha256"] == hashlib.sha256(b"model fixture").hexdigest()
    assert versions["layout_weights_sha256"] == hashlib.sha256(b"layout fixture").hexdigest()


def test_frozen_e2e_regression_pages_remain_in_full_run_analysis() -> None:
    root = Path(__file__).parents[1]
    manifest = json.loads((root / "benchmarks/manifests/omnidocbench-representative-v2.json").read_text())
    report = json.loads((root / "benchmarks/reports/omnidocbench/e2e-full-v2.json").read_text())
    required = {
        "yanbaopptmerge_1c5f17c3dfa38c45b86802b9d014da18.pdf_1372.jpg#3062",
        "page-062fc21c-6b9c-40be-8d0e-7a617509a9bc.png#0",
    }
    manifest_ids = {sample["page_id"] for sample in manifest["subset"]["samples"]}
    run_pages = {page["page_id"]: page for page in report["per_page"]}

    assert required <= manifest_ids
    assert required <= run_pages.keys()
    for page_id in required:
        assert run_pages[page_id]["status"] == "success"
        assert run_pages[page_id]["prediction_sha256"]
    assert run_pages[
        "page-062fc21c-6b9c-40be-8d0e-7a617509a9bc.png#0"
    ]["metric_values"]["text_edit_distance"] is not None

    determinism = json.loads(
        (root / "benchmarks/reports/omnidocbench/e2e-determinism-v1.json").read_text()
    )
    deterministic_ids = determinism["selected_page_ids"]
    assert len(deterministic_ids) == 10
    assert len(set(deterministic_ids)) == 10
    assert set(deterministic_ids) <= manifest_ids
    assert determinism["status"] == "NOT_RUN"
