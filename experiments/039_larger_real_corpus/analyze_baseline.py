#!/usr/bin/env python
"""Measure natural strict-D2 activation after the 039 baseline.

This is pre-treatment analysis only.  It uses frozen GT table boxes, frozen
production layout/ownership outputs, and the shared 035 matcher.  It never
invokes forced-crop code or selects a policy.
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


def region_detail(detail: dict, regions: list[dict], elements: list[dict], tables: list[dict]) -> dict | None:
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
        if (
            not run_row
            or run_row.get("status") != "complete"
            or not layout_path.is_file()
            or not document_path.is_file()
        ):
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
            matched = region_detail(detail, regions, page.get("elements", []), page.get("tables", []))
            contributors = []
            if verdict == "MULTIPLE_MATCH":
                for region_index in detail.get("contributing_region_indices", []):
                    if region_index < len(regions):
                        region = regions[region_index]
                        contributors.append({
                            "region_index": region_index,
                            "raw_label": region["label"],
                            "table_gate_pass": region["label"].lower() == "table",
                        })
            strict_d2 = (
                bool(contributors) and any(not row["table_gate_pass"] for row in contributors)
                if verdict == "MULTIPLE_MATCH"
                else bool(matched and not matched["table_gate_pass"] and matched["final_table_object"] is None)
            )
            wrong_labels = sorted({
                row["raw_label"] for row in contributors if not row["table_gate_pass"]
            })
            if strict_d2 and matched and not matched["table_gate_pass"]:
                wrong_labels.append(matched["raw_label"])
                wrong_labels = sorted(set(wrong_labels))
            rows.append({
                "image_id": item["image_id"],
                "file_name": item["file_name"],
                "doc_group": item["doc_group"],
                "doc_category": item["doc_category"],
                "split": item["split"],
                "page_no": item["page_no"],
                "gt_table_id": table["id"],
                "gt_bbox_px": gt_bbox,
                "n_regions": len(regions),
                "verdict": verdict,
                "verdict_detail": detail,
                "top_candidates": cand[:5],
                "matched_region": matched,
                "multiple_match_contributors": contributors,
                "strict_d2_wrong_labels": wrong_labels,
                "strict_d2": strict_d2,
            })

    strict_d2 = [row for row in rows if row["strict_d2"]]
    development_d2 = [row for row in strict_d2 if row["split"] == "development"]
    held_out_d2 = [row for row in strict_d2 if row["split"] == "held_out_test"]
    groups = Counter(row["doc_group"] for row in development_d2)
    labels = sorted({label for row in development_d2 for label in row["strict_d2_wrong_labels"]})
    categories = sorted({row["doc_category"] for row in development_d2})
    largest_group = max(groups.items(), key=lambda pair: (-pair[1], pair[0]), default=(None, 0))
    development_count = len(development_d2)
    gate = {
        "minimum_development_strict_d2": 12,
        "minimum_source_groups": 6,
        "minimum_raw_labels": 3,
        "minimum_categories": 4,
        "maximum_single_group_fraction": 0.5,
        "strict_d2_cases": development_count,
        "source_group_count": len(groups),
        "raw_label_count": len(labels),
        "category_count": len(categories),
        "largest_source_group": largest_group[0],
        "largest_source_group_cases": largest_group[1],
        "largest_source_group_fraction": (largest_group[1] / development_count if development_count else 0.0),
    }
    if incomplete:
        adequacy_status = "039_BASELINE_INCOMPLETE"
    elif development_count == 0:
        adequacy_status = "039_BLOCKED_NO_DEVELOPMENT_ACTIVATION"
    elif (
        development_count < 12
        or len(groups) < 6
        or len(labels) < 3
        or len(categories) < 4
        or largest_group[1] > development_count / 2
    ):
        adequacy_status = "039_BLOCKED_INSUFFICIENT_DIVERSITY"
    else:
        adequacy_status = "039_READY_FOR_POLICY_DESIGN"

    payload = {
        "experiment": "039_larger_real_corpus",
        "phase": "unchanged_production_baseline_activation",
        "status": adequacy_status,
        "definition": "035-compatible strict D2: relevant GT-table match under a non-table raw region with no existing table object; MULTIPLE_MATCH follows the frozen 035 contributor rule",
        "baseline": {
            "records_analyzed": len({row["image_id"] for row in rows}),
            "table_annotations_analyzed": len(rows),
            "incomplete_records": incomplete,
            "forced_crop_invocations": 0,
        },
        "verdict_counts": dict(Counter(row["verdict"] for row in rows)),
        "strict_d2_counts": {
            "all": len(strict_d2),
            "development": len(development_d2),
            "held_out_test": len(held_out_d2),
        },
        "development_activation_assessment": {
            "strict_d2_cases": development_count,
            "source_groups": sorted(groups),
            "source_group_count": len(groups),
            "raw_labels": labels,
            "raw_label_count": len(labels),
            "categories": categories,
            "category_count": len(categories),
            "cases_by_source_group": dict(sorted(groups.items())),
            "largest_source_group": largest_group[0],
            "largest_source_group_cases": largest_group[1],
            "largest_source_group_fraction": gate["largest_source_group_fraction"],
            "adequacy_gate": gate,
            "policy_selection_status": adequacy_status,
        },
        "records": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({
        "status": payload["status"],
        "tables": len(rows),
        "incomplete": len(incomplete),
        "strict_d2": len(strict_d2),
        "development_strict_d2": len(development_d2),
        "held_out_strict_d2": len(held_out_d2),
    }))
    return 0 if not incomplete else 1


if __name__ == "__main__":
    raise SystemExit(main())
