#!/usr/bin/env python3
"""Run the frozen Experiment 040 crop counterfactual.

The runner consumes the already-frozen 039 baseline artifacts.  It never
reruns layout/OCR, never reads held-out units, and never inserts treatment
tables into the 039 output tree.  Per-unit evidence and telemetry are written
atomically so a CPU interruption can be resumed without losing the previous
attempt.
"""
from __future__ import annotations

import argparse
import copy
import importlib.metadata
import json
import os
import platform
import resource
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
E039 = ROOT / "experiments" / "039_larger_real_corpus"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE))

from protocol import (
    BASELINE_CHECKPOINT,
    CONTROL_KIND,
    EXPERIMENT_ID,
    GT_IOU_MIN,
    INVOCATION_MODES,
    MATERIAL_CONFLICT_IOU,
    OWNER_IOU_MIN,
    TARGET_KIND,
    ProtocolViolation,
    atomic_write_json,
    bbox_dict,
    bbox_equal,
    canonical_json_hash,
    crop_png_bytes,
    iou,
    policy_fires,
    require_development,
    sha256_bytes,
    sha256_file,
    structure_validity,
)

from doc_extraction.backends.table_backend import (
    DETECTION_MODEL_ID,
    STRUCTURE_MODEL_ID,
    TableTransformerBackend,
)
from doc_extraction.pipelines.base import (
    LayoutResult,
    OCRResult,
    OCRToken,
    PageInput,
    Region,
    TableResult,
    _fill_table_cell_text,
    merge_regions_into_page,
)
from doc_extraction.schemas.element import BBox
from doc_extraction.schemas.page import Page
from doc_extraction.schemas.table import Table
from doc_extraction.stages.reading_order import compute_reading_order
from doc_extraction.utils.table_telemetry import TableTelemetryRecorder


def package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def git_head() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_frozen_baseline(unit: dict[str, Any]) -> tuple[Page, LayoutResult, OCRResult, TableResult, dict[str, Any]]:
    """Load only the immutable 039 baseline artifacts for one development unit."""
    require_development(unit)
    run = ROOT / unit["source_run"]
    layout_data = read_json(run / "layout/page-001.json")
    ocr_data = read_json(run / "ocr/page-001.json")
    tables_data = read_json(run / "tables/page-001.json")
    document = read_json(run / "final/document.json")
    page = Page.model_validate(document["pages"][0])
    layout = LayoutResult(
        regions=[
            Region(
                bbox=BBox.model_validate(item["bbox"]),
                label=item["label"],
                confidence=item.get("confidence"),
                source_id=item.get("source_id"),
            )
            for item in layout_data["regions"]
        ],
        backend=layout_data.get("backend", "docling"),
        warnings=list(layout_data.get("warnings", [])),
    )
    ocr = OCRResult(
        tokens=[
            OCRToken(
                text=str(item.get("text", "")),
                bbox=BBox.model_validate(item["bbox"]),
                confidence=item.get("confidence"),
            )
            for item in ocr_data.get("tokens", [])
        ],
        backend=ocr_data.get("backend", "docling"),
        warnings=list(ocr_data.get("warnings", [])),
    )
    tables = TableResult(
        tables=[Table.model_validate(item) for item in tables_data.get("tables", [])],
        backend=tables_data.get("backend", "table_transformer"),
        warnings=list(tables_data.get("warnings", [])),
        spans_by_table=dict(tables_data.get("spans_by_table", {})),
    )
    if not bbox_equal(layout.regions[unit["region_index"]].bbox, unit["region_bbox"]):
        raise ProtocolViolation(f"baseline region bbox changed for {unit['unit_id']}")
    if sha256_file(run / "final/document.json") != unit["source_artifact_sha256"]["final"]:
        raise ProtocolViolation(f"baseline final artifact changed for {unit['unit_id']}")
    metadata = read_json(run / "metadata.json")
    return page, layout, ocr, tables, metadata


def element_payload(element: Any) -> dict[str, Any]:
    payload = element.model_dump(mode="json")
    if payload.get("bbox") is not None:
        payload["bbox"] = bbox_dict(payload["bbox"])
    return payload


