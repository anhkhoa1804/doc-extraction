"""Optional PaddleOCR-VL 1.6 whole-page document parser adapter.

The Paddle runtime is imported lazily because it is a separate, heavyweight
inference stack. Install PaddleOCR 3.6+ and PaddlePaddle GPU 3.2.1+ in an
isolated environment; the core package remains importable without it.
"""
from __future__ import annotations

import atexit
import hashlib
import importlib.metadata
import importlib.util
import math
import mimetypes
import sys
import threading
import time
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
from doc_extraction.utils.limits import (
    ResourceLimitExceeded,
    current_runtime_elapsed_seconds,
    current_worker_policy,
)
from doc_extraction.utils.process_worker import (
    BoundedPersistentWorker,
    WorkerCrashed,
    WorkerError,
    WorkerProtocolError,
    WorkerTempLimit,
    WorkerTimeout,
)

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
_WORKERS: dict[str, BoundedPersistentWorker] = {}
_WORKERS_LOCK = threading.RLock()
_MAX_WORKER_MESSAGE_BYTES = 16 * 1024 * 1024


class E2EWorkerFailure(RuntimeError):
    """The isolated inference worker failed without producing a valid page."""


class E2EInvalidModelOutput(ValueError):
    """Model output failed canonical page validation."""


def _worker_for(device: str) -> BoundedPersistentWorker:
    with _WORKERS_LOCK:
        worker = _WORKERS.get(device)
        if worker is None:
            worker = BoundedPersistentWorker(
                [sys.executable, "-u", "-m", "doc_extraction.backends.paddleocr_vl_worker", "--device", device],
                max_message_bytes=_MAX_WORKER_MESSAGE_BYTES,
            )
            _WORKERS[device] = worker
        return worker


def shutdown_paddleocr_vl_workers() -> None:
    """Terminate owned PaddleOCR-VL worker sessions (also registered at exit)."""
    with _WORKERS_LOCK:
        workers = list(_WORKERS.values())
        _WORKERS.clear()
    errors: list[Exception] = []
    for worker in workers:
        try:
            worker.close()
        except (WorkerError, OSError) as exc:  # cleanup integrity errors are not hidden
            errors.append(exc)
    if errors:
        raise E2EWorkerFailure(f"failed to clean up {len(errors)} PaddleOCR-VL worker(s)") from errors[0]


atexit.register(shutdown_paddleocr_vl_workers)


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
    # HTML rowspans can extend beyond the last explicit <tr>. The canonical
    # grid must include every occupied row rather than declaring only the
    # number of serialized row elements.
    n_rows = max(
        len(rows),
        max((cell.row + cell.row_span for row in rows for cell in row), default=0),
    )
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


