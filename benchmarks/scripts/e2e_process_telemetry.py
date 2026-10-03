"""Bounded, read-only process/GPU telemetry for one E2E diagnostic command.

This wrapper does not change the command environment or model inputs. It samples
only the owned command's process tree plus aggregate GPU telemetry, and writes a
small JSON record after the command exits.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MAX_SAMPLES = 240
MAX_COMMAND_ARGUMENTS = 64


def _proc_stat(pid: int) -> tuple[int, int, int, int, str] | None:
    """Return PPID, CPU ticks, and RSS bytes from procfs without command text."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="ascii")
        # comm is parenthesized and may itself contain spaces/parentheses.
        fields = stat[stat.rfind(")") + 2 :].split()
        state = fields[0]
        ppid = int(fields[1])
        process_group = int(fields[2])
        cpu_ticks = int(fields[11]) + int(fields[12])
        status = Path(f"/proc/{pid}/status").read_text(encoding="ascii")
        rss_kib = next(
            (int(line.split()[1]) for line in status.splitlines() if line.startswith("VmRSS:")),
            0,
        )
        return ppid, process_group, cpu_ticks, rss_kib * 1024, state
    except (OSError, ValueError, IndexError):
        return None


def _process_table() -> dict[int, tuple[int, int, int, int, str]]:
    table: dict[int, tuple[int, int, int, int, str]] = {}
    try:
        pids = (int(item.name) for item in Path("/proc").iterdir() if item.name.isdigit())
        for pid in pids:
            record = _proc_stat(pid)
            if record is not None:
                table[pid] = record
    except OSError:
        pass
    return table


def _owned_pids(root_pid: int, table: dict[int, tuple[int, int, int, int, str]]) -> set[int]:
    owned = {root_pid}
    changed = True
    while changed:
        changed = False
        for pid, (ppid, _pgrp, _ticks, _rss, _state) in table.items():
            if ppid in owned and pid not in owned:
                owned.add(pid)
                changed = True
    return {pid for pid in owned if pid in table}


def process_tree(root_pid: int) -> dict[int, tuple[int, int]]:
    """Map owned descendant PIDs to (cumulative CPU ticks, RSS bytes)."""
    table = _process_table()
    owned = _owned_pids(root_pid, table)
    return {pid: (table[pid][2], table[pid][3]) for pid in owned}


def _terminate_owned_process_groups(root_pid: int) -> bool:
    """Stop only groups whose leaders are currently descendants of our command."""
    table = _process_table()
    owned = _owned_pids(root_pid, table)
    groups = {
        table[pid][1]
        for pid in owned
        if pid in table and table[pid][1] in owned and table[pid][1] != os.getpgrp()
    }
    for group in sorted(groups, reverse=True):
        try:
            if os.getpgid(group) == group:
                os.killpg(group, signal.SIGTERM)
        except ProcessLookupError:
            continue
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        if not any(_group_exists(group) for group in groups):
            break
        time.sleep(0.05)
    for group in sorted(groups, reverse=True):
        if _group_exists(group):
            try:
                if os.getpgid(group) == group:
                    os.killpg(group, signal.SIGKILL)
            except ProcessLookupError:
                pass
    return not any(_group_exists(group) for group in groups)


def _group_exists(group: int) -> bool:
    return any(
        record[1] == group and record[4] not in {"Z", "X"}
        for record in _process_table().values()
    )


def gpu_snapshot() -> dict[str, Any] | None:
    """Read aggregate L4 telemetry; return None when nvidia-smi is unavailable."""
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,utilization.gpu,memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=2,
            check=True,
        )
        rows = []
        for line in result.stdout.splitlines():
            fields = [part.strip() for part in line.split(",")]
            if len(fields) == 4:
                rows.append({"name": fields[0], "utilization_percent": int(fields[1]),
                             "memory_used_mib": int(fields[2]), "memory_total_mib": int(fields[3])})
        return {"gpus": rows} if rows else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def gpu_compute_processes() -> list[str] | None:
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-compute-apps=pid,used_memory", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=3,
            check=True,
        )
        return [line[:64] for line in result.stdout.splitlines() if line.strip()][:32]
    except (OSError, subprocess.SubprocessError):
        return None


