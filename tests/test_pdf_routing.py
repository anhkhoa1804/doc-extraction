"""PDF route selection, including the quality gate that distinguishes
'has text' from 'has *usable* text'.
"""
from __future__ import annotations

import pytest

from doc_extraction.config import PipelineConfig
from doc_extraction.ingest import dispatcher
from tests.fixtures import (
    CLEAN_ENGLISH_TEXT,
    make_empty_pdf,
    make_image,
    make_pdf_with_broken_cmap,
    make_pdf_with_text,
)


def test_digital_pdf_with_trustworthy_text_takes_the_native_route(tmp_path):
    path = make_pdf_with_text(tmp_path / "clean.pdf", [CLEAN_ENGLISH_TEXT] * 2)
    decision = dispatcher.route(path, PipelineConfig())
    assert decision.route == dispatcher.ROUTE_DIGITAL_PDF
    assert decision.text_profile is not None
    assert decision.text_profile.suspicious_page_ratio == 0.0


def test_pdf_with_plentiful_but_corrupt_text_is_rerouted_to_the_visual_path(tmp_path):
    """The core regression this phase exists to prevent: enough characters to
    pass a naive quantity check, but the characters are wrong."""
    path = make_pdf_with_broken_cmap(tmp_path / "garbled.pdf", n_pages=2)
    config = PipelineConfig()
    decision = dispatcher.route(path, config)

    assert decision.route == dispatcher.ROUTE_SCANNED_PDF
    # It must fail on *quality*, not quantity — the text layer is plentiful.
    assert decision.text_profile is not None
    assert decision.text_profile.text_page_ratio == 1.0
    assert decision.text_profile.suspicious_page_ratio > 0.5
    assert "text-quality" in decision.reason


def test_pdf_with_no_text_takes_the_scanned_route(tmp_path):
    path = make_empty_pdf(tmp_path / "blank.pdf", n_pages=2)
    decision = dispatcher.route(path, PipelineConfig())
    assert decision.route == dispatcher.ROUTE_SCANNED_PDF
    assert decision.text_profile is not None
    assert decision.text_profile.text_page_ratio == 0.0


def test_quality_gate_can_be_relaxed_by_config(tmp_path):
    """Routing policy is configuration, not a hardcoded opinion."""
    path = make_pdf_with_broken_cmap(tmp_path / "garbled.pdf", n_pages=2)
    permissive = PipelineConfig(text_quality_max_suspicious_page_ratio=1.0)
    assert dispatcher.route(path, permissive).route == dispatcher.ROUTE_DIGITAL_PDF


def test_route_decision_records_per_page_evidence(tmp_path):
    path = make_pdf_with_broken_cmap(tmp_path / "garbled.pdf", n_pages=1)
    decision = dispatcher.route(path, PipelineConfig())
    per_page = decision.text_profile.per_page
    assert 0 in per_page
    assert per_page[0]["suspicious"] is True
    assert per_page[0]["reasons"]


def test_image_routes_to_image(tmp_path):
    path = make_image(tmp_path / "page.png")
    assert dispatcher.route(path, PipelineConfig()).route == dispatcher.ROUTE_IMAGE


def test_profile_is_serializable(tmp_path):
    import json

    path = make_pdf_with_text(tmp_path / "clean.pdf", [CLEAN_ENGLISH_TEXT])
    profile = dispatcher.route(path, PipelineConfig()).text_profile
    assert "per_page" in json.loads(json.dumps(profile.as_dict()))


def test_real_corpus_business_license_is_detected_as_corrupt(sample_files):
    """Regression lock on the actual observed failure in the real corpus."""
    matches = [p for p in sample_files if p.name == "FROGSLEAP_BUSINESS LICENSE.pdf"]
    if not matches:  # corpus may legitimately differ on another machine
        pytest.skip("FROGSLEAP_BUSINESS LICENSE.pdf not present in local data/ corpus")
    decision = dispatcher.route(matches[0], PipelineConfig())
    assert decision.route == dispatcher.ROUTE_SCANNED_PDF
    assert decision.text_profile.text_page_ratio == 1.0
    assert decision.text_profile.suspicious_page_ratio == 1.0


def test_other_real_corpus_pdfs_are_not_false_positives(sample_files):
    """The quality gate must not reroute clean documents: a false positive
    costs an unnecessary OCR pass and degrades output."""
    config = PipelineConfig()
    candidates = [
        p for p in sample_files
        if p.suffix.lower() == ".pdf" and p.name != "FROGSLEAP_BUSINESS LICENSE.pdf"
    ]
    if not candidates:
        pytest.skip("no local sample PDFs under data/ (private corpus, see data/README.md)")
    for path in candidates:
        decision = dispatcher.route(path, config)
        assert decision.route == dispatcher.ROUTE_DIGITAL_PDF, f"{path.name} was unexpectedly rerouted"
