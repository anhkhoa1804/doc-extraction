"""Regression test for the device-resolution gap found by Milestone 034a's
OmniDocBench benchmark run (experiments/034a_omnidocbench_snapshot/
device_resolution_diagnosis.json): a caller of `process_file()` with
`config.device == "auto"` must never let the literal string "auto" reach a
backend constructor (TableTransformerBackend crashes on `.to("auto")`;
DoclingBackend silently tolerates it, which is why the smoke test's table
stage failed first).

The fix is a guard at the top of `process_file()` — before route dispatch,
so this is exercised on a fast native-route input, no model inference
needed. `resolve_device()`'s own resolution logic is already covered by
tests/test_resources.py; this test covers only the NEW invariant: that
process_file() actually calls it when the caller didn't.
"""
from __future__ import annotations

import pytest

from doc_extraction import cli
from doc_extraction.config import PipelineConfig
from tests.fixtures import make_pdf_with_text

_LONG_TEXT = ("This is a clean, unambiguous digital PDF paragraph. " * 6).strip()


def test_process_file_resolves_auto_device_before_any_backend_is_touched(tmp_path, monkeypatch):
    """The core regression: device="auto" must not survive process_file()."""
    monkeypatch.setattr("doc_extraction.utils.resources.torch_cuda_usable",
                        lambda: (False, "test: forced no CUDA"))
    path = make_pdf_with_text(tmp_path / "doc.pdf", [_LONG_TEXT])
    config = PipelineConfig(device="auto")

    cli.process_file(path, config, output_root=tmp_path / "out")

    # resolve_device() mutates the SAME config object it's given; if
    # process_file() never called it, config.device would still read "auto"
    # here, and any backend constructed along the way would have received
    # the literal string "auto" too.
    assert config.device == "cpu"


def test_process_file_does_not_reprobe_an_already_resolved_device(tmp_path, monkeypatch):
    """Guard must be conditional: a caller (cmd_run/cmd_compare, or a
    research script that calls resolve_device() itself) that already
    resolved "auto" to a concrete device must not have process_file()
    silently re-probe the GPU and clobber the recorded decision."""
    def _boom(*a, **k):
        raise AssertionError("process_file() must not re-resolve an already-concrete device")

    monkeypatch.setattr("doc_extraction.utils.resources.torch_cuda_usable", _boom)
    monkeypatch.setattr("doc_extraction.utils.resources.query_gpu", _boom)

    path = make_pdf_with_text(tmp_path / "doc.pdf", [_LONG_TEXT])
    config = PipelineConfig(device="cpu")  # already concrete, never "auto"

    cli.process_file(path, config, output_root=tmp_path / "out")

    assert config.device == "cpu"


@pytest.mark.parametrize("explicit_device", ["cpu", "cuda"])
def test_process_file_honours_an_explicit_device_verbatim(tmp_path, monkeypatch, explicit_device):
    """Explicit cpu/cuda must never be overridden or probed, per
    select_device()'s own documented contract (tests/test_resources.py
    test_explicit_device_is_never_overridden_and_never_probes) — the guard
    in process_file() must preserve this, not just handle "auto"."""
    def _boom(*a, **k):
        raise AssertionError("an explicit device must not probe the GPU")

    monkeypatch.setattr("doc_extraction.utils.resources.torch_cuda_usable", _boom)
    monkeypatch.setattr("doc_extraction.utils.resources.query_gpu", _boom)

    path = make_pdf_with_text(tmp_path / "doc.pdf", [_LONG_TEXT])
    config = PipelineConfig(device=explicit_device)

    cli.process_file(path, config, output_root=tmp_path / "out")

    assert config.device == explicit_device
