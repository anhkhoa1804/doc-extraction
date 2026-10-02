"""Canonical table representation.

Kept intentionally close to how table-structure models (Table Transformer,
Docling's TableFormer, PP-Structure) already think about tables: a bbox, a
grid of cells with row/col spans, and per-cell text/bbox. No business
semantics (e.g. "this column is a price") are attached here.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from doc_extraction.schemas.element import BBox


class Cell(BaseModel):
    model_config = ConfigDict(extra="forbid")

    row: int = Field(ge=0)
    col: int = Field(ge=0)
    row_span: int = Field(default=1, ge=1)
    col_span: int = Field(default=1, ge=1)
    bbox: BBox | None = None
    text: str = ""
    is_header: bool = False
    confidence: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)


class Table(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    bbox: BBox | None = None
    # 1-based rendered page number, or None where the source format has no
    # pagination without rendering (see Element.page_number).
    page_number: int | None = None
    n_rows: int = Field(ge=1)
    n_cols: int = Field(ge=1)
    cells: list[Cell] = Field(default_factory=list)
    source_backend: str
    confidence: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_cells_within_dimensions(self) -> Table:
        for cell in self.cells:
            if cell.row + cell.row_span > self.n_rows:
                raise ValueError("cell row span exceeds declared table dimensions")
            if cell.col + cell.col_span > self.n_cols:
                raise ValueError("cell column span exceeds declared table dimensions")
        return self

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
