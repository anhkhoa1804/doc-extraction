"""Regression matrix for orphan OCR evidence recovery.

Diagnosed on the real corpus (experiments/024_ocr_fidelity_recovery):
`_gather_region_text` keeps only tokens whose centre falls inside a detected
layout region, so tokens no region claims are discarded silently. Measured
over 49 PDFs, 1000 of 5845 recognised tokens (17.1%) were dropped that way.
On `cmb_scan_multicol_en` the dropped tokens are the page's entire second
column -- 15 of 34 -- including a `must_contain` string the recogniser had
read correctly.

These tests pin the recovery's contract, not its yield: that unclaimed text
comes back, that claimed text is never duplicated, that table-owned pixels
are left to the table, that recovered blocks carry real geometry and land in
reading order by position, and that a page with nothing orphaned is
untouched.

Synthetic geometry only -- no image, no model, no OCR, no GPU. The
end-to-end numbers live in `experiments/024_ocr_fidelity_recovery/`.
"""
from __future__ import annotations

from doc_extraction.evaluation.omnidocbench import page_to_prediction_markdown
from doc_extraction.pipelines.base import (
    LayoutResult,
    OCRResult,
    OCRToken,
    Region,
    TableResult,
    _fill_table_cell_text,
    merge_regions_into_page,
)
from doc_extraction.schemas.element import BBox
from doc_extraction.schemas.table import Cell, Table
from doc_extraction.stages.reading_order import compute_reading_order


def _tok(text: str, x0: float, y0: float, x1: float, y1: float, conf: float = 0.9):
    return OCRToken(text=text, bbox=BBox(x0=x0, y0=y0, x1=x1, y1=y1), confidence=conf)


def _region(label: str, x0: float, y0: float, x1: float, y1: float):
    return Region(label=label, bbox=BBox(x0=x0, y0=y0, x1=x1, y1=y1), confidence=0.9)


def _page(regions, tokens, tables=None):
    return merge_regions_into_page(
        page_index=0,
        width=600.0,
        height=800.0,
        dpi=200,
        layout_result=LayoutResult(regions=regions, backend="stub-layout"),
        ocr_result=OCRResult(tokens=tokens, backend="stub-ocr"),
        table_result=TableResult(tables=list(tables or []), backend="stub-table"),
        rendered_image_path=None,
    )


def _recovered(page):
    return [e for e in page.elements if e.extra.get("recovered") == "orphan_ocr_tokens"]


def _all_text(page) -> str:
    return " ".join(e.text or "" for e in page.elements)


def test_unclaimed_tokens_are_recovered():
    """The `cmb_scan_multicol_en` shape: one detected region, a second column
    of real text that no region covers."""
    page = _page(
        regions=[_region("text", 50, 50, 250, 120)],
        tokens=[
            _tok("Section", 60, 60, 130, 80), _tok("1.", 140, 60, 160, 80),
            _tok("Section", 350, 60, 420, 80), _tok("2.", 430, 60, 450, 80),
            _tok("Approval", 460, 60, 540, 80),
        ],
    )
    recovered = _recovered(page)
    assert len(recovered) == 1
    assert recovered[0].text == "Section 2. Approval"


def test_claimed_tokens_are_not_duplicated():
    page = _page(
        regions=[_region("text", 50, 50, 250, 120)],
        tokens=[_tok("Section", 60, 60, 130, 80), _tok("orphan", 400, 60, 470, 80)],
    )
    assert _all_text(page).split().count("Section") == 1
    assert _all_text(page).split().count("orphan") == 1


def test_no_recovered_element_when_every_token_is_claimed():
    """A page with nothing orphaned must be byte-for-byte what it was."""
    page = _page(
        regions=[_region("text", 50, 50, 250, 120)],
        tokens=[_tok("Section", 60, 60, 130, 80), _tok("1.", 140, 60, 160, 80)],
    )
    assert _recovered(page) == []
    assert len(page.elements) == 1
    assert page.notes == []


def test_tokens_inside_a_detected_table_are_left_to_the_table():
    """Table ownership has its own tiered rules (experiment 017). A token the
    table did not put in a cell must not reappear as a sibling text element,
    or the same pixels would be described twice with different structure."""
    table = Table(
        id="t0", page_number=1, n_rows=1, n_cols=1,
        bbox=BBox(x0=300, y0=200, x1=500, y1=300),
        cells=[Cell(row=0, col=0, bbox=BBox(x0=300, y0=200, x1=500, y1=300), text="")],
        source_backend="stub-table",
    )
    page = _page(
        regions=[_region("text", 50, 50, 250, 120)],
        tokens=[_tok("Section", 60, 60, 130, 80), _tok("inside", 380, 240, 440, 260)],
        tables=[table],
    )
    assert _recovered(page) == []
    assert "inside" not in _all_text(page)


