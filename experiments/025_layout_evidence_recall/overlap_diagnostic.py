"""025 line 7 -- Class C: multiply-owned tokens. A first-class diagnostic.

Offline. Reads `coverage_dataset.json`. Runs no pipeline, no OCR, no GPU.

Class B (a token inside NO region) and Class C (a token inside TWO OR MORE)
are opposite defects with opposite consequences, and are never summed here:

  Class B loses evidence   -- `_gather_region_text` never sees the token.
  Class C duplicates it    -- `_gather_region_text` runs once per region, so
                              a doubly-owned token is emitted into BOTH
                              elements' text.

Every multiply-owned token is classified by what the owning regions are, so
"overlap" does not become one undifferentiated number:

  table_text_overlap    one owner is a `table` region, another is text
  stamp_occlusion       one owner is a `picture` region (the stamp)
  duplicate_region      two owners of the same label with high mutual IoU
  boundary_ambiguity    owners barely overlap; the token sits on the seam
  legitimate_nesting    one owner strictly contains the other

    python experiments/025_layout_evidence_recall/overlap_diagnostic.py
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent


def iou(a, b):
    ix0, iy0 = max(a[0], b[0]), max(a[1], b[1])
    ix1, iy1 = min(a[2], b[2]), min(a[3], b[3])
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    inter = (ix1 - ix0) * (iy1 - iy0)
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua else 0.0


def contains(outer, inner):
    return (outer[0] <= inner[0] and outer[1] <= inner[1]
            and outer[2] >= inner[2] and outer[3] >= inner[3])


def owners_of(tok, regions):
    cx = (tok["bbox"][0] + tok["bbox"][2]) / 2
    cy = (tok["bbox"][1] + tok["bbox"][3]) / 2
    return [i for i, r in enumerate(regions)
            if r["bbox"][0] <= cx <= r["bbox"][2] and r["bbox"][1] <= cy <= r["bbox"][3]]


def classify_pair(ra, rb):
    """Containment is tested FIRST. An earlier ordering tested the `picture`
    label first and reported all 82 tokens as `stamp_occlusion`, which named
    the document rather than the geometry: these regions are strictly nested,
    a parent enclosing its own children, not two regions colliding."""
    la, lb = ra["label"], rb["label"]
    if contains(ra["bbox"], rb["bbox"]) or contains(rb["bbox"], ra["bbox"]):
        outer = ra if contains(ra["bbox"], rb["bbox"]) else rb
        # A `picture` that encloses text regions is a mislabelled block, not
        # an illustration: the enclosed regions are its cells.
        return ("nested_in_picture_labelled_block" if outer["label"] == "picture"
                else "legitimate_nesting")
    if "table" in (la, lb) and la != lb:
        return "table_text_overlap"
    if "picture" in (la, lb):
        return "stamp_occlusion"
    j = iou(ra["bbox"], rb["bbox"])
    if la == lb and j >= 0.5:
        return "duplicate_region"
    if j < 0.1:
        return "boundary_ambiguity"
    return "duplicate_region"


def main() -> int:
    d = json.loads((HERE / "coverage_dataset.json").read_text())
    hist = Counter()
    kinds = Counter()
    pages_aff, docs_aff = set(), set()
    per_doc = defaultdict(lambda: Counter())
    examples = []
    dup_chars = 0

    for p in d["pages"]:
        regions = p["regions"]
        page_multi = 0
        for t in p["tokens"]:
            o = owners_of(t, regions)
            n = len(o)
            hist[min(n, 3) if n < 3 else "3+"] += 1
            per_doc[p["document_id"]]["tokens"] += 1
            if n >= 2:
                page_multi += 1
                dup_chars += len(t["text"] or "") * (n - 1)
                per_doc[p["document_id"]]["multi"] += 1
                docs_aff.add(p["document_id"])
                k = classify_pair(regions[o[0]], regions[o[1]])
                kinds[k] += 1
                if len(examples) < 12:
                    examples.append({
                        "document_id": p["document_id"], "page_index": p["page_index"],
                        "text": t["text"], "kind": k,
                        "owner_labels": [regions[i]["label"] for i in o],
                        "owner_bboxes": [regions[i]["bbox"] for i in o],
                        "pair_iou": round(iou(regions[o[0]]["bbox"], regions[o[1]]["bbox"]), 4),
                    })
        if page_multi:
            pages_aff.add((p["document_id"], p["page_index"]))

    total = sum(v for k, v in hist.items())
    n0 = hist.get(0, 0)
    n1 = hist.get(1, 0)
    n2 = hist.get(2, 0)
    n3 = hist.get("3+", 0)
    payload = {
        "commit": d["commit"],
        "definitions": {
            "class_B": "token inside 0 regions -- evidence LOST (L5 rescues it)",
            "class_C": "token inside >=2 regions -- evidence DUPLICATED "
                       "(_gather_region_text runs per region)",
            "note": "B and C are never summed; they are opposite defects.",
        },
        "table": {
            "total_ocr_tokens": total,
            "tokens_in_0_regions": n0,
            "tokens_in_1_region": n1,
            "tokens_in_2_regions": n2,
            "tokens_in_3plus_regions": n3,
            "fraction_multiply_owned": round((n2 + n3) / total, 6),
            "pages_affected": len(pages_aff),
            "documents_affected": len(docs_aff),
            "duplicated_characters": dup_chars,
        },
        "multiply_owned_kinds": dict(kinds.most_common()),
        "per_document": {
            did: {"tokens": c["tokens"], "multiply_owned": c["multi"],
                  "rate": round(c["multi"] / c["tokens"], 4)}
            for did, c in sorted(per_doc.items(), key=lambda kv: -kv[1]["multi"])
            if c["multi"]},
        "examples": examples,
    }
    (HERE / "overlap_diagnostic.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False))

    t = payload["table"]
    print("| Metric                  | Value |")
    print("| ----------------------- | ----: |")
    for k in ["total_ocr_tokens", "tokens_in_0_regions", "tokens_in_1_region",
              "tokens_in_2_regions", "tokens_in_3plus_regions",
              "fraction_multiply_owned", "pages_affected", "documents_affected",
              "duplicated_characters"]:
        print(f"| {k:<23} | {t[k]} |")
    print(f"\nkinds: {dict(kinds)}")
    print(f"per document: {payload['per_document']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
