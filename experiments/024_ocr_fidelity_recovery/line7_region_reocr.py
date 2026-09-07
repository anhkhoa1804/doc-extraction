"""LINE 7 -- can a cheap targeted second pass recover what the normal pass misses?

Reached only because lines 1-5 left the tiny-glyph acquisition failures
unsolved: line 2 gained nothing, line 3 showed whole-page rescaling is
actively harmful, and lines 4-5 together still fall short of the frozen
acceptance threshold.

Line 3 established the mechanism. The 4.2 pt cell text *is* readable by
Tesseract -- a crop of one table column at 600 DPI with `--psm 6` reads it
perfectly -- but the same pixels inside a full-page or full-table crop read
as noise, because one "line" spanning several columns of very small type
defeats segmentation. So the second pass must be per column, not per page
and not per table.

The trigger has to be computable at runtime with no ground truth. This uses
the one the pipeline already has: a detected table whose cells come back
mostly empty after normal assembly is a table whose text was not read. Only
those tables are re-OCR'd, one invocation per detected column, and the
invocation count is reported because the contract caps it at 1.10 per
document -- roughly four extra calls across the whole 49-document corpus.

Geometry comes only from what production detects (Table Transformer cells),
never from the ground truth, so the measured gain is the gain production
could actually obtain. Line 3 showed the detected row extent is truncated
(experiment 017's structure-recall gap), which is expected to cap recovery
below what an oracle crop achieves -- that gap is the point of measuring.

CPU only.
"""
from __future__ import annotations

import csv
import io
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

import pymupdf

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "research/production_corpus"))

from doc_extraction.backends.tesseract_backend import to_tesseract_langs  # noqa: E402
from run_benchmark import _norm  # noqa: E402

CORPUS = REPO / "research/production_corpus/corpus"
RUNS = REPO / "experiments/023_evidence_centric/_runs/visual/tesseract"
SCRATCH = Path("/tmp/claude-1002/-home-leanhkhoa150204/"
               "c332e03d-3ca4-4cd3-a188-684628b67cdf/scratchpad/024_line7")
LANGS = to_tesseract_langs(["en", "vi"])
RENDER_DPI = 200          # the pipeline's own render, whose pixel space the bboxes live in
REOCR_DPI = 600           # line 3's measured sweet spot for 4.2 pt type
REOCR_PSM = 6
EMPTY_CELL_TRIGGER = 0.5  # re-OCR a table when this fraction of its cells is empty
FAILURE_CORPUS = {
    "hc_rotation_vi", "hc_tiny_cells_vi", "cmb_scan_multicol_en",
    "cmb_scan_tiny_vi", "cmb_tiny_table_en", "cmb_scan_stamp_table_vi",
    "cmb_stamp_table_vi",
}


def ocr(image: Path) -> tuple[str, float]:
    t0 = time.perf_counter()
    proc = subprocess.run(["tesseract", str(image), "stdout", "-l", LANGS,
                           "--psm", str(REOCR_PSM), "tsv"],
                          capture_output=True, text=True)
    words = []
    for row in csv.DictReader(io.StringIO(proc.stdout), delimiter="\t",
                              quoting=csv.QUOTE_NONE):
        if (row.get("level") or "").strip() != "5":
            continue
        text = (row.get("text") or "").strip()
        try:
            if text and float(row["conf"]) >= 0:
                words.append(text)
        except (KeyError, TypeError, ValueError):
            continue
    return _norm(" ".join(words)), time.perf_counter() - t0


def final_text(doc_dir: Path) -> str:
    parts: list[str] = []

    def walk(node) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                if k == "text" and isinstance(v, str):
                    parts.append(v)
                else:
                    walk(v)
        elif isinstance(node, list):
            for x in node:
                walk(x)

    walk(json.loads((doc_dir / "final" / "document.json").read_text()))
    return _norm(" ".join(parts))


def columns_of(table: dict) -> list[tuple[float, float]]:
    """Distinct column x-ranges from the detected cells, merged on overlap."""
    spans = sorted({(c["bbox"]["x0"], c["bbox"]["x1"])
                    for c in table.get("cells", []) if c.get("bbox")})
    merged: list[list[float]] = []
    for x0, x1 in spans:
        if merged and x0 <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], x1)
        else:
            merged.append([x0, x1])
    return [(a, b) for a, b in merged]


