"""031 Phase 4/5/6 -- signal discovery, deterministic table-shape probe, and
false-positive controls against genuine (non-table) picture regions.

Read-only, CPU-only, no new model dependency. Reuses the same band-
clustering logic 026 validated (group by mutual y-overlap, not a fixed
pixel tolerance) rather than inventing a new heuristic.

    python experiments/031_table_label_gating/table_shape_probe.py
"""
from __future__ import annotations
import json
import statistics
from collections import defaultdict
from pathlib import Path
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def band_count(boxes, axis):
    """Cluster boxes into bands by mutual overlap on the given axis (0=x,1=y).
    Same idea as 026's row-band clustering: group by overlap, not a magic
    pixel tolerance, then count distinct bands."""
    if not boxes:
        return 0
    lo_key, hi_key = ("x0", "x1") if axis == 0 else ("y0", "y1")
    items = sorted(boxes, key=lambda b: b[lo_key])
    bands = [[items[0]]]
    for b in items[1:]:
        band = bands[-1]
        ref = band[-1]
        lo, hi = max(b[lo_key], ref[lo_key]), min(b[hi_key], ref[hi_key])
        if hi > lo:  # any overlap keeps it in the same band
            band.append(b)
        else:
            bands.append([b])
    return len(bands)


def regularity(boxes, axis):
    """Coefficient of variation of gaps between consecutive band starts --
    LOW = regular grid spacing (table-like), HIGH = irregular (prose-like
    or scattered). Returns None if too few boxes to judge."""
    if len(boxes) < 3:
        return None
    key = "x0" if axis == 0 else "y0"
    vals = sorted({round(b[key], 0) for b in boxes})
    if len(vals) < 3:
        return None
    gaps = [b - a for a, b in zip(vals, vals[1:])]
    mean = statistics.mean(gaps)
    if mean == 0:
        return None
    return round(statistics.pstdev(gaps) / mean, 3)


def compute_signals(region_bbox, children):
    """All candidate signals from Phase 4, computed from what's ALREADY in
    the layout JSON -- no new model, no new field."""
    boxes = [c["bbox"] for c in children]
    n = len(boxes)
    w = region_bbox["x1"] - region_bbox["x0"]
    h = region_bbox["y1"] - region_bbox["y0"]
    area = max(1.0, w * h)
    text_area = sum((b["x1"] - b["x0"]) * (b["y1"] - b["y0"]) for b in boxes)
    return {
        "n_nested_text_regions": n,
        "aspect_ratio": round(w / h, 3) if h > 0 else None,
        "row_bands": band_count(boxes, axis=1),
        "col_bands": band_count(boxes, axis=0),
        "row_regularity_cv": regularity(boxes, axis=1),  # lower = more table-like
        "col_regularity_cv": regularity(boxes, axis=0),
        "text_density": round(text_area / area, 4),
        "children_per_row_band": round(n / max(1, band_count(boxes, axis=1)), 2),
    }


def table_shape_score(sig):
    """The probe itself: a small deterministic point-scoring rule, not a
    trained classifier. Each criterion is named so a false positive/negative
    can be attributed to the specific signal that misfired."""
    score, reasons = 0, []
    if sig["row_bands"] and sig["row_bands"] >= 2:
        score += 1; reasons.append("multi-row")
    if sig["col_bands"] and sig["col_bands"] >= 2:
        score += 1; reasons.append("multi-column")
    if sig["children_per_row_band"] and sig["children_per_row_band"] >= 2:
        score += 1; reasons.append("multiple children per row (grid, not a list)")
    if sig["row_regularity_cv"] is not None and sig["row_regularity_cv"] < 0.5:
        score += 1; reasons.append("regular row spacing")
    if sig["n_nested_text_regions"] >= 6:
        score += 1; reasons.append("high nested-text-region count")
    return score, reasons


