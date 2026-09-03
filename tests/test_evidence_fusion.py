"""Evidence Fusion v0 — structural correctness, not corpus measurement (see
`experiments/013_evidence_fusion/` for the benchmark)."""
from __future__ import annotations

from doc_extraction.ingest.evidence_fusion import (
    FusionStatus,
    assemble_fused_text,
    fuse_page,
    summarize,
)
from doc_extraction.pipelines.base import OCRToken
from doc_extraction.schemas.element import BBox


def _tok(text: str, x0: float, y0: float, x1: float, y1: float, conf: float | None = None) -> OCRToken:
    return OCRToken(text=text, bbox=BBox(x0=x0, y0=y0, x1=x1, y1=y1), confidence=conf)


def test_agreeing_regions_are_kept_once_not_duplicated():
    docling = [_tok("Hello world", 0, 0, 100, 20)]
    easyocr = [_tok("Hello", 0, 0, 45, 20, 0.9), _tok("world", 50, 0, 100, 20, 0.9)]

    groups = fuse_page(docling, easyocr)

    assert len(groups) == 1
    assert groups[0].decision == "keep_both_agree"
    assert groups[0].status is FusionStatus.TRUSTED
    fused = assemble_fused_text(groups)
    assert fused.count("Hello") == 1
    assert fused.count("world") == 1


def test_disagreeing_regions_are_marked_conflict_not_flattened():
    docling = [_tok("INVOICE NUMBER 4471", 0, 0, 200, 20)]
    easyocr = [_tok("INVALID NLIMBER 447l", 0, 0, 200, 20, 0.55)]

    groups = fuse_page(docling, easyocr)

    assert len(groups) == 1
    g = groups[0]
    assert g.decision == "conflict"
    assert g.status is FusionStatus.CONFLICT
    # both raw readings must survive -- never collapsed into one invented string
    fused = g.fused_text()
    assert "INVOICE NUMBER 4471" in fused
    assert "INVALID NLIMBER 447l" in fused


def test_easyocr_only_region_is_a_singleton_not_dropped():
    """The case that matters most operationally: Docling drops a whole
    region (as the pre-011 traverse_pictures bug did) and only EasyOCR has
    evidence for it. Fusion must surface it, not silently discard it for
    lack of a Docling counterpart."""
    docling: list[OCRToken] = []
    easyocr = [_tok("STT San pham A-100", 0, 0, 150, 20, 0.8)]

    groups = fuse_page(docling, easyocr)

    assert len(groups) == 1
    assert groups[0].decision == "single_easyocr"
    assert "STT San pham A-100" in assemble_fused_text(groups)


def test_low_confidence_singleton_is_flagged_suspicious():
    docling: list[OCRToken] = []
    easyocr = [_tok("blurry guess", 0, 0, 100, 20, 0.1)]

    groups = fuse_page(docling, easyocr)

    assert groups[0].status is FusionStatus.SUSPICIOUS
    assert any("confidence" in r for r in groups[0].reasons)


def test_no_hallucination_fused_words_are_a_subset_of_source_words():
    """Structured fusion only selects/concatenates existing tokens -- it
    cannot invent text the way a generative model could. This is an
    architectural property, verified here, not merely claimed in the
    report."""
    docling = [_tok("Hop dong mua ban", 0, 0, 200, 20)]
    easyocr = [_tok("Hop dong", 0, 0, 90, 20, 0.9), _tok("mua ban", 95, 0, 200, 20, 0.9)]

    groups = fuse_page(docling, easyocr)
    fused_words = set(assemble_fused_text(groups).lower().split())
    source_words = {"hop", "dong", "mua", "ban"}
    assert fused_words <= source_words


