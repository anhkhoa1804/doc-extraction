"""Does a genuinely independent recognizer read the tone marks EasyOCR loses?

Experiment 021 established two things: `cmb_scan_tiny_vi`'s 0.00 recall is
Vietnamese character-level corruption rather than a resolution limit, and
the project's two "independent" OCR backends share one recognizer
(`docling_backend.py:221` wires Docling's OCR to EasyOCR, so both resolve
`vi` through the same `latin_g2` weights).

That makes one question decisive, and falsifiable either way:

    is the diacritic information present in these pixels and missed by
    latin_g2, or absent from the render entirely?

Tesseract's LSTM engine with `vie` traineddata is the cheapest honest test
available -- a different model family, different training data, no shared
lineage with EasyOCR. If Tesseract reads the tone marks, the information is
on the page and the failure is a recognizer capability gap this project can
close by adding an evidence source. If Tesseract also fails, the
information is not recoverable at this DPI and the case is genuinely
closed, which is equally decisive.

Documents:
    cmb_scan_tiny_vi    experiment 021's misclassified 0.00-recall document
    ord_contract_vi     experiment 013 correlated error (0.782 / 0.782)
    hc_low_contrast_vi  experiment 013 correlated error (0.782 / 0.782)

The last two are the sharper test of non-independence: if Tesseract scores
differently from the identical EasyOCR/Docling pair, the pair's agreement
was measuring shared weights rather than corroboration.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "src"))
CORPUS = REPO / "research/production_corpus/corpus"

from diacritic_ladder import RUNGS, score

DOCS = ["cmb_scan_tiny_vi", "ord_contract_vi", "hc_low_contrast_vi"]


def manifest_entry(doc_id: str) -> dict:
    m = json.loads((CORPUS / "manifest.json").read_text())
    return next(d for d in m["documents_list"] if d["document_id"] == doc_id)


def render_all(doc_id: str, dpi: int, out: Path) -> list[Path]:
    """Render every page. Page-0-only would understate multi-page documents
    (the corpus averages 2.2 pages), and would do so for both engines, so it
    is fair but depressed -- not good enough for a corpus-level number."""
    import pymupdf

    from doc_extraction.stages.render import render_single_pdf_page
    with pymupdf.open(CORPUS / f"{doc_id}.pdf") as d:
        n = d.page_count
    return [render_single_pdf_page(CORPUS / f"{doc_id}.pdf", i, out, dpi)
            for i in range(n)]


def read_tesseract(imgs: list[Path], langs: str = "vie+eng") -> tuple[str, float]:
    t0 = time.time()
    parts = []
    for img in imgs:
        proc = subprocess.run(
            ["tesseract", str(img), "stdout", "-l", langs, "--psm", "3"],
            capture_output=True, text=True, check=True)
        parts.append(proc.stdout)
    return "\n".join(parts), round(time.time() - t0, 2)


def read_easyocr(imgs: list[Path], device: str, _cache={}) -> tuple[str, float]:
    import easyocr
    if "r" not in _cache:
        _cache["r"] = easyocr.Reader(["vi", "en"], gpu=(device == "cuda"),
                                     verbose=False)
    t0 = time.time()
    parts = [" ".join(d[1] for d in _cache["r"].readtext(str(img)))
             for img in imgs]
    return "\n".join(parts), round(time.time() - t0, 2)


def report(doc_id: str, engine: str, text: str, must: list[str],
           secs: float) -> dict:
    row = {"engine": engine, "seconds": secs, "chars": len(text),
           "text": text[:400]}
    for name, fn in RUNGS:
        ex, wr, hits = score(text, must, fn)
        row[name] = {"exact": round(ex, 4), "word": round(wr, 4)}
    raw, dia = row["raw"], row["+diacritics"]
    print(f"  {engine:<12} {secs:>6.2f}s  {len(text):>5}ch   "
          f"raw {raw['exact']:.3f}/{raw['word']:.3f}   "
          f"+dia {dia['exact']:.3f}/{dia['word']:.3f}")
    return row


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--dpi", type=int, default=200)
    ap.add_argument("--docs", nargs="*", default=DOCS)
    ap.add_argument("--json", type=Path,
                    default=Path(__file__).parent / "independent_recognizer.json")
    args = ap.parse_args()

    out = Path(tempfile.mkdtemp(prefix="indep_recog_"))
    results = {"device": args.device, "dpi": args.dpi,
               "tesseract_version": subprocess.run(
                   ["tesseract", "--version"], capture_output=True,
                   text=True).stdout.splitlines()[0],
               "documents": []}

    for doc_id in args.docs:
        entry = manifest_entry(doc_id)
        must = entry["must_contain"]
        if not must:
            continue
        if not (CORPUS / f"{doc_id}.pdf").exists():
            print(f"\n{doc_id}: not a PDF, skipped")
            continue
        imgs = render_all(doc_id, args.dpi, out)
        print(f"\n{doc_id}  ({entry['language']}, {entry['document_type']}, "
              f"difficulty={entry['difficulty']}, {len(imgs)}p)")
        print(f"  {'engine':<12} {'time':>6}  {'chars':>5}   "
              f"raw exact/word   +dia exact/word")
        rows = []
        for engine, fn in (("easyocr", lambda i: read_easyocr(i, args.device)),
                           ("tesseract", read_tesseract)):
            text, secs = fn(imgs)
            rows.append(report(doc_id, engine, text, must, secs))
        results["documents"].append(
            {"document_id": doc_id, "language": entry["language"],
             "difficulty": entry["difficulty"], "pages": len(imgs),
             "must_contain": must, "engines": rows})

    # corpus-level aggregate, per engine
    agg = {}
    for engine in ("easyocr", "tesseract"):
        rows = [next(r for r in d["engines"] if r["engine"] == engine)
                for d in results["documents"]]
        agg[engine] = {
            "n": len(rows),
            "mean_raw_exact": round(sum(r["raw"]["exact"] for r in rows) / len(rows), 4),
            "mean_raw_word": round(sum(r["raw"]["word"] for r in rows) / len(rows), 4),
            "mean_dia_exact": round(sum(r["+diacritics"]["exact"] for r in rows) / len(rows), 4),
            "total_seconds": round(sum(r["seconds"] for r in rows), 1),
            "docs_perfect_raw": sum(1 for r in rows if r["raw"]["exact"] == 1.0),
            "docs_zero_raw": sum(1 for r in rows if r["raw"]["exact"] == 0.0),
        }
    results["aggregate"] = agg
    print("\n=== corpus aggregate ===")
    for engine, a in agg.items():
        print(f"  {engine:<11} n={a['n']}  mean raw exact {a['mean_raw_exact']:.4f}  "
              f"word {a['mean_raw_word']:.4f}  perfect {a['docs_perfect_raw']}  "
              f"zero {a['docs_zero_raw']}  {a['total_seconds']}s")

    args.json.write_text(json.dumps(results, indent=1, ensure_ascii=False))
    print(f"\nwrote {args.json}")


if __name__ == "__main__":
    main()
