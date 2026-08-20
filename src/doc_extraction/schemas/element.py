"""Canonical page element representation.

This is deliberately a *technical* document representation (what a layout/
OCR/table model would emit), not a business ontology. Downstream systems are
expected to interpret `type`/`text`/`table` themselves.
"""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

# Note: Element intentionally does not embed a `Table` object directly.
# For type == TABLE, `table_id` points into the owning Page's `tables` list
# (see schemas/table.py, schemas/page.py). This keeps Element flat and
# avoids a circular import between element.py and table.py.


class ElementType(str, Enum):
    TEXT = "text"
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    LIST_ITEM = "list_item"
    TABLE = "table"
    IMAGE = "image"
    FORMULA = "formula"
    CHECKBOX = "checkbox"
    SIGNATURE = "signature"
    OTHER = "other"


class BBox(BaseModel):
    """Axis-aligned bounding box in the owning `Page`'s coordinate space.

    Coordinate convention (uniform across every backend in this repo — see
    docs/output-format.md):

    * **Origin** is the **top-left** corner of the page.
    * **+x** runs right, **+y** runs **down**.
    * ``x0 <= x1`` and ``y0 <= y1`` always hold: ``(x0, y0)`` is the
      top-left corner of the box and ``(x1, y1)`` the bottom-right.
    * **Units** are given by the owning `Page.coordinate_unit`
      (``pt`` | ``px`` | ``emu``); for ``px`` the scale is `Page.dpi`.

    Backends that natively use a bottom-left origin (some PDF/Docling
    coordinates) must convert on the way in, so consumers never have to ask
    which convention a given element used.
    """

    x0: float
    y0: float
    x1: float
    y1: float

    def as_tuple(self) -> tuple[float, float, float, float]:
        return (self.x0, self.y0, self.x1, self.y1)

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    def area(self) -> float:
        return max(0.0, self.width) * max(0.0, self.height)

    def iou(self, other: "BBox") -> float:
        ix0, iy0 = max(self.x0, other.x0), max(self.y0, other.y0)
        ix1, iy1 = min(self.x1, other.x1), min(self.y1, other.y1)
        inter = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
        union = self.area() + other.area() - inter
        return inter / union if union > 0 else 0.0


class Element(BaseModel):
    id: str
    type: ElementType
    text: str | None = None
    bbox: BBox | None = None
    # 1-based *rendered* page number, or None when the source format has no
    # meaningful pagination without rendering it (DOCX — see
    # pipelines/office.py). None means "unknown", never "page 1": callers
    # must not fabricate pagination that the format does not define.
    page_number: int | None = None
    confidence: float | None = None
    source_backend: str
    source_id: str | None = None
    parent_id: str | None = None
    order_index: int | None = None
    level: int | None = None  # heading level / list nesting depth, where known
    table_id: str | None = None  # set for type == TABLE; see Page.tables
    extra: dict[str, Any] = Field(default_factory=dict)
