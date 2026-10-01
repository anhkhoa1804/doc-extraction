#!/usr/bin/env python
"""Independent post-baseline forensic review for experiment 039.

This module deliberately recomputes the 035-compatible match and strict-D2
verdict from the frozen manifest and raw baseline JSON.  It does not import
``baseline_analysis.json`` and it never invokes treatment code.  The outputs
are compact, auditable summaries; raw baseline runs remain the source of
evidence.
"""
from __future__ import annotations

import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "experiments" / "035_mechanism_d_gating"))
import matching_lib as matching  # noqa: E402


MANIFEST_PATH = HERE / "population_manifest.json"
INDEX_PATH = HERE / "results" / "baseline_run_index.json"
RUN_ROOT = HERE / "results" / "baseline_runs"


def load(path: Path):
    return json.loads(path.read_text())


def bbox_from_coco(bbox: list[float]) -> dict[str, float]:
    x, y, width, height = bbox
    return {"x0": x, "y0": y, "x1": x + width, "y1": y + height}


def area(box: dict) -> float:
    return max(0.0, box["x1"] - box["x0"]) * max(0.0, box["y1"] - box["y0"])


def intersection(a: dict, b: dict) -> float:
    x0, y0 = max(a["x0"], b["x0"]), max(a["y0"], b["y0"])
    x1, y1 = min(a["x1"], b["x1"]), min(a["y1"], b["y1"])
    return max(0.0, x1 - x0) * max(0.0, y1 - y0)


def center(box: dict) -> tuple[float, float]:
    return ((box["x0"] + box["x1"]) / 2, (box["y0"] + box["y1"]) / 2)


def center_inside(inner: dict, outer: dict) -> bool:
    x, y = center(inner)
    return outer["x0"] <= x <= outer["x1"] and outer["y0"] <= y <= outer["y1"]


def round_or_none(value, digits: int = 4):
    return None if value is None else round(float(value), digits)


def quantiles(values: list[float | int]) -> dict[str, float | None]:
    values = sorted(float(v) for v in values if v is not None)
    if not values:
        return {key: None for key in ("min", "q25", "median", "q75", "q90", "max", "mean")}
    def at(fraction: float) -> float:
        return values[min(len(values) - 1, int((len(values) - 1) * fraction))]
    return {
        "min": round(values[0], 4),
        "q25": round(at(0.25), 4),
        "median": round(median(values), 4),
        "q75": round(at(0.75), 4),
        "q90": round(at(0.90), 4),
        "max": round(values[-1], 4),
        "mean": round(mean(values), 4),
    }


def candidate_rows(gt_bbox: dict, regions: list[dict]) -> list[dict]:
    rows = []
    for index, region in enumerate(regions):
        box = region["bbox"]
        iou = matching.bbox_iou(gt_bbox, box)
        over_gt = matching.containment_fraction(gt_bbox, box)
        over_region = matching.containment_fraction(box, gt_bbox)
        if iou <= 0 and over_gt <= 0 and over_region <= 0:
            continue
        rows.append({
            "region_index": index,
            "raw_label": region["label"],
            "normalized_role": region["label"].lower(),
            "bbox": box,
            "iou": round(iou, 4),
            "intersection_over_gt": round(over_gt, 4),
            "intersection_over_region": round(over_region, 4),
            "region_area_ratio": round(matching.bbox_area(box) / matching.bbox_area(gt_bbox), 4),
            "bbox_center_distance_px": round(matching.bbox_center_distance(gt_bbox, box), 2),
        })
    rows.sort(key=lambda row: row["intersection_over_gt"], reverse=True)
    return rows


def warning_strings(run_dir: Path, metadata: dict, layout: dict, ocr: dict,
                    table_raw: dict, page: dict) -> list[str]:
    values: list[str] = []
    values.extend(str(x) for x in metadata.get("warnings", []))
    values.extend(str(x) for x in metadata.get("errors", []))
    values.extend(str(x) for x in layout.get("warnings", []))
    values.extend(str(x) for x in ocr.get("warnings", []))
    values.extend(str(x) for x in table_raw.get("warnings", []))
    values.extend(str(x) for x in page.get("notes", []))
    log_path = run_dir / "logs" / "pipeline.jsonl"
    if log_path.is_file():
        for line in log_path.read_text().splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            values.extend(str(x) for x in event.get("warnings", []))
            if event.get("error"):
                values.append(str(event["error"]))
    return sorted(set(values))


