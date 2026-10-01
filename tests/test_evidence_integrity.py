"""Diagnostic fixture suite for the private evidence ledger.

Each ID below names one mechanism. They are deliberately tiny: this is a
falsification/control suite, not a substitute for a corpus benchmark.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from doc_extraction.evaluation.evidence_integrity import (
    Disposition, ObservationLedger, ObservationRecord, OwnershipClaim,
    baseline_phrase_match, evaluate_evidence_integrity, html_cell_texts, truth_aware_candidate, truth_exact_match,
)
from doc_extraction.pipelines.base import (
    LayoutResult, OCRResult, OCRToken, Region, TableResult, run_scanned_page_pipeline,
)
from doc_extraction.schemas.document import Document, RunMetadata
from doc_extraction.schemas.element import BBox
from doc_extraction.schemas.page import Page
from doc_extraction.schemas.table import Cell, Table


FIXTURE_IDS = {
    "ei-01-distinct-identical-text": "identical visible text / distinct observations",
    "ei-02-one-observation-duplicated": "one observation / multiple output refs",
    "ei-03-two-owner-claims": "ambiguous ownership stays unresolved",
    "ei-04-derived-table-cell": "cell derived from table plus OCR",
    "ei-05-empty-structure": "structural-only table recovery",
    "ei-06-baseline-duplicate": "recovered text already in baseline",
    "ei-07-competing-roles": "competing raw layout roles",
    "ei-08-native-ocr-disagreement": "multiple backend observations",
    "ei-09-normalization-loss": "captured observation excluded",
    "ei-10-warning-context": "valid output with warning context",
    "ei-11-unknown-confidence": "null confidence remains null",
    "ei-12-logical-locator": "no page locator / valid logical locator",
}


def _metadata() -> RunMetadata:
    return RunMetadata(input_filename="fixture", input_path="fixture", file_hash_sha256="0", file_type="png",
                       route="image", pipeline="test", backend="fake", timestamp="2026-10-01T00:00:00Z")


def _document(page: Page) -> Document:
    return Document(document_id="fixture", metadata=_metadata(), pages=[page])


def _captured_page(tmp_path: Path):
    from PIL import Image
    tmp_path.mkdir(parents=True, exist_ok=True)
    image = tmp_path / "fixture.png"
    Image.new("RGB", (100, 100), "white").save(image)

    class Layout:
        name = "layout-A"
        def is_available(self): return True
        def analyze(self, _):
            return LayoutResult(regions=[
                Region(BBox(x0=0, y0=0, x1=60, y1=40), "text"),
                Region(BBox(x0=40, y0=0, x1=100, y1=40), "text"),
            ], backend=self.name)
    class OCR:
        name = "ocr-A"
        def is_available(self): return True
        def recognize(self, _):
            return OCRResult(tokens=[
                OCRToken("same", BBox(x0=5, y0=5, x1=20, y1=15), None),
                OCRToken("same", BBox(x0=75, y0=5, x1=90, y1=15), None),
                OCRToken("ambiguous", BBox(x0=45, y0=5, x1=55, y1=15), None),
            ], backend=self.name)
    class Tables:
        name = "tables-A"
        def is_available(self): return False
    ledger = ObservationLedger()
    page = run_scanned_page_pipeline(image, 0, 100, Layout(), OCR(), Tables(), tmp_path / "out", observation_ledger=ledger)
    return page, ledger


def test_fixture_manifest_has_twelve_single_concept_cases():
    assert len(FIXTURE_IDS) == 12
    assert len(set(FIXTURE_IDS.values())) == 12


def test_stable_identity_is_deterministic_and_identical_text_is_not_merged(tmp_path):
    _, one = _captured_page(tmp_path / "one")
    _, two = _captured_page(tmp_path / "two")
    ids_one = [r.observation_id for r in one.records]
    assert ids_one == [r.observation_id for r in two.records]
    same = [r for r in one.records if r.payload_kind == "ocr_token" and r.text == "same"]
    assert len(same) == 2 and same[0].observation_id != same[1].observation_id
    assert all(r.confidence is None for r in same)


def test_ambiguous_ownership_is_unresolved_not_forced(tmp_path):
    page, ledger = _captured_page(tmp_path)
    record = next(r for r in ledger.records if r.text == "ambiguous")
    assert record.disposition is Disposition.UNRESOLVED
    assert len(record.candidate_claims) == 2
    result = evaluate_evidence_integrity(baseline=_document(page), candidate=_document(page), ledger=ledger)
    assert result["misownership"] == result["uncertainty_preserved"] == 1
    assert result["canonical_output_equivalent"]


def test_ledger_serialization_is_deterministic_and_records_accounting(tmp_path):
    page, ledger = _captured_page(tmp_path)
    assert ledger.to_json() == ledger.to_json()
    result = evaluate_evidence_integrity(baseline=_document(page), candidate=_document(page), ledger=ledger)
    assert result["accounting_invariant"]
    assert result["provenance_complete"]


def test_table_cell_derivation_and_empty_structure_are_explicit():
    cell = Cell(row=0, col=0, bbox=BBox(x0=0, y0=0, x1=10, y1=10), text="")
    page = Page(index=0, width=10, height=10, tables=[Table(id="t", n_rows=1, n_cols=1, cells=[cell], source_backend="table")])
    doc = _document(page)
    ledger = ObservationLedger()
    table_id = "table-observation"
    ledger.add(ObservationRecord(table_id, "table", "table", 0, disposition=Disposition.ACCEPTED,
                                 public_object_refs=("page:0:table:t",)))
    ledger.add(ObservationRecord("cell-observation", "table", "table_cell", 0, derivation_refs=(table_id,),
                                 disposition=Disposition.ACCEPTED, public_object_refs=("page:0:table:t:cell:0:0",)))
    result = evaluate_evidence_integrity(baseline=doc, candidate=doc, ledger=ledger)
    assert result["structural_only_recovery"] == 1
    assert result["derivation_complete"] == 1


def test_duplicate_detection_and_novelty_are_normalized_exact_only():
    base = _document(Page(index=0, width=1, height=1))
    candidate = base.model_copy(deep=True)
    # The ledger is sufficient for this evaluator test; canonical objects are
    # intentionally not fabricated just to claim provenance.
    ledger = ObservationLedger()
    ledger.add(ObservationRecord("x", "ocr", "ocr_token", 0, text="Already Present", disposition=Disposition.EXCLUDED))
    result = evaluate_evidence_integrity(baseline=base, candidate=candidate, ledger=ledger)
    assert result["novel_textual_evidence_count"] == 0
    assert result["duplicate_textual_evidence_count"] == 0


def test_records_are_immutable_and_duplicate_identity_rejected():
    record = ObservationRecord("immutable", "ocr", "ocr_token", 0)
    with pytest.raises(Exception):
        record.text = "no"  # type: ignore[misc]
    ledger = ObservationLedger()
    ledger.add(record)
    with pytest.raises(ValueError):
        ledger.add(record)


def test_html_truth_matching_is_normalized_exact_and_not_substring_based():
    cells = html_cell_texts("<table><tr><th> Alpha  Beta </th><td>42</td></tr></table>")
    assert cells == ("alpha beta", "42")
    assert truth_exact_match("alpha\n beta", cells)
    assert not truth_exact_match("alpha", cells)
    assert not truth_exact_match("42.0", cells)


def test_truth_aware_candidate_separates_duplicate_novel_and_structural_only():
    duplicate = truth_aware_candidate(text="Alpha", truth_cells=("alpha",), baseline_texts=("x alpha y",),
                                      ownership_valid=True, provenance_complete=True, structurally_valid=True)
    assert duplicate["correct"] and duplicate["duplicate_baseline"]
    assert not duplicate["novel_correct_textual_evidence"] and duplicate["structural_only_recovery"]
    novel = truth_aware_candidate(text="beta", truth_cells=("beta",), baseline_texts=(), ownership_valid=True,
                                  provenance_complete=True, structurally_valid=False)
    assert novel["novel_correct_textual_evidence"]
    unresolved = truth_aware_candidate(text="beta", truth_cells=(), baseline_texts=(), ownership_valid=True,
                                       provenance_complete=True, structurally_valid=False)
    assert not unresolved["correct"] and not unresolved["novel_correct_textual_evidence"]
    assert baseline_phrase_match("alpha", ("x alpha y",))
