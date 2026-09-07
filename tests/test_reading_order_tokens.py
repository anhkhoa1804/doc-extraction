"""Regression matrix for `_tokens_in_reading_order`.

Diagnosed on the real corpus (experiments/023_evidence_centric): the
assembler sorted OCR tokens on the raw `(y0, x0)` tuple. That is correct
only for a backend that emits one token per printed line -- with one token
per line the sort cannot reorder anything, which is why EasyOCR never
exposed it. Tesseract's TSV output is word-level, and words sharing a
baseline differ in `y0` by a few pixels (cap height, ascenders,
punctuation), so the lexicographic sort interleaved them by glyph height:
`ord_policy_en`'s title assembled as "POLICY INTERNAL EXPENDITURE".

Full-pipeline Tesseract exact recall over the 49-PDF corpus at 200 DPI
moved 0.2222 -> 0.9311 across the change that introduced this function.
That delta is shared with `to_tesseract_langs`' `eng`-last ordering, which
landed in the same change; the two were never measured apart end to end, so
neither should be credited with the whole of it.

These tests pin the ordering mechanism itself, which is what this module
owns. Note that the function is not a no-op for one-token-per-line backends
-- see `_tokens_in_reading_order.__doc__`; EasyOCR moved 0.6380 -> 0.6570.

Synthetic geometry only -- no image, no model, no GPU. The end-to-end
numbers live in `experiments/023_evidence_centric/`.
"""
from __future__ import annotations

from doc_extraction.pipelines.base import (
    OCRResult,
    OCRToken,
    Region,
    _gather_region_text,
    _tokens_in_reading_order,
)
from doc_extraction.schemas.element import BBox


def _tok(text: str, x0: float, y0: float, x1: float, y1: float) -> OCRToken:
    return OCRToken(text=text, bbox=BBox(x0=x0, y0=y0, x1=x1, y1=y1), confidence=0.9)


def _order(tokens: list[OCRToken]) -> list[str]:
    return [t.text for t in _tokens_in_reading_order(tokens)]


def test_empty_input_is_empty_output():
    assert _tokens_in_reading_order([]) == []


def test_words_on_one_line_read_left_to_right_despite_unequal_tops():
    """The exact geometry measured on `ord_policy_en` page 1: POLICY sits
    one pixel higher than its neighbours because it has no ascender above
    the cap line. A `(y0, x0)` sort puts it first."""
    tokens = [
        _tok("INTERNAL", 170, 139, 383, 167),
        _tok("EXPENDITURE", 401, 139, 700, 168),
        _tok("POLICY", 720, 138, 874, 168),
    ]
    assert _order(tokens) == ["INTERNAL", "EXPENDITURE", "POLICY"]


def test_short_word_between_taller_neighbours_keeps_its_place():
    """`Section 1. Scope`: the digit-and-period token's box starts a pixel
    below the words on either side of it, which the old sort moved to the
    end of the line."""
    tokens = [
        _tok("Section", 169, 227, 277, 250),
        _tok("1.", 293, 228, 315, 250),
        _tok("Scope", 331, 227, 420, 256),
    ]
    assert _order(tokens) == ["Section", "1.", "Scope"]


def test_lines_are_ordered_top_to_bottom():
    tokens = [
        _tok("second", 100, 200, 200, 230),
        _tok("line", 210, 199, 280, 230),
        _tok("first", 100, 100, 180, 130),
        _tok("line", 190, 101, 260, 130),
    ]
    assert _order(tokens) == ["first", "line", "second", "line"]


def test_a_token_out_of_x_order_within_a_line_is_reordered():
    """Backends do not promise left-to-right emission; the band must sort
    on x0 rather than trust arrival order."""
    tokens = [
        _tok("world", 300, 100, 400, 130),
        _tok("hello", 100, 100, 200, 130),
    ]
    assert _order(tokens) == ["hello", "world"]


def test_one_token_per_line_input_is_unchanged():
    """EasyOCR's shape. Every band holds exactly one token, so the result
    is identical to the sort this replaced -- no existing backend's
    assembled output moves."""
    tokens = [
        _tok("Section 1. Scope", 163, 221, 428, 264),
        _tok("This policy applies to all employees.", 162, 278, 1312, 326),
        _tok("INTERNAL EXPENDITURE POLICY", 163, 131, 877, 175),
    ]
    assert _order(tokens) == [
        "INTERNAL EXPENDITURE POLICY",
        "Section 1. Scope",
        "This policy applies to all employees.",
    ]


def test_lines_that_barely_touch_stay_separate():
    """Adjacent printed lines overlap by a pixel or two of leading. Below
    the threshold they must remain two lines, or a two-column-looking page
    would collapse into one band."""
    tokens = [
        _tok("upper", 100, 100, 200, 130),
        _tok("lower", 100, 128, 200, 158),
    ]
    assert _order(tokens) == ["upper", "lower"]


def test_a_tall_token_does_not_swallow_the_line_below_it():
    """Overlap is measured against the *shorter* box, so a tall token (a
    stamp, a heading glyph) that spans two lines joins the band it shares
    most with rather than absorbing both."""
    tall = _tok("TALL", 100, 100, 160, 190)
    below = _tok("below", 200, 160, 300, 190)
    above = _tok("above", 200, 100, 300, 130)
    ordered = _order([below, above, tall])
    assert ordered.index("above") < ordered.index("below")


def test_region_text_uses_reading_order():
    """The behaviour that actually reaches the IR: `_gather_region_text` is
    what every scanned page's element text comes from."""
    region = Region(bbox=BBox(x0=0, y0=0, x1=1000, y1=1000), label="text")
    ocr = OCRResult(tokens=[
        _tok("POLICY", 720, 138, 874, 168),
        _tok("INTERNAL", 170, 139, 383, 167),
        _tok("EXPENDITURE", 401, 139, 700, 168),
    ])
    assert _gather_region_text(region, ocr) == "INTERNAL EXPENDITURE POLICY"
