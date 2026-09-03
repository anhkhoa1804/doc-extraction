"""Regression matrix for `_fill_table_cell_text`'s tier 2/3 fallbacks.

Diagnosed on the real corpus (experiments/017_table_cell_geometry):
`ord_invoice_png_vi`'s Table Transformer output found 3 rows where 4
exist, so an entire row's OCR tokens had no cell to land in and were
silently dropped by plain center-containment. Not a coordinate-space bug
(`docling_page_size()` matched the render 1:1 for that document) -- a
genuine structure-detection undercount.

These tests use synthetic geometry throughout (no image, no model, no
GPU) so the fallback logic itself is locked in independent of any one
document or model version. Real end-to-end validation against the actual
failing document lives in `experiments/017_table_cell_geometry/`.
"""
from __future__ import annotations

from doc_extraction.pipelines.base import OCRResult, OCRToken, TableResult, _fill_table_cell_text
from doc_extraction.schemas.element import BBox
from doc_extraction.schemas.table import Cell, Table


def _tok(text: str, x0: float, y0: float, x1: float, y1: float, confidence: float | None = None) -> OCRToken:
    return OCRToken(text=text, bbox=BBox(x0=x0, y0=y0, x1=x1, y1=y1), confidence=confidence)


def _grid_table(n_rows: int, n_cols: int, row_h: float = 40.0, col_w: float = 100.0,
                x0: float = 0.0, y0: float = 0.0, table_id: str = "t0", bbox_pad: float = 200.0) -> Table:
    """A clean ruled grid with no gaps between adjacent cells -- the
    baseline geometry every test starts from and perturbs.

    The table's own outer bbox is padded well beyond the detected grid
    (`bbox_pad`), mirroring the real diagnosed case: Docling's LAYOUT
    region for a table is computed independently of Table Transformer's
    STRUCTURE detection, so the outer bbox routinely extends past
    whatever rows/columns the structure model actually found -- that gap
    is exactly where an undetected row's tokens live. A table bbox that
    stopped exactly at the last detected row (as an early draft of this
    helper did) would make every missing-row test pass for the wrong
    reason: the orphaned tokens would already be excluded by the outer
    containment check, never reaching tier 3 at all."""
    cells = []
    for r in range(n_rows):
        for c in range(n_cols):
            cells.append(Cell(
                row=r, col=c,
                bbox=BBox(x0=x0 + c * col_w, y0=y0 + r * row_h,
                          x1=x0 + (c + 1) * col_w, y1=y0 + (r + 1) * row_h),
                text="", is_header=(r == 0),
            ))
    return Table(
        id=table_id,
        bbox=BBox(x0=x0 - bbox_pad, y0=y0 - bbox_pad, x1=x0 + n_cols * col_w + bbox_pad, y1=y0 + n_rows * row_h + bbox_pad),
        page_number=1, n_rows=n_rows, n_cols=n_cols, cells=cells, source_backend="table_transformer",
    )


def _cell(table: Table, row: int, col: int) -> Cell:
    return next(c for c in table.cells if c.row == row and c.col == col)


# --- Tier 1: unchanged behavior (negative controls) -------------------------

def test_token_fully_inside_cell_unchanged():
    """The original, already-correct path: exact containment, no fallback
    involved. Must behave identically to before this milestone."""
    table = _grid_table(2, 2)
    ocr = OCRResult(tokens=[_tok("Hello", 10, 10, 30, 30)])
    _fill_table_cell_text(TableResult(tables=[table]), ocr)
    assert _cell(table, 0, 0).text == "Hello"
    assert _cell(table, 0, 0).confidence is None  # tier 1 never touches confidence
    assert _cell(table, 0, 1).text == ""


