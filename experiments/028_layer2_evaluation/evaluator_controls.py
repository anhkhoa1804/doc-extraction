"""028 Phase 6 -- negative controls. Validating the EVALUATOR, not a model.

Synthetic IR built by hand, no OCR, no pipeline, no GPU. Each case asserts
what the Layer-2 views must say about it. A control that the evaluator
mis-reads is an evaluator bug, and finding one here is the point.

    python experiments/028_layer2_evaluation/evaluator_controls.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from structural_integrity import structural_integrity  # noqa: E402
from table_text import table_text  # noqa: E402


def cell(r, c, x0, y0, x1, y1, text="t"):
    return {"row": r, "col": c, "row_span": 1, "col_span": 1,
            "bbox": {"x0": x0, "y0": y0, "x1": x1, "y1": y1},
            "text": text, "is_header": False, "confidence": None}


def table(cells, nr, nc, bbox=(0, 0, 400, 400), tid="t0"):
    return {"id": tid, "bbox": {"x0": bbox[0], "y0": bbox[1], "x1": bbox[2], "y1": bbox[3]},
            "page_number": 1, "n_rows": nr, "n_cols": nc, "cells": cells,
            "source_backend": "synthetic", "confidence": None}


def doc(tbl):
    return {"document_id": "ctl", "pages": [{"index": 0, "width": 400, "height": 400,
                                             "elements": [], "tables": [tbl],
                                             "reading_order": []}]}


GRID = [cell(r, c, 10 + c * 100, 10 + r * 100, 90 + c * 100, 90 + r * 100, f"r{r}c{c}")
        for r in range(2) for c in range(2)]

CASES = []


def case(name, tbl, expect):
    CASES.append({"name": name, "table": tbl, "expect": expect})


case("01_correct_table", table(list(GRID), 2, 2),
     {"structurally_valid": True, "list_order_canonical": True, "failed": []})

shuf = [GRID[3], GRID[0], GRID[2], GRID[1]]
case("02_shuffled_list_correct_rowcol", table(shuf, 2, 2),
     {"structurally_valid": True, "list_order_canonical": False, "failed": []})

dup = list(GRID[:3]) + [cell(0, 0, 210, 210, 290, 290, "dupe")]
# The duplicate is placed at a genuinely different position (210,210), so it
# violates row/col coherence as well as uniqueness. Both are true and both are
# reported; the expectation was tightened when `rows_vertically_coherent` was
# added in Phase 7, not the evaluator loosened.
case("03_duplicate_rowcol", table(dup, 2, 2),
     {"structurally_valid": False, "failed": ["no_duplicate_coordinates",
                                              "rows_vertically_coherent",
                                              "cols_horizontally_coherent"]})

case("04_missing_cell", table(list(GRID[:3]), 2, 2),
     {"structurally_valid": True, "note": "a hole is not incoherence; "
                                          "n_cells < dense shape is reported separately"})

bad_r = list(GRID[:3]) + [cell(9, 1, 110, 110, 190, 190)]
case("05_invalid_row", table(bad_r, 2, 2),
     {"structurally_valid": False, "failed": ["coords_in_declared_range",
                                              "rows_contiguous"]})

bad_c = list(GRID[:3]) + [cell(1, 9, 110, 110, 190, 190)]
case("06_invalid_col", table(bad_c, 2, 2),
     {"structurally_valid": False, "failed": ["coords_in_declared_range",
                                              "cols_contiguous"]})

bad_b = list(GRID[:3]) + [{"row": 1, "col": 1, "row_span": 1, "col_span": 1,
                           "bbox": {"x0": 200, "y0": 200, "x1": 100, "y1": 100},
                           "text": "t", "is_header": False, "confidence": None}]
case("07_invalid_bbox", table(bad_b, 2, 2),
     {"structurally_valid": False, "failed": ["all_cell_bboxes_valid"]})

out = list(GRID[:3]) + [cell(1, 1, 900, 900, 980, 980)]
# A cell teleported to (900,900) is outside the table AND shares no band with
# the rest of its row/col. Both violations are real.
case("08_cell_outside_table_bbox", table(out, 2, 2),
     {"structurally_valid": False, "failed": ["cells_within_table_bbox",
                                              "rows_vertically_coherent",
                                              "cols_horizontally_coherent"]})

samet = [cell(r, c, 10 + c * 100, 10 + r * 100, 90 + c * 100, 90 + r * 100, "same")
         for r in range(2) for c in range(2)]
case("09_duplicate_text_distinct_cells", table(samet, 2, 2),
     {"structurally_valid": True, "note": "identical text in distinct valid cells is "
                                          "not a structural defect"})

empt = [cell(0, 0, 10, 10, 90, 90, ""), GRID[1], GRID[2], GRID[3]]
case("10_empty_cell", table(empt, 2, 2), {"structurally_valid": True})

multi_r = [cell(r, 0, 10, 10 + r * 60, 90, 60 + r * 60, f"r{r}") for r in range(5)]
case("11_multi_row_single_col", table(multi_r, 5, 1), {"structurally_valid": True})

multi_c = [cell(0, c, 10 + c * 70, 10, 60 + c * 70, 60, f"c{c}") for c in range(5)]
case("12_multi_col_single_row", table(multi_c, 1, 5), {"structurally_valid": True})


def main() -> int:
    results, failures = [], []
    for c in CASES:
        d = doc(c["table"])
        si = structural_integrity(d)[0]
        tt = table_text(d)[0]
        exp = c["expect"]
        checks = {
            "structurally_valid": si["structurally_valid"] == exp["structurally_valid"],
            "failed_checks_expected": (sorted(si["failed_checks"]) == sorted(exp["failed"])
                                       if "failed" in exp else None),
            "list_order_canonical": (si["list_order_canonical"] == exp["list_order_canonical"]
                                     if "list_order_canonical" in exp else None),
            "text_multiset_preserved": tt["text_multiset_identical"],
        }
        ok = all(v for v in checks.values() if v is not None)
        if not ok:
            failures.append(c["name"])
        results.append({"case": c["name"], "expected": exp,
                        "structurally_valid": si["structurally_valid"],
                        "failed_checks": si["failed_checks"],
                        "list_order_canonical": si["list_order_canonical"],
                        "n_cells": si["n_cells"],
                        "declared_shape": si["declared_shape"],
                        "observed_shape": si["observed_shape"],
                        "checks": checks, "passed": ok})

    payload = {"cases": len(results), "passed": len(results) - len(failures),
               "failed": failures, "results": results}
    (HERE / "evaluator_controls.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False))
    for r in results:
        print(f"  {'PASS' if r['passed'] else 'FAIL'}  {r['case']:<36} "
              f"valid={str(r['structurally_valid']):<5} "
              f"canonical={str(r['list_order_canonical']):<5} failed={r['failed_checks']}")
    print(f"\n{payload['passed']}/{payload['cases']} controls passed; failures: {failures or 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