def main():
    pop = json.loads((HERE / "gated_table_population.json").read_text())

    # rebuild children lists (population.json stored counts, not raw boxes;
    # recompute from source layout files for the signal computation)
    inv_root = REPO / "experiments/029_deep_forensic_replay"
    inv = json.loads((inv_root / "cohort_inventory.json").read_text())
    arm_roots = {(a["milestone"], a["arm"]): REPO / a["artifact_root"] for a in inv["arms"]}

    def overlap_frac(a, b):
        ix0, iy0 = max(a["x0"], b["x0"]), max(a["y0"], b["y0"])
        ix1, iy1 = min(a["x1"], b["x1"]), min(a["y1"], b["y1"])
        if ix1 <= ix0 or iy1 <= iy0:
            return 0.0
        inter = (ix1 - ix0) * (iy1 - iy0)
        area_b = max(1.0, (b["x1"] - b["x0"]) * (b["y1"] - b["y0"]))
        return inter / area_b

    rows = []
    for c in pop["candidates"]:
        root = arm_roots.get((c["milestone"], c["arm"]))
        if root is None:
            continue
        doc_dirs = [d for d in root.iterdir() if d.is_dir()
                   and d.name.rsplit("-", 1)[0] == c["document_id"]]
        if not doc_dirs:
            continue
        lf = doc_dirs[0] / "layout" / c["layout_file"]
        if not lf.exists():
            continue
        layout = json.loads(lf.read_text())
        regions = layout.get("regions") or []
        pbb = c["region_bbox"]
        children = [r for r in regions if r.get("bbox")
                   and overlap_frac(pbb, r["bbox"]) > 0.5
                   and (r.get("label") or "").lower() not in ("picture", "chart")]
        sig = compute_signals(pbb, children)
        score, reasons = table_shape_score(sig)
        rows.append({**c, "signals": sig, "table_shape_score": score,
                    "score_reasons": reasons, "is_table_ground_truth":
                    c["classification"] in ("CONFIRMED", "PROBABLE")})

    # === negative controls: genuine pictures (0 text children, filtered out of
    # Phase 2's candidate list) -- re-scan for these specifically ===
    negatives = []
    for a in inv["arms"]:
        if a["is_smoke_or_warmup"] or a["manifest"].startswith("NONE"):
            continue
        root = REPO / a["artifact_root"]
        if not root.exists():
            continue
        for doc_dir in sorted(root.iterdir()):
            if not doc_dir.is_dir():
                continue
            did = doc_dir.name.rsplit("-", 1)[0]
            layout_dir = doc_dir / "layout"
            if not layout_dir.exists():
                continue
            for lf in sorted(layout_dir.glob("*.json")):
                try:
                    layout = json.loads(lf.read_text())
                except Exception:
                    continue
                regions = layout.get("regions") or []
                pictures = [r for r in regions if (r.get("label") or "").lower() in ("picture", "chart")]
                for pic in pictures:
                    pbb = pic.get("bbox")
                    if pbb is None:
                        continue
                    children = [r for r in regions if r.get("bbox")
                               and overlap_frac(pbb, r["bbox"]) > 0.5
                               and (r.get("label") or "").lower() not in ("picture", "chart")]
                    if len(children) >= 1:
                        continue  # this is a candidate, already covered above
                    sig = compute_signals(pbb, [])
                    score, reasons = table_shape_score(sig)
                    negatives.append({
                        "milestone": a["milestone"], "arm": a["arm"], "document_id": did,
                        "layout_file": lf.name, "region_bbox": pbb,
                        "signals": sig, "table_shape_score": score,
                        "score_reasons": reasons, "is_table_ground_truth": False,
                    })

    # dedupe negatives to one representative per distinct document (many arms
    # replay the same picture identically)
    seen_docs = set()
    negatives_dedup = []
    for n in negatives:
        if n["document_id"] in seen_docs:
            continue
        seen_docs.add(n["document_id"])
        negatives_dedup.append(n)

    all_rows = rows + negatives_dedup
    positives = [r for r in all_rows if r["is_table_ground_truth"]]
    true_negatives_pool = [r for r in all_rows if not r["is_table_ground_truth"]]

    # threshold sweep (deterministic score is 0-5)
    sweep = []
    for thresh in range(0, 6):
        tp = sum(1 for r in positives if r["table_shape_score"] >= thresh)
        fn = len(positives) - tp
        fp = sum(1 for r in true_negatives_pool if r["table_shape_score"] >= thresh)
        tn = len(true_negatives_pool) - fp
        precision = tp / (tp + fp) if (tp + fp) else None
        recall = tp / (tp + fn) if (tp + fn) else None
        sweep.append({"threshold": thresh, "tp": tp, "fn": fn, "fp": fp, "tn": tn,
                      "precision": round(precision, 4) if precision is not None else None,
                      "recall": round(recall, 4) if recall is not None else None})

    # leave-document-out: does the score generalize, or is it fit to one document?
    by_doc_positive = defaultdict(list)
    for r in positives:
        by_doc_positive[r["document_id"]].append(r)
    ldo = []
    for held_out_doc in by_doc_positive:
        train_docs = set(by_doc_positive) - {held_out_doc}
        # threshold=3 chosen from the sweep as a reasonable operating point; the
        # SAME fixed rule (no per-fold tuning) is applied to the held-out document
        held_rows = by_doc_positive[held_out_doc]
        recovered = sum(1 for r in held_rows if r["table_shape_score"] >= 3)
        ldo.append({"held_out_document": held_out_doc,
                    "instances": len(held_rows),
                    "recovered_at_threshold_3": recovered,
                    "recovery_rate": round(recovered / len(held_rows), 4)})

    payload = {
        "note": "Diagnostic probe, deterministic point-score, NOT a trained/fitted "
               "classifier -- no per-document tuning. Purpose is diagnosis: how much "
               "existing evidence already distinguishes table-shaped pictures from "
               "genuine pictures, using only fields already in the layout JSON.",
        "positive_population": {"n": len(positives),
                                "distinct_documents": sorted({r["document_id"] for r in positives})},
        "negative_population": {"n": len(true_negatives_pool),
                                "distinct_documents": sorted({r["document_id"] for r in true_negatives_pool})},
        "threshold_sweep": sweep,
        "leave_document_out": ldo,
        "false_positives_at_threshold_3": [
            {"document_id": r["document_id"], "milestone": r["milestone"], "arm": r.get("arm"),
             "score": r["table_shape_score"], "reasons": r["score_reasons"], "signals": r["signals"]}
            for r in true_negatives_pool if r["table_shape_score"] >= 3],
        "false_negatives_at_threshold_3": [
            {"document_id": r["document_id"], "milestone": r["milestone"], "arm": r.get("arm"),
             "score": r["table_shape_score"], "reasons": r["score_reasons"], "signals": r["signals"]}
            for r in positives if r["table_shape_score"] < 3],
        "all_positive_rows": rows,
        "all_negative_rows": negatives_dedup,
    }
    Path("table_shape_probe.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False))

    print(f"positives: {len(positives)} ({len({r['document_id'] for r in positives})} docs)")
    print(f"negatives (deduped genuine pictures): {len(true_negatives_pool)} "
          f"({len({r['document_id'] for r in true_negatives_pool})} docs)")
    print("\nthreshold sweep:")
    for s in sweep:
        print(f"  t={s['threshold']} tp={s['tp']:<4} fn={s['fn']:<4} fp={s['fp']:<4} tn={s['tn']:<4} "
              f"precision={s['precision']} recall={s['recall']}")
    print("\nleave-document-out (threshold=3):")
    for l in ldo:
        print(f"  {l['held_out_document']:<30} {l['recovered_at_threshold_3']}/{l['instances']} "
              f"({l['recovery_rate']:.0%})")
    print(f"\nnegative document ids: {sorted({r['document_id'] for r in true_negatives_pool})}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