def test_ordinary_full_table_is_completely_unchanged():
    """A table where every token lands cleanly must produce identical
    output to the pre-fallback function -- the fallback tiers must never
    fire when there is nothing for them to do."""
    table = _grid_table(2, 2)
    ocr = OCRResult(tokens=[
        _tok("A1", 10, 10, 30, 30), _tok("B1", 110, 10, 130, 30),
        _tok("A2", 10, 50, 30, 70), _tok("B2", 110, 50, 130, 70),
    ])
    result = TableResult(tables=[table])
    _fill_table_cell_text(result, ocr)
    assert [c.text for c in sorted(table.cells, key=lambda c: (c.row, c.col))] == ["A1", "B1", "A2", "B2"]
    assert all(c.confidence is None for c in table.cells)
    assert result.warnings == []


def test_multi_token_cell_joins_in_reading_order():
    """A cell spanning several tokens must join them left-to-right, not in
    OCR emission order -- reading order must survive the fallback path
    existing unchanged."""
    table = _grid_table(1, 1)
    ocr = OCRResult(tokens=[_tok("world", 50, 10, 90, 30), _tok("Hello", 10, 10, 45, 30)])
    _fill_table_cell_text(TableResult(tables=[table]), ocr)
    assert _cell(table, 0, 0).text == "Hello world"


# --- Tier 2: near-miss overlap fallback -------------------------------------

def test_token_slightly_outside_due_to_rounding_is_recovered():
    """A token whose CENTER sits a couple of pixels past a cell's edge (so
    tier 1's exact center-containment misses it) -- the plausible result of
    PIL's float-to-int truncation on crop/render boundaries -- must still
    be recovered via the rounding-margin fallback. The cell is isolated
    (only one cell in the table) so there is no neighboring cell to make
    this ambiguous."""
    table = _grid_table(1, 1, col_w=100.0, row_h=40.0)  # cell bbox = [0,0,100,40]
    ocr = OCRResult(tokens=[_tok("X", -4, 15, 0, 25)])  # center_x = -2, 2px left of the cell's edge
    _fill_table_cell_text(TableResult(tables=[table]), ocr)
    assert _cell(table, 0, 0).text == "X"
    assert _cell(table, 0, 0).confidence == 0.7


def test_token_beyond_rounding_margin_is_not_recovered():
    """A token whose center is well past the margin (not just a rounding
    artifact) must stay unassigned rather than being guessed into the
    nearest cell."""
    table = _grid_table(1, 1, col_w=100.0, row_h=40.0)
    ocr = OCRResult(tokens=[_tok("Y", -20, 15, -12, 25)])  # center_x = -16, far past the 3px margin
    _fill_table_cell_text(TableResult(tables=[table]), ocr)
    assert _cell(table, 0, 0).text == ""


def test_token_in_gap_between_cells_ambiguously_is_not_assigned():
    """A token centered in a real gap between two non-touching cells,
    within rounding margin of BOTH, must be claimed by NEITHER --
    ambiguous ownership must not be resolved by iteration order or
    arbitrary tie-breaking. (Adjacent cells that touch exactly, as
    `_grid_table` builds by default, have no such ambiguous zone: a
    boundary-inclusive center check deterministically picks one side, which
    is not the case this test is targeting -- Table Transformer's real
    output does have small inter-cell gaps.)"""
    table = Table(
        id="t2", bbox=BBox(x0=0, y0=0, x1=250, y1=40), page_number=1, n_rows=1, n_cols=2,
        source_backend="table_transformer",
        cells=[
            Cell(row=0, col=0, bbox=BBox(x0=0, y0=0, x1=98, y1=40), text=""),
            Cell(row=0, col=1, bbox=BBox(x0=102, y0=0, x1=250, y1=40), text=""),
        ],
    )
    ocr = OCRResult(tokens=[_tok("straddle", 90, 10, 110, 30)])  # center_x = 100, in the 98-102 gap
    _fill_table_cell_text(TableResult(tables=[table]), ocr)
    assert _cell(table, 0, 0).text == ""
    assert _cell(table, 0, 1).text == ""