def test_recovered_block_keeps_multi_column_reading_order():
    """Recovered text must be placed by geometry, not appended. Two columns
    with a real gutter: the recovered right-column block must follow the
    left column's own content in `compute_reading_order`."""
    page = _page(
        regions=[_region("text", 50, 50, 250, 120), _region("text", 50, 150, 250, 220)],
        tokens=[
            _tok("left", 60, 60, 120, 80), _tok("lower", 60, 160, 130, 180),
            _tok("right", 400, 60, 460, 80),
        ],
    )
    order = compute_reading_order(page.elements, page_width=page.width)
    recovered_id = _recovered(page)[0].id
    assert order.index(recovered_id) > order.index("p0-e1"), (
        "recovered right-column text must come after the whole left column"
    )


def test_separate_orphan_blocks_are_not_merged_across_a_page():
    """A dropped header and a dropped footer share no vertical neighbourhood
    and must not collapse into one element."""
    page = _page(
        regions=[_region("text", 50, 300, 550, 400)],
        tokens=[
            _tok("header", 60, 40, 140, 60),
            _tok("footer", 60, 700, 140, 720),
        ],
    )
    recovered = _recovered(page)
    assert len(recovered) == 2
    assert [e.text for e in recovered] == ["header", "footer"]


def test_adjacent_orphan_lines_join_into_one_block():
    page = _page(
        regions=[_region("text", 50, 400, 250, 500)],
        tokens=[
            _tok("first", 60, 60, 120, 80), _tok("line", 130, 60, 180, 80),
            _tok("second", 60, 86, 130, 106),
        ],
    )
    recovered = _recovered(page)
    assert len(recovered) == 1
    assert recovered[0].text == "first line second"


def test_recovered_element_preserves_provenance_and_confidence():
    page = _page(
        regions=[_region("text", 50, 400, 250, 500)],
        tokens=[_tok("alpha", 60, 60, 120, 80, conf=0.8),
                _tok("beta", 130, 60, 180, 80, conf=0.6)],
    )
    element = _recovered(page)[0]
    assert element.source_backend == "stub-ocr", "provenance is the recogniser, not a layout backend"
    assert element.extra == {"recovered": "orphan_ocr_tokens", "token_count": 2}
    assert element.confidence == 0.7
    assert element.page_number == 1
    assert element.bbox == BBox(x0=60, y0=60, x1=180, y1=80)


def test_decorative_glyph_run_is_not_recovered_as_text():
    """A block with no alphanumeric character is page furniture -- a rule or
    a border read as glyphs -- not dropped content."""
    page = _page(
        regions=[_region("text", 50, 400, 250, 500)],
        tokens=[_tok("---", 60, 60, 120, 80), _tok("|", 130, 60, 140, 80)],
    )
    assert _recovered(page) == []


def test_orphan_recovery_is_recorded_in_page_notes():
    page = _page(
        regions=[_region("text", 50, 400, 250, 500)],
        tokens=[_tok("dropped", 60, 60, 130, 80)],
    )
    assert any("orphan OCR recovery" in n for n in page.notes)


def test_recovery_is_deterministic_for_the_same_input():
    args = {
        "regions": [_region("text", 50, 400, 250, 500)],
        "tokens": [
            _tok("beta", 130, 60, 180, 80),
            _tok("alpha", 60, 60, 120, 80),
            _tok("gamma", 60, 90, 130, 110),
        ],
    }
    first, second = _page(**args), _page(**args)
    assert [e.text for e in _recovered(first)] == [e.text for e in _recovered(second)]
    assert [e.text for e in _recovered(first)] == ["alpha beta gamma"]


def test_cell_tokens_are_excluded_even_when_the_table_has_no_outer_bbox():
    """`Table.bbox` is optional. A table with cells but no outer box still
    owns its cells' tokens, and `_fill_table_cell_text` will have placed
    them, so recovery must not hand the same pixels to a text element."""
    table = Table(
        id="t0", page_number=1, n_rows=1, n_cols=1, bbox=None,
        cells=[Cell(row=0, col=0, bbox=BBox(x0=300, y0=200, x1=500, y1=300), text="")],
        source_backend="stub-table",
    )
    page = _page(
        regions=[_region("text", 50, 50, 250, 120)],
        tokens=[_tok("Section", 60, 60, 130, 80), _tok("incell", 380, 240, 440, 260)],
        tables=[table],
    )
    assert _recovered(page) == []
    assert "incell" not in _all_text(page)


