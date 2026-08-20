"""Image pipeline: a standalone raster image is treated as a single scanned
page and run through the same layout -> OCR -> table -> merge chain as a
scanned PDF page (see pipelines/base.run_scanned_page_pipeline).
"""
from __future__ import annotations

from pathlib import Path

from doc_extraction.pipelines.base import LayoutBackend, OCRBackend, TableBackend, run_scanned_page_pipeline
from doc_extraction.schemas.page import Page
from doc_extraction.stages.render import render_image_passthrough
from doc_extraction.utils.logging import StageLogger


def parse_image(
    path: Path,
    dpi: int,
    layout_backend: LayoutBackend,
    ocr_backend: OCRBackend,
    table_backend: TableBackend,
    output_dir: Path,
    logger: StageLogger | None = None,
) -> list[Page]:
    image_path = render_image_passthrough(path, output_dir / "rendered", logger)
    page = run_scanned_page_pipeline(
        image_path, 0, dpi, layout_backend, ocr_backend, table_backend, output_dir, logger
    )
    return [page]
