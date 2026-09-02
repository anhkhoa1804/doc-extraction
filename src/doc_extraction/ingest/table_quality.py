"""Table quality gate: is this table's cell text trustworthy?

Why this exists
---------------
Experiment 010 found the worst failure class in the project so far — a table
that is *silently wrong*. Where a seal was drawn across an invoice, cells came
back as `'NBHộH'` and `'ỆGTói'`: the overlay's characters woven through the
cell's. The grid was the right shape, every cell was populated, text recall
barely moved, and nothing anywhere reported a problem.

The ownership fix in `pymupdf_table_backend` removes the *interleaving* — no
cell can hold a fragment of a text run any more. It cannot remove all
*contamination*: when an overlay sits inside a cell, its text is a legitimate
text run at that position, and geometry alone does not say it is foreign. That
was measured rather than assumed — on the corpus documents, an overlay's
vertical centre differs from its row's by only 1.4–2.6 pt, far too little to
separate the two by position.

So the residual belongs to a gate. This module answers one question:

    Should a consumer trust these cells, and if not, which ones and why?

Design constraints (mission §11, §21): cheap, interpretable, testable. No
model, no new dependency. It runs on data the extraction already produced.

What it deliberately does not do
--------------------------------
It does not try to detect every table failure. It detects the corruption class
there is evidence for, plus the geometric disagreement that produces it. A
gate that fires on ordinary tables gets ignored, and an ignored gate is worse
than none — so an empty cell, on its own, is not a signal.

Measured operating point
------------------------
On the production corpus (13 born-digital tables, `run_table_benchmark.py`):
precision 1.000, recall 1.000, zero false alarms.

That corpus draws its seal at one position, so it cannot show where the gate
degrades. Over **80 randomized variants** — randomized table origin, column
widths, row height, font size, row count, stamp centre and radius, hence
overlap ratio (`probe_randomized.py`) — the two severities separate into a
genuine operating curve:

    severity >= medium    precision 0.913    recall 1.000
    severity == high      precision 1.000    recall 0.952

Every false alarm is a `medium` raised by signal 1 alone: randomized column
widths make a cell's own text overflow its ruling, which *is* a boundary
crossing, just a benign one. Every `high` was real contamination.

So the severity is not decoration — it is the knob. A consumer that cannot
tolerate false alarms should act on `high` and merely record `medium`; one
that cannot tolerate a missed corruption should treat both as untrusted. The
thresholds are deliberately *not* tuned to close that gap, because the only
evidence available is synthetic and tuning against one generator's geometry
is how a gate silently becomes a corpus artifact.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from doc_extraction.schemas.table import Table

SEVERITY_NONE = "none"
SEVERITY_MEDIUM = "medium"
SEVERITY_HIGH = "high"

# A span must overlap a cell by at least this fraction of its own area before
# it is considered to belong there. Below it, the run is crossing boundaries.
MIN_CONTAINMENT = 0.6

# Font size differing from the row's dominant size by more than this ratio is
# treated as a style outlier. 8pt seal text against 9pt cell text is 0.11, so
# this is deliberately tight; it is corroborating evidence, never sole cause.
SIZE_OUTLIER_RATIO = 0.08


@dataclass
class TableQualityReport:
    """The gate's verdict. `trusted` is the decision; the rest is why."""

    trusted: bool = True
    severity: str = SEVERITY_NONE
    signals: list[str] = field(default_factory=list)
    affected_cells: list[tuple[int, int]] = field(default_factory=list)

    def as_warning(self, table_id: str) -> str:
        """One line for `TableResult.warnings`, so the finding reaches the
        caller and the run log rather than living only on this object."""
        where = ", ".join(f"r{r}c{c}" for r, c in self.affected_cells[:6])
        more = "" if len(self.affected_cells) <= 6 else f" (+{len(self.affected_cells) - 6} more)"
        return (f"table quality: {table_id} SUSPICIOUS [{self.severity}] — "
                f"{'; '.join(self.signals)}; cells: {where}{more}")


def _area(b) -> float:
    return max(0.0, (b[2] - b[0])) * max(0.0, (b[3] - b[1]))


