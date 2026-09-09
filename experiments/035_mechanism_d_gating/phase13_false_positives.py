"""035 Phase 13 -- false-positive side. Internal regions labelled 'table'
that overlap NO GT table at all, over the stratified non-table-page sample
(build_non_table_sample.py, run separately AFTER the primary gt_tables
extraction to avoid CPU contention -- see that script's docstring).

For each: label, bbox, geometry, child text, table-shape evidence (033's
rule, reused via phase12's shape_signature), final table existence,
downstream impact. Classified as harmless over-detection / false table /
annotation mismatch / ambiguous.

    python experiments/035_mechanism_d_gating/phase13_false_positives.py
"""
from __future__ import annotations
import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
GT_FULL = HERE.parents[1] / "experiments" / "034a_omnidocbench_snapshot" / "dataset" / "full" / "OmniDocBench.json"
RUN_DIR = HERE / "results" / "non_table_sample" / "_doc_extraction_runs"

sys.path.insert(0, str(HERE))
from phase12_table_shape_on_gt import shape_signature, rule_033, center_in  # noqa: E402


def poly_to_bbox(poly):
    xs = poly[0::2]; ys = poly[1::2]
    return {"x0": min(xs), "y0": min(ys), "x1": max(xs), "y1": max(ys)}


def bbox_iou(a, b):
    x0 = max(a["x0"], b["x0"]); y0 = max(a["y0"], b["y0"])
    x1 = min(a["x1"], b["x1"]); y1 = min(a["y1"], b["y1"])
    if x1 <= x0 or y1 <= y0:
        return 0.0
    inter = (x1 - x0) * (y1 - y0)
    area_a = (a["x1"] - a["x0"]) * (a["y1"] - a["y0"])
    area_b = (b["x1"] - b["x0"]) * (b["y1"] - b["y0"])
    denom = area_a + area_b - inter
    return inter / denom if denom > 0 else 0.0


def main():
    gt_raw = json.loads(GT_FULL.read_text())
    gt_by_image = {r["page_info"]["image_path"]: r for r in gt_raw}

    if not RUN_DIR.exists():
        print(f"NOT YET RUN: {RUN_DIR} does not exist -- run prepare.py on "
              f"dataset/non_table_sample with --keep-runs first.", file=sys.stderr)
        return 1

    findings = []
    n_pages = 0
    n_table_labeled_regions_total = 0
    for run_dir in sorted(RUN_DIR.iterdir()):
        meta_p, layout_p, doc_p, ocr_p = (
            run_dir / "metadata.json", run_dir / "layout" / "page-001.json",
            run_dir / "final" / "document.json", run_dir / "ocr" / "page-001.json",
        )
        if not all(p.exists() for p in (meta_p, layout_p, doc_p)):
            continue
        n_pages += 1
        meta = json.loads(meta_p.read_text())
        fname = meta["input_filename"]
        gt_record = gt_by_image.get(fname)
        if gt_record is None:
            continue
        # Sanity: this page must genuinely have zero GT tables (population contract)
        gt_tables = [d for d in gt_record.get("layout_dets", []) if d.get("category_type") == "table"]
        gt_bboxes = [poly_to_bbox(t["poly"]) for t in gt_tables]

        layout = json.loads(layout_p.read_text())
        doc = json.loads(doc_p.read_text())
        elements = doc["pages"][0]["elements"]
        tables_in_ir = doc["pages"][0].get("tables", [])
        tokens = json.loads(ocr_p.read_text())["tokens"] if ocr_p.exists() else []

        for i, region in enumerate(layout["regions"]):
            if region["label"].lower() != "table":
                continue
            n_table_labeled_regions_total += 1
            b = region["bbox"]
            max_iou_vs_any_gt = max((bbox_iou(b, gtb) for gtb in gt_bboxes), default=0.0)
            if max_iou_vs_any_gt > 0.1:
                # Keep the record: silently dropping it made the declared
                # classification counts and audit trail disagree whenever
                # the supposedly no-table sample contained a GT overlap.
                classification = "annotation_mismatch"  # page-level "no table" contract violated by overlap -- investigate
                findings.append({
                    "image": fname, "region_index": i, "label": region["label"], "bbox": b,
                    "max_iou_vs_gt": max_iou_vs_any_gt,
                    "n_tokens_in_region": None, "shape_signature": None,
                    "rule_033_fires": None,
                    "final_table_object_present": None, "final_table_populated": None,
                    "classification": classification,
                })
                continue
            else:
                toks = [t for t in tokens if center_in(t["bbox"], b)]
                sig = shape_signature(toks)
                el = elements[i] if i < len(elements) else None
                table_id = el.get("table_id") if el else None
                table_obj = next((t for t in tables_in_ir if t.get("id") == table_id), None) if table_id else None
                downstream_populated = bool(table_obj and any((c.get("text") or "").strip() for c in table_obj.get("cells", [])))

                if rule_033(sig) and downstream_populated:
                    classification = "harmless_over_detection"  # genuinely table-shaped, just not GT-annotated (borderline/missed annotation, or a real small table GT skipped)
                elif not rule_033(sig) and not downstream_populated:
                    classification = "false_table"  # neither shape evidence nor populated content supports it
                else:
                    classification = "ambiguous"

                findings.append({
                    "image": fname, "region_index": i, "label": region["label"], "bbox": b,
                    "n_tokens_in_region": len(toks), "shape_signature": sig,
                    "rule_033_fires": rule_033(sig),
                    "final_table_object_present": table_obj is not None,
                    "final_table_populated": downstream_populated,
                    "classification": classification,
                })

    class_counts = {}
    for f in findings:
        class_counts[f["classification"]] = class_counts.get(f["classification"], 0) + 1

    result = {
        "source_run_dir": str(RUN_DIR.relative_to(HERE.parents[1])),
        "n_pages_processed": n_pages,
        "n_table_labeled_regions_on_no_gt_table_pages": n_table_labeled_regions_total,
        "n_findings_total": len(findings),
        "n_findings_no_gt_overlap": sum(f["classification"] != "annotation_mismatch" for f in findings),
        "n_annotation_mismatches": sum(f["classification"] == "annotation_mismatch" for f in findings),
        "classification_counts": class_counts,
        "classification_definitions": {
            "harmless_over_detection": "table-shaped by 033's own rule AND the final table "
                "has populated cell text -- plausibly a real small/borderline table the GT "
                "annotation simply didn't mark, not a pipeline defect.",
            "false_table": "neither shape evidence nor populated downstream content -- a "
                "genuine mislabel with no supporting evidence either way.",
            "ambiguous": "shape evidence and downstream content disagree.",
            "annotation_mismatch": "the region DOES overlap a GT table on this page (>0.1 "
                "IoU) despite the page being sampled as 'no GT table' -- a data-pipeline "
                "bug in this phase's own sampling, or a genuine annotation "
                "inconsistency; investigate rather than silently exclude.",
        },
        "risk_envelope_note": "This is the exposure any label-relaxation intervention "
            "(Phase 17/18 Option A/B) would inherit -- compare "
            "n_findings_no_gt_overlap against the D2 recovery count from Phase 12/mechanism_"
            "d_population.json to judge whether relaxing the gate trades few false losses "
            "for many new false positives, or the reverse.",
        "findings": findings,
    }
    Path(HERE / "false_positive_tables.json").write_text(json.dumps(result, indent=1, ensure_ascii=False))
    print(f"pages: {n_pages}, table-labeled regions checked: {n_table_labeled_regions_total}")
    print(f"findings (no GT overlap): {len(findings)}, classes: {class_counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
