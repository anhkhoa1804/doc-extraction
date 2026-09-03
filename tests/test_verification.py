"""The shared Verification contract, and the post-hoc pass over an
assembled `Document`.

Reuses the same real-world regression fixtures as `test_text_quality.py`
(the broken-CMap sample is observed output from this repo's own corpus, not
an invented string) — this module deliberately does not re-derive those
signals, only their unified verdict.
"""
from __future__ import annotations

from doc_extraction.ingest.verification import (
    VerificationStatus,
    from_table_confidence,
    from_text_quality,
    verify_document,
    verify_element_text,
)
from doc_extraction.ingest.text_quality import assess_text
from doc_extraction.schemas.document import Document, RunMetadata
from doc_extraction.schemas.element import BBox, Element, ElementType
from doc_extraction.schemas.page import Page
from doc_extraction.schemas.table import Cell, Table
from tests.fixtures import CLEAN_ENGLISH_TEXT, CLEAN_VIETNAMESE_TEXT, GARBLED_CMAP_TEXT


def _element(text, etype=ElementType.TEXT, eid="e0") -> Element:
    return Element(id=eid, type=etype, text=text, source_backend="test")


def _metadata() -> RunMetadata:
    return RunMetadata(
        input_filename="doc.pdf", input_path="doc.pdf", file_hash_sha256="0" * 64,
        file_type="pdf", route="digital_pdf", pipeline="baseline", backend="test",
        model_versions={}, config_snapshot={}, timestamp="2026-01-01T00:00:00Z", device="cpu",
    )


def test_clean_text_verifies_trusted():
    result = from_text_quality(assess_text(CLEAN_ENGLISH_TEXT))
    assert result.status is VerificationStatus.TRUSTED


def test_clean_vietnamese_verifies_trusted():
    """The same corpus-observed Vietnamese sample the text-quality gate
    itself is calibrated against must not be misflagged one layer up."""
    result = from_text_quality(assess_text(CLEAN_VIETNAMESE_TEXT))
    assert result.status is VerificationStatus.TRUSTED


def test_broken_cmap_text_verifies_suspicious_not_invalid():
    """Regression: the exact garbled-CMap sample this project's own corpus
    produced. `assess_text` is deliberately binary/conservative, so this
    must land as SUSPICIOUS — inventing an INVALID tier the underlying gate
    was never calibrated to support would be a false precision."""
    result = from_text_quality(assess_text(GARBLED_CMAP_TEXT))
    assert result.status is VerificationStatus.SUSPICIOUS
    assert result.reasons  # explainable, not an opaque flag


def test_verify_element_text_skips_elements_with_no_text():
    """Not-applicable and checked-and-fine are different claims: an image
    element must not silently read as TRUSTED."""
    assert verify_element_text(_element(None, etype=ElementType.IMAGE)) is None
    assert verify_element_text(_element("")) is None


def test_verify_element_text_treats_short_text_as_not_applicable():
    assert verify_element_text(_element("Hi.")) is None


def test_table_confidence_maps_to_all_three_statuses():
    assert from_table_confidence(None).status is VerificationStatus.TRUSTED
    assert from_table_confidence(1.0).status is VerificationStatus.TRUSTED
    assert from_table_confidence(0.5).status is VerificationStatus.SUSPICIOUS
    assert from_table_confidence(0.25).status is VerificationStatus.INVALID


def test_verify_document_annotates_elements_and_summarizes():
    clean = _element(CLEAN_VIETNAMESE_TEXT, eid="e-clean")
    garbled = _element(GARBLED_CMAP_TEXT, eid="e-garbled")
    page = Page(index=0, width=595, height=842, elements=[clean, garbled])
    document = Document(document_id="doc-1", metadata=_metadata(), pages=[page])

    summary = verify_document(document)

    assert summary.trusted == 1
    assert summary.suspicious == 1
    assert summary.invalid == 0

    assert clean.extra["verification"]["status"] == "trusted"
    assert garbled.extra["verification"]["status"] == "suspicious"
    assert any("e-garbled" in note and "suspicious" in note for note in page.notes)
    assert not any("e-clean" in note for note in page.notes), (
        "a trusted element must not add noise to page.notes — only findings do"
    )


def test_verify_document_counts_table_verdicts_without_duplicating_notes():
    table = Table(
        id="t0", n_rows=1, n_cols=1, source_backend="test", confidence=0.25,
        cells=[Cell(row=0, col=0, text="ỆGTói", bbox=BBox(x0=0, y0=0, x1=10, y1=10))],
    )
    page = Page(index=0, width=595, height=842, tables=[table],
                notes=["table quality: t0 SUSPICIOUS [high] — 1 cell(s) contain runs of more than one style"])
    document = Document(document_id="doc-1", metadata=_metadata(), pages=[page])

    summary = verify_document(document)

    assert summary.invalid == 1
    # The table backend already wrote its own note at extraction time; the
    # verification pass must count it, not add a second note for the same
    # finding.
    assert len(page.notes) == 1
