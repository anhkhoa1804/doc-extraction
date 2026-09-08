"""029 Phase 7 -- decompose Layer-1 order failure into three causal channels.

Offline, read-only. Extends 027's table-vs-page decomposition with the
channel discovered in Phase 6: Layer 1 never reads `Page.reading_order`,
only raw element-list order, so a scrambled reading_order can be invisible
to it whenever list order happens to look monotonic.

For every document/arm, computes THREE independent boolean order checks so
each failure is attributed to real structural evidence, not inferred from a
score delta:

  A. table_order_ok        canonical (row,col) table serialization
                            (027's transform, reused unchanged)
  B. list_order_page_ok    non-table elements in RAW LIST order (what
                            Layer 1 actually reads)
  C. reading_order_page_ok non-table elements in Page.reading_order
                            (production's own computed answer; what
                            page_order_ok in 028 reads)

Layer1 order_ok = A(as serialized) AND B, by construction (027 proved
document_text = elements-in-list-order + tables-in-list-order).

    python experiments/029_deep_forensic_replay/order_decomposition.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
L28 = REPO / "experiments/028_layer2_evaluation"
sys.path.insert(0, str(L28))
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "research/production_corpus"))
sys.path.insert(0, str(REPO / "experiments/023_evidence_centric"))

from run_benchmark import _norm  # noqa: E402
from page_order import ordered_elements  # noqa: E402


def positions_monotonic(text: str, strings: list[str]) -> tuple[bool, int, int]:
    pos = [text.find(_norm(s)) for s in strings]
    found = [p for p in pos if p >= 0]
    return found == sorted(found), len(found), len(strings)


def table_text_canonical(doc: dict) -> str:
    parts = []
    for pg in doc.get("pages") or []:
        for tb in pg.get("tables") or []:
            flat = []
            for row in tb.get("cells") or []:
                flat.extend(row if isinstance(row, list) else [row])
            for c in sorted(flat, key=lambda z: (z.get("row", 0), z.get("col", 0))):
                if c.get("text"):
                    parts.append(c["text"])
    return _norm("\n".join(parts))


def full_text_list_order(doc: dict, table_canonical: bool) -> str:
    parts = []
    for pg in doc.get("pages") or []:
        for el in pg.get("elements") or []:
            if el.get("text"):
                parts.append(el["text"])
        for tb in pg.get("tables") or []:
            flat = []
            for row in tb.get("cells") or []:
                flat.extend(row if isinstance(row, list) else [row])
            if table_canonical:
                flat = sorted(flat, key=lambda z: (z.get("row", 0), z.get("col", 0)))
            for c in flat:
                if c.get("text"):
                    parts.append(c["text"])
    return _norm("\n".join(parts))


def non_table_text(doc: dict, use_reading_order: bool) -> str:
    parts = []
    for pg in doc.get("pages") or []:
        els = ordered_elements(pg) if use_reading_order else (pg.get("elements") or [])
        for el in els:
            if el.get("type") == "table":
                continue
            if el.get("text"):
                parts.append(el["text"])
    return _norm("\n".join(parts))


def main() -> int:
    corpus = {d["document_id"]: d for d in
             json.loads((REPO / "research/production_corpus/corpus/manifest.json").read_text())["documents_list"]}
    scan = {d["document_id"]: d for d in
           json.loads((REPO / "experiments/024_ocr_fidelity_recovery/scan_cohort_manifest.json").read_text())["documents_list"]}
    inv = json.loads((HERE / "cohort_inventory.json").read_text())

    rows, channel_counts = [], Counter()
    for a in inv["arms"]:
        if a["is_smoke_or_warmup"] or a["manifest"].startswith("NONE"):
            continue
        man = scan if a["manifest"] == "scan_cohort_manifest" else corpus
        root = REPO / a["artifact_root"]
        for f in sorted(root.rglob("final/document.json")):
            did = f.parent.parent.name.rsplit("-", 1)[0]
            entry = man.get(did)
            if entry is None or not entry.get("must_contain"):
                continue
            doc = json.loads(f.read_text())
            required = entry["must_contain"]

            t_legacy = full_text_list_order(doc, table_canonical=False)
            layer1_ok, _, _ = positions_monotonic(t_legacy, required)

            t_A = table_text_canonical(doc)
            t_list_full = full_text_list_order(doc, table_canonical=True)
            table_ok, _, _ = positions_monotonic(t_list_full, required)

            nt_list = non_table_text(doc, use_reading_order=False)
            list_page_ok, _, _ = positions_monotonic(nt_list, required)

            nt_ro = non_table_text(doc, use_reading_order=True)
            ro_page_ok, n_meas, n_req = positions_monotonic(nt_ro, required)

            # Channel attribution -- corrected. Each test asks "if I fix ONLY
            # this one thing, does order_ok become True?", checked against
            # table_ok / list_page_ok directly rather than inferred.
            #
            # An earlier version of this classifier required table_ok==False
            # to attribute a table-order failure, which is backwards: table_ok
            # already means "canonicalizing tables alone fixes the sequence".
            # Caught by spot-checking cmb_borderless_lowcontrast_en, one of
            # 027's own 4 known table-order documents, which this bug had
            # placed in "unattributed" despite table_ok=True.
            if layer1_ok:
                channel = "layer1_ok"
            elif table_ok:
                # canonicalizing ONLY the table cells (keeping the elements-
                # before-tables append structure) already fixes the sequence.
                channel = "table_order_failure"
            elif list_page_ok:
                # non-table elements ALONE are monotonic, and table
                # canonicalization alone did NOT fix the full sequence ->
                # the append boundary itself (every element precedes every
                # table regardless of true position) is implicated, possibly
                # together with table order.
                channel = "append_boundary_failure"
            else:
                # non-table elements themselves are not monotonic in raw
                # list order -- a page-level ordering problem independent
                # of any table.
                channel = "list_page_order_failure"
            channel_counts[channel] += 1

            # does reading_order surface something list-order missed?
            reading_order_extra_failure = list_page_ok and not ro_page_ok
            if reading_order_extra_failure:
                channel_counts["reading_order_reveals_hidden_failure"] += 1

            rows.append({
                "milestone": a["milestone"], "arm": a["arm"], "document_id": did,
                "layer1_order_ok": layer1_ok,
                "table_order_ok": table_ok,
                "list_page_order_ok": list_page_ok,
                "reading_order_page_order_ok": ro_page_ok,
                "channel": channel,
                "reading_order_reveals_hidden_failure": reading_order_extra_failure,
            })

    payload = {
        "commit": inv["commit"],
        "method": "each of A/B/C computed independently from structural IR evidence, "
                 "not inferred from score deltas; layer1_order_ok is the frozen "
                 "run_ab.order_ok logic reproduced over the frozen document_text shape",
        "total_document_arm_pairs": len(rows),
        "channel_counts": dict(channel_counts),
        "layer1_failures_total": sum(1 for r in rows if not r["layer1_order_ok"]),
        "of_those__table_order_failure": sum(1 for r in rows if r["channel"] == "table_order_failure"),
        "of_those__append_boundary_failure": sum(1 for r in rows if r["channel"] == "append_boundary_failure"),
        "of_those__list_page_order_failure": sum(1 for r in rows if r["channel"] == "list_page_order_failure"),
        "reading_order_hidden_failures": sum(1 for r in rows if r["reading_order_reveals_hidden_failure"]),
        "reading_order_hidden_failure_documents": sorted({
            (r["milestone"], r["arm"], r["document_id"]) for r in rows
            if r["reading_order_reveals_hidden_failure"]}),
        "rows": rows,
    }
    (HERE / "order_decomposition.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False))

    print(f"document-arm pairs: {len(rows)}")
    print(f"Layer1 order failures: {payload['layer1_failures_total']}")
    print(f"  table_order_failure     (canonicalizing tables alone fixes it)    : {payload['of_those__table_order_failure']}")
    print(f"  append_boundary_failure (elements-before-tables structure at fault) : {payload['of_those__append_boundary_failure']}")
    print(f"  list_page_order_failure (non-table elements themselves scrambled)   : {payload['of_those__list_page_order_failure']}")
    print(f"\nreading_order reveals a HIDDEN failure (list order looked fine, "
          f"actual reading_order is not): {payload['reading_order_hidden_failures']}")
    for m, a_, d_ in payload["reading_order_hidden_failure_documents"]:
        print(f"    {m} {a_} {d_}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
