"""Native table extraction for born-digital PDFs (PyMuPDF `find_tables`).

Why this backend exists
-----------------------
Table Transformer (backends/table_backend.py) works on *pixels*: it needs a
rendered page and, because it only produces grid geometry, an OCR pass to
fill cell text. For a born-digital PDF that is an absurd amount of work to
recover structure the file already describes — the ruling lines are vector
graphics and the cell text is right there in the text layer.

PyMuPDF's table finder reads exactly that: vector ruling lines plus text
positions. No rendering, no OCR, no model download, no GPU. It is the
lightest reliable path for the digital-PDF route, which is why the digital
route uses it and the scanned/image route uses Table Transformer.

Merged cells
------------
PyMuPDF marks cells merged away by a horizontal span as `None` in the row's
cell list (and `None` in the corresponding `extract()` position). We walk
each row and turn a run of `None`s following a real cell into that cell's
`col_span`.

Limitations (documented, not silently absorbed)
-----------------------------------------------
* **Row spans are not recovered.** PyMuPDF's finder treats rows
  independently and does not mark vertical merges, so every cell this
  backend emits has `row_span == 1`. A vertically merged cell appears as one
  populated cell plus empty cells beneath it. Table Transformer on the
  rendered page is the fallback when true row spans matter.
* Detection is driven by ruling lines and whitespace alignment. Borderless
  tables laid out purely by tab stops may be missed entirely, and dense
  multi-column text is occasionally detected as a spurious table.
* Header detection is PyMuPDF's own (`table.header`); when it reports an
  "external" header the header row is outside the table bbox and we mark no
  in-grid header row.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from doc_extraction.ingest.table_quality import assess_table
from doc_extraction.pipelines.base import PageInput, Region, TableResult
from doc_extraction.schemas.element import BBox
from doc_extraction.schemas.table import Cell, Table


def is_available() -> bool:
    return importlib.util.find_spec("pymupdf") is not None


def backend_version() -> str:
    try:
        import pymupdf

        return str(getattr(pymupdf, "__version__", "unknown"))
    except Exception:  # pragma: no cover - pymupdf is a core dependency
        return "unavailable"


def _touches(run: dict, table: Table) -> bool:
    """Whether a run overlaps the table at all.

    Runs that landed in no cell are still evidence: a run straddling two cells
    is the signal that the grid and the text disagree. Runs nowhere near the
    table are not, and including them would make every page look suspicious.
    """
    if table.bbox is None:
        return False
    b = run["bbox"]
    return not (b[2] < table.bbox.x0 or b[0] > table.bbox.x1
                or b[3] < table.bbox.y0 or b[1] > table.bbox.y1)


def _cell_bbox(raw) -> BBox | None:
    if raw is None:
        return None
    x0, y0, x1, y1 = (float(v) for v in raw)
    return BBox(x0=x0, y0=y0, x1=x1, y1=y1)


# A run lying at least this far inside its best cell sits cleanly within the
# grid. Below it the run straddles a boundary -- it is still assigned (losing
# text would be a worse bug than the one being fixed) but marked `_crossed`
# so the quality gate can report the disagreement.
MIN_CONTAINMENT = 0.6


# A character whose box starts more than this far before the previous
# character's box ends did not continue that character — the two were drawn
# by separate operations and PyMuPDF merged them into one span.
_ADVANCE_OVERLAP_TOL = 0.5
# A gap wider than this multiple of the font size is likewise a break. A
# normal inter-word space is ~0.35 em, so 1.2 em is well clear of any real one.
_ADVANCE_GAP_EM = 1.2


def _split_span_at_discontinuities(span: dict) -> list[dict]:
    """Cut one span into maximal monotonically-advancing character sequences.

    A PyMuPDF span is *not* always one drawing operation. Two adjacent
    `insert_text` calls that share a baseline are merged into a single span,
    and the merged span then straddles a cell boundary that neither original
    text crossed. Measured on `ord_invoice_vi`, the header comes back as one
    span `'Số lượngThành tiền'` spanning x=[300, 396] across a cell boundary
    at x=340 — so span-level ownership had to give the whole thing to one
    cell, emptying the other.

    The merge is detectable because a genuine run advances monotonically:

        'g'  x=[337.85, 344.29]
        'T'  x=[342.00, 348.14]     <- starts 2.29 pt BEFORE 'g' ends

    Overlapping advance boxes mean two operations, so the span is cut there.
    This recovers the true drawing units without ever mixing two of them,
    which is what keeps the interleaving bug fixed: characters from an
    overlay and characters from a cell still land in different runs.
    """
    chars = span.get("chars") or []
    if not chars:
        return []
    size = span.get("size") or 9.0
    groups: list[list[dict]] = [[chars[0]]]
    for prev, cur in zip(chars, chars[1:]):
        overlapping = cur["bbox"][0] < prev["bbox"][2] - _ADVANCE_OVERLAP_TOL
        far_apart = cur["bbox"][0] - prev["bbox"][2] > _ADVANCE_GAP_EM * size
        new_baseline = abs(cur["origin"][1] - prev["origin"][1]) > 0.5
        if overlapping or far_apart or new_baseline:
            groups.append([cur])
        else:
            groups[-1].append(cur)

    runs: list[dict] = []
    for group in groups:
        text = "".join(c["c"] for c in group)
        if not text.strip():
            continue
        runs.append({
            "text": text,
            "bbox": (min(c["bbox"][0] for c in group), min(c["bbox"][1] for c in group),
                     max(c["bbox"][2] for c in group), max(c["bbox"][3] for c in group)),
            "size": span.get("size"),
            "color": span.get("color"),
            "font": span.get("font"),
        })
    return runs


def page_text_runs(page) -> list[dict]:
    """Flatten a page into text runs — the drawing operations that produced it.

    Ownership needs the unit that is guaranteed to come from a single drawing
    operation. Measured on the production corpus (see
    `research/experiments/_table_integrity/probe_granularity.py`), over eight
    cells covering overlay, boundary-crossing and merged-header cases:

        span    5/8    safe against interleaving, but a span can be two
                       merged draw calls, so it straddles cells legitimately
        char    2/8    reproduces the original bug exactly — an overlay's
                       glyphs interleave with a cell's ('BộNHH', 'ỆTGói')
        subrun  7/8    span cut at advance discontinuities

    So a run here is a span split at its discontinuities. The one remaining
    miss is genuine overlay contamination sitting inside a cell, which no
    geometry can attribute away and which the quality gate reports instead.
    """
    runs: list[dict] = []
    for block in page.get_text("rawdict").get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                runs.extend(_split_span_at_discontinuities(span))
    return runs


def _union(boxes) -> tuple | None:
    boxes = list(boxes)
    if not boxes:
        return None
    return (min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes))


def _centre_inside(span_bbox, box) -> bool:
    cx = (span_bbox[0] + span_bbox[2]) / 2.0
    cy = (span_bbox[1] + span_bbox[3]) / 2.0
    return box[0] <= cx <= box[2] and box[1] <= cy <= box[3]


def _containment(span_bbox, cell_bbox) -> float:
    ix = max(0.0, min(span_bbox[2], cell_bbox[2]) - max(span_bbox[0], cell_bbox[0]))
    iy = max(0.0, min(span_bbox[3], cell_bbox[3]) - max(span_bbox[1], cell_bbox[1]))
    area = max(0.0, span_bbox[2] - span_bbox[0]) * max(0.0, span_bbox[3] - span_bbox[1])
    return (ix * iy) / area if area > 0 else 0.0


def assign_runs_to_cells(cell_boxes: dict, runs: list[dict]) -> dict:
    """Give every text run to at most one cell, whole.

    This is the fix. `find_tables().extract()` re-gathers text by raw
    coordinate, so a run lying across two cells is cut at the boundary
    ('Số lượng' + 'Thành tiền' became 'Số lượn' + 'gThành tiền') and a run
    drawn *over* the table is merged into whatever cell it covers, character
    by character ('Bộ' + 'NHH' became 'NBHộH').

    Assigning whole runs makes both impossible: a cell's text is a
    concatenation of complete runs or nothing. It does not decide whether a
    run is foreign — geometry cannot, as an overlay sits at a legitimate
    position — so contamination that survives is left for the quality gate to
    report rather than silently accepted.

    Each run is annotated in place with `_cell`, the position it was given to
    (or None), so the gate can judge without recomputing.
    """
    assigned: dict = {}
    table_box = _union(cell_boxes.values())
    for run in runs:
        run["_cell"] = None
        run["_crossed"] = False
        # Only runs centred within the grid are candidates. A seal drawn
        # elsewhere on the page may clip a corner of the table bbox; pulling
        # it in would replace one contamination bug with another.
        if table_box is None or not _centre_inside(run["bbox"], table_box):
            continue
        best_pos, best_frac = None, 0.0
        for pos, box in cell_boxes.items():
            frac = _containment(run["bbox"], box)
            if frac > best_frac:
                best_pos, best_frac = pos, frac
        if best_pos is None or best_frac <= 0.0:
            continue
        # Assign to the best cell even when the run straddles a boundary.
        # Dropping it would make legitimate table text vanish -- the header
        # 'Số lượngThành tiền' is exactly such a run -- and silent deletion is
        # no better than silent corruption. The run is flagged instead.
        run["_cell"] = best_pos
        run["_crossed"] = best_frac < MIN_CONTAINMENT
        assigned.setdefault(best_pos, []).append(run)
    for pos, runs_here in assigned.items():
        # Reading order within a cell: top to bottom, then left to right.
        runs_here.sort(key=lambda r: (round(r["bbox"][1], 1), r["bbox"][0]))
    return assigned


def convert_pymupdf_table(table, page_index: int, table_id: str,
                          runs: list[dict] | None = None) -> Table:
    """Convert one `pymupdf.table.Table` into the canonical `Table`.

    When `runs` is supplied, cell text comes from run-ownership assignment.
    Without it the function falls back to PyMuPDF's own `extract()`, which is
    kept only so callers that have no page handy still work; that path has the
    interleaving defect described in `assign_runs_to_cells`.
    """
    extracted = table.extract()
    n_rows = table.row_count
    n_cols = table.col_count

    header_row_texts: set[str] = set()
    header_is_internal = False
    header = getattr(table, "header", None)
    if header is not None and not getattr(header, "external", True):
        header_is_internal = True
        header_row_texts = {str(n) for n in (getattr(header, "names", None) or []) if n}

    owned: dict = {}
    if runs is not None:
        cell_boxes = {}
        for r_i, r in enumerate(table.rows):
            for c_i, raw_cell in enumerate(r.cells):
                if raw_cell is not None:
                    cell_boxes[(r_i, c_i)] = tuple(float(v) for v in raw_cell)
        owned = assign_runs_to_cells(cell_boxes, runs)

    cells: list[Cell] = []
    for row_index, row in enumerate(table.rows):
        row_cells = list(row.cells)
        col_index = 0
        while col_index < len(row_cells):
            raw = row_cells[col_index]
            if raw is None:
                # A leading None (no preceding real cell in this row) carries
                # no geometry we can attribute — skip rather than invent one.
                col_index += 1
                continue

            col_span = 1
            while col_index + col_span < len(row_cells) and row_cells[col_index + col_span] is None:
                col_span += 1

            if runs is not None:
                text = " ".join(r["text"].strip()
                                for r in owned.get((row_index, col_index), [])).strip()
            else:
                text = ""
                if row_index < len(extracted) and col_index < len(extracted[row_index]):
                    text = (extracted[row_index][col_index] or "").strip()

            is_header = header_is_internal and row_index == 0 and (not header_row_texts or text in header_row_texts)

            cells.append(
                Cell(
                    row=row_index,
                    col=col_index,
                    row_span=1,  # see module docstring: row spans are not recoverable here
                    col_span=col_span,
                    bbox=_cell_bbox(raw),
                    text=text,
                    is_header=is_header,
                )
            )
            col_index += col_span

    return Table(
        id=table_id,
        bbox=_cell_bbox(table.bbox),
        page_number=page_index + 1,
        n_rows=n_rows,
        n_cols=n_cols,
        cells=cells,
        source_backend=PyMuPDFTableBackend.name,
        confidence=None,
    )


class PyMuPDFTableBackend:
    """TableBackend for born-digital PDF pages.

    Unlike the image-based table backends, this one reads the source PDF
    directly, so `PageInput.source_pdf_path` must be set (the digital-PDF
    pipeline does this). `regions` is accepted for interface compatibility
    and used only to filter detected tables to the given areas when regions
    are supplied.
    """

    name = "pymupdf_tables"

    def is_available(self) -> bool:
        return is_available()

    def version(self) -> str:
        return backend_version()

    def extract(self, page: PageInput, regions: list[Region]) -> TableResult:
        if page.source_pdf_path is None:
            return TableResult(
                tables=[],
                backend=self.name,
                warnings=["no source PDF path on this page — native table extraction needs the original PDF"],
            )

        import pymupdf

        warnings: list[str] = []
        tables: list[Table] = []
        spans_by_table: dict[str, list[dict]] = {}
        doc = pymupdf.open(Path(page.source_pdf_path))
        try:
            if page.page_index >= doc.page_count:
                return TableResult(
                    tables=[], backend=self.name,
                    warnings=[f"page index {page.page_index} out of range for {doc.page_count}-page PDF"],
                )
            pdf_page = doc[page.page_index]
            runs = page_text_runs(pdf_page)
            found = pdf_page.find_tables()
            for i, table in enumerate(found.tables):
                try:
                    # Each table gets its own copy of the runs: `_cell` is
                    # annotated in place, and two tables on one page must not
                    # overwrite each other's attribution.
                    table_runs = [dict(r) for r in runs]
                    converted = convert_pymupdf_table(
                        table, page.page_index, f"p{page.page_index}-t{i}", runs=table_runs)
                except Exception as exc:  # noqa: BLE001 - reported, not swallowed
                    warnings.append(f"table {i} could not be converted: {type(exc).__name__}: {exc}")
                    continue
                if converted.n_rows == 0 or converted.n_cols == 0:
                    warnings.append(f"table {i} has an empty {converted.n_rows}x{converted.n_cols} grid; skipped")
                    continue
                if regions and converted.bbox is not None:
                    if not any(converted.bbox.iou(r.bbox) > 0.05 for r in regions):
                        continue

                # Judge the cells against the runs that produced them. A
                # suspicious table is still returned -- suppressing it would
                # lose data -- but it is returned *labelled*, both on the
                # table's confidence and as a warning the caller records.
                considered = [r for r in table_runs if r.get("_cell") is not None
                              or _touches(r, converted)]
                report = assess_table(converted, considered)
                spans_by_table[converted.id] = considered
                if not report.trusted:
                    warnings.append(report.as_warning(converted.id))
                    converted.confidence = 0.5 if report.severity == "medium" else 0.25
                tables.append(converted)
        finally:
            doc.close()

        return TableResult(tables=tables, backend=self.name, warnings=warnings,
                           spans_by_table=spans_by_table)
