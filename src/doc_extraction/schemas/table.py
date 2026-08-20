"""Canonical table representation.

Kept intentionally close to how table-structure models (Table Transformer,
Docling's TableFormer, PP-Structure) already think about tables: a bbox, a
grid of cells with row/col spans, and per-cell text/bbox. No business
semantics (e.g. "this column is a price") are attached here.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from doc_extraction.schemas.element import BBox


class Cell(BaseModel):
    row: int
    col: int
    row_span: int = 1
    col_span: int = 1
    bbox: BBox | None = None
    text: str = ""
    is_header: bool = False
    confidence: float | None = None


class Table(BaseModel):
    id: str
    bbox: BBox | None = None
    # 1-based rendered page number, or None where the source format has no
    # pagination without rendering (see Element.page_number).
    page_number: int | None = None
    n_rows: int
    n_cols: int
    cells: list[Cell] = Field(default_factory=list)
    source_backend: str
    confidence: float | None = None

    def to_grid(self) -> list[list[str]]:
        """Materialize cells into a dense n_rows x n_cols text grid.

        Spanned cells repeat their text into every covered position, which
        is the simplest representation for a quick Markdown/HTML render.
        """
        grid = [["" for _ in range(self.n_cols)] for _ in range(self.n_rows)]
        for cell in self.cells:
            for r in range(cell.row, min(cell.row + cell.row_span, self.n_rows)):
                for c in range(cell.col, min(cell.col + cell.col_span, self.n_cols)):
                    grid[r][c] = cell.text
        return grid

    def to_markdown(self) -> str:
        grid = self.to_grid()
        if not grid:
            return ""
        lines = ["| " + " | ".join(row) + " |" for row in grid]
        header_sep = "| " + " | ".join(["---"] * self.n_cols) + " |"
        lines.insert(1, header_sep)
        return "\n".join(lines)
