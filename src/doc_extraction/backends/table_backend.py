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
from dataclasses import dataclass
from time import perf_counter

from doc_extraction.pipelines.base import PageInput, Region, TableResult
from doc_extraction.schemas.element import BBox
from doc_extraction.schemas.table import Cell, Table

DETECTION_MODEL_ID = "microsoft/table-transformer-detection"
STRUCTURE_MODEL_ID = "microsoft/table-transformer-structure-recognition"

_DETECTION_THRESHOLD = 0.7
_STRUCTURE_THRESHOLD = 0.6


@dataclass
class CropCounterfactualResult:
    """Experimental evidence from one explicitly supplied region crop.

    This is deliberately separate from :class:`TableResult`: production's
    region path treats the layout region as the table box and only performs
    structure recognition.  Research needs to observe both that faithful
    path and what the detector would say about the same pixels, without
    changing production routing or ownership.
    """

    detected_boxes: list[BBox]
    forced_crop_table: Table | None
    detector_tables: list[Table]


@dataclass(frozen=True)
class _DetectedTableBox:
    bbox: BBox
    score: float | None


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
        extract_start = perf_counter()
        specialist_metadata = {
            "detector_model_id": DETECTION_MODEL_ID,
            "structure_model_id": STRUCTURE_MODEL_ID,
            "detector_threshold": _DETECTION_THRESHOLD,
            "structure_threshold": _STRUCTURE_THRESHOLD,
            "device": self.device,
        }
        if not self.is_available():
            result = TableResult(
                tables=[], backend=self.name, warnings=["backend unavailable — see docs/backends.md"]
            )
            telemetry = page.telemetry
            if telemetry is not None:
                telemetry.record_not_invoked(
                    page=page,
                    backend_name=self.name,
                    reason="backend_unavailable",
                    regions=regions,
                    page_regions=page.telemetry_page_regions,
                    page_region_count=page.telemetry_page_region_count,
                    runtime_seconds=perf_counter() - extract_start,
                    specialist_metadata=specialist_metadata,
                )
            return result
        if page.image_path is None:
            result = TableResult(tables=[], backend=self.name, warnings=["no rendered image for this page"])
            telemetry = page.telemetry
            if telemetry is not None:
                telemetry.record_not_invoked(
                    page=page,
                    backend_name=self.name,
                    reason="no_rendered_image",
                    regions=regions,
                    page_regions=page.telemetry_page_regions,
                    page_region_count=page.telemetry_page_region_count,
                    runtime_seconds=perf_counter() - extract_start,
                    specialist_metadata=specialist_metadata,
                )
            return result

        from PIL import Image

        try:
            self._lazy_load()
        except Exception as exc:
            if telemetry is not None:
                telemetry.record_invocation(
                    page=page,
                    backend_name=self.name,
                    invocation_mode="NOT_INVOKED",
                    reason="model_load_failure",
                    regions=regions,
                    page_regions=page.telemetry_page_regions,
                    page_region_count=page.telemetry_page_region_count,
                    specialist_calls=[
                        {
                            "stage": "model_load",
                            "mode": "NOT_INVOKED",
                            "status": "error",
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    ],
                    warnings=[],
                    errors=[f"{type(exc).__name__}: {exc}"],
                    output_tables=[],
                    runtime_seconds=perf_counter() - extract_start,
                    specialist_metadata=specialist_metadata,
                )
            raise
        image = Image.open(page.image_path).convert("RGB")

        table_boxes = [r.bbox for r in regions if r.label.lower() == "table"]
        telemetry = page.telemetry
        mode = "LABELLED_CROP" if table_boxes else "PAGE_WIDE"
        reason = "layout_table_region_present" if table_boxes else "no_table_labelled_region"
        specialist_calls: list[dict] = []
        detector_boxes: list[_DetectedTableBox] = []
        tables: list[Table] = []
        warnings: list[str] = []
        if not table_boxes:
            detector_start = perf_counter()
            try:
                detector_boxes = self._detect_tables_with_scores(image)
            except Exception as exc:
                specialist_calls.append(
                    {
                        "stage": "detector",
                        "mode": "PAGE_WIDE",
                        "status": "error",
                        "runtime_seconds": perf_counter() - detector_start,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
                if telemetry is not None:
                    telemetry.record_invocation(
                        page=page,
                        backend_name=self.name,
                        invocation_mode="PAGE_WIDE",
                        reason=reason,
                        regions=regions,
                        page_regions=page.telemetry_page_regions,
                        page_region_count=page.telemetry_page_region_count,
                        specialist_calls=specialist_calls,
                        warnings=warnings,
                        errors=[f"{type(exc).__name__}: {exc}"],
                        output_tables=tables,
                        runtime_seconds=perf_counter() - extract_start,
                        specialist_metadata=specialist_metadata,
                    )
                raise
            specialist_calls.append(
                {
                    "stage": "detector",
                    "mode": "PAGE_WIDE",
                    "status": "success",
                    "runtime_seconds": perf_counter() - detector_start,
                    "boxes": [
                        {"bbox": candidate.bbox.model_dump(), "score": candidate.score}
                        for candidate in detector_boxes
                    ],
                }
            )
            table_boxes = [candidate.bbox for candidate in detector_boxes]

        for i, bbox in enumerate(table_boxes):
            crop = image.crop((bbox.x0, bbox.y0, bbox.x1, bbox.y1))
            if crop.width < 10 or crop.height < 10:
                warnings.append(f"table region {i} too small to process ({crop.width}x{crop.height})")
                specialist_calls.append(
                    {
                        "stage": "structure",
                        "mode": mode,
                        "candidate_index": i,
                        "status": "skipped_too_small",
                        "crop_bbox": bbox.model_dump(),
                    }
                )
                continue
            structure_start = perf_counter()
            try:
                table = self._recognize_structure(crop, bbox, page.page_index, table_id=f"p{page.page_index}-t{i}")
            except Exception as exc:
                specialist_calls.append(
                    {
                        "stage": "structure",
                        "mode": mode,
                        "candidate_index": i,
                        "status": "error",
                        "runtime_seconds": perf_counter() - structure_start,
                        "crop_bbox": bbox.model_dump(),
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
                if telemetry is not None:
                    telemetry.record_invocation(
                        page=page,
                        backend_name=self.name,
                        invocation_mode=mode,
                        reason=reason,
                        regions=regions,
                        page_regions=page.telemetry_page_regions,
                        page_region_count=page.telemetry_page_region_count,
                        supplied_crop_bboxes=table_boxes,
                        specialist_calls=specialist_calls,
                        warnings=warnings,
                        errors=[f"{type(exc).__name__}: {exc}"],
                        output_tables=tables,
                        runtime_seconds=perf_counter() - extract_start,
                        specialist_metadata=specialist_metadata,
                    )
                raise
            specialist_calls.append(
                {
                    "stage": "structure",
                    "mode": mode,
                    "candidate_index": i,
                    "status": "valid_structure" if table is not None else "no_structure",
                    "runtime_seconds": perf_counter() - structure_start,
                    "crop_bbox": bbox.model_dump(),
                    "table_id": table.id if table is not None else None,
                }
            )
            if table is not None:
                tables.append(table)
            else:
                warnings.append(f"structure recognition found no row/column grid for table region {i}")

        result = TableResult(tables=tables, backend=self.name, warnings=warnings)
        if telemetry is not None:
            telemetry.record_invocation(
                page=page,
                backend_name=self.name,
                invocation_mode=mode,
                reason=reason,
                regions=regions,
                page_regions=page.telemetry_page_regions,
                page_region_count=page.telemetry_page_region_count,
                supplied_crop_bboxes=table_boxes if mode == "LABELLED_CROP" else [],
                specialist_calls=specialist_calls,
                warnings=warnings,
                errors=[],
                output_tables=tables,
                runtime_seconds=perf_counter() - extract_start,
                specialist_metadata=specialist_metadata,
            )
        return result

    def extract_crop_counterfactual(
        self, page: PageInput, crop_bbox: BBox, table_id_prefix: str = "counterfactual"
    ) -> CropCounterfactualResult:
        """Run a non-production, same-crop Table Transformer probe.

        The forced-crop table exactly mirrors ``extract`` when the layout
        stage supplies a table-labelled region.  ``detected_boxes`` and
        ``detector_tables`` are additive observability: they reveal whether
        the detection model independently finds a table inside those same
        pixels.  No page, region, or production result is modified.
        """
        if not self.is_available():
            raise RuntimeError("Table Transformer backend is unavailable")
        if page.image_path is None:
            raise ValueError("counterfactual crop requires a rendered image")

        from PIL import Image

        self._lazy_load()
        with Image.open(page.image_path) as source:
            image = source.convert("RGB")
        crop = image.crop((crop_bbox.x0, crop_bbox.y0, crop_bbox.x1, crop_bbox.y1))
        if crop.width < 10 or crop.height < 10:
            raise ValueError(f"counterfactual crop is too small: {crop.width}x{crop.height}")

        # This is the exact production region-path operation: structure
        # recognition over the supplied region, not an inferred detector box.
        forced_crop_table = self._recognize_structure(
            crop, crop_bbox, page.page_index, table_id=f"{table_id_prefix}-forced"
        )

        local_boxes = self._detect_tables(crop)
        detected_boxes = [
            BBox(
                x0=crop_bbox.x0 + box.x0,
                y0=crop_bbox.y0 + box.y0,
                x1=crop_bbox.x0 + box.x1,
                y1=crop_bbox.y0 + box.y1,
            )
            for box in local_boxes
        ]
        detector_tables: list[Table] = []
        for i, (local_box, page_box) in enumerate(zip(local_boxes, detected_boxes)):
            detected_crop = crop.crop((local_box.x0, local_box.y0, local_box.x1, local_box.y1))
            if detected_crop.width < 10 or detected_crop.height < 10:
                continue
            table = self._recognize_structure(
                detected_crop, page_box, page.page_index, table_id=f"{table_id_prefix}-detected-{i}"
            )
            if table is not None:
                detector_tables.append(table)
        return CropCounterfactualResult(
            detected_boxes=detected_boxes,
            forced_crop_table=forced_crop_table,
            detector_tables=detector_tables,
        )

    def _detect_tables(self, image) -> list[BBox]:
        return [candidate.bbox for candidate in self._detect_tables_with_scores(image)]

    def _detect_tables_with_scores(self, image) -> list[_DetectedTableBox]:
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
        scores = results.get("scores", [])
        return [
            _DetectedTableBox(
                bbox=BBox(x0=float(box[0]), y0=float(box[1]), x1=float(box[2]), y1=float(box[3])),
                score=float(scores[index]) if index < len(scores) else None,
            )
            for index, box in enumerate(results["boxes"])
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
