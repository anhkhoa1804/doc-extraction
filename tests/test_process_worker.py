from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from doc_extraction.utils.process_worker import (
    BoundedPersistentWorker,
    WorkerCrashed,
    WorkerProtocolError,
    WorkerTempLimit,
    WorkerTimeout,
)

FIXTURE = Path(__file__).parent / "fixtures" / "persistent_worker_fixture.py"


def _worker(tmp_path: Path, **env: str) -> BoundedPersistentWorker:
    return BoundedPersistentWorker(
        [sys.executable, "-u", str(FIXTURE)],
        max_message_bytes=4096,
        env=env,
    )


def test_worker_startup_and_bounded_json_output(tmp_path: Path) -> None:
    with _worker(tmp_path) as worker:
        assert worker.request({"value": "hello"}, timeout=2, scratch_limit=1024)["value"] == "hello"
        assert worker.state == "ready"
        assert worker.last_state == "completed"


def test_worker_timeout_kills_group_and_cleans_scratch(tmp_path: Path) -> None:
    pid_file = tmp_path / "child.pid"
    worker = _worker(tmp_path, FIXTURE_CHILD_PID_FILE=str(pid_file))
    with pytest.raises(WorkerTimeout):
        worker.request({"action": "hang"}, timeout=0.5, scratch_limit=1024)
    assert worker.last_state == "timed_out"
    assert worker.termination_verified is True
    assert worker.process is None
    assert worker.scratch_dir is None
    child_pid = int(pid_file.read_text(encoding="ascii"))
    with pytest.raises(ProcessLookupError):
        os.kill(child_pid, 0)


def test_worker_continues_after_timeout_by_restarting_cleanly(tmp_path: Path) -> None:
    worker = _worker(tmp_path, FIXTURE_CHILD_PID_FILE=str(tmp_path / "child.pid"))
    try:
        assert worker.request({"value": "A"}, timeout=2, scratch_limit=1024)["value"] == "A"
        with pytest.raises(WorkerTimeout):
            worker.request({"action": "hang"}, timeout=0.5, scratch_limit=1024)
        assert worker.request({"value": "C"}, timeout=2, scratch_limit=1024)["value"] == "C"
    finally:
        worker.close()


def test_worker_failure_and_oversized_output_are_not_accepted(tmp_path: Path) -> None:
    worker = _worker(tmp_path, FIXTURE_CHILD_PID_FILE=str(tmp_path / "child.pid"))
    try:
        with pytest.raises(WorkerCrashed, match="fixture_failure"):
            worker.request({"action": "failed"}, timeout=2, scratch_limit=1024)
        with pytest.raises(WorkerProtocolError, match="exceeds"):
            worker.request({"action": "oversized"}, timeout=2, scratch_limit=1024)
        assert worker.process is None
    finally:
        worker.close()


def test_worker_private_scratch_limit_is_enforced(tmp_path: Path) -> None:
    worker = _worker(tmp_path, FIXTURE_CHILD_PID_FILE=str(tmp_path / "child.pid"))
    try:
        with pytest.raises(WorkerTempLimit):
            worker.request({"action": "scratch"}, timeout=2, scratch_limit=8)
        assert worker.process is None
    finally:
        worker.close()