def test_token_far_outside_any_cell_or_table_is_never_assigned():
    """A token nowhere near the table (outside its own outer bbox too)
    must be left completely untouched -- the containment boundary that
    protects ordinary page text from being pulled into a table."""
    table = _grid_table(1, 1)
    ocr = OCRResult(tokens=[_tok("unrelated", 1000, 1000, 1050, 1020)])
    _fill_table_cell_text(TableResult(tables=[table]), ocr)
    assert _cell(table, 0, 0).text == ""


# --- Tier 3: missing-row synthesis -------------------------------------------

def test_missing_row_below_last_detected_row_is_synthesized():
    """The exact real-world shape: a table region is taller than the
    detected grid, and one whole row's tokens sit just below it, each
    aligned with a different existing column. Reproduces
    ord_invoice_png_vi's Table Transformer under-count directly."""
    table = _grid_table(2, 3, row_h=40.0, col_w=100.0)  # rows at y[0,40) and y[40,80)
    ocr = OCRResult(tokens=[
        _tok("R0C0", 10, 10, 30, 30), _tok("R0C1", 110, 10, 130, 30), _tok("R0C2", 210, 10, 230, 30),
        _tok("R1C0", 10, 50, 30, 70), _tok("R1C1", 110, 50, 130, 70), _tok("R1C2", 210, 50, 230, 70),
        # a whole third row Table Transformer never detected, just below y=80:
        _tok("Missing", 10, 90, 30, 110), _tok("Row", 110, 90, 130, 110), _tok("Data", 210, 90, 230, 110),
    ])
    result = TableResult(tables=[table])
    _fill_table_cell_text(result, ocr)
    assert table.n_rows == 3
    assert _cell(table, 2, 0).text == "Missing"
    assert _cell(table, 2, 1).text == "Row"
    assert _cell(table, 2, 2).text == "Data"
    assert _cell(table, 2, 0).confidence == 0.5  # marks provenance: synthesized, not detected
    assert any("synthesized 1 row" in w for w in result.warnings)


def test_single_stray_token_does_not_synthesize_a_row():
    """A LONE orphaned token aligned with one column, with no siblings in
    other columns at the same y-band, must NOT create a new row -- the
    corroboration requirement is the ownership defense against a single
    stray mark (e.g. a stamp fragment) becoming table content."""
    table = _grid_table(2, 3, row_h=40.0, col_w=100.0)
    ocr = OCRResult(tokens=[_tok("Lone", 10, 90, 30, 110)])  # aligns with col 0 only, alone
    result = TableResult(tables=[table])
    _fill_table_cell_text(result, ocr)
    assert table.n_rows == 2  # unchanged
    assert all(c.text == "" for c in table.cells)
    assert result.warnings == []


def test_stray_token_not_aligned_to_any_column_is_never_assigned():
    """A token inside the table's outer bbox but past every detected
    column's x-range (e.g. the table region has padding wider than its own
    column grid) must not be claimed by tier 3, even in a row-band with a
    real corroborating token elsewhere -- non-alignment excludes it from
    `by_col` entirely, so it cannot count toward corroboration either."""
    table = _grid_table(2, 3, row_h=40.0, col_w=100.0)  # columns span x in [0,300]
    table.bbox = BBox(x0=0, y0=0, x1=400, y1=120)  # table's own bbox padded wider than its columns
    ocr = OCRResult(tokens=[
        _tok("Real0", 10, 90, 30, 110),      # aligns with col 0 -- real corroborating evidence
        _tok("Drift", 320, 90, 360, 110),    # inside table.bbox, past every column's x-range
    ])
    result = TableResult(tables=[table])
    _fill_table_cell_text(result, ocr)
    # only one column corroborates ("Real0"); "Drift" matches no column at
    # all, so len(by_col) stays 1 -- below MIN_CORROBORATING_COLUMNS -- and
    # neither token is assigned.
    assert table.n_rows == 2
    assert all(c.text == "" for c in table.cells)