def build_treatment_page(
    *,
    baseline_page: Page,
    layout: LayoutResult,
    ocr: OCRResult,
    baseline_tables: TableResult,
    forced_table: Any,
    unit: dict[str, Any],
) -> tuple[Page, dict[str, Any]]:
    """Run the existing merge/reading-order path with one isolated candidate."""
    treatment_region = Region(
        bbox=BBox.model_validate(unit["region_bbox"]),
        label="table",
        confidence=None,
        source_id=f"040-treatment:{unit['unit_id']}",
    )
    treatment_layout = LayoutResult(
        regions=list(layout.regions) + [treatment_region],
        backend=layout.backend,
        warnings=list(layout.warnings),
    )
    combined_tables = TableResult(
        tables=[copy.deepcopy(table) for table in baseline_page.tables] + [forced_table],
        backend="table_transformer_counterfactual",
        warnings=list(baseline_tables.warnings),
    )
    treatment_page = merge_regions_into_page(
        baseline_page.index,
        baseline_page.width,
        baseline_page.height,
        baseline_page.dpi,
        treatment_layout,
        ocr,
        combined_tables,
        None,
    )
    treatment_page.reading_order = compute_reading_order(
        treatment_page.elements, page_width=treatment_page.width or None
    )
    # Preserve the production verification layer for a meaningful final-IR
    # comparison, without writing a canonical 039 artifact.
    from doc_extraction.ingest.verification import verify_document
    # `verify_document` only needs pages.  Apply it to a lightweight object so
    # no fabricated RunMetadata enters the serialized evidence.
    class _DocumentView:
        def __init__(self, pages: list[Page]) -> None:
            self.pages = pages
    verify_document(_DocumentView([treatment_page]))
    synthetic_id = f"p{baseline_page.index}-e{len(layout.regions)}"
    return treatment_page, {
        "synthetic_region_index": len(layout.regions),
        "synthetic_element_id": synthetic_id,
        "treatment_region": treatment_region,
        "combined_table_result": combined_tables,
    }


def serialization_delta(baseline_page: Page, treatment_page: Page, synthetic_element_id: str) -> dict[str, Any]:
    baseline_elements = {element.id: element_payload(element) for element in baseline_page.elements}
    treatment_elements = {
        element.id: element_payload(element)
        for element in treatment_page.elements
        if element.id != synthetic_element_id
    }
    changed = sorted(
        element_id for element_id in baseline_elements
        if baseline_elements[element_id] != treatment_elements.get(element_id)
    )
    missing = sorted(set(baseline_elements) - set(treatment_elements))
    extra = sorted(set(treatment_elements) - set(baseline_elements))
    baseline_order = [item for item in baseline_page.reading_order if item != synthetic_element_id]
    treatment_order = [item for item in treatment_page.reading_order if item != synthetic_element_id]
    return {
        "changed_existing_element_ids": changed,
        "missing_existing_element_ids": missing,
        "unexpected_non_synthetic_element_ids": extra,
        "reading_order_changed": baseline_order != treatment_order,
        "baseline_table_count": len(baseline_page.tables),
        "treatment_table_count": len(treatment_page.tables),
        "baseline_table_element_count": sum(element.table_id is not None for element in baseline_page.elements),
        "treatment_table_element_count": sum(element.table_id is not None for element in treatment_page.elements),
        "baseline_page_hash": canonical_json_hash(baseline_page.model_dump(mode="json")),
        "treatment_page_hash": canonical_json_hash(treatment_page.model_dump(mode="json")),
    }


def ownership_evidence(
    *,
    baseline_page: Page,
    treatment_page: Page,
    forced_table: dict[str, Any],
    synthetic_element_id: str,
) -> dict[str, Any]:
    forced_bbox = forced_table.get("bbox")
    candidate_ids = [
        table["id"]
        for table in treatment_page.model_dump(mode="json")["tables"]
        if forced_bbox is not None and table.get("bbox") is not None
        and iou(table["bbox"], forced_bbox) > OWNER_IOU_MIN
    ]
    synthetic_element = next(
        (element for element in treatment_page.elements if element.id == synthetic_element_id),
        None,
    )
    chosen = synthetic_element.table_id if synthetic_element is not None else None
    existing_overlaps = [
        {"table_id": table.id, "iou": round(iou(forced_bbox, table.bbox), 6)}
        for table in baseline_page.tables
        if forced_bbox is not None and table.bbox is not None and iou(forced_bbox, table.bbox) > 0
    ]
    max_existing = max((item["iou"] for item in existing_overlaps), default=0.0)
    return {
        "candidate_owner_ids": candidate_ids,
        "chosen_owner_id": chosen,
        "owner_candidate_count": len(candidate_ids),
        "unique_intended_owner": bool(chosen == forced_table.get("id") and candidate_ids == [forced_table.get("id")]),
        "existing_production_table_overlaps": existing_overlaps,
        "existing_production_table_max_iou": round(max_existing, 6),
        "material_production_conflict": max_existing > MATERIAL_CONFLICT_IOU,
        "cross_table_overlap_count": sum(item["iou"] > MATERIAL_CONFLICT_IOU for item in existing_overlaps),
        "ownership_resolver": "production_merge_regions_into_page_plus_conservative_040_conflict_gate",
    }


