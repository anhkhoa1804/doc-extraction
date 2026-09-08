"""026 Phase 3 -- offline counterfactual. Cell LIST order only.

Offline. Reads the frozen 025 baseline IR
(`experiments/025_layout_evidence_recall/_runs/coverage/*/final/document.json`,
commit 0355e79, text_sha-identical to 024's frozen `l5` arm 49/49). Runs no
pipeline, no OCR, no model, no GPU. Production code is not modified.

Phase 1 established that the intervention the brief proposed is already in
production: all 94 tables carry geometrically correct `row`/`col`, assigned
by `_renumber_rows_by_position`, which anchors on min(y0) -- the anchor the
data supports. Nothing needs canonicalizing.

What is NOT canonical is the ORDER OF THE `cells` LIST. 11 of 94 tables hold
their cells in Table Transformer's emission order. Every production consumer
keys on `(cell.row, cell.col)` -- `Table.to_grid`, `to_markdown`,
`evaluation/table_metrics.py`, the research probes -- so none of them can
see this. The single consumer that reads the raw list is
`research/production_corpus/run_benchmark.py::document_text`, the BENCHMARK's
own flattening helper, which is why the defect surfaced as `order_ok`.

INTERVENTION: sort each table's `cells` list by `(row, col)`. Nothing else.
Text, counts, bboxes, row/col values, table membership all untouched.

    python experiments/026_table_cell_ordering/counterfactual.py
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
BASE = REPO / "experiments/025_layout_evidence_recall/_runs/coverage"
sys.path.insert(0, str(REPO / "experiments/023_evidence_centric"))
sys.path.insert(0, str(REPO / "research/production_corpus"))

import run_ab  # noqa: E402
from run_benchmark import _norm  # noqa: E402  -- the REAL normalizer, imported not reimplemented

E024 = REPO / "experiments/024_ocr_fidelity_recovery"


def document_text(doc: dict) -> str:
    """Byte-for-byte reimplementation of run_benchmark.document_text over the
    saved IR dict (the real one takes pydantic objects)."""
    parts = []
    for pg in doc["pages"]:
        for el in pg.get("elements") or []:
            if el.get("text"):
                parts.append(el["text"])
        for tb in pg.get("tables") or []:
            for c in tb.get("cells") or []:
                if c.get("text"):
                    parts.append(c["text"])
    return _norm("\n".join(parts))  # same normalizer the benchmark uses


def canonicalize(doc: dict) -> int:
    """Sort every table's cells list by (row, col). Returns tables reordered."""
    n = 0
    for pg in doc["pages"]:
        for tb in pg.get("tables") or []:
            cells = tb.get("cells") or []
            before = [id(c) for c in cells]
            cells.sort(key=lambda c: (c["row"], c["col"]))
            if [id(c) for c in cells] != before:
                n += 1
    return n


def invariants(a: dict, b: dict) -> dict:
    """The 11 required invariants, checked structurally."""
    def tables(d):
        return [tb for pg in d["pages"] for tb in (pg.get("tables") or [])]

    def cells(d):
        return [c for tb in tables(d) for c in (tb.get("cells") or [])]

    def els(d):
        return [e for pg in d["pages"] for e in (pg.get("elements") or [])]

    ta, tb_ = tables(a), tables(b)
    ca, cb = cells(a), cells(b)
    return {
        "1_cell_text_multiset_identical": Counter(c.get("text", "") for c in ca)
                                          == Counter(c.get("text", "") for c in cb),
        "2_cell_count_identical": len(ca) == len(cb),
        "3_table_count_identical": len(ta) == len(tb_),
        "4_table_bboxes_identical": [t.get("bbox") for t in ta] == [t.get("bbox") for t in tb_],
        "5_no_table_or_cell_created": len(ca) == len(cb) and len(ta) == len(tb_),
        "6_no_cell_deleted": len(ca) == len(cb),
        "7_rowcol_values_unchanged": Counter((c["row"], c["col"]) for c in ca)
                                     == Counter((c["row"], c["col"]) for c in cb),
        "8_cell_bboxes_unchanged": Counter(json.dumps(c.get("bbox"), sort_keys=True) for c in ca)
                                   == Counter(json.dumps(c.get("bbox"), sort_keys=True) for c in cb),
        "9_page_element_order_unchanged": [e["id"] for e in els(a)] == [e["id"] for e in els(b)],
        "10_non_table_text_unchanged": [e.get("text") for e in els(a)] == [e.get("text") for e in els(b)],
        "11_declared_shape_unchanged": [(t.get("n_rows"), t.get("n_cols")) for t in ta]
                                       == [(t.get("n_rows"), t.get("n_cols")) for t in tb_],
    }


