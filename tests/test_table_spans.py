from doc_extraction.backends.table_backend import _structure_cells
from doc_extraction.schemas.element import BBox


def test_structure_prediction_span_merges_only_its_observed_grid_slots():
    cells = _structure_cells(
        rows=[(0, 20), (20, 40)],
        cols=[(0, 50), (50, 100)],
        header_rows=[(0, 20)],
        span_boxes=[((0, 0, 100, 20), 0.93)],
        table_bbox=BBox(x0=100, y0=200, x1=200, y1=240),
    )

    assert [(cell.row, cell.col, cell.row_span, cell.col_span) for cell in cells] == [
        (0, 0, 1, 2),
        (1, 0, 1, 1),
        (1, 1, 1, 1),
    ]
    assert cells[0].bbox == BBox(x0=100, y0=200, x1=200, y1=220)
    assert cells[0].is_header is True
    assert cells[0].confidence == 0.93


def test_structure_prediction_rowspan_preserves_uncovered_cells():
    cells = _structure_cells(
        rows=[(0, 20), (20, 40), (40, 60)],
        cols=[(0, 50), (50, 100)],
        header_rows=[],
        span_boxes=[((0, 0, 50, 40), 0.8)],
        table_bbox=BBox(x0=10, y0=20, x1=110, y1=80),
    )

    assert [(cell.row, cell.col, cell.row_span, cell.col_span) for cell in cells] == [
        (0, 0, 2, 1),
        (0, 1, 1, 1),
        (1, 1, 1, 1),
        (2, 0, 1, 1),
        (2, 1, 1, 1),
    ]


def test_noncontiguous_or_single_slot_span_is_ignored():
    cells = _structure_cells(
        rows=[(0, 10), (10, 20), (20, 30)],
        cols=[(0, 50), (50, 100)],
        header_rows=[],
        span_boxes=[
            ((0, 0, 100, 30), 0.99),  # contiguous: legitimately covers the grid
        ],
        table_bbox=BBox(x0=0, y0=0, x1=100, y1=30),
    )
    assert [(cell.row_span, cell.col_span) for cell in cells] == [(3, 2)]

    ignored = _structure_cells(
        rows=[(0, 10), (10, 20)],
        cols=[(0, 50), (50, 100)],
        header_rows=[],
        span_boxes=[((0, 0, 50, 10), 0.99)],  # exactly one slot
        table_bbox=BBox(x0=0, y0=0, x1=100, y1=20),
    )
    assert len(ignored) == 4
    assert all(cell.row_span == cell.col_span == 1 for cell in ignored)


def test_overlapping_span_predictions_keep_highest_confidence_only():
    cells = _structure_cells(
        rows=[(0, 20), (20, 40)],
        cols=[(0, 50), (50, 100)],
        header_rows=[],
        span_boxes=[
            ((0, 0, 100, 20), 0.8),
            ((0, 0, 50, 40), 0.95),
        ],
        table_bbox=BBox(x0=0, y0=0, x1=100, y1=40),
    )
    assert [(cell.row, cell.col, cell.row_span, cell.col_span) for cell in cells] == [
        (0, 0, 2, 1),
        (0, 1, 1, 1),
        (1, 1, 1, 1),
    ]


def test_rectangular_span_and_multiple_disjoint_spans_preserve_grid_dimensions():
    cells = _structure_cells(
        rows=[(0, 10), (10, 20), (20, 30), (30, 40)],
        cols=[(0, 10), (10, 20), (20, 30), (30, 40)],
        header_rows=[],
        span_boxes=[
            ((0, 0, 20, 20), 0.95),
            ((20, 20, 40, 40), 0.90),
        ],
        table_bbox=BBox(x0=5, y0=7, x1=45, y1=47),
    )

    assert [(cell.row, cell.col, cell.row_span, cell.col_span) for cell in cells] == [
        (0, 0, 2, 2), (0, 2, 1, 1), (0, 3, 1, 1),
        (1, 2, 1, 1), (1, 3, 1, 1), (2, 0, 1, 1), (2, 1, 1, 1),
        (2, 2, 2, 2), (3, 0, 1, 1), (3, 1, 1, 1),
    ]
    assert all(cell.row + cell.row_span <= 4 for cell in cells)
    assert all(cell.col + cell.col_span <= 4 for cell in cells)
    assert cells[0].bbox == BBox(x0=5, y0=7, x1=25, y1=27)
    assert cells[7].bbox == BBox(x0=25, y0=27, x1=45, y1=47)


def test_span_crossing_grid_boundary_is_rejected_not_clipped():
    cells = _structure_cells(
        rows=[(0, 20), (20, 40)],
        cols=[(0, 50), (50, 100)],
        header_rows=[],
        span_boxes=[((-10, 0, 100, 20), 0.99)],
        table_bbox=BBox(x0=0, y0=0, x1=100, y1=40),
    )

    assert len(cells) == 4
    assert all(cell.row_span == cell.col_span == 1 for cell in cells)


def test_missing_row_or_column_structure_yields_no_cells():
    bbox = BBox(x0=0, y0=0, x1=100, y1=40)
    assert _structure_cells([], [(0, 100)], [], [], bbox) == []
    assert _structure_cells([(0, 40)], [], [], [], bbox) == []