def specialist_call_payload(result: Any) -> list[dict[str, Any]]:
    forced = result.forced_crop_table.model_dump(mode="json") if result.forced_crop_table else None
    calls = [{
        "stage": "structure",
        "mode": "LABELLED_CROP",
        "candidate_index": 0,
        "status": "valid_structure" if forced is not None else "no_structure",
        "table_id": forced.get("id") if forced else None,
        "table_bbox": forced.get("bbox") if forced else None,
        "runtime_seconds": result.stage_timings.get("forced_structure_seconds"),
        "intervention": "exact_frozen_baseline_crop",
    }]
    calls.append({
        "stage": "detector_observation_on_supplied_crop",
        "mode": "LABELLED_CROP",
        "status": "success",
        "runtime_seconds": result.stage_timings.get("crop_detector_seconds"),
        "boxes": [
            {"bbox": box.model_dump(mode="json"), "score": score}
            for box, score in zip(result.detected_boxes, result.detected_scores)
        ],
    })
    for index, table in enumerate(result.detector_tables):
        timings = result.stage_timings.get("detector_structure_seconds", [])
        calls.append({
            "stage": "detector_candidate_structure_observation",
            "mode": "LABELLED_CROP",
            "candidate_index": index,
            "status": "valid_structure",
            "table_id": table.id,
            "table_bbox": table.bbox.model_dump(mode="json") if table.bbox else None,
            "runtime_seconds": timings[index] if index < len(timings) else None,
        })
    return calls


