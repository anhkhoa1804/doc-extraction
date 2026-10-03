from __future__ import annotations

import json

import numpy as np
import pytest

import doc_extraction.backends.paddlex_forensic as forensic
from doc_extraction.backends.paddlex_forensic import (
    Trace,
    _experiment_cap,
    _generated_lengths,
    _shape,
    _wrap_iterator,
)


def test_trace_flushes_bounded_metadata_without_content(tmp_path):
    path = tmp_path / "trace.jsonl"
    trace = Trace(path)
    trace.emit("stage_started", stage="recognition", input_count=2)
    trace.close()

    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [row["event"] for row in rows] == ["trace_started", "stage_started"]
    assert rows[1]["stage"] == "recognition"
    assert "trace_elapsed_seconds" in rows[1]
    assert path.stat().st_size <= 64 * 1024


def test_trace_stops_at_event_bound(tmp_path, monkeypatch):
    monkeypatch.setattr(forensic, "_MAX_EVENTS", 2)
    path = tmp_path / "bounded.jsonl"
    trace = Trace(path)
    trace.emit("second")
    trace.emit("ignored")
    trace.close()

    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [row["event"] for row in rows] == ["trace_started", "second"]


def test_iterator_instrumentation_preserves_values_and_only_summarizes_lengths(tmp_path):
    trace = Trace(tmp_path / "trace.jsonl")
    source = iter([{"result": "secret-looking document text"}, {"result": "second"}])
    result = list(_wrap_iterator(
        source,
        trace,
        start_event="recognition_started",
        done_event="recognition_finished",
        details={"input_count": 2},
        summarize=lambda item: {"result_chars": len(item["result"])},
    ))
    trace.close()

    assert result == [{"result": "secret-looking document text"}, {"result": "second"}]
    contents = (tmp_path / "trace.jsonl").read_text(encoding="utf-8")
    assert "secret-looking" not in contents
    finished = json.loads(contents.splitlines()[-1])
    assert finished["status"] == "returned"
    assert finished["count"] == 2
    assert finished["outputs"] == [{"result_chars": 28}, {"result_chars": 6}]


def test_shape_summary_uses_only_dimensions_and_pixel_count():
    assert _shape(np.zeros((12, 34, 3), dtype=np.uint8)) == {
        "width": 34,
        "height": 12,
        "pixels": 408,
    }
    assert _shape("not an image") is None


def test_generated_token_count_subtracts_prompt_prefix_when_shapes_are_exposed():
    class Tensor:
        def __init__(self, shape):
            self.shape = shape

    result = Tensor((1, 710 + 1024))
    model_inputs = {"input_ids": Tensor((1, 710))}
    assert _generated_lengths(result, model_inputs) == {
        "generated_tokens": 1024,
        "input_tokens": 710,
        "output_sequence_tokens": 1734,
    }


def test_generated_token_count_is_unavailable_without_both_sequence_shapes():
    assert _generated_lengths(object(), {}) == {
        "generated_tokens": None,
        "input_tokens": None,
        "output_sequence_tokens": None,
    }


def test_experiment_token_cap_is_explicit_and_allowlisted():
    assert _experiment_cap(None) is None
    assert _experiment_cap("4096") == 4096
    assert _experiment_cap("2048") == 2048
    assert _experiment_cap("1024") == 1024
    with pytest.raises(ValueError):
        _experiment_cap("512")
