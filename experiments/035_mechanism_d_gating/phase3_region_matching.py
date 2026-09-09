"""035 Phase 3 -- deterministic GT-table <-> internal-region matcher over
the full GT-table page population (results/gt_tables_chunk0 +
results/gt_tables_chunk1, built by build_gt_table_chunks.py, extracted
with --keep-runs on CPU -- see baseline.json for why CPU/targeted rather
than GPU/full-corpus).

For every GT table (665 across 458 pages), compares against every internal
layout region on that page (not just table-labelled ones -- that's the
whole point) using matching_lib's geometry primitives, and classifies the
match per the taxonomy: EXACT_MATCH / GOOD_MATCH / PARTIAL_MATCH /
MULTIPLE_MATCH / AMBIGUOUS / NO_REGION.

    python experiments/035_mechanism_d_gating/phase3_region_matching.py
"""
from __future__ import annotations
import json
from pathlib import Path
import matching_lib as ml

HERE = Path(__file__).resolve().parent
GT_FULL = HERE.parents[1] / "experiments" / "034a_omnidocbench_snapshot" / "dataset" / "full" / "OmniDocBench.json"
def build_candidates(gt_bbox, regions):
    cands = []
    for i, r in enumerate(regions):
        b = r["bbox"]
        iou = ml.bbox_iou(gt_bbox, b)
        i_over_gt = ml.containment_fraction(gt_bbox, b)  # intersection / gt_area
        i_over_region = ml.containment_fraction(b, gt_bbox)  # intersection / region_area
        if iou <= 0 and i_over_gt <= 0 and i_over_region <= 0:
            continue
        cands.append({
            "region_index": i, "label": r["label"], "bbox": b,
            "iou": round(iou, 4),
            "intersection_over_gt": round(i_over_gt, 4),
            "intersection_over_region": round(i_over_region, 4),
            "region_area_ratio": round(ml.bbox_area(b) / ml.bbox_area(gt_bbox), 4) if ml.bbox_area(gt_bbox) > 0 else None,
            "bbox_center_distance_px": round(ml.bbox_center_distance(gt_bbox, b), 2),
            "gt_centroid_in_region": ml.centroid_in_bbox(gt_bbox, b),
            "region_centroid_in_gt": ml.centroid_in_bbox(b, gt_bbox),
        })
    cands.sort(key=lambda c: c["intersection_over_gt"], reverse=True)
    return cands


