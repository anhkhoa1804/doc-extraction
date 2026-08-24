"""Environment / accelerator diagnostics.

Exists because this project's compute target moved off the development
laptop and onto a GPU host: the single most common bring-up failure is a
config that *says* `device: cuda` while the installed torch is a CPU-only
build, or a driver too old for the wheel's CUDA runtime. That failure is
silent — models load on CPU and the run merely takes 30x longer — so it is
worth one explicit command that answers "will this host actually do GPU
work, and with which backends" before anyone starts a multi-hour benchmark.

Deliberately import-safe: every probe is individually guarded, so this runs
on a machine with no torch, no CUDA and none of the optional backends
installed and still produces a complete report rather than a traceback.
"""
from __future__ import annotations

import importlib.util
import os
import platform
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Any

# Optional backends, mapped to the import name that proves availability.
# Kept in sync with pyproject's optional-dependencies by intent, not by
# import — checking a spec must never trigger the (heavy) import itself.
_OPTIONAL_BACKENDS: dict[str, str] = {
    "docling": "docling",
    "easyocr": "easyocr",
    "transformers": "transformers",
    "torch": "torch",
    "mineru": "mineru",
    "mineru_vl_utils": "mineru_vl_utils",
    "paddleocr": "paddleocr",
}


@dataclass
class EnvironmentReport:
    python_version: str
    platform: str
    torch_version: str | None = None
    torch_cuda_build: str | None = None
    cuda_available: bool = False
    gpus: list[dict[str, Any]] = field(default_factory=list)
    driver_cuda_version: str | None = None
    available_backends: dict[str, bool] = field(default_factory=dict)
    cache_dirs: dict[str, str | None] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def gpu_ready(self) -> bool:
        """Whether real GPU inference is possible here — a CUDA-enabled
        torch build AND a device it can actually see. `device: cuda` in a
        config is a request, not evidence."""
        return self.cuda_available and bool(self.gpus)

    def to_dict(self) -> dict[str, Any]:
        return {
            "python_version": self.python_version,
            "platform": self.platform,
            "torch_version": self.torch_version,
            "torch_cuda_build": self.torch_cuda_build,
            "cuda_available": self.cuda_available,
            "gpu_ready": self.gpu_ready,
            "gpus": self.gpus,
            "driver_cuda_version": self.driver_cuda_version,
            "available_backends": self.available_backends,
            "cache_dirs": self.cache_dirs,
            "warnings": self.warnings,
        }


def _probe_nvidia_smi() -> tuple[str | None, list[dict[str, Any]]]:
    """Driver-reported CUDA version and GPUs, via nvidia-smi.

    Read separately from torch on purpose: a host can have a working driver
    and GPUs while torch is a CPU-only wheel, and distinguishing "no GPU
    hardware" from "GPU present but torch cannot use it" is exactly the
    diagnosis this module exists to make.
    """
    if shutil.which("nvidia-smi") is None:
        return None, []
    gpus: list[dict[str, Any]] = []
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,driver_version",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=30, check=False,
        )
        if out.returncode == 0:
            for line in out.stdout.strip().splitlines():
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 3:
                    gpus.append({
                        "name": parts[0],
                        "memory_total_mib": _safe_int(parts[1]),
                        "driver_version": parts[2],
                    })
    except (OSError, subprocess.SubprocessError):
        return None, gpus

    driver_cuda = None
    try:
        out = subprocess.run(["nvidia-smi"], capture_output=True, text=True, timeout=30, check=False)
        for line in out.stdout.splitlines():
            if "CUDA Version" in line:
                driver_cuda = line.split("CUDA Version:")[-1].strip().rstrip("| ").strip()
                break
    except (OSError, subprocess.SubprocessError):
        pass
    return driver_cuda, gpus