def region_features(region: dict, index: int, n_regions: int,
                    tokens: list[dict], width: float, height: float,
                    route: str, category: str, split: str, doc_group: str,
                    image_id: int, page_no: int, page_role: str) -> dict:
    box = region["bbox"]
    token_rows = [token for token in tokens if center_inside(token["bbox"], box)]
    width_px = max(0.0, box["x1"] - box["x0"])
    height_px = max(0.0, box["y1"] - box["y0"])
    return {
        "image_id": image_id,
        "page_no": page_no,
        "doc_group": doc_group,
        "doc_category": category,
        "split": split,
        "page_role": page_role,
        "route": route,
        "region_index": index,
        "raw_label": region["label"],
        "normalized_role": region["label"].lower(),
        "bbox": box,
        "confidence": region.get("confidence"),
        "region_area_px": round(area(box), 2),
        "region_area_fraction": round(area(box) / (width * height), 6) if width and height else None,
        "width_fraction": round(width_px / width, 6) if width else None,
        "height_fraction": round(height_px / height, 6) if height else None,
        "aspect_ratio": round(width_px / height_px, 6) if height_px else None,
        "region_index_fraction": round(index / (n_regions - 1), 6) if n_regions > 1 else 0.0,
        "page_region_count": n_regions,
        "ocr_child_count": len(token_rows),
        "ocr_child_chars": sum(len(str(token.get("text", ""))) for token in token_rows),
    }


def table_info(table: dict, region_box: dict) -> dict:
    box = table.get("bbox")
    if not box:
        return {"id": table.get("id"), "iou": 0.0, "intersection_over_region": 0.0}
    return {
        "id": table.get("id"),
        "iou": round(matching.bbox_iou(region_box, box), 4),
        "intersection_over_region": round(matching.containment_fraction(region_box, box), 4),
        "intersection_over_table": round(matching.containment_fraction(box, region_box), 4),
        "n_rows": table.get("n_rows"),
        "n_cols": table.get("n_cols"),
        "n_cells": len(table.get("cells", [])),
        "nonempty_cells": sum(bool(cell.get("text")) for cell in table.get("cells", [])),
        "text_chars": sum(len(str(cell.get("text", ""))) for cell in table.get("cells", [])),
        "confidence": table.get("confidence"),
    }


def verification_summary(page: dict) -> dict:
    statuses = Counter()
    for element in page.get("elements", []):
        verification = element.get("extra", {}).get("verification")
        if verification:
            statuses[verification.get("status", "unknown")] += 1
    table_confidence = [table.get("confidence") for table in page.get("tables", [])]
    return {
        "element_statuses": dict(sorted(statuses.items())),
        "table_confidences": table_confidence,
        "suspicious_elements": statuses.get("suspicious", 0),
        "invalid_elements": statuses.get("invalid", 0),
    }


