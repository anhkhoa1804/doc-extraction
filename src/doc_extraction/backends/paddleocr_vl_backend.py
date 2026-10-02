"""Optional PaddleOCR-VL 1.6 whole-page document parser adapter.

The Paddle runtime is imported lazily because it is a separate, heavyweight
inference stack. Install PaddleOCR 3.6+ and PaddlePaddle GPU 3.2.1+ in an
isolated environment; the core package remains importable without it.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import importlib.util
import math
import mimetypes
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from doc_extraction.schemas.document import Document, RunMetadata
from doc_extraction.schemas.element import BBox, Element, ElementType
from doc_extraction.schemas.page import Page
from doc_extraction.schemas.table import Cell, Table
from doc_extraction.utils.hashing import sha256_file
from doc_extraction.utils.ids import document_id as make_document_id

_LABEL_TYPES = {
    "paragraph_title": ElementType.HEADING,
    "title": ElementType.HEADING,
    "text": ElementType.PARAGRAPH,
    "paragraph": ElementType.PARAGRAPH,
    "table": ElementType.TABLE,
    "display_formula": ElementType.FORMULA,
    "inline_formula": ElementType.FORMULA,
    "formula": ElementType.FORMULA,
    "list": ElementType.LIST_ITEM,
    "list_item": ElementType.LIST_ITEM,
    "image": ElementType.IMAGE,
    "chart": ElementType.IMAGE,
}
_PIPELINE_CACHE: dict[str, Any] = {}


class _TableHTMLParser(HTMLParser):
    """Small, dependency-free conversion of Paddle's table HTML into cells."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[Cell]] = []
        self._row: list[Cell] | None = None
        self._cell_text: list[str] | None = None
        self._row_index = -1
        self._col_index = 0
        self._row_spans: dict[int, int] = {}
        self._row_span = 1
        self._col_span = 1
        self._is_header = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_map = dict(attrs)
        if tag.lower() == "tr":
            self._row_index += 1
            self._col_index = 0
            self._row = []
            self.rows.append(self._row)
        elif tag.lower() in {"td", "th"} and self._row is not None:
            self._cell_text = []
            self._row_span = _positive_int(attrs_map.get("rowspan"), 1)
            self._col_span = _positive_int(attrs_map.get("colspan"), 1)
            self._is_header = tag.lower() == "th"
        elif tag.lower() == "br" and self._cell_text is not None:
            self._cell_text.append("\n")

    def handle_data(self, data: str) -> None:
        if self._cell_text is not None:
            self._cell_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "tr":
            self._row_spans = {
                col: remaining - 1 for col, remaining in self._row_spans.items() if remaining > 1
            }
            return
        if tag.lower() not in {"td", "th"} or self._row is None or self._cell_text is None:
            return
        while any(self._row_spans.get(col, 0) > 0 for col in range(self._col_index, self._col_index + self._col_span)):
            self._col_index += 1
        self._row.append(
            Cell(
                row=self._row_index,
                col=self._col_index,
                row_span=self._row_span,
                col_span=self._col_span,
                text="".join(self._cell_text).strip(),
                is_header=self._is_header,
            )
        )
        if self._row_span > 1:
            for col in range(self._col_index, self._col_index + self._col_span):
                self._row_spans[col] = max(self._row_spans.get(col, 0), self._row_span)
        self._col_index += self._col_span
        self._cell_text = None


def _positive_int(value: str | None, default: int) -> int:
    try:
        parsed = int(value or "")
        return parsed if parsed > 0 else default
    except ValueError:
        return default


def _bbox(raw: Any) -> BBox | None:
    if not isinstance(raw, (list, tuple)) or len(raw) != 4:
        return None
    try:
        values = tuple(float(value) for value in raw)
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(value) for value in values):
        return None
    x0, y0, x1, y1 = values
    if x0 > x1 or y0 > y1:
        return None
    return BBox(x0=x0, y0=y0, x1=x1, y1=y1)


def _table_from_html(table_id: str, html: str, bbox: BBox | None) -> Table | None:
    parser = _TableHTMLParser()
    parser.feed(html)
    parser.close()
    rows = [row for row in parser.rows if row]
    n_rows = len(rows)
    n_cols = max((max(cell.col + cell.col_span for cell in row) for row in rows), default=0)
    if not n_rows or not n_cols:
        return None
    return Table(
        id=table_id,
        bbox=bbox,
        page_number=1,
        n_rows=n_rows,
        n_cols=n_cols,
        cells=[cell for row in rows for cell in row],
        source_backend="paddleocr_vl",
    )


def _result_data(result: Any) -> dict[str, Any]:
    raw = getattr(result, "json", None)
    raw = raw() if callable(raw) else raw
    if not isinstance(raw, dict):
        raise TypeError("PaddleOCR-VL result did not expose a JSON object")
    data = raw.get("res", raw)
    if not isinstance(data, dict):
        raise TypeError("PaddleOCR-VL result res field is not an object")
    return data


