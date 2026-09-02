"""Regression tests for table cell text ownership.

The failure these lock down was found by the production corpus (experiment
010) and is the worst kind: **silent data corruption**. Where a seal is drawn
across a table, cell text came back as `'NBHộH'` (the seal's `NHH` woven
through the cell's `Bộ`) and `'ỆGTói'` (`ỆT` through `Gói`). The table looked
healthy — right shape, every cell populated — recall barely moved, and no
check fired.

Root cause: cell text came from PyMuPDF's `find_tables().extract()`, which
re-gathers text by raw coordinate and discards the block/line/span structure
that already separates an overlay from the cell content beneath it.

The guarantee these tests encode is *ownership*: a text run belongs to at
most one cell, whole. It is never split across cells and never interleaved
with another run.

Fixtures are built here rather than read from `research/production_corpus/`,
whose documents are deliberately not committed.
"""
from __future__ import annotations

import pytest

pymupdf = pytest.importorskip("pymupdf")

from doc_extraction.backends.pymupdf_table_backend import (  # noqa: E402
    PyMuPDFTableBackend,
)
from doc_extraction.ingest.table_quality import assess_table  # noqa: E402
from doc_extraction.pipelines.base import PageInput  # noqa: E402

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
HEADERS = ["STT", "Mô tả hàng hóa", "Đơn vị", "Số lượng", "Thành tiền"]
ROWS = [
    ["1", "Sản phẩm A-100", "Cái", "12", "18.000.000"],
    ["2", "Bộ lọc khí Mã 22B", "Bộ", "4", "6.400.000"],
    ["3", "Dịch vụ lắp đặt", "Gói", "1", "3.500.000"],
]
# Wide enough that no cell's own text overflows its column: this file tests
# ownership, and a generator that overflows would confound the assertions.
WIDTHS = [30, 150, 60, 60, 100]
X0, Y0, RH = 60.0, 190.0, 20.0


def _text(page, point, s, size=9.0, color=(0, 0, 0)):
    page.insert_text(pymupdf.Point(*point), s, fontsize=size, fontfile=FONT,
                     fontname="dv", color=color)


def _table_pdf(path, stamp_at=None, stamp_text="ĐÃ DUYỆT"):
    """A ruled 4x5 table, optionally with an opaque seal drawn over it.

    `stamp_at` is the seal centre in page coordinates, or None for the clean
    control. The seal is a filled circle plus text, exactly as a Vietnamese
    business document carries one.
    """
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    total_w = sum(WIDTHS)
    n = len(ROWS) + 1
    for i in range(n + 1):
        page.draw_line(pymupdf.Point(X0, Y0 + i * RH),
                       pymupdf.Point(X0 + total_w, Y0 + i * RH),
                       color=(0.3, 0.3, 0.3), width=0.5)
    cx = X0
    for w in WIDTHS + [0]:
        page.draw_line(pymupdf.Point(cx, Y0), pymupdf.Point(cx, Y0 + n * RH),
                       color=(0.3, 0.3, 0.3), width=0.5)
        cx += w
    for r, row in enumerate([HEADERS, *ROWS]):
        cx = X0
        for w, cell in zip(WIDTHS, row):
            _text(page, (cx + 2, Y0 + r * RH + RH - 6), cell)
            cx += w

    if stamp_at is not None:
        c = pymupdf.Point(*stamp_at)
        red = (0.75, 0.05, 0.10)
        page.draw_circle(c, 40, color=red, fill=(0.95, 0.80, 0.82), width=0)
        page.draw_circle(c, 42, color=red, width=2.0)
        _text(page, (c.x - 30, c.y + 4), stamp_text, size=8.0, color=red)

    doc.save(path)
    doc.close()
    return path


def _extract(path):
    backend = PyMuPDFTableBackend()
    page = PageInput(page_index=0, width=595, height=842, dpi=72,
                     image_path=None, source_pdf_path=path)
    result = backend.extract(page, [])
    assert result.tables, "no table detected in the fixture"
    return result


def _grid(table):
    g = {}
    for c in table.cells:
        g[(c.row, c.col)] = (c.text or "").strip()
    return g


# --------------------------------------------------------------------------
# Ownership: the property the fix exists to guarantee
# --------------------------------------------------------------------------


