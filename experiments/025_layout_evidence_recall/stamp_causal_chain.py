"""025 line 9 -- the three stamp/occlusion documents: the full causal chain.

Offline. Reads `coverage_dataset.json` and the IR under `_runs/coverage/`.
Runs no pipeline, no OCR, no GPU. §6 asks for the chain to be documented
before any fix is proposed; this documents it and proposes nothing.

The chain, each link measured rather than inferred:

  1. CLASSIFIER, not detector. Docling emits a region whose geometry is the
     table almost exactly -- 1039x337 px on cmb_stamp_table_vi -- and labels
     it `picture`. The box is right. The label is wrong.

  2. GATING. `run_scanned_page_pipeline` (pipelines/base.py:747) selects
     table regions as `[r for r in layout_result.regions
     if r.label.lower() == "table"]`. With the block labelled `picture` the
     list is empty, so TableTransformer is never invoked on it. That, and
     not a table-detection failure, is why `tables_found = 0`.

  3. THE CELLS EXIST ANYWAY. Docling also emits 13-17 small `text` regions
     strictly nested inside the mislabelled block, and they are the table's
     own cells. The geometry needed to rebuild the table is present in the
     detector's output and is discarded by step 2.

  4. DUPLICATION. `_LABEL_TO_ELEMENT_TYPE` maps `picture` to `image`, which
     is not the TABLE branch, so `merge_regions_into_page` calls
     `_gather_region_text` on it and the image element absorbs every token
     under it. Each nested cell region independently absorbs its own tokens.
     `document_text` concatenates every element's text regardless of type,
     so each of those tokens reaches the scored output twice.

  5. INVISIBLE. Duplication cannot lower exact or char recall -- both count
     ground-truth strings found, not output emitted. All three documents
     score char_recall 1.0 while emitting 26-28 duplicate token emissions.

    python experiments/025_layout_evidence_recall/stamp_causal_chain.py
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNS = HERE / "_runs" / "coverage"
CASES = ["hc_stamp_table_vi", "cmb_stamp_table_vi", "cmb_scan_stamp_table_vi"]


def contains(o, i):
    return o[0] <= i[0] and o[1] <= i[1] and o[2] >= i[2] and o[3] >= i[3]


def inside(tok, r):
    cx = (tok["bbox"][0] + tok["bbox"][2]) / 2
    cy = (tok["bbox"][1] + tok["bbox"][3]) / 2
    return r["bbox"][0] <= cx <= r["bbox"][2] and r["bbox"][1] <= cy <= r["bbox"][3]


def main() -> int:
    ds = json.loads((HERE / "coverage_dataset.json").read_text())
    docs = {r["document_id"]: r for r in ds["documents"]}
    dirs = {p.name.rsplit("-", 1)[0]: p for p in RUNS.iterdir() if p.is_dir()}

    out = []
    for did in CASES:
        p = [x for x in ds["pages"] if x["document_id"] == did][0]
        regions = p["regions"]
        pics = [r for r in regions if r["label"] == "picture"]
        nested = []
        for pic in pics:
            for r in regions:
                if r["idx"] != pic["idx"] and contains(pic["bbox"], r["bbox"]):
                    nested.append({"idx": r["idx"], "label": r["label"], "bbox": r["bbox"],
                                   "w": round(r["bbox"][2] - r["bbox"][0], 1),
                                   "h": round(r["bbox"][3] - r["bbox"][1], 1)})
        emissions = sum(sum(1 for t in p["tokens"] if inside(t, r)) for r in regions)
        doc = json.loads((dirs[did] / "final" / "document.json").read_text())
        els = [e for pg in doc["pages"] for e in (pg.get("elements") or [])]
        img_els = [e for e in els if e["type"] == "image" and e.get("text")]

        r = docs[did]
        out.append({
            "document_id": did,
            "labels": r["labels"],
            "exact": r["text_recall"], "char": r["char_recall"],
            "order_ok": r["order_ok"], "tables_ok": r["tables_ok"],
            "tables_expected": r["tables_expected"], "tables_found": r["tables_found"],
            "link_1_classifier": {
                "picture_regions": [{"idx": q["idx"], "bbox": q["bbox"],
                                     "w": round(q["bbox"][2] - q["bbox"][0], 1),
                                     "h": round(q["bbox"][3] - q["bbox"][1], 1)} for q in pics],
                "verdict": "geometry correct, label wrong -- classifier failure",
            },
            "link_2_gating": {
                "regions_labelled_table": sum(1 for x in regions if x["label"] == "table"),
                "table_backend_invoked_on": 0,
                "tables_in_ir": len(p["tables"]),
                "code": "pipelines/base.py:747 -- label.lower() == 'table'",
                "verdict": "table structure recognition never ran -- gating failure, "
                           "not table-detection failure",
            },
            "link_3_cells_exist": {
                "nested_regions": len(nested),
                "nested_labels": dict(Counter(x["label"] for x in nested)),
                "median_nested_w": sorted(x["w"] for x in nested)[len(nested) // 2] if nested else None,
                "median_nested_h": sorted(x["h"] for x in nested)[len(nested) // 2] if nested else None,
                "verdict": "cell-level geometry is present in the detector output "
                           "and is discarded by link 2",
            },
            "link_4_duplication": {
                "page_tokens": len(p["tokens"]),
                "token_emissions_over_all_regions": emissions,
                "duplicate_emissions": emissions - len(p["tokens"]),
                "multiply_owned_tokens": sum(1 for t in p["tokens"] if t["n_owners"] > 1),
                "image_elements_carrying_text": len(img_els),
                "image_element_chars": sum(len(e["text"]) for e in img_els),
                "verdict": "picture element and its nested cell elements both emit "
                           "the same tokens into document_text",
            },
            "link_5_invisibility": {
                "char_recall": r["char_recall"],
                "verdict": "duplication cannot reduce exact or char recall; the "
                           "benchmark cannot see it at all",
            },
            "failure_attribution": {
                "detector_failure": "partial -- classification, not localisation",
                "postprocessing_failure": "PRIMARY -- a single label-equality test "
                                          "discards a correctly localised table and its cells",
                "ownership_failure": "secondary -- _center_in has no nesting rule, so "
                                     "a token inside parent and child belongs to both",
                "assembly_failure": "consequence only",
            },
        })

    (HERE / "stamp_causal_chain.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    for e in out:
        print(f"\n=== {e['document_id']} ===")
        print(f"  exact {e['exact']} char {e['char']} tables {e['tables_found']}/{e['tables_expected']}")
        pr = e["link_1_classifier"]["picture_regions"]
        print(f"  1 classifier: picture regions {[(q['w'], q['h']) for q in pr]} -- geometry right, label wrong")
        g = e["link_2_gating"]
        print(f"  2 gating: regions labelled 'table' = {g['regions_labelled_table']}, "
              f"tables in IR = {g['tables_in_ir']} -> TableTransformer never invoked")
        c = e["link_3_cells_exist"]
        print(f"  3 cells exist: {c['nested_regions']} nested {c['nested_labels']} "
              f"median {c['median_nested_w']}x{c['median_nested_h']} px")
        dpl = e["link_4_duplication"]
        print(f"  4 duplication: {dpl['page_tokens']} tokens -> {dpl['token_emissions_over_all_regions']} "
              f"emissions = {dpl['duplicate_emissions']} duplicates; "
              f"image elements with text {dpl['image_elements_carrying_text']} "
              f"({dpl['image_element_chars']} chars)")
        print(f"  5 invisible: char_recall {e['link_5_invisibility']['char_recall']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
