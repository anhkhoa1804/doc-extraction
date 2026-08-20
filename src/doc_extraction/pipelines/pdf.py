"""PDF pipeline.

Two routes, chosen by ingest/dispatcher.py:

**digital_pdf** — the text layer is present *and* passes text-quality
checks. Structure comes from the PDF itself:

    native text blocks (PyMuPDF)  ->  elements
    native table finder (PyMuPDF) ->  tables      [no render, no OCR, no model]
    per-page text-quality check   ->  fall back to the visual path for
                                      individual bad pages only

**scanned_pdf** — no usable text layer (either too little text, or text that
decodes to garbage). Every page is rendered and goes through the shared
layout -> OCR -> table -> merge chain in pipelines/base.py.

The per-page fallback is the point of the design: text-quality assessment is
cheap enough to run on every page, so expensive visual re-extraction is
spent only on the pages that actually need it, instead of choosing one route
for a whole document.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

import pymupdf

from doc_extraction.config import PipelineConfig
from doc_extraction.ingest.text_quality import TextQualityThresholds, assess_text
from doc_extraction.pipelines.base import (
    LayoutBackend,
    OCRBackend,
    PageInput,
    Region,
    TableBackend,
    run_scanned_page_pipeline,
)
from doc_extraction.schemas.element import BBox, Element, ElementType
from doc_extraction.schemas.page import Page
from doc_extraction.stages.render import render_pdf_pages, render_single_pdf_page
from doc_extraction.utils.logging import StageLogger, noop_stage

BACKEND_NAME_NATIVE = "pymupdf-native"


def _estimate_body_font_size(doc: "pymupdf.Document") -> float:
    sizes: Counter[int] = Counter()
    for page in doc:
        for block in page.get_text("dict")["blocks"]:
            if block.get("type") != 0:
                continue
            for line in block["lines"]:
                for span in line["spans"]:
                    sizes[round(span["size"])] += len(span["text"])
    return float(sizes.most_common(1)[0][0]) if sizes else 10.0


def _extract_text_elements(pdf_page: "pymupdf.Page", page_index: int, body_size: float) -> list[Element]:
    elements: list[Element] = []
    order_index = 0
    for block in pdf_page.get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue  # non-text (image) block, handled separately below
        lines: list[str] = []
        max_size = 0.0
        for line in block["lines"]:
            line_text = "".join(span["text"] for span in line["spans"]).strip()
            if line_text:
                lines.append(line_text)
            for span in line["spans"]:
                max_size = max(max_size, span["size"])
        text = "\n".join(lines).strip()
        if not text:
            continue
        bbox = BBox(x0=block["bbox"][0], y0=block["bbox"][1], x1=block["bbox"][2], y1=block["bbox"][3])
        is_heading = max_size >= body_size * 1.15 and len(text) < 120
        elements.append(
            Element(
                id=f"p{page_index}-e{order_index}",
                type=ElementType.HEADING if is_heading else ElementType.PARAGRAPH,
                text=text,
                bbox=bbox,
                page_number=page_index + 1,
                confidence=1.0,
                source_backend=BACKEND_NAME_NATIVE,
                order_index=order_index,
                level=1 if is_heading else None,
            )
        )
        order_index += 1

    for image_index, img in enumerate(pdf_page.get_images(full=True)):
        bbox = None
        try:
            rect = pdf_page.get_image_bbox(img)
            bbox = BBox(x0=rect.x0, y0=rect.y0, x1=rect.x1, y1=rect.y1)
        except Exception:
            # get_image_bbox fails for images placed by an uncommon
            # transform; the element is still worth recording without a box.
            pass
        elements.append(
            Element(
                id=f"p{page_index}-eimg{image_index}",
                type=ElementType.IMAGE,
                bbox=bbox,
                page_number=page_index + 1,
                confidence=1.0,
                source_backend=BACKEND_NAME_NATIVE,
                source_id=f"xref-{img[0]}",
                order_index=order_index,
            )
        )
        order_index += 1

    return elements


def _drop_elements_inside_tables(elements: list[Element], table_boxes: list[BBox]) -> list[Element]:
    """Remove text blocks that fall inside a detected table's bbox.

    Without this, a table's contents would appear twice in the IR: once as
    structured `Table` cells and again as loose paragraph elements. The
    table element itself is added separately by the caller.
    """
    if not table_boxes:
        return elements
    kept: list[Element] = []
    for element in elements:
        if element.bbox is not None and any(
            element.bbox.iou(tb) > 0.0 and _mostly_inside(element.bbox, tb) for tb in table_boxes
        ):
            continue
        kept.append(element)
    return kept


def _mostly_inside(inner: BBox, outer: BBox, threshold: float = 0.7) -> bool:
    ix0, iy0 = max(inner.x0, outer.x0), max(inner.y0, outer.y0)
    ix1, iy1 = min(inner.x1, outer.x1), min(inner.y1, outer.y1)
    overlap = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
    inner_area = inner.area()
    return inner_area > 0 and (overlap / inner_area) >= threshold


def parse_digital_pdf(
    path: Path,
    config: PipelineConfig,
    output_dir: Path,
    layout_backend: LayoutBackend | None = None,
    ocr_backend: OCRBackend | None = None,
    image_table_backend: TableBackend | None = None,
    logger: StageLogger | None = None,
) -> list[Page]:
    """Native extraction for a born-digital PDF, with native table structure
    and per-page fallback to the visual path for pages whose text layer
    fails quality checks.

    The visual-fallback backends are optional: when they are not supplied
    (or not installed), a suspicious page is kept with its native text and
    flagged in `Page.notes` rather than silently presented as trustworthy.
    """
    from doc_extraction.backends.pymupdf_table_backend import PyMuPDFTableBackend
    from doc_extraction.stages import table as table_stage

    thresholds = TextQualityThresholds(
        min_chars_for_assessment=config.text_quality_min_chars,
        max_mixed_script_word_ratio=config.text_quality_max_mixed_script_word_ratio,
        max_unexpected_script_ratio=config.text_quality_max_unexpected_script_ratio,
        max_replacement_ratio=config.text_quality_max_replacement_ratio,
        max_control_ratio=config.text_quality_max_control_ratio,
        min_alpha_ratio=config.text_quality_min_alpha_ratio,
        max_digit_in_word_ratio=config.text_quality_max_digit_in_word_ratio,
        expected_scripts=tuple(config.text_quality_expected_scripts),
    )
    native_table_backend = PyMuPDFTableBackend()

    ctx_manager = logger.stage("parse", BACKEND_NAME_NATIVE) if logger else noop_stage()
    with ctx_manager as ctx:
        doc = pymupdf.open(path)
        try:
            body_size = _estimate_body_font_size(doc)
            page_specs: list[tuple[int, float, float, list[Element], list[str], bool]] = []
            suspicious_indices: list[int] = []

            for page_index in range(doc.page_count):
                pdf_page = doc[page_index]
                report = assess_text(pdf_page.get_text(), thresholds)
                notes = [f"text_quality: {'; '.join(report.reasons)}"]
                if report.suspicious:
                    suspicious_indices.append(page_index)
                elements = _extract_text_elements(pdf_page, page_index, body_size)
                page_specs.append(
                    (
                        page_index,
                        pdf_page.rect.width,
                        pdf_page.rect.height,
                        elements,
                        notes,
                        report.suspicious,
                    )
                )
        finally:
            doc.close()

        pages: list[Page] = []
        total_elements = 0
        total_tables = 0

        for page_index, width, height, elements, notes, suspicious in page_specs:
            page_input = PageInput(
                page_index=page_index,
                width=width,
                height=height,
                dpi=None,
                source_pdf_path=path,
            )

            tables = []
            if config.digital_pdf_tables:
                table_result = table_stage.run_table(
                    page_input, [], native_table_backend, output_dir / "tables", logger
                )
                tables = table_result.tables
                notes.extend(table_result.warnings)

            if tables:
                table_boxes = [t.bbox for t in tables if t.bbox is not None]
                elements = _drop_elements_inside_tables(elements, table_boxes)
                next_index = len(elements)
                for offset, table in enumerate(tables):
                    elements.append(
                        Element(
                            id=f"p{page_index}-etbl{offset}",
                            type=ElementType.TABLE,
                            bbox=table.bbox,
                            page_number=page_index + 1,
                            source_backend=table.source_backend,
                            table_id=table.id,
                            order_index=next_index + offset,
                        )
                    )

            pages.append(
                Page(
                    index=page_index,
                    width=width,
                    height=height,
                    coordinate_unit="pt",
                    coordinate_origin="top-left",
                    is_rendered_page=True,
                    source_route="digital_pdf",
                    source_backend=BACKEND_NAME_NATIVE,
                    elements=elements,
                    tables=tables,
                    notes=notes,
                )
            )
            total_elements += len(elements)
            total_tables += len(tables)

        ctx.metrics = {
            "num_pages": len(pages),
            "num_elements": total_elements,
            "num_tables": total_tables,
            "num_suspicious_pages": len(suspicious_indices),
        }
        if suspicious_indices:
            ctx.warnings.append(
                f"{len(suspicious_indices)} page(s) failed text-quality checks: "
                f"{[i + 1 for i in suspicious_indices]}"
            )

    if suspicious_indices and config.digital_pdf_page_fallback:
        pages = _apply_page_fallback(
            path=path,
            pages=pages,
            suspicious_indices=suspicious_indices,
            config=config,
            output_dir=output_dir,
            layout_backend=layout_backend,
            ocr_backend=ocr_backend,
            table_backend=image_table_backend,
            logger=logger,
        )

    return pages


def _apply_page_fallback(
    path: Path,
    pages: list[Page],
    suspicious_indices: list[int],
    config: PipelineConfig,
    output_dir: Path,
    layout_backend: LayoutBackend | None,
    ocr_backend: OCRBackend | None,
    table_backend: TableBackend | None,
    logger: StageLogger | None,
) -> list[Page]:
    """Re-extract individual pages through the visual path.

    Only the pages in `suspicious_indices` are rendered and OCR'd; every
    other page keeps its cheap native extraction. When no visual backend is
    available the native page is kept but explicitly annotated as
    untrustworthy — never silently passed off as fine.
    """
    unavailable_reason: str | None = None
    if layout_backend is None or ocr_backend is None:
        unavailable_reason = "no layout/OCR backend supplied for fallback"
    elif not layout_backend.is_available() or not ocr_backend.is_available():
        unavailable_reason = "layout/OCR backend not installed in this environment"

    if unavailable_reason is not None:
        for index in suspicious_indices:
            pages[index].notes.append(
                f"SUSPECT native text retained: {unavailable_reason}. "
                f"Install an OCR backend (see docs/backends.md) to re-extract this page."
            )
            if logger is not None:
                logger.log_event(
                    stage="page_fallback", backend="none", status="failure", page=index,
                    error=unavailable_reason,
                    warnings=["suspicious page kept with untrusted native text"],
                )
        return pages

    for index in suspicious_indices:
        try:
            image_path = render_single_pdf_page(
                path, index, output_dir / "rendered", config.render_dpi, logger
            )
            rebuilt = run_scanned_page_pipeline(
                image_path=image_path,
                page_index=index,
                dpi=config.render_dpi,
                layout_backend=layout_backend,
                ocr_backend=ocr_backend,
                table_backend=table_backend,
                output_dir=output_dir,
                logger=logger,
            )
            native_notes = list(pages[index].notes)
            rebuilt.notes = native_notes + [
                "page re-extracted via visual/OCR fallback because its native "
                "text layer failed text-quality checks"
            ]
            rebuilt.source_route = "digital_pdf+page_fallback"
            pages[index] = rebuilt
        except Exception as exc:  # noqa: BLE001 - recorded, page kept, run continues
            pages[index].notes.append(
                f"SUSPECT native text retained: visual fallback failed "
                f"({type(exc).__name__}: {exc})"
            )
            if logger is not None:
                logger.log_event(
                    stage="page_fallback", backend="visual", status="failure", page=index,
                    error=f"{type(exc).__name__}: {exc}",
                )

    return pages


def parse_scanned_pdf(
    path: Path,
    dpi: int,
    layout_backend: LayoutBackend,
    ocr_backend: OCRBackend,
    table_backend: TableBackend,
    output_dir: Path,
    logger: StageLogger | None = None,
) -> list[Page]:
    """Steps D-H for a scanned PDF: render every page, then run the shared
    layout/OCR/table/merge chain per page."""
    image_paths = render_pdf_pages(path, output_dir / "rendered", dpi, logger)
    pages = []
    for page_index, image_path in enumerate(image_paths):
        page = run_scanned_page_pipeline(
            image_path, page_index, dpi, layout_backend, ocr_backend, table_backend, output_dir, logger
        )
        page.source_route = "scanned_pdf"
        pages.append(page)
    return pages
