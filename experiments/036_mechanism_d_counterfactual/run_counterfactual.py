#!/usr/bin/env python
"""Execute an isolated 036 crop counterfactual arm; never writes production runs."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import subprocess
import time
from pathlib import Path

from doc_extraction.backends.table_backend import (
    DETECTION_MODEL_ID,
    STRUCTURE_MODEL_ID,
    TableTransformerBackend,
)
from doc_extraction.pipelines.base import PageInput
from doc_extraction.schemas.element import BBox

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def iou(a: dict, b: dict) -> float:
    x0, y0 = max(a["x0"], b["x0"]), max(a["y0"], b["y0"])
    x1, y1 = min(a["x1"], b["x1"]), min(a["y1"], b["y1"])
    if x1 <= x0 or y1 <= y0:
        return 0.0
    inter = (x1 - x0) * (y1 - y0)
    union = (a["x1"] - a["x0"]) * (a["y1"] - a["y0"]) + (b["x1"] - b["x0"]) * (b["y1"] - b["y0"]) - inter
    return inter / union if union else 0.0


def structural_validity(table: dict | None) -> dict:
    if table is None:
        return {"valid": False, "reason": "no_structure"}
    rows, cols, cells, bbox = table["n_rows"], table["n_cols"], table["cells"], table.get("bbox")
    if rows < 1 or cols < 1 or not cells or bbox is None:
        return {"valid": False, "reason": "empty_or_missing_geometry"}
    escaping = sum(1 for cell in cells if cell.get("bbox") and (
        cell["bbox"]["x0"] < bbox["x0"] - 1 or cell["bbox"]["x1"] > bbox["x1"] + 1
        or cell["bbox"]["y0"] < bbox["y0"] - 1 or cell["bbox"]["y1"] > bbox["y1"] + 1
    ))
    return {
        "valid": escaping / len(cells) < 0.2,
        "reason": None if escaping / len(cells) < 0.2 else "cells_escape_table_bbox",
        "n_rows": rows, "n_cols": cols, "n_cells": len(cells),
        "escaping_cell_fraction": round(escaping / len(cells), 4),
    }


def versions() -> dict[str, str | None]:
    result = {}
    for package in ("torch", "transformers", "timm", "pillow", "doc-extraction"):
        try:
            result[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            result[package] = None
    return result


def gpu_snapshot() -> str | None:
    try:
        return subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name,memory.used,memory.total", "--format=csv,noheader"], text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def load_production_tables(case: dict) -> list[dict]:
    document = json.loads((ROOT / case["source_run"] / "final/document.json").read_text())
    return document["pages"][0].get("tables", [])


def run_target(backend: TableTransformerBackend, case: dict, target: dict, target_index: int, device: str) -> dict:
    from PIL import Image
    import torch

    image_path = ROOT / "experiments/034a_omnidocbench_snapshot/dataset/full/images" / case["image"]
    with Image.open(image_path) as image:
        width, height = image.size
    bbox = BBox(**target["bbox"])
    page = PageInput(page_index=0, width=width, height=height, image_path=image_path, dpi=None)
    started = time.perf_counter()
    result = backend.extract_crop_counterfactual(page, bbox, f"{case['case_id']}-r{target_index}")
    runtime = time.perf_counter() - started
    forced = result.forced_crop_table.model_dump() if result.forced_crop_table else None
    detected = [box.model_dump() for box in result.detected_boxes]
    detected_tables = [table.model_dump() for table in result.detector_tables]
    forced_validity = structural_validity(forced)
    existing = load_production_tables(case)
    existing_overlap = max((iou(forced["bbox"], table["bbox"]) for table in existing if forced and table.get("bbox")), default=0.0)
    gt_bbox = case.get("gt_bbox_px")
    gt_iou = iou(forced["bbox"], gt_bbox) if forced and gt_bbox else None
    detector_gt_iou = max((iou(box, gt_bbox) for box in detected), default=0.0) if gt_bbox else None
    ownership_established = bool(forced_validity["valid"] and iou(forced["bbox"], target["bbox"]) > 0.1)
    # Valid recovery is deliberately stricter than invocation/detection:
    # valid structure, isolated owner mapping, geometry relevant to the GT,
    # and no table already owning materially overlapping evidence.
    valid_recovery = bool(
        gt_bbox and forced_validity["valid"] and ownership_established and gt_iou >= 0.3 and existing_overlap <= 0.1
    )
    max_vram = None
    if device.startswith("cuda") and torch.cuda.is_available():
        max_vram = int(torch.cuda.max_memory_allocated())
    return {
        "target": target,
        "specialist_invocation_success": True,
        "runtime_seconds": round(runtime, 6),
        "crop_detector_boxes": detected,
        "crop_detector_found_table": bool(detected),
        "crop_detector_max_gt_iou": detector_gt_iou,
        "forced_crop_table": forced,
        "forced_crop_structural_validity": forced_validity,
        "ownership_established_in_isolated_counterfactual": ownership_established,
        "existing_production_table_max_iou": round(existing_overlap, 6),
        "duplicate_ownership": existing_overlap > 0.1,
        "cross_region_conflict": existing_overlap > 0.1,
        "gt_iou": gt_iou,
        "valid_recovery": valid_recovery,
        "detector_tables": detected_tables,
        "process_max_vram_bytes": max_vram,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arm", choices=("treatment", "control"), required=True)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    manifest = json.loads((HERE / "population_manifest.json").read_text())
    cases = manifest["treatment_cases" if args.arm == "treatment" else "control_cases"]
    if args.limit is not None:
        cases = cases[:args.limit]
    args.output.mkdir(parents=True, exist_ok=True)
    backend = TableTransformerBackend(device=args.device)
    run_info = {
        "experiment": manifest["experiment"], "arm": args.arm, "device": args.device,
        "models": {"detection": DETECTION_MODEL_ID, "structure": STRUCTURE_MODEL_ID},
        "library_versions": versions(), "gpu_before": gpu_snapshot(), "cases_requested": len(cases),
    }
    (args.output / "run_metadata.json").write_text(json.dumps(run_info, indent=2) + "\n")
    for case in cases:
        out = args.output / f"{case['case_id']}.json"
        if out.exists():
            existing = json.loads(out.read_text())
            if existing.get("status") == "success":
                continue
        targets = case["targets"] if args.arm == "treatment" else [{
            "region_index": case["region_index"], "label": case["label"], "bbox": case["bbox"]
        }]
        started = time.perf_counter()
        payload = {"case": case, "status": "success", "targets": []}
        try:
            for index, target in enumerate(targets):
                payload["targets"].append(run_target(backend, case, target, index, args.device))
        except Exception as exc:  # preserve operational failures as experimental evidence
            payload["status"] = "failure"
            payload["error"] = f"{type(exc).__name__}: {exc}"
        payload["case_runtime_seconds"] = round(time.perf_counter() - started, 6)
        payload["gpu_after_case"] = gpu_snapshot()
        out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
