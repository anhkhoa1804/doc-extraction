"""Phases 12-14 — where does a scanned document's text actually disappear?

Experiment 010 ranked `scan_quality` the most frequent production failure
class and noted that what goes missing is disproportionately **titles and
headers** — text that is *larger* than the body, so a resolution floor does
not explain it. That was recorded as a lead, not a finding. This resolves it.

Method
------
For every failing scanned document, follow one expected string through every
stage and record the first one at which it is no longer recoverable:

    render      does the rasterized page contain the pixels at all?
    layout      is there a layout region covering where the string should be?
    ocr         do the OCR tokens contain the string?
    regions     did the string's tokens land inside some region?
    assembly    did it reach the Document's elements?
    output      is it in the final text?

The distinction that matters, and the reason this is not a guess: if OCR
holds the string but the final output does not, the defect is in layout or
selection and no amount of resolution or model quality will fix it. If OCR
never saw it, the defect is upstream and resolution, contrast or segmentation
are the candidates.

Every stage is recorded for every string, so the answer is a table rather than
an anecdote.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import unicodedata
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO))

CORPUS = REPO / "research/production_corpus/corpus"

# The six scanned documents experiment 010 measured as failing, with the
# recall it recorded for each.
CASES = {
    "cmb_scan_tiny_vi": 0.00,
    "hc_scan_vi": 0.25,
    "cmb_scan_stamp_table_vi": 0.25,
    "ord_invoice_png_vi": 0.57,
    "cmb_scan_multicol_en": 0.67,
    "hc_scan_en": 0.67,
}


def norm(s: str) -> str:
    return " ".join(unicodedata.normalize("NFC", s or "").split()).lower()


def contains(haystack: str, needle: str) -> bool:
    return norm(needle) in norm(haystack)


def load_manifest() -> dict:
    m = json.loads((CORPUS / "manifest.json").read_text())
    docs = m["documents_list"]
    if isinstance(docs, dict):
        return docs
    return {d["document_id"]: d for d in docs}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--dpi", type=int, default=200)
    ap.add_argument("--docs", nargs="*", default=list(CASES))
    ap.add_argument("--json", type=Path, default=Path(__file__).parent / "forensics.json")
    args = ap.parse_args()

    import pymupdf

    from doc_extraction.backends.docling_backend import DoclingBackend
    from doc_extraction.config import PipelineConfig
    from doc_extraction.pipelines.base import PageInput
    from doc_extraction.stages.render import (
        render_image_passthrough,
        render_single_pdf_page,
    )

    manifest = load_manifest()
    config = PipelineConfig()
    config.device = args.device
    config.render_dpi = args.dpi

    backend = DoclingBackend(device=args.device, ocr_languages=["en", "vi"])
    print(f"docling available: {backend.is_available()}  device={args.device} dpi={args.dpi}")

    out_root = Path("/tmp/claude-1002/-home-leanhkhoa150204/"
                    "17350d12-6add-4719-8ecd-40b53c80d434/scratchpad/forensics")
    out_root.mkdir(parents=True, exist_ok=True)

    results = []
    for name in args.docs:
        meta = manifest.get(name)
        if meta is None:
            print(f"  {name}: not in manifest")
            continue
        src = CORPUS / meta["filename"]
        if not src.exists():
            print(f"  {name}: {src.name} missing")
            continue

        must = meta.get("must_contain", [])
        print(f"\n{'='*78}\n{name}   ({len(must)} expected strings, "
              f"010 recall {CASES.get(name, float('nan')):.2f})\n{'='*78}")

        doc_rec = {"document": name, "filename": meta["filename"],
                   "must_contain": must, "device": args.device, "dpi": args.dpi,
                   "pages": []}

        is_pdf = src.suffix.lower() == ".pdf"
        pdf = pymupdf.open(src) if is_pdf else None
        try:
            n_pages = pdf.page_count if is_pdf else 1
            for pno in range(n_pages):
                page_w, page_h = (pdf[pno].rect.width, pdf[pno].rect.height) if is_pdf else (0.0, 0.0)
                # STAGE 1 — render
                t0 = time.perf_counter()
                page_dir = out_root / f"{name}_p{pno}"
                if is_pdf:
                    img_path = render_single_pdf_page(src, pno, page_dir, dpi=args.dpi)
                else:
                    img_path = render_image_passthrough(src, page_dir)
                t_render = time.perf_counter() - t0

                from PIL import Image
                with Image.open(img_path) as im:
                    w, h = im.size

                if not is_pdf:
                    page_w, page_h = float(w), float(h)
                pi = PageInput(page_index=pno, width=page_w,
                               height=page_h, image_path=img_path,
                               dpi=args.dpi,
                               source_pdf_path=src if is_pdf else None)

                # STAGE 2 — layout
                t0 = time.perf_counter()
                layout = backend.analyze(pi)
                t_layout = time.perf_counter() - t0

                # STAGE 3 — OCR
                t0 = time.perf_counter()
                ocr = backend.recognize(pi)
                t_ocr = time.perf_counter() - t0

                ocr_text = " ".join(tok.text for tok in ocr.tokens)

                # Which tokens fall inside some layout region?
                def in_any_region(tok) -> bool:
                    for r in layout.regions:
                        b, rb = tok.bbox, r.bbox
                        ix = max(0.0, min(b.x1, rb.x1) - max(b.x0, rb.x0))
                        iy = max(0.0, min(b.y1, rb.y1) - max(b.y0, rb.y0))
                        if ix * iy > 0.5 * max(1e-6, b.area()):
                            return True
                    return False

                covered = [t for t in ocr.tokens if in_any_region(t)]
                covered_text = " ".join(t.text for t in covered)

                page_rec = {
                    "page": pno,
                    "image_size": [w, h],
                    "timings": {"render": round(t_render, 3),
                                "layout": round(t_layout, 3),
                                "ocr": round(t_ocr, 3)},
                    "n_regions": len(layout.regions),
                    "region_labels": sorted({r.label for r in layout.regions}),
                    "n_ocr_tokens": len(ocr.tokens),
                    "n_tokens_in_regions": len(covered),
                    "layout_warnings": layout.warnings,
                    "ocr_warnings": ocr.warnings,
                    "regions": [{"label": r.label,
                                 "bbox": [round(v, 1) for v in r.bbox.as_tuple()]}
                                for r in layout.regions],
                    "ocr_tokens": [{"text": t.text[:120],
                                    "bbox": [round(v, 1) for v in t.bbox.as_tuple()],
                                    "conf": t.confidence}
                                   for t in ocr.tokens],
                    "strings": [],
                }

                for s in must:
                    page_rec["strings"].append({
                        "string": s,
                        "in_ocr": contains(ocr_text, s),
                        "in_covered_tokens": contains(covered_text, s),
                    })

                doc_rec["pages"].append(page_rec)

                print(f"  page {pno}: {w}x{h}px  regions={len(layout.regions)} "
                      f"{page_rec['region_labels']}")
                print(f"    ocr tokens={len(ocr.tokens)}  in-region={len(covered)}  "
                      f"render {t_render:.2f}s layout {t_layout:.2f}s ocr {t_ocr:.2f}s")
                for tk in page_rec["ocr_tokens"][:6]:
                    print(f"      token @{tk['bbox']}: {tk['text'][:70]!r}")
                for s in page_rec["strings"]:
                    if not s["in_ocr"]:
                        verdict = "LOST BEFORE/AT OCR"
                    elif not s["in_covered_tokens"]:
                        verdict = "OCR HAS IT, NO REGION COVERS IT"
                    else:
                        verdict = "present through OCR+layout"
                    print(f"      {s['string'][:44]!r:48} {verdict}")
        finally:
            if pdf is not None:
                pdf.close()

        results.append(doc_rec)

    # ---- aggregate: first stage of loss, per string --------------------
    print(f"\n{'='*78}\nWHERE STRINGS ARE LOST (all documents, all pages)\n{'='*78}")
    tally = {"lost_before_ocr": 0, "ocr_only_no_region": 0, "survived": 0}
    for d in results:
        for p in d["pages"]:
            for s in p["strings"]:
                if not s["in_ocr"]:
                    tally["lost_before_ocr"] += 1
                elif not s["in_covered_tokens"]:
                    tally["ocr_only_no_region"] += 1
                else:
                    tally["survived"] += 1
    total = sum(tally.values()) or 1
    for k, v in tally.items():
        print(f"  {k:<24} {v:4d}   {v/total:6.1%}")

    args.json.write_text(json.dumps({"cases": CASES, "results": results,
                                     "tally": tally}, ensure_ascii=False, indent=2))
    print(f"\nwrote {args.json}")


if __name__ == "__main__":
    main()
