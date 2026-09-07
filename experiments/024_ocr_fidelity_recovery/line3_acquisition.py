"""LINE 3 -- can the tiny-glyph acquisition failures be acquired at all?

The failing cells are set in 4.2-4.5 pt type. At the pipeline's 200 DPI that
renders about 12 px tall, well under the ~30 px x-height Tesseract's LSTM
wants, so the indicated variable is effective scale rather than a
segmentation or preprocessing grid. Four configurations are probed, chosen
from that measurement rather than swept:

    A  200 DPI, psm 3   -- the shipped path, reproduced as the control
    B  400 DPI, psm 3   -- 2x
    C  600 DPI, psm 3   -- 3x, the scale the glyph size actually implies
    D  600 DPI, psm 6   -- 3x with a uniform-block assumption for the table

The question this answers is "did OCR acquire new evidence", not "did the
score move": success is the required string appearing in the recognizer's
own output. Anything that acquires evidence still has to survive the
control and the cost guardrail before it can be promoted.

Tesseract is invoked exactly as `TesseractBackend.recognize` invokes it
(same binary, same `vie+eng` ordering, same tsv output), so a difference
here is a difference the production path would also see.

Renders into a scratch directory outside the repository. CPU only.
"""
from __future__ import annotations

import csv
import io
import json
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
SCRATCH = Path("/tmp/claude-1002/-home-leanhkhoa150204/"
               "c332e03d-3ca4-4cd3-a188-684628b67cdf/scratchpad/024_line3")
LANGS = to_tesseract_langs(["en", "vi"])

# The small-text documents in the frozen failure corpus. hc_rotation_vi is
# excluded: its mechanism is orientation, which is line 4's subject.
DOCS = ["hc_tiny_cells_vi", "cmb_tiny_table_en", "cmb_stamp_table_vi",
        "cmb_scan_tiny_vi", "cmb_scan_stamp_table_vi"]
CONFIGS = [("A_200dpi_psm3", 200, 3), ("B_400dpi_psm3", 400, 3),
           ("C_600dpi_psm3", 600, 3), ("D_600dpi_psm6", 600, 6)]


def ocr(image: Path, psm: int) -> tuple[str, float]:
    t0 = time.perf_counter()
    proc = subprocess.run(["tesseract", str(image), "stdout", "-l", LANGS,
                           "--psm", str(psm), "tsv"],
                          capture_output=True, text=True, check=True)
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


def main() -> int:
    SCRATCH.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((CORPUS / "manifest.json").read_text())
    by_id = {d["document_id"]: d for d in manifest["documents_list"]}

    results, rows = {}, []
    for name, dpi, psm in CONFIGS:
        acquired_total = required_total = 0
        secs = 0.0
        for doc_id in DOCS:
            pdf = pymupdf.open(CORPUS / f"{doc_id}.pdf")
            text_parts = []
            for i, page in enumerate(pdf):
                img = SCRATCH / f"{doc_id}-{dpi}-{i}.png"
                if not img.exists():
                    page.get_pixmap(dpi=dpi).save(img)
                text, dt = ocr(img, psm)
                text_parts.append(text)
                secs += dt
            text = _norm(" ".join(text_parts))
            req = by_id[doc_id]["must_contain"]
            found = [s for s in req if _norm(s) in text]
            acquired_total += len(found)
            required_total += len(req)
            rows.append({"config": name, "dpi": dpi, "psm": psm,
                         "document_id": doc_id,
                         "acquired": len(found), "required": len(req),
                         "missing": [s for s in req if _norm(s) not in text]})
        results[name] = {"dpi": dpi, "psm": psm,
                         "strings_acquired": acquired_total,
                         "strings_required": required_total,
                         "acquisition_rate": round(acquired_total / required_total, 4),
                         "ocr_seconds": round(secs, 1)}

    out = {"line": 3, "question": "did OCR acquire new evidence at greater effective scale?",
           "note": "raw-recognizer probe on 5 small-text failure-corpus documents; "
                   "not an end-to-end pipeline run",
           "langs": LANGS, "documents": DOCS, "configs": results, "rows": rows}
    (HERE / "line3_acquisition.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))

    print(f"{'config':16s} {'acquired':>9s} {'rate':>7s} {'ocr_s':>8s}")
    for name, r in results.items():
        print(f"{name:16s} {r['strings_acquired']:>4d}/{r['strings_required']:<4d} "
              f"{r['acquisition_rate']:>7.4f} {r['ocr_seconds']:>8.1f}")
    print("\nper document (strings acquired):")
    print(f"{'document':26s} " + " ".join(f"{n.split('_')[0]:>6s}" for n, _, _ in CONFIGS))
    for doc_id in DOCS:
        cells = []
        for name, _, _ in CONFIGS:
            r = next(x for x in rows if x["config"] == name and x["document_id"] == doc_id)
            cells.append(f"{r['acquired']:>2d}/{r['required']:<3d}")
        print(f"{doc_id:26s} " + " ".join(f"{c:>6s}" for c in cells))
    print("\nwrote line3_acquisition.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
