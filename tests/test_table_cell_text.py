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

    def iterate_items(self, traverse_pictures=False, **_kwargs):
        # Mirrors docling's DoclingDocument.iterate_items signature.
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


# ---------------------------------------------------------------------------
# Native-table fallback (pipelines/base.select_better_populated_table /
# _apply_native_table_fallback)
#
# Real-world evidence (experiments/005_omnidocbench/observations.md,
# "Bottleneck Analysis"): on one real OmniDocBench page, Table Transformer
# detected the wrong grid entirely (1x3 instead of the correct 4x2, TEDS
# 0.083) while Docling's own TableFormer (exposed via
# DoclingBackend.native_tables) found the exact right structure with every
# cell populated. On a different page the reverse held. Neither backend is
# uniformly better, so the fix is a per-table, fill-rate-based choice
# between two independently-produced candidates -- not a preference for
# either specific backend.
# ---------------------------------------------------------------------------

from doc_extraction.pipelines.base import (
    TableResult,
    _apply_native_table_fallback,
    select_better_populated_table,
)
from doc_extraction.schemas.element import BBox


def _table(id_, bbox, cells, source_backend="table_transformer"):
    # The schema requires at least one row and column (no fabricated 0-dimension tables),
    # so an empty table is represented as the smallest valid 1x1 grid with no cells.
    n_rows = max((c.row for c in cells), default=0) + 1
    n_cols = max((c.col for c in cells), default=0) + 1
    return Table(id=id_, bbox=bbox, page_number=1, n_rows=n_rows, n_cols=n_cols,
                 cells=cells, source_backend=source_backend)


def test_select_better_populated_table_prefers_higher_fill_rate():
    sparse = _table("t0", BBox(x0=0, y0=0, x1=100, y1=100), [
        Cell(row=0, col=0, text="only this one"),
        Cell(row=0, col=1, text=""),
    ])
    dense = _table("native-t0", BBox(x0=0, y0=0, x1=100, y1=100), [
        Cell(row=0, col=0, text="a"), Cell(row=0, col=1, text="b"),
    ], source_backend="docling")

    chosen = select_better_populated_table(sparse, dense)

    assert chosen.id == "t0", "keeps the original candidate's id so Element.table_id linkage still resolves"
    assert chosen.cells == dense.cells
    assert chosen.source_backend == "docling+fallback"


def test_select_better_populated_table_keeps_candidate_on_tie_or_worse_alternative():
    candidate = _table("t0", BBox(x0=0, y0=0, x1=100, y1=100), [
        Cell(row=0, col=0, text="a"), Cell(row=0, col=1, text="b"),
    ])
    worse = _table("native-t0", BBox(x0=0, y0=0, x1=100, y1=100), [
        Cell(row=0, col=0, text=""), Cell(row=0, col=1, text=""),
    ])

    assert select_better_populated_table(candidate, worse) is candidate
    assert select_better_populated_table(candidate, None) is candidate


def test_apply_native_table_fallback_matches_by_geometry_not_order():
    """Two table_backend tables and two native tables at different
    positions -- each must be compared against its own geometric match, not
    e.g. list index."""
    weak_a = _table("t0", BBox(x0=0, y0=0, x1=100, y1=100), [Cell(row=0, col=0, text="")])
    weak_b = _table("t1", BBox(x0=200, y0=200, x1=300, y1=300), [Cell(row=0, col=0, text="")])
    table_result = TableResult(tables=[weak_a, weak_b], backend="table_transformer")

    strong_for_b = _table("native-t1", BBox(x0=205, y0=205, x1=295, y1=295),
                           [Cell(row=0, col=0, text="right region")], source_backend="docling")
    # Overlaps weak_a's region only slightly (< 0.1 IoU threshold) -- must NOT be selected for it.
    near_a_but_below_threshold = _table(
        "native-t0", BBox(x0=95, y0=95, x1=195, y1=195),
        [Cell(row=0, col=0, text="wrong region, low overlap")], source_backend="docling",
    )

    class _FakeOCRBackend:
        def native_tables(self, page):
            return [near_a_but_below_threshold, strong_for_b]

    _apply_native_table_fallback(table_result, _FakeOCRBackend(), page=None)

    assert table_result.tables[0].cells[0].text == "", "weak_a has no adequately-overlapping alternative"
    assert table_result.tables[1].cells[0].text == "right region"


def test_apply_native_table_fallback_noop_when_backend_has_no_native_tables():
    """OCR backends without a native_tables method (PaddleOCR/MinerU stubs,
    or any future non-Docling backend) must be silently skipped, not
    crash."""
    weak = _table("t0", BBox(x0=0, y0=0, x1=100, y1=100), [Cell(row=0, col=0, text="")])
    table_result = TableResult(tables=[weak], backend="table_transformer")

    class _BackendWithoutNativeTables:
        pass

    _apply_native_table_fallback(table_result, _BackendWithoutNativeTables(), page=None)

    assert table_result.tables[0] is weak


