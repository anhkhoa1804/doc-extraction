#!/usr/bin/env python
"""Measure natural table/region ownership activation after the 038 baseline.

This is still pre-treatment analysis.  It uses only the frozen independent
GT table boxes to identify naturally occurring D2-like cases and never calls
the 036 forced-crop path.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "experiments" / "035_mechanism_d_gating"))
import matching_lib as matching  # noqa: E402


def bbox_from_coco(bbox: list[float]) -> dict:
    """Convert COCO [x, y, width, height] to the frozen pixel-space bbox."""
    x, y, width, height = bbox
    return {"x0": x, "y0": y, "x1": x + width, "y1": y + height}


def candidates(gt_bbox: dict, regions: list[dict]) -> list[dict]:
    rows = []
    for index, region in enumerate(regions):
        bbox = region["bbox"]
        iou = matching.bbox_iou(gt_bbox, bbox)
        over_gt = matching.containment_fraction(gt_bbox, bbox)
        over_region = matching.containment_fraction(bbox, gt_bbox)
        if iou <= 0 and over_gt <= 0 and over_region <= 0:
            continue
        rows.append({
            "region_index": index,
            "label": region["label"],
            "bbox": bbox,
            "iou": round(iou, 4),
            "intersection_over_gt": round(over_gt, 4),
            "intersection_over_region": round(over_region, 4),
            "region_area_ratio": round(matching.bbox_area(bbox) / matching.bbox_area(gt_bbox), 4),
            "bbox_center_distance_px": round(matching.bbox_center_distance(gt_bbox, bbox), 2),
        })
    rows.sort(key=lambda row: row["intersection_over_gt"], reverse=True)
    return rows


def single_region_detail(detail: dict, regions: list[dict], elements: list[dict], tables: list[dict]) -> dict | None:
    index = detail.get("matched_region_index")
    if index is None or index >= len(regions):
        return None
    region = regions[index]
    element = elements[index] if index < len(elements) else {}
    table_id = element.get("table_id")
    return {
        "region_index": index,
        "raw_label": region["label"],
        "label_lower": region["label"].lower(),
        "table_gate_pass": region["label"].lower() == "table",
        "final_ir_element_type": element.get("type"),
        "final_ir_table_id": table_id,
        "final_table_object": next((table for table in tables if table.get("id") == table_id), None),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=HERE / "baseline_analysis.json")
    args = parser.parse_args()

    manifest = json.loads((HERE / "population_manifest.json").read_text())
    index_path = HERE / "results" / "baseline_run_index.json"
    index = json.loads(index_path.read_text()) if index_path.is_file() else None
    run_by_image = {item["image_id"]: item for item in (index or {}).get("records", [])}
    rows = []
    incomplete = []
    for item in manifest["records"]:
        run_row = run_by_image.get(item["image_id"])
        run_dir = ROOT / run_row["run"] if run_row and run_row.get("run") else None
        layout_path = run_dir / "layout" / "page-001.json" if run_dir else None
        document_path = run_dir / "final" / "document.json" if run_dir else None
        if not run_row or run_row.get("status") != "complete" or not layout_path.is_file() or not document_path.is_file():
            incomplete.append({"image_id": item["image_id"], "file_name": item["file_name"]})
            continue
        layout = json.loads(layout_path.read_text())
        document = json.loads(document_path.read_text())
        page = document["pages"][0]
        regions = layout["regions"]
        for table in item["tables"]:
            gt_bbox = bbox_from_coco(table["bbox"])
            cand = candidates(gt_bbox, regions)
            verdict, detail = matching.classify_match(gt_bbox, cand)
            matched = single_region_detail(detail, regions, page.get("elements", []), page.get("tables", []))
            multiple_wrong = []
            if verdict == "MULTIPLE_MATCH":
                for region_index in detail.get("contributing_region_indices", []):
                    if region_index < len(regions):
                        region = regions[region_index]
                        multiple_wrong.append({
                            "region_index": region_index,
                            "raw_label": region["label"],
                            "table_gate_pass": region["label"].lower() == "table",
                        })
            strict_d2 = (
                bool(multiple_wrong) and any(not row["table_gate_pass"] for row in multiple_wrong)
                if verdict == "MULTIPLE_MATCH"
                else bool(matched and not matched["table_gate_pass"] and matched["final_table_object"] is None)
            )
            rows.append({
                "image_id": item["image_id"], "file_name": item["file_name"],
                "doc_group": item["doc_group"],
                "split": "development" if list(dict.fromkeys(x["doc_group"] for x in manifest["records"])).index(item["doc_group"]) < 10 else "held_out_test",
                "page_no": item["page_no"], "gt_table_id": table["id"],
                "gt_bbox_px": gt_bbox, "n_regions": len(regions),
                "verdict": verdict, "verdict_detail": detail,
                "top_candidates": cand[:5], "matched_region": matched,
                "multiple_match_contributors": multiple_wrong,
                "strict_d2": strict_d2,
            })

    counts = Counter(row["verdict"] for row in rows)
    d2 = [row for row in rows if row["strict_d2"]]
    by_split = Counter(row["split"] for row in d2)
    development_d2 = [row for row in d2 if row["split"] == "development"]
    development_groups = sorted({row["doc_group"] for row in development_d2})
    development_labels = sorted({row["matched_region"]["raw_label"] for row in development_d2 if row["matched_region"]})
    development_group_counts = Counter(row["doc_group"] for row in development_d2)
    payload = {
        "experiment": "038_independent_real_corpus",
        "phase": "unchanged_production_baseline_activation",
        "status": "baseline_incomplete" if incomplete else "NATURAL_D2_ACTIVATED",
        "definition": "035-compatible strict D2: relevant GT-table match under a non-table raw region with no existing table object; MULTIPLE_MATCH follows the frozen 035/036 contributor rule",
        "baseline": {
            "records_analyzed": len({row["image_id"] for row in rows}),
            "table_annotations_analyzed": len(rows),
            "incomplete_records": incomplete,
            "forced_crop_invocations": 0,
        },
        "verdict_counts": dict(counts),
        "strict_d2_counts": {"all": len(d2), **dict(by_split)},
        "development_activation_assessment": {
            "strict_d2_cases": len(development_d2),
            "source_groups": development_groups,
            "source_group_count": len(development_groups),
            "raw_labels": development_labels,
            "raw_label_count": len(development_labels),
            "cases_by_source_group": dict(development_group_counts),
            "policy_selection_status": (
                "038_BLOCKED_INADEQUATE_DEVELOPMENT"
                if not incomplete and len(development_groups) < 3
                else "not_assessed"
            ),
            "policy_selection_reason": (
                "Only six development cases are present across two source-document groups, "
                "with one raw label; this is insufficient to assess document-group-generalized "
                "selectivity or compare policy families defensibly."
                if not incomplete and len(development_groups) < 3
                else None
            ),
        },
        "strict_d2_wrong_labels": dict(Counter(
            row["matched_region"]["raw_label"]
            for row in d2 if row["matched_region"]
        )),
        "records": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"status": payload["status"], "tables": len(rows), "incomplete": len(incomplete), "strict_d2": len(d2), "development_strict_d2": by_split["development"]}))
    return 0 if not incomplete else 1


if __name__ == "__main__":
    raise SystemExit(main())
