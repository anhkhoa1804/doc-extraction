"""Backend interfaces (spec §8) plus the small value types stages pass
between each other. Concrete implementations live in `backends/`; stages in
`stages/` orchestrate calls against whichever backend a config selects.

These Protocols are the whole point of the "modular, not a black box" design:
`doc_extraction compare` runs several `WholeDocumentBackend` implementations
over the same file, and the baseline pipeline's `stages/*.py` call
`LayoutBackend`/`OCRBackend`/`TableBackend` implementations independently, so
any one component can be swapped or studied in isolation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from doc_extraction.schemas.element import BBox, Element, ElementType
from doc_extraction.schemas.page import Page
from doc_extraction.schemas.table import Table
from doc_extraction.utils.logging import StageLogger

if TYPE_CHECKING:
    from doc_extraction.config import PipelineConfig
    from doc_extraction.schemas.document import Document


class BackendUnavailableError(RuntimeError):
    """Raised when a selected backend isn't installed/importable in this
    environment. Callers must handle this explicitly (log + skip, fall back
    to another backend, or fail the run) — it is never swallowed silently."""


@dataclass
class PageInput:
    """What a stage backend needs to operate on one page.

    A backend uses whichever inputs it needs and reports a warning when a
    required one is missing, rather than assuming: image-based backends need
    `image_path`, native PDF backends need `source_pdf_path`.
    """

    page_index: int  # 0-based
    width: float
    height: float
    image_path: Path | None = None  # rendered raster, when the stage needs pixels
    text: str | None = None  # extracted text layer, when available (digital PDFs)
    dpi: int | None = None
    source_pdf_path: Path | None = None  # original PDF, for native (non-raster) backends


@dataclass
class Region:
    bbox: BBox
    label: str
    confidence: float | None = None
    source_id: str | None = None


@dataclass
class LayoutResult:
    regions: list[Region] = field(default_factory=list)
    backend: str = ""
    warnings: list[str] = field(default_factory=list)


@dataclass
class OCRToken:
    text: str
    bbox: BBox
    confidence: float | None = None


@dataclass
class OCRResult:
    tokens: list[OCRToken] = field(default_factory=list)
    backend: str = ""
    warnings: list[str] = field(default_factory=list)


@dataclass
class TableResult:
    tables: list[Table] = field(default_factory=list)
    backend: str = ""
    warnings: list[str] = field(default_factory=list)


@runtime_checkable
class LayoutBackend(Protocol):
    name: str

    def is_available(self) -> bool: ...

    def analyze(self, page: PageInput) -> LayoutResult: ...


@runtime_checkable
class OCRBackend(Protocol):
    name: str

    def is_available(self) -> bool: ...

    def recognize(self, page: PageInput) -> OCRResult: ...


@runtime_checkable
class TableBackend(Protocol):
    name: str

    def is_available(self) -> bool: ...

    def extract(self, page: PageInput, regions: list[Region]) -> TableResult: ...


@runtime_checkable
class WholeDocumentBackend(Protocol):
    """Full end-to-end conversion used by `doc_extraction compare` — one
    library's own pipeline, adapted into the canonical IR."""

    name: str

    def is_available(self) -> bool: ...

    def convert(self, path: Path, config: "PipelineConfig") -> "Document": ...


# ---------------------------------------------------------------------------
# Shared scanned-page orchestration (Steps E-H for the "scanned" route).
#
# Both pipelines/pdf.py (scanned PDFs) and pipelines/image.py (raw images)
# need the identical layout -> OCR -> table -> element-merge sequence per
# rendered page; it lives here rather than being duplicated in each pipeline
# module.
# ---------------------------------------------------------------------------

_LABEL_TO_ELEMENT_TYPE: dict[str, str] = {
    "title": "heading",
    "section-header": "heading",
    "section_header": "heading",
    "text": "text",
    "paragraph": "paragraph",
    "list-item": "list_item",
    "list_item": "list_item",
    "table": "table",
    "picture": "image",
    "figure": "image",
    "formula": "formula",
    "checkbox-selected": "checkbox",
    "checkbox-unselected": "checkbox",
    "caption": "text",
    "footnote": "text",
    "page-header": "other",
    "page-footer": "other",
}


def _center_in(inner: BBox, outer: BBox) -> bool:
    cx = (inner.x0 + inner.x1) / 2
    cy = (inner.y0 + inner.y1) / 2
    return outer.x0 <= cx <= outer.x1 and outer.y0 <= cy <= outer.y1


def _gather_region_text(region: Region, ocr_result: OCRResult) -> str | None:
    if not ocr_result.tokens:
        return None
    contained = [t for t in ocr_result.tokens if _center_in(t.bbox, region.bbox)]
    if not contained:
        return None
    contained.sort(key=lambda t: (t.bbox.y0, t.bbox.x0))
    text = " ".join(t.text for t in contained if t.text).strip()
    return text or None