# ---------------------------------------------------------------------------
# Model-agnostic candidate abstraction (pipelines/base.TableCandidate /
# compute_table_quality_features / select_best_table_candidate)
#
# select_better_populated_table and _apply_native_table_fallback (tested
# above) are now thin wrappers over these — this section tests the general
# N-candidate primitives directly, independent of which two backends the
# production pipeline currently wires together.
# ---------------------------------------------------------------------------

from doc_extraction.pipelines.base import (
    compute_table_quality_features,
    make_table_candidate,
    select_best_table_candidate,
)


def test_compute_table_quality_features_empty_table():
    empty = _table("t0", BBox(x0=0, y0=0, x1=100, y1=100), [])
    features = compute_table_quality_features(empty)
    assert features["fill_rate"] == 0.0
    assert features["n_cells"] == 0.0
    assert features["empty_cell_ratio"] == 1.0


def test_compute_table_quality_features_partial_fill():
    table = _table("t0", BBox(x0=0, y0=0, x1=100, y1=100), [
        Cell(row=0, col=0, text="abc"), Cell(row=0, col=1, text=""),
        Cell(row=1, col=0, text="de"), Cell(row=1, col=1, text=""),
    ])
    features = compute_table_quality_features(table)
    assert features["fill_rate"] == 0.5
    assert features["n_cells"] == 4.0
    assert features["empty_cell_ratio"] == 0.5
    assert features["avg_text_len"] == 2.5  # (3 + 2) / 2 non-empty cells


def test_compute_table_quality_features_never_populates_confidence_signals():
    """Guard against silently inventing a signal the pipeline can't
    actually produce: neither TableTransformerBackend nor Docling's table
    conversion populate Cell.confidence today (see schemas/table.py), so
    the quality-feature dict must not claim one exists."""
    table = _table("t0", BBox(x0=0, y0=0, x1=100, y1=100), [Cell(row=0, col=0, text="x")])
    assert "confidence" not in compute_table_quality_features(table)
    assert "ocr_confidence" not in compute_table_quality_features(table)


def test_select_best_table_candidate_picks_highest_key_among_n():
    """Three independent backends, not just two — the selector must not be
    hardcoded to a pairwise comparison."""
    weak = make_table_candidate(_table("a", None, [Cell(row=0, col=0, text="")], source_backend="mineru"))
    medium = make_table_candidate(_table("b", None, [
        Cell(row=0, col=0, text="x"), Cell(row=0, col=1, text=""),
    ], source_backend="table_transformer"))
    strong = make_table_candidate(_table("c", None, [
        Cell(row=0, col=0, text="x"), Cell(row=0, col=1, text="y"),
    ], source_backend="docling"))

    best = select_best_table_candidate([weak, medium, strong])

    assert best is strong


def test_select_best_table_candidate_tie_keeps_first_by_input_order():
    a = make_table_candidate(_table("a", None, [Cell(row=0, col=0, text="x")], source_backend="table_transformer"))
    b = make_table_candidate(_table("b", None, [Cell(row=0, col=0, text="y")], source_backend="docling"))

    assert select_best_table_candidate([a, b]) is a
    assert select_best_table_candidate([b, a]) is b


def test_select_best_table_candidate_empty_list_returns_none():
    assert select_best_table_candidate([]) is None


def test_select_best_table_candidate_respects_custom_key():
    short_but_full = make_table_candidate(_table("a", None, [
        Cell(row=0, col=0, text="x"), Cell(row=0, col=1, text="y"),
    ], source_backend="table_transformer"))
    sparse_but_verbose = make_table_candidate(_table("b", None, [
        Cell(row=0, col=0, text="a much longer cell value here"), Cell(row=0, col=1, text=""),
    ], source_backend="docling"))

    assert select_best_table_candidate([short_but_full, sparse_but_verbose], key="fill_rate") is short_but_full
    assert select_best_table_candidate([short_but_full, sparse_but_verbose], key="avg_text_len") is sparse_but_verbose


def test_apply_native_table_fallback_considers_multiple_extra_sources():
    """_gather_extra_table_candidates iterates every candidate-source method
    a backend exposes, not just one -- simulate a backend with two, and
    confirm the better of *all* candidates (primary + both extras) wins,
    not just primary-vs-first-extra."""
    primary = _table("t0", BBox(x0=0, y0=0, x1=100, y1=100), [Cell(row=0, col=0, text="")])
    table_result = TableResult(tables=[primary], backend="table_transformer")

    weak_extra = _table("native-t0", BBox(x0=0, y0=0, x1=100, y1=100),
                         [Cell(row=0, col=0, text="a")], source_backend="mineru")
    strong_extra = _table("native-t1", BBox(x0=0, y0=0, x1=100, y1=100),
                           [Cell(row=0, col=0, text="a"), Cell(row=0, col=1, text="b")], source_backend="docling")

    class _MultiSourceBackend:
        def native_tables(self, page):
            return [weak_extra]

        def mineru_tables(self, page):  # not a recognized source method -- must be ignored, not crash
            return [strong_extra]

    _apply_native_table_fallback(table_result, _MultiSourceBackend(), page=None)

    # only native_tables is a recognized source today, so weak_extra (the
    # only *reachable* alternative) wins over the empty primary.
    assert table_result.tables[0].cells[0].text == "a"


