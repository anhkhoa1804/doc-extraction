from __future__ import annotations

import hashlib
import importlib.util
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
