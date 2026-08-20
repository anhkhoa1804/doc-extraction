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


def _cell_bbox(raw) -> BBox | None:
    if raw is None:
        return None
    x0, y0, x1, y1 = (float(v) for v in raw)
    return BBox(x0=x0, y0=y0, x1=x1, y1=y1)


def convert_pymupdf_table(table, page_index: int, table_id: str) -> Table:
    """Convert one `pymupdf.table.Table` into the canonical `Table`."""
    extracted = table.extract()
    n_rows = table.row_count
    n_cols = table.col_count

    header_row_texts: set[str] = set()
    header_is_internal = False
    header = getattr(table, "header", None)
    if header is not None and not getattr(header, "external", True):
        header_is_internal = True
        header_row_texts = {str(n) for n in (getattr(header, "names", None) or []) if n}

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
        doc = pymupdf.open(Path(page.source_pdf_path))
        try:
            if page.page_index >= doc.page_count:
                return TableResult(
                    tables=[], backend=self.name,
                    warnings=[f"page index {page.page_index} out of range for {doc.page_count}-page PDF"],
                )
            found = doc[page.page_index].find_tables()
            for i, table in enumerate(found.tables):
                try:
                    converted = convert_pymupdf_table(table, page.page_index, f"p{page.page_index}-t{i}")
                except Exception as exc:  # noqa: BLE001 - reported, not swallowed
                    warnings.append(f"table {i} could not be converted: {type(exc).__name__}: {exc}")
                    continue
                if converted.n_rows == 0 or converted.n_cols == 0:
                    warnings.append(f"table {i} has an empty {converted.n_rows}x{converted.n_cols} grid; skipped")
                    continue
                if regions and converted.bbox is not None:
                    if not any(converted.bbox.iou(r.bbox) > 0.05 for r in regions):
                        continue
                tables.append(converted)
        finally:
            doc.close()

        return TableResult(tables=tables, backend=self.name, warnings=warnings)
