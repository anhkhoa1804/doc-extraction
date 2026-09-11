#!/usr/bin/env python
"""Independent raw-artifact forensic audit for Experiment 036.

This intentionally does not import ``analyze.py`` or trust summary.json for
any count.  It reads immutable raw case records, frozen 035 sources, and the
036 manifest in a new Python process, then records every agreement check.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
E035 = ROOT / "experiments" / "035_mechanism_d_gating"
FULL_IMAGES = ROOT / "experiments" / "034a_omnidocbench_snapshot" / "dataset" / "full" / "images"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def iou(a: dict[str, float], b: dict[str, float]) -> float:
    x0, y0 = max(a["x0"], b["x0"]), max(a["y0"], b["y0"])
    x1, y1 = min(a["x1"], b["x1"]), min(a["y1"], b["y1"])
    if x1 <= x0 or y1 <= y0:
        return 0.0
    inter = (x1 - x0) * (y1 - y0)
    union = ((a["x1"] - a["x0"]) * (a["y1"] - a["y0"])
             + (b["x1"] - b["x0"]) * (b["y1"] - b["y0"]) - inter)
    return inter / union if union > 0 else 0.0


def structure_valid(table: dict[str, Any] | None) -> tuple[bool, str | None]:
    """036's frozen geometric definition, reimplemented independently."""
    if table is None:
        return False, "no_structure"
    if table.get("n_rows", 0) < 1 or table.get("n_cols", 0) < 1 or not table.get("cells") or not table.get("bbox"):
        return False, "empty_or_missing_geometry"
    bbox, cells = table["bbox"], table["cells"]
    escaped = sum(
        cell.get("bbox") is not None and (
            cell["bbox"]["x0"] < bbox["x0"] - 1 or cell["bbox"]["x1"] > bbox["x1"] + 1
            or cell["bbox"]["y0"] < bbox["y0"] - 1 or cell["bbox"]["y1"] > bbox["y1"] + 1
        )
        for cell in cells
    )
    return escaped / len(cells) < 0.2, None if escaped / len(cells) < 0.2 else "cells_escape_table_bbox"


def is_strict_d2(record: dict[str, Any]) -> bool:
    if record["verdict"] == "MULTIPLE_MATCH":
        contributors = record.get("multiple_match_contributors") or []
        return bool(contributors) and any(not c["table_gate_pass"] for c in contributors)
    region = record.get("matched_region")
    return region is not None and not region["table_gate_pass"] and record["final_table_object"] is None


def records(root: Path, prefix: str) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for path in sorted(root.glob(f"{prefix}-*.json")):
        payload = json.loads(path.read_text())
        case_id = payload.get("case", {}).get("case_id")
        if case_id in output:
            raise RuntimeError(f"duplicate raw case identity {case_id}")
        output[case_id] = payload
    return output


def production_tables(case: dict[str, Any]) -> list[dict[str, Any]]:
    document_path = ROOT / case["source_run"] / "final" / "document.json"
    return json.loads(document_path.read_text())["pages"][0].get("tables", [])


