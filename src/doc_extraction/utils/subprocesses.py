"""Bounded capture of an owned POSIX subprocess and its process group."""
from __future__ import annotations

import os
import selectors
import signal
import subprocess
import time

from doc_extraction.utils.limits import ResourceLimitExceeded


def run_bounded(argv: list[str], *, timeout: float, max_output_bytes: int) -> subprocess.CompletedProcess:
    """No shell; limit combined stdout/stderr while reading, and reap child.

    The new process group contains only this invocation.  A child that
    deliberately creates a different session requires worker isolation.
    """
    started = time.monotonic()
    captured: dict[str, bytearray] = {"stdout": bytearray(), "stderr": bytearray()}
    total = 0
    process = subprocess.Popen(
        argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        with selectors.DefaultSelector() as selector:
            for name, pipe in (("stdout", process.stdout), ("stderr", process.stderr)):
                os.set_blocking(pipe.fileno(), False)
                selector.register(pipe, selectors.EVENT_READ, name)
            while selector.get_map():
                remaining = timeout - (time.monotonic() - started)
                if remaining <= 0:
                    raise ResourceLimitExceeded("max_runtime_seconds", timeout, time.monotonic() - started, "OCR subprocess")
                for key, _mask in selector.select(min(remaining, 0.1)):
                    chunk = os.read(key.fd, 64 * 1024)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    total += len(chunk)
                    if total > max_output_bytes:
                        raise ResourceLimitExceeded("max_ocr_output_bytes", max_output_bytes, total, "OCR stdout/stderr")
                    captured[key.data].extend(chunk)
            # Observe exit without reaping the group leader. Until cleanup
            # finishes its PID cannot be reused by an unrelated process.
            while not os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT):
                if time.monotonic() - started >= timeout:
                    raise ResourceLimitExceeded("max_runtime_seconds", timeout, time.monotonic() - started, "OCR subprocess")
                time.sleep(0.01)
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        returncode = process.wait()
        return subprocess.CompletedProcess(
            argv, returncode, captured["stdout"].decode("utf-8", errors="replace"),
            captured["stderr"].decode("utf-8", errors="replace"),
        )
    finally:
        if process.returncode is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        process.wait()
        process.stdout.close()
        process.stderr.close()