def page_from_paddle_result(result: Any) -> Page:
    """Map one official PaddleOCR-VL page result to the internal canonical Page.

    Missing geometry/confidence remains null. Layout regions are retained as
    typed canonical elements, and table HTML is represented as cells when it
    can be parsed safely; unsupported table content remains a text element.
    """
    data = _result_data(result)
    try:
        width, height = float(data["width"]), float(data["height"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("PaddleOCR-VL result is missing valid page dimensions") from exc
    if not math.isfinite(width) or not math.isfinite(height) or width <= 0 or height <= 0:
        raise ValueError("PaddleOCR-VL page dimensions must be finite and positive")

    elements: list[Element] = []
    tables: list[Table] = []
    notes: list[str] = []
    ordered_blocks = list(data.get("parsing_res_list") or [])
    for order, block in enumerate(ordered_blocks):
        if not isinstance(block, dict):
            notes.append(f"E2E_UNSUPPORTED: ignored non-object parsing block at index {order}")
            continue
        label = str(block.get("block_label") or "other").lower()
        content_value = block.get("block_content")
        content = content_value if isinstance(content_value, str) else ""
        bbox = _bbox(block.get("block_bbox"))
        element_type = _LABEL_TYPES.get(label, ElementType.OTHER)
        table_id = None
        text: str | None = content or None

        if element_type == ElementType.TABLE:
            candidate_table_id = f"p0-t{len(tables)}"
            table = _table_from_html(candidate_table_id, content, bbox)
            if table is not None:
                tables.append(table)
                table_id = candidate_table_id
                text = None
            else:
                notes.append(f"E2E_UNSUPPORTED: table block {order} was not valid HTML; retained as text")
                element_type = ElementType.PARAGRAPH

        element_id = f"p0-e{len(elements)}"
        elements.append(
            Element(
                id=element_id,
                type=element_type,
                text=text,
                bbox=bbox,
                page_number=1,
                confidence=None,
                source_backend="paddleocr_vl",
                source_id=str(block.get("block_id")) if block.get("block_id") is not None else None,
                order_index=order,
                table_id=table_id,
                extra={"model_block_label": label},
            )
        )

    reading_order = [element.id for element in elements]
    return Page(
        index=0,
        width=width,
        height=height,
        coordinate_unit="px",
        coordinate_origin="top-left",
        is_rendered_page=True,
        source_route="e2e_document_parser",
        source_backend="paddleocr_vl",
        elements=elements,
        tables=tables,
        reading_order=reading_order,
        notes=notes,
    )


class PaddleOCRVLBackend:
    """Whole-document backend using PaddleOCR-VL's official v1.6 pipeline."""

    name = "paddleocr_vl"
    model_id = "PaddlePaddle/PaddleOCR-VL-1.6"
    # PaddleX resolves the versioned model through its registry, so a Git
    # revision is not guaranteed. Run metadata records local weight hashes.
    model_revision = "PaddleX registry v1.6; resolved weight hashes recorded when available"

    def __init__(self, device: str = "cuda", pipeline: Any | None = None) -> None:
        if pipeline is None:
            if importlib.util.find_spec("paddleocr") is None:
                raise RuntimeError(
                    "PaddleOCR-VL requires the optional isolated PaddleOCR runtime; "
                    "install paddlepaddle-gpu and paddleocr[doc-parser]"
                )
            paddle_device = "gpu:0" if device == "cuda" else "cpu"
            if paddle_device not in _PIPELINE_CACHE:
                from paddleocr import PaddleOCRVL

                _PIPELINE_CACHE[paddle_device] = PaddleOCRVL(
                    pipeline_version="v1.6", device=paddle_device
                )
            pipeline = _PIPELINE_CACHE[paddle_device]
        self._pipeline = pipeline

    @staticmethod
    def is_available() -> bool:
        return importlib.util.find_spec("paddleocr") is not None

    def convert(self, path: Path, config: Any) -> Document:
        if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}:
            raise ValueError("PaddleOCR-VL benchmark adapter currently accepts raster images only")
        results = list(self._pipeline.predict(str(path)))
        if len(results) != 1:
            raise ValueError(f"PaddleOCR-VL expected one image result, received {len(results)}")
        page = page_from_paddle_result(results[0])
        sha256 = sha256_file(path)
        document_id = make_document_id(path, sha256)
        metadata = RunMetadata(
            input_filename=path.name,
            input_path=str(path),
            file_hash_sha256=sha256,
            file_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream",
            route="image",
            pipeline=self.name,
            backend=self.name,
            model_versions=self.model_versions(),
            timestamp=datetime.now(timezone.utc).isoformat(),
            device="cuda" if config.device == "cuda" else "cpu",
        )
        return Document(document_id=document_id, metadata=metadata, pages=[page])

    @classmethod
    def model_versions(cls) -> dict[str, str]:
        versions = {"model": cls.model_id, "model_revision": cls.model_revision, "pipeline": "PaddleOCR v1.6"}
        for key, distribution in (
            ("paddleocr", "paddleocr"),
            ("paddlex", "paddlex"),
            ("paddlepaddle", "paddlepaddle-gpu"),
        ):
            try:
                versions[key] = importlib.metadata.version(distribution)
            except importlib.metadata.PackageNotFoundError:
                if key == "paddlepaddle":
                    try:
                        versions[key] = importlib.metadata.version("paddlepaddle")
                    except importlib.metadata.PackageNotFoundError:
                        pass
        model_root = Path.home() / ".paddlex" / "official_models"
        for key, relative_path in (
            ("model_weights_sha256", Path("PaddleOCR-VL-1.6/model.safetensors")),
            ("layout_weights_sha256", Path("PP-DocLayoutV3/inference.pdiparams")),
        ):
            weight_path = model_root / relative_path
            if weight_path.is_file():
                digest = hashlib.sha256()
                with weight_path.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(chunk)
                versions[key] = digest.hexdigest()
        return versions
