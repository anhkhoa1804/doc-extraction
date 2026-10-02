"""Bounded request/response client for a private, persistent worker process."""
from __future__ import annotations

import json
import os
import selectors
import shutil
import struct
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from typing_extensions import Self

from doc_extraction.utils.subprocesses import terminate_process_group


class WorkerError(RuntimeError):
    """Base worker lifecycle error with a stable machine-readable kind."""

    kind = "worker_failure"


class WorkerCrashed(WorkerError):
    kind = "worker_crash"


class WorkerProtocolError(WorkerError):
    kind = "invalid_worker_output"


class WorkerTimeout(WorkerError):
    kind = "timeout"

    def __init__(self, timeout: float, elapsed: float) -> None:
        self.timeout = timeout
        self.elapsed = elapsed
        super().__init__(f"isolated worker exceeded {timeout:.3f}s operation deadline")


class WorkerTempLimit(WorkerError):
    kind = "temporary_storage_limit"

    def __init__(self, limit: int, actual: int) -> None:
        self.limit = limit
        self.actual = actual
        super().__init__(f"isolated worker scratch exceeded {limit} bytes (observed {actual})")


class WorkerTerminationError(WorkerError):
    kind = "worker_termination_failure"


def _directory_size(root: Path, stop_after: int) -> int:
    """Count regular-file bytes without following symlinks; stop over quota."""
    total = 0
    stack = [root]
    while stack:
        directory = stack.pop()
        try:
            entries = os.scandir(directory)
        except FileNotFoundError:
            continue
        with entries:
            for entry in entries:
                try:
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(Path(entry.path))
                    elif entry.is_file(follow_symlinks=False):
                        total += entry.stat(follow_symlinks=False).st_size
                        if total > stop_after:
                            return total
                except FileNotFoundError:
                    continue
    return total


