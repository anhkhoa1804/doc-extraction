"""LINE 4 -- does `--psm 1` (auto segmentation with OSD) pay for itself corpus-wide?

`hc_rotation_vi` is the failure corpus's worst document (0/3) and its
mechanism is orientation: Tesseract's own OSD reports `Rotate: 90`. Switching
the page segmentation mode from 3 (auto, no OSD) to 1 (auto, with OSD)
acquires 2 of its 3 strings for no extra OCR call -- it is the same
invocation with a different flag, which is the cheapest possible shape for an
intervention.

But `psm` is a backend-wide setting, so the question is not whether it helps
one document. It is whether it helps that document without costing the other
48. This screens both halves of the frozen split at the recogniser level
before anything is run end to end.

Raw-recogniser acquisition is not the contract's metric -- exact recall
through the full pipeline is -- so this is a screen, not a result. It exists
to decide whether an end-to-end run is worth its 3 minutes.

CPU only, renders at the pipeline's own 200 DPI.
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
SCRATCH = Path("/tmp/claude-1002/-home-leanhkhoa150204/"
               "c332e03d-3ca4-4cd3-a188-684628b67cdf/scratchpad/024_psm")
LANGS = to_tesseract_langs(["en", "vi"])
DPI = 200
FAILURE_CORPUS = {
    "hc_rotation_vi", "hc_tiny_cells_vi", "cmb_scan_multicol_en",
    "cmb_scan_tiny_vi", "cmb_tiny_table_en", "cmb_scan_stamp_table_vi",
    "cmb_stamp_table_vi",
}


def ocr(image: Path, psm: int) -> tuple[str, float]:
    t0 = time.perf_counter()
    proc = subprocess.run(["tesseract", str(image), "stdout", "-l", LANGS,
                           "--psm", str(psm), "tsv"], capture_output=True, text=True)
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
    docs = [d for d in manifest["documents_list"]
            if d["must_contain"] and (CORPUS / d["filename"]).exists()
            and d["filename"].lower().endswith(".pdf")]

    per_psm: dict[int, dict] = {}
    rows = []
    for psm in (3, 1):
        fc, ctl, secs = [], [], 0.0
        for entry in docs:
            doc_id = entry["document_id"]
            pdf = pymupdf.open(CORPUS / entry["filename"])
            parts = []
            for i, page in enumerate(pdf):
                img = SCRATCH / f"{doc_id}-{i}.png"
                if not img.exists():
                    page.get_pixmap(dpi=DPI).save(img)
                text, dt = ocr(img, psm)
                parts.append(text)
                secs += dt
            text = _norm(" ".join(parts))
            req = entry["must_contain"]
            found = [s for s in req if _norm(s) in text]
            rate = len(found) / len(req)
            (fc if doc_id in FAILURE_CORPUS else ctl).append(rate)
            rows.append({"psm": psm, "document_id": doc_id,
                         "in_failure_corpus": doc_id in FAILURE_CORPUS,
                         "acquired": len(found), "required": len(req),
                         "found": found})
        per_psm[psm] = {"failure_corpus_acquisition": round(statistics.mean(fc), 4),
                        "control_acquisition": round(statistics.mean(ctl), 4),
                        "ocr_seconds": round(secs, 1),
                        "n_failure": len(fc), "n_control": len(ctl)}

    by_doc = {}
    for r in rows:
        by_doc.setdefault(r["document_id"], {})[r["psm"]] = r
    deltas = [{"document_id": d, "in_failure_corpus": v[3]["in_failure_corpus"],
               "psm3": v[3]["acquired"], "psm1": v[1]["acquired"],
               "required": v[3]["required"],
               "gained": sorted(set(v[1]["found"]) - set(v[3]["found"])),
               "lost": sorted(set(v[3]["found"]) - set(v[1]["found"]))}
              for d, v in by_doc.items() if v[3]["acquired"] != v[1]["acquired"]]

    out = {"line": 4, "question": "does --psm 1 pay for itself corpus-wide?",
           "note": "raw-recogniser screen at 200 DPI; not the contract metric",
           "langs": LANGS, "dpi": DPI, "psm": per_psm, "changed_documents": deltas,
           "rows": rows}
    (HERE / "line4_psm_screen.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))

    print(f"{'psm':>4s} {'failure_acq':>12s} {'control_acq':>12s} {'ocr_s':>8s}")
    for psm, r in per_psm.items():
        print(f"{psm:>4d} {r['failure_corpus_acquisition']:>12.4f} "
              f"{r['control_acquisition']:>12.4f} {r['ocr_seconds']:>8.1f}")
    print(f"\ndocuments whose acquisition changed: {len(deltas)}")
    for d in sorted(deltas, key=lambda x: x["psm1"] - x["psm3"]):
        flag = "FC" if d["in_failure_corpus"] else "  "
        print(f"  {flag} {d['document_id']:28s} {d['psm3']}->{d['psm1']} /{d['required']}"
              f"  gained={d['gained']} lost={d['lost']}")
    print("\nwrote line4_psm_screen.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
