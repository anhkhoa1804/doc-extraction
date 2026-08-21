"""Docling backend — the one whole-document backend actually installed and
run end-to-end in the reference environment (pure pip install, CPU-friendly,
covers PDF/DOCX/XLSX/PPTX natively plus layout + OCR (EasyOCR by default) +
table structure (TableFormer) + its own reading order in a single call).

Serves three roles:
  1. `WholeDocumentBackend.convert()` — full-document conversion, used by
     `doc_extraction compare` and by `--backend docling`. Preserves
     Docling's own reading order (from `iterate_items()` traversal), so it
     can be diffed against our own `stages/reading_order.py` heuristic.
  2. `LayoutBackend.analyze()` / `OCRBackend.recognize()` — used as the
     *default* component backends for the baseline pipeline's scanned-page
     route. Both call Docling's ordinary `convert()` on a single rendered
     page image (Docling's well-documented, stable "convert any file,
     image or PDF" entrypoint — no special per-image configuration needed)
     and share one cached conversion per image so layout+OCR only run
     Docling once per page, not twice.

Docling text items are block/line granularity, not word-level tokens — the
OCRResult "tokens" this backend returns are really "text regions," which is
coarser than a typical OCR engine's token output. That's an explicit,
documented choice: reaching into Docling's internal word-level OCR results
isn't part of its stable public API.
"""
from __future__ import annotations

import importlib.util
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from doc_extraction.pipelines.base import LayoutResult, OCRResult, OCRToken, PageInput, Region
from doc_extraction.schemas.document import Document, RunMetadata
from doc_extraction.schemas.element import BBox, Element, ElementType
from doc_extraction.schemas.page import Page
from doc_extraction.schemas.table import Cell, Table
from doc_extraction.utils.hashing import sha256_file
from doc_extraction.utils.ids import document_id as make_document_id

_LABEL_MAP: dict[str, ElementType] = {
    "title": ElementType.HEADING,
    "section_header": ElementType.HEADING,
    "text": ElementType.TEXT,
    "paragraph": ElementType.PARAGRAPH,
    "list_item": ElementType.LIST_ITEM,
    "table": ElementType.TABLE,
    "picture": ElementType.IMAGE,
    "chart": ElementType.IMAGE,
    "formula": ElementType.FORMULA,
    "code": ElementType.OTHER,
    "caption": ElementType.TEXT,
    "footnote": ElementType.TEXT,
    "page_header": ElementType.OTHER,
    "page_footer": ElementType.OTHER,
    "checkbox_selected": ElementType.CHECKBOX,
    "checkbox_unselected": ElementType.CHECKBOX,
    "form": ElementType.OTHER,
    "key_value_region": ElementType.OTHER,
    "handwritten_text": ElementType.TEXT,
    "reference": ElementType.TEXT,
    "document_index": ElementType.OTHER,
}


def is_available() -> bool:
    return importlib.util.find_spec("docling") is not None


def _label_str(item: Any) -> str:
    label = getattr(item, "label", "text")
    return str(getattr(label, "value", label)).lower()


def _bbox_from_docling(bbox: Any, page_height: float) -> BBox | None:
    if bbox is None:
        return None
    l, t, r, b = float(bbox.l), float(bbox.t), float(bbox.r), float(bbox.b)
    origin = str(getattr(bbox, "coord_origin", "TOPLEFT")).upper()
    if "BOTTOMLEFT" in origin and page_height:
        y0, y1 = page_height - t, page_height - b
    else:
        y0, y1 = t, b
    x0, x1 = l, r
    if y0 > y1:
        y0, y1 = y1, y0
    if x0 > x1:
        x0, x1 = x1, x0
    return BBox(x0=x0, y0=y0, x1=x1, y1=y1)