def page_from_paddle_result(result: Any, phase_timings: dict[str, float] | None = None) -> Page:
    """Map one official PaddleOCR-VL page result to the internal canonical Page.

    Missing geometry/confidence remains null. Layout regions are retained as
    typed canonical elements, and table HTML is represented as cells when it
    can be parsed safely; unsupported table content remains a text element.
    """
    decode_started = time.perf_counter()
    data = _result_data(result)
    if phase_timings is not None:
        phase_timings["result_json_decode_seconds"] = time.perf_counter() - decode_started
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
    mapping_started = time.perf_counter()
    table_parse_seconds = 0.0
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
            table_started = time.perf_counter()
            table = _table_from_html(candidate_table_id, content, bbox)
            table_parse_seconds += time.perf_counter() - table_started
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
    page = Page(
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
    if phase_timings is not None:
        phase_timings["table_parsing_seconds"] = table_parse_seconds
        phase_timings["canonical_mapping_inclusive_seconds"] = time.perf_counter() - mapping_started
    return page


def validate_worker_page(value: Any) -> Page:
    """Validate structural invariants before accepting a worker-produced page."""
    try:
        page = Page.model_validate(value)
        if page.index != 0 or not page.is_rendered_page:
            raise ValueError("E2E page must identify the sole rendered image page")
        if not math.isfinite(page.width) or not math.isfinite(page.height) or page.width <= 0 or page.height <= 0:
            raise ValueError("E2E page dimensions are invalid")
        element_ids = [element.id for element in page.elements]
        table_ids = [table.id for table in page.tables]
        if len(element_ids) != len(set(element_ids)) or len(table_ids) != len(set(table_ids)):
            raise ValueError("E2E output contains duplicate element/table identifiers")
        if len(page.reading_order) != len(set(page.reading_order)) or set(page.reading_order) != set(element_ids):
            raise ValueError("E2E reading order must reference every element exactly once")
        tables = {table.id: table for table in page.tables}
        table_elements: dict[str, int] = {table_id: 0 for table_id in tables}
        for element in page.elements:
            if element.bbox is not None and not all(math.isfinite(v) for v in element.bbox.as_tuple()):
                raise ValueError("E2E element geometry contains a non-finite value")
            if element.type == ElementType.TABLE:
                if element.table_id not in tables:
                    raise ValueError("E2E table element references a missing table")
                table_elements[element.table_id] += 1
            elif element.table_id is not None:
                raise ValueError("E2E non-table element contains a table reference")
        if any(count != 1 for count in table_elements.values()):
            raise ValueError("E2E each table must have exactly one owning table element")
        for table in page.tables:
            if table.n_rows <= 0 or table.n_cols <= 0:
                raise ValueError("E2E table dimensions must be positive")
            occupied: set[tuple[int, int]] = set()
            for cell in table.cells:
                if cell.row < 0 or cell.col < 0 or cell.row_span <= 0 or cell.col_span <= 0:
                    raise ValueError("E2E table cell coordinates/spans are invalid")
                if cell.row + cell.row_span > table.n_rows or cell.col + cell.col_span > table.n_cols:
                    raise ValueError("E2E table cell span exceeds declared dimensions")
                if cell.bbox is not None and not all(math.isfinite(v) for v in cell.bbox.as_tuple()):
                    raise ValueError("E2E table cell geometry contains a non-finite value")
                slots = {
                    (row, col)
                    for row in range(cell.row, cell.row + cell.row_span)
                    for col in range(cell.col, cell.col + cell.col_span)
                }
                if occupied.intersection(slots):
                    raise ValueError("E2E table cells overlap")
                occupied.update(slots)
        return page
    except Exception as exc:
        if isinstance(exc, E2EInvalidModelOutput):
            raise
        raise E2EInvalidModelOutput(f"invalid PaddleOCR-VL page output: {type(exc).__name__}: {exc}") from exc


class PaddleOCRVLBackend:
    """Whole-document backend using PaddleOCR-VL's official v1.6 pipeline."""

    name = "paddleocr_vl"
    model_id = "PaddlePaddle/PaddleOCR-VL-1.6"
    model_revision = "PaddleX registry model version v1.6 (weight SHA-256 recorded by worker)"

    def __init__(self, device: str = "cuda", pipeline: Any | None = None) -> None:
        if device not in ("cpu", "cuda"):
            raise ValueError("PaddleOCR-VL device must be resolved to cpu or cuda")
        if pipeline is None and not self.is_available():
            raise RuntimeError(
                "PaddleOCR-VL requires the optional isolated PaddleOCR runtime; "
                "install paddlepaddle-gpu and paddleocr[doc-parser]"
            )
        self.device = device
        self.last_phase_timings: dict[str, float | str | None] = {}
        # Injectable only for small deterministic adapter unit tests. Normal
        # execution always goes through the separately supervised process.
        self._test_pipeline = pipeline

    @staticmethod
    def is_available() -> bool:
        return importlib.util.find_spec("paddleocr") is not None

    def convert(self, path: Path, config: Any) -> Document:
        if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}:
            raise ValueError("PaddleOCR-VL benchmark adapter currently accepts raster images only")
        sha256 = sha256_file(path)
        model_versions = self.model_versions()
        if self._test_pipeline is not None:
            predict_started = time.perf_counter()
            results = list(self._test_pipeline.predict(str(path)))
            self.last_phase_timings = {
                "pipeline_predict_seconds": time.perf_counter() - predict_started,
                "timing_source": "injected_test_pipeline",
            }
            if len(results) != 1:
                raise E2EInvalidModelOutput(f"PaddleOCR-VL expected one image result, received {len(results)}")
            page = validate_worker_page(page_from_paddle_result(results[0]))
        else:
            weight_keys = ("model_weights_sha256", "layout_weights_sha256")
            missing_weights = [key for key in weight_keys if not model_versions.get(key)]
            if missing_weights:
                raise E2EWorkerFailure(
                    "refusing inference without pre-run model artifact hashes: " + ", ".join(missing_weights)
                )
            scratch_limit, timeout, hard_timeout, ipc_limit = current_worker_policy()
            if scratch_limit <= 0:
                raise ResourceLimitExceeded(
                    "max_temp_bytes", 0, 1, "PaddleOCR-VL worker requires a positive remaining scratch budget"
                )
            worker = _worker_for(self.device)
            worker.max_message_bytes = min(_MAX_WORKER_MESSAGE_BYTES, ipc_limit)
            request_started = time.perf_counter()
            try:
                reply = worker.request(
                    {"op": "predict", "input_path": str(path), "input_sha256": sha256},
                    timeout=timeout,
                    scratch_limit=scratch_limit,
                )
            except WorkerTimeout as exc:
                self.last_phase_timings = {
                    "worker_startup_seconds": worker.last_startup_seconds,
                    "parent_request_elapsed_seconds": worker.last_request_seconds,
                    "worker_termination_and_cleanup_seconds": worker.last_termination_seconds,
                    "model_initialization_seconds": worker.ready_metadata.get("model_initialization_seconds"),
                    "model_weight_attestation_seconds": worker.ready_metadata.get("model_weight_attestation_seconds"),
                    "pipeline_predict_seconds": None,
                    "timeout": "max_runtime_seconds",
                    "timing_source": "parent_supervisor; timed-out worker phases unavailable",
                }
                elapsed = current_runtime_elapsed_seconds()
                raise ResourceLimitExceeded(
                    "max_runtime_seconds",
                    hard_timeout,
                    elapsed if elapsed is not None else hard_timeout,
                    "PaddleOCR-VL isolated worker startup/inference/postprocessing; worker deadline expired",
                ) from exc
            except WorkerTempLimit as exc:
                self.last_phase_timings = {
                    "worker_startup_seconds": worker.last_startup_seconds,
                    "parent_request_elapsed_seconds": worker.last_request_seconds,
                    "worker_termination_and_cleanup_seconds": worker.last_termination_seconds,
                    "model_initialization_seconds": worker.ready_metadata.get("model_initialization_seconds"),
                    "model_weight_attestation_seconds": worker.ready_metadata.get("model_weight_attestation_seconds"),
                    "timeout": "max_temp_bytes",
                    "timing_source": "parent_supervisor",
                }
                raise ResourceLimitExceeded(
                    "max_temp_bytes", exc.limit, exc.actual,
                    "PaddleOCR-VL isolated worker private scratch",
                ) from exc
            except (WorkerCrashed, WorkerProtocolError) as exc:
                self.last_phase_timings = {
                    "worker_startup_seconds": worker.last_startup_seconds,
                    "parent_request_elapsed_seconds": worker.last_request_seconds,
                    "worker_termination_and_cleanup_seconds": worker.last_termination_seconds,
                    "model_initialization_seconds": worker.ready_metadata.get("model_initialization_seconds"),
                    "model_weight_attestation_seconds": worker.ready_metadata.get("model_weight_attestation_seconds"),
                    "timing_source": "parent_supervisor; worker failed before complete timing response",
                }
                raise E2EWorkerFailure(f"PaddleOCR-VL {exc.kind}: {exc}") from exc
            reply_timings = reply.get("phase_timings")
            reply_timings = reply_timings if isinstance(reply_timings, dict) else {}
            worker_accounted = reply_timings.get("worker_accounted_seconds")
            self.last_phase_timings = {
                **reply_timings,
                "worker_startup_seconds": worker.last_startup_seconds,
                "model_initialization_seconds": worker.ready_metadata.get("model_initialization_seconds"),
                "model_weight_attestation_seconds": worker.ready_metadata.get("model_weight_attestation_seconds"),
                "parent_request_elapsed_seconds": worker.last_request_seconds,
                "parent_request_wall_seconds": time.perf_counter() - request_started,
                "worker_termination_and_cleanup_seconds": worker.last_termination_seconds,
                "timing_source": "worker/public-pipeline boundaries; preprocess/inference/decoder internals are opaque",
            }
            if isinstance(worker_accounted, (int, float)):
                self.last_phase_timings["parent_roundtrip_residual_seconds"] = max(
                    0.0, worker.last_request_seconds - float(worker_accounted)
                )
            validation_started = time.perf_counter()
            page = validate_worker_page(reply.get("page"))
            self.last_phase_timings["parent_canonical_validation_seconds"] = (
                time.perf_counter() - validation_started
            )
            if reply.get("input_sha256") != sha256:
                raise E2EInvalidModelOutput("worker result input identity does not match submitted page")
            versions = reply.get("model_versions")
            if not isinstance(versions, dict):
                raise E2EInvalidModelOutput("worker did not return model artifact identity")
            if any(versions.get(key) != model_versions.get(key) for key in weight_keys):
                raise E2EWorkerFailure("model weight identity changed between pre-run attestation and worker load")
            model_versions = {**model_versions, **{str(k): str(v) for k, v in versions.items()}}
        document_id = make_document_id(path, sha256)
        metadata = RunMetadata(
            input_filename=path.name,
            input_path=str(path),
            file_hash_sha256=sha256,
            file_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream",
            route="image",
            pipeline=self.name,
            backend=self.name,
            model_versions=model_versions,
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
