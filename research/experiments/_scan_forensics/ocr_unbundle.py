"""Phase 13 conclusion — is the scan failure an OCR failure, or an integration
failure?

The forensics established that on `cmb_scan_stamp_table_vi` docling's layout
labels the stamped table a `picture`, and `DoclingBackend.recognize()` drops
any item without a `.text` attribute. The table's text is therefore never
emitted. Running EasyOCR — *the same recognizer docling itself wraps* —
directly on those same pixels returns every expected string at word recall
1.00.

So the question this settles is not "is EasyOCR better than docling". It is
whether the information the pipeline loses was ever unavailable. This runs
both paths over all six failing scanned documents and reports, per string,
which path holds it.

The second thing it measures is confidence. `DoclingBackend` emits
`OCRToken.confidence = None` for every token, because docling's stable public
API exposes text items rather than word-level OCR results. EasyOCR returns a
per-detection confidence. That is the cheapest quality-estimation signal
available to this project and it is currently discarded by the layer above it.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import unicodedata
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "src"))
CORPUS = REPO / "research/production_corpus/corpus"
SCRATCH = Path("/tmp/claude-1002/-home-leanhkhoa150204/"
               "17350d12-6add-4719-8ecd-40b53c80d434/scratchpad/unbundle")

DOCS = ["cmb_scan_tiny_vi", "hc_scan_vi", "cmb_scan_stamp_table_vi",
        "ord_invoice_png_vi", "cmb_scan_multicol_en", "hc_scan_en"]


def words(s: str) -> list[str]:
    s = unicodedata.normalize("NFC", s).lower()
    return [w for w in re.split(r"[^0-9a-zà-ỹăâđêôơư]+", s, flags=re.I) if w]


def norm(s: str) -> str:
    return " ".join(unicodedata.normalize("NFC", s or "").split()).lower()


def recall(text: str, must: list[str]) -> tuple[float, float, list[float]]:
    tw = set(words(text))
    ex = sum(1 for s in must if norm(s) in norm(text)) / len(must)
    per = []
    for s in must:
        sw = words(s)
        per.append(sum(1 for w in sw if w in tw) / len(sw) if sw else 0.0)
    return ex, sum(per) / len(per), per


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--dpi", type=int, default=200)
    ap.add_argument("--json", type=Path,
                    default=Path(__file__).parent / "ocr_unbundle.json")
    args = ap.parse_args()

    import easyocr
    import pymupdf

    from doc_extraction.backends.docling_backend import DoclingBackend
    from doc_extraction.pipelines.base import PageInput
    from doc_extraction.stages.render import (
        render_image_passthrough,
        render_single_pdf_page,
    )

    SCRATCH.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((CORPUS / "manifest.json").read_text())
    by_id = {d["document_id"]: d for d in manifest["documents_list"]}

    docling = DoclingBackend(device=args.device, ocr_languages=["en", "vi"])
    reader = easyocr.Reader(["vi", "en"], gpu=(args.device == "cuda"), verbose=False)

    rows, results = [], []
    for name in DOCS:
        meta = by_id[name]
        src = CORPUS / meta["filename"]
        must = meta["must_contain"]
        is_pdf = src.suffix.lower() == ".pdf"

        page_dir = SCRATCH / name
        if is_pdf:
            img = render_single_pdf_page(src, 0, page_dir, dpi=args.dpi)
            d = pymupdf.open(src)
            pw, ph = d[0].rect.width, d[0].rect.height
            d.close()
        else:
            img = render_image_passthrough(src, page_dir)
            from PIL import Image
            with Image.open(img) as im:
                pw, ph = float(im.size[0]), float(im.size[1])

        # --- path A: the shipped docling component path -------------------
        pi = PageInput(page_index=0, width=pw, height=ph, image_path=img,
                       dpi=args.dpi, source_pdf_path=src if is_pdf else None)
        t0 = time.perf_counter()
        layout = docling.analyze(pi)
        ocr_d = docling.recognize(pi)
        t_docling = time.perf_counter() - t0
        text_d = " ".join(t.text for t in ocr_d.tokens)
        conf_d = [t.confidence for t in ocr_d.tokens if t.confidence is not None]

        # --- path B: EasyOCR directly on the same pixels ------------------
        t0 = time.perf_counter()
        det = reader.readtext(str(img), detail=1)
        t_easy = time.perf_counter() - t0
        text_e = " ".join(d[1] for d in det)
        conf_e = [float(d[2]) for d in det]

        ex_d, wr_d, per_d = recall(text_d, must)
        ex_e, wr_e, per_e = recall(text_e, must)
        # Union: what the pipeline could have if it kept both.
        ex_u, wr_u, _ = recall(text_d + " " + text_e, must)

        rows.append((name, len(must), ex_d, wr_d, ex_e, wr_e, ex_u, wr_u,
                     t_docling, t_easy, len(ocr_d.tokens), len(det),
                     len(conf_d), len(conf_e),
                     sorted({r.label for r in layout.regions})))
        results.append({
            "document": name, "must_contain": must,
            "region_labels": sorted({r.label for r in layout.regions}),
            "docling": {"exact_recall": round(ex_d, 4), "word_recall": round(wr_d, 4),
                        "tokens": len(ocr_d.tokens), "seconds": round(t_docling, 2),
                        "tokens_with_confidence": len(conf_d),
                        "per_string": [round(x, 3) for x in per_d],
                        "text": text_d[:400]},
            "easyocr": {"exact_recall": round(ex_e, 4), "word_recall": round(wr_e, 4),
                        "detections": len(det), "seconds": round(t_easy, 2),
                        "detections_with_confidence": len(conf_e),
                        "mean_confidence": round(sum(conf_e) / len(conf_e), 4) if conf_e else None,
                        "low_confidence_count": sum(1 for c in conf_e if c < 0.5),
                        "per_string": [round(x, 3) for x in per_e],
                        "text": text_e[:400]},
            "union": {"exact_recall": round(ex_u, 4), "word_recall": round(wr_u, 4)},
        })
        print(f"  {name} done")

    print(f"\n{'document':<26} {'n':>2} {'docling':>15} {'easyocr':>15} {'union':>15}  regions")
    print(f"{'':<26} {'':>2} {'exact  word':>15} {'exact  word':>15} {'exact  word':>15}")
    print("=" * 108)
    for (n, k, ed, wd, ee, we, eu, wu, td, te, ntd, nte, cd, ce, labels) in rows:
        print(f"{n:<26} {k:2d} {ed:6.2f} {wd:6.2f} {ee:6.2f} {we:6.2f} "
              f"{eu:6.2f} {wu:6.2f}  {labels}")

    n = len(rows)
    print(f"\n{'':<26} {'mean exact':>12} {'mean word':>11} {'total s':>9} "
          f"{'tokens':>8} {'w/ conf':>8}")
    for label, i_e, i_w, i_t, i_n, i_c in (("docling", 2, 3, 8, 10, 12),
                                           ("easyocr", 4, 5, 9, 11, 13)):
        print(f"{label:<26} {sum(r[i_e] for r in rows)/n:12.3f} "
              f"{sum(r[i_w] for r in rows)/n:11.3f} {sum(r[i_t] for r in rows):9.1f} "
              f"{sum(r[i_n] for r in rows):8d} {sum(r[i_c] for r in rows):8d}")
    print(f"{'union (both kept)':<26} {sum(r[6] for r in rows)/n:12.3f} "
          f"{sum(r[7] for r in rows)/n:11.3f}")

    args.json.write_text(json.dumps(
        {"device": args.device, "dpi": args.dpi, "results": results},
        ensure_ascii=False, indent=2))
    print(f"\nwrote {args.json}")


if __name__ == "__main__":
    main()
