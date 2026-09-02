"""Phases 32-33 — does the ownership fix survive randomization, or is it tuned
to one stamp coordinate?

The production corpus draws its seal at one position, in one size, over one
table geometry. A fix that only works there is not a fix, and the corpus
cannot tell the difference. This probe generates many variants of the same
*mechanism* and checks invariants rather than expected strings.

Randomized: table origin, column widths, row height, font size, number of
rows, stamp centre, stamp radius, and therefore the overlap ratio between the
seal and the grid. Text content is held fixed so ground truth stays exact.

Invariants asserted on every variant (these are the properties the fix claims,
stated so they can fail):

  I1  no cell holds a *fragment* of a source run  -- the interleaving bug
  I2  no source run's text appears in two cells   -- ownership means one owner
  I3  Vietnamese diacritics survive unchanged
  I4  structure is independent of the overlay     -- a seal must not change
                                                     the detected grid shape
  I5  a clean table is never flagged by the gate  -- false alarms kill a gate
  I6  a table with contaminated cells is always flagged
"""
from __future__ import annotations

import json
import random
import sys
import unicodedata
from pathlib import Path

import pymupdf

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "src"))

from doc_extraction.backends.pymupdf_table_backend import (  # noqa: E402
    convert_pymupdf_table,
    page_text_runs,
)
from doc_extraction.ingest.table_quality import assess_table  # noqa: E402

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
HEADERS = ["STT", "Mô tả hàng hóa", "Đơn vị", "Số lượng", "Thành tiền"]
ROWS = [
    ["1", "Sản phẩm A-100", "Cái", "12", "18.000.000"],
    ["2", "Bộ lọc khí Mã 22B", "Bộ", "4", "6.400.000"],
    ["3", "Dịch vụ lắp đặt", "Gói", "1", "3.500.000"],
    ["4", "Vật tư phụ trợ", "Thùng", "7", "9.750.000"],
    ["5", "Bảo trì định kỳ", "Lần", "2", "4.200.000"],
]
STAMP_LINES = ["CÔNG TY TNHH", "ĐÃ DUYỆT"]


def norm(s: str) -> str:
    return " ".join(unicodedata.normalize("NFC", s or "").split())


def build(path: Path, rng: random.Random, stamped: bool) -> dict:
    """Draw one randomized invoice table, optionally with a seal over it."""
    n_rows = rng.randint(3, 5)
    size = rng.choice([7.5, 8.0, 9.0, 10.0])
    rh = rng.choice([16.0, 18.0, 20.0, 24.0])
    widths = [rng.randint(22, 34), rng.randint(120, 175), rng.randint(40, 62),
              rng.randint(36, 58), rng.randint(80, 110)]
    x0 = rng.uniform(45, 90)
    y0 = rng.uniform(150, 300)

    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    total_w, n = sum(widths), n_rows + 1
    for i in range(n + 1):
        page.draw_line(pymupdf.Point(x0, y0 + i * rh),
                       pymupdf.Point(x0 + total_w, y0 + i * rh),
                       color=(0.3, 0.3, 0.3), width=0.5)
    cx = x0
    for w in widths + [0]:
        page.draw_line(pymupdf.Point(cx, y0), pymupdf.Point(cx, y0 + n * rh),
                       color=(0.3, 0.3, 0.3), width=0.5)
        cx += w

    grid = [list(HEADERS)] + [list(r) for r in ROWS[:n_rows]]
    for r, row in enumerate(grid):
        cx = x0
        for w, cell in zip(widths, row):
            page.insert_text(pymupdf.Point(cx + 2, y0 + r * rh + rh - size * 0.55),
                             cell, fontsize=size, fontfile=FONT, fontname="dv",
                             color=(0.15, 0.15, 0.15))
            cx += w

    stamp_at = None
    if stamped:
        # Anywhere over the grid, so overlap ratio varies across the sample.
        stamp_at = (rng.uniform(x0 + 20, x0 + total_w - 20),
                    rng.uniform(y0 + 10, y0 + n * rh - 10))
        radius = rng.uniform(28, 52)
        red = (0.75, 0.05, 0.10)
        c = pymupdf.Point(*stamp_at)
        page.draw_circle(c, radius, color=red, fill=(0.95, 0.80, 0.82), width=0)
        page.draw_circle(c, radius + 2, color=red, width=2.0)
        for k, line in enumerate(STAMP_LINES):
            page.insert_text(pymupdf.Point(c.x - radius * 0.75, c.y - 4 + k * 12),
                             line, fontsize=size * 0.85, fontfile=FONT,
                             fontname="dv", color=red)

    doc.save(path)
    doc.close()
    return {"grid": grid, "stamped": stamped, "stamp_at": stamp_at,
            "size": size, "rh": rh, "widths": widths, "n_rows": n_rows}


