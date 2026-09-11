"""Additive telemetry for the production table-specialist boundary.

The baseline pipeline does not need telemetry in order to run.  An optional
``TableTelemetryRecorder`` is passed explicitly through the page input when a
research run needs to observe the table-specialist decision.  Records are
kept in memory until the caller writes one complete payload atomically; a
partially written JSON file is therefore never a valid completed run.

This module deliberately contains no model or pipeline imports.  It is safe to
import in the lightweight core package and its records are plain JSON data so
that later analyses do not need to re-run inference.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Any


TELEMETRY_SCHEMA_VERSION = "table-invocation-1"
INVOCATION_MODES = ("PAGE_WIDE", "LABELLED_CROP", "NOT_INVOKED")


def _bbox_payload(bbox: Any) -> dict[str, float] | None:
    if bbox is None:
        return None
    return {
        "x0": float(bbox.x0),
        "y0": float(bbox.y0),
        "x1": float(bbox.x1),
        "y1": float(bbox.y1),
    }


def bbox_metrics(bbox: Any, page_width: float, page_height: float) -> dict[str, float | None]:
    """Return deterministic geometry covariates for a region or crop."""
    width = max(0.0, float(bbox.x1) - float(bbox.x0))
    height = max(0.0, float(bbox.y1) - float(bbox.y0))
    area = width * height
    page_area = max(0.0, float(page_width) * float(page_height))
    return {
        "area_fraction": area / page_area if page_area else None,
        "aspect_ratio": width / height if height else None,
    }


def bbox_overlap_metrics(first: Any, second: Any) -> dict[str, float]:
    """Return IoU and directional intersection fractions for two boxes."""
    ix0 = max(float(first.x0), float(second.x0))
    iy0 = max(float(first.y0), float(second.y0))
    ix1 = min(float(first.x1), float(second.x1))
    iy1 = min(float(first.y1), float(second.y1))
    intersection = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
    first_area = max(0.0, float(first.x1) - float(first.x0)) * max(0.0, float(first.y1) - float(first.y0))
    second_area = max(0.0, float(second.x1) - float(second.x0)) * max(0.0, float(second.y1) - float(second.y0))
    union = first_area + second_area - intersection
    return {
        "iou": intersection / union if union else 0.0,
        "intersection_over_first": intersection / first_area if first_area else 0.0,
        "intersection_over_second": intersection / second_area if second_area else 0.0,
    }


def _region_payload(
    region: Any,
    index: int,
    page_width: float,
    page_height: float,
    ocr_result: Any | None = None,
) -> dict[str, Any]:
    label = str(region.label)
    bbox = _bbox_payload(region.bbox)
    ocr_tokens = list(getattr(ocr_result, "tokens", []) or [])
    child_tokens = [
        token
        for token in ocr_tokens
        if region.bbox.x0 <= (token.bbox.x0 + token.bbox.x1) / 2 <= region.bbox.x1
        and region.bbox.y0 <= (token.bbox.y0 + token.bbox.y1) / 2 <= region.bbox.y1
    ]
    return {
        "region_index": index,
        "raw_region_label": label,
        # The production code has no independent role-normalization stage at
        # this boundary.  Lower-casing is recorded explicitly as the current
        # normalized-role convention, rather than implying a richer ontology.
        "normalized_role": label.strip().lower(),
        "confidence": region.confidence,
        "source_id": region.source_id,
        "bbox": bbox,
        "geometry": bbox_metrics(region.bbox, page_width, page_height),
        "ocr_child_count": len(child_tokens) if ocr_result is not None else None,
        "ocr_child_chars": (
            sum(len(str(token.text or "")) for token in child_tokens)
            if ocr_result is not None
            else None
        ),
    }


def _table_payload(table: Any) -> dict[str, Any]:
    return {
        "id": table.id,
        "bbox": _bbox_payload(table.bbox),
        "page_number": table.page_number,
        "n_rows": table.n_rows,
        "n_cols": table.n_cols,
        "cell_count": len(table.cells),
        "source_backend": table.source_backend,
        "confidence": table.confidence,
        "cells": [
            {
                "row": cell.row,
                "col": cell.col,
                "row_span": cell.row_span,
                "col_span": cell.col_span,
                "bbox": _bbox_payload(cell.bbox),
                "is_header": cell.is_header,
                "confidence": cell.confidence,
            }
            for cell in table.cells
        ],
    }


@dataclass
class TableTelemetryRecorder:
    """Explicit per-run collector for table invocation and ownership facts.

    ``context`` should contain only facts known before treatment.  The
    recorder also accepts post-extraction ownership events, but those are
    stored as a separate record kind and cannot accidentally become selector
    features without an explicit analysis step.
    """

    experiment_id: str
    run_id: str
    context: dict[str, Any] = field(default_factory=dict)
    records: list[dict[str, Any]] = field(default_factory=list)
    _next_sequence: int = 0

    def bind_document(
        self,
        *,
        document_id: str,
        input_sha256: str,
        route: str,
        device: str,
        backend: str = "baseline",
    ) -> None:
        """Attach run facts known by ``process_file`` before page execution."""
        self.context.update(
            {
                "document_id": document_id,
                "input_sha256": input_sha256,
                "route": route,
                "device": device,
                "pipeline_backend": backend,
            }
        )

    def _id(self, page_index: int, kind: str) -> str:
        value = f"{self.run_id}:{kind}:p{page_index}:n{self._next_sequence:06d}"
        self._next_sequence += 1
        return value

    def record_not_invoked(
        self,
        *,
        page: Any,
        backend_name: str,
        reason: str,
        route: str | None = None,
        regions: list[Any] | None = None,
        page_regions: list[Any] | None = None,
        page_region_count: int | None = None,
        runtime_seconds: float | None = None,
        specialist_metadata: Mapping[str, Any] | None = None,
    ) -> str:
        """Record a decision where the table specialist was not called."""
        return self.record_invocation(
            page=page,
            backend_name=backend_name,
            invocation_mode="NOT_INVOKED",
            reason=reason,
            route=route,
            regions=regions or [],
            specialist_calls=[],
            warnings=[],
            errors=[],
            output_tables=[],
            page_regions=page_regions,
            page_region_count=page_region_count,
            runtime_seconds=runtime_seconds,
            specialist_metadata=specialist_metadata,
        )

    def record_invocation(
        self,
        *,
        page: Any,
        backend_name: str,
        invocation_mode: str,
        reason: str,
        route: str | None = None,
        regions: list[Any],
        specialist_calls: list[dict[str, Any]],
        warnings: list[str],
        errors: list[str],
        output_tables: list[Any],
        supplied_crop_bboxes: list[Any] | None = None,
        page_regions: list[Any] | None = None,
        page_region_count: int | None = None,
        runtime_seconds: float | None = None,
        specialist_metadata: Mapping[str, Any] | None = None,
    ) -> str:
        if invocation_mode not in INVOCATION_MODES:
            raise ValueError(f"unknown table invocation mode: {invocation_mode!r}")
        invocation_id = self._id(page.page_index, "table")
        width = float(page.width)
        height = float(page.height)
        all_regions = page_regions if page_regions is not None else regions
        payload = {
            "record_kind": "specialist_invocation",
            "schema_version": TELEMETRY_SCHEMA_VERSION,
            "invocation_id": invocation_id,
            "experiment_id": self.experiment_id,
            "run_id": self.run_id,
            **self.context,
            "route": route if route is not None else self.context.get("route"),
            "page_index": page.page_index,
            "page": {
                "width": width,
                "height": height,
                "dpi": page.dpi,
                "image_path": str(page.image_path) if page.image_path is not None else None,
            },
            "backend_name": backend_name,
            "invocation_mode": invocation_mode,
            "reason": reason,
            "runtime_seconds": runtime_seconds,
            "region_count": len(regions),
            "page_region_count": page_region_count if page_region_count is not None else len(all_regions),
            "regions": [
                _region_payload(
                    region,
                    i,
                    width,
                    height,
                    getattr(page, "telemetry_ocr_result", None),
                )
                for i, region in enumerate(all_regions)
            ],
            "supplied_crop_bboxes": [_bbox_payload(bbox) for bbox in (supplied_crop_bboxes or [])],
            "specialist": dict(specialist_metadata or {}),
            "specialist_calls": specialist_calls,
            "output": {
                "table_count": len(output_tables),
                "tables": [_table_payload(table) for table in output_tables],
                "warnings": list(warnings),
                "errors": list(errors),
            },
        }
        self.records.append(payload)
        return invocation_id

    def record_page_assembly(
        self,
        *,
        page: Any,
        layout_result: Any,
        table_result: Any | None,
        route: str | None = None,
    ) -> str:
        """Record post-specialist ownership and final-IR facts separately."""
        event_id = self._id(page.index, "assembly")
        tables = list(page.tables)
        table_ids = {table.id for table in tables}
        elements = list(page.elements)
        table_elements = [element for element in elements if element.table_id is not None]
        owners_by_table: dict[str, list[str]] = {table_id: [] for table_id in table_ids}
        for element in table_elements:
            if element.table_id in owners_by_table:
                owners_by_table[element.table_id].append(element.id)

        region_ownership: list[dict[str, Any]] = []
        for index, region in enumerate(layout_result.regions):
            candidate_table_ids = [
                table.id
                for table in tables
                if table.bbox is not None and table.bbox.iou(region.bbox) > 0.1
            ]
            owner_ids = [
                element.table_id
                for element in table_elements
                if element.order_index == index and element.table_id is not None
            ]
            region_ownership.append(
                {
                    "region_index": index,
                    "raw_region_label": region.label,
                    "bbox": _bbox_payload(region.bbox),
                    "candidate_table_ids": candidate_table_ids,
                    "candidate_table_overlaps": [
                        {
                            "table_id": table.id,
                            **bbox_overlap_metrics(table.bbox, region.bbox),
                        }
                        for table in tables
                        if table.bbox is not None
                    ],
                    "chosen_table_ids": owner_ids,
                    "collision_status": (
                        "duplicate_owner"
                        if len(owner_ids) > 1 or any(len(owners) > 1 for owners in owners_by_table.values())
                        else "unique_or_unowned"
                    ),
                }
            )

        source_invocations = [
            record["invocation_id"]
            for record in self.records
            if record.get("record_kind") == "specialist_invocation"
            and record.get("page_index") == page.index
        ]
        payload = {
            "record_kind": "page_assembly",
            "schema_version": TELEMETRY_SCHEMA_VERSION,
            "assembly_id": event_id,
            "experiment_id": self.experiment_id,
            "run_id": self.run_id,
            **self.context,
            "route": route if route is not None else self.context.get("route"),
            "page_index": page.index,
            "source_invocation_ids": source_invocations,
            "ownership": {
                "region_ownership": region_ownership,
                "owners_by_table": owners_by_table,
                "unowned_table_ids": sorted(table_id for table_id, owners in owners_by_table.items() if not owners),
                "table_element_count": len(table_elements),
                "duplicate_table_ids": sorted(
                    table_id for table_id, owners in owners_by_table.items() if len(owners) > 1
                ),
            },
            "output": {
                "table_count": len(tables),
                "cell_count": sum(len(table.cells) for table in tables),
                "final_ir_table_element_ids": [element.id for element in table_elements],
                "final_ir_element_ids": [element.id for element in elements],
                "reading_order": list(page.reading_order),
                "page_notes": list(page.notes),
                "table_result_warnings": list(table_result.warnings) if table_result else [],
            },
        }
        self.records.append(payload)
        return event_id

    def payload(self, *, status: str, error: str | None = None) -> dict[str, Any]:
        return {
            "schema_version": TELEMETRY_SCHEMA_VERSION,
            "experiment_id": self.experiment_id,
            "run_id": self.run_id,
            "status": status,
            "error": error,
            "context": dict(self.context),
            "record_count": len(self.records),
            "records": list(self.records),
        }

    def write_atomic(self, path: Path, *, status: str, error: str | None = None) -> None:
        """Write one complete telemetry payload using replace-on-success."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(self.payload(status=status, error=error), handle, indent=2, ensure_ascii=False)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


def stable_config_hash(config_snapshot: Mapping[str, Any]) -> str:
    """Hash a JSON-serializable config snapshot for provenance."""
    encoded = json.dumps(config_snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def timed_call(function: Any, *args: Any, **kwargs: Any) -> tuple[Any, float]:
    """Call a specialist stage while recording an elapsed wall-clock value."""
    start = perf_counter()
    result = function(*args, **kwargs)
    return result, perf_counter() - start