def test_clean_table_cells_are_exact(tmp_path):
    """The control. Every cell must come back exactly as drawn, or nothing
    else in this file means anything."""
    table = _extract(_table_pdf(tmp_path / "clean.pdf")).tables[0]
    g = _grid(table)
    for col, head in enumerate(HEADERS):
        assert g[(0, col)] == head
    for r, row in enumerate(ROWS, start=1):
        for col, want in enumerate(row):
            assert g[(r, col)] == want, f"cell ({r},{col})"


def test_vietnamese_diacritics_survive(tmp_path):
    """Half the production population is Vietnamese; a cell fix that mangles
    diacritics is not a fix."""
    g = _grid(_extract(_table_pdf(tmp_path / "vi.pdf")).tables[0])
    assert g[(0, 1)] == "Mô tả hàng hóa"
    assert g[(2, 1)] == "Bộ lọc khí Mã 22B"
    assert g[(3, 2)] == "Gói"


def test_overlay_never_interleaves_into_cell_text(tmp_path):
    """The regression lock.

    Previously produced 'NBHộH' and 'ỆGTói' — the seal's characters woven
    through the cell's. Whatever else the overlay does, no cell may contain a
    *fragment* of a source text run: every cell is whole runs or nothing.
    """
    path = _table_pdf(tmp_path / "stamped.pdf", stamp_at=(240, 250))
    g = _grid(_extract(path).tables[0])

    # Every non-empty cell must be built only from complete source runs.
    doc = pymupdf.open(path)
    runs = {s["text"].strip()
            for b in doc[0].get_text("dict")["blocks"]
            for line in b.get("lines", [])
            for s in line["spans"] if s["text"].strip()}
    doc.close()

    for (r, c), text in g.items():
        if not text:
            continue
        for token in text.split():
            assert any(token in run for run in runs), (
                f"cell ({r},{c}) = {text!r} contains {token!r}, which is not part "
                f"of any source text run — this is the interleaving bug")


def test_cell_text_is_never_a_partial_run(tmp_path):
    """`extract()` also split a single span across a cell boundary, turning
    'Số lượngThành tiền' into 'Số lượn' + 'gThành tiền'. A cell must never
    hold a proper prefix/suffix of a run."""
    path = _table_pdf(tmp_path / "clean2.pdf")
    g = _grid(_extract(path).tables[0])
    doc = pymupdf.open(path)
    runs = [s["text"].strip()
            for b in doc[0].get_text("dict")["blocks"]
            for line in b.get("lines", [])
            for s in line["spans"] if s["text"].strip()]
    doc.close()
    for text in g.values():
        if text:
            assert text in runs or all(t in runs for t in text.split("  ")), \
                f"{text!r} is not a whole source run"


def test_no_text_is_duplicated_across_cells(tmp_path):
    """Ownership means *one* cell. A run appearing in two cells would inflate
    every downstream count."""
    g = _grid(_extract(_table_pdf(tmp_path / "dup.pdf", stamp_at=(240, 250))).tables[0])
    seen: dict[str, tuple[int, int]] = {}
    for pos, text in g.items():
        for token in text.split():
            if len(token) < 3:
                continue  # short numerals legitimately repeat
            assert token not in seen, (
                f"{token!r} appears in {seen.get(token)} and {pos}")
            seen[token] = pos


def test_stamp_outside_the_table_stays_outside(tmp_path):
    """A seal elsewhere on the page must not be pulled into the grid."""
    path = _table_pdf(tmp_path / "outside.pdf", stamp_at=(300, 600))
    g = _grid(_extract(path).tables[0])
    joined = " ".join(g.values())
    assert "DUYỆT" not in joined
    # and the clean content is untouched
    assert g[(1, 1)] == "Sản phẩm A-100"


# --------------------------------------------------------------------------
# Quality gate
# --------------------------------------------------------------------------


def test_gate_trusts_a_clean_table(tmp_path):
    result = _extract(_table_pdf(tmp_path / "gate_clean.pdf"))
    report = assess_table(result.tables[0], result.spans_by_table[result.tables[0].id])
    assert report.trusted, report.signals
    assert report.severity == "none"


