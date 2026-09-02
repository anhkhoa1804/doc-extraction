"""Shared-GPU resource inspection and device selection.

Why this exists
---------------
This project runs on a shared research VM whose GPU is used by other
projects. Two failure modes matter, and they are opposite:

* Taking the GPU when another job needs it — competing for VRAM can OOM
  *the other project's* run, which is a far worse outcome than this project
  being slow.
* Refusing the GPU when it is free — "shared" is not a reason to leave an
  idle accelerator unused.

So `device: auto` is not "use CUDA if it exists". It inspects what the GPU
is actually doing right now and decides. `device: cpu` and `device: cuda`
keep their exact literal meanings — an explicit choice is never overridden,
because a benchmark that silently changed device would be unreproducible.

Design constraints
------------------
* **No CUDA initialization.** Everything here goes through `nvidia-smi`, a
  subprocess. Importing torch and calling `torch.cuda.*` would create a CUDA
  context and allocate VRAM on the very device we are trying to measure
  politely — the measurement would perturb what it measures.
* **Never fails the run.** Any error (no driver, no `nvidia-smi`, timeout,
  unparseable output) resolves to CPU with a recorded reason. A resource
  probe must not become a new way for extraction to crash.
* **Explainable.** Every decision carries the numbers it was made from, so a
  run's metadata says *why* it landed on a device, not just which one.
"""
from __future__ import annotations

import shutil
import subprocess
import time
from dataclasses import asdict, dataclass, field
from typing import Any

# --- Classification thresholds -------------------------------------------
# A workload of this project's shape (docling layout + Table Transformer,
# one page at a time) was measured peaking at ~16.6 GiB on real benchmark
# pages and ~0.9 GiB on trivial synthetic ones. The default requirement is
# deliberately closer to the *small* end: callers running the heavy path
# should pass their own `required_mib` rather than have a large default
# silently veto the GPU for light work.
DEFAULT_REQUIRED_MIB = 2048

# Leave this much VRAM unclaimed even when we are allowed to proceed, so a
# co-tenant has somewhere to grow. This is a courtesy margin, not a limit we
# can enforce on ourselves.
DEFAULT_SAFETY_MARGIN_MIB = 1024

# Utilization at or above this, with another compute process present, means
# somebody is actively computing — not merely holding memory.
BUSY_UTILIZATION_PCT = 50

STATE_CLEAR = "clear"          # no other compute process, ample VRAM
STATE_LIMITED = "limited"      # co-tenant present, but room remains
STATE_PROTECTED = "protected"  # co-tenant is busy or VRAM is tight — do not compete
STATE_UNAVAILABLE = "unavailable"  # no usable GPU on this machine

_NVIDIA_SMI_TIMEOUT_S = 10


@dataclass
class GpuProcess:
    pid: int
    name: str
    used_mib: int


@dataclass
class GpuState:
    """A point-in-time snapshot. Deliberately a snapshot and not a
    subscription: the GPU can be claimed by another project a second after
    this returns, which is why long runs re-check rather than trusting one
    reading."""

    available: bool
    name: str | None = None
    driver_version: str | None = None
    total_mib: int = 0
    used_mib: int = 0
    free_mib: int = 0
    utilization_pct: int = 0
    # Median of several utilization samples when `samples` > 1. GPU
    # utilization is bursty: a co-tenant measured here sat at a median of 17%
    # with periodic spikes to 100%, so a single reading classifies the same
    # GPU differently depending on the instant it lands in. The median is what
    # decisions are made on; the raw samples are kept for the record.
    utilization_samples: list[int] = field(default_factory=list)
    temperature_c: int | None = None
    processes: list[GpuProcess] = field(default_factory=list)
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["processes"] = [asdict(p) for p in self.processes]
        return d


@dataclass
class DeviceDecision:
    """The resolved device plus the evidence behind it."""

    device: str          # "cpu" | "cuda"
    requested: str       # what the config asked for
    state: str           # one of STATE_*
    reason: str
    gpu: GpuState | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "device": self.device,
            "requested": self.requested,
            "gpu_state": self.state,
            "reason": self.reason,
            "gpu": self.gpu.as_dict() if self.gpu else None,
        }