def check(path: Path, spec: dict) -> dict:
    doc = pymupdf.open(path)
    try:
        page = doc[0]
        found = page.find_tables()
        if not found.tables:
            return {"detected": False}
        t = max(found.tables, key=lambda x: x.row_count * x.col_count)
        runs = page_text_runs(page)
        table_runs = [dict(r) for r in runs]
        table = convert_pymupdf_table(t, 0, "p0-t0", runs=table_runs)
        considered = [r for r in table_runs if r.get("_cell") is not None]
        report = assess_table(table, considered)

        cells = {(c.row, c.col): norm(c.text) for c in table.cells}
        run_texts = [norm(r["text"]) for r in runs if r["text"].strip()]
        truth = {(r, c): norm(v) for r, row in enumerate(spec["grid"])
                 for c, v in enumerate(row)}
        stamp_tokens = {tok for line in STAMP_LINES for tok in norm(line).split()}
        vocab = {tok for v in truth.values() for tok in v.split()}

        # I1 — fragments
        frag = []
        for pos, text in cells.items():
            for tok in text.split():
                if len(tok) >= 2 and not any(tok in r for r in run_texts):
                    frag.append({"cell": f"r{pos[0]}c{pos[1]}", "text": text, "token": tok})
                    break
        # I2 — duplication of a substantial token across cells
        seen, dup = {}, []
        for pos, text in cells.items():
            for tok in set(text.split()):
                if len(tok) < 4 or tok in stamp_tokens:
                    continue
                if tok in seen:
                    dup.append({"token": tok, "cells": [seen[tok], f"r{pos[0]}c{pos[1]}"]})
                seen[tok] = f"r{pos[0]}c{pos[1]}"
        # I3 — diacritics: every expected diacritic-bearing value present somewhere
        joined = " ".join(cells.values())
        diacritic_lost = [v for v in truth.values()
                          if v and any(ord(ch) > 127 for ch in v) and v not in joined]
        # contamination = foreign token in a cell
        contaminated = [f"r{p[0]}c{p[1]}" for p, text in cells.items()
                        if any(tok not in vocab for tok in text.split())]

        return {
            "detected": True,
            "shape": [table.n_rows, table.n_cols],
            "fragments": frag,
            "duplicates": dup,
            "diacritic_lost": diacritic_lost,
            "contaminated": contaminated,
            "gate_trusted": report.trusted,
            "gate_severity": report.severity,
            "gate_signals": report.signals,
        }
    finally:
        doc.close()


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    tmp = Path("/tmp/claude-1002/-home-leanhkhoa150204/"
               "17350d12-6add-4719-8ecd-40b53c80d434/scratchpad/rand_tables")
    tmp.mkdir(parents=True, exist_ok=True)

    violations = {f"I{i}": [] for i in range(1, 7)}
    records, undetected = [], 0
    expected_shape_ok = 0

    for i in range(n):
        rng = random.Random(9000 + i)
        stamped = (i % 2 == 1)
        path = tmp / f"v{i:03d}.pdf"
        spec = build(path, rng, stamped)
        res = check(path, spec)
        res["variant"], res["stamped"] = i, stamped
        records.append(res)

        if not res["detected"]:
            undetected += 1
            continue
        if res["shape"] == [spec["n_rows"] + 1, 5]:
            expected_shape_ok += 1
        else:
            violations["I4"].append({"variant": i, "stamped": stamped,
                                     "shape": res["shape"],
                                     "expected": [spec["n_rows"] + 1, 5]})
        if res["fragments"]:
            violations["I1"].append({"variant": i, "detail": res["fragments"][:3]})
        if res["duplicates"]:
            violations["I2"].append({"variant": i, "detail": res["duplicates"][:3]})
        if res["diacritic_lost"]:
            violations["I3"].append({"variant": i, "lost": res["diacritic_lost"]})
        if not res["contaminated"] and not res["gate_trusted"]:
            violations["I5"].append({"variant": i, "stamped": stamped,
                                     "signals": res["gate_signals"]})
        if res["contaminated"] and res["gate_trusted"]:
            violations["I6"].append({"variant": i, "cells": res["contaminated"]})

    detected = [r for r in records if r["detected"]]
    contaminated = [r for r in detected if r["contaminated"]]
    flagged = [r for r in detected if not r["gate_trusted"]]
    tp = len([r for r in flagged if r["contaminated"]])
    fp = len(flagged) - tp
    fn = len([r for r in detected if r["gate_trusted"] and r["contaminated"]])

    print(f"variants: {n}   detected: {len(detected)}   undetected: {undetected}")
    print(f"structure recovered exactly: {expected_shape_ok}/{len(detected)}")
    print(f"contaminated (ground truth): {len(contaminated)}   flagged by gate: {len(flagged)}")
    print(f"gate  TP={tp}  FP={fp}  FN={fn}"
          f"  precision={tp/len(flagged) if flagged else float('nan'):.3f}"
          f"  recall={tp/(tp+fn) if (tp+fn) else float('nan'):.3f}")
    print("\ninvariant violations:")
    names = {
        "I1": "cell holds a fragment of a source run",
        "I2": "a run's text appears in two cells",
        "I3": "Vietnamese diacritics lost",
        "I4": "structure changed / wrong shape",
        "I5": "clean table falsely flagged",
        "I6": "contaminated table not flagged",
    }
    for k in sorted(violations):
        v = violations[k]
        status = "PASS" if not v else f"FAIL ({len(v)})"
        print(f"  {k}  {names[k]:<44} {status}")
        for item in v[:3]:
            print(f"        {json.dumps(item, ensure_ascii=False)[:150]}")

    out = Path(__file__).parent / "phase33_randomized.json"
    out.write_text(json.dumps(
        {"n": n, "undetected": undetected,
         "structure_exact": expected_shape_ok,
         "gate": {"tp": tp, "fp": fp, "fn": fn,
                  "contaminated": len(contaminated), "flagged": len(flagged)},
         "violations": violations, "records": records},
        ensure_ascii=False, indent=2))
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