def test_missing_row_inserted_between_existing_rows_renumbers_correctly():
    """A missing row does not have to be the last one -- Table Transformer
    could plausibly miss a middle row too. Row indices must be renumbered
    so reading order (top-to-bottom) is preserved for every row, not just
    the synthesized one."""
    # rows detected at y[0,40) and y[80,120); the missing row belongs at y[40,80)
    table = Table(
        id="t1", bbox=BBox(x0=0, y0=0, x1=200, y1=120), page_number=1, n_rows=2, n_cols=2,
        source_backend="table_transformer",
        cells=[
            Cell(row=0, col=0, bbox=BBox(x0=0, y0=0, x1=100, y1=40), text=""),
            Cell(row=0, col=1, bbox=BBox(x0=100, y0=0, x1=200, y1=40), text=""),
            Cell(row=1, col=0, bbox=BBox(x0=0, y0=80, x1=100, y1=120), text=""),
            Cell(row=1, col=1, bbox=BBox(x0=100, y0=80, x1=200, y1=120), text=""),
        ],
    )
    ocr = OCRResult(tokens=[
        _tok("Top0", 10, 10, 30, 30), _tok("Top1", 110, 10, 130, 30),
        _tok("Mid0", 10, 50, 30, 70), _tok("Mid1", 110, 50, 130, 70),
        _tok("Bot0", 10, 90, 30, 110), _tok("Bot1", 110, 90, 130, 110),
    ])
    result = TableResult(tables=[table])
    _fill_table_cell_text(result, ocr)
    assert table.n_rows == 3
    assert _cell(table, 0, 0).text == "Top0"
    assert _cell(table, 1, 0).text == "Mid0"  # the synthesized row, correctly placed in the middle
    assert _cell(table, 1, 1).text == "Mid1"
    assert _cell(table, 2, 0).text == "Bot0"  # the original "row 1" renumbered to row 2


def test_missing_row_before_first_row_renumbers_correctly():
    """Symmetric edge case: the missing row sits above every detected row."""
    table = _grid_table(1, 2, row_h=40.0, col_w=100.0, y0=40.0)  # only row at y[40,80)
    ocr = OCRResult(tokens=[
        _tok("New0", 10, 0, 30, 20), _tok("New1", 110, 0, 130, 20),  # above the detected row
        _tok("Old0", 10, 50, 30, 70), _tok("Old1", 110, 50, 130, 70),
    ])
    table.bbox = BBox(x0=0, y0=0, x1=200, y1=80)  # widen the table's own bbox to include the gap above
    result = TableResult(tables=[table])
    _fill_table_cell_text(result, ocr)
    assert table.n_rows == 2
    assert _cell(table, 0, 0).text == "New0"
    assert _cell(table, 1, 0).text == "Old0"


def test_scale_invariance_2x():
    """The same missing-row scenario, all coordinates doubled (simulating
    a higher-DPI render) -- the fallback is relative-geometry based, so
    behavior must be identical regardless of absolute pixel scale."""
    table = _grid_table(2, 2, row_h=80.0, col_w=200.0)  # 2x the base geometry
    ocr = OCRResult(tokens=[
        _tok("A", 20, 20, 60, 60), _tok("B", 220, 20, 260, 60),
        _tok("C", 20, 100, 60, 140), _tok("D", 220, 100, 260, 140),
        _tok("Miss0", 20, 180, 60, 220), _tok("Miss1", 220, 180, 260, 220),
    ])
    result = TableResult(tables=[table])
    _fill_table_cell_text(result, ocr)
    assert table.n_rows == 3
    assert _cell(table, 2, 0).text == "Miss0"
    assert _cell(table, 2, 1).text == "Miss1"