def test_agree_branch_preserves_word_only_docling_has():
    """Regression for the exact bug experiment 013 diagnosed: a Docling
    anchor reading "Section 1. Scope This policy to all employees..." and
    an EasyOCR reading "Scope Section This policy applies to all
    employees..." score 0.80 word-Jaccard (correctly judged "agree"), but
    EasyOCR's reading is missing "1" and Docling's is missing "applies".
    Both words must survive fusion -- neither side may be silently
    discarded just because the group as a whole is judged to agree."""
    docling = [_tok(
        "Section 1. Scope This policy to all employees of the company and its branch offices.",
        0, 0, 600, 40,
    )]
    easyocr = [_tok(
        "Scope Section This policy applies to all employees of the company and its branch offices",
        0, 0, 600, 40, 0.9,
    )]

    groups = fuse_page(docling, easyocr)

    assert len(groups) == 1
    assert groups[0].decision == "keep_both_agree"
    fused_words = set(assemble_fused_text(groups).lower().split())
    assert "1" in fused_words or "1." in " ".join(w for w in assemble_fused_text(groups).split())
    assert "applies" in fused_words


def test_agree_branch_does_not_duplicate_when_sides_are_identical():
    """The fix must not regress the common case: when the two sides read
    exactly the same text, only one copy is emitted -- this is what keeps
    fusion's duplicate rate below naive union's."""
    docling = [_tok("Hop dong mua ban hang hoa", 0, 0, 300, 20)]
    easyocr = [_tok("Hop dong mua ban hang hoa", 0, 0, 300, 20, 0.9)]

    groups = fuse_page(docling, easyocr)

    assert groups[0].decision == "keep_both_agree"
    fused = assemble_fused_text(groups)
    assert fused.lower().count("hop dong") == 1


def test_agree_branch_adds_only_the_docling_token_with_new_words():
    """When a group has multiple Docling tokens (e.g. two lines merged into
    one anchor), only the ones carrying words EasyOCR's reading lacks
    should be appended -- a fully-redundant Docling token must not create
    a second copy of text EasyOCR already covers."""
    docling = [
        _tok("Invoice number 4471", 0, 0, 200, 20),  # fully covered by easyocr below
        _tok("Extra unique clause", 0, 25, 200, 45),  # not covered at all
    ]
    easyocr = [_tok("Invoice number 4471", 0, 0, 200, 20, 0.9)]

    groups = fuse_page(docling, easyocr)
    # Both docling tokens overlap the single easyocr token's region enough
    # to land in different anchors in this construction (they are separate
    # Docling anchors), so build the merge directly on one group instead.
    from doc_extraction.ingest.evidence_fusion import EvidenceGroup, EvidenceToken
    from doc_extraction.schemas.element import BBox

    g = EvidenceGroup(
        bbox=BBox(x0=0, y0=0, x1=200, y1=45),
        docling=[
            EvidenceToken("Invoice number 4471", BBox(x0=0, y0=0, x1=200, y1=20), None, "docling", 0),
            EvidenceToken("Extra unique clause", BBox(x0=0, y0=25, x1=200, y1=45), None, "docling", 1),
        ],
        easyocr=[EvidenceToken("Invoice number 4471", BBox(x0=0, y0=0, x1=200, y1=20), 0.9, "easyocr", 0)],
        decision="keep_both_agree",
    )
    merged = g.fused_text()
    assert merged.count("Invoice number 4471") == 1
    assert "Extra unique clause" in merged


def test_summarize_counts_match_decisions():
    docling = [_tok("Agree text", 0, 0, 100, 20), _tok("Only docling", 0, 30, 100, 50)]
    easyocr = [_tok("Agree text", 0, 0, 100, 20, 0.9), _tok("Only easyocr", 0, 60, 100, 80, 0.9)]

    groups = fuse_page(docling, easyocr)
    summary = summarize(groups)

    assert summary.n_groups == 3
    assert summary.n_agree == 1
    assert summary.n_single_docling == 1
    assert summary.n_single_easyocr == 1
    assert summary.n_conflict == 0
    assert summary.conflict_rate == 0.0


def test_reading_order_is_top_to_bottom():
    docling = [_tok("Second line", 0, 50, 100, 70), _tok("First line", 0, 0, 100, 20)]
    groups = fuse_page(docling, [])
    texts = [g.docling_text for g in groups]
    assert texts == ["First line", "Second line"]
