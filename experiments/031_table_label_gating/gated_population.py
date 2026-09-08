"""031 Phase 2 -- enumerate every historical picture-labelled, table-shaped
region across all frozen IR (023-025), not just 025's 3 named documents.

Read-only, CPU-only. For every picture-labelled region on every page of
every replayed arm, compute table-shape signals from its geometry and its
Docling-emitted children (nested regions within its bbox, per the
traverse_pictures=True behavior confirmed in gating_contract.json), then
classify as CONFIRMED / PROBABLE / AMBIGUOUS gated-table candidate.

    python experiments/031_table_label_gating/gated_population.py
"""
from __future__ import annotations
import json
from collections import defaultdict
from pathlib import Path
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
L29 = REPO / "experiments/029_deep_forensic_replay"


def overlap_frac(a, b):
    ix0, iy0 = max(a["x0"], b["x0"]), max(a["y0"], b["y0"])
    ix1, iy1 = min(a["x1"], b["x1"]), min(a["y1"], b["y1"])
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    inter = (ix1 - ix0) * (iy1 - iy0)
    area_b = max(1.0, (b["x1"] - b["x0"]) * (b["y1"] - b["y0"]))
    return inter / area_b


def find_layout_json(doc_dir):
    layout_dir = doc_dir / "layout"
    if not layout_dir.exists():
        return None
    return sorted(layout_dir.glob("*.json"))


def main():
    inv = json.loads((L29 / "cohort_inventory.json").read_text())
    candidates = []
    scanned_arms = 0
    total_picture_regions = 0

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
            layout_files = find_layout_json(doc_dir)
            if not layout_files:
                continue
            scanned_arms += 1
            for lf in layout_files:
                try:
                    layout = json.loads(lf.read_text())
                except Exception:
                    continue
                regions = layout.get("regions") or []
                pictures = [r for r in regions if (r.get("label") or "").lower() in ("picture", "chart")]
                for pic in pictures:
                    total_picture_regions += 1
                    pbb = pic.get("bbox")
                    if pbb is None:
                        continue
                    children = [r for r in regions if r is not pic and r.get("bbox")
                               and overlap_frac(pbb, r["bbox"]) > 0.5]
                    text_children = [c for c in children if (c.get("label") or "").lower()
                                     not in ("picture", "chart", "table")]
                    n_children = len(children)
                    n_text_children = len(text_children)
                    width = pbb["x1"] - pbb["x0"]
                    height = pbb["y1"] - pbb["y0"]
                    area = max(1.0, width * height)
                    aspect = round(width / height, 3) if height > 0 else None

                    xs = sorted({round(c["bbox"]["x0"], 0) for c in text_children})
                    ys = sorted({round(c["bbox"]["y0"], 0) for c in text_children})

                    if n_text_children >= 6:
                        confidence_class = "CONFIRMED" if n_text_children >= 10 else "PROBABLE"
                    elif n_text_children >= 3:
                        confidence_class = "PROBABLE"
                    elif n_text_children >= 1:
                        confidence_class = "AMBIGUOUS"
                    else:
                        confidence_class = "NOT_A_CANDIDATE"

                    if confidence_class == "NOT_A_CANDIDATE":
                        continue

                    candidates.append({
                        "milestone": a["milestone"], "arm": a["arm"],
                        "document_id": did, "layout_file": lf.name,
                        "region_bbox": pbb, "region_label": pic.get("label"),
                        "area": round(area, 1), "aspect_ratio": aspect,
                        "n_nested_regions": n_children,
                        "n_nested_text_regions": n_text_children,
                        "n_distinct_x_bands": len(xs),
                        "n_distinct_y_bands": len(ys),
                        "classification": confidence_class,
                    })

    by_class = defaultdict(int)
    for c in candidates:
        by_class[c["classification"]] += 1
    by_doc = defaultdict(set)
    for c in candidates:
        by_doc[c["document_id"]].add(c["classification"])

    payload = {
        "method": "every 'picture'/'chart'-labelled region on every scanned layout "
                 "json in the replayed 023-025 corpus; children = any other region "
                 "on the same page overlapping >50% of the picture's own area (the "
                 "traverse_pictures=True nesting behavior confirmed in "
                 "gating_contract.json). Classification is by NESTED TEXT-CHILD "
                 "COUNT only, as a first-pass population filter -- Phase 4/5 add "
                 "geometric regularity signals on top of this population.",
        "arms_with_layout_data_scanned": scanned_arms,
        "total_picture_or_chart_regions_examined": total_picture_regions,
        "candidates_found": len(candidates),
        "by_classification": dict(by_class),
        "distinct_documents": {d: sorted(cls) for d, cls in by_doc.items()},
        "distinct_document_count": len(by_doc),
        "candidates": candidates,
    }
    Path("gated_table_population.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False))
    print(f"arms scanned: {scanned_arms}  picture/chart regions examined: {total_picture_regions}")
    print(f"candidates: {len(candidates)}  by class: {dict(by_class)}")
    print(f"distinct documents: {len(by_doc)}")
    for d, cls in sorted(by_doc.items()):
        print(f"  {d:<30} {cls}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