def run_specialist(
    *, unit: dict[str, Any], baseline_page: Page, layout: LayoutResult, ocr: OCRResult,
    baseline_tables: TableResult,
    backend: TableTransformerBackend, population_hash: str, run_id: str,
) -> tuple[dict[str, Any], TableTelemetryRecorder, Page]:
    """Execute treatment without accepting GT as an argument."""
    require_development(unit)
    image_path = E039 / "results" / "doclaynet" / "PNG" / unit["file_name"]
    if sha256_file(image_path) != unit["source_image_sha256"]:
        raise ProtocolViolation(f"source image hash mismatch for {unit['unit_id']}")
    frozen_bbox = bbox_dict(unit["region_bbox"])
    crop_bytes, width, height = crop_png_bytes(image_path, frozen_bbox)
    if {
        "sha256": sha256_bytes(crop_bytes),
        "width": width,
        "height": height,
    } != {
        "sha256": unit["crop"]["sha256"],
        "width": unit["crop"]["width"],
        "height": unit["crop"]["height"],
    }:
        raise ProtocolViolation(f"frozen crop identity mismatch for {unit['unit_id']}")

    page_input = PageInput(
        page_index=baseline_page.index,
        width=baseline_page.width,
        height=baseline_page.height,
        image_path=image_path,
        dpi=baseline_page.dpi,
    )
    page_input.telemetry_page_regions = list(layout.regions)
    page_input.telemetry_page_region_count = len(layout.regions)
    page_input.telemetry_ocr_result = ocr

    recorder = TableTelemetryRecorder(
        experiment_id=EXPERIMENT_ID,
        run_id=run_id,
        context={
            "code_commit": git_head(),
            "baseline_checkpoint": BASELINE_CHECKPOINT,
            "population_hash": population_hash,
            "unit_id": unit["unit_id"],
            "kind": unit["kind"],
            "split": unit["split"],
            "source_image_sha256": unit["source_image_sha256"],
            "treatment_input_bbox": frozen_bbox,
            "feature_contract": "040 feature_manifest.json",
        },
    )
    recorder.bind_document(
        document_id=unit["source_document_id"],
        input_sha256=unit["source_image_sha256"],
        route="image",
        device="cpu",
        backend="counterfactual",
    )
    started = time.perf_counter()
    result = backend.extract_crop_counterfactual(
        page_input, BBox.model_validate(frozen_bbox), table_id_prefix=f"040-{unit['unit_id']}"
    )
    total_runtime = time.perf_counter() - started
    if result.forced_crop_table is None:
        forced_table_result = TableResult(tables=[], backend="table_transformer")
    else:
        forced_table_result = TableResult(tables=[result.forced_crop_table], backend="table_transformer")
        _fill_table_cell_text(forced_table_result, ocr)
    forced = forced_table_result.tables[0] if forced_table_result.tables else None
    if forced is None:
        # Keep an empty table result for the page assembly record, but a real
        # treatment candidate does not exist and therefore cannot be owned.
        treatment_page = copy.deepcopy(baseline_page)
        treatment_page.reading_order = list(baseline_page.reading_order)
        assembly_context = {"synthetic_region_index": len(layout.regions), "synthetic_element_id": None}
    else:
        treatment_page, assembly_context = build_treatment_page(
            baseline_page=baseline_page,
            layout=layout,
            ocr=ocr,
            baseline_tables=baseline_tables,
            forced_table=forced,
            unit=unit,
        )
    mode = "LABELLED_CROP"
    if mode not in INVOCATION_MODES or not forced_table_result.backend:
        raise ProtocolViolation(f"invalid treatment invocation state for {unit['unit_id']}")
    recorder.record_invocation(
        page=page_input,
        backend_name=backend.name,
        invocation_mode=mode,
        reason="040_exact_frozen_baseline_region_crop",
        regions=[Region(bbox=BBox.model_validate(frozen_bbox), label="table", source_id=f"040:{unit['unit_id']}")],
        page_regions=layout.regions,
        page_region_count=len(layout.regions),
        supplied_crop_bboxes=[BBox.model_validate(frozen_bbox)],
        specialist_calls=specialist_call_payload(result),
        warnings=[],
        errors=[],
        output_tables=forced_table_result.tables,
        runtime_seconds=total_runtime,
        specialist_metadata={
            "detector_model_id": DETECTION_MODEL_ID,
            "structure_model_id": STRUCTURE_MODEL_ID,
            "detector_threshold": 0.7,
            "structure_threshold": 0.6,
            "device": "cpu",
            "treatment_mode_contract": "LABELLED_CROP",
        },
    )
    if forced is not None:
        recorder.record_page_assembly(
            page=treatment_page,
            layout_result=LayoutResult(
                regions=list(layout.regions) + [assembly_context["treatment_region"]],
                backend=layout.backend,
            ),
            table_result=assembly_context["combined_table_result"],
            route="image",
        )
    telemetry_path = f"results/raw/{unit['unit_id']}/table_telemetry.json"
    forced_dump = forced.model_dump(mode="json") if forced else None
    return {
        "status": "complete",
        "unit_id": unit["unit_id"],
        "treatment_input": {
            "image_sha256": unit["source_image_sha256"],
            "region_bbox": frozen_bbox,
            "bbox_equal_to_frozen_manifest": True,
            "crop_sha256": unit["crop"]["sha256"],
            "crop_width": unit["crop"]["width"],
            "crop_height": unit["crop"]["height"],
        },
        "specialist": {
            "invocation_mode": mode,
            "detector_boxes": [box.model_dump(mode="json") for box in result.detected_boxes],
            "detector_scores": list(result.detected_scores),
            "forced_crop_table": forced_dump,
            "detector_tables": [table.model_dump(mode="json") for table in result.detector_tables],
            "stage_timings": result.stage_timings,
            "total_runtime_seconds": total_runtime,
        },
        "treatment_page": treatment_page,
        "telemetry": recorder,
        "telemetry_path": telemetry_path,
        "assembly_context": assembly_context,
    }, recorder, treatment_page