def test_gate_flags_an_overlaid_table(tmp_path):
    """The gate's whole purpose: contamination that survives the ownership
    fix must be *visible* rather than silent."""
    result = _extract(_table_pdf(tmp_path / "gate_stamped.pdf", stamp_at=(240, 250)))
    table = result.tables[0]
    report = assess_table(table, result.spans_by_table[table.id])
    assert not report.trusted
    assert report.signals, "a suspicious table must say why"
    assert report.affected_cells, "a suspicious table must say where"
    assert report.severity in ("medium", "high")


def test_gate_reports_reason_cells_and_severity(tmp_path):
    """Section 13: never return a suspicious table as if it were fine."""
    result = _extract(_table_pdf(tmp_path / "gate_detail.pdf", stamp_at=(240, 250)))
    table = result.tables[0]
    report = assess_table(table, result.spans_by_table[table.id])
    assert isinstance(report.signals, list) and all(isinstance(s, str) for s in report.signals)
    assert all(isinstance(rc, tuple) and len(rc) == 2 for rc in report.affected_cells)
    assert report.severity in ("none", "medium", "high")
    # the warning must reach the caller, not just the report object
    assert any("table quality" in w.lower() for w in result.warnings), result.warnings


def test_gate_does_not_flag_an_empty_cell_alone(tmp_path):
    """An empty cell is ordinary. Flagging it would make the gate noisy enough
    to be ignored, which is the usual way a quality signal dies."""
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    for i in range(3):
        page.draw_line(pymupdf.Point(60, 200 + i * 20), pymupdf.Point(260, 200 + i * 20),
                       color=(0.3, 0.3, 0.3), width=0.5)
    for x in (60, 160, 260):
        page.draw_line(pymupdf.Point(x, 200), pymupdf.Point(x, 240),
                       color=(0.3, 0.3, 0.3), width=0.5)
    _text(page, (62, 214), "Alpha")
    _text(page, (62, 234), "Beta")          # right column intentionally empty
    path = tmp_path / "empty_cell.pdf"
    doc.save(path)
    doc.close()

    result = _extract(path)
    table = result.tables[0]
    report = assess_table(table, result.spans_by_table[table.id])
    assert report.trusted, f"empty cells alone must not trip the gate: {report.signals}"


# --------------------------------------------------------------------------
# Property-based: the invariants must hold at arbitrary geometry, not just at
# the one stamp coordinate the corpus happens to draw.
#
# A fix validated only on fixed fixtures is indistinguishable from a fix tuned
# to them. These generate randomized tables — origin, column widths, row
# height, font size, row count, stamp centre and radius, hence overlap ratio —
# and assert properties rather than expected strings.
#
# Measured over 80 variants (research/experiments/_table_integrity/
# probe_randomized.py): structure recovered 80/80, zero fragmentation, zero
# duplication, zero diacritic loss, gate recall 1.000 at precision 0.913.
# --------------------------------------------------------------------------

import random  # noqa: E402
import unicodedata  # noqa: E402

STAMP_LINES = ["CÔNG TY TNHH", "ĐÃ DUYỆT"]
_RANDOM_ROWS = ROWS + [
    ["4", "Vật tư phụ trợ", "Thùng", "7", "9.750.000"],
    ["5", "Bảo trì định kỳ", "Lần", "2", "4.200.000"],
]


def _norm(s):
    return " ".join(unicodedata.normalize("NFC", s or "").split())