def _safe_int(value: str) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def collect_environment(min_vram_gib: float = 20.0) -> EnvironmentReport:
    """Probe this host. `min_vram_gib` is the bar a GPU must clear to be
    called adequate for the document-VLM tier (A30 = 24 GiB; the 20 GiB
    default leaves headroom for reporting a 24 GiB card as adequate while
    still flagging a 16 GiB one)."""
    report = EnvironmentReport(
        python_version=platform.python_version(),
        platform=platform.platform(),
    )

    for name, module in _OPTIONAL_BACKENDS.items():
        try:
            report.available_backends[name] = importlib.util.find_spec(module) is not None
        except (ImportError, ValueError):
            report.available_backends[name] = False

    if report.available_backends.get("torch"):
        try:
            import torch

            report.torch_version = torch.__version__
            report.torch_cuda_build = torch.version.cuda
            report.cuda_available = bool(torch.cuda.is_available())
            if report.cuda_available:
                for i in range(torch.cuda.device_count()):
                    props = torch.cuda.get_device_properties(i)
                    report.gpus.append({
                        "index": i,
                        "name": props.name,
                        "memory_total_mib": int(props.total_memory / (1024 ** 2)),
                        "capability": f"{props.major}.{props.minor}",
                        "source": "torch",
                    })
        except Exception as exc:  # noqa: BLE001 — diagnostics must never crash
            report.warnings.append(f"torch probe failed: {type(exc).__name__}: {exc}")

    driver_cuda, smi_gpus = _probe_nvidia_smi()
    report.driver_cuda_version = driver_cuda
    if smi_gpus and not report.gpus:
        report.gpus = [{**g, "source": "nvidia-smi"} for g in smi_gpus]

    report.cache_dirs = {
        "HF_HOME": os.environ.get("HF_HOME"),
        "HUGGINGFACE_HUB_CACHE": os.environ.get("HUGGINGFACE_HUB_CACHE"),
        "TORCH_HOME": os.environ.get("TORCH_HOME"),
        "DOC_EXTRACTION_CACHE": os.environ.get("DOC_EXTRACTION_CACHE"),
    }

    # --- interpretation, not just raw facts -----------------------------
    if report.torch_version and report.torch_cuda_build is None:
        report.warnings.append(
            f"torch {report.torch_version} is a CPU-only build (torch.version.cuda is None). "
            "A config setting device: cuda will silently run on CPU. Install a CUDA wheel."
        )
    if smi_gpus and not report.cuda_available:
        report.warnings.append(
            "nvidia-smi reports GPU(s) but torch.cuda.is_available() is False — "
            "usually a CPU-only torch build or a driver older than the wheel's CUDA runtime."
        )
    if not smi_gpus and not report.cuda_available:
        report.warnings.append("No GPU detected. This host is development-only for model work.")
    for gpu in report.gpus:
        mib = gpu.get("memory_total_mib")
        if mib is not None and mib / 1024 < min_vram_gib:
            report.warnings.append(
                f"GPU '{gpu.get('name')}' has {mib} MiB (~{mib / 1024:.1f} GiB), "
                f"below the {min_vram_gib:.0f} GiB bar for the document-VLM tier. "
                "Smaller models may still fit; see docs/gpu_host.md."
            )
    if not any(report.cache_dirs.values()):
        report.warnings.append(
            "No model-cache env var set (HF_HOME etc.). On a shared GPU host, point these at "
            "a large shared volume or every user re-downloads multi-GB weights."
        )
    return report


def format_report(report: EnvironmentReport) -> str:
    lines = ["doc_extraction environment report", "=" * 34, ""]
    lines.append(f"Python:   {report.python_version}")
    lines.append(f"Platform: {report.platform}")
    lines.append("")
    lines.append(f"torch:            {report.torch_version or 'not installed'}")
    lines.append(f"torch CUDA build: {report.torch_cuda_build or 'CPU-only'}")
    lines.append(f"driver CUDA:      {report.driver_cuda_version or 'unknown'}")
    lines.append(f"GPU usable:       {'YES' if report.gpu_ready else 'NO'}")
    if report.gpus:
        for gpu in report.gpus:
            mib = gpu.get("memory_total_mib")
            vram = f"{mib} MiB (~{mib / 1024:.1f} GiB)" if mib else "unknown VRAM"
            lines.append(f"  - {gpu.get('name', '?')}: {vram} [{gpu.get('source', '?')}]")
    else:
        lines.append("  (none detected)")
    lines.append("")
    lines.append("Backends importable:")
    for name, ok in sorted(report.available_backends.items()):
        lines.append(f"  {'OK ' if ok else '-- '} {name}")
    lines.append("")
    lines.append("Model cache dirs:")
    for name, value in report.cache_dirs.items():
        lines.append(f"  {name}: {value or '(unset)'}")
    if report.warnings:
        lines.append("")
        lines.append("Warnings:")
        for w in report.warnings:
            lines.append(f"  ! {w}")
    return "\n".join(lines)