def evaluate_post_treatment(
    *, unit: dict[str, Any], baseline_page: Page, treatment: dict[str, Any], treatment_page: Page
) -> dict[str, Any]:
    """Evaluate GT and ownership only after treatment output exists."""
    forced = treatment["specialist"]["forced_crop_table"]
    structure = structure_validity(forced)
    synthetic_id = treatment["assembly_context"].get("synthetic_element_id")
    if forced is None or synthetic_id is None:
        ownership = {
            "candidate_owner_ids": [], "chosen_owner_id": None, "owner_candidate_count": 0,
            "unique_intended_owner": False, "existing_production_table_overlaps": [],
            "existing_production_table_max_iou": 0.0, "material_production_conflict": False,
            "cross_table_overlap_count": 0,
            "ownership_resolver": "no_candidate",
        }
        delta = serialization_delta(baseline_page, treatment_page, "__absent__")
    else:
        ownership = ownership_evidence(
            baseline_page=baseline_page,
            treatment_page=treatment_page,
            forced_table=forced,
            synthetic_element_id=synthetic_id,
        )
        delta = serialization_delta(baseline_page, treatment_page, synthetic_id)
    detector_success = bool(treatment["specialist"]["detector_boxes"])
    tags: list[str] = []
    if detector_success:
        tags.append("detector_success")
    else:
        tags.append("detector_miss")
    if not structure["valid"]:
        tags.append("structure_invalid")
    if ownership["owner_candidate_count"] != 1 or not ownership["unique_intended_owner"]:
        tags.append("ownership_ambiguity")
    if ownership["cross_table_overlap_count"] > 0:
        tags.append("cross_table_contamination")
    if delta["changed_existing_element_ids"] or delta["missing_existing_element_ids"] or delta["reading_order_changed"]:
        tags.append("serialization_damage")
    if unit["kind"] == TARGET_KIND and unit.get("raw_role") not in ("document_index", "picture", "text", "list_item", "code"):
        tags.append("unsupported_role")

    gt_evaluations = []
    for gt in unit.get("linked_gt_tables", []):
        gt_iou = iou(forced["bbox"], gt["bbox"]) if forced and forced.get("bbox") else None
        valid = bool(
            structure["valid"]
            and ownership["unique_intended_owner"]
            and gt_iou is not None
            and gt_iou >= GT_IOU_MIN
            and not ownership["material_production_conflict"]
            and not delta["changed_existing_element_ids"]
            and not delta["missing_existing_element_ids"]
            and not delta["reading_order_changed"]
            and treatment["specialist"]["invocation_mode"] == "LABELLED_CROP"
        )
        gt_evaluations.append({
            "gt_table_id": gt["gt_table_id"],
            "gt_bbox": gt["bbox"],
            "gt_iou": gt_iou,
            "gt_iou_ge_0_3": bool(gt_iou is not None and gt_iou >= GT_IOU_MIN),
            "valid_recovery": valid,
        })
    valid_recovery = any(item["valid_recovery"] for item in gt_evaluations)

    if unit["kind"] == CONTROL_KIND:
        if not structure["valid"]:
            primary = "NO_EFFECT"
        elif delta["changed_existing_element_ids"] or delta["missing_existing_element_ids"] or delta["reading_order_changed"]:
            primary = "DUPLICATION_DAMAGE"
        elif ownership["cross_table_overlap_count"] > 0:
            primary = "CROSS_TABLE_CONTAMINATION"
        elif not ownership["unique_intended_owner"]:
            primary = "OWNERSHIP_CONFLICT"
        else:
            primary = "FALSE_POSITIVE"
    else:
        if valid_recovery:
            primary = "VALID_RECOVERY"
        elif not structure["valid"]:
            primary = "STRUCTURE_INVALID"
        elif ownership["cross_table_overlap_count"] > 0:
            primary = "CROSS_TABLE_CONTAMINATION"
        elif not ownership["unique_intended_owner"]:
            primary = "OWNERSHIP_AMBIGUITY"
        else:
            primary = "GT_IRRELEVANT_OR_NONRECOVERY"
    return {
        "primary_outcome": primary,
        "detector_success": detector_success,
        "structure": structure,
        "ownership": ownership,
        "serialization_delta": delta,
        "gt_evaluations": gt_evaluations,
        "valid_recovery": valid_recovery,
        "failure_tags": sorted(set(tags)),
        "policy_fires": policy_fires(unit["baseline_features"]),
    }


def public_treatment_payload(treatment: dict[str, Any]) -> dict[str, Any]:
    result = dict(treatment)
    result.pop("telemetry", None)
    result.pop("treatment_page", None)
    result.pop("assembly_context", None)
    return result