def _intersection(a, b) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    return ix * iy


def _containment(span_bbox, cell_bbox) -> float:
    """Fraction of the span that lies inside the cell."""
    a = _area(span_bbox)
    return _intersection(span_bbox, cell_bbox) / a if a > 0 else 0.0


def assess_table(table: Table, spans: list[dict[str, Any]] | None) -> TableQualityReport:
    """Judge one table against the text runs that produced it.

    `spans` are the source text runs considered for this table, each a
    PyMuPDF span dict (``bbox``, ``size``, ``color``, ``text``) annotated by
    the backend with the cell it was assigned to (``_cell``: ``(row, col)`` or
    ``None`` when the run was rejected). Passing None means the backend could
    not supply run-level evidence — the honest verdict then is "trusted", not
    a guess, because there is nothing to judge.
    """
    report = TableQualityReport()
    if not spans:
        return report

    cell_boxes = {
        (c.row, c.col): (c.bbox.x0, c.bbox.y0, c.bbox.x1, c.bbox.y1)
        for c in table.cells if c.bbox is not None
    }
    if not cell_boxes:
        return report

    affected: set[tuple[int, int]] = set()
    signals: list[str] = []

    # --- Signal 1: a run that straddles cell boundaries -------------------
    # A table whose own text runs disagree with its ruling lines is either
    # mis-detected or has something drawn across it. Either way the cells
    # below are not reliable.
    crossing = 0
    for span in spans:
        boxes = [(pos, _containment(span["bbox"], cb)) for pos, cb in cell_boxes.items()]
        touching = [(pos, f) for pos, f in boxes if f > 0.05]
        if len(touching) > 1 and max(f for _, f in touching) < MIN_CONTAINMENT:
            crossing += 1
            affected.update(pos for pos, _ in touching)
    if crossing:
        signals.append(f"{crossing} text run(s) cross cell boundaries")

    # --- Signal 2: style outlier against the row's own consensus ----------
    # Not colour alone (mission §5): a run is flagged only when it disagrees
    # with the dominant style of the row it landed in, on size or colour, and
    # that row has enough runs for "dominant" to mean something.
    by_row: dict[int, list[dict[str, Any]]] = {}
    for span in spans:
        pos = span.get("_cell")
        if pos is not None:
            by_row.setdefault(pos[0], []).append(span)

    outliers = 0
    for row, row_spans in by_row.items():
        if len(row_spans) < 3:
            continue  # too few runs to establish a consensus
        sizes = [s.get("size", 0.0) for s in row_spans]
        colors = [s.get("color", 0) for s in row_spans]
        dom_size = max(set(sizes), key=sizes.count)
        dom_color = max(set(colors), key=colors.count)
        for s in row_spans:
            size_off = dom_size > 0 and abs(s.get("size", 0.0) - dom_size) / dom_size > SIZE_OUTLIER_RATIO
            color_off = s.get("color", 0) != dom_color
            if size_off and color_off:
                outliers += 1
                affected.add(s["_cell"])
    if outliers:
        signals.append(f"{outliers} text run(s) differ in size and colour from their row")

    # --- Signal 3: a cell holding runs of disjoint styles ------------------
    # The direct signature of contamination: one cell, two different origins.
    by_cell: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for span in spans:
        pos = span.get("_cell")
        if pos is not None:
            by_cell.setdefault(pos, []).append(span)
    mixed = 0
    for pos, cell_spans in by_cell.items():
        if len(cell_spans) < 2:
            continue
        styles = {(round(s.get("size", 0.0), 1), s.get("color", 0)) for s in cell_spans}
        if len(styles) > 1:
            mixed += 1
            affected.add(pos)
    if mixed:
        signals.append(f"{mixed} cell(s) contain runs of more than one style")

    if signals:
        report.trusted = False
        report.signals = signals
        report.affected_cells = sorted(affected)
        # Mixed-style cells mean text from two sources is already merged into
        # one value — a consumer reading that cell is reading a wrong string,
        # which is worse than knowing the geometry is doubtful.
        report.severity = SEVERITY_HIGH if mixed else SEVERITY_MEDIUM
    return report
