"""Scan Recovery v1 — page-level orchestration of already-shipped
primitives (`assess_ocr_agreement` as trigger, `evidence_fusion.fuse_page`
as action). Stubs `easyocr.Reader` (no GPU/model needed), same convention
as `test_easyocr_backend.py`."""
from __future__ import annotations

from doc_extraction.backends.easyocr_backend import EasyOCRBackend
from doc_extraction.ingest.scan_recovery import recover_page_elements
from doc_extraction.schemas.element import BBox, Element, ElementType
from doc_extraction.schemas.page import Page


class _StubReader:
    def __init__(self, detections):
        self.detections = detections

    def readtext(self, path, detail=1):
        return self.detections


def _detection(text, conf, x0, y0, x1, y1):
    return ([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], text, conf)


def _page_with(text: str, bbox: BBox) -> Page:
    page = Page(index=0, width=1000, height=1000, dpi=200)
    page.elements.append(Element(
        id="e0", type=ElementType.TEXT, text=text, bbox=bbox,
        page_number=1, source_backend="docling",
    ))
    return page


def test_word_set_difference_triggers_and_can_be_recovered():
    """`assess_ocr_agreement` is word-Jaccard -- order-insensitive by
    construction (confirmed empirically against the real hc_scan_vi case:
    reordering alone does not lower Jaccard agreement, so pure word-order
    scrambling is NOT a defect this trigger can catch -- see
    experiments/015_scan_recovery/README.md). What it *can* catch is a
    genuine word-set difference: Docling's element is missing a word
    EasyOCR's reading has. That should trigger, and fusion's own
    single/dual-source logic should recover the missing word."""
    bbox = BBox(x0=0, y0=0, x1=200, y1=20)
    page = _page_with("4471", bbox)  # missing "Invoice number" entirely
    backend = EasyOCRBackend(device="cpu")
    backend._reader = _StubReader([_detection("Invoice number 4471", 0.9, 0, 0, 200, 20)])

    summary = recover_page_elements(page, "unused.png", backend, page_width=1000, page_height=1000)

    assert any(r.trigger == "agreement_low" for r in summary.records)
    assert summary.replaced == 1
    assert "4471" in page.elements[0].text


def test_pure_word_reordering_does_not_trigger():
    """Documents the limitation directly: identical word sets in a
    different order score perfect word-Jaccard agreement, so this
    mechanism does not fire for order-only defects. Not a bug in this
    module -- a property of the trigger signal it reuses, worth locking in
    as an explicit, intentional non-goal rather than an accidental gap."""
    bbox = BBox(x0=0, y0=0, x1=400, y1=20)
    page = _page_with("Kinh Phong Tai chinh Ke toan gui", bbox)
    backend = EasyOCRBackend(device="cpu")
    backend._reader = _StubReader([_detection("Kinh gui Phong Tai chinh Ke toan", 0.9, 0, 0, 400, 20)])

    summary = recover_page_elements(page, "unused.png", backend, page_width=1000, page_height=1000)

    assert summary.replaced == 0
    assert summary.skipped_not_suspicious == 1
    assert page.elements[0].text == "Kinh Phong Tai chinh Ke toan gui"


def test_trusted_element_is_never_touched():
    """No EasyOCR tokens land in the element's bbox (e.g. it's off in a
    completely different part of the page) -- must not attempt recovery
    without cross-check evidence."""
    bbox = BBox(x0=0, y0=0, x1=100, y1=20)
    page = _page_with("Some clean text", bbox)
    backend = EasyOCRBackend(device="cpu")
    backend._reader = _StubReader([_detection("unrelated", 0.9, 500, 500, 600, 520)])

    summary = recover_page_elements(page, "unused.png", backend, page_width=1000, page_height=1000)

    assert summary.replaced == 0
    assert page.elements[0].text == "Some clean text"
    assert summary.skipped_not_suspicious == 1


def test_agreeing_element_is_not_replaced_needlessly():
    """Old and new readings already agree closely -- assess_ocr_agreement
    should report TRUSTED, and recovery must skip it (nothing to fix)."""
    bbox = BBox(x0=0, y0=0, x1=200, y1=20)
    page = _page_with("Invoice number 4471", bbox)
    backend = EasyOCRBackend(device="cpu")
    backend._reader = _StubReader([_detection("Invoice number 4471", 0.9, 0, 0, 200, 20)])

    summary = recover_page_elements(page, "unused.png", backend, page_width=1000, page_height=1000)

    assert summary.replaced == 0
    assert page.elements[0].text == "Invoice number 4471"


def test_conflicting_recovery_is_not_accepted():
    """Agreement is low (triggers), but the fused evidence itself resolves
    to CONFLICT (the two readings genuinely diverge, not just reorder) --
    must keep the old text rather than accept an unverified guess."""
    bbox = BBox(x0=0, y0=0, x1=200, y1=20)
    page = _page_with("Completely different content here", bbox)
    backend = EasyOCRBackend(device="cpu")
    backend._reader = _StubReader([_detection("xyz qwerty asdf zzzz", 0.9, 0, 0, 200, 20)])

    summary = recover_page_elements(page, "unused.png", backend, page_width=1000, page_height=1000)

    assert summary.replaced == 0
    assert page.elements[0].text == "Completely different content here"
    assert summary.records[0].decision == "kept_old"