def main() -> int:
    SCRATCH.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((CORPUS / "manifest.json").read_text())
    by_id = {d["document_id"]: d for d in manifest["documents_list"]}
    dirs = {p.name.rsplit("-", 1)[0]: p.name for p in RUNS.iterdir() if p.is_dir()}

    base_fc, base_ct, new_fc, new_ct = [], [], [], []
    extra_calls = 0
    secs = 0.0
    rows, gained, lost = [], [], []

    for doc_id, dir_name in sorted(dirs.items()):
        d = RUNS / dir_name
        req = by_id[doc_id]["must_contain"]
        base = final_text(d)
        triggered, recovered_parts, calls = [], [], 0

        pdf = pymupdf.open(CORPUS / by_id[doc_id]["filename"])
        for tbl_page in sorted((d / "tables").glob("page-*.json")):
            page_no = int(tbl_page.stem.split("-")[1]) - 1
            if page_no >= len(pdf):
                continue
            page = pdf[page_no]
            sx, sy = page.rect.x1 / 1653.0, page.rect.y1 / 2339.0
            for ti, table in enumerate(json.loads(tbl_page.read_text()).get("tables", [])):
                cells = table.get("cells") or []
                if not cells:
                    continue
                empty = sum(1 for c in cells if not (c.get("text") or "").strip())
                if empty / len(cells) < EMPTY_CELL_TRIGGER:
                    continue
                triggered.append(f"p{page_no}t{ti}")
                ys = [c["bbox"]["y0"] for c in cells if c.get("bbox")]
                ye = [c["bbox"]["y1"] for c in cells if c.get("bbox")]
                y0, y1 = min(ys) * sy, max(ye) * sy
                for ci, (cx0, cx1) in enumerate(columns_of(table)):
                    clip = pymupdf.Rect(max(0, cx0 * sx - 4), max(0, y0 - 4),
                                        min(page.rect.x1, cx1 * sx + 4),
                                        min(page.rect.y1, y1 + 4))
                    if clip.width <= 1 or clip.height <= 1:
                        continue
                    img = SCRATCH / f"{doc_id}-p{page_no}-t{ti}-c{ci}.png"
                    if not img.exists():
                        page.get_pixmap(dpi=REOCR_DPI, clip=clip).save(img)
                    text, dt = ocr(img)
                    calls += 1
                    secs += dt
                    recovered_parts.append(text)

        extra_calls += calls
        aug = _norm(base + " " + " ".join(recovered_parts)) if recovered_parts else base
        b = [s for s in req if _norm(s) in base]
        n = [s for s in req if _norm(s) in aug]
        (base_fc if doc_id in FAILURE_CORPUS else base_ct).append(len(b) / len(req))
        (new_fc if doc_id in FAILURE_CORPUS else new_ct).append(len(n) / len(req))
        for s in set(n) - set(b):
            gained.append({"document_id": doc_id, "string": s})
        for s in set(b) - set(n):
            lost.append({"document_id": doc_id, "string": s})
        if calls or triggered:
            rows.append({"document_id": doc_id, "in_failure_corpus": doc_id in FAILURE_CORPUS,
                         "triggered_tables": triggered, "extra_ocr_calls": calls,
                         "base_found": len(b), "new_found": len(n), "required": len(req)})

    n_docs = len(dirs)
    out = {
        "line": 7, "question": "can a cheap targeted second pass recover what the normal pass misses?",
        "trigger": f"detected table with >={EMPTY_CELL_TRIGGER:.0%} empty cells after normal assembly",
        "second_pass": f"one OCR call per detected column, {REOCR_DPI} DPI, psm {REOCR_PSM}",
        "note": "proxy: recovered text is appended to the document, not routed into cells",
        "failure_corpus_recall": {"base": round(statistics.mean(base_fc), 4),
                                  "after": round(statistics.mean(new_fc), 4)},
        "control_recall": {"base": round(statistics.mean(base_ct), 4),
                           "after": round(statistics.mean(new_ct), 4)},
        "cost": {"documents": n_docs, "extra_ocr_calls": extra_calls,
                 "invocations_per_document": round((n_docs + extra_calls) / n_docs, 4),
                 "reocr_seconds": round(secs, 1)},
        "gained": gained, "lost": lost, "rows": rows,
    }
    (HERE / "line7_region_reocr.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))

    print(f"failure corpus : {out['failure_corpus_recall']['base']:.4f} -> {out['failure_corpus_recall']['after']:.4f}")
    print(f"control        : {out['control_recall']['base']:.4f} -> {out['control_recall']['after']:.4f}")
    c = out["cost"]
    print(f"cost           : +{c['extra_ocr_calls']} OCR calls over {c['documents']} docs "
          f"= {c['invocations_per_document']:.4f} invocations/document  ({c['reocr_seconds']}s)")
    print(f"\ngained {len(gained)}: {[(g['document_id'], g['string'][:30]) for g in gained]}")
    print(f"lost   {len(lost)}: {[(l['document_id'], l['string'][:30]) for l in lost]}")
    print("\ntriggered documents:")
    for r in rows:
        flag = "FC" if r["in_failure_corpus"] else "  "
        print(f"  {flag} {r['document_id']:28s} calls={r['extra_ocr_calls']} "
              f"found {r['base_found']}->{r['new_found']}/{r['required']}  {r['triggered_tables']}")
    print("\nwrote line7_region_reocr.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
