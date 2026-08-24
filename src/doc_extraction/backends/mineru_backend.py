"""MinerU (OpenDataLab) backend.

Two separate things live here:

1. `MinerUBackend` — the full-document `mineru` package path, still NOT
   installed in the reference environment (its `[all]` extra documents a
   ~20 GB engine footprint, and the VLM/hybrid engines require 8 GB VRAM
   which this machine does not have). Kept as a structured "unavailable"
   backend so `doc_extraction compare --backends mineru ...` degrades
   cleanly instead of raising an import error.

2. `MinerUVLTableBackend` — a deliberately thin table-candidate source
   built on `mineru-vl-utils` + `transformers`, which *is* installable
   here (core deps: httpx/pillow/pydantic/loguru/tqdm; the model itself is
   1.2B params / ~2.3 GB on disk). It exposes exactly one method the rest
   of the pipeline already knows how to consume — `native_tables(page)` —
   the same duck-typed hook `pipelines/base._gather_extra_table_candidates`
   already looks for on the OCR backend. That means the existing N-way
   composition can take MinerU as an additional candidate with **no change
   to the composition algorithm or the canonical IR**.

Measured on the residual hard tables this project could not extract with
either Table Transformer or Docling's TableFormer (see
`docs/sota_comparison.md`): MinerU2.5 returned `TEDS_structure_only =
1.0000` on all five, including both 2x2 borderless grids that returned no
grid at all from the other two models at 1x, 2x and 3x scale.

**Feed it whole pages, not pre-cropped table regions.** Measured directly:
on `page-28657a85` a tight ground-truth crop made MinerU classify the
region as ordinary text (no table at all), while the *unmodified full
page* produced the exactly-correct 1x3 table (TEDS 0.98). MinerU2.5 already
performs its own internal coarse-to-fine pass (global layout on a
downscaled page, then native-resolution crops per region — see its paper,
arXiv 2509.22186), so pre-cropping removes the page context its layout
stage depends on and duplicates work it does internally. This is the
opposite of `TableTransformerBackend`, which *needs* a crop.

Licensing note for downstream users: the `MinerU2.5-2509-1.2B` weights are
published under **AGPL-3.0** (the MinerU code is Apache-2.0-based). That is
a materially different obligation from this repo's other model
dependencies and must be reviewed before any redistribution or hosted
deployment — flagged here rather than buried in a doc.
"""
from __future__ import annotations

import importlib.util
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from doc_extraction.pipelines.base import BackendUnavailableError, PageInput
from doc_extraction.schemas.document import Document
from doc_extraction.schemas.element import BBox
from doc_extraction.schemas.table import Cell, Table

DEFAULT_MINERU_VL_MODEL = "opendatalab/MinerU2.5-2509-1.2B"


def is_available() -> bool:
    return importlib.util.find_spec("mineru") is not None


def is_vl_available() -> bool:
    """Whether the thin VL table-candidate path can run here — the
    lightweight `mineru-vl-utils` wrapper plus a torch/transformers stack,
    not the full `mineru` engine install."""
    return all(
        importlib.util.find_spec(mod) is not None
        for mod in ("mineru_vl_utils", "transformers", "torch")
    )


