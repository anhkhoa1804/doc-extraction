from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

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

    model_config = ConfigDict(extra="forbid")

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

    @model_validator(mode="after")
    def validate_local_references(self) -> Page:
        element_ids = [element.id for element in self.elements]
        table_ids = [table.id for table in self.tables]
        if len(element_ids) != len(set(element_ids)):
            raise ValueError("page contains duplicate element identifiers")
        if len(table_ids) != len(set(table_ids)):
            raise ValueError("page contains duplicate table identifiers")
        if len(self.reading_order) != len(set(self.reading_order)):
            raise ValueError("page reading_order contains duplicate identifiers")
        element_id_set = set(element_ids)
        unknown_order_ids = [item for item in self.reading_order if item not in element_id_set]
        if unknown_order_ids:
            raise ValueError(f"page reading_order references unknown elements: {unknown_order_ids[:5]}")
        table_id_set = set(table_ids)
        for element in self.elements:
            if element.type.value == "table" and element.table_id is None:
                raise ValueError(f"table element {element.id!r} is missing its table reference")
            if element.table_id is not None and element.table_id not in table_id_set:
                raise ValueError(f"element {element.id!r} references an unknown table")
        return self

    def element_by_id(self, element_id: str) -> Element | None:
        return next((e for e in self.elements if e.id == element_id), None)

    def table_by_id(self, table_id: str) -> Table | None:
        return next((t for t in self.tables if t.id == table_id), None)

    def elements_in_reading_order(self, *, require_complete: bool = True) -> list[Element]:
        """Return elements using only the explicit reading-order relation.

        ``elements`` is a storage collection, not an ordering claim. A
        consumer that requires a complete sequence (for example a benchmark
        serializer) must fail closed when that relation is absent or
        incomplete rather than treating collection order as reading order.
        """
        element_ids = [element.id for element in self.elements]
        if len(element_ids) != len(set(element_ids)):
            raise ValueError("page contains duplicate element identifiers")
        if len(self.reading_order) != len(set(self.reading_order)):
            raise ValueError("page reading_order contains duplicate identifiers")
        by_id = {element.id: element for element in self.elements}
        unknown = [element_id for element_id in self.reading_order if element_id not in by_id]
        if unknown:
            raise ValueError(f"page reading_order references unknown elements: {unknown[:5]}")
        missing = set(element_ids) - set(self.reading_order)
        if require_complete and missing:
            raise ValueError("page reading_order does not include every element")
        return [by_id[element_id] for element_id in self.reading_order]
