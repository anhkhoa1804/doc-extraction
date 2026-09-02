"""Phase 1 — reproduce the table corruption, and measure what the fix does.

Compares the two cell-text strategies that live side by side in
`pymupdf_table_backend.convert_pymupdf_table`:

  * `runs=None`  -> PyMuPDF's own `extract()`, the shipped HEAD behaviour
  * `runs=[...]` -> run-ownership assignment, the uncommitted fix

Both run in one process against the same detected table objects, so the
comparison isolates the cell-text strategy and nothing else. No stashing, no
second checkout, no rebuild.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from doc_extraction.backends.pymupdf_table_backend import (  # noqa: E402
    convert_pymupdf_table,
    page_text_runs,
)
from doc_extraction.ingest.table_quality import assess_table  # noqa: E402

CORPUS = Path(__file__).resolve().parents[3] / "research/production_corpus/corpus"

STAMPED = ["hc_stamp_table_vi", "cmb_stamp_table_vi", "cmb_stamp_boundary_vi"]
CONTROLS = ["ord_invoice_vi", "ord_purchase_order_en", "hc_merged_en"]


def runs_of(page):
    return [dict(r) for r in page_text_runs(page)]


def grid(table):
    return {f"r{c.row}c{c.col}": (c.text or "").strip() for c in table.cells}


def boxes(table):
    return {f"r{c.row}c{c.col}": (None if c.bbox is None else
            [round(v, 2) for v in c.bbox.as_tuple()]) for c in table.cells}


def analyse(doc_name):
    path = CORPUS / f"{doc_name}.pdf"
    if not path.exists():
        return {"document": doc_name, "error": "missing"}
    doc = pymupdf.open(path)
    out = {"document": doc_name, "pages": []}
    try:
        for pno in range(doc.page_count):
            page = doc[pno]
            found = page.find_tables()
            if not found.tables:
                continue
            page_rec = {"page": pno, "tables": []}
            all_runs = page_text_runs(page)
            for i, t in enumerate(found.tables):
                tid = f"p{pno}-t{i}"
                # OLD: extract()-based cell text
                old = convert_pymupdf_table(t, pno, tid, runs=None)
                # NEW: run-ownership cell text
                tr = [dict(r) for r in all_runs]
                new = convert_pymupdf_table(t, pno, tid, runs=tr)

                considered = [r for r in tr if r.get("_cell") is not None]
                report = assess_table(new, considered)

                og, ng = grid(old), grid(new)
                changed = {k: {"old": og.get(k, ""), "new": ng.get(k, "")}
                           for k in set(og) | set(ng) if og.get(k, "") != ng.get(k, "")}

                # Fragment test: does a cell hold a piece of a run rather than
                # whole runs? This is the interleaving signature.
                source_runs = [s["text"].strip() for s in all_runs if s["text"].strip()]

                def fragments(g):
                    bad = []
                    for k, v in g.items():
                        if not v:
                            continue
                        for tok in v.split():
                            if len(tok) < 2:
                                continue
                            if not any(tok in r for r in source_runs):
                                bad.append({"cell": k, "text": v, "token": tok})
                                break
                    return bad

                page_rec["tables"].append({
                    "id": tid,
                    "shape": [new.n_rows, new.n_cols],
                    "bbox": None if new.bbox is None else [round(v, 2) for v in new.bbox.as_tuple()],
                    "n_runs_on_page": len(all_runs),
                    "n_runs_owned": len(considered),
                    "old_fragmented_cells": fragments(og),
                    "new_fragmented_cells": fragments(ng),
                    "changed_cells": changed,
                    "gate": {
                        "trusted": report.trusted,
                        "severity": report.severity,
                        "signals": report.signals,
                        "affected_cells": [f"r{r}c{c}" for r, c in report.affected_cells],
                    },
                    "old_grid": og,
                    "new_grid": ng,
                    "cell_bboxes": boxes(new),
                })
            if page_rec["tables"]:
                out["pages"].append(page_rec)
    finally:
        doc.close()
    return out


def main():
    result = {"stamped": [analyse(d) for d in STAMPED],
              "controls": [analyse(d) for d in CONTROLS]}

    for group in ("stamped", "controls"):
        print(f"\n{'='*72}\n{group.upper()}\n{'='*72}")
        for rec in result[group]:
            if rec.get("error"):
                print(f"  {rec['document']}: {rec['error']}")
                continue
            n_t = sum(len(p["tables"]) for p in rec["pages"])
            print(f"\n--- {rec['document']}  ({n_t} table(s)) ---")
            for p in rec["pages"]:
                for t in p["tables"]:
                    of, nf = t["old_fragmented_cells"], t["new_fragmented_cells"]
                    print(f"  {t['id']} {t['shape'][0]}x{t['shape'][1]}  "
                          f"runs owned {t['n_runs_owned']}/{t['n_runs_on_page']}")
                    print(f"    fragmented cells:  OLD {len(of)}  ->  NEW {len(nf)}")
                    for f in of[:4]:
                        print(f"      OLD {f['cell']}: {f['text']!r}  (token {f['token']!r})")
                    for f in nf[:4]:
                        print(f"      NEW {f['cell']}: {f['text']!r}  (token {f['token']!r})")
                    if t["changed_cells"]:
                        print(f"    cells changed by the fix: {len(t['changed_cells'])}")
                        for k, v in list(t["changed_cells"].items())[:6]:
                            print(f"      {k}: {v['old']!r}  ->  {v['new']!r}")
                    g = t["gate"]
                    print(f"    gate: trusted={g['trusted']} severity={g['severity']}")
                    for s in g["signals"]:
                        print(f"      signal: {s}")
                    if g["affected_cells"]:
                        print(f"      cells: {', '.join(g['affected_cells'][:8])}")

    out = Path(__file__).parent / "phase1_ownership.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
