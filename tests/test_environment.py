"""Tests for environment/accelerator diagnostics.

These matter because this command is the first thing run on a new GPU host,
and its whole job is to catch the *silent* failure: a config requesting
`device: cuda` on a CPU-only torch build runs fine and is merely ~30x
slower. A diagnostic that itself crashes, or that reports "GPU ready" when
torch cannot use the GPU, would be worse than none.
"""
from __future__ import annotations

from doc_extraction.utils.environment import (
    EnvironmentReport,
    collect_environment,
    format_report,
)


def test_collect_environment_runs_and_reports_core_facts():
    """Must never raise, whatever is or isn't installed."""
    report = collect_environment()

    assert report.python_version
    assert report.platform
    assert isinstance(report.available_backends, dict)
    assert "torch" in report.available_backends
    assert isinstance(report.warnings, list)


def test_gpu_ready_requires_both_cuda_and_a_device():
    """`device: cuda` in a config is a request, not evidence. gpu_ready must
    require a CUDA-capable torch AND a visible device -- reporting ready on
    either alone is the exact mistake this module exists to prevent."""
    both = EnvironmentReport(python_version="3.12", platform="x", cuda_available=True,
                             gpus=[{"name": "A30", "memory_total_mib": 24576}])
    assert both.gpu_ready is True

    cuda_but_no_device = EnvironmentReport(python_version="3.12", platform="x",
                                           cuda_available=True, gpus=[])
    assert cuda_but_no_device.gpu_ready is False

    device_but_no_cuda = EnvironmentReport(
        python_version="3.12", platform="x", cuda_available=False,
        gpus=[{"name": "RTX 3050", "memory_total_mib": 4096}],
    )
    assert device_but_no_cuda.gpu_ready is False, (
        "a GPU visible only to nvidia-smi, with a CPU-only torch, is NOT usable"
    )


def test_report_to_dict_is_json_serializable():
    import json

    payload = collect_environment().to_dict()
    json.dumps(payload)  # must not raise
    assert "gpu_ready" in payload and "warnings" in payload


def test_format_report_includes_the_decisive_lines():
    text = format_report(collect_environment())

    assert "GPU usable:" in text
    assert "torch CUDA build:" in text
    assert "Backends importable:" in text


def test_format_report_handles_a_bare_report_with_no_probes():
    """A host with no torch, no GPU and nothing installed must still format."""
    text = format_report(EnvironmentReport(python_version="3.12", platform="linux"))

    assert "not installed" in text
    assert "(none detected)" in text


def test_low_vram_gpu_is_flagged_against_the_vlm_tier_bar():
    report = collect_environment(min_vram_gib=1000.0)  # nothing can clear this

    if report.gpus:
        assert any("below the" in w for w in report.warnings)


def test_cpu_only_torch_build_is_explicitly_warned_about():
    """The silent failure mode: torch installed, importable, and useless for
    GPU work. If torch is a CPU build here, the warning must say so."""
    report = collect_environment()

    if report.torch_version and report.torch_cuda_build is None:
        assert any("CPU-only build" in w for w in report.warnings)
