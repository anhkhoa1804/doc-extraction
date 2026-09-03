#!/usr/bin/env python
"""Cell-level before/after scoring for ord_invoice_png_vi's product table --
the one real document this milestone's fix changed. Uses the repo's own
`table_metrics.score_table` (built in the earlier ownership-fix milestone)
so structure and content are scored separately, per that module's own
stated reason for existing: a document-level `must_contain` recall number
cannot see this table's improvement, because the specific probe phrase for
the recovered row ('Dịch vụ lắp đặt') collides with a separate, pre-existing
Docling OCR word-order defect on the exact same phrase (see
experiments/016_scan_failure_boundary/README.md) -- the geometry fix and
that defect are independent, and only cell-level scoring shows both facts
at once: structure fully recovered, content 15/16 cells exact (the 16th
blocked by the unrelated word-order bug, not by this fix).

Ground truth's row 3 ("Dịch vụ lắp đặt") is written in the TRUE word order,
not Docling's scrambled reading -- this is deliberate, to make that
residual gap visible in `mismatch_detail` rather than hidden by using the
same wrong string as both prediction and truth.

    python experiments/017_table_cell_geometry/score_ord_invoice.py \\
        --before /tmp/.../prod_before/adaptive/ord_invoice_png_vi-*/final/document.json \\
        --after  /tmp/.../prod_final/adaptive/ord_invoice_png_vi-*/final/document.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from doc_extraction.evaluation.table_metrics import TableGroundTruth, score_table  # noqa: E402
from doc_extraction.schemas.table import Table  # noqa: E402

TRUTH = TableGroundTruth(
    grid=[
        ["Mô tả hàng hóa", "Đơn vị", "", ""],
        ["Sản phẩm A-100", "Cái", "12", "18.000.000"],
        ["Bộ lọc khí Mã 22B", "Bộ", "4", "6.400.000"],
        ["Dịch vụ lắp đặt", "Gói", "1", "3.500.000"],
    ],
    label="ord_invoice_png_vi product table",
)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--before", required=True, type=Path)
    ap.add_argument("--after", required=True, type=Path)
    args = ap.parse_args()

    for label, path in [("BEFORE", args.before), ("AFTER", args.after)]:
        d = json.loads(path.read_text())
        table = Table.model_validate(d["pages"][0]["tables"][0])
        score = score_table(table, TRUTH)
        print(f"--- {label} ---")
        print(json.dumps(score.as_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