def test_vietnamese_diacritics_preserved_through_tier1_and_tier2():
    """No tier does any text transformation -- diacritics must survive
    both center-containment and the rounding-margin fallback identically."""
    table = _grid_table(1, 1, col_w=200.0, row_h=40.0)  # single cell, isolated (no neighbor to make tier 2 ambiguous)
    ocr = OCRResult(tokens=[
        _tok("Đơn vị tính", 10, 10, 190, 30),   # tier 1
        _tok("Bộ lọc khí", 10, -3, 190, -1),    # tier 2: center_y = -2, 2px above the cell's top edge
    ])
    result = TableResult(tables=[table])
    _fill_table_cell_text(result, ocr)
    assert _cell(table, 0, 0).text == "Đơn vị tính Bộ lọc khí"


def test_vietnamese_diacritics_preserved_through_tier3_synthesis():
    """A synthesized row's text (tier 3) must also preserve diacritics
    exactly -- and confirms a single-column table can never grow a
    synthesized row, since MIN_CORROBORATING_COLUMNS can never be met
    with only one column to align against."""
    table = _grid_table(2, 2, row_h=40.0, col_w=100.0)
    ocr = OCRResult(tokens=[
        _tok("Dịch vụ", 10, 90, 30, 110), _tok("lắp đặt", 110, 92, 130, 112),
    ])
    result = TableResult(tables=[table])
    _fill_table_cell_text(result, ocr)
    assert table.n_rows == 3
    assert _cell(table, 2, 0).text == "Dịch vụ"
    assert _cell(table, 2, 1).text == "lắp đặt"


# --- Known limitation, documented rather than hidden ------------------------

def test_synthesized_row_downgrades_table_confidence_but_tier2_does_not():
    """A synthesized row must feed the existing `Table.confidence` /
    `verify_document()` / `from_table_confidence()` convention (see
    `verification.py`) so a downstream consumer sees SUSPICIOUS rather
    than a blind TRUSTED -- the existence of the row was inferred, not
    detected. A tier-2 rounding correction on an already-detected cell is
    a much smaller claim and must not trigger the same downgrade."""
    table = _grid_table(2, 3, row_h=40.0, col_w=100.0)
    ocr = OCRResult(tokens=[
        _tok("Miss0", 10, 90, 30, 110), _tok("Miss1", 110, 90, 130, 110),
    ])
    _fill_table_cell_text(TableResult(tables=[table]), ocr)
    assert table.confidence == 0.5

    table2 = _grid_table(1, 1, col_w=100.0, row_h=40.0)
    ocr2 = OCRResult(tokens=[_tok("X", -4, 15, 0, 25)])  # tier 2 only
    _fill_table_cell_text(TableResult(tables=[table2]), ocr2)
    assert table2.confidence is None


def test_two_stamp_fragments_coincidentally_aligned_can_still_synthesize_a_row():
    """LIMITATION: the corroboration check is purely geometric. If an
    overlay/stamp happens to drop fragments into two different column
    x-ranges at the same y-band -- not exercised by any real document in
    this corpus, but not structurally impossible -- this fallback has no
    way to distinguish that from a genuine missing row, because it does
    not reason about text content or source style at all. Recorded here so
    the gap is visible rather than silently assumed away; closing it would
    need a content/style signal (e.g. table_quality's own outlier checks),
    which this milestone deliberately did not add to the table path."""
    table = _grid_table(1, 3, row_h=40.0, col_w=100.0)
    ocr = OCRResult(tokens=[
        _tok("DUYET", 10, 60, 30, 80),   # stamp fragment, aligns with col 0
        _tok("XYZ", 110, 62, 130, 82),   # unrelated stamp fragment, aligns with col 1
    ])
    result = TableResult(tables=[table])
    _fill_table_cell_text(result, ocr)
    assert table.n_rows == 2  # a row WAS synthesized -- the documented gap, not a hidden success
    assert _cell(table, 1, 0).text == "DUYET"
    assert _cell(table, 1, 1).text == "XYZ"
