"""Canonical table representation.

Kept intentionally close to how table-structure models (Table Transformer,
Docling's TableFormer, PP-Structure) already think about tables: a bbox, a
grid of cells with row/col spans, and per-cell text/bbox. No business
semantics (e.g. "this column is a price") are attached here.
"""
from __future__ import annotations

from html import escape

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
        # Pipe tables cannot represent merged cells or literal delimiters /
        # line breaks in cell text. HTML is valid Markdown and preserves the
        # physical grid instead of silently creating extra rows/columns.
        if any(
            cell.row_span > 1 or cell.col_span > 1 or "|" in cell.text
            or "\n" in cell.text or "\r" in cell.text
            for cell in self.cells
        ):
            return self.to_html()
        grid = self.to_grid()
        if not grid:
            return ""
        lines = ["| " + " | ".join(row) + " |" for row in grid]
        header_sep = "| " + " | ".join(["---"] * self.n_cols) + " |"
        lines.insert(1, header_sep)
        return "\n".join(lines)

    def to_html(self) -> str:
        """Render observed cell content and spans without delimiter ambiguity.

        Unoccupied grid positions retain the existing empty-grid rendering.
        Overlapping cells cannot be serialized unambiguously and fail closed.
        """
        origins: dict[tuple[int, int], Cell] = {}
        covered: set[tuple[int, int]] = set()
        for cell in self.cells:
            positions = {
                (row, col)
                for row in range(cell.row, cell.row + cell.row_span)
                for col in range(cell.col, cell.col + cell.col_span)
            }
            if positions & covered:
                raise ValueError(f"overlapping cells in table {self.id!r}")
            covered.update(positions)
            origins[(cell.row, cell.col)] = cell
        rows = []
        for row in range(self.n_rows):
            cells = []
            for col in range(self.n_cols):
                cell = origins.get((row, col))
                if cell is None:
                    if (row, col) not in covered:
                        cells.append("<td></td>")
                    continue
                tag = "th" if cell.is_header else "td"
                spans = ""
                if cell.row_span > 1:
                    spans += f' rowspan="{cell.row_span}"'
                if cell.col_span > 1:
                    spans += f' colspan="{cell.col_span}"'
                cells.append(f"<{tag}{spans}>{escape(cell.text)}</{tag}>")
            rows.append("<tr>" + "".join(cells) + "</tr>")
        return "<table>\n" + "\n".join(rows) + "\n</table>"