def main():
    gt_raw = json.loads(GT_FULL.read_text())
    gt_by_image = {r["page_info"]["image_path"]: r for r in gt_raw}

    run_roots = ml.gt_table_run_roots(HERE)
    run_dirs = ml.gt_table_run_dirs(HERE)

    records = []
    n_pages_processed = 0
    n_pages_incomplete = 0
    n_pages_no_gt_match = 0
    verdict_counts = {}

    for run_dir in run_dirs:
        page_run = ml.load_page_run(run_dir)
        if page_run is None:
            n_pages_incomplete += 1
            continue
        fname = page_run["metadata"]["input_filename"]
        gt_record = gt_by_image.get(fname)
        if gt_record is None:
            n_pages_no_gt_match += 1
            continue
        n_pages_processed += 1

        regions = page_run["layout"]["regions"]
        doc_page = page_run["document"]["pages"][0]
        elements = doc_page["elements"]
        route = page_run["metadata"].get("route")
        backend_name = page_run["layout"].get("backend")
        page_attr = gt_record["page_info"].get("page_attribute", {})

        gt_tables = [d for d in gt_record.get("layout_dets", []) if d.get("category_type") == "table"]
        for gt_t in gt_tables:
            gt_bbox = ml.poly_to_bbox(gt_t["poly"])
            cands = build_candidates(gt_bbox, regions)
            verdict, detail = ml.classify_match(gt_bbox, cands)
            verdict_counts[verdict] = verdict_counts.get(verdict, 0) + 1

            # For a single matched-region verdict, pull the final-IR element at
            # that SAME positional index -- merge_regions_into_page assigns
            # element_id f"p{page}-e{i}" for region i, in order, before any
            # orphan-recovery elements are appended (matching_lib docstring).
            matched_region_detail = None
            single_idx = detail.get("matched_region_index")
            if single_idx is not None and single_idx < len(elements):
                el = elements[single_idx]
                region = regions[single_idx]
                nested = sum(
                    1 for j, other in enumerate(regions)
                    if j != single_idx and ml.containment_fraction(other["bbox"], region["bbox"]) >= 0.9
                )
                matched_region_detail = {
                    "region_index": single_idx,
                    "internal_label_raw": region["label"],
                    "label_lower": region["label"].lower(),
                    "table_gate_pass": region["label"].lower() == "table",
                    "confidence": region.get("confidence"),
                    "final_ir_element_type": el.get("type"),
                    "final_ir_table_id": el.get("table_id"),
                    "source_backend": el.get("source_backend"),
                    "nested_regions_within_match_bbox": nested,
                }

            contributing_detail = None
            if verdict == "MULTIPLE_MATCH":
                contrib = []
                for ridx in detail.get("contributing_region_indices", []):
                    if ridx < len(elements):
                        el = elements[ridx]
                        region = regions[ridx]
                        contrib.append({
                            "region_index": ridx, "internal_label_raw": region["label"],
                            "table_gate_pass": region["label"].lower() == "table",
                            "final_ir_element_type": el.get("type"),
                        })
                contributing_detail = contrib

            # final table object presence (regardless of which candidate)
            table_obj = None
            if matched_region_detail and matched_region_detail["final_ir_table_id"]:
                tid = matched_region_detail["final_ir_table_id"]
                table_obj = next((t for t in doc_page.get("tables", []) if t.get("id") == tid), None)

            records.append({
                "image": fname,
                "gt_table_anno_id": gt_t.get("anno_id"),
                "gt_order": gt_t.get("order"),
                "gt_bbox_px": gt_bbox,
                "data_source": page_attr.get("data_source"),
                "language": page_attr.get("language"),
                "layout_attr": page_attr.get("layout"),
                "special_issue": page_attr.get("special_issue", []),
                "route": route, "layout_backend": backend_name,
                "n_regions_on_page": len(regions),
                "verdict": verdict,
                "verdict_detail": detail,
                "top_candidates": cands[:5],
                "matched_region": matched_region_detail,
                "multiple_match_contributors": contributing_detail,
                "final_table_object": table_obj,
            })

    # Audit fix (035 preflight, Phase D item 5): see matching_lib.detect_region_reuse
    # docstring. ADDITIVE ONLY -- never changes verdict, threshold, or classification.
    n_collisions = ml.detect_region_reuse(records)

    payload = {
        "method": "See matching_lib.classify_match docstring for exact "
            "thresholds (round numbers, not tuned). Candidates built from "
            "EVERY internal layout region on the page, not only "
            "table-labelled ones -- Mechanism D is precisely about GT "
            "tables landing under a non-table label.",
        "source_run_dirs": [str(c.relative_to(HERE.parents[1])) for c in run_roots],
        "n_pages_available_in_runs": len(run_dirs),
        "n_pages_processed": n_pages_processed,
        "n_pages_incomplete_or_missing_artifacts": n_pages_incomplete,
        "n_pages_present_but_not_in_gt_index": n_pages_no_gt_match,
        "n_gt_tables_matched_total": len(records),
        "expected_total_gt_tables_in_full_population": 665,
        "coverage_fraction_of_full_gt_table_population": round(len(records) / 665, 4),
        "verdict_counts": verdict_counts,
        "n_region_reuse_collisions": n_collisions,
        "region_reuse_note": "count of (image, region_index) pairs matched by "
            ">1 GT table -- each affected record carries "
            "shared_region_with_other_gt_tables listing the other anno_ids "
            "involved. Non-zero values mean downstream D0/recovery counts "
            "may include one extracted table credited to multiple GT tables "
            "-- inspect before treating D0 counts as fully independent.",
        "records": records,
    }
    Path(HERE / "table_region_matching.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False))
    print(f"pages processed: {n_pages_processed} / {len(run_dirs)} available run dirs")
    print(f"GT tables matched: {len(records)} / 665")
    print(f"verdict counts: {verdict_counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
