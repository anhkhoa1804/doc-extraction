"""025 line 4 -- the six documents §7 named, inspected individually.

Offline. Reads `coverage_dataset.json` and `orphan_topology.json`.

For each: region count and types, orphan count and spatial class, table
detection state, reading-order outcome, and the explicit question -- would a
missing region explain the observed failure? The two 44%-orphan multi-column
pages carry the 024 headline, so their orphan text is printed verbatim.

    python experiments/025_layout_evidence_recall/case_studies.py
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
CASES = ["hc_multicolumn_en", "cmb_scan_multicol_en", "cmb_scan_tiny_vi",
         "hc_tiny_cells_vi", "cmb_stamp_table_vi", "cmb_scan_stamp_table_vi"]


def main() -> int:
    d = json.loads((HERE / "coverage_dataset.json").read_text())
    topo = {(r["document_id"], r["page_index"]): r
            for r in json.loads((HERE / "orphan_topology.json").read_text())["per_page"]}
    docs = {r["document_id"]: r for r in d["documents"]}

    out = []
    for did in CASES:
        row = docs[did]
        pages = [p for p in d["pages"] if p["document_id"] == did]
        entry = {
            "document_id": did, "labels": row["labels"], "language": row["language"],
            "exact": row["text_recall"], "char": row["char_recall"],
            "order_ok": row["order_ok"], "tables_ok": row["tables_ok"],
            "tables_expected": row["tables_expected"], "tables_found": row["tables_found"],
            "missing_strings": row.get("missing") or [], "pages": [],
        }
        for p in pages:
            cl = Counter(t["claim"] for t in p["tokens"])
            orph = [t for t in p["tokens"] if t["claim"] == "orphan"]
            entry["pages"].append({
                "page_index": p["page_index"], "page_size": [p["width"], p["height"]],
                "n_regions": len(p["regions"]),
                "region_labels": [r["label"] for r in p["regions"]],
                "region_bboxes": [r["bbox"] for r in p["regions"]],
                "region_claimed": [r["claimed_tokens"] for r in p["regions"]],
                "n_tables": len(p["tables"]), "table_bboxes": [t["bbox"] for t in p["tables"]],
                "table_cells": [t["n_cells"] for t in p["tables"]],
                "tokens": len(p["tokens"]), "claims": dict(cl),
                "orphan_rate": round(cl["orphan"] / len(p["tokens"]), 4) if p["tokens"] else 0,
                "orphan_classes": topo.get((did, p["page_index"]), {}).get("classes", {}),
                "orphan_text": " ".join(t["text"] for t in orph)[:600],
            })
        out.append(entry)

    (HERE / "case_studies.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))

    for e in out:
        print(f"\n=== {e['document_id']}  {e['labels']} ===")
        print(f"  exact {e['exact']}  char {e['char']}  order_ok {e['order_ok']}  "
              f"tables {e['tables_found']}/{e['tables_expected']} ok={e['tables_ok']}")
        if e["missing_strings"]:
            print(f"  missing: {e['missing_strings']}")
        for p in e["pages"][:4]:
            print(f"  p{p['page_index']}: {p['n_regions']} regions {p['region_labels']} "
                  f"| {p['n_tables']} tables (cells {p['table_cells']}) "
                  f"| tokens {p['tokens']} claims {p['claims']} orphan {p['orphan_rate']:.2f}")
            print(f"       classes {p['orphan_classes']}")
            if p["orphan_text"]:
                print(f"       orphan text: {p['orphan_text'][:220]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