def build_rows(manifest: dict, index: dict) -> tuple[list[dict], list[dict], dict]:
    by_id = {row["image_id"]: row for row in index["records"]}
    if len(by_id) != len(index["records"]):
        raise RuntimeError("baseline index contains duplicate image IDs")
    if len(by_id) != len(manifest["records"]):
        raise RuntimeError("baseline index does not cover the frozen manifest")
    rows: list[dict] = []
    page_rows: list[dict] = []
    all_regions: list[dict] = []

    for item in manifest["records"]:
        run_row = by_id[item["image_id"]]
        if run_row.get("status") != "complete":
            raise RuntimeError(f"incomplete baseline row: {item['image_id']}")
        run_dir = ROOT / run_row["run"]
        layout = load(run_dir / "layout" / "page-001.json")
        ocr = load(run_dir / "ocr" / "page-001.json")
        document = load(run_dir / "final" / "document.json")
        metadata = load(run_dir / "metadata.json")
        table_raw = load(run_dir / "tables" / "page-001.json")
        page = document["pages"][0]
        regions = layout.get("regions", [])
        tokens = ocr.get("tokens", [])
        tables = page.get("tables", [])
        elements = page.get("elements", [])
        warnings = warning_strings(run_dir, metadata, layout, ocr, table_raw, page)
        vsummary = verification_summary(page)
        page_row = {
            "image_id": item["image_id"],
            "file_name": item["file_name"],
            "doc_group": item["doc_group"],
            "doc_category": item["doc_category"],
            "split": item["split"],
            "page_no": item["page_no"],
            "role": item["role"],
            "route": metadata.get("route"),
            "route_reason": metadata.get("route_reason"),
            "page_source_route": page.get("source_route"),
            "layout_backend": layout.get("backend"),
            "ocr_backend": ocr.get("backend"),
            "table_backend": table_raw.get("backend"),
            "n_regions": len(regions),
            "n_ocr_tokens": len(tokens),
            "n_tables": len(tables),
            "warnings": warnings,
            "warning_flags": {
                "any": bool(warnings),
                "fallback": any("fallback" in warning.lower() for warning in warnings),
                "ownership": any(any(word in warning.lower() for word in ("owner", "ownership", "conflict", "duplicate")) for warning in warnings),
                "table_quality": any("table quality" in warning.lower() for warning in warnings),
                "ocr": any("ocr" in warning.lower() for warning in warnings),
            },
            "verification": vsummary,
        }
        page_rows.append(page_row)
        for idx, region in enumerate(regions):
            all_regions.append(region_features(
                region, idx, len(regions), tokens, page["width"], page["height"],
                metadata.get("route"), item["doc_category"], item["split"],
                item["doc_group"], item["image_id"], item["page_no"],
                item["role"],
            ))

        for gt_table in item.get("tables", []):
            gt_bbox = bbox_from_coco(gt_table["bbox"])
            candidates = candidate_rows(gt_bbox, regions)
            verdict, detail = matching.classify_match(gt_bbox, candidates)
            contributor_indices = detail.get("contributing_region_indices", []) if verdict == "MULTIPLE_MATCH" else []
            if verdict == "MULTIPLE_MATCH":
                matched_indices = list(contributor_indices)
            else:
                index_value = detail.get("matched_region_index")
                matched_indices = [] if index_value is None else [index_value]
            matched_regions = []
            for index_value in matched_indices:
                if index_value >= len(regions):
                    continue
                rf = region_features(
                    regions[index_value], index_value, len(regions), tokens,
                    page["width"], page["height"], metadata.get("route"),
                    item["doc_category"], item["split"], item["doc_group"],
                    item["image_id"], item["page_no"],
                    item["role"],
                )
                element = elements[index_value] if index_value < len(elements) else None
                owner_table_id = element.get("table_id") if element else None
                final_table = next((table for table in tables if table.get("id") == owner_table_id), None)
                near_tables = [table_info(table, regions[index_value]["bbox"]) for table in tables
                               if intersection(regions[index_value]["bbox"], table.get("bbox", {})) > 0]
                match_metrics = next(
                    (candidate for candidate in candidates if candidate["region_index"] == index_value),
                    {},
                )
                rf.update({
                    "n_tables": len(tables),
                    "match_iou": match_metrics.get("iou"),
                    "intersection_over_gt": match_metrics.get("intersection_over_gt"),
                    "intersection_over_region": match_metrics.get("intersection_over_region"),
                    "match_region_area_ratio": match_metrics.get("region_area_ratio"),
                    "match_center_distance_px": match_metrics.get("bbox_center_distance_px"),
                    "table_gate_pass": regions[index_value]["label"].lower() == "table",
                    "final_ir_element_type": element.get("type") if element else None,
                    "final_ir_element_id": element.get("id") if element else None,
                    "final_ir_table_id": owner_table_id,
                    "final_table_object": table_info(final_table, regions[index_value]["bbox"]) if final_table else None,
                    "nearby_table_objects": near_tables,
                    "material_nearby_table_objects": [
                        table for table in near_tables
                        if table.get("iou", 0) >= 0.1 or table.get("intersection_over_table", 0) >= 0.5
                    ],
                    "multiple_regions_contributed": verdict == "MULTIPLE_MATCH",
                    "element_bbox_matches_region": bool(element and element.get("bbox") == regions[index_value]["bbox"]),
                    "final_element_text_chars": len(str(element.get("text") or "")) if element else 0,
                })
                matched_regions.append(rf)
            wrong_labels = sorted({r["raw_label"] for r in matched_regions if not r["table_gate_pass"]})
            if verdict != "MULTIPLE_MATCH" and matched_regions and not matched_regions[0]["table_gate_pass"]:
                wrong_labels = sorted(set(wrong_labels + [matched_regions[0]["raw_label"]]))
            strict_d2 = (
                bool(matched_regions) and any(not row["table_gate_pass"] for row in matched_regions)
                if verdict == "MULTIPLE_MATCH"
                else bool(matched_regions and not matched_regions[0]["table_gate_pass"] and matched_regions[0]["final_table_object"] is None)
            )
            rows.append({
                "image_id": item["image_id"],
                "file_name": item["file_name"],
                "doc_group": item["doc_group"],
                "doc_category": item["doc_category"],
                "split": item["split"],
                "page_no": item["page_no"],
                "role": item["role"],
                "route": metadata.get("route"),
                "gt_table_id": gt_table["id"],
                "gt_bbox_px": gt_bbox,
                "verdict": verdict,
                "verdict_detail": detail,
                "top_candidates": candidates[:8],
                "matched_regions": matched_regions,
                "matched_region": matched_regions[0] if len(matched_regions) == 1 else None,
                "strict_d2_wrong_labels": wrong_labels,
                "strict_d2": strict_d2,
                "page_context": page_row,
            })

    # Retrospective region reuse is added after all GT rows exist.  This is a
    # diagnostic ownership signal, not a change to strict-D2 classification.
    region_users: defaultdict[tuple[int, int], list[int]] = defaultdict(list)
    for row_index, row in enumerate(rows):
        for region in row["matched_regions"]:
            region_users[(row["image_id"], region["region_index"])].append(row_index)
    for row in rows:
        others = []
        for region in row["matched_regions"]:
            users = [rows[i]["gt_table_id"] for i in region_users[(row["image_id"], region["region_index"])] if rows[i] is not row]
            region["shared_region_with_other_gt_tables"] = sorted(set(users))
            others.extend(users)
        row["shared_region_with_other_gt_tables"] = sorted(set(others))

    for region in all_regions:
        users = [row for row in rows if row["image_id"] == region["image_id"]
                 and any(m["region_index"] == region["region_index"] for m in row["matched_regions"])]
        d2_users = [row for row in users if row["strict_d2"]]
        region["matched_gt_table_count"] = len(users)
        region["strict_d2_gt_table_count"] = len(d2_users)
        region["strict_d2_associated"] = bool(d2_users)

    return rows, page_rows, {"regions": all_regions}