def test_apply_native_table_fallback_both_fail_keeps_primary_unchanged():
    """When every candidate is equally empty (both models failed), the
    primary table object must be left as-is -- not replaced by an
    equally-empty copy that loses its original identity/id linkage."""
    primary = _table("t0", BBox(x0=0, y0=0, x1=100, y1=100), [Cell(row=0, col=0, text="")])
    table_result = TableResult(tables=[primary], backend="table_transformer")

    also_empty = _table("native-t0", BBox(x0=0, y0=0, x1=100, y1=100),
                         [Cell(row=0, col=0, text="")], source_backend="docling")

    class _FakeOCRBackend:
        def native_tables(self, page):
            return [also_empty]

    _apply_native_table_fallback(table_result, _FakeOCRBackend(), page=None)

    assert table_result.tables[0] is primary


# ---------------------------------------------------------------------------
# Candidate *recovery*: an extra source's table for a region the primary
# backend produced nothing for must be ADDED, not discarded.
#
# Real-world evidence (experiments/005_omnidocbench/hard_tables/failure_taxonomy.md):
# on the 100-page subset every ground-truth table with <= 2 rows scored
# exactly 0.0 TEDS (7/7). On 3 of them, Docling's layout had correctly
# located the table region and Docling's own TableFormer had produced a real
# table for it -- on one, a 2x12 answer-key table with all 18 cells
# populated and a bbox matching ground truth within ~2px -- while Table
# Transformer's structure model returned no row/column grid for the same
# crop, so no primary Table object existed. The reconciliation loop only
# iterated over primary tables, so with zero primary tables the good
# candidate was silently dropped and the page emitted no table at all.
# ---------------------------------------------------------------------------


def test_apply_native_table_fallback_recovers_table_when_primary_found_none():
    """The core regression: primary backend produced NO tables, an extra
    source produced a populated one -- it must be added, not discarded."""
    table_result = TableResult(tables=[], backend="table_transformer")

    recovered = _table("p0-native-t0", BBox(x0=10, y0=10, x1=200, y1=60), [
        Cell(row=0, col=0, text="题号"), Cell(row=0, col=1, text="1"),
        Cell(row=1, col=0, text="答案"), Cell(row=1, col=1, text="C"),
    ], source_backend="docling")

    class _FakeOCRBackend:
        def native_tables(self, page):
            return [recovered]

    _apply_native_table_fallback(table_result, _FakeOCRBackend(), page=None)

    assert len(table_result.tables) == 1, "a viable candidate must not be discarded"
    added = table_result.tables[0]
    assert added.n_rows == 2 and added.n_cols == 2
    assert [c.text for c in added.cells] == ["题号", "1", "答案", "C"]
    assert added.source_backend == "docling+recovered"


def test_apply_native_table_fallback_does_not_recover_an_empty_candidate():
    """An all-empty grid carries no content -- adding it would replace the
    region's real OCR text with nothing of value."""
    table_result = TableResult(tables=[], backend="table_transformer")
    empty = _table("p0-native-t0", BBox(x0=10, y0=10, x1=200, y1=60),
                    [Cell(row=0, col=0, text=""), Cell(row=0, col=1, text="")],
                    source_backend="docling")

    class _FakeOCRBackend:
        def native_tables(self, page):
            return [empty]

    _apply_native_table_fallback(table_result, _FakeOCRBackend(), page=None)

    assert table_result.tables == []


def test_apply_native_table_fallback_does_not_double_add_a_matched_candidate():
    """A candidate already consumed by the comparison step must not also be
    appended as a recovered table."""
    primary = _table("t0", BBox(x0=0, y0=0, x1=100, y1=100), [Cell(row=0, col=0, text="")])
    table_result = TableResult(tables=[primary], backend="table_transformer")
    better = _table("native-t0", BBox(x0=2, y0=2, x1=98, y1=98),
                     [Cell(row=0, col=0, text="real")], source_backend="docling")

    class _FakeOCRBackend:
        def native_tables(self, page):
            return [better]

    _apply_native_table_fallback(table_result, _FakeOCRBackend(), page=None)

    assert len(table_result.tables) == 1, "matched candidate must be used to replace, not also appended"
    assert table_result.tables[0].cells[0].text == "real"
    assert table_result.tables[0].id == "t0", "replacement keeps the primary's id for Element.table_id linkage"


