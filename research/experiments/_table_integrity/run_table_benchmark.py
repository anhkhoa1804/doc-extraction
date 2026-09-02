"""Phases 4 + 9 — validate the ownership fix and measure the gate, corpus-wide.

Runs every ruled-table document in the production corpus through both cell-text
strategies that live side by side in `convert_pymupdf_table`:

    runs=None   ->  PyMuPDF `extract()`      (shipped HEAD)
    runs=[...]  ->  run-ownership assignment (the uncommitted fix)

and scores both with `evaluation/table_metrics`, which separates structure from
content. Ground truth comes from the generator's own constants, so it is exact
rather than annotated.

The gate is scored against measured corruption rather than against intent: a
flag on a table that really is corrupt is a true positive, a flag on a clean
one is a false alarm. A gate is only useful if that ratio is good, and nothing
in the repository has measured it until now.
"""
from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from pathlib import Path

import pymupdf

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO))

from doc_extraction.backends.pymupdf_table_backend import (  # noqa: E402
    convert_pymupdf_table,
    page_text_runs,
)
from doc_extraction.evaluation.table_metrics import (  # noqa: E402
    CorpusTableReport,
    TableGroundTruth,
    score_table,
)
from doc_extraction.ingest.table_quality import assess_table  # noqa: E402

CORPUS = REPO / "research/production_corpus/corpus"

HEADERS_VI = ["STT", "Mô tả hàng hóa", "Đơn vị", "Số lượng", "Thành tiền"]
HEADERS_EN = ["No.", "Item description", "Unit", "Qty", "Amount"]
ROWS_VI = [
    ["1", "Sản phẩm A-100", "Cái", "12", "18.000.000"],
    ["2", "Bộ lọc khí Mã 22B", "Bộ", "4", "6.400.000"],
    ["3", "Dịch vụ lắp đặt", "Gói", "1", "3.500.000"],
]
ROWS_EN = [
    ["1", "Product A-100", "pcs", "12", "18,000.00"],
    ["2", "Air filter type 22B", "set", "4", "6,400.00"],
    ["3", "Installation service", "job", "1", "3,500.00"],
]

# Every born-digital corpus document that draws a table, with the generator
# options that determine its expected grid. Scanned documents are excluded:
# they have no text layer, so the native table path is not the system under
# test here.
DOCS: dict[str, dict] = {
    # ordinary, ruled — the controls that must not regress
    "ord_invoice_vi":            dict(lang="vi", style="ruled", stamp=None),
    "ord_invoice_en":            dict(lang="en", style="ruled", stamp=None),
    "ord_purchase_order_en":     dict(lang="en", style="ruled", stamp=None),
    "ord_purchase_order_vi":     dict(lang="vi", style="ruled", stamp=None),
    "ord_financial_report_en":   dict(lang="en", style="ruled", stamp=None),
    "ord_financial_report_vi":   dict(lang="vi", style="ruled", stamp=None),
    # single-mechanism hard cases
    "hc_stamp_table_vi":         dict(lang="vi", style="ruled",      stamp="table"),
    "hc_merged_en":              dict(lang="en", style="merged",     stamp=None),
    "hc_borderless_en":          dict(lang="en", style="borderless", stamp=None),
    "hc_tiny_cells_vi":          dict(lang="vi", style="tiny",       stamp=None),
    # combination cases
    "cmb_stamp_table_vi":        dict(lang="vi", style="merged", stamp="table"),
    "cmb_stamp_boundary_vi":     dict(lang="vi", style="ruled",  stamp="boundary"),
    "cmb_tiny_table_en":         dict(lang="en", style="tiny",   stamp=None),
    "cmb_multicol_table_en":     dict(lang="en", style="ruled",  stamp=None),
    "cmb_borderless_lowcontrast_en": dict(lang="en", style="borderless", stamp=None),
}


def ground_truth(lang: str, style: str) -> TableGroundTruth:
    """Rebuild the expected grid exactly as `generate.py::_draw_table` draws it."""
    headers = HEADERS_VI if lang == "vi" else HEADERS_EN
    rows = ROWS_VI if lang == "vi" else ROWS_EN
    grid = [list(headers)]
    spans: dict[tuple[int, int], tuple[int, int]] = {}
    for r, row in enumerate(rows, start=1):
        if style == "merged" and r == 1:
            merged = "Số lượng / Thành tiền" if lang == "vi" else "Qty / Amount"
            grid.append([row[0], row[1], row[2], merged, ""])
            spans[(1, 3)] = (1, 2)
        else:
            grid.append(list(row))
    return TableGroundTruth(grid=grid, spans=spans, label=f"{lang}/{style}")