def by_key_counts(rows: list[dict], key: str) -> dict:
    groups: defaultdict[str, dict[str, int]] = defaultdict(lambda: {"all": 0, "d2": 0})
    for row in rows:
        value = row.get(key)
        if value is None:
            value = "<none>"
        value = str(value)
        groups[value]["all"] += 1
        groups[value]["d2"] += int(row["strict_d2"])
    return {
        value: {**counts, "rate": round(counts["d2"] / counts["all"], 6) if counts["all"] else 0.0}
        for value, counts in sorted(groups.items())
    }


def region_label_summary(regions: list[dict], d2_labels: set[str]) -> dict:
    result: defaultdict[str, dict[str, int]] = defaultdict(lambda: {
        "all_non_table_regions": 0,
        "strict_d2_associated_regions": 0,
        "control_non_table_regions": 0,
        "control_pages_with_label": 0,
        "pages": 0,
    })
    control_pages: defaultdict[str, set[int]] = defaultdict(set)
    all_pages: defaultdict[str, set[int]] = defaultdict(set)
    for region in regions:
        label = region["raw_label"]
        if label == "table":
            continue
        row = result[label]
        row["all_non_table_regions"] += 1
        row["strict_d2_associated_regions"] += int(region["strict_d2_associated"])
        all_pages[label].add(region["image_id"])
        if region["page_role"] == "non_table_control_page":
            row["control_non_table_regions"] += 1
            control_pages[label].add(region["image_id"])
    for label, row in result.items():
        row["pages"] = len(all_pages[label])
        row["control_pages_with_label"] = len(control_pages[label])
        row["is_observed_d2_label"] = label in d2_labels
        row["region_d2_association_rate"] = round(row["strict_d2_associated_regions"] / row["all_non_table_regions"], 6) if row["all_non_table_regions"] else 0.0
    return dict(sorted(result.items()))


def selected_region_label(row: dict) -> str:
    matched = row.get("matched_region")
    if matched is not None:
        return matched.get("raw_label") or "<none>"
    labels = sorted({region.get("raw_label") for region in row.get("matched_regions", []) if region.get("raw_label")})
    if labels:
        return "<multiple:" + "+".join(labels) + ">"
    return "<none>"


def by_selected_region_label(rows: list[dict]) -> dict:
    groups: defaultdict[str, dict[str, int]] = defaultdict(lambda: {"all": 0, "d2": 0})
    for row in rows:
        value = selected_region_label(row)
        groups[value]["all"] += 1
        groups[value]["d2"] += int(row["strict_d2"])
    return {
        value: {**counts, "rate": round(counts["d2"] / counts["all"], 6) if counts["all"] else 0.0}
        for value, counts in sorted(groups.items())
    }