def _convert_docling_table(item: Any, page_no: int, table_id: str, bbox: BBox | None) -> Table:
    data = item.data
    n_rows = getattr(data, "num_rows", 0) or 0
    n_cols = getattr(data, "num_cols", 0) or 0
    cells: list[Cell] = []
    for tc in getattr(data, "table_cells", []) or []:
        row = getattr(tc, "start_row_offset_idx", 0)
        col = getattr(tc, "start_col_offset_idx", 0)
        row_span = max(1, getattr(tc, "end_row_offset_idx", row + 1) - row)
        col_span = max(1, getattr(tc, "end_col_offset_idx", col + 1) - col)
        is_header = bool(getattr(tc, "column_header", False) or getattr(tc, "row_header", False))
        cells.append(
            Cell(
                row=row,
                col=col,
                row_span=row_span,
                col_span=col_span,
                text=(getattr(tc, "text", "") or "").strip(),
                is_header=is_header,
            )
        )
    return Table(
        id=table_id,
        bbox=bbox,
        page_number=page_no,
        n_rows=n_rows,
        n_cols=n_cols,
        cells=cells,
        source_backend="docling",
        confidence=None,
    )


class DoclingBackend:
    name = "docling"

    def __init__(self, device: str = "cpu", ocr_languages: list[str] | None = None) -> None:
        self.device = device
        self.ocr_languages = ocr_languages or ["en"]
        self._converter = None
        self._page_cache: "OrderedDict[str, Any]" = OrderedDict()
        self._page_cache_size = 8

    def is_available(self) -> bool:
        return is_available()

    def _get_converter(self):
        if self._converter is None:
            from docling.datamodel.base_models import InputFormat
            from docling.datamodel.pipeline_options import AcceleratorOptions, EasyOcrOptions, PdfPipelineOptions
            from docling.document_converter import DocumentConverter, ImageFormatOption, PdfFormatOption

            pipeline_options = PdfPipelineOptions()
            pipeline_options.do_ocr = True
            # Drive *every* model stage (layout, TableFormer, OCR) from the
            # configured device. Without this, docling falls back to its own
            # `device="auto"` default, which silently disagrees with
            # `config.device` — on a GPU box that means layout runs on CUDA
            # while the config claims "cpu".
            pipeline_options.accelerator_options = AcceleratorOptions(device=self.device)
            # EasyOCR (not docling's RapidOCR default) specifically for proper
            # Vietnamese ("vi") support — see docs/backends.md.
            #
            # `use_gpu` is deliberately left unset: it is deprecated upstream,
            # and setting it *overrides* the accelerator device rather than
            # following it. Leaving it None makes EasyOCR derive its device
            # from `accelerator_options` above, so one setting controls all
            # stages. Passing it explicitly is what previously pinned EasyOCR
            # to CPU even on a CUDA box, and emitted a per-page deprecation
            # warning.
            pipeline_options.ocr_options = EasyOcrOptions(lang=self.ocr_languages)

            self._converter = DocumentConverter(
                format_options={
                    InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
                    InputFormat.IMAGE: ImageFormatOption(pipeline_options=pipeline_options),
                }
            )
        return self._converter

    def _convert_cached(self, path: Path):
        key = str(path)
        if key in self._page_cache:
            self._page_cache.move_to_end(key)
            return self._page_cache[key]
        result = self._get_converter().convert(str(path))
        self._page_cache[key] = result
        if len(self._page_cache) > self._page_cache_size:
            self._page_cache.popitem(last=False)
        return result

    # -- WholeDocumentBackend --------------------------------------------

    def convert(self, path: Path, config: Any) -> Document:
        import docling

        result = self._get_converter().convert(str(path))
        docling_doc = result.document

        pages: dict[int, Page] = {}
        raw_pages = getattr(docling_doc, "pages", None) or {}
        page_items = raw_pages.items() if hasattr(raw_pages, "items") else enumerate(raw_pages, start=1)
        for page_no, page_item in page_items:
            size = getattr(page_item, "size", None)
            width = float(getattr(size, "width", 0.0) or 0.0)
            height = float(getattr(size, "height", 0.0) or 0.0)
            pages[page_no] = Page(index=page_no - 1, width=width, height=height, coordinate_unit="pt")

        order_counters: dict[int, int] = {}
        for item, _level in docling_doc.iterate_items():
            label = _label_str(item)
            prov_list = getattr(item, "prov", None) or []
            prov = prov_list[0] if prov_list else None
            page_no = getattr(prov, "page_no", 1) if prov else 1
            page = pages.setdefault(page_no, Page(index=page_no - 1, width=0.0, height=0.0))
            idx = order_counters.get(page_no, 0)
            bbox = _bbox_from_docling(getattr(prov, "bbox", None), page.height) if prov else None
            element_id = f"p{page_no - 1}-e{idx}"

            if label == "table":
                table = _convert_docling_table(item, page_no, table_id=f"p{page_no - 1}-t{idx}", bbox=bbox)
                page.tables.append(table)
                element = Element(
                    id=element_id, type=ElementType.TABLE, bbox=bbox, page_number=page_no,
                    source_backend=self.name, table_id=table.id, order_index=idx,
                )
            else:
                etype = _LABEL_MAP.get(label, ElementType.OTHER)
                element = Element(
                    id=element_id, type=etype, text=getattr(item, "text", None), bbox=bbox,
                    page_number=page_no, source_backend=self.name, order_index=idx,
                    level=1 if etype == ElementType.HEADING else None,
                )
            page.elements.append(element)
            page.reading_order.append(element_id)  # Docling's own traversal order — not recomputed
            order_counters[page_no] = idx + 1

        ordered_pages = [pages[k] for k in sorted(pages.keys())] or [Page(index=0, width=0, height=0)]

        file_hash = sha256_file(path)
        metadata = RunMetadata(
            input_filename=path.name,
            input_path=str(path),
            file_hash_sha256=file_hash,
            file_type=path.suffix.lower().lstrip("."),
            route="whole_document_backend",
            pipeline="docling",
            backend=self.name,
            model_versions={"docling": getattr(docling, "__version__", "unknown")},
            config_snapshot=config.to_snapshot() if hasattr(config, "to_snapshot") else {},
            timestamp=datetime.now(timezone.utc).isoformat(),
            device=self.device,
        )
        return Document(document_id=make_document_id(path, file_hash), metadata=metadata, pages=ordered_pages)

    # -- LayoutBackend / OCRBackend (component use in the baseline pipeline) --

    def analyze(self, page: PageInput) -> LayoutResult:
        if page.image_path is None:
            return LayoutResult(regions=[], backend=self.name, warnings=["no rendered image for this page"])
        result = self._convert_cached(page.image_path)
        docling_doc = result.document
        regions: list[Region] = []
        for item, _level in docling_doc.iterate_items():
            prov_list = getattr(item, "prov", None) or []
            prov = prov_list[0] if prov_list else None
            bbox = _bbox_from_docling(getattr(prov, "bbox", None), page.height) if prov else None
            if bbox is None:
                continue
            regions.append(Region(bbox=bbox, label=_label_str(item), confidence=None))
        return LayoutResult(regions=regions, backend=self.name)

    def recognize(self, page: PageInput) -> OCRResult:
        if page.image_path is None:
            return OCRResult(tokens=[], backend=self.name, warnings=["no rendered image for this page"])
        result = self._convert_cached(page.image_path)
        docling_doc = result.document
        tokens: list[OCRToken] = []
        for item, _level in docling_doc.iterate_items():
            label = _label_str(item)
            if label == "table":
                continue  # table text is handled by the table stage, not OCR tokens
            text = getattr(item, "text", None)
            if not text:
                continue
            prov_list = getattr(item, "prov", None) or []
            prov = prov_list[0] if prov_list else None
            bbox = _bbox_from_docling(getattr(prov, "bbox", None), page.height) if prov else None
            if bbox is None:
                continue
            tokens.append(OCRToken(text=text, bbox=bbox, confidence=None))
        return OCRResult(tokens=tokens, backend=self.name)