class _TableHTMLParser(HTMLParser):
    """Minimal `<table>` HTML -> row-major cell grid.

    Uses the standard library rather than adding a BeautifulSoup/lxml
    dependency for what is a small, well-shaped input: MinerU emits plain
    `<table><tr><td>...` with optional `colspan`/`rowspan`. Text inside a
    cell is flattened (MinerU puts line breaks inside cells for wrapped
    content); nested markup is reduced to its text.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[dict[str, Any]]] = []
        self._row: list[dict[str, Any]] | None = None
        self._cell: dict[str, Any] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th"):
            if self._row is None:  # a cell outside any <tr> — tolerate it
                self._row = []
            a = {k: v for k, v in attrs}
            self._cell = {
                "text": [],
                "row_span": _positive_int(a.get("rowspan"), 1),
                "col_span": _positive_int(a.get("colspan"), 1),
                "is_header": tag == "th",
            }

    def handle_endtag(self, tag: str) -> None:
        if tag in ("td", "th") and self._cell is not None:
            text = " ".join("".join(self._cell["text"]).split())
            self._cell["text"] = text
            if self._row is not None:
                self._row.append(self._cell)
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell["text"].append(data)

    def close(self) -> None:  # tolerate an unclosed final <tr>
        super().close()
        if self._cell is not None and self._row is not None:
            self._cell["text"] = " ".join("".join(self._cell["text"]).split())
            self._row.append(self._cell)
            self._cell = None
        if self._row:
            self.rows.append(self._row)
            self._row = None


def _positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(str(value))
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 1 else default


def parse_html_table(
    html: str, *, table_id: str, page_number: int | None = None,
    bbox: BBox | None = None, source_backend: str = "mineru_vl",
) -> Table | None:
    """Convert one `<table>` HTML string into a canonical `Table`.

    Honours `colspan`/`rowspan` by walking an occupancy grid, so a spanned
    cell lands at its true row/col rather than being shifted left by
    however many cells the rows above it span into. Returns None when the
    HTML contains no cells at all — a caller should treat that as "this
    source produced no candidate", not as an empty table.
    """
    parser = _TableHTMLParser()
    parser.feed(html or "")
    parser.close()
    if not parser.rows:
        return None

    occupied: set[tuple[int, int]] = set()
    cells: list[Cell] = []
    max_row = -1
    max_col = -1
    for r_idx, row in enumerate(parser.rows):
        c_idx = 0
        for raw in row:
            while (r_idx, c_idx) in occupied:
                c_idx += 1
            row_span, col_span = raw["row_span"], raw["col_span"]
            cells.append(
                Cell(
                    row=r_idx, col=c_idx, row_span=row_span, col_span=col_span,
                    text=raw["text"], is_header=raw["is_header"],
                )
            )
            for dr in range(row_span):
                for dc in range(col_span):
                    occupied.add((r_idx + dr, c_idx + dc))
            max_row = max(max_row, r_idx + row_span - 1)
            max_col = max(max_col, c_idx + col_span - 1)
            c_idx += col_span

    if not cells:
        return None
    return Table(
        id=table_id, bbox=bbox, page_number=page_number,
        n_rows=max_row + 1, n_cols=max_col + 1, cells=cells,
        source_backend=source_backend, confidence=None,
    )


class MinerUBackend:
    name = "mineru"

    def is_available(self) -> bool:
        return is_available()

    def convert(self, path: Path, config: Any) -> Document:
        detail = (
            "the full `mineru` package is not installed in this environment"
            if not is_available()
            else "whole-document conversion is not implemented for this backend yet"
        )
        extra = (
            " Note: `mineru-vl-utils` IS importable here, so MinerU2.5 is usable as a *table "
            "candidate source* via MinerUVLTableBackend.native_tables() — it is only "
            "whole-document `convert()` that is unavailable."
            if is_vl_available()
            else ""
        )
        raise BackendUnavailableError(
            f"MinerU whole-document backend unavailable: {detail}. "
            "Install with `pip install -e '.[mineru]'` after verifying the current "
            f"package name/version and model download size upstream — see docs/backends.md.{extra}"
        )


class MinerUVLTableBackend:
    """MinerU2.5 as an additional *table candidate source*.

    Exposes `native_tables(page)`, the same hook
    `pipelines/base._gather_extra_table_candidates` already looks for, so
    the existing N-way composition consumes it unchanged.

    The model is loaded lazily on first use and cached on the instance —
    it is ~2.3 GB on disk and takes ~26 s to load on CPU, so a caller
    should hold one instance for a whole run rather than per page.
    """

    name = "mineru_vl"

    def __init__(self, device: str = "cpu", model_id: str = DEFAULT_MINERU_VL_MODEL) -> None:
        self.device = device
        self.model_id = model_id
        self._client = None

    def is_available(self) -> bool:
        return is_vl_available()

    def _lazy_load(self):
        if self._client is not None:
            return self._client
        if not self.is_available():
            raise BackendUnavailableError(
                "mineru-vl-utils/transformers/torch are not all importable — install with "
                "`pip install 'mineru-vl-utils[transformers]'`. See docs/sota_comparison.md."
            )
        import torch
        from mineru_vl_utils import MinerUClient
        from transformers import AutoModelForImageTextToText, AutoProcessor

        # float32 rather than the checkpoint's native bfloat16: CPU bf16
        # support is uneven across torch builds, and this backend's whole
        # point is running where no usable CUDA device exists.
        dtype = torch.float32 if self.device == "cpu" else torch.bfloat16
        model = AutoModelForImageTextToText.from_pretrained(
            self.model_id, dtype=dtype, device_map=self.device,
        ).eval()
        processor = AutoProcessor.from_pretrained(self.model_id, use_fast=True)
        self._client = MinerUClient(backend="transformers", model=model, processor=processor)
        return self._client

    def native_tables(self, page: PageInput) -> list[Table]:
        """Every table MinerU finds on this page, as canonical `Table`s.

        Takes the whole page image deliberately — see this module's
        docstring for the measurement showing a pre-cropped region makes
        MinerU *lose* tables its own layout stage would otherwise find.
        """
        if page.image_path is None:
            return []
        from PIL import Image

        client = self._lazy_load()
        with Image.open(page.image_path) as raw:
            image = raw.convert("RGB")
        width, height = image.size

        tables: list[Table] = []
        for idx, block in enumerate(client.two_step_extract(image)):
            if _block_field(block, "type") != "table":
                continue
            content = _block_field(block, "content") or ""
            table = parse_html_table(
                content,
                table_id=f"p{page.page_index}-mineru-t{idx}",
                page_number=page.page_index + 1,
                bbox=_bbox_from_mineru(_block_field(block, "bbox"), width, height),
            )
            if table is not None:
                tables.append(table)
        return tables


def _block_field(block: Any, field: str) -> Any:
    if isinstance(block, dict):
        return block.get(field)
    return getattr(block, field, None)


def _bbox_from_mineru(bbox: Any, width: float, height: float) -> BBox | None:
    """MinerU returns page-relative [x0, y0, x1, y1] in 0..1; the canonical
    IR uses absolute pixels in the page's own coordinate space."""
    if not bbox or len(bbox) != 4:
        return None
    try:
        x0, y0, x1, y1 = (float(v) for v in bbox)
    except (TypeError, ValueError):
        return None
    return BBox(
        x0=min(x0, x1) * width, y0=min(y0, y1) * height,
        x1=max(x0, x1) * width, y1=max(y0, y1) * height,
    )