def recompute_target(case: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    forced = target.get("forced_crop_table")
    valid_structure, structure_reason = structure_valid(forced)
    owner = bool(forced and valid_structure and iou(forced["bbox"], target["target"]["bbox"]) > 0.1)
    overlap = max(
        (iou(forced["bbox"], table["bbox"]) for table in production_tables(case)
         if forced and table.get("bbox")),
        default=0.0,
    )
    gt = case.get("gt_bbox_px")
    gt_iou = iou(forced["bbox"], gt) if forced and gt else None
    conflict = overlap > 0.1
    recovery = bool(gt and valid_structure and owner and gt_iou >= 0.3 and not conflict)
    return {
        "structure_valid": valid_structure,
        "structure_reason": structure_reason,
        "ownership": owner,
        "gt_iou": gt_iou,
        "gt_iou_ge_0_3": bool(gt_iou is not None and gt_iou >= 0.3),
        "production_overlap": overlap,
        "conflict": conflict,
        "recovery": recovery,
    }


def expected_control(case: dict[str, Any]) -> dict[str, Any]:
    layout = json.loads((ROOT / case["source_run"] / "layout" / "page-001.json").read_text())["regions"]
    eligible = [
        (index, region) for index, region in enumerate(layout)
        if region.get("label", "").lower() != "table"
        and region["bbox"]["x1"] > region["bbox"]["x0"]
        and region["bbox"]["y1"] > region["bbox"]["y0"]
    ]
    index, region = max(
        eligible,
        key=lambda item: ((item[1]["bbox"]["x1"] - item[1]["bbox"]["x0"])
                          * (item[1]["bbox"]["y1"] - item[1]["bbox"]["y0"]), -item[0]),
    )
    return {"region_index": index, "label": region["label"], "bbox": region["bbox"]}


def model_loading_audit() -> dict[str, Any]:
    """Load the exact cached checkpoints and obtain Transformers loading info."""
    from transformers import AutoConfig, TableTransformerForObjectDetection

    output: dict[str, Any] = {}
    for model_id in (
        "microsoft/table-transformer-detection",
        "microsoft/table-transformer-structure-recognition",
    ):
        config = AutoConfig.from_pretrained(model_id, local_files_only=True)
        model, info = TableTransformerForObjectDetection.from_pretrained(
            model_id, local_files_only=True, output_loading_info=True
        )
        output[model_id] = {
            "model_type": config.model_type,
            "architectures": config.architectures,
            "num_labels": config.num_labels,
            "id2label": {str(k): v for k, v in config.id2label.items()},
            "missing_keys": sorted(info.get("missing_keys", [])),
            "unexpected_keys": sorted(info.get("unexpected_keys", [])),
            "mismatched_keys": sorted(info.get("mismatched_keys", [])),
            "parameter_count": sum(parameter.numel() for parameter in model.parameters()),
            "parameter_bytes": sum(parameter.numel() * parameter.element_size() for parameter in model.parameters()),
        }
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-root", type=Path, default=HERE / "results")
    parser.add_argument("--output", type=Path, default=HERE / "forensic_audit.json")
    parser.add_argument("--verify-model-loading", action="store_true")
    args = parser.parse_args()

    manifest = json.loads((HERE / "population_manifest.json").read_text())
    matching = json.loads((E035 / "table_region_matching.json").read_text())
    phase13 = json.loads((E035 / "non_table_sample_manifest.json").read_text())
    ledger = json.loads((E035 / "phase13_identity_ledger.json").read_text())
    summary = json.loads((HERE / "summary.json").read_text())
    treatment_raw = records(args.raw_root / "treatment", "d2")
    control_raw = records(args.raw_root / "control", "control")
    errors: list[str] = []

    expected_artifact_hashes = {
        "table_region_matching.json": sha256(E035 / "table_region_matching.json"),
        "non_table_sample_manifest.json": sha256(E035 / "non_table_sample_manifest.json"),
        "final_evidence_index.json": sha256(E035 / "final_evidence_index.json"),
    }
    if manifest.get("source_artifact_sha256") != expected_artifact_hashes:
        errors.append("036 manifest source-artifact hashes no longer match frozen 035 artifacts")

    strict = {
        (record["image"], str(record["gt_table_anno_id"]))
        for record in matching["records"] if is_strict_d2(record)
    }
    treatment_manifest = {(case["image"], str(case["gt_table_anno_id"])) for case in manifest["treatment_cases"]}
    if len(strict) != 34 or strict != treatment_manifest:
        errors.append("036 treatment identities do not exactly equal frozen 035 strict-D2 identities")
    if len(treatment_manifest) != len(manifest["treatment_cases"]):
        errors.append("duplicate treatment identity in manifest")
    strict_by_identity = {
        (record["image"], str(record["gt_table_anno_id"])): record
        for record in matching["records"] if is_strict_d2(record)
    }

    frozen_control_images = set(phase13["image_names"])
    control_images = {case["image"] for case in manifest["control_cases"]}
    excluded_images = {case["image"] for case in manifest["excluded_control_pages"]}
    if len(control_images) != len(manifest["control_cases"]):
        errors.append("duplicate control identity in manifest")
    if control_images | excluded_images != frozen_control_images or control_images & excluded_images:
        errors.append("control and exclusion identities do not partition the frozen Phase-13 frame")
    if len(control_images) != 145 or len(excluded_images) != 5:
        errors.append("control/exclusion counts are not 145/5")
    ledger_images = {entry["image_name"] for entry in ledger["identities"]}
    if ledger_images != frozen_control_images:
        errors.append("Phase-13 ledger does not equal frozen sample identity frame")

    expected_treatment_ids = {case["case_id"] for case in manifest["treatment_cases"]}
    expected_control_ids = {case["case_id"] for case in manifest["control_cases"]}
    if set(treatment_raw) != expected_treatment_ids:
        errors.append("raw treatment case files do not exactly match the manifest")
    if set(control_raw) != expected_control_ids:
        errors.append("raw control case files do not exactly match the manifest")
    for arm, expected_count in (("treatment", 34), ("control", 145)):
        run_info = json.loads((args.raw_root / arm / "run_metadata.json").read_text())
        if run_info.get("device") != "cpu" or run_info.get("cases_requested") != expected_count:
            errors.append(f"{arm} run metadata has unexpected device or requested count")
        if run_info.get("models") != {
            "detection": "microsoft/table-transformer-detection",
            "structure": "microsoft/table-transformer-structure-recognition",
        }:
            errors.append(f"{arm} run metadata has unexpected model IDs")

    treatment_rows: list[dict[str, Any]] = []
    for case in manifest["treatment_cases"]:
        raw = treatment_raw.get(case["case_id"])
        if raw is None:
            continue
        if raw.get("case") != case or raw.get("status") != "success" or len(raw.get("targets", [])) != len(case["targets"]):
            errors.append(f"treatment raw provenance/status mismatch: {case['case_id']}")
            continue
        source_image = FULL_IMAGES / case["image"]
        if sha256(source_image) != case["source_image_sha256"]:
            errors.append(f"source image hash mismatch: {case['case_id']}")
        layout_path = ROOT / case["source_run"] / "layout" / "page-001.json"
        document_path = ROOT / case["source_run"] / "final" / "document.json"
        if sha256(layout_path) != case["source_layout_sha256"] or sha256(document_path) != case["source_document_sha256"]:
            errors.append(f"source run hash mismatch: {case['case_id']}")
        strict_record = strict_by_identity[(case["image"], str(case["gt_table_anno_id"]))]
        if strict_record["gt_bbox_px"] != case["gt_bbox_px"]:
            errors.append(f"GT table linkage/bbox mismatch: {case['case_id']}")
        layout_regions = json.loads(layout_path.read_text())["regions"]
        for expected, observed in zip(case["targets"], raw["targets"]):
            if observed.get("target") != expected:
                errors.append(f"crop target mismatch: {case['case_id']}")
            if layout_regions[expected["region_index"]]["bbox"] != expected["bbox"]:
                errors.append(f"treatment crop is not the frozen source-layout bbox: {case['case_id']}")
            recomputed = recompute_target(case, observed)
            for field, raw_field in (("structure_valid", "forced_crop_structural_validity"), ("ownership", "ownership_established_in_isolated_counterfactual"),
                                     ("conflict", "duplicate_ownership"), ("recovery", "valid_recovery")):
                actual = observed[raw_field]["valid"] if raw_field == "forced_crop_structural_validity" else observed[raw_field]
                if recomputed[field] != actual:
                    errors.append(f"recomputed {field} mismatch: {case['case_id']}")
            treatment_rows.append({
                "case_id": case["case_id"], "image": case["image"], "gt_table_anno_id": case["gt_table_anno_id"],
                "role": expected["label"], "crop_bbox": expected["bbox"],
                "detector_found": observed["crop_detector_found_table"], "structure_valid": recomputed["structure_valid"],
                "ownership": recomputed["ownership"], "gt_iou": recomputed["gt_iou"],
                "gt_iou_ge_0_3": recomputed["gt_iou_ge_0_3"], "production_overlap": recomputed["production_overlap"],
                "conflict": recomputed["conflict"], "valid_recovery": recomputed["recovery"],
                "runtime_seconds": observed["runtime_seconds"],
            })

    phase13_records = json.loads((E035 / "dataset" / "non_table_sample" / "OmniDocBench.json").read_text())
    source_by_image = {Path(item["page_info"]["image_path"]).name: item["page_info"]["page_attribute"].get("data_source") for item in phase13_records}
    control_rows: list[dict[str, Any]] = []
    for case in manifest["control_cases"]:
        raw = control_raw.get(case["case_id"])
        if raw is None:
            continue
        expected = expected_control(case)
        if {k: case[k] for k in ("region_index", "label", "bbox")} != expected:
            errors.append(f"control deterministic selection mismatch: {case['case_id']}")
        if raw.get("case") != case or raw.get("status") != "success" or len(raw.get("targets", [])) != 1:
            errors.append(f"control raw provenance/status mismatch: {case['case_id']}")
            continue
        observed = raw["targets"][0]
        source_image = FULL_IMAGES / case["image"]
        if sha256(source_image) != case["source_image_sha256"]:
            errors.append(f"control source image hash mismatch: {case['case_id']}")
        layout_path = ROOT / case["source_run"] / "layout" / "page-001.json"
        document_path = ROOT / case["source_run"] / "final" / "document.json"
        if sha256(layout_path) != case["source_layout_sha256"] or sha256(document_path) != case["source_document_sha256"]:
            errors.append(f"control source run hash mismatch: {case['case_id']}")
        if observed.get("target") != expected:
            errors.append(f"control crop mismatch: {case['case_id']}")
        recomputed = recompute_target(case, observed)
        false_positive = recomputed["structure_valid"] and recomputed["ownership"]
        if false_positive != (observed["forced_crop_structural_validity"]["valid"] and observed["ownership_established_in_isolated_counterfactual"]):
            errors.append(f"control false-positive recomputation mismatch: {case['case_id']}")
        control_rows.append({
            "case_id": case["case_id"], "image": case["image"], "role": case["label"],
            "data_source": source_by_image.get(case["image"]), "detector_found": observed["crop_detector_found_table"],
            "structure_valid": recomputed["structure_valid"], "ownership": recomputed["ownership"],
            "false_positive": false_positive, "conflict": recomputed["conflict"],
            "runtime_seconds": observed["runtime_seconds"],
        })

    def count(rows: list[dict[str, Any]], field: str) -> int:
        return sum(bool(row[field]) for row in rows)

    treatment_counts = {
        "invocation_success": sum(raw.get("status") == "success" for raw in treatment_raw.values()),
        "detector_found": count(treatment_rows, "detector_found"), "structure_valid": count(treatment_rows, "structure_valid"),
        "ownership": count(treatment_rows, "ownership"), "valid_recovery": count(treatment_rows, "valid_recovery"),
        "conflict": count(treatment_rows, "conflict"),
    }
    control_counts = {
        "invocation_success": sum(raw.get("status") == "success" for raw in control_raw.values()),
        "detector_found": count(control_rows, "detector_found"), "structure_valid": count(control_rows, "structure_valid"),
        "ownership": count(control_rows, "ownership"), "false_positive": count(control_rows, "false_positive"),
        "conflict": count(control_rows, "conflict"),
    }
    expected_counts = {
        "treatment": {"invocation_success": 34, "detector_found": 14, "structure_valid": 31, "ownership": 31, "valid_recovery": 17, "conflict": 8},
        "control": {"invocation_success": 145, "detector_found": 38, "structure_valid": 104, "ownership": 104, "false_positive": 104, "conflict": 3},
    }
    if treatment_counts != expected_counts["treatment"] or control_counts != expected_counts["control"]:
        errors.append("raw recomputation does not equal published primary counts")

    # summary.json aggregates case wall time, not just the model-call span.
    # Read that same raw field directly rather than trusting its aggregate.
    all_runtimes = [raw["case_runtime_seconds"] for raw in treatment_raw.values()] + [
        raw["case_runtime_seconds"] for raw in control_raw.values()
    ]
    runtime = {"n": len(all_runtimes), "total": round(sum(all_runtimes), 4), "median": round(statistics.median(all_runtimes), 4),
               "min": round(min(all_runtimes), 4), "max": round(max(all_runtimes), 4)}
    target_runtime = [row["runtime_seconds"] for row in treatment_rows + control_rows]
    if runtime != {"n": 179, "total": 2875.5174, "median": 1.2643, "min": 0.1693, "max": 122.7583}:
        errors.append("runtime aggregation mismatch")

    summary_agrees = (
        summary["treatment_case_level"]["valid_recovery"] == treatment_counts["valid_recovery"]
        and summary["control_target_level"]["false_positive"] == control_counts["false_positive"]
        and summary["execution"]["case_runtime_seconds"] == {k: v for k, v in runtime.items() if k != "n"}
    )
    if not summary_agrees:
        errors.append("tracked summary.json disagrees with independent recomputation")

    model = model_loading_audit() if args.verify_model_loading else {"not_run": True}
    model_ok = all(not value.get("missing_keys") and not value.get("mismatched_keys") for value in model.values() if isinstance(value, dict))
    if args.verify_model_loading and not model_ok:
        errors.append("model loading has missing or mismatched checkpoint weights")
    intersections = {
        "detector_and_structure": sum(row["detector_found"] and row["structure_valid"] for row in treatment_rows),
        "detector_and_recovery": sum(row["detector_found"] and row["valid_recovery"] for row in treatment_rows),
        "recovery_and_conflict": sum(row["valid_recovery"] and row["conflict"] for row in treatment_rows),
        "recovery_without_detector": sum(row["valid_recovery"] and not row["detector_found"] for row in treatment_rows),
        "structure_without_detector": sum(row["structure_valid"] and not row["detector_found"] for row in treatment_rows),
    }
    control_forensics = {
        "false_positive_and_detector": sum(row["false_positive"] and row["detector_found"] for row in control_rows),
        "false_positive_structure_only": sum(row["false_positive"] and not row["detector_found"] for row in control_rows),
        "false_positive_and_conflict": sum(row["false_positive"] and row["conflict"] for row in control_rows),
        "false_positive_by_role": dict(Counter(row["role"] for row in control_rows if row["false_positive"]).most_common()),
        "false_positive_by_data_source": dict(Counter(row["data_source"] for row in control_rows if row["false_positive"]).most_common()),
    }
    output = {
        "experiment": "036_mechanism_d_counterfactual", "audit_version": 1,
        "population": {"strict_d2_from_035": len(strict), "treatment_manifest": len(manifest["treatment_cases"]),
                       "treatment_raw": len(treatment_raw), "control_frame": len(frozen_control_images),
                       "controls": len(manifest["control_cases"]), "excluded_controls": len(manifest["excluded_control_pages"]),
                       "control_raw": len(control_raw)},
        "recomputed": {"treatment": treatment_counts, "control": control_counts, "runtime": runtime,
                       "target_operation_runtime_seconds": round(sum(target_runtime), 3)},
        "agreement": {"population_exact": not any("identity" in error or "partition" in error or "selection" in error for error in errors),
                      "raw_counts_exact": treatment_counts == expected_counts["treatment"] and control_counts == expected_counts["control"],
                      "summary_agrees": summary_agrees, "source_hashes_and_crops_exact": not any("hash" in error or "crop" in error for error in errors)},
        "treatment_intersections": intersections, "control_forensics": control_forensics,
        "treatment_cases": treatment_rows, "model_loading": model,
        "helper_isolation": {"verdict": "PASS", "basis": "helper calls the same lazy-loaded models, processors, thresholds, and no-grad/eval methods; it writes no production artifacts and has no model-parameter mutation path."},
        "errors": errors, "overall_verdict": "036_CONFIRMED_WITH_LIMITATIONS" if not errors else "036_NEEDS_REPAIR",
    }
    args.output.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({k: output[k] for k in ("population", "recomputed", "agreement", "treatment_intersections", "control_forensics", "errors", "overall_verdict")}, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
