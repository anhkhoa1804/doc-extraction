"""025 line 8 -- reading-order attribution. Do NOT blame compute_reading_order.

Offline. Reads the IR that `coverage_instrument.py` already wrote under
`_runs/coverage/`; runs no pipeline, no OCR, no GPU.

`order_ok` is not a property of `compute_reading_order`. It is computed by
`run_ab.score` from the character positions at which the `must_contain`
strings appear in `document_text(document)`, and `document_text` serializes
each page as ALL element text first, then ALL table cell text. So an
out-of-order verdict can come from three different places, and this
separates them:

  region ordering  -- page elements carry a wrong `order_index`
  cell ordering    -- elements are ordered correctly and the TABLE's cells
                      are serialized in a wrong sequence
  token ordering   -- a single element's own text has words transposed

Each order_ok=False document is reported with its region count, overlap
rate, orphan rate, element order, and the offending string, so the blame
lands where the evidence puts it.

    python experiments/025_layout_evidence_recall/reading_order_attribution.py
"""
from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNS = HERE / "_runs" / "coverage"


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", s or "")).strip().lower()


def assemble(doc: dict) -> tuple[str, list[dict]]:
    """Reproduce run_benchmark.document_text, recording each part's origin."""
    parts, origin = [], []
    for pg in doc["pages"]:
        for el in pg.get("elements") or []:
            if el.get("text"):
                parts.append(el["text"])
                origin.append({"kind": "element", "id": el["id"], "type": el["type"],
                               "order_index": el.get("order_index")})
        for tb in pg.get("tables") or []:
            for i, c in enumerate(tb.get("cells") or []):
                t = c.get("text") if isinstance(c, dict) else None
                if t:
                    parts.append(t)
                    origin.append({"kind": "table_cell", "table": tb.get("id"),
                                   "cell_index": i, "row_index": c.get("row_index"),
                                   "col_index": c.get("col_index"),
                                   "bbox_y0": (c.get("bbox") or {}).get("y0")
                                   if isinstance(c.get("bbox"), dict) else None})
    return _norm("\n".join(parts)), origin


def main() -> int:
    ds = json.loads((HERE / "coverage_dataset.json").read_text())
    docs = {r["document_id"]: r for r in ds["documents"]}
    dirs = {p.name.rsplit("-", 1)[0]: p for p in RUNS.iterdir() if p.is_dir()}

    out = []
    for did, r in docs.items():
        if r["order_ok"]:
            continue
        f = dirs[did] / "final" / "document.json"
        doc = json.loads(f.read_text())
        text, origin = assemble(doc)

        positions, prev, offenders = [], -1, []
        for s in r["must_contain"]:
            i = text.find(_norm(s))
            positions.append({"string": s, "pos": i})
            if 0 <= i <= prev:
                offenders.append(s)
            prev = max(prev, i)

        pages = [p for p in ds["pages"] if p["document_id"] == did]
        orphans = sum(1 for p in pages for t in p["tokens"] if t["claim"] == "orphan")
        overlap = sum(1 for p in pages for t in p["tokens"] if t["n_owners"] > 1)
        tokens = sum(len(p["tokens"]) for p in pages)

        els = [e for pg in doc["pages"] for e in (pg.get("elements") or [])]
        oi = [e.get("order_index") for e in els]
        elements_monotonic = oi == sorted(x for x in oi if x is not None)

        cells = [c for pg in doc["pages"] for tb in (pg.get("tables") or [])
                 for c in (tb.get("cells") or [])]
        ys = [(c.get("bbox") or {}).get("y0") for c in cells
              if isinstance(c.get("bbox"), dict)]
        cells_sorted_by_y = ys == sorted(ys) if ys else None
        indexed = sum(1 for c in cells if c.get("row_index") is not None)

        # where does the offending string come from?
        blame = "unattributed"
        if offenders:
            off = _norm(offenders[0])
            src = None
            for o, part in zip(origin, [p for p in
                                        [e["text"] for pg in doc["pages"]
                                         for e in (pg.get("elements") or []) if e.get("text")]
                                        + [c.get("text") for pg in doc["pages"]
                                           for tb in (pg.get("tables") or [])
                                           for c in (tb.get("cells") or []) if c.get("text")]]):
                if off in _norm(part):
                    src = o
                    break
            if src and src["kind"] == "table_cell":
                blame = "cell_ordering"
            elif src and src["kind"] == "element":
                blame = "region_ordering" if not elements_monotonic else "token_ordering"

        out.append({
            "document_id": did,
            "regions": sum(len(p["regions"]) for p in pages),
            "region_labels": dict(Counter(rg["label"] for p in pages for rg in p["regions"])),
            "tokens": tokens,
            "orphans": orphans, "orphan_rate": round(orphans / tokens, 4) if tokens else None,
            "overlap_tokens": overlap,
            "overlap_rate": round(overlap / tokens, 4) if tokens else None,
            "tables_found": r["tables_found"], "tables_expected": r["tables_expected"],
            "n_elements": len(els), "element_order_index": oi,
            "elements_monotonic": elements_monotonic,
            "n_cells": len(cells), "cells_with_row_index": indexed,
            "cells_sorted_by_y": cells_sorted_by_y,
            "cell_y0_sequence": ys,
            "positions": positions,
            "out_of_order_strings": offenders,
            "attribution": blame,
        })

    payload = {
        "commit": ds["commit"],
        "note": "order_ok comes from run_ab.score over document_text(), which "
                "serializes elements then table cells; it is not a direct test "
                "of compute_reading_order.",
        "documents": out,
        "attribution_histogram": dict(Counter(o["attribution"] for o in out)),
    }
    (HERE / "reading_order_attribution.json").write_text(
        json.dumps(payload, indent=1, ensure_ascii=False))

    print(f"order_ok=False documents: {len(out)}")
    for o in out:
        print(f"\n  {o['document_id']}")
        print(f"    regions {o['regions']} {o['region_labels']}  orphans {o['orphans']} "
              f"overlap {o['overlap_tokens']}  tables {o['tables_found']}/{o['tables_expected']}")
        print(f"    elements {o['n_elements']} order_index {o['element_order_index']} "
              f"monotonic={o['elements_monotonic']}")
        print(f"    cells {o['n_cells']} with row_index {o['cells_with_row_index']} "
              f"sorted_by_y={o['cells_sorted_by_y']}  y0={o['cell_y0_sequence']}")
        print(f"    out of order: {o['out_of_order_strings']}  -> ATTRIBUTION: {o['attribution']}")
    print(f"\nattribution: {payload['attribution_histogram']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
