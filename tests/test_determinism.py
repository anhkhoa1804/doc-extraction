"""Repeated runs over the same input must produce the same IR.

Determinism is a precondition for the rest of the research programme: if two
runs of an unchanged pipeline can disagree, then a measured difference
between a baseline and a candidate cannot be attributed to the change. This
locks that property for the routes that contain no model — which are exactly
the routes where determinism is achievable and therefore worth asserting.

The visual route is deliberately *not* covered here: it depends on model
kernels whose determinism this project does not control, and asserting it
would either be flaky or force `torch.use_deterministic_algorithms`, which
is a real performance decision rather than a test detail.
"""
from __future__ import annotations

import json

from doc_extraction.cli import process_file
from doc_extraction.config import PipelineConfig
from tests.fixtures import (
    CLEAN_ENGLISH_TEXT,
    make_docx,
    make_pdf_with_table,
    make_pdf_with_text,
    make_pptx,
    make_xlsx,
)

# Fields that legitimately vary between two runs of the same input: wall
# clock, measured durations, and the paths the operator happened to choose.
_RUN_EXTRINSIC = {
    "timestamp", "runtime_seconds", "input_path", "output_path",
    "input_dir", "output_dir", "rendered_image_path",
}


def _canonical(obj):
    if isinstance(obj, dict):
        return {k: _canonical(v) for k, v in sorted(obj.items()) if k not in _RUN_EXTRINSIC}
    if isinstance(obj, list):
        return [_canonical(v) for v in obj]
    return obj


def _run_twice(path, tmp_path):
    config = PipelineConfig(device="cpu")
    docs = []
    for i in (1, 2):
        document = process_file(path, config, output_root=tmp_path / f"run{i}")
        docs.append(json.loads(document.model_dump_json()))
    return docs


def test_digital_pdf_extraction_is_deterministic(tmp_path):
    # Both pages need enough text to clear the quantity gate
    # (digital_pdf_min_chars_per_page=40, page ratio 0.6). A short second page
    # drops the ratio to 0.5 and the document is routed to scanned_pdf — which
    # is the router behaving correctly, but means the test would silently
    # exercise the visual route instead of the native one it names.
    path = make_pdf_with_text(tmp_path / "in.pdf", [CLEAN_ENGLISH_TEXT, CLEAN_ENGLISH_TEXT])
    first, second = _run_twice(path, tmp_path)
    assert first["metadata"]["route"] == "digital_pdf", "fixture must exercise the native route"
    assert _canonical(first) == _canonical(second)


def test_native_table_extraction_is_deterministic(tmp_path):
    """Table cell ordering and geometry must not vary between runs."""
    path = make_pdf_with_table(tmp_path / "table.pdf")
    first, second = _run_twice(path, tmp_path)
    assert _canonical(first) == _canonical(second)
    assert first["pages"][0]["tables"], "fixture should produce a table to compare"


def test_reading_order_is_stable_across_runs(tmp_path):
    """The ordering heuristic is documented as a pure function of its input;
    an unstable sort would silently break backend-disagreement analysis."""
    path = make_pdf_with_text(tmp_path / "in.pdf", [CLEAN_ENGLISH_TEXT])
    first, second = _run_twice(path, tmp_path)
    assert first["pages"][0]["reading_order"] == second["pages"][0]["reading_order"]


def test_office_routes_are_deterministic(tmp_path):
    for name, make in (("d.docx", make_docx), ("x.xlsx", make_xlsx), ("p.pptx", make_pptx)):
        path = make(tmp_path / name)
        first, second = _run_twice(path, tmp_path / name.replace(".", "_"))
        assert _canonical(first) == _canonical(second), f"{name} was not deterministic"


def test_document_id_is_stable_for_identical_content(tmp_path):
    """`document_id` embeds a content hash, so two runs of the same bytes must
    land in the same output directory — that is what makes re-runs
    comparable rather than accumulating."""
    path = make_pdf_with_text(tmp_path / "in.pdf", [CLEAN_ENGLISH_TEXT])
    first, second = _run_twice(path, tmp_path)
    assert first["document_id"] == second["document_id"]
