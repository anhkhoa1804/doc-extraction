"""Regression tests for the table-cell-text fix in docling_backend.py.

Real-world evidence (experiments/005_omnidocbench/observations.md,
"table cell text association"): every table in the `baseline` pipeline's
OmniDocBench predictions had 100% empty cells. Root cause, traced with real
data (not assumed): `TableTransformerBackend` detects grid geometry only —
by design, it never reads text — and the intended text source,
`DoclingBackend.recognize()`, explicitly excluded table-labeled items from
its OCR tokens (`if label == "table": continue`) with a comment claiming
"table text is handled by the table stage" — which was never actually true,
since the table stage has no text to hand out. Docling's own conversion
already computes real per-cell text (TableFormer + its internal OCR) for
that exact table item; it was simply being discarded.

These tests exercise `recognize()`'s fixed behavior against fake
docling-shaped objects (no model weights, no real inference — fast and
deterministic) and confirm the fix's actual effect end-to-end through the
existing (unmodified) `_fill_table_cell_text` cell-matching logic.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from doc_extraction.backends.docling_backend import DoclingBackend
from doc_extraction.pipelines.base import PageInput, _fill_table_cell_text
from doc_extraction.schemas.table import Cell, Table


@dataclass
class _FakeBBox:
    l: float
    t: float
    r: float
    b: float
    coord_origin: str = "TOPLEFT"


@dataclass
class _FakeProv:
    bbox: _FakeBBox
    page_no: int = 1


@dataclass
class _FakeTableCell:
    text: str
    bbox: _FakeBBox
    start_row_offset_idx: int = 0
    end_row_offset_idx: int = 1
    start_col_offset_idx: int = 0
    end_col_offset_idx: int = 1
    column_header: bool = False
    row_header: bool = False


@dataclass
class _FakeTableData:
    table_cells: list
    num_rows: int = 1
    num_cols: int = 1


@dataclass
class _FakeLabel:
    value: str


@dataclass
class _FakeItem:
    label: _FakeLabel
    prov: list
    text: str | None = None
    data: object | None = None


@dataclass
class _FakeDoc:
    items: list

    def iterate_items(self):
        return [(item, 0) for item in self.items]


@dataclass
class _FakeConvertResult:
    document: _FakeDoc


def _table_item(cells, whole_table_bbox=_FakeBBox(0, 0, 1000, 1000)):
    return _FakeItem(
        label=_FakeLabel("table"),
        prov=[_FakeProv(bbox=whole_table_bbox)],
        text=None,
        data=_FakeTableData(table_cells=cells),
    )


def _text_item(text, bbox):
    return _FakeItem(label=_FakeLabel("text"), prov=[_FakeProv(bbox=bbox)], text=text)


def _backend_with_fake_conversion(doc: _FakeDoc) -> DoclingBackend:
    backend = DoclingBackend(device="cpu", ocr_languages=["en", "ch_sim"])
    backend._convert_cached = lambda path: _FakeConvertResult(document=doc)  # type: ignore[method-assign]
    return backend


def _page_input(height: float = 1000.0) -> PageInput:
    return PageInput(page_index=0, width=1000.0, height=height, image_path=Path("fake.png"), dpi=200)


def test_recognize_emits_one_token_per_populated_table_cell():
    cells = [
        _FakeTableCell(text="Industry", bbox=_FakeBBox(10, 10, 90, 30)),
        _FakeTableCell(text="Bank", bbox=_FakeBBox(100, 10, 180, 30)),
        _FakeTableCell(text="", bbox=_FakeBBox(10, 40, 90, 60)),  # blank cell — no ground truth text
    ]
    doc = _FakeDoc(items=[_table_item(cells)])
    backend = _backend_with_fake_conversion(doc)

    result = backend.recognize(_page_input())

    texts = {t.text for t in result.tokens}
    assert texts == {"Industry", "Bank"}, "blank cells must not produce empty-text tokens"


def test_recognize_uses_each_cells_own_tight_bbox_not_the_whole_table_bbox():
    """The bug this fix targets: a single token spanning the whole table can
    only ever land (by center-point containment) inside one grid cell,
    leaving every other cell empty. Each emitted token must carry its own
    cell's bbox, not the table's outer bbox."""
    whole_table = _FakeBBox(0, 0, 1000, 1000)
    cell_bbox = _FakeBBox(10, 10, 90, 30)
    cells = [_FakeTableCell(text="Industry", bbox=cell_bbox)]
    doc = _FakeDoc(items=[_table_item(cells, whole_table_bbox=whole_table)])
    backend = _backend_with_fake_conversion(doc)

    result = backend.recognize(_page_input())

    assert len(result.tokens) == 1
    token = result.tokens[0]
    assert (token.bbox.x0, token.bbox.y0, token.bbox.x1, token.bbox.y1) == (10, 10, 90, 30)
    assert (token.bbox.x0, token.bbox.y0, token.bbox.x1, token.bbox.y1) != (0, 0, 1000, 1000)


def test_recognize_still_emits_non_table_text_tokens():
    """Regression guard: adding table-cell tokens must not disturb ordinary
    (non-table) OCR token extraction."""
    cells = [_FakeTableCell(text="Cell", bbox=_FakeBBox(10, 10, 90, 30))]
    doc = _FakeDoc(items=[
        _text_item("Heading text", _FakeBBox(0, 0, 200, 20)),
        _table_item(cells),
    ])
    backend = _backend_with_fake_conversion(doc)

    result = backend.recognize(_page_input())

    texts = {t.text for t in result.tokens}
    assert texts == {"Heading text", "Cell"}


def test_recognize_converts_bottomleft_cell_bbox_like_other_docling_bboxes():
    """Empirically, real Docling table_cells carry TOPLEFT-origin bboxes —
    but the conversion helper (_bbox_from_docling) supports BOTTOMLEFT too,
    and cell bboxes go through the same helper as everything else in this
    backend. A BOTTOMLEFT cell bbox must still convert correctly."""
    page_height = 1000.0
    # BOTTOMLEFT: t/b measured from the bottom; expect y0=height-t, y1=height-b.
    cells = [_FakeTableCell(text="X", bbox=_FakeBBox(l=10, t=970, r=90, b=950, coord_origin="BOTTOMLEFT"))]
    doc = _FakeDoc(items=[_table_item(cells)])
    backend = _backend_with_fake_conversion(doc)

    result = backend.recognize(_page_input(height=page_height))

    assert len(result.tokens) == 1
    bbox = result.tokens[0].bbox
    assert (bbox.x0, bbox.y0, bbox.x1, bbox.y1) == (10, 30, 90, 50)


def test_fill_table_cell_text_end_to_end_with_fine_grained_tokens():
    """The practical effect that actually matters: independently-detected
    Table Transformer cells get correctly populated once recognize() emits
    per-cell (not per-table) tokens, through the existing (unmodified)
    center-point matching in _fill_table_cell_text."""
    docling_cells = [
        _FakeTableCell(text="Industry", bbox=_FakeBBox(10, 10, 90, 30)),
        _FakeTableCell(text="Bank", bbox=_FakeBBox(100, 10, 180, 30)),
    ]
    doc = _FakeDoc(items=[_table_item(docling_cells)])
    backend = _backend_with_fake_conversion(doc)
    ocr_result = backend.recognize(_page_input())

    # A Table Transformer-style detected grid, independent geometry, cells
    # start empty exactly like the real backend produces them.
    from doc_extraction.pipelines.base import TableResult
    from doc_extraction.schemas.element import BBox

    table = Table(
        id="t0", bbox=BBox(x0=0, y0=0, x1=300, y1=100), page_number=1,
        n_rows=1, n_cols=2,
        cells=[
            Cell(row=0, col=0, bbox=BBox(x0=5, y0=5, x1=95, y1=35), text=""),
            Cell(row=0, col=1, bbox=BBox(x0=95, y0=5, x1=200, y1=35), text=""),
        ],
        source_backend="table_transformer",
    )
    table_result = TableResult(tables=[table], backend="table_transformer")

    _fill_table_cell_text(table_result, ocr_result)

    assert table.cells[0].text == "Industry"
    assert table.cells[1].text == "Bank"


def test_recognize_handles_missing_table_cells_gracefully():
    """A table item with no table_cells (or a None data) must not crash —
    getattr(..., None) or [] already guards this; assert the contract."""
    doc = _FakeDoc(items=[_table_item(cells=[])])
    backend = _backend_with_fake_conversion(doc)

    result = backend.recognize(_page_input())

    assert result.tokens == []
