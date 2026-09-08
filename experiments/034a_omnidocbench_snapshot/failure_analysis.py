"""034a Phase 9 -- per-page failure ranking.

IMPORTANT: the official evaluator's own output (metrics.json) does NOT
expose per-page/per-document scores through any file evaluate.py collects
-- verified directly this milestone: metrics[cat]['page'] is keyed by
metric name (e.g. 'Edit_dist'), whose value is itself an ATTRIBUTE-grouped
breakdown (data_source/language/layout/subset), not a per-image dict;
metrics[cat]['group']['sample_count'] is empty; run_summary.json has
environment/stage info only. This is a property of this evaluator version
mediated through evaluate.py's collected files, not a training-set-size
artifact (checked at both 6 and 77 samples).

So per-page ranking here uses a DELIBERATELY SIMPLE, clearly-labeled
APPROXIMATE proxy (difflib text similarity between the prediction .md and
a naive concatenation of the ground truth's own text_block spans) --
NEVER presented as the official metric, used only for RELATIVE ranking
to identify worst/best/median cases for qualitative inspection (Phase 9's
actual purpose).

    python experiments/034a_omnidocbench_snapshot/failure_analysis.py <results_dir> <dataset_dir>
"""
from __future__ import annotations
import difflib, json, re, sys
from pathlib import Path


def ground_truth_text(record):
    parts = []
    for d in record.get("layout_dets", []):
        if d.get("category_type") in ("text_block", "title"):
            t = d.get("text")
            if t:
                parts.append(t)
    return "\n".join(parts)


def main():
    results_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("experiments/034a_omnidocbench_snapshot/results/subset_B_fixed_auto")
    dataset_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("experiments/034a_omnidocbench_snapshot/dataset/subset")

    raw = json.loads((dataset_dir / "OmniDocBench.json").read_text())
    gt_by_image = {}
    for r in raw:
        name = Path(r["page_info"]["image_path"]).name
        gt_by_image[name] = r

    preds_dir = results_dir / "predictions"
    rows = []
    for pred_f in sorted(preds_dir.glob("*.md")):
        # prediction filename = image filename with .md extension (odb.OmniDocSample.prediction_filename)
        stem = pred_f.stem
        gt_record = None
        gt_image_name = None
        for name, r in gt_by_image.items():
            if Path(name).stem == stem:
                gt_record = r
                gt_image_name = name
                break
        if gt_record is None:
            continue
        pred_text = pred_f.read_text(encoding="utf-8", errors="replace")
        gt_text = ground_truth_text(gt_record)
        ratio = difflib.SequenceMatcher(None, pred_text, gt_text).ratio() if gt_text else None
        attr = gt_record["page_info"].get("page_attribute", {})
        rows.append({
            "prediction_file": pred_f.name, "image": gt_image_name,
            "data_source": attr.get("data_source"), "language": attr.get("language"),
            "subset": attr.get("subset"),
            "pred_len": len(pred_text), "gt_len": len(gt_text),
            "approx_similarity_ratio": round(ratio, 4) if ratio is not None else None,
        })

    scored = [r for r in rows if r["approx_similarity_ratio"] is not None]
    scored.sort(key=lambda r: r["approx_similarity_ratio"])

    worst10 = scored[:10]
    best10 = scored[-10:][::-1]
    mid = len(scored) // 2
    median3 = scored[max(0, mid-1):mid+2]

    payload = {
        "method": "APPROXIMATE proxy only -- difflib.SequenceMatcher ratio "
                 "between the prediction markdown and a naive newline-joined "
                 "concatenation of the ground truth's own text_block/title "
                 "spans. NOT the official OmniDocBench edit-distance metric "
                 "(which normalizes/tokenizes text and handles reading order "
                 "explicitly) -- used ONLY to rank pages for qualitative "
                 "worst/best/median inspection, since the official evaluator's "
                 "own collected output does not expose per-page scores "
                 "through any file available to this milestone (see module "
                 "docstring).",
        "n_scored": len(scored),
        "worst_10": worst10,
        "best_10": best10,
        "median_3": median3,
        "all_rows": rows,
    }
    out_name = f"failure_analysis_{results_dir.name}.json"
    Path(out_name).write_text(json.dumps(payload, indent=1, ensure_ascii=False))
    print(f"scored: {len(scored)}")
    print("WORST 10:")
    for r in worst10:
        print(f"  {r['approx_similarity_ratio']:<8} {r['image']} ({r['data_source']}, {r['language']})")
    print("BEST 10:")
    for r in best10:
        print(f"  {r['approx_similarity_ratio']:<8} {r['image']} ({r['data_source']}, {r['language']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
