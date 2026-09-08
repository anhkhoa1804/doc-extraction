"""025 line 3 -- orphan topology. Where do orphans sit, and are they structured?

Offline. Reads `coverage_dataset.json`; runs no pipeline, no OCR, no model,
no GPU.

The question 024 could not answer: are orphan tokens *missing regions* -- a
coherent block of text the detector simply failed to enclose -- or genuinely
unstructured noise that no region should ever have covered? The answer
decides whether a deterministic geometric correction is even possible.

Every orphan token is placed relative to the page's region hull (the union
box of everything the detector did emit) into one mutually exclusive class,
tested in this order:

  table_adjacent   within one token-height of a detected table's box
  interior_gap     inside the hull, not inside any region, not near an edge
  edge_adjacent    inside the hull and within one token-height of a region edge
  lateral_band     outside the hull horizontally, overlapping it vertically
                   -- the shape a dropped second column makes
  header_band      above the hull
  footer_band      below the hull
  outside_corner   outside on both axes

Structure is then measured with the PRODUCTION clustering rule (imported,
not reimplemented) so "structured" means exactly what L5 already means by it.

    python experiments/025_layout_evidence_recall/orphan_topology.py
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "src"))

from doc_extraction.pipelines.base import _cluster_orphans  # noqa: E402
from doc_extraction.schemas.element import BBox  # noqa: E402

DATA = HERE / "coverage_dataset.json"


class Tok:
    """Minimal OCRToken stand-in so the production clusterer can run on the
    recorded dataset without re-running the pipeline."""
    __slots__ = ("text", "bbox", "confidence")

    def __init__(self, text, bbox, conf):
        self.text, self.bbox, self.confidence = text, bbox, conf


def bb(v) -> BBox:
    return BBox(x0=v[0], y0=v[1], x1=v[2], y1=v[3])


def centre(v):
    return ((v[0] + v[2]) / 2, (v[1] + v[3]) / 2)


def classify(tokv, regions, tables, hull, margin):
    cx, cy = centre(tokv)
    for t in tables:
        if t["bbox"]:
            x0, y0, x1, y1 = t["bbox"]
            if x0 - margin <= cx <= x1 + margin and y0 - margin <= cy <= y1 + margin:
                return "table_adjacent"
    if hull is None:
        return "no_regions_on_page"
    hx0, hy0, hx1, hy1 = hull
    inside_x, inside_y = hx0 <= cx <= hx1, hy0 <= cy <= hy1
    if inside_x and inside_y:
        for r in regions:
            x0, y0, x1, y1 = r["bbox"]
            if x0 - margin <= cx <= x1 + margin and y0 - margin <= cy <= y1 + margin:
                return "edge_adjacent"
        return "interior_gap"
    if inside_y and not inside_x:
        return "lateral_band"
    if inside_x and not inside_y:
        return "header_band" if cy < hy0 else "footer_band"
    return "outside_corner"


def main() -> int:
    d = json.loads(DATA.read_text())
    pages = d["pages"]

    classes = Counter()
    per_page = []
    block_sizes, block_lines = [], []
    structured_tokens = singleton_tokens = 0
    lateral_pages = []
    adjacency_by_label = Counter()

    for p in pages:
        orphans = [t for t in p["tokens"] if t["claim"] == "orphan"]
        if not orphans:
            per_page.append({"document_id": p["document_id"], "page_index": p["page_index"],
                             "orphans": 0, "classes": {}, "blocks": 0})
            continue
        heights = [t["bbox"][3] - t["bbox"][1] for t in p["tokens"]] or [10.0]
        margin = statistics.median(heights)
        regions = p["regions"]
        hull = None
        if regions:
            hull = (min(r["bbox"][0] for r in regions), min(r["bbox"][1] for r in regions),
                    max(r["bbox"][2] for r in regions), max(r["bbox"][3] for r in regions))
        pc = Counter()
        for t in orphans:
            k = classify(t["bbox"], regions, p["tables"], hull, margin)
            pc[k] += 1
            classes[k] += 1
            if k == "edge_adjacent":
                cx, cy = centre(t["bbox"])
                near = min(regions, key=lambda r: min(
                    abs(cx - r["bbox"][0]), abs(cx - r["bbox"][2]),
                    abs(cy - r["bbox"][1]), abs(cy - r["bbox"][3])))
                adjacency_by_label[near["label"]] += 1

        # structure, using the production clusterer
        blocks = _cluster_orphans([Tok(t["text"], bb(t["bbox"]), t["conf"]) for t in orphans])
        for blk in blocks:
            block_sizes.append(len(blk))
            ys = sorted({round(t.bbox.y0) for t in blk})
            lines = 1 + sum(1 for a, b in zip(ys, ys[1:]) if b - a > margin * 0.5)
            block_lines.append(lines)
            if len(blk) >= 3:
                structured_tokens += len(blk)
            if len(blk) == 1:
                singleton_tokens += 1

        if pc.get("lateral_band"):
            xs = [centre(t["bbox"])[0] for t in orphans]
            lateral_pages.append({
                "document_id": p["document_id"], "page_index": p["page_index"],
                "orphans": len(orphans), "lateral": pc["lateral_band"],
                "orphan_x_span": [round(min(xs), 1), round(max(xs), 1)],
                "hull_x_span": [round(hull[0], 1), round(hull[2], 1)] if hull else None,
                "page_width": p["width"],
            })
        per_page.append({"document_id": p["document_id"], "page_index": p["page_index"],
                         "orphans": len(orphans), "classes": dict(pc), "blocks": len(blocks)})

    total = sum(classes.values())
    payload = {
        "commit": d["commit"],
        "source": "coverage_dataset.json",
        "question": "are orphans structured missing regions, or unstructured noise?",
        "classification_order": ["table_adjacent", "edge_adjacent", "interior_gap",
                                 "lateral_band", "header_band", "footer_band",
                                 "outside_corner"],
        "orphan_tokens": total,
        "classes": dict(classes.most_common()),
        "class_share": {k: round(v / total, 4) for k, v in classes.most_common()},
        "structure": {
            "blocks": len(block_sizes),
            "tokens_in_blocks_of_3_or_more": structured_tokens,
            "structured_share": round(structured_tokens / total, 4) if total else None,
            "singleton_blocks": singleton_tokens,
            "singleton_share": round(singleton_tokens / total, 4) if total else None,
            "median_block_size": statistics.median(block_sizes) if block_sizes else None,
            "max_block_size": max(block_sizes) if block_sizes else None,
            "median_block_lines": statistics.median(block_lines) if block_lines else None,
            "clusterer": "doc_extraction.pipelines.base._cluster_orphans (production)",
        },
        "edge_adjacent_nearest_region_label": dict(adjacency_by_label.most_common()),
        "lateral_band_pages": sorted(lateral_pages, key=lambda r: -r["lateral"]),
        "per_page": per_page,
    }
    (HERE / "orphan_topology.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False))

    print(f"orphan tokens: {total}")
    for k, v in classes.most_common():
        print(f"  {k:<18} {v:>5}  {v/total:6.2%}")
    print(f"\nblocks {len(block_sizes)}  median size {payload['structure']['median_block_size']}  "
          f"max {payload['structure']['max_block_size']}")
    print(f"structured (blocks>=3 tokens): {structured_tokens}/{total} "
          f"= {structured_tokens/total:.2%};  singletons {singleton_tokens}")
    print(f"\nnearest-region label for edge-adjacent orphans: {dict(adjacency_by_label)}")
    print(f"lateral-band pages: {len(lateral_pages)}")
    for r in payload["lateral_band_pages"][:8]:
        print(f"  {r['document_id']:<28} p{r['page_index']} lateral={r['lateral']}/{r['orphans']} "
              f"orphan_x {r['orphan_x_span']} hull_x {r['hull_x_span']} W={r['page_width']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