def test_visual_table_owns_tokens_also_covered_by_layout_text_region():
    """Overlapping layout text/table regions must not emit the cell twice.

    The representative-v2 Classic artifact for
    ``jiaocaineedrop_jiaocai_needrop_en_397.jpg`` showed table values such as
    ``Time`` both in table cells and sibling text elements. The broad text
    region may still contain genuine text outside the table, so ownership is
    resolved per token center rather than suppressing the whole region.
    """
    table = Table(
        id="t0",
        page_number=1,
        n_rows=1,
        n_cols=1,
        bbox=BBox(x0=300, y0=200, x1=500, y1=300),
        cells=[
            Cell(
                row=0,
                col=0,
                bbox=BBox(x0=300, y0=200, x1=400, y1=300),
                text="",
            )
        ],
        source_backend="stub-table",
    )
    table_result = TableResult(tables=[table], backend="stub-table")
    ocr_result = OCRResult(
        tokens=[
            _tok("owned-cell-text", 320, 230, 360, 250),
            _tok("outside-table-text", 510, 230, 550, 250),
        ],
        backend="stub-ocr",
    )
    owned_token_ids = _fill_table_cell_text(table_result, ocr_result)

    page = merge_regions_into_page(
        page_index=0,
        width=600,
        height=400,
        dpi=200,
        layout_result=LayoutResult(
            regions=[
                _region("table", 300, 200, 500, 300),
                _region("text", 250, 180, 560, 320),
            ],
            backend="stub-layout",
        ),
        ocr_result=ocr_result,
        table_result=table_result,
        rendered_image_path=None,
        table_owned_token_ids=owned_token_ids,
    )

    loose_text = " ".join(
        element.text or "" for element in page.elements if element.type.value != "table"
    )
    assert table.cells[0].text == "owned-cell-text"
    assert "owned-cell-text" not in loose_text
    assert "outside-table-text" in loose_text


def test_structured_table_without_layout_table_region_has_one_owner_and_keeps_unassigned_text():
    """A structure backend may find a table that layout labels only as text.

    Cell-assigned tokens belong to the table exactly once, while a title in
    the outer table bounds but outside every cell remains ordinary text.
    """
    table = Table(
        id="t0",
        page_number=1,
        n_rows=1,
        n_cols=2,
        bbox=BBox(x0=100, y0=200, x1=500, y1=400),
        cells=[
            Cell(row=0, col=0, bbox=BBox(x0=100, y0=250, x1=290, y1=380), text=""),
            Cell(row=0, col=1, bbox=BBox(x0=300, y0=250, x1=500, y1=380), text=""),
        ],
        source_backend="stub-table",
    )
    table_result = TableResult(tables=[table], backend="stub-table")
    ocr_result = OCRResult(
        tokens=[
            _tok("Time", 120, 270, 180, 292),
            _tok("Fee", 320, 270, 360, 292),
            _tok("Welcome to the 2010 Summer Camp", 120, 210, 430, 238),
        ],
        backend="stub-ocr",
    )
    owned_token_ids = _fill_table_cell_text(table_result, ocr_result)
    page = merge_regions_into_page(
        page_index=0,
        width=600,
        height=500,
        dpi=200,
        layout_result=LayoutResult(
            regions=[_region("text", 80, 180, 520, 420)],
            backend="stub-layout",
        ),
        ocr_result=ocr_result,
        table_result=table_result,
        rendered_image_path=None,
        table_owned_token_ids=owned_token_ids,
    )
    page.reading_order = [element.id for element in page.elements]

    table_owners = [element for element in page.elements if element.table_id == "t0"]
    assert len(table_owners) == 1
    assert table_owners[0].type.value == "table"
    assert table.cells[0].text == "Time"
    assert table.cells[1].text == "Fee"
    text_elements = [element.text or "" for element in page.elements if element.type.value != "table"]
    assert text_elements == ["Welcome to the 2010 Summer Camp"]

    markdown = page_to_prediction_markdown(page)
    assert markdown.count("Time") == 1
    assert markdown.count("Fee") == 1
    assert markdown.count("Welcome to the 2010 Summer Camp") == 1


def test_unmatched_layout_table_region_is_preserved_without_fabricated_reference():
    """A layout-only table remains visible when structure recognition fails."""
    page = _page(
        regions=[_region("table", 100, 100, 300, 220)],
        tokens=[_tok("observed cell text", 120, 120, 260, 145)],
    )

    region = page.elements[0]
    assert region.type.value == "other"
    assert region.table_id is None
    assert region.bbox == BBox(x0=100, y0=100, x1=300, y1=220)
    assert region.extra == {"layout_label": "table"}
    assert region.text == "observed cell text"
    assert any("no matching structured table was produced" in note for note in page.notes)


def test_unmatched_layout_table_does_not_attach_to_nearest_unrelated_table():
    recognized = Table(
        id="t0",
        page_number=1,
        n_rows=1,
        n_cols=1,
        bbox=BBox(x0=10, y0=10, x1=100, y1=100),
        cells=[Cell(row=0, col=0, bbox=BBox(x0=10, y0=10, x1=100, y1=100), text="known")],
        source_backend="stub-table",
    )
    page = _page(
        regions=[_region("table", 10, 10, 100, 100), _region("table", 400, 400, 550, 550)],
        tokens=[_tok("unstructured content", 420, 420, 520, 450)],
        tables=[recognized],
    )

    assert page.elements[0].type.value == "table"
    assert page.elements[0].table_id == recognized.id
    assert page.elements[1].type.value == "other"
    assert page.elements[1].table_id is None
    assert page.elements[1].text == "unstructured content"
    assert page.tables == [recognized]