def main() -> int:
    cohort = json.loads((E024 / "scan_cohort_manifest.json").read_text())
    meta = {d["document_id"]: d for d in cohort["documents_list"] if d["stratum"] == "SCAN-49"}
    dirs = {p.name.rsplit("-", 1)[0]: p for p in BASE.iterdir() if p.is_dir()}

    rows, inv_fail, reordered_tables = [], [], 0
    for did, d in sorted(dirs.items()):
        raw = (d / "final" / "document.json").read_text()
        ctl = json.loads(raw)
        itv = json.loads(raw)
        reordered_tables += canonicalize(itv)

        inv = invariants(ctl, itv)
        if not all(inv.values()):
            inv_fail.append({"document_id": did, "invariants": inv})

        tc, ti = document_text(ctl), document_text(itv)
        sc = run_ab.score(meta[did], tc)
        si = run_ab.score(meta[did], ti)
        rows.append({
            "document_id": did,
            "labels": meta[did]["hard_case_labels"],
            "control": {k: sc[k] for k in ("text_recall", "char_recall", "order_ok",
                                           "hallucinated", "found", "required")},
            "intervention": {k: si[k] for k in ("text_recall", "char_recall", "order_ok",
                                                "hallucinated", "found", "required")},
            "text_identical": tc == ti,
            "text_multiset_identical": Counter(tc.split()) == Counter(ti.split()),
            "order_repaired": (not sc["order_ok"]) and si["order_ok"],
            "order_broken": sc["order_ok"] and (not si["order_ok"]),
            "invariants_ok": all(inv.values()),
        })

    def agg(key):
        return {
            "mean_text_recall": round(sum(r[key]["text_recall"] for r in rows) / len(rows), 4),
            "mean_char_recall": round(sum(r[key]["char_recall"] for r in rows) / len(rows), 4),
            "docs_perfect": sum(1 for r in rows if r[key]["text_recall"] == 1.0),
            "docs_order_ok": sum(1 for r in rows if r[key]["order_ok"]),
            "docs_hallucinated": sum(1 for r in rows if r[key]["hallucinated"]),
        }

    payload = {
        "baseline_commit": "0355e79476f87d4613dd4d470518eabcfc73909a",
        "source": "frozen 025 baseline IR; offline transformation only",
        "intervention": "sort each table's cells list by (row, col); nothing else",
        "tables_reordered": reordered_tables,
        "documents": len(rows),
        "invariant_failures": inv_fail,
        "all_invariants_hold": not inv_fail,
        "control": agg("control"),
        "intervention_result": agg("intervention"),
        "order_repaired": [r["document_id"] for r in rows if r["order_repaired"]],
        "order_broken": [r["document_id"] for r in rows if r["order_broken"]],
        "documents_with_changed_text": [r["document_id"] for r in rows if not r["text_identical"]],
        "documents_with_changed_text_multiset": [r["document_id"] for r in rows
                                                 if not r["text_multiset_identical"]],
        "rows": rows,
    }
    (HERE / "counterfactual.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False))

    c, i = payload["control"], payload["intervention_result"]
    print(f"tables reordered: {reordered_tables}   documents: {len(rows)}")
    print(f"all 11 invariants hold: {payload['all_invariants_hold']}")
    print(f"\n{'metric':<22}{'control':>10}{'intervention':>14}{'delta':>9}")
    for k in c:
        dv = i[k] - c[k]
        print(f"{k:<22}{c[k]:>10}{i[k]:>14}{dv:>+9}")
    print(f"\norder_ok repaired : {payload['order_repaired']}")
    print(f"order_ok broken   : {payload['order_broken']}")
    print(f"text changed (order) in {len(payload['documents_with_changed_text'])} documents")
    print(f"text MULTISET changed in {len(payload['documents_with_changed_text_multiset'])} documents "
          f"{payload['documents_with_changed_text_multiset']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