def feature_summary(rows: list[dict], key: str) -> dict:
    d2 = [row for row in rows if row["strict_d2"] and row["matched_region"] is not None]
    non = [row for row in rows if not row["strict_d2"] and row["matched_region"] is not None]
    return {
        "d2": quantiles([row["matched_region"].get(key) for row in d2]),
        "non_d2": quantiles([row["matched_region"].get(key) for row in non]),
    }


def descriptive_thresholds(rows: list[dict]) -> dict:
    """Post-outcome descriptive bins; explicitly not selector thresholds."""
    eligible = [row for row in rows if row.get("matched_region") is not None]
    rules = {
        "region_area_fraction_ge_0_4": lambda m: m.get("region_area_fraction", 0) >= 0.4,
        "aspect_ratio_ge_5": lambda m: m.get("aspect_ratio", 0) >= 5,
        "page_region_count_ge_20": lambda m: m.get("page_region_count", 0) >= 20,
        "ocr_child_count_le_1": lambda m: m.get("ocr_child_count", 0) <= 1,
        "ocr_child_count_eq_0": lambda m: m.get("ocr_child_count", 0) == 0,
    }
    result = {}
    for name, predicate in rules.items():
        selected = [row for row in eligible if predicate(row["matched_region"])]
        d2 = sum(row["strict_d2"] for row in selected)
        non_d2 = len(selected) - d2
        result[name] = {
            "eligible_rows": len(eligible),
            "selected_rows": len(selected),
            "d2_rows": d2,
            "non_d2_rows": non_d2,
            "d2_share_among_selected": round(d2 / len(selected), 6) if selected else 0.0,
            "d2_recall_among_eligible": round(d2 / sum(row["strict_d2"] for row in eligible), 6) if any(row["strict_d2"] for row in eligible) else 0.0,
        }
    return result


def label_stability(rows: list[dict], d2_labels: set[str]) -> dict:
    result = {}
    for label in sorted(d2_labels):
        label_rows = [row for row in rows if label in row["strict_d2_wrong_labels"]]
        result[label] = {
            "all_d2_cases": len(label_rows),
            "development_d2_cases": sum(row["split"] == "development" for row in label_rows),
            "held_out_d2_cases_descriptive": sum(row["split"] == "held_out_test" for row in label_rows),
            "all_source_groups": len({row["doc_group"] for row in label_rows}),
            "development_source_groups": len({row["doc_group"] for row in label_rows if row["split"] == "development"}),
            "all_categories": len({row["doc_category"] for row in label_rows}),
            "development_categories": len({row["doc_category"] for row in label_rows if row["split"] == "development"}),
        }
    return result


def control_feature_exposure(regions: list[dict], d2_labels: set[str]) -> dict:
    controls = [region for region in regions if region["page_role"] == "non_table_control_page" and region["raw_label"] != "table"]
    rules = {
        "raw_label_in_observed_d2_labels": lambda region: region["raw_label"] in d2_labels,
        "raw_label_document_index": lambda region: region["raw_label"] == "document_index",
        "ocr_child_count_le_1": lambda region: region["ocr_child_count"] <= 1,
        "ocr_child_count_eq_0": lambda region: region["ocr_child_count"] == 0,
        "page_region_count_ge_20": lambda region: region["page_region_count"] >= 20,
        "region_area_fraction_ge_0_4": lambda region: region["region_area_fraction"] >= 0.4,
        "aspect_ratio_ge_5": lambda region: region["aspect_ratio"] >= 5,
        "document_index_and_ocr_le_1": lambda region: region["raw_label"] == "document_index" and region["ocr_child_count"] <= 1,
    }
    result = {"control_non_table_regions": len(controls), "control_pages": len({region["image_id"] for region in controls}), "rules": {}}
    for name, predicate in rules.items():
        selected = [region for region in controls if predicate(region)]
        result["rules"][name] = {
            "regions": len(selected),
            "pages": len({region["image_id"] for region in selected}),
            "fraction_of_control_non_table_regions": round(len(selected) / len(controls), 6) if controls else 0.0,
        }
    return result


