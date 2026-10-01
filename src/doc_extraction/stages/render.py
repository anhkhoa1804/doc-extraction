"""Stage D — render page images only where a later stage actually needs
pixels (scanned PDFs, raw images). Digital PDFs and native office documents
skip this stage entirely (spec: "do not immediately route everything through
OCR/VLM").

Uses PyMuPDF's built-in rasterizer — no external binary (poppler, etc.)
required, which keeps this portable across the mixed Windows environment
this was built on.
"""
from __future__ import annotations

from pathlib import Path

import pymupdf as fitz
from PIL import Image

from doc_extraction.utils.limits import ResourceGuard
from doc_extraction.utils.logging import StageLogger, noop_stage

BACKEND_NAME = "pymupdf"


def render_pdf_pages(
    pdf_path: Path,
    output_dir: Path,
    dpi: int,
    logger: StageLogger | None = None,
    resource_guard: ResourceGuard | None = None,
) -> list[Path]:
    """Rasterize every page of `pdf_path` to `output_dir/page-NNN.png`."""
    output_dir.mkdir(parents=True, exist_ok=True)
    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)

    doc = fitz.open(pdf_path)
    out_paths: list[Path] = []
    try:
        for index in range(doc.page_count):
            if resource_guard is not None:
                page_rect = doc[index].rect
                resource_guard.check_runtime(f"before rendering PDF page {index + 1}")
                resource_guard.reserve_raster(
                    round(page_rect.width * zoom), round(page_rect.height * zoom), f"PDF page {index + 1}"
                )
            ctx_manager = (
                logger.stage("render", BACKEND_NAME, page=index) if logger else noop_stage()
            )
            with ctx_manager as ctx:
                pixmap = doc[index].get_pixmap(matrix=matrix)
                out_path = output_dir / f"page-{index + 1:03d}.png"
                pixmap.save(out_path)
                if resource_guard is not None:
                    resource_guard.check_runtime(f"after rendering PDF page {index + 1}")
                out_paths.append(out_path)
                if ctx is not None:
                    ctx.output_path = str(out_path)
                    ctx.metrics = {"width": pixmap.width, "height": pixmap.height, "dpi": dpi}
    finally:
        doc.close()
    return out_paths


def render_single_pdf_page(
    pdf_path: Path,
    page_index: int,
    output_dir: Path,
    dpi: int,
    logger: StageLogger | None = None,
    resource_guard: ResourceGuard | None = None,
) -> Path:
    """Rasterize exactly one page. Used by the digital-PDF route's per-page
    fallback, where only a few pages need pixels and rendering the whole
    document would defeat the point of the cheap-signal design."""
    output_dir.mkdir(parents=True, exist_ok=True)
    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)

    doc = fitz.open(pdf_path)
    try:
        if page_index >= doc.page_count:
            raise IndexError(f"page index {page_index} out of range for {doc.page_count}-page PDF")
        if resource_guard is not None:
            page_rect = doc[page_index].rect
            resource_guard.check_runtime(f"before rendering PDF page {page_index + 1}")
            resource_guard.reserve_raster(
                round(page_rect.width * zoom), round(page_rect.height * zoom), f"PDF page {page_index + 1}"
            )
        ctx_manager = logger.stage("render", BACKEND_NAME, page=page_index) if logger else noop_stage()
        with ctx_manager as ctx:
            pixmap = doc[page_index].get_pixmap(matrix=matrix)
            out_path = output_dir / f"page-{page_index + 1:03d}.png"
            pixmap.save(out_path)
            if resource_guard is not None:
                resource_guard.check_runtime(f"after rendering PDF page {page_index + 1}")
            ctx.output_path = str(out_path)
            ctx.metrics = {"width": pixmap.width, "height": pixmap.height, "dpi": dpi}
        return out_path
    finally:
        doc.close()


def render_image_passthrough(
    image_path: Path,
    output_dir: Path,
    logger: StageLogger | None = None,
) -> Path:
    """Normalize a standalone image input into the same rendered/page-001.png
    shape the rest of the pipeline expects, without ever touching the
    original file. Always re-encodes to PNG (also fixes e.g. CMYK JPEGs that
    downstream OCR/table backends can't read)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    ctx_manager = logger.stage("render", BACKEND_NAME, page=0) if logger else noop_stage()
    with ctx_manager as ctx:
        with Image.open(image_path) as im:
            im = im.convert("RGB")
            out_path = output_dir / "page-001.png"
            im.save(out_path, format="PNG")
            width, height = im.size
        if ctx is not None:
            ctx.output_path = str(out_path)
            ctx.metrics = {"width": width, "height": height}
    return out_path