class BoundedPersistentWorker:
    """One isolated process with bounded JSON-line requests and framed replies.

    The child is launched in a new POSIX session. On a timeout or protocol
    error the entire owned process group is killed and verified absent before
    the scratch directory is removed. The worker receives no output paths or
    policy object; callers send only operation-specific input data.
    """

    def __init__(
        self,
        argv: list[str],
        *,
        max_message_bytes: int,
        scratch_parent: Path | None = None,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        if not argv or max_message_bytes <= 0:
            raise ValueError("worker command and positive message limit are required")
        self.argv = list(argv)
        self.max_message_bytes = max_message_bytes
        self.scratch_parent = scratch_parent
        self.cwd = str(cwd) if cwd is not None else None
        self.base_env = env
        self.process: subprocess.Popen[bytes] | None = None
        self.scratch_dir: Path | None = None
        self.state = "terminated"
        self.last_state = "terminated"
        self.termination_verified = True
        self.ready_metadata: dict[str, Any] = {}
        self.last_startup_seconds = 0.0
        self.last_request_seconds = 0.0
        self.last_termination_seconds = 0.0
        self._stdout_fd: int | None = None
        self._buffer = bytearray()
        self._lock = threading.RLock()

    def _remaining(self, deadline: float, timeout: float) -> float:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise WorkerTimeout(timeout, timeout - remaining)
        return remaining

    def _read_exactly(self, count: int, deadline: float, timeout: float, scratch_limit: int) -> bytes:
        assert self._stdout_fd is not None
        selector = selectors.DefaultSelector()
        selector.register(self._stdout_fd, selectors.EVENT_READ)
        try:
            while len(self._buffer) < count:
                remaining = self._remaining(deadline, timeout)
                if self.scratch_dir is not None:
                    scratch = _directory_size(self.scratch_dir, scratch_limit)
                    if scratch > scratch_limit:
                        raise WorkerTempLimit(scratch_limit, scratch)
                if self.process is None:
                    raise WorkerCrashed("worker process is unavailable")
                if self.process.poll() is not None:
                    raise WorkerCrashed(f"worker exited with status {self.process.returncode}")
                events = selector.select(min(remaining, 0.05))
                if not events:
                    continue
                chunk = os.read(self._stdout_fd, min(65536, count - len(self._buffer)))
                if not chunk:
                    code = self.process.poll()
                    raise WorkerCrashed(f"worker closed its protocol stream (exit={code})")
                self._buffer.extend(chunk)
            result = bytes(self._buffer[:count])
            del self._buffer[:count]
            return result
        finally:
            selector.close()

    def _read_frame(self, deadline: float, timeout: float, scratch_limit: int) -> dict[str, Any]:
        header = self._read_exactly(4, deadline, timeout, scratch_limit)
        length = struct.unpack(">I", header)[0]
        if length > self.max_message_bytes:
            raise WorkerProtocolError(
                f"worker reply length {length} exceeds {self.max_message_bytes}-byte IPC limit"
            )
        payload = self._read_exactly(length, deadline, timeout, scratch_limit)
        try:
            data = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise WorkerProtocolError("worker reply is not valid UTF-8 JSON") from exc
        if not isinstance(data, dict):
            raise WorkerProtocolError("worker reply must be a JSON object")
        return data

    def _spawn(self, deadline: float, timeout: float, scratch_limit: int) -> None:
        self.state = "starting"
        startup_started = time.perf_counter()
        self.ready_metadata = {}
        self.scratch_dir = Path(tempfile.mkdtemp(prefix="doc-extraction-e2e-", dir=self.scratch_parent))
        os.chmod(self.scratch_dir, 0o700)
        environment = os.environ.copy()
        if self.base_env:
            environment.update(self.base_env)
        environment.update(
            {
                "TMPDIR": str(self.scratch_dir),
                "TMP": str(self.scratch_dir),
                "TEMP": str(self.scratch_dir),
                "DOC_EXTRACTION_WORKER_FILE_LIMIT": str(max(1, scratch_limit)),
            }
        )
        try:
            self.process = subprocess.Popen(
                self.argv,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                cwd=self.cwd,
                env=environment,
                bufsize=0,
                close_fds=True,
                start_new_session=True,
            )
            assert self.process.stdout is not None
            self._stdout_fd = self.process.stdout.fileno()
            os.set_blocking(self._stdout_fd, False)
            ready = self._read_frame(deadline, timeout, scratch_limit)
            if ready.get("state") != "ready":
                raise WorkerCrashed(f"worker failed during startup: {ready.get('kind', 'unknown')}")
            self.ready_metadata = ready
            self.last_startup_seconds = time.perf_counter() - startup_started
            self.state = "ready"
            self.last_state = "ready"
        except Exception:
            self.last_startup_seconds = time.perf_counter() - startup_started
            self.terminate("terminated")
            raise

    def request(self, payload: dict[str, Any], *, timeout: float, scratch_limit: int) -> dict[str, Any]:
        if timeout <= 0 or scratch_limit < 0:
            raise ValueError("worker timeout must be positive and scratch limit non-negative")
        deadline = time.monotonic() + timeout
        with self._lock:
            self.last_startup_seconds = 0.0
            self.last_request_seconds = 0.0
            self.last_termination_seconds = 0.0
            try:
                if self.process is None or self.process.poll() is not None:
                    if self.process is not None:
                        self.terminate("terminated")
                    self.last_startup_seconds = 0.0
                    self._spawn(deadline, timeout, scratch_limit)
                encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                if len(encoded) > self.max_message_bytes:
                    raise WorkerProtocolError("worker request exceeds bounded IPC limit")
                assert self.process is not None and self.process.stdin is not None
                request_started = time.perf_counter()
                self.state = "running"
                self.last_state = "running"
                self.process.stdin.write(encoded + b"\n")
                self.process.stdin.flush()
                reply = self._read_frame(deadline, timeout, scratch_limit)
                self.last_request_seconds = time.perf_counter() - request_started
                state = reply.get("state")
                if state == "failed":
                    self.last_state = "failed"
                    raise WorkerCrashed(
                        f"worker operation failed ({reply.get('kind', 'model_failure')}): "
                        f"{reply.get('message', 'no details')}"
                    )
                if state != "completed":
                    raise WorkerProtocolError(f"unexpected worker response state: {state!r}")
                self.state = "ready"
                self.last_state = "completed"
                return reply
            except WorkerTimeout:
                if "request_started" in locals():
                    self.last_request_seconds = time.perf_counter() - request_started
                self.last_state = "timed_out"
                self.terminate("timed_out")
                raise
            except WorkerTempLimit:
                self.last_state = "failed"
                self.terminate("failed")
                raise
            except WorkerError:
                if self.process is not None:
                    self.terminate(self.last_state if self.last_state == "failed" else "terminated")
                raise
            except (BrokenPipeError, OSError) as exc:
                self.last_state = "failed"
                self.terminate("failed")
                raise WorkerCrashed("worker IPC failed") from exc

    def terminate(self, terminal_state: str = "terminated") -> None:
        if self.process is None and self.scratch_dir is None:
            self.state = terminal_state
            if terminal_state != "timed_out":
                self.last_state = terminal_state
            return
        termination_started = time.perf_counter()
        process = self.process
        if process is not None:
            verified = terminate_process_group(process)
            self.termination_verified = verified
            if not verified:
                self.state = "failed"
                self.last_state = "termination_unverified"
                raise WorkerTerminationError("owned worker process group did not terminate")
            if process.stdin is not None:
                process.stdin.close()
            if process.stdout is not None:
                process.stdout.close()
        self.process = None
        self._stdout_fd = None
        self._buffer.clear()
        self.state = terminal_state
        if terminal_state != "timed_out":
            self.last_state = terminal_state
        if self.scratch_dir is not None:
            shutil.rmtree(self.scratch_dir, ignore_errors=False)
            self.scratch_dir = None
        self.last_termination_seconds = time.perf_counter() - termination_started

    def close(self) -> None:
        with self._lock:
            if self.process is not None:
                self.terminate("terminated")

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()