def norm(s: str) -> str:
    return " ".join(unicodedata.normalize("NFC", s).split())


def run_document(name: str, opts: dict) -> dict | None:
    path = CORPUS / f"{name}.pdf"
    if not path.exists():
        return None
    truth = ground_truth(opts["lang"], opts["style"])
    doc = pymupdf.open(path)
    try:
        page = doc[0]
        runs = page_text_runs(page)
        source_runs = [s["text"] for s in runs if s.get("text", "").strip()]
        found = page.find_tables()
        if not found.tables:
            return {"document": name, "options": opts, "tables_found": 0,
                    "note": "no table detected by the native finder"}

        # Score the largest detected table: the corpus draws exactly one, and a
        # spurious extra detection should not be matched against its truth.
        best = max(found.tables, key=lambda t: t.row_count * t.col_count)
        tid = f"p0-t0"

        old = convert_pymupdf_table(best, 0, tid, runs=None)
        table_runs = [dict(r) for r in runs]
        new = convert_pymupdf_table(best, 0, tid, runs=table_runs)

        considered = [r for r in table_runs if r.get("_cell") is not None]
        report = assess_table(new, considered)

        s_old = score_table(old, truth, source_runs)
        s_new = score_table(new, truth, source_runs)
        s_new.gate_trusted = report.trusted
        s_new.gate_severity = report.severity
        s_new.gate_signals = list(report.signals)
        # The old path has no gate of its own; judged as "trusted" because
        # that is exactly what shipped HEAD does — it returns the table with
        # no verdict at all.
        s_old.gate_trusted = True
        s_old.gate_severity = "none"

        return {"document": name, "options": opts, "tables_found": len(found.tables),
                "old": s_old.as_dict(), "new": s_new.as_dict(),
                "_score_old": s_old, "_score_new": s_new}
    finally:
        doc.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", type=Path,
                    default=Path(__file__).parent / "table_benchmark.json")
    args = ap.parse_args()

    results, rep_old, rep_new = [], CorpusTableReport(), CorpusTableReport()
    for name, opts in DOCS.items():
        rec = run_document(name, opts)
        if rec is None:
            print(f"  {name}: MISSING")
            continue
        if rec.get("tables_found", 0) == 0:
            print(f"  {name}: no table detected ({opts['style']})")
            results.append(rec)
            continue
        rep_old.add(rec.pop("_score_old"))
        rep_new.add(rec.pop("_score_new"))
        results.append(rec)

    print(f"\n{'='*88}")
    print(f"{'document':<32} {'struct':>14}  {'content f1':>14}  {'contam':>10}  gate")
    print(f"{'':<32} {'old -> new':>14}  {'old -> new':>14}  {'old->new':>10}")
    print("=" * 88)
    for r in results:
        if "new" not in r:
            print(f"{r['document']:<32} {'— no table detected —':>44}")
            continue
        o, n = r["old"], r["new"]
        so = f"{o['structure']['position_recall']:.2f}->{n['structure']['position_recall']:.2f}"
        cf = f"{o['content']['cell_text_f1']:.3f}->{n['content']['cell_text_f1']:.3f}"
        ct = f"{o['content']['contaminated_cells']}->{n['content']['contaminated_cells']}"
        gate = "FLAG" if not n["gate_trusted"] else "ok"
        sev = n["gate_severity"]
        corrupt = "CORRUPT" if n["is_corrupt"] else "clean"
        print(f"{r['document']:<32} {so:>14}  {cf:>14}  {ct:>10}  {gate}/{sev} [{corrupt}]")

    print(f"\n{'='*88}\nOLD (shipped HEAD)\n{'='*88}")
    print(json.dumps(rep_old.summary(), indent=2, ensure_ascii=False))
    print(f"\n{'='*88}\nNEW (ownership fix + gate)\n{'='*88}")
    print(json.dumps(rep_new.summary(), indent=2, ensure_ascii=False))

    args.json.write_text(json.dumps(
        {"documents": results,
         "summary_old": rep_old.summary(),
         "summary_new": rep_new.summary()},
        indent=2, ensure_ascii=False))
    print(f"\nwrote {args.json}")


if __name__ == "__main__":
    main()