def run_unit(unit: dict[str, Any], backend: TableTransformerBackend, population_hash: str, phase_root: Path) -> dict[str, Any]:
    require_development(unit)
    started = time.perf_counter()
    try:
        baseline_page, layout, ocr, baseline_tables, _metadata = load_frozen_baseline(unit)
        treatment, recorder, treatment_page = run_specialist(
            unit=unit,
            baseline_page=baseline_page,
            layout=layout,
            ocr=ocr,
            baseline_tables=baseline_tables,
            backend=backend,
            population_hash=population_hash,
            run_id=f"040-{unit['unit_id']}",
        )
        unit_root = phase_root / "raw" / unit["unit_id"]
        recorder.write_atomic(unit_root / "table_telemetry.json", status="complete")
        # Preserve specialist and assembly evidence if a later pure
        # evaluation helper has an engineering defect.
        atomic_write_json(unit_root / "treatment_observed.json", public_treatment_payload(treatment))
        evaluation = evaluate_post_treatment(
            unit=unit,
            baseline_page=baseline_page,
            treatment=treatment,
            treatment_page=treatment_page,
        )
        payload = {
            "status": "complete",
            "unit": unit,
            "treatment": public_treatment_payload(treatment),
            "evaluation": evaluation,
            "provenance": {
                "code_commit": git_head(),
                "baseline_checkpoint": BASELINE_CHECKPOINT,
                "population_hash": population_hash,
                "treatment_commit": git_head(),
                "device": "cpu",
                "runtime_seconds": time.perf_counter() - started,
                "baseline_metadata_sha256": unit["source_artifact_sha256"]["metadata"],
            },
        }
        atomic_write_json(unit_root / "result.json", payload)
        return payload
    except Exception as exc:  # preserve operational/protocol failure evidence
        unit_root = phase_root / "raw" / unit["unit_id"]
        failure = {
            "status": "operational_failure" if not isinstance(exc, ProtocolViolation) else "protocol_violation",
            "unit": unit,
            "error": f"{type(exc).__name__}: {exc}",
            "preserved_treatment_observed": str((phase_root / "raw" / unit["unit_id"] / "treatment_observed.json").relative_to(HERE))
            if (phase_root / "raw" / unit["unit_id"] / "treatment_observed.json").is_file()
            else None,
            "provenance": {
                "code_commit": git_head(),
                "baseline_checkpoint": BASELINE_CHECKPOINT,
                "population_hash": population_hash,
                "device": "cpu",
                "runtime_seconds": time.perf_counter() - started,
            },
        }
        atomic_write_json(unit_root / "result.json", failure)
        return failure


