"""Tiny process-protocol fixture for timeout/cleanup unit tests."""
from __future__ import annotations

import json
import os
import struct
import subprocess
import sys
import time


def send(value: dict) -> None:
    payload = json.dumps(value, separators=(",", ":")).encode()
    packet = struct.pack(">I", len(payload)) + payload
    fd = int(os.environ["WORKER_PROTOCOL_FD"])
    offset = 0
    while offset < len(packet):
        offset += os.write(fd, packet[offset:])


def main() -> None:
    protocol_fd = os.dup(1)
    os.environ["WORKER_PROTOCOL_FD"] = str(protocol_fd)
    os.dup2(os.open(os.devnull, os.O_WRONLY), 1)
    if os.environ.get("FIXTURE_HANG_READY") == "1":
        time.sleep(5)
    send({"state": "ready"})
    for line in sys.stdin.buffer:
        request = json.loads(line)
        if request.get("action") == "hang":
            child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(5)"])
            with open(os.environ["FIXTURE_CHILD_PID_FILE"], "w", encoding="ascii") as target:
                target.write(str(child.pid))
            time.sleep(5)
        elif request.get("action") == "failed":
            send({"state": "failed", "kind": "fixture_failure", "message": "controlled"})
        elif request.get("action") == "scratch":
            with open(os.path.join(os.environ["TMPDIR"], "spill"), "wb") as target:
                target.write(b"x" * 32)
            send({"state": "completed"})
        elif request.get("action") == "oversized":
            os.write(protocol_fd, struct.pack(">I", 1_000_000))
            time.sleep(5)
        else:
            send({"state": "completed", "value": request.get("value")})


if __name__ == "__main__":
    main()
