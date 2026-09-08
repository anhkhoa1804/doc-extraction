"""029 Phase 2 -- replay Layer 1 + Layer 2 across every frozen arm.

Offline, CPU only, read-only. Reuses 028's views verbatim (imported, not
copied) so results are directly comparable to the SCAN-49 baseline. Layer 1
is the frozen `run_ab.score` over the frozen `run_benchmark.document_text`,
executed unchanged on the real pydantic Document objects. No mutation of any
artifact; each arm's document.json files are only read.

Skips arms with no must_contain manifest (024/realscan_probe -- OmniDocBench
mechanism probe) and smoke/warmup arms (1 document, not a cohort).

    python experiments/029_deep_forensic_replay/replay_all_arms.py
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

import run_ab  # noqa: E402
from doc_extraction.schemas.document import Document  # noqa: E402
from run_benchmark import document_text as layer1_document_text  # noqa: E402

from page_order import page_order  # noqa: E402  -- 028's view, imported
from structural_integrity import structural_integrity  # noqa: E402
from table_structure import table_structure  # noqa: E402
from table_text import table_text  # noqa: E402

CORPUS_MANIFEST = REPO / "research/production_corpus/corpus/manifest.json"
SCAN_MANIFEST = REPO / "experiments/024_ocr_fidelity_recovery/scan_cohort_manifest.json"
RESULTS = HERE / "results"
RESULTS.mkdir(exist_ok=True)


def load_manifests():
    corpus = {d["document_id"]: d for d in json.loads(CORPUS_MANIFEST.read_text())["documents_list"]}
    scan = {d["document_id"]: d for d in json.loads(SCAN_MANIFEST.read_text())["documents_list"]}
    return corpus, scan


def replay_arm(milestone: str, arm: str, root: Path, files: list[Path], man: dict) -> dict:
    doc_rows, tables = [], []
    for f in sorted(files):
        did = f.parent.parent.name.rsplit("-", 1)[0]
        entry = man.get(did)
        if entry is None or not entry.get("must_contain"):
            continue
        raw = json.loads(f.read_text())

        try:
            pyd = Document.model_validate(raw)
            t1 = layer1_document_text(pyd)
            s1 = run_ab.score(entry, t1)
        except Exception as exc:
            s1 = {"text_recall": None, "char_recall": None, "order_ok": None,
                 "hallucinated": [], "found": 0, "required": len(entry.get("must_contain") or []),
                 "error": f"{type(exc).__name__}: {exc}"}

        tt = table_text(raw)
        ts = table_structure(raw)
        si = structural_integrity(raw)
        po = page_order(raw, entry["must_contain"])

        for a, c in zip(ts, si):
            tables.append({
                "milestone": milestone, "arm": arm, "document_id": did,
                "table_id": a["table_id"], "n_cells": a["n_cells"],
                "declared_shape": [a["declared_n_rows"], a["declared_n_cols"]],
                "source_backend": a["source_backend"],
                "structurally_valid": c["structurally_valid"],
                "failed_checks": c["failed_checks"],
                "list_order_canonical": c["list_order_canonical"],
                "duplicate_coordinates": a["duplicate_coordinates"],
                "spanning_cells": a["spanning_cells"],
                "cells_inside_table_bbox": a["cells_inside_table_bbox"],
                "cells_with_valid_bbox": a["cells_with_valid_bbox"],
                "empty_cells": a["empty_cells"],
                "labels": entry.get("hard_case_labels", []),
                "language": entry.get("language"),
                "document_type": entry.get("document_type"),
            })

        doc_rows.append({
            "document_id": did,
            "labels": entry.get("hard_case_labels", []),
            "language": entry.get("language"), "document_type": entry.get("document_type"),
            "layer1": s1,
            "layer2_page_order_ok": po["page_order_ok"],
            "layer2_strings_unmeasurable": po["strings_unmeasurable"],
            "layer2_unmeasurable_detail": po["unmeasurable_detail"],
            "layer2_n_tables": len(ts),
            "layer2_tables_valid": sum(1 for c in si if c["structurally_valid"]),
            "layer2_tables_canonical": sum(1 for c in si if c["list_order_canonical"]),
        })

    n = len(doc_rows)
    if n == 0:
        return None
    ok_rows = [r for r in doc_rows if r["layer1"].get("text_recall") is not None]

    def mean(key):
        vals = [r["layer1"][key] for r in ok_rows]
        return round(sum(vals) / len(vals), 4) if vals else None

    n_tables = len(tables)
    valid_tables = sum(1 for t in tables if t["structurally_valid"])
    canon_tables = sum(1 for t in tables if t["list_order_canonical"])

    summary = {
        "milestone": milestone, "arm": arm, "documents": n,
        "documents_scored": len(ok_rows), "documents_errored": n - len(ok_rows),
        "layer1": {
            "mean_text_recall": mean("text_recall"), "mean_char_recall": mean("char_recall"),
            "docs_perfect": sum(1 for r in ok_rows if r["layer1"]["text_recall"] == 1.0),
            "docs_order_ok": sum(1 for r in ok_rows if r["layer1"]["order_ok"]),
            "docs_hallucinated": sum(1 for r in ok_rows if r["layer1"]["hallucinated"]),
        },
        "layer2": {
            "page_order_ok_documents": sum(1 for r in doc_rows if r["layer2_page_order_ok"]),
            "tables": n_tables,
            "structurally_valid_tables": valid_tables,
            "structurally_invalid_tables": n_tables - valid_tables,
            "list_order_canonical_tables": canon_tables,
            "list_order_non_canonical_tables": n_tables - canon_tables,
            "unmeasurable_strings_total": sum(r["layer2_strings_unmeasurable"] for r in doc_rows),
            "documents_with_unmeasurable_strings": sum(
                1 for r in doc_rows if r["layer2_strings_unmeasurable"]),
        },
        "documents": doc_rows,
    }
    out_name = f"{milestone}__{arm.replace('/', '_')}.json"
    (RESULTS / out_name).write_text(json.dumps(summary, indent=1, ensure_ascii=False))
    return {"milestone": milestone, "arm": arm, "file": out_name,
           "documents": n, "layer1": summary["layer1"], "layer2": summary["layer2"]}, tables


def main() -> int:
    corpus, scan = load_manifests()
    inv = json.loads((HERE / "cohort_inventory.json").read_text())

    all_summaries, all_tables = [], []
    for a in inv["arms"]:
        if a["is_smoke_or_warmup"]:
            continue
        if a["manifest"].startswith("NONE"):
            continue
        man = scan if a["manifest"] == "scan_cohort_manifest" else corpus
        root = REPO / a["artifact_root"]
        files = sorted(root.rglob("final/document.json"))
        if not files:
            continue
        result = replay_arm(a["milestone"], a["arm"], root, files, man)
        if result is None:
            continue
        summary, tables = result
        all_summaries.append(summary)
        all_tables.extend(tables)
        l1, l2 = summary["layer1"], summary["layer2"]
        print(f"  {a['milestone']} {a['arm']:<42} docs={summary['documents']:<3} "
              f"exact={l1['mean_text_recall']} order_ok={l1['docs_order_ok']} | "
              f"tables={l2['tables']:<3} valid={l2['structurally_valid_tables']:<3} "
              f"canon={l2['list_order_canonical_tables']:<3} "
              f"page_order_ok={l2['page_order_ok_documents']}", flush=True)

    all_arms_payload = {
        "commit": inv["commit"],
        "arms_replayed": len(all_summaries),
        "total_tables": len(all_tables),
        "summaries": all_summaries,
    }
    (HERE / "results" / "all_arms.json").write_text(json.dumps(all_arms_payload, indent=1, ensure_ascii=False))
    (HERE / "results" / "all_tables.json").write_text(json.dumps(all_tables, indent=1, ensure_ascii=False))

    print(f"\narms replayed: {len(all_summaries)}")
    print(f"total (arm, table) rows: {len(all_tables)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