def taxonomy(row: dict) -> dict:
    matched = row.get("matched_region")
    regions = row.get("matched_regions", [])
    primary = "unclassified"
    secondary = None
    confidence = "medium"
    support: list[str] = []
    against: list[str] = [
        "The post-baseline record cannot establish causality or prove whole-page specialist absence.",
        "The matched region is selected retrospectively using GT geometry and is not itself a selector feature.",
    ]
    if row["verdict"] == "MULTIPLE_MATCH":
        primary = "multi_region_ownership_fragmentation"
        confidence = "high"
        support.append(f"035 MULTIPLE_MATCH rule identified {len(regions)} contributing regions covering the GT table.")
        if any(not region["table_gate_pass"] for region in regions):
            support.append("At least one contributor fails the explicit table-region gate.")
        secondary = "wrong_role_ownership" if any(not region["table_gate_pass"] for region in regions) else None
    elif matched is None:
        primary = "no_region_match"
        confidence = "high"
        support.append("No matched layout region passed the frozen matching threshold.")
        against.append("This is near-D2 evidence, not strict D2 under the frozen definition.")
    else:
        if matched.get("shared_region_with_other_gt_tables"):
            primary = "cross_table_contamination_or_shared_region"
            confidence = "high"
            support.append("The same production region is retrospectively matched to another GT table on the page.")
            secondary = "wrong_role_ownership"
        elif matched.get("material_nearby_table_objects"):
            primary = "table_object_present_but_not_correctly_attached"
            confidence = "high"
            support.append("A production table object overlaps the relevant non-table region, but is not the matched region's owner.")
            secondary = "wrong_role_ownership"
        elif matched.get("intersection_over_gt", 0) < 0.5:
            primary = "partial_non_table_ownership"
            confidence = "medium"
            support.append(f"The best non-table region covers only {matched.get('intersection_over_gt', 0):.3f} of the GT box.")
            secondary = "geometry_or_region_fragmentation"
        else:
            primary = "wrong_role_ownership"
            confidence = "high" if matched.get("match_iou", 0) >= 0.75 else "medium"
            support.append(f"The matched region is labelled {matched.get('raw_label')!r}, not table, and has IoU {matched.get('match_iou', 0):.3f}.")
        if matched.get("match_region_area_ratio", 0) >= 2 or matched.get("intersection_over_region", 1) < 0.25:
            secondary = "oversized_region_geometry"
            support.append("The matched region is materially larger than the GT table or only a small part of it overlaps.")
    if matched and matched.get("ocr_child_count", 0) == 0:
        against.append("No OCR child token falls inside the matched region; OCR interaction is therefore not directly evidenced.")
    elif matched:
        support.append(f"The matched region contains {matched.get('ocr_child_count', 0)} production OCR child token(s) under center containment.")
    if row["page_context"].get("warning_flags", {}).get("any"):
        support.append("The raw run carries one or more pipeline/page warnings; these are reported separately and are not treated as causal proof.")
    return {
        "image_id": row["image_id"],
        "gt_table_id": row["gt_table_id"],
        "doc_group": row["doc_group"],
        "doc_category": row["doc_category"],
        "split": row["split"],
        "primary_mechanism_candidate": primary,
        "secondary_mechanism_candidate": secondary,
        "assignment_confidence": confidence,
        "evidence_supporting_assignment": support,
        "evidence_against_causal_assignment": against,
    }