def runtime_metadata(manifest: dict[str, Any], phase: str, protocol_hash: str, feature_hash: str) -> dict[str, Any]:
    import torch

    return {
        "experiment": EXPERIMENT_ID,
        "phase": phase,
        "status": "running",
        "code_commit": git_head(),
        "baseline_checkpoint": BASELINE_CHECKPOINT,
        "population_hash": manifest["population_hash"],
        "protocol_sha256": protocol_hash,
        "feature_manifest_sha256": feature_hash,
        "device": "cpu",
        "python": platform.python_version(),
        "packages": {
            name: package_version(name)
            for name in ("torch", "torchvision", "transformers", "docling", "docling-core", "easyocr", "pillow", "doc-extraction")
        },
        "torch_version": torch.__version__,
        "torch_cuda_available": bool(torch.cuda.is_available()),
        "models": {"detection": DETECTION_MODEL_ID, "structure": STRUCTURE_MODEL_ID},
        "cpu_environment_note": "CPU-only; VM libGL workaround, if needed, is external and not stored here",
        "requested_units": len(manifest["pilot_unit_ids"]) if phase == "pilot" else manifest["counts"]["total_units"],
        "started_at": now(),
        "max_rss_bytes_before": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("pilot", "full"), required=True)
    args = parser.parse_args()
    manifest = read_json(HERE / "population_manifest.json")
    protocol_hash = sha256_file(HERE / "protocol.json")
    feature_hash = sha256_file(HERE / "feature_manifest.json")
    units = manifest["units"]
    if args.phase == "pilot":
        selected_ids = list(manifest["pilot_unit_ids"])
    else:
        selected_ids = [unit["unit_id"] for unit in units]
        pilot_integrity_path = HERE / "results" / "pilot" / "pilot_integrity.json"
        if not pilot_integrity_path.is_file() or read_json(pilot_integrity_path).get("status") != "PASS":
            raise SystemExit("refusing full run until the clean pilot integrity gate is PASS")
    by_id = {unit["unit_id"]: unit for unit in units}
    if len(by_id) != len(units):
        raise SystemExit("duplicate unit identity in frozen population")
    selected = []
    for unit_id in selected_ids:
        if unit_id not in by_id:
            raise SystemExit(f"selected unit absent from frozen population: {unit_id}")
        unit = by_id[unit_id]
        require_development(unit)
        selected.append(unit)

    phase_root = HERE / "results" / args.phase
    phase_root.mkdir(parents=True, exist_ok=True)
    metadata_path = phase_root / "run_metadata.json"
    metadata = runtime_metadata(manifest, args.phase, protocol_hash, feature_hash)
    if metadata_path.exists():
        prior = read_json(metadata_path)
        immutable = ("experiment", "phase", "code_commit", "baseline_checkpoint", "population_hash", "protocol_sha256", "feature_manifest_sha256", "device", "models")
        if any(prior.get(key) != metadata.get(key) for key in immutable):
            raise SystemExit("refusing to resume phase with changed immutable metadata")
        metadata = prior
    else:
        atomic_write_json(metadata_path, metadata)

    index_path = phase_root / "run_index.json"
    index = read_json(index_path) if index_path.exists() else {
        "experiment": EXPERIMENT_ID,
        "phase": args.phase,
        "population_hash": manifest["population_hash"],
        "records": [],
    }
    if index.get("population_hash") != manifest["population_hash"]:
        raise SystemExit("phase index population hash mismatch")
    index_by_id = {row["unit_id"]: row for row in index.get("records", [])}
    backend = TableTransformerBackend(device="cpu")
    for ordinal, unit in enumerate(selected, 1):
        existing = index_by_id.get(unit["unit_id"])
        result_path = phase_root / "raw" / unit["unit_id"] / "result.json"
        if existing and existing.get("status") == "complete" and result_path.is_file():
            print(f"[{ordinal}/{len(selected)}] existing {unit['unit_id']}", flush=True)
            continue
        if result_path.is_file():
            archive = result_path.parent / "attempts" / f"failure-{time.time_ns()}"
            archive.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(result_path, archive.with_suffix(".json"))
            telemetry_path = result_path.parent / "table_telemetry.json"
            if telemetry_path.is_file():
                shutil.copy2(telemetry_path, archive.with_name(f"{archive.name}-telemetry.json"))
        print(f"[{ordinal}/{len(selected)}] running {unit['unit_id']} ({unit['doc_group']})", flush=True)
        payload = run_unit(unit, backend, manifest["population_hash"], phase_root)
        index_by_id[unit["unit_id"]] = {
            "unit_id": unit["unit_id"],
            "kind": unit["kind"],
            "split": unit["split"],
            "image_id": unit["image_id"],
            "doc_group": unit["doc_group"],
            "status": payload["status"],
            "result": str(result_path.relative_to(HERE)),
            "updated_at": now(),
        }
        atomic_write_json(index_path, {**index, "records": [index_by_id[key] for key in sorted(index_by_id)]})
        print(json.dumps({"unit_id": unit["unit_id"], "status": payload["status"], "free_bytes": __import__("shutil").disk_usage(ROOT).free}), flush=True)

    records = [index_by_id.get(unit["unit_id"]) for unit in selected]
    complete = all(row and row.get("status") == "complete" for row in records)
    if complete:
        result_rows = [read_json(phase_root / "raw" / unit["unit_id"] / "result.json") for unit in selected]
        atomic_write_json(phase_root / "results.json", {
            "status": "complete",
            "experiment": EXPERIMENT_ID,
            "phase": args.phase,
            "population_hash": manifest["population_hash"],
            "records": result_rows,
            "completed_at": now(),
        })
        metadata["status"] = "complete"
        metadata["completed_at"] = now()
        metadata["completed_units"] = len(result_rows)
        atomic_write_json(metadata_path, metadata)
    print(json.dumps({"phase": args.phase, "requested": len(selected), "complete": sum(row and row.get("status") == "complete" for row in records), "total": len(selected)}))
    return 0 if complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