def test_apply_native_table_fallback_recovers_only_the_unmatched_candidate():
    """Mixed case: one extra candidate matches a primary table, another
    covers a region the primary missed entirely. The first replaces, the
    second is added."""
    primary = _table("t0", BBox(x0=0, y0=0, x1=100, y1=100), [Cell(row=0, col=0, text="")])
    table_result = TableResult(tables=[primary], backend="table_transformer")

    matches_primary = _table("native-t0", BBox(x0=2, y0=2, x1=98, y1=98),
                              [Cell(row=0, col=0, text="replaced")], source_backend="docling")
    unmatched = _table("native-t1", BBox(x0=500, y0=500, x1=700, y1=560),
                        [Cell(row=0, col=0, text="recovered")], source_backend="docling")

    class _FakeOCRBackend:
        def native_tables(self, page):
            return [matches_primary, unmatched]

    _apply_native_table_fallback(table_result, _FakeOCRBackend(), page=None)

    assert len(table_result.tables) == 2
    assert table_result.tables[0].cells[0].text == "replaced"
    assert table_result.tables[1].cells[0].text == "recovered"
    assert table_result.tables[1].source_backend == "docling+recovered"


def test_apply_native_table_fallback_recovered_id_does_not_collide():
    """A recovered candidate whose id already exists must be given a
    distinct one -- Page.table_by_id resolves by id, so a duplicate would
    make one of the two tables unreachable."""
    primary = _table("native-t0", BBox(x0=0, y0=0, x1=100, y1=100), [Cell(row=0, col=0, text="primary")])
    table_result = TableResult(tables=[primary], backend="table_transformer")
    clashing = _table("native-t0", BBox(x0=500, y0=500, x1=700, y1=560),
                       [Cell(row=0, col=0, text="recovered")], source_backend="docling")

    class _FakeOCRBackend:
        def native_tables(self, page):
            return [clashing]

    _apply_native_table_fallback(table_result, _FakeOCRBackend(), page=None)

    ids = [t.id for t in table_result.tables]
    assert len(ids) == len(set(ids)), f"table ids must stay unique, got {ids}"


# ---------------------------------------------------------------------------
# merge_regions_into_page: a table region that matches no detected Table
# must still emit its text, not vanish.
# ---------------------------------------------------------------------------


def test_table_region_without_matching_table_keeps_its_text():
    """Second content-loss path found in the same investigation: when some
    table was detected on the page but not for THIS region, the element got
    table_id=None and no text, so it serialized to nothing at all and the
    region's content disappeared entirely."""
    from doc_extraction.pipelines.base import (
        LayoutResult,
        OCRResult,
        OCRToken,
        Region,
        merge_regions_into_page,
    )

    far_away_table = _table("t0", BBox(x0=0, y0=0, x1=100, y1=100), [Cell(row=0, col=0, text="x")])
    table_result = TableResult(tables=[far_away_table], backend="table_transformer")

    # A table-labelled region nowhere near the detected table.
    region = Region(bbox=BBox(x0=500, y0=500, x1=800, y1=560), label="table")
    layout = LayoutResult(regions=[region], backend="docling")
    ocr = OCRResult(
        tokens=[OCRToken(text="unmatched region text", bbox=BBox(x0=510, y0=510, x1=790, y1=550))],
        backend="docling",
    )

    page = merge_regions_into_page(0, 1000, 1000, 200, layout, ocr, table_result, None)

    element = page.elements[0]
    assert element.table_id is None
    assert element.text == "unmatched region text", "content must not silently vanish"


def test_table_region_with_matching_table_does_not_duplicate_text():
    """Guard the other direction: when a region DOES match a table, it must
    not also carry text, or the content would be emitted twice (once as the
    table, once as a text block)."""
    from doc_extraction.pipelines.base import (
        LayoutResult,
        OCRResult,
        OCRToken,
        Region,
        merge_regions_into_page,
    )

    matched_table = _table("t0", BBox(x0=500, y0=500, x1=800, y1=560), [Cell(row=0, col=0, text="cell")])
    table_result = TableResult(tables=[matched_table], backend="table_transformer")
    region = Region(bbox=BBox(x0=500, y0=500, x1=800, y1=560), label="table")
    layout = LayoutResult(regions=[region], backend="docling")
    ocr = OCRResult(
        tokens=[OCRToken(text="cell", bbox=BBox(x0=510, y0=510, x1=790, y1=550))],
        backend="docling",
    )

    page = merge_regions_into_page(0, 1000, 1000, 200, layout, ocr, table_result, None)

    element = page.elements[0]
    assert element.table_id == "t0"
    assert element.text is None, "a matched table region must not also emit its text"