def _idle_gpu_gate() -> None:
    processes = gpu_compute_processes()
    if processes is None:
        raise RuntimeError("cannot verify GPU process occupancy; refusing diagnostic launch")
    if processes:
        raise RuntimeError(f"GPU has active compute processes; refusing diagnostic launch: {processes}")


def sample_command(
    command: list[str], *, interval_seconds: float, max_wall_seconds: float,
    require_idle_gpu: bool = False,
) -> dict[str, Any]:
    if not command or len(command) > MAX_COMMAND_ARGUMENTS:
        raise ValueError("a command of 1..64 arguments is required")
    if not (0.25 <= interval_seconds <= 10) or max_wall_seconds <= 0:
        raise ValueError("sampling interval must be 0.25..10 seconds and wall limit positive")
    if require_idle_gpu:
        _idle_gpu_gate()

    started_at = datetime.now(timezone.utc).isoformat()
    started = time.monotonic()
    child = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True, close_fds=True)
    previous_cpu: dict[int, tuple[int, float]] = {}
    samples: list[dict[str, Any]] = []
    deadline = started + max_wall_seconds
    while child.poll() is None and len(samples) < MAX_SAMPLES and time.monotonic() < deadline:
        now = time.monotonic()
        tree = process_tree(child.pid)
        process_rows = []
        for pid, (ticks, rss) in sorted(tree.items()):
            previous = previous_cpu.get(pid)
            cpu_percent = None
            if previous is not None:
                old_ticks, old_time = previous
                cpu_percent = max(0.0, (ticks - old_ticks) / os.sysconf("SC_CLK_TCK") /
                                  max(now - old_time, 1e-6) * 100.0)
            previous_cpu[pid] = (ticks, now)
            process_rows.append({"pid": pid, "cpu_percent_since_sample": cpu_percent, "rss_bytes": rss})
        samples.append({"elapsed_seconds": round(now - started, 3), "processes": process_rows,
                        "gpu": gpu_snapshot(), "gpu_compute_processes": gpu_compute_processes()})
        if child.poll() is None:
            time.sleep(min(interval_seconds, max(0.0, deadline - time.monotonic())))

    timed_out = child.poll() is None
    cleanup_verified = True
    if timed_out:
        # This is only the diagnostic wrapper's outer safety limit, not a change
        # to the extraction's configured 300-second operation timeout.
        cleanup_verified = _terminate_owned_process_groups(child.pid)
        child.wait(timeout=3)
    return {
        "schema": "e2e-process-telemetry/1",
        "started_at": started_at,
        "duration_seconds": round(time.monotonic() - started, 3),
        "executable": Path(command[0]).name,
        "command_argument_count": len(command),
        "return_code": child.returncode,
        "wrapper_timeout": timed_out,
        "wrapper_cleanup_verified": cleanup_verified,
        "sample_interval_seconds": interval_seconds,
        "sample_limit": MAX_SAMPLES,
        "sample_count": len(samples),
        "samples": samples,
        "privacy_note": "No source text, image pixels, full environment, or process command lines are collected.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--wall-limit", type=float, default=360.0)
    parser.add_argument("--require-idle-gpu", action="store_true")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command and args.command[0] == "--" else args.command
    try:
        result = sample_command(command, interval_seconds=args.interval,
                                max_wall_seconds=args.wall_limit,
                                require_idle_gpu=args.require_idle_gpu)
    except (ValueError, RuntimeError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"telemetry written: {args.output}; return_code={result['return_code']}; "
          f"samples={result['sample_count']}; wrapper_timeout={result['wrapper_timeout']}")
    return result["return_code"] or (124 if result["wrapper_timeout"] else 0)


if __name__ == "__main__":
    raise SystemExit(main())
