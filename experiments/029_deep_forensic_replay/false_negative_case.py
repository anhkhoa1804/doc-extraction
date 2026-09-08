"""029 Phase 6 -- cmb_stamp_boundary_vi: a formal Layer-1/Layer-2 counterexample.

Offline, read-only. 028 found this document has `order_ok=True` under Layer 1
(both the frozen serializer and its (row,col)-canonical counterfactual) while
Layer 2's `page_order_ok=False`. Reconstructs the complete ordering chain to
determine which semantic relationship Layer 1 cannot express.

    python experiments/029_deep_forensic_replay/false_negative_case.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
L28 = REPO / "experiments/028_layer2_evaluation"
sys.path.insert(0, str(L28))
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "research/production_corpus"))
sys.path.insert(0, str(REPO / "experiments/023_evidence_centric"))

import run_ab  # noqa: E402
from doc_extraction.schemas.document import Document  # noqa: E402
from run_benchmark import _norm, document_text as layer1_document_text  # noqa: E402

from page_order import ordered_elements, page_order  # noqa: E402

DID = "cmb_stamp_boundary_vi"
ROOT = REPO / "experiments/024_ocr_fidelity_recovery/_runs/scan_cohort/SCAN-49/baseline"
MANIFEST = REPO / "experiments/024_ocr_fidelity_recovery/scan_cohort_manifest.json"


def main() -> int:
    man = {d["document_id"]: d for d in json.loads(MANIFEST.read_text())["documents_list"]}
    entry = man[DID]
    d = next(p for p in ROOT.iterdir() if p.name.rsplit("-", 1)[0] == DID)
    raw = json.loads((d / "final" / "document.json").read_text())

    # --- Layer 1: frozen serializer, real objects ---
    pyd = Document.model_validate(raw)
    t1 = layer1_document_text(pyd)
    s1 = run_ab.score(entry, t1)

    # Layer 1 counterfactual (canonical table cells) -- 027's transform
    def l1_canonical(doc):
        parts = []
        for pg in doc.get("pages") or []:
            for el in pg.get("elements") or []:
                if el.get("text"):
                    parts.append(el["text"])
            for tb in pg.get("tables") or []:
                flat = []
                for row in tb.get("cells") or []:
                    flat.extend(row if isinstance(row, list) else [row])
                for c in sorted(flat, key=lambda z: (z.get("row", 0), z.get("col", 0))):
                    if c.get("text"):
                        parts.append(c["text"])
        return _norm("\n".join(parts))

    t1cf = l1_canonical(raw)
    s1cf = run_ab.score(entry, t1cf)

    # --- Layer 2: page_order_ok ---
    po = page_order(raw, entry["must_contain"])

    # --- reconstruct the full ordering chain ---
    pg0 = raw["pages"][0]
    els = pg0.get("elements") or []
    ro = pg0.get("reading_order") or []
    ordered = ordered_elements(pg0)

    element_chain = [{"id": e.get("id"), "type": e.get("type"),
                      "order_index": e.get("order_index"),
                      "bbox": e.get("bbox"),
                      "text": (e.get("text") or "")[:80]} for e in ordered]

    # where do required strings land in each representation?
    def positions_in(text, strings):
        out = []
        for s in strings:
            i = text.find(_norm(s))
            out.append({"string": s, "position": i, "found": i >= 0})
        return out

    pos_l1 = positions_in(t1, entry["must_contain"])
    pos_l1cf = positions_in(t1cf, entry["must_contain"])

    non_table_text = "\n".join(e.get("text") for e in ordered
                               if e.get("type") != "table" and e.get("text"))
    non_table_text_norm = _norm(non_table_text)
    pos_l2 = positions_in(non_table_text_norm, entry["must_contain"])

    # table text: where do the table's OWN required strings sit, in table reading order?
    table_ids = [e.get("table_id") for e in els if e.get("type") == "table" and e.get("table_id")]
    table_texts = []
    for tb in pg0.get("tables") or []:
        cells = tb.get("cells") or []
        flat = []
        for row in cells:
            flat.extend(row if isinstance(row, list) else [row])
        raw_seq = [c.get("text", "") for c in flat]
        can_seq = [c.get("text", "") for c in sorted(flat, key=lambda c: (c.get("row", 0), c.get("col", 0)))]
        table_texts.append({"table_id": tb.get("id"), "raw_sequence": raw_seq,
                            "canonical_sequence": can_seq})

    # THE KEY QUESTION: is there a required string whose true semantic position
    # (as read by a human scanning the rendered page top-to-bottom) is BEFORE
    # the table, but which Layer 1 places AFTER the table because tables are
    # always appended last regardless of their bbox position?
    table_els = [e for e in els if e.get("type") == "table" and e.get("bbox")]
    text_els = [e for e in els if e.get("type") != "table" and e.get("bbox") and e.get("text")]
    interleaving = []
    for tb_el in table_els:
        tb_y0 = tb_el["bbox"]["y0"]
        after_by_geometry = [e["id"] for e in text_els if e["bbox"]["y0"] > tb_y0]
        interleaving.append({
            "table_element_id": tb_el["id"], "table_y0": tb_y0,
            "text_elements_geometrically_below_this_table": after_by_geometry,
            "but_serialized_before_table_by_layer1": True,  # elements always precede tables in document_text
        })

    payload = {
        "document_id": DID,
        "labels": entry["hard_case_labels"],
        "layer1": {"order_ok": s1["order_ok"], "positions": pos_l1,
                  "text_recall": s1["text_recall"], "char_recall": s1["char_recall"]},
        "layer1_counterfactual_canonical_tables": {"order_ok": s1cf["order_ok"], "positions": pos_l1cf},
        "layer2_page_order": {"page_order_ok": po["page_order_ok"],
                              "positions_non_table_only": pos_l2,
                              "strings_measurable": po["strings_measurable"],
                              "strings_unmeasurable": po["strings_unmeasurable"],
                              "unmeasurable_detail": po["unmeasurable_detail"]},
        "element_reading_order_chain": element_chain,
        "table_cell_sequences": table_texts,
        "geometric_interleaving": interleaving,
        "classification": None,  # filled below
        "formal_counterexample": None,
    }

    # Classify: FACT-based determination
    l2_found_positions = [p["position"] for p in pos_l2 if p["found"]]
    l2_monotonic = l2_found_positions == sorted(l2_found_positions)
    if not l2_monotonic:
        cls = "IR ordering defect: non-table elements themselves are out of "\
              "geometric sequence -- a genuine page-order problem Layer 1 cannot see."
    elif any(iv["text_elements_geometrically_below_this_table"] for iv in interleaving):
        cls = ("scorer blind spot / benchmark definition mismatch: Layer 1 ALWAYS "
              "serializes every element before every table on a page, regardless of "
              "the table's actual vertical position. Elements positioned BELOW the "
              "table geometrically are still scored as preceding it, so the position "
              "Layer 1 assigns to a post-table string is systematically wrong whenever "
              "any text element sits below the table -- not a mis-ordering of the IR, "
              "a structural limitation of the flattening rule itself.")
    else:
        cls = "AMBIGUOUS: neither IR defect nor the append-order artifact explains it; requires manual inspection."
    payload["classification"] = cls

    payload["formal_counterexample"] = {
        "statement": "Let doc D have element order [heading(y0=A), table(y0=B), "
                    "text(y0=C)] with A < B < C (heading above table above trailing "
                    "text). Layer 1's document_text serializes ALL elements before "
                    "ALL tables: [heading, text, <table cells>]. If a required string "
                    "s1 lives in `text` (y0=C, geometrically AFTER the table) and a "
                    "required string s2 lives in the table (y0=B), Layer 1 places s1's "
                    "position BEFORE s2's -- even though s2 is geometrically higher on "
                    "the page. Layer 1 therefore CANNOT DISTINGUISH a document where "
                    "trailing text truly precedes the table from one where it follows "
                    "it: both serialize identically. Layer 2's page_order_ok, which "
                    "excludes tables entirely from the position test, reports on "
                    "non-table order only and does not manufacture a false ordering "
                    "claim across the table boundary -- this is why it disagrees.",
        "concrete_evidence": "see `geometric_interleaving` and `element_reading_order_chain` below",
    }

    (HERE / "false_negative_case.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False))

    print(f"document: {DID}")
    print(f"Layer 1 order_ok: {s1['order_ok']}  (canonical-table counterfactual: {s1cf['order_ok']})")
    print(f"Layer 2 page_order_ok: {po['page_order_ok']}")
    print(f"\nelement chain ({len(element_chain)} elements):")
    for e in element_chain:
        print(f"  {e['id']:<10} type={e['type']:<8} order_index={e['order_index']} "
              f"y0={e['bbox']['y0'] if e['bbox'] else None} text={e['text'][:50]!r}")
    print(f"\ngeometric interleaving:")
    for iv in interleaving:
        print(f"  table {iv['table_element_id']} (y0={iv['table_y0']}): "
              f"text elements geometrically BELOW it = {iv['text_elements_geometrically_below_this_table']}")
    print(f"\nCLASSIFICATION:\n  {cls}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
