"""The log-aggregating profiler.

The cold/warm split is the part worth locking down: reporting a stage's
mean including its first (model-loading) call misstates steady-state
inference by a large factor, which is exactly the mistake the profiler
exists to prevent.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "_profile_pipeline_under_test", REPO_ROOT / "scripts" / "profile_pipeline.py"
)
prof = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(prof)


def _write_log(root: Path, doc: str, records: list[dict]) -> None:
    log_dir = root / doc / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "pipeline.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in records), encoding="utf-8"
    )


def _rec(ts, stage, backend, runtime, device="cpu", status="success"):
    return {"timestamp": ts, "document": "d", "page": 0, "stage": stage, "backend": backend,
            "status": status, "runtime_seconds": runtime, "device": device,
            "output_path": None, "warnings": [], "error": None, "metrics": {}}


def test_first_call_is_cold_and_the_rest_are_warm(tmp_path):
    _write_log(tmp_path, "doc1", [
        _rec("2026-09-01T10:00:00", "layout", "docling", 30.0),
        _rec("2026-09-01T10:00:31", "layout", "docling", 2.0),
        _rec("2026-09-01T10:00:33", "layout", "docling", 2.2),
    ])
    rows = prof.summarize(prof.load_records([tmp_path]))
    layout = next(r for r in rows if r["stage"] == "layout")
    assert layout["cold_s"] == 30.0
    assert layout["warm_mean_s"] == 2.1
    assert layout["implied_model_load_s"] == 27.9
    assert layout["calls"] == 3


def test_cold_is_determined_by_timestamp_not_file_order(tmp_path):
    """Documents are separate files; execution order across them is only
    recoverable from timestamps. The cold call is the globally first one."""
    _write_log(tmp_path, "zzz_first", [_rec("2026-09-01T10:00:00", "layout", "docling", 30.0)])
    _write_log(tmp_path, "aaa_second", [_rec("2026-09-01T10:05:00", "layout", "docling", 2.0)])
    rows = prof.summarize(prof.load_records([tmp_path]))
    layout = next(r for r in rows if r["stage"] == "layout")
    assert layout["cold_s"] == 30.0, "the chronologically first call must be cold"
    assert layout["warm_mean_s"] == 2.0


def test_single_call_has_no_warm_statistics(tmp_path):
    """One observation cannot separate load from inference; the profiler must
    say so rather than invent a warm figure."""
    _write_log(tmp_path, "doc1", [_rec("2026-09-01T10:00:00", "assemble", "doc_extraction", 0.01)])
    row = prof.summarize(prof.load_records([tmp_path]))[0]
    assert row["warm_mean_s"] is None
    assert row["implied_model_load_s"] is None


def test_device_is_part_of_the_grouping_key(tmp_path):
    """CPU and GPU timings for the same stage must never be pooled into one
    mean — that is the comparison the whole exercise is about."""
    _write_log(tmp_path, "doc1", [
        _rec("2026-09-01T10:00:00", "layout", "docling", 14.0, device="cpu"),
        _rec("2026-09-01T10:00:20", "layout", "docling", 1.6, device="cuda"),
    ])
    rows = prof.summarize(prof.load_records([tmp_path]))
    assert {r["device"] for r in rows} == {"cpu", "cuda"}


def test_latency_model_separates_one_off_load_from_steady_state(tmp_path):
    _write_log(tmp_path, "doc1", [
        _rec("2026-09-01T10:00:00", "layout", "docling", 30.0),
        _rec("2026-09-01T10:00:31", "layout", "docling", 2.0),
    ])
    model = prof.latency_model(prof.summarize(prof.load_records([tmp_path])))
    assert model["one_off_model_load_s"] == 28.0
    assert model["steady_state_s"] == 4.0          # 32.0 total - 28.0 load
    assert model["total_logged_s"] == 32.0


def test_failures_are_counted_but_their_time_still_accrues(tmp_path):
    """A failed stage consumed real wall-clock time; hiding it would make the
    profile disagree with the clock."""
    _write_log(tmp_path, "doc1", [
        _rec("2026-09-01T10:00:00", "layout", "docling", 5.0, status="failure"),
        _rec("2026-09-01T10:00:06", "layout", "docling", 5.0),
    ])
    row = prof.summarize(prof.load_records([tmp_path]))[0]
    assert row["failures"] == 1
    assert row["total_s"] == 10.0


def test_truncated_log_line_is_skipped_not_fatal(tmp_path):
    """A killed run leaves a partial final line; profiling must still work."""
    log_dir = tmp_path / "doc1" / "logs"
    log_dir.mkdir(parents=True)
    with open(log_dir / "pipeline.jsonl", "w", encoding="utf-8") as f:
        f.write(json.dumps(_rec("2026-09-01T10:00:00", "layout", "docling", 1.0)) + "\n")
        f.write('{"timestamp": "2026-09-01T10:00:01", "stage": "lay')
    assert len(prof.load_records([tmp_path])) == 1


def test_negative_implied_load_is_reported_as_not_separable(tmp_path):
    """On a heterogeneous corpus the first call can be *faster* than average,
    which means its cost cannot be attributed to model loading.

    Reporting that as a load of 0.0 would look measured; reporting it as None
    plus an explicit flag says the estimate does not apply. This is the real
    behaviour on OmniDocBench, where per-page cost spans an order of
    magnitude and an easy first page inverts the split.
    """
    _write_log(tmp_path, "doc1", [
        _rec("2026-09-01T10:00:00", "layout", "docling", 51.4),   # easy first page
        _rec("2026-09-01T10:01:00", "layout", "docling", 70.0),
        _rec("2026-09-01T10:02:00", "layout", "docling", 70.1),
    ])
    rows = prof.summarize(prof.load_records([tmp_path]))
    layout = next(r for r in rows if r["stage"] == "layout")
    assert layout["implied_model_load_s"] is None
    assert layout["load_estimate_unreliable"] is True

    model = prof.latency_model(rows)
    assert model["load_not_separable_for"] == ["layout/docling"]
    # None of it may be silently booked as one-off load.
    assert model["one_off_model_load_s"] == 0.0
    assert model["steady_state_s"] == layout["total_s"]
