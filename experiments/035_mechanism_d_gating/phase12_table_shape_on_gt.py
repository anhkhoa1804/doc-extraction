"""035 Phase 12 -- for every strict Mechanism-D (D2) case, would the
existing OCR-grid table-shape evidence (experiments/019_ocr_grid_table_
detection/table_candidate.py's detect_table_candidate(), the same
row_bands/col_bands primitive 031/033 built their own candidate rules on
top of) have recognized the region as table-shaped despite its wrong
Docling label? And, symmetrically, does that rule also fire on ordinary
D0 (correctly labelled, successfully processed) non-table prose regions
on the same pages -- the false-positive side within Phase 12's own scope
(Phase 13 does the full false-positive sweep separately, over ALL regions
labelled 'table' with no GT table, not just this rule).

Reuses table_candidate.py directly (import, not reimplementation) so this
milestone's numbers are computed by the SAME code 019/031 already used --
not a new, drifted reimplementation of "table-shaped."

Rule applied (033's own "best candidate" rule, FINAL_REPORT.md of 033):
row_bands >= 3 AND col_bands >= 2 AND children_per_row_band >= 1.5
(children_per_row_band := mean tokens per row band -- not tuned here,
taken verbatim from 033).

    python experiments/035_mechanism_d_gating/phase12_table_shape_on_gt.py
"""
from __future__ import annotations
import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "experiments" / "019_ocr_grid_table_detection"))
from table_candidate import Tok, cluster_rows, cluster_columns  # noqa: E402


def center_in(bbox, outer):
    cx = (bbox["x0"] + bbox["x1"]) / 2
    cy = (bbox["y0"] + bbox["y1"]) / 2
    return outer["x0"] <= cx <= outer["x1"] and outer["y0"] <= cy <= outer["y1"]


def shape_signature(tokens_in_bbox: list[dict]):
    toks = [Tok(text=t["text"], x0=t["bbox"]["x0"], y0=t["bbox"]["y0"],
                x1=t["bbox"]["x1"], y1=t["bbox"]["y1"]) for t in tokens_in_bbox if t.get("text")]
    if not toks:
        return {"row_bands": 0, "col_bands": 0, "children_per_row_band": 0.0, "n_tokens": 0}
    rows = cluster_rows(toks)
    col_bands = cluster_columns(rows)
    children_per_row = sum(len(r) for r in rows) / len(rows) if rows else 0.0
    return {
        "row_bands": len(rows), "col_bands": len(col_bands),
        "children_per_row_band": round(children_per_row, 3), "n_tokens": len(toks),
    }


def rule_033(sig) -> bool:
    return sig["row_bands"] >= 3 and sig["col_bands"] >= 2 and sig["children_per_row_band"] >= 1.5