def _run_nvidia_smi(args: list[str]) -> str | None:
    exe = shutil.which("nvidia-smi")
    if exe is None:
        return None
    try:
        proc = subprocess.run(
            [exe, *args],
            capture_output=True,
            text=True,
            timeout=_NVIDIA_SMI_TIMEOUT_S,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout


def query_gpu(index: int = 0, samples: int = 1, interval_s: float = 0.25) -> GpuState:
    """Snapshot GPU `index` via nvidia-smi. Never raises.

    `samples > 1` reads utilization several times and reports the **median**
    in `utilization_pct`. Memory is not resampled: VRAM held by a co-tenant is
    steady (measured: 4671 MiB across every sample of a minute), whereas its
    utilization swung between 10% and 100%. Sampling costs one subprocess per
    reading, so callers making a real scheduling decision should pay for a few;
    a status display need not.
    """
    fields = "name,driver_version,memory.total,memory.used,memory.free,utilization.gpu,temperature.gpu"
    out = _run_nvidia_smi(
        [f"--query-gpu={fields}", "--format=csv,noheader,nounits", f"--id={index}"]
    )
    if not out or not out.strip():
        return GpuState(available=False, error="nvidia-smi unavailable or returned nothing")

    parts = [p.strip() for p in out.strip().splitlines()[0].split(",")]
    if len(parts) < 7:
        return GpuState(available=False, error=f"unparseable nvidia-smi output: {out.strip()[:120]!r}")

    def _int(value: str) -> int:
        try:
            return int(float(value))
        except ValueError:
            return 0

    state = GpuState(
        available=True,
        name=parts[0] or None,
        driver_version=parts[1] or None,
        total_mib=_int(parts[2]),
        used_mib=_int(parts[3]),
        free_mib=_int(parts[4]),
        utilization_pct=_int(parts[5]),
        temperature_c=_int(parts[6]) or None,
    )

    if samples > 1:
        readings = [state.utilization_pct]
        for _ in range(samples - 1):
            time.sleep(interval_s)
            more = _run_nvidia_smi(
                ["--query-gpu=utilization.gpu", "--format=csv,noheader,nounits", f"--id={index}"]
            )
            if more and more.strip():
                readings.append(_int(more.strip().splitlines()[0]))
        readings.sort()
        state.utilization_samples = readings
        state.utilization_pct = readings[len(readings) // 2]

    # Compute processes are queried separately: the per-GPU query above has
    # no column for them, and their absence is itself meaningful.
    apps = _run_nvidia_smi(
        ["--query-compute-apps=pid,process_name,used_memory", "--format=csv,noheader,nounits"]
    )
    if apps:
        for line in apps.strip().splitlines():
            cells = [c.strip() for c in line.split(",")]
            if len(cells) < 3:
                continue
            try:
                pid = int(cells[0])
            except ValueError:
                continue
            state.processes.append(GpuProcess(pid=pid, name=cells[1], used_mib=_int(cells[2])))
    return state


def classify_gpu(
    state: GpuState,
    required_mib: int = DEFAULT_REQUIRED_MIB,
    safety_margin_mib: int = DEFAULT_SAFETY_MARGIN_MIB,
    exclude_pids: set[int] | None = None,
) -> tuple[str, str]:
    """Classify `state` into one of STATE_*, with a human-readable reason.

    `exclude_pids` lets a caller ignore its own already-running processes so
    a job does not classify itself as a competing tenant.
    """
    if not state.available:
        return STATE_UNAVAILABLE, state.error or "no GPU detected"

    others = [p for p in state.processes if not exclude_pids or p.pid not in exclude_pids]
    needed = required_mib + safety_margin_mib

    if state.free_mib < needed:
        return STATE_PROTECTED, (
            f"only {state.free_mib} MiB free, need {required_mib} MiB "
            f"+ {safety_margin_mib} MiB margin"
        )

    if not others:
        return STATE_CLEAR, (
            f"no other compute process; {state.free_mib} MiB free, "
            f"{state.utilization_pct}% utilization"
        )

    # Someone else is here. Holding memory while idle is tolerable to share;
    # actively computing is not something to pile onto.
    if state.utilization_pct >= BUSY_UTILIZATION_PCT:
        held = sum(p.used_mib for p in others)
        return STATE_PROTECTED, (
            f"{len(others)} other compute process(es) holding {held} MiB at "
            f"{state.utilization_pct}% utilization — actively computing"
        )

    held = sum(p.used_mib for p in others)
    return STATE_LIMITED, (
        f"{len(others)} other compute process(es) holding {held} MiB but only "
        f"{state.utilization_pct}% utilization; {state.free_mib} MiB free"
    )


def torch_cuda_usable() -> tuple[bool, str]:
    """Whether *this environment's* torch build can actually use CUDA.

    Separate from whether a GPU exists, because the two failure modes look
    identical at `torch.cuda.is_available()` and call for opposite fixes: a
    CPU-only wheel on a perfectly good GPU needs a reinstall, while a missing
    GPU does not.
    """
    try:
        import torch
    except Exception as exc:  # noqa: BLE001 - torch is an optional extra
        return False, f"torch not importable ({type(exc).__name__})"
    if not getattr(torch.version, "cuda", None):
        return False, f"torch {torch.__version__} is a CPU-only build (no CUDA runtime)"
    if not torch.cuda.is_available():
        return False, f"torch {torch.__version__} reports no available CUDA device"
    return True, f"torch {torch.__version__} with CUDA {torch.version.cuda}"


def select_device(
    requested: str,
    required_mib: int = DEFAULT_REQUIRED_MIB,
    safety_margin_mib: int = DEFAULT_SAFETY_MARGIN_MIB,
    allow_limited: bool = True,
    exclude_pids: set[int] | None = None,
    samples: int = 5,
) -> DeviceDecision:
    """Resolve a configured device string to a concrete device.

    `cpu` and `cuda` are returned verbatim — an explicit choice is honoured
    even when it is a poor one, because silently overriding it would make a
    recorded benchmark device untrustworthy. Only `auto` inspects the GPU.

    With `auto`:
      * no usable GPU (or CPU-only torch) -> cpu
      * PROTECTED                          -> cpu
      * LIMITED                            -> cuda if `allow_limited`, else cpu
      * CLEAR                              -> cuda
    """
    requested_norm = (requested or "cpu").strip().lower()

    if requested_norm != "auto":
        return DeviceDecision(
            device=requested_norm,
            requested=requested_norm,
            state="not_probed",
            reason="explicit device; GPU not probed",
        )

    usable, torch_reason = torch_cuda_usable()
    if not usable:
        return DeviceDecision(
            device="cpu", requested="auto", state=STATE_UNAVAILABLE,
            reason=f"auto -> cpu: {torch_reason}",
        )

    state = query_gpu(samples=samples)
    classification, reason = classify_gpu(
        state, required_mib=required_mib, safety_margin_mib=safety_margin_mib,
        exclude_pids=exclude_pids,
    )

    if classification == STATE_CLEAR:
        device = "cuda"
    elif classification == STATE_LIMITED:
        device = "cuda" if allow_limited else "cpu"
    else:
        device = "cpu"

    return DeviceDecision(
        device=device, requested="auto", state=classification,
        reason=f"auto -> {device}: {reason}", gpu=state,
    )
