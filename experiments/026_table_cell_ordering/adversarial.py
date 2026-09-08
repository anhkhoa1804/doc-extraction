"""026 Phase 5 -- adversarial controls for the geometric ordering rule.

Offline, synthetic, deterministic. No pipeline, no OCR, no GPU.

Phase 1 showed production already carries correct `row`/`col` on 94/94
tables, so canonicalization has two separable parts and this tests both:

  RULE-A  recover (row, col) from cell geometry alone
  RULE-B  order the cells list by (row, col)

RULE-B is trivially correct given correct row/col. RULE-A is the part that
could be wrong, and the frozen corpus already falsified the anchor the 026
brief preferred: on `hc_tiny_cells_vi` row 2 is 70px tall against ~20px
neighbours, so its y-CENTRE falls below row 3's and a centre-anchored rule
inverts them. The rule under test therefore anchors on the row's top edge,
min(y0) -- which is what production's `_renumber_rows_by_position` uses.

Twelve cases the brief names, each with an asserted expected assignment.
A case the rule cannot solve from geometry is recorded as a LIMITATION
rather than patched with another heuristic.

    python experiments/026_table_cell_ordering/adversarial.py
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent


def cell(r, c, x0, y0, x1, y1, text=""):
    return {"row": r, "col": c, "bbox": {"x0": x0, "y0": y0, "x1": x1, "y1": y1}, "text": text}


def assign(cells):
    """RULE-A: recover (row, col) from geometry.

    Rows are grouped by mutual vertical overlap of at least half the SHORTER
    cell's height -- the same mutual-overlap idea `_tokens_in_reading_order`
    already uses for text lines, rather than a pixel tolerance that would
    need tuning per DPI. Bands are then ordered by their top edge, min(y0),
    and cells within a band by x0. Deterministic: ties fall back to x0 then
    the input index, so the output is a pure function of the input.
    """
    idx = list(range(len(cells)))
    idx.sort(key=lambda i: (cells[i]["bbox"]["y0"], cells[i]["bbox"]["x0"], i))
    bands: list[list[int]] = []
    for i in idx:
        b = cells[i]["bbox"]
        placed = False
        for band in bands:
            ref = cells[band[0]]["bbox"]
            lo, hi = max(b["y0"], ref["y0"]), min(b["y1"], ref["y1"])
            overlap = max(0.0, hi - lo)
            shorter = min(b["y1"] - b["y0"], ref["y1"] - ref["y0"])
            if shorter > 0 and overlap / shorter >= 0.5:
                band.append(i)
                placed = True
                break
        if not placed:
            bands.append([i])
    bands.sort(key=lambda band: (min(cells[i]["bbox"]["y0"] for i in band),
                                 min(cells[i]["bbox"]["x0"] for i in band)))
    out = {}
    for r, band in enumerate(bands):
        for c, i in enumerate(sorted(band, key=lambda i: (cells[i]["bbox"]["x0"], i))):
            out[i] = (r, c)
    return out


CASES = []


def case(name, cells, expected, note=""):
    CASES.append({"name": name, "cells": cells, "expected": expected, "note": note})


# 1 two rows, slightly different cell heights
case("1_two_rows_slightly_different_heights",
     [cell(0, 0, 0, 100, 100, 130), cell(0, 1, 110, 100, 210, 128),
      cell(1, 0, 0, 140, 100, 172), cell(1, 1, 110, 141, 210, 170)],
     {0: (0, 0), 1: (0, 1), 2: (1, 0), 3: (1, 1)})

# 2 uneven vertical offsets within the same row
case("2_uneven_offsets_same_row",
     [cell(0, 0, 0, 100, 100, 130), cell(0, 1, 110, 104, 210, 134),
      cell(0, 2, 220, 97, 320, 127)],
     {0: (0, 0), 1: (0, 1), 2: (0, 2)})

# 3 different row heights
case("3_different_row_heights",
     [cell(0, 0, 0, 100, 100, 120), cell(0, 1, 110, 100, 210, 120),
      cell(1, 0, 0, 130, 100, 200), cell(1, 1, 110, 130, 210, 200)],
     {0: (0, 0), 1: (0, 1), 2: (1, 0), 3: (1, 1)})

# 4 borderless table (identical geometry, no rules drawn -- geometry is all we have)
case("4_borderless",
     [cell(0, 0, 10, 50, 200, 80), cell(0, 1, 210, 50, 400, 80),
      cell(1, 0, 10, 90, 200, 120), cell(1, 1, 210, 90, 400, 120)],
     {0: (0, 0), 1: (0, 1), 2: (1, 0), 3: (1, 1)})

# 5 tiny cells
case("5_tiny_cells",
     [cell(0, 0, 0, 10, 8, 16), cell(0, 1, 9, 10, 17, 16),
      cell(1, 0, 0, 18, 8, 24), cell(1, 1, 9, 18, 17, 24)],
     {0: (0, 0), 1: (0, 1), 2: (1, 0), 3: (1, 1)})

# 6 a tall header-like cell beside short ones -- the hc_tiny_cells_vi shape
case("6_tall_row_beside_short_rows",
     [cell(0, 0, 0, 524, 100, 554), cell(1, 0, 0, 551, 100, 571),
      cell(2, 0, 0, 555, 100, 625), cell(3, 0, 0, 572, 100, 591)],
     None, note="the real hc_tiny_cells_vi geometry; rows overlap heavily")

# 7 touching edges
case("7_touching_edges",
     [cell(0, 0, 0, 100, 100, 130), cell(0, 1, 100, 100, 200, 130),
      cell(1, 0, 0, 130, 100, 160), cell(1, 1, 100, 130, 200, 160)],
     {0: (0, 0), 1: (0, 1), 2: (1, 0), 3: (1, 1)})

# 8 slight overlap between consecutive rows
case("8_slight_row_overlap",
     [cell(0, 0, 0, 100, 100, 132), cell(0, 1, 110, 100, 210, 132),
      cell(1, 0, 0, 128, 100, 160), cell(1, 1, 110, 128, 210, 160)],
     {0: (0, 0), 1: (0, 1), 2: (1, 0), 3: (1, 1)})

# 9 empty cells (text absent, geometry present)
case("9_empty_cells",
     [cell(0, 0, 0, 100, 100, 130, ""), cell(0, 1, 110, 100, 210, 130, ""),
      cell(1, 0, 0, 140, 100, 170, "x"), cell(1, 1, 110, 140, 210, 170, "")],
     {0: (0, 0), 1: (0, 1), 2: (1, 0), 3: (1, 1)})

# 10 one-column table
case("10_one_column",
     [cell(0, 0, 0, 100, 100, 130), cell(1, 0, 0, 140, 100, 170),
      cell(2, 0, 0, 180, 100, 210)],
     {0: (0, 0), 1: (1, 0), 2: (2, 0)})

# 11 multi-column, many rows
case("11_multi_column",
     [cell(r, c, c * 100, 100 + r * 40, c * 100 + 90, 130 + r * 40)
      for r in range(4) for c in range(4)],
     {i: (i // 4, i % 4) for i in range(16)})

# 12 irregular geometry: ragged right edge, varying widths
case("12_irregular_widths",
     [cell(0, 0, 0, 100, 60, 130), cell(0, 1, 70, 100, 300, 130),
      cell(1, 0, 0, 140, 120, 170), cell(1, 1, 130, 140, 300, 170)],
     {0: (0, 0), 1: (0, 1), 2: (1, 0), 3: (1, 1)})


def main() -> int:
    results, limitations = [], []
    for c in CASES:
        got = assign(c["cells"])
        got_map = {i: got[i] for i in range(len(c["cells"]))}
        declared = {i: (cl["row"], cl["col"]) for i, cl in enumerate(c["cells"])}
        if c["expected"] is None:
            ok = None
            limitations.append({
                "case": c["name"], "note": c["note"],
                "recovered": {str(k): v for k, v in got_map.items()},
                "declared_in_ir": {str(k): v for k, v in declared.items()},
                "agrees_with_ir": got_map == declared,
            })
        else:
            ok = got_map == c["expected"]
        # RULE-B invariant: sorting by (row,col) never changes the text multiset
        texts_before = sorted(x["text"] for x in c["cells"])
        srt = sorted(c["cells"], key=lambda x: (x["row"], x["col"]))
        texts_after = sorted(x["text"] for x in srt)
        results.append({
            "case": c["name"],
            "cells": len(c["cells"]),
            "rule_A_recovers_expected": ok,
            "recovered": {str(k): v for k, v in got_map.items()},
            "expected": ({str(k): v for k, v in c["expected"].items()}
                         if c["expected"] else None),
            "rule_B_text_multiset_preserved": texts_before == texts_after,
            "deterministic": assign(c["cells"]) == got,
        })

    passed = [r for r in results if r["rule_A_recovers_expected"] is True]
    failed = [r for r in results if r["rule_A_recovers_expected"] is False]
    payload = {
        "rule_A": "group by mutual vertical overlap >= 0.5 of the shorter cell height; "
                  "order bands by min(y0); order within band by x0; ties by input index",
        "rule_B": "sort cells list by (row, col)",
        "anchor_note": "y-centre anchoring was falsified on the real corpus "
                       "(hc_tiny_cells_vi); min(y0) is used instead",
        "cases": len(results), "passed": len(passed), "failed": len(failed),
        "limitations": limitations,
        "results": results,
    }
    (HERE / "adversarial.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False))

    for r in results:
        mark = {True: "PASS", False: "FAIL", None: "LIMIT"}[r["rule_A_recovers_expected"]]
        print(f"  {mark}  {r['case']:<42} cells={r['cells']:<3} "
              f"multiset_preserved={r['rule_B_text_multiset_preserved']} "
              f"deterministic={r['deterministic']}")
    print(f"\nRULE-A: {len(passed)} passed, {len(failed)} failed, {len(limitations)} limitation(s)")
    for l in limitations:
        print(f"\n  LIMITATION {l['case']}: {l['note']}")
        print(f"    recovered   : {l['recovered']}")
        print(f"    declared IR : {l['declared_in_ir']}")
        print(f"    agrees      : {l['agrees_with_ir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
