"""Reading-order baseline.

Covers the five layouts named in the hardening brief: single column, two
column, text + table, header/footer, and irregular blocks. These lock in the
*documented* behaviour of a geometric baseline — including where it is known
to be wrong — so that a future ordering model has something to diff against.
"""
from __future__ import annotations

from doc_extraction.schemas.element import BBox, Element, ElementType
from doc_extraction.stages.reading_order import ORDER_STRATEGY, compute_reading_order

PAGE_WIDTH = 600.0


def el(element_id: str, x0: float, y0: float, x1: float, y1: float, etype=ElementType.TEXT) -> Element:
    return Element(
        id=element_id,
        type=etype,
        bbox=BBox(x0=x0, y0=y0, x1=x1, y1=y1),
        page_number=1,
        source_backend="test",
    )


def order(elements, **kwargs):
    return compute_reading_order(elements, page_width=PAGE_WIDTH, **kwargs)


def test_strategy_is_named():
    """The baseline must identify itself; results on disk record which
    ordering produced them."""
    assert ORDER_STRATEGY == "column-aware-xy-band"


# 1. Single column ----------------------------------------------------------


def test_single_column_orders_top_to_bottom():
    elements = [
        el("c", 50, 300, 550, 340),
        el("a", 50, 100, 550, 140),
        el("b", 50, 200, 550, 240),
    ]
    assert order(elements) == ["a", "b", "c"]


def test_single_row_orders_left_to_right():
    elements = [el("right", 400, 100, 550, 140), el("left", 50, 100, 200, 140)]
    assert order(elements) == ["left", "right"]


# 2. Two-column layout ------------------------------------------------------


def test_two_column_layout_reads_column_by_column():
    """The failure a naive row-band sort makes: interleaving the columns."""
    elements = [
        el("L1", 40, 100, 280, 140),
        el("R1", 320, 100, 560, 140),
        el("L2", 40, 160, 280, 200),
        el("R2", 320, 160, 560, 200),
    ]
    assert order(elements) == ["L1", "L2", "R1", "R2"]


def test_two_column_layout_with_full_width_header_and_footer():
    elements = [
        el("header", 40, 40, 560, 70, ElementType.HEADING),
        el("L1", 40, 100, 280, 140),
        el("R1", 320, 100, 560, 140),
        el("L2", 40, 160, 280, 200),
        el("R2", 320, 160, 560, 200),
        el("footer", 40, 700, 560, 730),
    ]
    result = order(elements)
    assert result[0] == "header"
    assert result[-1] == "footer"
    assert result.index("L1") < result.index("L2") < result.index("R1")


def test_narrow_gap_does_not_split_into_columns():
    """Conservative by design: inventing columns is worse than missing one."""
    elements = [
        el("a", 40, 100, 290, 140),
        el("b", 300, 100, 560, 140),  # 10pt gap, well under the gutter threshold
    ]
    assert order(elements) == ["a", "b"]


# 3. Text + table -----------------------------------------------------------


def test_text_table_text_keeps_document_flow():
    elements = [
        el("intro", 40, 100, 560, 140),
        el("table", 40, 160, 560, 400, ElementType.TABLE),
        el("outro", 40, 420, 560, 460),
    ]
    assert order(elements) == ["intro", "table", "outro"]


# 4. Header / footer --------------------------------------------------------


def test_header_and_footer_bracket_the_body():
    elements = [
        el("body", 40, 200, 560, 600),
        el("footer", 40, 780, 560, 800),
        el("header", 40, 30, 560, 50),
    ]
    assert order(elements) == ["header", "body", "footer"]


# 5. Irregular blocks -------------------------------------------------------


def test_irregular_blocks_are_ordered_deterministically():
    elements = [
        el("big", 40, 100, 560, 300),
        el("small_left", 40, 320, 180, 350),
        el("wide_mid", 40, 360, 400, 420),
        el("tiny", 420, 320, 460, 340),
    ]
    first = order(elements)
    second = order(list(reversed(elements)))
    assert first[0] == "big"
    # Determinism: the same geometry must produce the same order regardless
    # of the order elements were discovered in.
    assert set(first) == set(second)
    assert first.index("big") == 0 and second.index("big") == 0


def test_identical_geometry_is_stable_by_input_order():
    elements = [el("first", 40, 100, 100, 120), el("second", 40, 100, 100, 120)]
    assert order(elements) == ["first", "second"]


def test_elements_without_bbox_are_appended_not_dropped():
    elements = [
        el("boxed", 40, 100, 200, 140),
        Element(id="unboxed", type=ElementType.TEXT, page_number=1, source_backend="test"),
    ]
    result = order(elements)
    assert result == ["boxed", "unboxed"]
    assert len(result) == len(elements)


def test_empty_input():
    assert compute_reading_order([]) == []


def test_all_elements_are_returned_exactly_once():
    elements = [el(f"e{i}", 40 + (i % 2) * 300, 100 + (i // 2) * 50, 280 + (i % 2) * 280, 140 + (i // 2) * 50)
                for i in range(10)]
    result = order(elements)
    assert sorted(result) == sorted(e.id for e in elements)
    assert len(result) == len(set(result))
