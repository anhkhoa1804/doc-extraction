from __future__ import annotations

from pydantic import BaseModel, Field

from doc_extraction.schemas.element import Element
from doc_extraction.schemas.table import Table


class Page(BaseModel):
    """One page (PDF/image), slide (PPTX), sheet (XLSX), or — for formats
    without rendered pagination — one logical document body (DOCX).

    `index` is always a 0-based position within `Document.pages` and is
    always present. It is *not* necessarily a rendered page number: see
    `is_rendered_page`. Element/Table `page_number` fields carry the
    1-based rendered page number where one genuinely exists, and None
    otherwise.
    """

    index: int  # 0-based position in Document.pages; always defined
    width: float
    height: float
    dpi: int | None = None
    # Units for every bbox on this page. "pt" = PDF points, "px" = pixels in
    # the rendered image at `dpi`, "emu" = PowerPoint English Metric Units.
    coordinate_unit: str = "pt"
    # Binding for every bbox on this page. Backends normalize to this; see
    # schemas/element.py BBox.
    coordinate_origin: str = "top-left"
    # False when this Page is a logical container rather than a rendered
    # page — e.g. a DOCX body or an XLSX sheet, where width/height are not
    # physical dimensions and no true page number exists.
    is_rendered_page: bool = True
    # How this page was produced, for provenance when several routes or
    # backends contribute to one document (e.g. per-page OCR fallback
    # inside an otherwise-native digital PDF).
    source_route: str | None = None
    source_backend: str | None = None

    elements: list[Element] = Field(default_factory=list)
    tables: list[Table] = Field(default_factory=list)
    reading_order: list[str] = Field(default_factory=list)  # Element.id, in reading order
    rendered_image_path: str | None = None  # relative to the document's output dir
    notes: list[str] = Field(default_factory=list)  # per-page warnings/provenance notes

    def element_by_id(self, element_id: str) -> Element | None:
        return next((e for e in self.elements if e.id == element_id), None)

    def table_by_id(self, table_id: str) -> Table | None:
        return next((t for t in self.tables if t.id == table_id), None)
