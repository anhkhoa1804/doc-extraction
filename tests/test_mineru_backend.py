"""Tests for the MinerU2.5 table-candidate adapter.

Scope note: these cover the *adapter* only — HTML-to-canonical-Table
conversion, bbox normalisation, and availability/laziness contracts. They
deliberately do not load the 1.2B model (~2.3 GB, ~26 s load, ~60-220 s
per page on CPU); the model's own behaviour is measured in
`docs/sota_comparison.md`, not asserted here.

Why this adapter exists: on the five residual hard tables neither Table
Transformer nor Docling's TableFormer could extract, MinerU2.5 returned
TEDS_structure_only = 1.0000 on all five. See docs/sota_comparison.md.
"""
from __future__ import annotations

from pathlib import Path

from doc_extraction.backends.mineru_backend import (
    MinerUVLTableBackend,
    _bbox_from_mineru,
    parse_html_table,
)
from doc_extraction.pipelines.base import PageInput


def test_parse_html_table_simple_2x2():
    """The exact shape MinerU returned for the residual borderless grids."""
    html = "<table><tr><td>主句</td><td>从句</td></tr><tr><td>一般将来时</td><td>unless +一般现在时</td></tr></table>"

    table = parse_html_table(html, table_id="t0", page_number=1)

    assert table is not None
    assert (table.n_rows, table.n_cols) == (2, 2)
    assert [c.text for c in table.cells] == ["主句", "从句", "一般将来时", "unless +一般现在时"]
    assert table.source_backend == "mineru_vl"
    assert table.page_number == 1


def test_parse_html_table_returns_none_for_no_cells():
    """No cells means "this source produced no candidate" -- which must be
    distinguishable from "an empty table", because the composition layer
    treats an empty-but-present table differently from an absent one."""
    assert parse_html_table("<table></table>", table_id="t0") is None
    assert parse_html_table("", table_id="t0") is None
    assert parse_html_table("not html at all", table_id="t0") is None


def test_parse_html_table_honours_colspan():
    html = "<table><tr><td colspan='2'>wide</td></tr><tr><td>a</td><td>b</td></tr></table>"

    table = parse_html_table(html, table_id="t0")

    assert (table.n_rows, table.n_cols) == (2, 2)
    wide = table.cells[0]
    assert wide.text == "wide" and wide.col_span == 2 and (wide.row, wide.col) == (0, 0)
    assert [(c.row, c.col, c.text) for c in table.cells[1:]] == [(1, 0, "a"), (1, 1, "b")]


def test_parse_html_table_honours_rowspan_positions_following_cells():
    """The occupancy-grid case: with a rowspan above it, the next row's
    first cell belongs at col=1, not col=0. Getting this wrong silently
    shifts every subsequent cell left."""
    html = (
        "<table>"
        "<tr><td rowspan='2'>tall</td><td>top-right</td></tr>"
        "<tr><td>bottom-right</td></tr>"
        "</table>"
    )

    table = parse_html_table(html, table_id="t0")

    assert (table.n_rows, table.n_cols) == (2, 2)
    by_pos = {(c.row, c.col): c.text for c in table.cells}
    assert by_pos == {(0, 0): "tall", (0, 1): "top-right", (1, 1): "bottom-right"}
    assert table.cells[0].row_span == 2


def test_parse_html_table_flattens_wrapped_cell_text():
    """MinerU emits real newlines inside cells for wrapped content (seen
    directly on page-d29fe4d2); cells must carry single-line text."""
    html = "<table><tr><td>浙江省\n15,926万元\n248张</td></tr></table>"

    table = parse_html_table(html, table_id="t0")

    assert table.cells[0].text == "浙江省 15,926万元 248张"


def test_parse_html_table_marks_header_cells():
    html = "<table><tr><th>H1</th><th>H2</th></tr><tr><td>a</td><td>b</td></tr></table>"

    table = parse_html_table(html, table_id="t0")

    assert [c.is_header for c in table.cells] == [True, True, False, False]


def test_parse_html_table_ignores_bad_span_values():
    html = "<table><tr><td colspan='0'>a</td><td rowspan='abc'>b</td></tr></table>"

    table = parse_html_table(html, table_id="t0")

    assert all(c.col_span >= 1 and c.row_span >= 1 for c in table.cells)


def test_bbox_from_mineru_scales_normalised_coords_to_pixels():
    """MinerU returns page-relative 0..1 coords; the canonical IR is
    absolute pixels."""
    bbox = _bbox_from_mineru([0.1, 0.2, 0.5, 0.6], width=1000, height=2000)

    assert (bbox.x0, bbox.y0, bbox.x1, bbox.y1) == (100.0, 400.0, 500.0, 1200.0)


def test_bbox_from_mineru_handles_missing_or_malformed():
    assert _bbox_from_mineru(None, 100, 100) is None
    assert _bbox_from_mineru([0.1, 0.2], 100, 100) is None
    assert _bbox_from_mineru(["a", "b", "c", "d"], 100, 100) is None


def test_bbox_from_mineru_normalises_inverted_coordinates():
    """x0<=x1 and y0<=y1 are invariants of the canonical BBox."""
    bbox = _bbox_from_mineru([0.9, 0.8, 0.1, 0.2], width=100, height=100)

    assert bbox.x0 <= bbox.x1 and bbox.y0 <= bbox.y1


def test_native_tables_returns_empty_without_an_image_and_does_not_load_model():
    """A page with no rendered image must short-circuit before touching the
    2.3 GB model -- otherwise every text-only page pays the load cost."""
    backend = MinerUVLTableBackend()
    page = PageInput(page_index=0, width=100, height=100, image_path=None)

    assert backend.native_tables(page) == []
    assert backend._client is None, "model must not be loaded for an imageless page"


def test_backend_exposes_native_tables_hook_the_composition_layer_looks_for():
    """pipelines/base._gather_extra_table_candidates duck-types on this
    exact attribute name; renaming it would silently disconnect MinerU from
    the N-way composition without failing any other test."""
    from doc_extraction.pipelines.base import _gather_extra_table_candidates

    backend = MinerUVLTableBackend()
    assert callable(getattr(backend, "native_tables", None))

    class _NoImage:
        pass

    # A backend without the hook must still be skipped silently.
    assert _gather_extra_table_candidates(_NoImage(), page=None) == []