def main():
    matching = json.loads((HERE / "table_region_matching.json").read_text())
    # mechanism_d_population.json's own strict_mechanism_d_count is the
    # cross-check target below; the full D2 (image, anno_id) set is
    # re-derived fresh from table_region_matching.json + classify_stage()
    # a few lines down rather than read from table_failure_funnel.json's
    # per_stage_example_cases, which is capped at 10 examples per stage.
    mech_d = json.loads((HERE / "mechanism_d_population.json").read_text())

    import matching_lib as ml
    CHUNK_DIRS = ml.gt_table_run_roots(HERE)
    ocr_by_image = {}
    layout_by_image = {}
    for cd in CHUNK_DIRS:
        if not cd.exists():
            continue
        for run_dir in cd.iterdir():
            meta_p = run_dir / "metadata.json"
            ocr_p = run_dir / "ocr" / "page-001.json"
            layout_p = run_dir / "layout" / "page-001.json"
            if meta_p.exists() and ocr_p.exists() and layout_p.exists():
                meta = json.loads(meta_p.read_text())
                ocr_by_image[meta["input_filename"]] = json.loads(ocr_p.read_text())["tokens"]
                layout_by_image[meta["input_filename"]] = json.loads(layout_p.read_text())["regions"]

    d2_results = []
    # table_region_matching.json (Phase 3's output) never contains "_stage"
    # -- phase4_9_14_funnel.py computes it in-memory but never rewrites
    # that file (confirmed in its own audit note). Re-derive D2 membership
    # here by importing classify_stage() itself (the single source of
    # truth), then cross-check the resulting COUNT against
    # mechanism_d_population.json's own total below.
    import importlib.util
    spec = importlib.util.spec_from_file_location("p4", HERE / "phase4_9_14_funnel.py")
    p4 = importlib.util.module_from_spec(spec)
    sys.modules["p4"] = p4
    spec.loader.exec_module(p4)

    raw_by_image = {}
    for cd in CHUNK_DIRS:
        if not cd.exists():
            continue
        for run_dir in cd.iterdir():
            meta_p = run_dir / "metadata.json"
            tables_p = run_dir / "tables" / "page-001.json"
            if meta_p.exists() and tables_p.exists():
                meta = json.loads(meta_p.read_text())
                raw_by_image[meta["input_filename"]] = json.loads(tables_p.read_text()).get("tables", [])

    for rec in matching["records"]:
        rec["_tables_raw_for_page"] = raw_by_image.get(rec["image"])
    for rec in matching["records"]:
        stage, _ = p4.classify_stage(rec)
        rec["_stage"] = stage

    for rec in matching["records"]:
        if rec["_stage"] != "D2":
            continue
        image = rec["image"]
        tokens = ocr_by_image.get(image, [])
        gt_bbox = rec["gt_bbox_px"]
        toks_in_gt = [t for t in tokens if center_in(t["bbox"], gt_bbox)]
        sig = shape_signature(toks_in_gt)
        d2_results.append({
            "image": image, "gt_table_anno_id": rec["gt_table_anno_id"],
            "wrong_label": rec["matched_region"]["internal_label_raw"] if rec["matched_region"] else None,
            "signature": sig, "would_rule_033_recognize": rule_033(sig),
        })

    n_recognized = sum(1 for r in d2_results if r["would_rule_033_recognize"])

    # False-positive check within this rule's scope: apply the SAME rule to
    # every D0 (correctly-labelled, successfully-processed) NON-table region
    # on the same set of pages, using each region's own bbox as the token
    # search window -- does the rule also fire where it shouldn't?
    fp_results = []
    n_non_table_regions_checked = 0
    n_non_table_regions_ge4_tokens = 0
    for image, regions in layout_by_image.items():
        tokens = ocr_by_image.get(image, [])
        for i, region in enumerate(regions):
            if region["label"].lower() == "table":
                continue
            n_non_table_regions_checked += 1
            toks_in_region = [t for t in tokens if center_in(t["bbox"], region["bbox"])]
            if len(toks_in_region) < 4:
                continue  # too few tokens for row/col clustering to mean anything
            n_non_table_regions_ge4_tokens += 1
            sig = shape_signature(toks_in_region)
            if rule_033(sig):
                fp_results.append({"image": image, "region_index": i, "label": region["label"], "signature": sig})

    payload = {
        "rule": "033's own best-candidate rule: row_bands>=3 AND col_bands>=2 "
            "AND children_per_row_band>=1.5, computed via experiments/019_"
            "ocr_grid_table_detection/table_candidate.py (imported, not "
            "reimplemented). Token search window: GT table bbox (for D2 "
            "recognition) / each non-table region's own bbox (for the "
            "false-positive side).",
        "d2_population_size_this_run": len(d2_results),
        "d2_population_size_mechanism_d_population_json": mech_d["strict_mechanism_d_count"],
        "population_size_cross_check_ok": len(d2_results) == mech_d["strict_mechanism_d_count"],
        "n_d2_cases_rule_would_recognize": n_recognized,
        "recognition_fraction": round(n_recognized / len(d2_results), 4) if d2_results else None,
        "d2_cases": d2_results,
        "false_positive_side": {
            "n_non_table_regions_checked": n_non_table_regions_checked,
            "n_non_table_regions_with_ge4_tokens": n_non_table_regions_ge4_tokens,
            "n_rule_fires_on_non_table_region": len(fp_results),
            "fire_fraction_of_eligible": (round(len(fp_results) / n_non_table_regions_ge4_tokens, 4)
                                           if n_non_table_regions_ge4_tokens else None),
            "examples": fp_results[:20],
        },
        "interpretation_note": "would_rule_033_recognize does NOT mean 'safe to "
            "auto-route to table processing' -- Phase 13 measures the full "
            "false-positive exposure (this sub-check only covers non-table "
            "regions on D2-relevant pages). A high recognition fraction here "
            "with a low false-positive fraction is what would make Option A/B "
            "(Phase 18) look attractive; either alone is not sufficient.",
    }
    Path(HERE / "table_shape_on_gt.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False))
    print(f"D2 cases: {len(d2_results)}, rule recognizes: {n_recognized} ({payload['recognition_fraction']})")
    print(f"false positives on non-table regions: {len(fp_results)} / {n_non_table_regions_checked}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
