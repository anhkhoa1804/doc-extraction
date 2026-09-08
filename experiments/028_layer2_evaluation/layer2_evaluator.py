"""028 Phases 3-5, 8 -- run Layer 2 on the frozen SCAN-49 cohort.

Offline, CPU only. Reads the frozen IR produced by 025's
`coverage_instrument.py` (commit 0355e79, text_sha-identical to 024's frozen
`l5` arm on 49/49) plus 025's token-level `coverage_dataset.json`. Modifies
no production code, no scorer, and no extraction output.

Layer 1 is executed UNCHANGED, via the frozen `run_ab.score` over the frozen
`run_benchmark.document_text`, and reported alongside Layer 2 rather than
replaced by it.

Every 025/026 fact quoted in the README is recomputed here from the IR. None
is read out of a previous milestone's write-up.

    python experiments/028_layer2_evaluation/layer2_evaluator.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "research/production_corpus"))
sys.path.insert(0, str(REPO / "experiments/023_evidence_centric"))

import run_ab  # noqa: E402
from doc_extraction.schemas.document import Document  # noqa: E402
from run_benchmark import document_text as layer1_document_text  # noqa: E402

from page_order import page_order  # noqa: E402
from structural_integrity import structural_integrity  # noqa: E402
from table_structure import table_structure  # noqa: E402
from table_text import non_table_text, table_text  # noqa: E402

BASE = REPO / "experiments/025_layout_evidence_recall/_runs/coverage"
COVERAGE = REPO / "experiments/025_layout_evidence_recall/coverage_dataset.json"
MANIFEST = REPO / "experiments/024_ocr_fidelity_recovery/scan_cohort_manifest.json"


def layer1_counterfactual(doc: dict) -> str:
    """Layer 1's serializer with table cells iterated in (row, col) order.
    Used only to quantify how much of `order_ok` was table serialization."""
    from run_benchmark import _norm
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


def main() -> int:
    man = {d["document_id"]: d for d in json.loads(MANIFEST.read_text())["documents_list"]
           if d["stratum"] == "SCAN-49"}
    dirs = {p.name.rsplit("-", 1)[0]: p for p in BASE.iterdir() if p.is_dir()}

    # 025's token-level ownership data, for the OWNERSHIP dimension
    own = {}
    if COVERAGE.exists():
        cd = json.loads(COVERAGE.read_text())
        for p in cd["pages"]:
            k = own.setdefault(p["document_id"], Counter())
            for t in p["tokens"]:
                k["tokens"] += 1
                # 025 defines the orphan rate on n_owners == 0. `claim == "orphan"`
                # is a stricter subset: it also excludes the 3 tokens that sit
                # inside a detected table or cell but inside no region. Both are
                # recorded so the two milestones' numbers reconcile exactly
                # instead of differing by 3 for an unexplained reason.
                k["no_region"] += int(t["n_owners"] == 0)
                k["orphan"] += int(t["claim"] == "orphan")
                k["multi"] += int(t["n_owners"] > 1)

    docs, tables, l1_rows, l1cf_rows = [], [], [], []
    for did, d in sorted(dirs.items()):
        if did not in man:
            continue
        doc = json.loads((d / "final" / "document.json").read_text())

        tt = table_text(doc)
        ts = table_structure(doc)
        si = structural_integrity(doc)
        po = page_order(doc, man[did]["must_contain"])

        # --- Layer 1, executed unchanged on the real objects ---
        t1 = layer1_document_text(Document.model_validate(doc))
        s1 = run_ab.score(man[did], t1)
        s1cf = run_ab.score(man[did], layer1_counterfactual(doc))
        l1_rows.append(s1)
        l1cf_rows.append(s1cf)

        o = own.get(did, Counter())
        for a, b, c in zip(tt, ts, si):
            # --- Phase 5 status vector, per table ---
            status = {
                "TEXT": "UNMEASURABLE",   # no per-cell ground truth in the corpus
                "STRUCTURE": "VALID" if c["structurally_valid"] else "INVALID",
                "OWNERSHIP": ("UNMEASURABLE" if not o else
                              ("CLEAN" if o["multi"] == 0 else "DUPLICATED")),
                "ORDER": "CANONICAL" if c["list_order_canonical"] else "NON_CANONICAL",
            }
            tables.append({"document_id": did, **a, "structure": b,
                           "integrity": c, "status": status})

        docs.append({
            "document_id": did,
            "labels": man[did]["hard_case_labels"],
            "layer1": {k: s1[k] for k in ("text_recall", "char_recall", "order_ok",
                                          "found", "required", "hallucinated")},
            "layer1_counterfactual_order_ok": s1cf["order_ok"],
            "layer2": {
                "page_order": po,
                "n_tables": len(tt),
                "tables_structurally_valid": sum(1 for x in si if x["structurally_valid"]),
                "tables_list_order_canonical": sum(1 for x in si if x["list_order_canonical"]),
                "evidence": {"tokens": o.get("tokens"), "orphan": o.get("orphan"),
                             "multiply_owned": o.get("multi")} if o else None,
            },
        })

    n = len(docs)
    ncell = sum(t["n_cells"] for t in tables)
    valid = sum(1 for t in tables if t["integrity"]["structurally_valid"])
    canon = sum(1 for t in tables if t["integrity"]["list_order_canonical"])
    failed = Counter(k for t in tables for k in t["integrity"]["failed_checks"])
    tok = sum(o["tokens"] for o in own.values()) if own else 0
    orph = sum(o["orphan"] for o in own.values()) if own else 0
    nore = sum(o["no_region"] for o in own.values()) if own else 0
    multi = sum(o["multi"] for o in own.values()) if own else 0

    def agg(rows, key):
        return sum(1 for r in rows if r[key])

    payload = {
        "commit": "271abf22b7bf1df326eeddea2f63e6d333881366",
        "ir_commit": "0355e79476f87d4613dd4d470518eabcfc73909a",
        "cohort": "SCAN-49 (frozen)",
        "layer1_executed": "run_benchmark.document_text + run_ab.score, UNCHANGED",
        "layer1": {
            "n": n,
            "mean_text_recall": round(sum(r["text_recall"] for r in l1_rows) / n, 4),
            "mean_char_recall": round(sum(r["char_recall"] for r in l1_rows) / n, 4),
            "docs_perfect": sum(1 for r in l1_rows if r["text_recall"] == 1.0),
            "docs_order_ok": agg(l1_rows, "order_ok"),
            "docs_hallucinated": sum(1 for r in l1_rows if r["hallucinated"]),
        },
        "layer1_counterfactual": {"docs_order_ok": agg(l1cf_rows, "order_ok")},
        "layer2": {
            "documents": n,
            "tables": len(tables),
            "cells": ncell,
            "tables_structurally_valid": valid,
            "tables_structurally_invalid": len(tables) - valid,
            "structural_validity_rate": round(valid / len(tables), 4) if tables else None,
            "tables_list_order_canonical": canon,
            "tables_list_order_non_canonical": len(tables) - canon,
            "failed_check_histogram": dict(failed.most_common()),
            "duplicate_coordinate_tables": sum(
                1 for t in tables if t["structure"]["duplicate_coordinates"]),
            "spanning_cell_tables": sum(1 for t in tables if t["structure"]["spanning_cells"]),
            "empty_cells": sum(t["structure"]["empty_cells"] for t in tables),
            "page_order_ok_documents": sum(1 for d in docs if d["layer2"]["page_order"]["page_order_ok"]),
            "documents_with_unmeasurable_strings": sum(
                1 for d in docs if d["layer2"]["page_order"]["strings_unmeasurable"]),
            "unmeasurable_strings_total": sum(
                d["layer2"]["page_order"]["strings_unmeasurable"] for d in docs),
            "evidence": {"tokens": tok,
                         "tokens_in_zero_regions": nore,
                         "orphan_recoverable_by_L5": orph,
                         "inside_table_but_no_region": nore - orph,
                         "multiply_owned": multi,
                         "orphan_rate": round(nore / tok, 4) if tok else None,
                         "overlap_rate": round(multi / tok, 4) if tok else None,
                         "evidence_coverage": round((tok - nore - multi) / tok, 4) if tok else None},
        },
        "status_vector_histogram": dict(Counter(
            tuple(sorted(t["status"].items())) for t in tables).most_common()) and {
            " / ".join(f"{k}={v}" for k, v in sorted(s.items())): c
            for s, c in Counter(
                tuple(sorted(t["status"].items())) for t in tables).items()
            for s in [dict(s)]},
        "documents": docs,
        "tables": tables,
    }
    (HERE / "layer2_scan49.json").write_text(json.dumps(payload, ensure_ascii=False))

    l1, l2 = payload["layer1"], payload["layer2"]
    print(f"LAYER 1 (frozen, unchanged): exact {l1['mean_text_recall']} "
          f"char {l1['mean_char_recall']} perfect {l1['docs_perfect']} "
          f"order_ok {l1['docs_order_ok']}")
    print(f"  same serializer, canonical table cells -> order_ok "
          f"{payload['layer1_counterfactual']['docs_order_ok']}")
    print(f"\nLAYER 2: {l2['documents']} docs  {l2['tables']} tables  {l2['cells']} cells")
    print(f"  structurally valid tables   : {l2['tables_structurally_valid']}/{l2['tables']} "
          f"({l2['structural_validity_rate']})")
    print(f"  list order canonical        : {l2['tables_list_order_canonical']}/{l2['tables']}")
    print(f"  failed checks               : {l2['failed_check_histogram']}")
    print(f"  duplicate-coordinate tables : {l2['duplicate_coordinate_tables']}")
    print(f"  spanning-cell tables        : {l2['spanning_cell_tables']}")
    print(f"  page_order_ok documents     : {l2['page_order_ok_documents']}/{n}")
    print(f"  unmeasurable strings        : {l2['unmeasurable_strings_total']} "
          f"in {l2['documents_with_unmeasurable_strings']} documents")
    print(f"  evidence                    : {l2['evidence']}")
    print(f"\nstatus vectors: {payload['status_vector_histogram']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