def _random_table_pdf(path, rng, stamped):
    """One randomized invoice table, optionally with a seal drawn over it."""
    n_rows = rng.randint(3, 5)
    size = rng.choice([7.5, 8.0, 9.0, 10.0])
    rh = rng.choice([16.0, 18.0, 20.0, 24.0])
    widths = [rng.randint(22, 34), rng.randint(120, 175), rng.randint(40, 62),
              rng.randint(36, 58), rng.randint(80, 110)]
    x0, y0 = rng.uniform(45, 90), rng.uniform(150, 300)

    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    total_w, n = sum(widths), n_rows + 1
    for i in range(n + 1):
        page.draw_line(pymupdf.Point(x0, y0 + i * rh),
                       pymupdf.Point(x0 + total_w, y0 + i * rh),
                       color=(0.3, 0.3, 0.3), width=0.5)
    cx = x0
    for w in widths + [0]:
        page.draw_line(pymupdf.Point(cx, y0), pymupdf.Point(cx, y0 + n * rh),
                       color=(0.3, 0.3, 0.3), width=0.5)
        cx += w

    grid = [list(HEADERS)] + [list(r) for r in _RANDOM_ROWS[:n_rows]]
    for r, row in enumerate(grid):
        cx = x0
        for w, cell in zip(widths, row):
            _text(page, (cx + 2, y0 + r * rh + rh - size * 0.55), cell, size=size)
            cx += w

    if stamped:
        c = pymupdf.Point(rng.uniform(x0 + 20, x0 + total_w - 20),
                          rng.uniform(y0 + 10, y0 + n * rh - 10))
        radius = rng.uniform(28, 52)
        red = (0.75, 0.05, 0.10)
        page.draw_circle(c, radius, color=red, fill=(0.95, 0.80, 0.82), width=0)
        page.draw_circle(c, radius + 2, color=red, width=2.0)
        for k, line in enumerate(STAMP_LINES):
            _text(page, (c.x - radius * 0.75, c.y - 4 + k * 12), line,
                  size=size * 0.85, color=red)

    doc.save(path)
    doc.close()
    return grid


@pytest.mark.parametrize("seed", range(12))
def test_property_ownership_holds_under_randomization(tmp_path, seed):
    """I1-I4: whatever the geometry, no cell may hold a fragment of a run, no
    run may be owned twice, diacritics must survive, and an overlay must not
    change the detected grid."""
    rng = random.Random(9000 + seed)
    stamped = bool(seed % 2)
    path = tmp_path / f"rand{seed}.pdf"
    grid = _random_table_pdf(path, rng, stamped)

    result = _extract(path)
    table = result.tables[0]

    # I4 — the seal must not alter the structure
    assert [table.n_rows, table.n_cols] == [len(grid), 5]

    doc = pymupdf.open(path)
    runs = [_norm(s["text"]) for s in page_text_runs_for_test(doc[0])]
    doc.close()

    cells = {(c.row, c.col): _norm(c.text) for c in table.cells}

    # I1 — no fragment of a source run
    for pos, text in cells.items():
        for tok in text.split():
            if len(tok) >= 2:
                assert any(tok in r for r in runs), (
                    f"seed={seed} cell r{pos[0]}c{pos[1]}={text!r}: {tok!r} is not "
                    f"part of any whole source run")

    # I2 — no substantial token owned by two cells
    stamp_tokens = {t for line in STAMP_LINES for t in _norm(line).split()}
    seen: dict[str, tuple[int, int]] = {}
    for pos, text in cells.items():
        for tok in set(text.split()):
            if len(tok) < 4 or tok in stamp_tokens:
                continue
            assert tok not in seen, f"seed={seed} {tok!r} in {seen[tok]} and {pos}"
            seen[tok] = pos

    # I3 — every diacritic-bearing expected value survives somewhere
    joined = " ".join(cells.values())
    for row in grid:
        for value in row:
            v = _norm(value)
            if v and any(ord(ch) > 127 for ch in v):
                assert v in joined, f"seed={seed}: lost {v!r}"


@pytest.mark.parametrize("seed", range(12))
def test_property_gate_never_misses_contamination(tmp_path, seed):
    """I6: a table holding text from outside its own vocabulary must be
    flagged. A false alarm is tolerable; a silent corruption is the failure
    this whole mechanism exists to prevent, so recall is the property tested.
    """
    rng = random.Random(9000 + seed)
    path = tmp_path / f"gate{seed}.pdf"
    grid = _random_table_pdf(path, rng, stamped=bool(seed % 2))

    result = _extract(path)
    table = result.tables[0]
    report = assess_table(table, result.spans_by_table[table.id])

    vocab = {tok for row in grid for v in row for tok in _norm(v).split()}
    contaminated = [
        f"r{c.row}c{c.col}" for c in table.cells
        if any(tok not in vocab for tok in _norm(c.text).split())
    ]
    if contaminated:
        assert not report.trusted, (
            f"seed={seed}: cells {contaminated} hold foreign text but the gate "
            f"reported the table as trustworthy")


def page_text_runs_for_test(page):
    from doc_extraction.backends.pymupdf_table_backend import page_text_runs
    return page_text_runs(page)
