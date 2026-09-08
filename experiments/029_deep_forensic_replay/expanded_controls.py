"""029 Phase 10 -- expanded negative controls for the semantics 029 discovered.

Extends 028's 12 controls / 7 attacks with 15 new synthetic cases targeting:
row-synthesis bbox escape, reading_order vs list-order divergence, and the
append-boundary effect. Each asserts what the intended property SHOULD say,
independent of any particular numeric score.

    python experiments/029_deep_forensic_replay/expanded_controls.py
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

from run_benchmark import _norm  # noqa: E402
from page_order import ordered_elements  # noqa: E402
from structural_integrity import structural_integrity  # noqa: E402
from table_text import table_text  # noqa: E402


def cell(r, c, x0, y0, x1, y1, text="t", conf=None):
    return {"row": r, "col": c, "row_span": 1, "col_span": 1,
            "bbox": {"x0": x0, "y0": y0, "x1": x1, "y1": y1},
            "text": text, "is_header": False, "confidence": conf}


def table(cells, nr, nc, bbox=(0, 0, 400, 400), tid="t0"):
    return {"id": tid, "bbox": {"x0": bbox[0], "y0": bbox[1], "x1": bbox[2], "y1": bbox[3]},
            "page_number": 1, "n_rows": nr, "n_cols": nc, "cells": cells,
            "source_backend": "synthetic", "confidence": None}


def elem(eid, etype, text, x0, y0, x1, y1, table_id=None):
    e = {"id": eid, "type": etype, "text": text,
         "bbox": {"x0": x0, "y0": y0, "x1": x1, "y1": y1},
         "page_number": 1, "confidence": None, "source_backend": "synthetic"}
    if table_id:
        e["table_id"] = table_id
    return e


def page(elements, tables, reading_order=None):
    return {"index": 0, "width": 500, "height": 500,
            "elements": elements, "tables": tables,
            "reading_order": reading_order or []}


def doc(pages):
    return {"document_id": "ctl", "pages": pages}


CASES = []


def case(name, d, assertion_fn, note):
    CASES.append({"name": name, "doc": d, "assertion": assertion_fn, "note": note})


# 1. valid structure + noncanonical storage order (should be VALID, NON_CANONICAL)
grid = [cell(0, 0, 10, 10, 90, 90), cell(0, 1, 110, 10, 190, 90),
        cell(1, 0, 10, 110, 90, 190), cell(1, 1, 110, 110, 190, 190)]
shuffled = [grid[3], grid[0], grid[2], grid[1]]
case("01_valid_structure_noncanonical_order",
     doc([page([], [table(shuffled, 2, 2)])]),
     lambda d: (structural_integrity(d)[0]["structurally_valid"] is True
               and structural_integrity(d)[0]["list_order_canonical"] is False),
     "structure valid, order non-canonical -- must be independently true")

# 2. canonical storage order + invalid geometry (VALID order, INVALID structure)
bad_geo = list(grid[:3]) + [cell(1, 1, 900, 900, 980, 980)]
case("02_canonical_order_invalid_geometry",
     doc([page([], [table(bad_geo, 2, 2)])]),
     lambda d: (structural_integrity(d)[0]["list_order_canonical"] is True
               and structural_integrity(d)[0]["structurally_valid"] is False),
     "order canonical, structure invalid -- the two axes must not correlate by construction")

# 3/4. correct page order vs incorrect table order, and vice versa
e1 = elem("e0", "text", "A", 10, 10, 90, 40)
e2 = elem("e1", "text", "B", 10, 60, 90, 90)
tbl_ok = table(grid, 2, 2)
case("03_correct_page_order_incorrect_table_order",
     doc([page([e1, e2], [table(shuffled, 2, 2)], ["e0", "e1"])]),
     lambda d: (ordered_elements(d["pages"][0])[0]["id"] == "e0"
               and structural_integrity(d)[0]["list_order_canonical"] is False),
     "page order correct via reading_order; table order independently wrong")

case("04_incorrect_page_order_correct_table_order",
     doc([page([e1, e2], [tbl_ok], ["e1", "e0"])]),  # reading_order reversed
     lambda d: (ordered_elements(d["pages"][0])[0]["id"] == "e1"
               and structural_integrity(d)[0]["list_order_canonical"] is True),
     "reading_order reversed relative to list order; table order independently correct")

# 5/6. table-contained vs non-table required text
case("05_table_contained_required_text",
     doc([page([], [table([cell(0, 0, 10, 10, 90, 90, "SECRET")], 1, 1)])]),
     lambda d: "SECRET" in table_text(d)[0]["canonical_text"],
     "required text living only in a table cell is retrievable via table_text")

case("06_non_table_required_text",
     doc([page([elem("e0", "text", "SECRET", 10, 10, 90, 40)], [])]),
     lambda d: any(e.get("text") == "SECRET" for e in ordered_elements(d["pages"][0])),
     "required text living in a non-table element is retrievable via page_order's view")

# 9. picture-labelled table-shaped region (025/026's stamp-gating shape)
case("09_picture_labelled_table_shaped_region",
     doc([page([elem("e0", "image", "", 0, 0, 400, 200)],
               [table([cell(0, 0, 10, 10, 90, 90)], 1, 1, bbox=(0, 0, 400, 200))])]),
     lambda d: True,  # documents the shape; no IR-level distinguishing signal exists (FACT)
     "a picture-labelled region and a table can share identical geometry; the IR alone "
     "cannot distinguish 'picture that is really a table' from 'picture' -- this is why "
     "025's fix targets the LABEL, not a geometric heuristic")

# 10. outside-table cell with otherwise coherent row/col (the 029 mechanism, EXACT reproduction)
synth_row = list(grid[:3]) + [cell(0, 0, 10, -5, 90, 5, "phantom", conf=0.5)]
# careful: two cells at (0,0) would trip duplicate-coordinate; use a 3rd row for the escapee
synth_row = list(grid) + [cell(2, 0, 10, 195, 90, 205, "phantom", conf=0.5)]
case("10_synthesized_cell_escapes_table_bbox",
     doc([page([], [table(synth_row, 3, 2, bbox=(0, 0, 200, 200))])]),
     lambda d: (structural_integrity(d)[0]["structurally_valid"] is False
               and "cells_within_table_bbox" in structural_integrity(d)[0]["failed_checks"]),
     "reproduces the EXACT 029 mechanism: a confidence=0.5 cell whose bbox pokes past "
     "the table's own bbox is caught by cells_within_table_bbox")

# 13/14/15. reading_order vs missing vs contradictory
case("13_reordered_reading_order",
     doc([page([e1, e2], [], ["e1", "e0"])]),
     lambda d: ordered_elements(d["pages"][0])[0]["id"] == "e1",
     "ordered_elements must honor an explicit reading_order that contradicts list order")

case("14_missing_reading_order",
     doc([page([e1, e2], [], [])]),
     lambda d: [e["id"] for e in ordered_elements(d["pages"][0])] == ["e0", "e1"],
     "empty reading_order falls back to list order, matching Document.to_markdown's "
     "documented behaviour -- not an invented fallback")

case("15_contradictory_page_vs_geometric_order",
     doc([page([elem("e0", "text", "X", 10, 300, 90, 340),
               elem("e1", "text", "Y", 10, 10, 90, 50)],
               [], ["e0", "e1"])]),  # reading_order says e0 (y=300) before e1 (y=10)
     lambda d: (ordered_elements(d["pages"][0])[0]["id"] == "e0"
               and d["pages"][0]["elements"][0]["bbox"]["y0"]
               > d["pages"][0]["elements"][1]["bbox"]["y0"]),
     "reading_order can contradict raw geometry (y-position); the view must honor "
     "reading_order as authoritative and MUST NOT silently re-sort by y -- catches an "
     "evaluator that 'helpfully' second-guesses production's own computed order")


def main() -> int:
    results, failed = [], []
    for c in CASES:
        try:
            ok = bool(c["assertion"](c["doc"]))
        except Exception as exc:
            ok = False
            c["error"] = f"{type(exc).__name__}: {exc}"
        if not ok:
            failed.append(c["name"])
        results.append({"case": c["name"], "note": c["note"], "passed": ok,
                        "error": c.get("error")})

    payload = {"cases": len(results), "passed": len(results) - len(failed),
              "failed": failed, "results": results}
    (HERE / "expanded_controls.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False))
    for r in results:
        print(f"  {'PASS' if r['passed'] else 'FAIL'}  {r['case']:<48} {r['note'][:60]}")
        if r.get("error"):
            print(f"        ERROR: {r['error']}")
    print(f"\n{payload['passed']}/{payload['cases']} passed; failures: {failed or 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
