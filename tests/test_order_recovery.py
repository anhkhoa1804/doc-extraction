"""Order Recovery v1 -- page-level orchestration of the order-consistency
signal + line-cluster reconstruction (experiment 018). Stubs
`easyocr.Reader`, same convention as `test_scan_recovery.py`."""
from __future__ import annotations

from doc_extraction.backends.easyocr_backend import EasyOCRBackend
from doc_extraction.ingest.order_recovery import (
    line_cluster_reconstruction,
    order_consistency,
    recover_page_order,
    word_jaccard,
)
from doc_extraction.pipelines.base import OCRToken
from doc_extraction.schemas.element import BBox, Element, ElementType
from doc_extraction.schemas.page import Page


def _tok(text: str, x0: float, y0: float, x1: float, y1: float) -> OCRToken:
    return OCRToken(text=text, bbox=BBox(x0=x0, y0=y0, x1=x1, y1=y1))


def _detection(text, conf, x0, y0, x1, y1):
    return ([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], text, conf)


def _page_with(text: str, bbox: BBox) -> Page:
    page = Page(index=0, width=1000, height=1000, dpi=200)
    page.elements.append(Element(
        id="e0", type=ElementType.TEXT, text=text, bbox=bbox,
        page_number=1, source_backend="docling",
    ))
    return page


class _StubReader:
    def __init__(self, detections):
        self.detections = detections

    def readtext(self, path, detail=1):
        return self.detections


# --- order_consistency: pure signal tests -----------------------------------

def test_order_consistency_perfect_match_is_1():
    assert order_consistency("Kính gửi Phòng Tài chính", "Kính gửi Phòng Tài chính") == 1.0


def test_order_consistency_reversed_is_low():
    assert order_consistency("Kính gửi Phòng Tài chính", "chính Tài Phòng gửi Kính") < 0.5


def test_order_consistency_one_word_transposed_is_high_but_not_1():
    """A single displaced word among many should score close to 1.0 but
    not exactly -- this is the real signature measured on hc_scan_vi's
    motto line ('Tự' displaced from position 3 to the end)."""
    score = order_consistency("Độc lập do Hạnh phúc Tự", "Độc lập Tự do Hạnh phúc")
    assert 0.7 < score < 1.0


def test_order_consistency_insensitive_to_word_jaccard_difference():
    """Two sequences can have identical order_consistency behavior
    regardless of how much word_jaccard differs -- the two signals must
    stay genuinely independent, or this module is just word-Jaccard
    again with extra steps."""
    same_order_high_jaccard = order_consistency("a b c", "a b c d")
    same_order_low_jaccard = order_consistency("a b c", "a b c")
    assert same_order_high_jaccard == same_order_low_jaccard == 1.0


# --- line_cluster_reconstruction ---------------------------------------------

def test_line_cluster_reconstruction_orders_same_line_by_x_not_by_y0():
    """Same-line tokens with slightly different y0 (measured on real
    corpus data: 449.0/450.9/452.0) must still sort by x, not by their
    slightly-different y0 -- this is the exact case a naive (y0, x0)
    tuple sort gets wrong."""
    region = BBox(x0=0, y0=400, x1=1000, y1=550)
    tokens = [
        _tok("thu", 368, 449.0, 400, 497),
        _tok("phai", 293, 450.9, 320, 495),
        _tok("no", 161, 452.0, 200, 496),
    ]
    result = line_cluster_reconstruction(tokens, region)
    assert result == "no phai thu"


def test_line_cluster_reconstruction_orders_lines_top_to_bottom():
    region = BBox(x0=0, y0=0, x1=1000, y1=200)
    tokens = [
        _tok("second", 0, 100, 100, 130),
        _tok("first", 0, 0, 100, 30),
    ]
    result = line_cluster_reconstruction(tokens, region)
    assert result == "first second"


def test_line_cluster_reconstruction_empty_when_nothing_in_region():
    region = BBox(x0=0, y0=0, x1=100, y1=100)
    tokens = [_tok("far away", 500, 500, 600, 520)]
    assert line_cluster_reconstruction(tokens, region) == ""


