"""Shared-GPU resource inspection and `device: auto` selection.

These tests exercise the classification logic against synthetic GPU states
rather than the real device: the decisions must be reproducible on a machine
with no GPU, and a test that depended on what the VM's GPU happened to be
doing would be exactly the kind of contended measurement this module exists
to avoid.
"""
from __future__ import annotations

import pytest

from doc_extraction.utils import resources as res


def _state(free_mib=20000, used_mib=1000, util=0, procs=(), available=True):
    return res.GpuState(
        available=available,
        name="NVIDIA L4",
        driver_version="580.173.02",
        total_mib=23034,
        used_mib=used_mib,
        free_mib=free_mib,
        utilization_pct=util,
        processes=[res.GpuProcess(pid=p, name="python3", used_mib=m) for p, m in procs],
    )


# --- classification -------------------------------------------------------


def test_empty_idle_gpu_is_clear():
    state, reason = res.classify_gpu(_state())
    assert state == res.STATE_CLEAR
    assert "no other compute process" in reason


def test_idle_cotenant_is_limited_not_protected():
    """Another project *holding memory* while idle is shareable. Refusing the
    GPU here would leave an idle accelerator unused, which is the failure
    mode opposite to competing for it."""
    state, reason = res.classify_gpu(_state(free_mib=17810, used_mib=4755, util=2, procs=((9877, 4746),)))
    assert state == res.STATE_LIMITED
    assert "4746 MiB" in reason


def test_busy_cotenant_is_protected():
    """A co-tenant actively computing must not be piled onto."""
    state, reason = res.classify_gpu(_state(free_mib=17810, used_mib=4755, util=100, procs=((9877, 4746),)))
    assert state == res.STATE_PROTECTED
    assert "actively computing" in reason


def test_insufficient_vram_is_protected_even_on_an_empty_gpu():
    """Free VRAM is checked before tenancy: an empty GPU that cannot fit the
    workload is still not usable for it."""
    state, reason = res.classify_gpu(_state(free_mib=1000, used_mib=22000, util=0), required_mib=16000)
    assert state == res.STATE_PROTECTED
    assert "free" in reason


def test_safety_margin_is_enforced():
    """Requesting exactly the free VRAM must fail: the margin exists so a
    co-tenant has somewhere to grow."""
    protected, _ = res.classify_gpu(_state(free_mib=5000), required_mib=5000, safety_margin_mib=1024)
    assert protected == res.STATE_PROTECTED
    ok, _ = res.classify_gpu(_state(free_mib=5000), required_mib=3000, safety_margin_mib=1024)
    assert ok == res.STATE_CLEAR


def test_own_pids_can_be_excluded():
    """A job must not classify itself as a competing tenant."""
    st = _state(free_mib=17810, util=2, procs=((4242, 4746),))
    assert res.classify_gpu(st)[0] == res.STATE_LIMITED
    assert res.classify_gpu(st, exclude_pids={4242})[0] == res.STATE_CLEAR


def test_unavailable_gpu_classifies_unavailable():
    state, _ = res.classify_gpu(res.GpuState(available=False, error="nvidia-smi unavailable"))
    assert state == res.STATE_UNAVAILABLE


# --- device selection -----------------------------------------------------


@pytest.mark.parametrize("explicit", ["cpu", "cuda"])
def test_explicit_device_is_never_overridden_and_never_probes(explicit, monkeypatch):
    """An explicit device is honoured verbatim even if it is a poor choice.
    Silently overriding it would make a recorded benchmark device a lie.

    It must also not probe: the probe is a subprocess, and an explicit run
    should not pay for it or depend on nvidia-smi existing.
    """
    def _boom(*a, **k):  # pragma: no cover - must never be called
        raise AssertionError("explicit device must not probe the GPU")

    monkeypatch.setattr(res, "query_gpu", _boom)
    monkeypatch.setattr(res, "torch_cuda_usable", _boom)

    decision = res.select_device(explicit)
    assert decision.device == explicit
    assert decision.requested == explicit
    assert decision.state == "not_probed"


def test_auto_falls_back_to_cpu_without_a_cuda_torch(monkeypatch):
    monkeypatch.setattr(res, "torch_cuda_usable", lambda: (False, "torch 2.13.0+cpu is a CPU-only build"))
    decision = res.select_device("auto")
    assert decision.device == "cpu"
    assert decision.state == res.STATE_UNAVAILABLE
    assert "CPU-only build" in decision.reason


def test_auto_picks_cuda_on_a_clear_gpu(monkeypatch):
    monkeypatch.setattr(res, "torch_cuda_usable", lambda: (True, "torch cu128"))
    monkeypatch.setattr(res, "query_gpu", lambda index=0: _state())
    decision = res.select_device("auto")
    assert decision.device == "cuda"
    assert decision.state == res.STATE_CLEAR
    assert decision.gpu is not None and decision.gpu.name == "NVIDIA L4"


def test_auto_refuses_a_busy_gpu(monkeypatch):
    """The property that matters most on a shared VM: `auto` must not take a
    GPU another project is actively computing on."""
    monkeypatch.setattr(res, "torch_cuda_usable", lambda: (True, "torch cu128"))
    monkeypatch.setattr(res, "query_gpu", lambda index=0: _state(util=100, procs=((9877, 4746),)))
    decision = res.select_device("auto")
    assert decision.device == "cpu"
    assert decision.state == res.STATE_PROTECTED


def test_auto_shares_an_idle_cotenant_gpu_by_default(monkeypatch):
    monkeypatch.setattr(res, "torch_cuda_usable", lambda: (True, "torch cu128"))
    monkeypatch.setattr(res, "query_gpu", lambda index=0: _state(util=2, procs=((9877, 4746),)))
    assert res.select_device("auto").device == "cuda"


def test_allow_limited_false_requires_an_entirely_clear_gpu(monkeypatch):
    monkeypatch.setattr(res, "torch_cuda_usable", lambda: (True, "torch cu128"))
    monkeypatch.setattr(res, "query_gpu", lambda index=0: _state(util=2, procs=((9877, 4746),)))
    assert res.select_device("auto", allow_limited=False).device == "cpu"


def test_decision_is_serializable_for_run_metadata():
    """The decision is written into metadata.json, so it must survive
    JSON round-tripping with its evidence intact."""
    import json

    decision = res.DeviceDecision(
        device="cpu", requested="auto", state=res.STATE_PROTECTED,
        reason="auto -> cpu: busy", gpu=_state(util=100, procs=((9877, 4746),)),
    )
    restored = json.loads(json.dumps(decision.as_dict()))
    assert restored["device"] == "cpu"
    assert restored["gpu_state"] == res.STATE_PROTECTED
    assert restored["gpu"]["processes"][0]["pid"] == 9877


# --- robustness -----------------------------------------------------------


def test_query_gpu_never_raises_without_nvidia_smi(monkeypatch):
    """A resource probe must not become a new way for extraction to crash."""
    monkeypatch.setattr(res.shutil, "which", lambda _: None)
    state = res.query_gpu()
    assert state.available is False
    assert state.error


def test_query_gpu_survives_unparseable_output(monkeypatch):
    monkeypatch.setattr(res, "_run_nvidia_smi", lambda args: "garbage output\n")
    state = res.query_gpu()
    assert state.available is False
    assert "unparseable" in (state.error or "")
