"""Table Transformer (microsoft/table-transformer-*) TableBackend.

Two HF models, run in sequence:
  1. table-transformer-detection: finds table bounding boxes on a page.
     Skipped when `regions` (from the layout stage) already names table
     areas — the model still runs standalone if layout didn't run/find one.
  2. table-transformer-structure-recognition: rows/columns/headers *within*
     a detected table crop.

This backend only produces table geometry (bbox + row/col grid + spans),
not cell text — Table Transformer doesn't read text. Cell text is filled in
by the caller (pipelines/base.run_scanned_page_pipeline) by matching OCR
tokens to each cell's bbox, the same way region text is assembled elsewhere.
That keeps this backend's job identical across whether it's fed OCR'd
scanned pages or (in a future extension) digital PDF pages with a native
text layer.

CPU-runnable; ~115M + ~28M parameters. MIT-licensed weights. See
docs/backends.md for install/timing notes.
"""
from __future__ import annotations

import importlib.util

from doc_extraction.pipelines.base import PageInput, Region, TableResult
from doc_extraction.schemas.element import BBox
from doc_extraction.schemas.table import Cell, Table

DETECTION_MODEL_ID = "microsoft/table-transformer-detection"
STRUCTURE_MODEL_ID = "microsoft/table-transformer-structure-recognition"

_DETECTION_THRESHOLD = 0.7
_STRUCTURE_THRESHOLD = 0.6


def is_available() -> bool:
    return (
        importlib.util.find_spec("transformers") is not None
        and importlib.util.find_spec("torch") is not None
    )


class TableTransformerBackend:
    name = "table_transformer"

    def __init__(self, device: str = "cpu") -> None:
        self.device = device
        self._detection_model = None
        self._detection_processor = None
        self._structure_model = None
        self._structure_processor = None

    def is_available(self) -> bool:
        return is_available()

    def _lazy_load(self) -> None:
        if self._detection_model is not None:
            return
        from transformers import AutoImageProcessor, TableTransformerForObjectDetection

        self._detection_processor = AutoImageProcessor.from_pretrained(DETECTION_MODEL_ID)
        self._detection_model = (
            TableTransformerForObjectDetection.from_pretrained(DETECTION_MODEL_ID)
            .to(self.device)
            .eval()
        )
        self._structure_processor = AutoImageProcessor.from_pretrained(STRUCTURE_MODEL_ID)
        self._structure_model = (
            TableTransformerForObjectDetection.from_pretrained(STRUCTURE_MODEL_ID)
            .to(self.device)
            .eval()
        )

    def extract(self, page: PageInput, regions: list[Region]) -> TableResult:
        if not self.is_available():
            return TableResult(tables=[], backend=self.name, warnings=["backend unavailable — see docs/backends.md"])
        if page.image_path is None:
            return TableResult(tables=[], backend=self.name, warnings=["no rendered image for this page"])

        from PIL import Image

        self._lazy_load()
        image = Image.open(page.image_path).convert("RGB")

        table_boxes = [r.bbox for r in regions if r.label.lower() == "table"]
        if not table_boxes:
            table_boxes = self._detect_tables(image)

        tables: list[Table] = []
        warnings: list[str] = []
        for i, bbox in enumerate(table_boxes):
            crop = image.crop((bbox.x0, bbox.y0, bbox.x1, bbox.y1))
            if crop.width < 10 or crop.height < 10:
                warnings.append(f"table region {i} too small to process ({crop.width}x{crop.height})")
                continue
            table = self._recognize_structure(crop, bbox, page.page_index, table_id=f"p{page.page_index}-t{i}")
            if table is not None:
                tables.append(table)
            else:
                warnings.append(f"structure recognition found no row/column grid for table region {i}")

        return TableResult(tables=tables, backend=self.name, warnings=warnings)

    def _detect_tables(self, image) -> list[BBox]:
        import torch

        inputs = self._detection_processor(images=image, return_tensors="pt")
        # The models were moved to self.device in _lazy_load; their inputs must
        # follow, or torch raises "Expected all tensors to be on the same
        # device" the moment device is anything but cpu.
        inputs = {k: v.to(self.device) for k, v in inputs.items()}
        with torch.no_grad():
            outputs = self._detection_model(**inputs)
        target_sizes = torch.tensor([image.size[::-1]])
        results = self._detection_processor.post_process_object_detection(
            outputs, threshold=_DETECTION_THRESHOLD, target_sizes=target_sizes
        )[0]
        return [
            BBox(x0=float(box[0]), y0=float(box[1]), x1=float(box[2]), y1=float(box[3]))
            for box in results["boxes"]
        ]

    def _recognize_structure(self, crop_image, table_bbox: BBox, page_index: int, table_id: str) -> Table | None:
        import torch

        inputs = self._structure_processor(images=crop_image, return_tensors="pt")
        inputs = {k: v.to(self.device) for k, v in inputs.items()}  # see _detect_tables
        with torch.no_grad():
            outputs = self._structure_model(**inputs)
        target_sizes = torch.tensor([crop_image.size[::-1]])
        results = self._structure_processor.post_process_object_detection(
            outputs, threshold=_STRUCTURE_THRESHOLD, target_sizes=target_sizes
        )[0]

        id2label = self._structure_model.config.id2label
        rows: list[tuple[float, float]] = []
        cols: list[tuple[float, float]] = []
        header_rows: list[tuple[float, float]] = []

        for label_id, box in zip(results["labels"], results["boxes"]):
            label = id2label[int(label_id)]
            x0, y0, x1, y1 = (float(v) for v in box)
            if label == "table row":
                rows.append((y0, y1))
            elif label == "table column":
                cols.append((x0, x1))
            elif label == "table column header":
                header_rows.append((y0, y1))

        if not rows or not cols:
            return None
        rows.sort()
        cols.sort()

        cells: list[Cell] = []
        for r_idx, (ry0, ry1) in enumerate(rows):
            is_header = any(min(ry1, hy1) - max(ry0, hy0) > 0 for hy0, hy1 in header_rows)
            for c_idx, (cx0, cx1) in enumerate(cols):
                cell_bbox = BBox(
                    x0=table_bbox.x0 + cx0,
                    y0=table_bbox.y0 + ry0,
                    x1=table_bbox.x0 + cx1,
                    y1=table_bbox.y0 + ry1,
                )
                cells.append(Cell(row=r_idx, col=c_idx, bbox=cell_bbox, text="", is_header=is_header))

        return Table(
            id=table_id,
            bbox=table_bbox,
            page_number=page_index + 1,
            n_rows=len(rows),
            n_cols=len(cols),
            cells=cells,
            source_backend=self.name,
            confidence=None,
        )
