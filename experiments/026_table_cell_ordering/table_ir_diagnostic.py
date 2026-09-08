"""026 Phase 1 -- what is actually wrong with table cell ordering?

Offline. Reads the frozen 025 baseline IR under
`experiments/025_layout_evidence_recall/_runs/coverage/*/final/document.json`
(produced at commit 0355e79, text_sha-identical to 024's frozen `l5` arm on
49/49 documents). No pipeline, no OCR, no model, no GPU.

025 reported "0 cells carry row_index / col_index". That was a measurement
artifact: the schema fields are `row` and `col` (schemas/table.py), and the
025 diagnostic queried `row_index`/`col_index`, which do not exist and so
read as None on every cell. This re-measures with the real field names and
separates three questions 025 conflated:

  Q1  Is the cells LIST in geometric order?          (what 025 measured)
  Q2  Are the `row`/`col` VALUES geometrically correct?  (what matters)
  Q3  Who actually depends on which of the two?

    python experiments/026_table_cell_ordering/table_ir_diagnostic.py
"""
from __future__ import annotations

import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
BASE = REPO / "experiments/025_layout_evidence_recall/_runs/coverage"


def yc(b):
    return (b["y0"] + b["y1"]) / 2


def xc(b):
    return (b["x0"] + b["x1"]) / 2


def row_order_by(cells, anchor):
    """Order the DECLARED rows of a table by a geometric anchor.

    This does not re-cluster. The IR already groups cells into rows via
    `cell.row`; the only question is whether that grouping's ORDER agrees
    with geometry. Re-clustering from scratch is what the first version of
    this diagnostic did, and it produced 66 false positives on tables whose
    row bands genuinely overlap (`long_policy_vi_60p` row 3 spans
    839.9-944.4 while row 4 spans 857.8-964.7). Grouping is not in question;
    ordering is.

    anchor "y0"  -- the row's topmost edge, min(y0). This is the rule
                    production's `_renumber_rows_by_position` already uses.
    anchor "yc"  -- the row's mean cell centre, the anchor the 026 brief
                    proposed as preferable.
    """
    by_row = {}
    for c in cells:
        by_row.setdefault(c["row"], []).append(c)
    if anchor == "y0":
        key = lambda cs: min(z["bbox"]["y0"] for z in cs)
    else:
        key = lambda cs: sum(yc(z["bbox"]) for z in cs) / len(cs)
    return [r for r, _ in sorted(by_row.items(), key=lambda kv: key(kv[1]))], by_row


