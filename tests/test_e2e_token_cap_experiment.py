"""CPU-only tests for token-cap experiment coverage accounting."""
from __future__ import annotations

import json
from pathlib import Path

from benchmarks.scripts.e2e_token_cap_experiment import _coverage


def _write_run(tmp_path: Path, records: list[dict[str, object]], names: list[str]) -> Path:
    run = tmp_path / "run"
    run.mkdir()
    prediction_dir = run / "predictions"
    prediction_dir.mkdir()
    for name in names:
        (prediction_dir / name).write_text("prediction\n", encoding="utf-8")
    (run / "run_metadata.json").write_text(
        json.dumps({"prediction_directory": "predictions"}), encoding="utf-8"
    )
    (run / "runtime.json").write_text(json.dumps({"per_page": records}), encoding="utf-8")
    return run


def test_coverage_counts_timeout_as_failure_even_when_error_field_is_null(tmp_path: Path) -> None:
    run = _write_run(
        tmp_path,
        [
            {"page_id": "a.png#0", "status": "success", "error": None},
            {"page_id": "b.png#0", "status": "failed", "error": None},
        ],
        ["a.md"],
    )

    result = _coverage(run, ["a.png#0", "b.png#0"])

    assert result["success"] == 1
    assert [record["page_id"] for record in result["failures"]] == ["b.png#0"]
    assert result["missing_predictions"] == ["b.md"]
    assert result["valid"] is False


def test_coverage_accepts_success_with_warnings_when_prediction_set_is_exact(tmp_path: Path) -> None:
    run = _write_run(
        tmp_path,
        [
            {"page_id": "a.png#0", "status": "success", "error": None},
            {"page_id": "b.png#0", "status": "success_with_warnings", "error": None},
        ],
        ["a.md", "b.md"],
    )

    result = _coverage(run, ["a.png#0", "b.png#0"])

    assert result["success"] == 2
    assert result["failures"] == []
    assert result["valid"] is True