def _fill_table_cell_text(table_result: "TableResult", ocr_result: OCRResult) -> None:
    """Table Transformer produces grid geometry only (no text). Fill each
    cell's text in-place from whichever OCR tokens center inside its bbox —
    the same containment rule region text uses elsewhere, applied per cell
    instead of per region."""
    if not ocr_result.tokens:
        return
    for table in table_result.tables:
        for cell in table.cells:
            if cell.bbox is None:
                continue
            contained = [t for t in ocr_result.tokens if _center_in(t.bbox, cell.bbox)]
            if not contained:
                continue
            contained.sort(key=lambda t: (t.bbox.y0, t.bbox.x0))
            cell.text = " ".join(t.text for t in contained if t.text).strip()


def merge_regions_into_page(
    page_index: int,
    width: float,
    height: float,
    dpi: int | None,
    layout_result: LayoutResult,
    ocr_result: OCRResult,
    table_result: "TableResult | None",
    rendered_image_path: Path | None,
) -> "Page":
    """Combine one page's layout regions + OCR tokens + detected tables into
    a canonical Page. Region text is assembled from whichever OCR tokens
    fall inside the region's bbox (center-point containment — a simple,
    deliberately inspectable rule); table regions are matched to detected
    Table objects by bbox IoU."""
    tables = list(table_result.tables) if table_result else []
    elements: list[Element] = []

    for i, region in enumerate(layout_result.regions):
        etype = ElementType(_LABEL_TO_ELEMENT_TYPE.get(region.label.lower(), "other"))
        element_id = f"p{page_index}-e{i}"

        if etype == ElementType.TABLE and tables:
            best_table = max(
                tables, key=lambda t: (t.bbox.iou(region.bbox) if t.bbox else 0.0)
            )
            matched = (
                best_table.id
                if best_table.bbox is not None and best_table.bbox.iou(region.bbox) > 0.1
                else None
            )
            elements.append(
                Element(
                    id=element_id,
                    type=etype,
                    bbox=region.bbox,
                    page_number=page_index + 1,
                    confidence=region.confidence,
                    source_backend=layout_result.backend,
                    table_id=matched,
                    order_index=i,
                )
            )
            continue

        text = _gather_region_text(region, ocr_result)
        elements.append(
            Element(
                id=element_id,
                type=etype,
                text=text,
                bbox=region.bbox,
                page_number=page_index + 1,
                confidence=region.confidence,
                source_backend=layout_result.backend,
                order_index=i,
            )
        )

    return Page(
        index=page_index,
        width=width,
        height=height,
        dpi=dpi,
        coordinate_unit="px",
        elements=elements,
        tables=tables,
        rendered_image_path=str(rendered_image_path) if rendered_image_path else None,
    )


def run_scanned_page_pipeline(
    image_path: Path,
    page_index: int,
    dpi: int,
    layout_backend: LayoutBackend,
    ocr_backend: OCRBackend,
    table_backend: TableBackend,
    output_dir: Path,
    logger: "StageLogger | None" = None,
) -> "Page":
    """Steps E-H for one already-rendered page: layout -> OCR -> table ->
    merge into a canonical Page. Raises BackendUnavailableError (uncaught)
    if the configured layout/OCR backend isn't installed; the table backend
    is optional (skipped, with a warning, if unavailable)."""
    # Imported lazily to avoid a hard import-time dependency of pipelines.base
    # on the stages package (stages already imports pipelines.base for the
    # Protocol types, so a module-level import here would be circular).
    from PIL import Image

    from doc_extraction.stages import layout as layout_stage
    from doc_extraction.stages import ocr as ocr_stage
    from doc_extraction.stages import table as table_stage

    with Image.open(image_path) as im:
        width_px, height_px = im.size

    page_input = PageInput(
        page_index=page_index, width=width_px, height=height_px, image_path=image_path, dpi=dpi
    )

    layout_result = layout_stage.run_layout(page_input, layout_backend, output_dir / "layout", logger)
    ocr_result = ocr_stage.run_ocr(page_input, ocr_backend, output_dir / "ocr", logger)

    table_result: TableResult | None = None
    if table_backend.is_available():
        table_regions = [r for r in layout_result.regions if r.label.lower() == "table"]
        table_result = table_stage.run_table(
            page_input, table_regions, table_backend, output_dir / "tables", logger
        )
        _fill_table_cell_text(table_result, ocr_result)
    elif logger is not None:
        logger.log_event(
            stage="table",
            backend=table_backend.name,
            status="failure",
            warnings=[f"table backend '{table_backend.name}' unavailable — tables on this page are unstructured"],
            page=page_index,
            error="backend not installed",
        )

    return merge_regions_into_page(
        page_index, width_px, height_px, dpi, layout_result, ocr_result, table_result, image_path
    )