def main() -> int:
    dirs = {p.name.rsplit("-", 1)[0]: p for p in BASE.iterdir() if p.is_dir()}
    rows = []
    for did, d in sorted(dirs.items()):
        doc = json.loads((d / "final" / "document.json").read_text())
        for pg in doc["pages"]:
            for tb in pg.get("tables") or []:
                cells = tb.get("cells") or []
                withbox = [c for c in cells if isinstance(c.get("bbox"), dict)]
                degenerate = [c for c in withbox
                              if c["bbox"]["x1"] <= c["bbox"]["x0"]
                              or c["bbox"]["y1"] <= c["bbox"]["y0"]]
                spans = [c for c in cells if c.get("row_span", 1) > 1 or c.get("col_span", 1) > 1]

                # Q1: is the LIST in geometric (row-major by position) order?
                list_order_y = [c["bbox"]["y0"] for c in withbox]
                list_is_geometric = list_order_y == sorted(list_order_y)

                # Q2: are the row/col VALUES geometrically correct?
                heights = [c["bbox"]["y1"] - c["bbox"]["y0"] for c in withbox]
                ord_y0, by_row = row_order_by(withbox, "y0")
                ord_yc, _ = row_order_by(withbox, "yc")
                declared = sorted(by_row)
                rows_correct_y0 = ord_y0 == declared
                rows_correct_yc = ord_yc == declared
                # columns: within each declared row, does col order agree with x?
                col_bad = 0
                for r, cs in by_row.items():
                    by_x = [z["col"] for z in sorted(cs, key=lambda z: z["bbox"]["x0"])]
                    if by_x != sorted(by_x):
                        col_bad += 1
                cols_correct = col_bad == 0
                rowcol_correct = rows_correct_y0 and cols_correct

                band_ranges = [(min(z["bbox"]["y0"] for z in cs),
                                max(z["bbox"]["y1"] for z in cs)) for _, cs in
                               sorted(by_row.items(), key=lambda kv: min(z["bbox"]["y0"] for z in kv[1]))]
                crossing = sum(1 for i in range(len(band_ranges))
                               for j in range(i + 1, len(band_ranges))
                               if band_ranges[i][1] > band_ranges[j][0])

                rows.append({
                    "document_id": did, "table_id": tb.get("id"),
                    "page": pg.get("index"),
                    "n_cells": len(cells), "cells_with_bbox": len(withbox),
                    "bbox_valid": len(withbox) == len(cells) and not degenerate,
                    "degenerate_boxes": len(degenerate),
                    "spanning_cells": len(spans),
                    "declared_n_rows": tb.get("n_rows"), "declared_n_cols": tb.get("n_cols"),
                    "inferred_n_rows": len(by_row),
                    "inferred_n_cols": max((len(cs) for cs in by_row.values()), default=0),
                    "median_cell_height_px": round(statistics.median(heights), 2) if heights else None,
                    "y0_list_order": [round(v, 1) for v in list_order_y],
                    "Q1_list_in_geometric_order": list_is_geometric,
                    "Q2_row_order_correct_anchor_y0": rows_correct_y0,
                    "Q2_row_order_correct_anchor_ycentre": rows_correct_yc,
                    "Q2_col_values_correct": cols_correct,
                    "Q2_rowcol_fully_correct": rowcol_correct,
                    "rows_with_bad_col_order": col_bad,
                    "bands_crossing": crossing,
                })

    q1_bad = [r for r in rows if not r["Q1_list_in_geometric_order"]]
    q2_bad = [r for r in rows if not r["Q2_rowcol_fully_correct"]]
    payload = {
        "source": "experiments/025_layout_evidence_recall/_runs/coverage (frozen 025 baseline IR)",
        "baseline_commit": "0355e79476f87d4613dd4d470518eabcfc73909a",
        "correction_to_025": "025 reported '0 cells carry row_index/col_index'. The schema "
                             "fields are `row` and `col`; `row_index`/`col_index` do not exist, "
                             "so that statement measured a missing key, not missing metadata.",
        "totals": {
            "tables": len(rows),
            "cells": sum(r["n_cells"] for r in rows),
            "tables_with_list_out_of_geometric_order": len(q1_bad),
            "tables_with_incorrect_row_col_values": len(q2_bad),
            "tables_with_degenerate_boxes": sum(1 for r in rows if r["degenerate_boxes"]),
            "tables_with_spanning_cells": sum(1 for r in rows if r["spanning_cells"]),
            "tables_with_missing_bboxes": sum(1 for r in rows if r["cells_with_bbox"] != r["n_cells"]),
            "tables_with_crossing_bands": sum(1 for r in rows if r["bands_crossing"]),
        },
        "anchor_comparison": {
            "tables_correct_with_y0": sum(1 for r in rows if r["Q2_row_order_correct_anchor_y0"]),
            "tables_correct_with_ycentre": sum(1 for r in rows if r["Q2_row_order_correct_anchor_ycentre"]),
            "finding": "y0 (top edge) is the correct anchor; the y-centre anchor the "
                       "brief proposed inverts rows whenever one row is much taller "
                       "than its neighbour (hc_tiny_cells_vi row 2 is 70px vs ~20px, "
                       "so its centre falls below row 3's). Production's "
                       "_renumber_rows_by_position already anchors on min(y0).",
        },
        "Q1_list_out_of_order_tables": [r["document_id"] for r in q1_bad],
        "Q2_incorrect_rowcol_tables": [r["document_id"] for r in q2_bad],
        "tables": rows,
    }
    (HERE / "table_ir_diagnostic.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False))

    t = payload["totals"]
    print(f"tables {t['tables']}  cells {t['cells']}")
    print(f"  Q1  cells LIST out of geometric order : {t['tables_with_list_out_of_geometric_order']}")
    print(f"  Q2  row/col VALUES incorrect          : {t['tables_with_incorrect_row_col_values']}")
    print(f"  degenerate boxes / spanning / missing bbox / crossing bands: "
          f"{t['tables_with_degenerate_boxes']} / {t['tables_with_spanning_cells']} / "
          f"{t['tables_with_missing_bboxes']} / {t['tables_with_crossing_bands']}")
    print(f"\nQ1 offenders ({len(q1_bad)}): {sorted({r['document_id'] for r in q1_bad})}")
    print(f"Q2 offenders ({len(q2_bad)}): {sorted({r['document_id'] for r in q2_bad})}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