def main() -> int:
    manifest = load(MANIFEST_PATH)
    index = load(INDEX_PATH)
    rows, pages, region_payload = build_rows(manifest, index)
    all_regions = region_payload["regions"]
    strict = [row for row in rows if row["strict_d2"]]
    development = [row for row in strict if row["split"] == "development"]
    held_out = [row for row in strict if row["split"] == "held_out_test"]
    d2_labels = {label for row in strict for label in row["strict_d2_wrong_labels"]}
    d2_groups = Counter(row["doc_group"] for row in development)
    d2_categories = Counter(row["doc_category"] for row in development)
    d2_page_regions = {(row["image_id"], region["region_index"])
                       for row in strict for region in row["matched_regions"]
                       if not region["table_gate_pass"]}
    shared = [row for row in strict if row["shared_region_with_other_gt_tables"]]
    nearby = [row for row in strict if any(region.get("nearby_table_objects") for region in row["matched_regions"])]
    no_region = [row for row in rows if row["verdict"] == "NO_REGION"]
    ambiguous = [row for row in rows if row["verdict"] == "AMBIGUOUS"]

    case_payload = {
        "experiment": "039_larger_real_corpus",
        "analysis": "independent_forensic_recomputation",
        "source_files": [
            "population_manifest.json",
            "population_audit.json",
            "results/baseline_run_index.json",
            "results/baseline_runs/<image_id>/{metadata,layout,ocr,tables,final,logs}",
            "experiments/035_mechanism_d_gating/matching_lib.py",
        ],
        "boundary": "Post-baseline descriptive analysis. GT geometry is used only to reconstruct outcomes; no treatment or selector is run.",
        "matching_recomputed": True,
        "baseline_records": len(index["records"]),
        "table_annotations": len(rows),
        "strict_d2_counts": {"all": len(strict), "development": len(development), "held_out_test": len(held_out)},
        "cases": [
            {**row, "taxonomy": taxonomy(row)}
            for row in strict
        ],
        "near_d2": {
            "no_region_cases": [{"image_id": row["image_id"], "gt_table_id": row["gt_table_id"], "doc_group": row["doc_group"], "doc_category": row["doc_category"], "split": row["split"], "top_candidates": row["top_candidates"]} for row in no_region],
            "ambiguous_cases": [{"image_id": row["image_id"], "gt_table_id": row["gt_table_id"], "doc_group": row["doc_group"], "doc_category": row["doc_category"], "split": row["split"], "top_candidates": row["top_candidates"]} for row in ambiguous],
        },
    }
    (HERE / "039_D2_FORENSIC_CASES.json").write_text(json.dumps(case_payload, indent=2, ensure_ascii=False) + "\n")

    taxonomy_payload = {
        "experiment": "039_larger_real_corpus",
        "definition": "Descriptive case assignment; not causal proof.",
        "counts": dict(Counter(item["taxonomy"]["primary_mechanism_candidate"] for item in case_payload["cases"])),
        "cases": [{
            "image_id": item["image_id"], "gt_table_id": item["gt_table_id"],
            "doc_group": item["doc_group"], "doc_category": item["doc_category"],
            "split": item["split"], "strict_d2": item["strict_d2"],
            "primary_mechanism_candidate": item["taxonomy"]["primary_mechanism_candidate"],
            "secondary_mechanism_candidate": item["taxonomy"]["secondary_mechanism_candidate"],
            "assignment_confidence": item["taxonomy"]["assignment_confidence"],
            "evidence_supporting_assignment": item["taxonomy"]["evidence_supporting_assignment"],
            "evidence_against_causal_assignment": item["taxonomy"]["evidence_against_causal_assignment"],
        } for item in case_payload["cases"]],
    }
    (HERE / "039_D2_TAXONOMY.json").write_text(json.dumps(taxonomy_payload, indent=2, ensure_ascii=False) + "\n")

    matched_comparisons = {
        "experiment": "039_larger_real_corpus",
        "row_unit": "GT table annotation; a page with multiple GT tables contributes multiple rows",
        "region_unit": "unique production layout region; used for control/false-positive exposure summaries",
        "strict_d2_definition": "035-compatible strict D2, recomputed from raw layout/final outputs",
        "table_annotation_counts": {
            "all": len(rows), "strict_d2": len(strict), "non_d2": len(rows) - len(strict),
            "development_strict_d2": len(development), "held_out_strict_d2_descriptive": len(held_out),
        },
        "verdict_counts": dict(Counter(row["verdict"] for row in rows)),
        "by_split": by_key_counts(rows, "split"),
        "by_category": by_key_counts(rows, "doc_category"),
        "by_route": by_key_counts(rows, "route"),
        "by_doc_group": by_key_counts(rows, "doc_group"),
        "by_raw_label_of_selected_region": by_selected_region_label(rows),
        "development_d2_groups": dict(sorted(d2_groups.items())),
        "development_d2_categories": dict(sorted(d2_categories.items())),
        "development_d2_raw_labels": sorted(d2_labels),
        "adequacy_gate": {
            "minimum_development_strict_d2": 12,
            "minimum_source_groups": 6,
            "minimum_raw_labels": 3,
            "minimum_categories": 4,
            "maximum_single_group_fraction": 0.5,
            "development_strict_d2": len(development),
            "development_source_groups": len(d2_groups),
            "development_raw_labels": len(d2_labels),
            "development_categories": len(d2_categories),
            "largest_group": d2_groups.most_common(1)[0] if d2_groups else [None, 0],
            "largest_group_fraction": round((d2_groups.most_common(1)[0][1] / len(development)) if development else 0.0, 6),
            "status": "039_READY_FOR_POLICY_DESIGN" if len(development) >= 12 and len(d2_groups) >= 6 and len(d2_labels) >= 3 and len(d2_categories) >= 4 and (d2_groups.most_common(1)[0][1] <= len(development) / 2 if development else False) else "039_BLOCKED_INSUFFICIENT_DIVERSITY",
        },
        "feature_comparisons_d2_vs_non_d2": {
            key: feature_summary(rows, key)
            for key in ("region_area_fraction", "aspect_ratio", "region_index_fraction", "page_region_count", "ocr_child_count", "ocr_child_chars", "n_tables")
        },
        "descriptive_numeric_bins_not_selector_thresholds": descriptive_thresholds(rows),
        "raw_label_cross_group_stability": label_stability(rows, d2_labels),
        "control_feature_exposure": control_feature_exposure(all_regions, d2_labels),
        "region_label_summary": region_label_summary(all_regions, d2_labels),
        "region_level": {
            "all_regions": len(all_regions),
            "non_table_regions": sum(region["raw_label"] != "table" for region in all_regions),
            "strict_d2_associated_unique_regions": len(d2_page_regions),
            "shared_region_d2_rows": len(shared),
            "strict_d2_rows_with_nearby_table_object": len(nearby),
            "strict_d2_rows_with_material_nearby_table_object": sum(any(region.get("material_nearby_table_objects") for region in row["matched_regions"]) for row in strict),
            "control_pages": sum(page["role"] == "non_table_control_page" for page in pages),
            "control_pages_with_any_observed_d2_label": sum(page["role"] == "non_table_control_page" and any(region["raw_label"] in d2_labels for region in all_regions if region["image_id"] == page["image_id"]) for page in pages),
            "control_regions_with_any_observed_d2_label": sum(region["page_role"] == "non_table_control_page" and region["raw_label"] in d2_labels for region in all_regions),
        },
        "run_provenance": {
            "routes": dict(Counter(page["route"] for page in pages)),
            "layout_backends": dict(Counter(page["layout_backend"] for page in pages)),
            "ocr_backends": dict(Counter(page["ocr_backend"] for page in pages)),
            "table_backends": dict(Counter(page["table_backend"] for page in pages)),
            "pages_with_warnings": sum(bool(page["warnings"]) for page in pages),
            "pages_with_fallback_warning": sum(page["warning_flags"]["fallback"] for page in pages),
            "pages_with_ownership_warning": sum(page["warning_flags"]["ownership"] for page in pages),
            "layout_confidence_non_null": sum(region.get("confidence") is not None for region in all_regions),
        },
        "d2_end_to_end_proxies": {
            "final_ir_element_types": dict(Counter(region["final_ir_element_type"] for row in strict for region in row["matched_regions"])),
            "d2_rows_with_any_nonempty_final_region_text": sum(any(region["final_element_text_chars"] > 0 for region in row["matched_regions"]) for row in strict),
            "d2_rows_with_no_final_table_owner": sum(all(region["final_ir_table_id"] is None for region in row["matched_regions"]) for row in strict),
            "d2_rows_with_nearby_table_object": len(nearby),
            "d2_rows_with_material_nearby_table_object": sum(any(region.get("material_nearby_table_objects") for region in row["matched_regions"]) for row in strict),
            "d2_rows_with_shared_region": len(shared),
            "d2_matched_region_ocr_child_count": quantiles([region["ocr_child_count"] for row in strict for region in row["matched_regions"]]),
            "d2_final_region_text_chars": quantiles([region["final_element_text_chars"] for row in strict for region in row["matched_regions"]]),
        },
        "feature_boundary_notes": {
            "valid_pre_treatment_fields_observed": ["raw_label", "normalized_role", "layout confidence (all null in 039)", "region bbox geometry", "region index", "page region count", "OCR child count", "route", "category"],
            "forbidden_post_treatment_fields": ["GT bbox/table identity", "strict-D2 label", "forced-crop result", "post-treatment ownership/conflict", "held-out outcome"],
            "retrospective_matching_note": "The selected/matched region in these comparisons is GT-selected for audit and cannot be fed directly to a selector without a separately defined region-level policy.",
        },
    }
    (HERE / "039_MATCHED_COMPARISONS.json").write_text(json.dumps(matched_comparisons, indent=2, ensure_ascii=False) + "\n")

    print(json.dumps({
        "status": "forensic_artifacts_written",
        "table_annotations": len(rows),
        "strict_d2": len(strict),
        "development_strict_d2": len(development),
        "held_out_strict_d2": len(held_out),
        "unique_d2_regions": len(d2_page_regions),
        "shared_region_rows": len(shared),
        "nearby_table_object_rows": len(nearby),
        "no_region": len(no_region),
        "ambiguous": len(ambiguous),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