# --- recover_page_order: page-level orchestration ---------------------------

def test_scrambled_element_is_corrected():
    """The real hc_scan_vi motto case, reproduced with synthetic tokens:
    Docling's element has the words in the wrong order; EasyOCR's
    per-line tokens (all on one physical line here) are correct, and the
    reconstruction should replace Docling's scrambled reading."""
    bbox = BBox(x0=0, y0=0, x1=900, y1=50)
    page = _page_with("Doc lap do Hanh phuc Tu", bbox)
    backend = EasyOCRBackend(device="cpu")
    backend._reader = _StubReader([
        _detection("Doc lap", 0.9, 0, 0, 200, 50),
        _detection("Tu do", 0.9, 220, 0, 400, 50),
        _detection("Hanh phuc", 0.9, 420, 0, 600, 50),
    ])

    summary = recover_page_order(page, "unused.png", backend, page_width=1000, page_height=1000)

    assert summary.replaced == 1
    assert page.elements[0].text == "Doc lap Tu do Hanh phuc"


def test_pure_word_order_agreement_is_not_touched():
    """Already-correct order must not be replaced -- order_consistency
    is at ceiling, nothing to fix."""
    bbox = BBox(x0=0, y0=0, x1=900, y1=50)
    page = _page_with("Doc lap Tu do Hanh phuc", bbox)
    backend = EasyOCRBackend(device="cpu")
    backend._reader = _StubReader([_detection("Doc lap Tu do Hanh phuc", 0.9, 0, 0, 900, 50)])

    summary = recover_page_order(page, "unused.png", backend, page_width=1000, page_height=1000)

    assert summary.replaced == 0
    assert page.elements[0].text == "Doc lap Tu do Hanh phuc"


def test_low_jaccard_content_disagreement_is_not_reordered():
    """The cmb_scan_multicol_en failure mode: EasyOCR's own coverage of
    the region is incomplete, so its reconstruction disagrees with
    Docling on WHICH words are present (not just order). Must be
    excluded by the jaccard precondition -- reordering a content
    disagreement would make things worse, not better."""
    bbox = BBox(x0=0, y0=0, x1=900, y1=50)
    page = _page_with(
        "Section 1 Scope This policy applies to all employees Section 2 Approval authority",
        bbox,
    )
    backend = EasyOCRBackend(device="cpu")
    backend._reader = _StubReader([
        _detection("all employees of the company", 0.9, 0, 0, 500, 50),
        _detection("Section 1 Scope", 0.9, 520, 0, 700, 50),
    ])

    summary = recover_page_order(page, "unused.png", backend, page_width=1000, page_height=1000)

    assert summary.replaced == 0
    assert page.elements[0].text == (
        "Section 1 Scope This policy applies to all employees Section 2 Approval authority"
    )
    assert any("content disagreement" in r for r in summary.records[0].reasons)


def test_trusted_element_with_no_easyocr_evidence_is_never_touched():
    bbox = BBox(x0=0, y0=0, x1=100, y1=20)
    page = _page_with("Some clean text", bbox)
    backend = EasyOCRBackend(device="cpu")
    backend._reader = _StubReader([_detection("unrelated", 0.9, 500, 500, 600, 520)])

    summary = recover_page_order(page, "unused.png", backend, page_width=1000, page_height=1000)

    assert summary.replaced == 0
    assert page.elements[0].text == "Some clean text"


def test_word_jaccard_helper_is_order_insensitive_by_contrast():
    """Documents the deliberate contrast this module is built around:
    word_jaccard (imported here for reference/tests) reports perfect
    agreement on a pure reordering; order_consistency does not."""
    a, b = "Kinh Phong Tai chinh Ke toan gui", "Kinh gui Phong Tai chinh Ke toan"
    assert word_jaccard(a, b) == 1.0
    assert order_consistency(a, b) < 1.0
