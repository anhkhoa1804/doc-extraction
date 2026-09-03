"""012 — Direct EasyOCR vs Docling-wrapped OCR, as production backends.

Prior milestone's `research/experiments/_scan_forensics/ocr_unbundle.py`
made this comparison as a one-off research script, calling `easyocr.Reader`
ad hoc. This re-runs the same underlying question through the actual
production adapters this milestone built
(`doc_extraction.backends.docling_backend.DoclingBackend.recognize` vs
`doc_extraction.backends.easyocr_backend.EasyOCRBackend.recognize`) --
partly to re-confirm the finding still holds post the traverse_pictures fix
(experiment 011 changed what DoclingBackend emits for one document in this
set), and partly because testing the real adapter is a different, stronger
claim than testing the library it wraps.

Only the OCR stage is compared -- same rendered page, same DPI, same
languages, same device, only the OCR implementation differs (mission's own
"controlled A/B" instruction). Layout/table are not run.

    python experiments/012_direct_easyocr/run_ab.py --device cuda
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
import unicodedata
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
CORPUS = REPO / "research/production_corpus/corpus"

# The 6 documents the mission requires at minimum (experiment 010's ranked
# scan_quality failures), plus additional categories the mission asks for
# (clean EN/VI, small text, low contrast, stamp, table) drawn from the same
# corpus so ground truth (`must_contain`) is already defined and audited.
DOCS = [
    # required minimum
    "hc_scan_vi", "hc_scan_en", "cmb_scan_multicol_en",
    "cmb_scan_stamp_table_vi", "cmb_scan_tiny_vi", "ord_invoice_png_vi",
    # additional hard-case categories (mission section 7)
    "ord_contract_en",       # clean EN, rendered (born-digital; OCR quality on clean pixels)
    "ord_contract_vi",       # clean VI, rendered
    "hc_tiny_text_en",       # small text
    "hc_tiny_text_vi",       # small text, VI
    "hc_low_contrast_vi",    # low contrast
    "hc_stamp_text_vi",      # stamp over text (not table)
    "cmb_multicol_table_en", # table, born-digital rendered
]


def words(s: str) -> list[str]:
    s = unicodedata.normalize("NFC", s).lower()
    return [w for w in re.split(r"[^0-9a-zà-ỹăâđêôơư]+", s, flags=re.I) if w]


def norm(s: str) -> str:
    return " ".join(unicodedata.normalize("NFC", s or "").split()).lower()


def recall(text: str, must: list[str]) -> tuple[float, float]:
    tw = set(words(text))
    ex = sum(1 for s in must if norm(s) in norm(text)) / len(must) if must else 1.0
    per = []
    for s in must:
        sw = words(s)
        per.append(sum(1 for w in sw if w in tw) / len(sw) if sw else 0.0)
    wr = sum(per) / len(per) if per else 1.0
    return ex, wr


def bbox_sane(tokens, page_w: float, page_h: float) -> tuple[int, int]:
    """Coarse geometric sanity, not a ground-truth IoU (no hand-labeled
    boxes exist for this corpus): a token's bbox must have positive area
    and lie within the page. Returns (n_sane, n_total)."""
    n_ok = 0
    for t in tokens:
        b = t.bbox
        ok = (b.x1 > b.x0 and b.y1 > b.y0
              and b.x0 >= -1 and b.y0 >= -1
              and b.x1 <= page_w + 1 and b.y1 <= page_h + 1)
        n_ok += int(ok)
    return n_ok, len(tokens)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--dpi", type=int, default=200)
    ap.add_argument("--resource-state", default="unspecified",
                     help="CLEAR/LIMITED/PROTECTED, recorded from nvidia-smi at launch, not measured here")
    ap.add_argument("--json", type=Path, default=Path(__file__).parent / "results.json")
    args = ap.parse_args()

    from doc_extraction.backends.docling_backend import DoclingBackend
    from doc_extraction.backends.easyocr_backend import EasyOCRBackend
    from doc_extraction.pipelines.base import PageInput
    from doc_extraction.stages.render import render_image_passthrough, render_single_pdf_page

    scratch = Path("/tmp/claude-1002/-home-leanhkhoa150204/b99be592-4e1c-45b0-9aa4-c7c93b132efa/scratchpad/ocr_ab")
    scratch.mkdir(parents=True, exist_ok=True)

    manifest = json.loads((CORPUS / "manifest.json").read_text())
    by_id = {d["document_id"]: d for d in manifest["documents_list"]}

    docling = DoclingBackend(device=args.device, ocr_languages=["en", "vi"])
    easyocr_backend = EasyOCRBackend(device=args.device, languages=["en", "vi"])

    results = []
    for i, name in enumerate(DOCS):
        meta = by_id[name]
        src = CORPUS / meta["filename"]
        must = meta["must_contain"]
        is_pdf = src.suffix.lower() == ".pdf"

        page_dir = scratch / name
        if is_pdf:
            img = render_single_pdf_page(src, 0, page_dir, dpi=args.dpi)
        else:
            img = render_image_passthrough(src, page_dir)
        # Read actual rendered pixel dimensions from the file itself, the
        # same way run_scanned_page_pipeline does -- this is the space
        # PageInput.width/height and every returned bbox must agree with.
        from PIL import Image
        with Image.open(img) as im:
            pw, ph = float(im.size[0]), float(im.size[1])

        page_input = PageInput(page_index=0, width=pw, height=ph, image_path=img, dpi=args.dpi)

        t0 = time.perf_counter()
        docling_result = docling.recognize(page_input)
        t_docling = time.perf_counter() - t0
        cold_docling = (i == 0)

        t0 = time.perf_counter()
        easyocr_result = easyocr_backend.recognize(page_input)
        t_easyocr = time.perf_counter() - t0
        cold_easyocr = (i == 0)

        text_d = " ".join(t.text for t in docling_result.tokens)
        text_e = " ".join(t.text for t in easyocr_result.tokens)

        ex_d, wr_d = recall(text_d, must)
        ex_e, wr_e = recall(text_e, must)
        ex_u, wr_u = recall(text_d + " " + text_e, must)

        # Cross-backend agreement: word-set Jaccard between what the two
        # backends each read off the same pixels. Section 21's hypothesis --
        # disagreement itself may be a stronger verification signal than
        # either backend's own confidence.
        wd, we = set(words(text_d)), set(words(text_e))
        jaccard = len(wd & we) / len(wd | we) if (wd or we) else 1.0

        conf_d = [t.confidence for t in docling_result.tokens if t.confidence is not None]
        conf_e = [t.confidence for t in easyocr_result.tokens if t.confidence is not None]

        sane_d = bbox_sane(docling_result.tokens, pw, ph)
        sane_e = bbox_sane(easyocr_result.tokens, pw, ph)

        row = {
            "document": name,
            "n_must_contain": len(must),
            "device": args.device,
            "dpi": args.dpi,
            "resource_state": args.resource_state,
            "page_px": [pw, ph],
            "docling": {
                "exact_recall": round(ex_d, 4), "word_recall": round(wr_d, 4),
                "tokens": len(docling_result.tokens), "seconds": round(t_docling, 3),
                "cold": cold_docling,
                "tokens_with_confidence": len(conf_d),
                "bbox_sane": f"{sane_d[0]}/{sane_d[1]}",
            },
            "easyocr": {
                "exact_recall": round(ex_e, 4), "word_recall": round(wr_e, 4),
                "tokens": len(easyocr_result.tokens), "seconds": round(t_easyocr, 3),
                "cold": cold_easyocr,
                "tokens_with_confidence": len(conf_e),
                "mean_confidence": round(statistics.mean(conf_e), 4) if conf_e else None,
                "min_confidence": round(min(conf_e), 4) if conf_e else None,
                "low_confidence_count_below_0.5": sum(1 for c in conf_e if c < 0.5),
                "bbox_sane": f"{sane_e[0]}/{sane_e[1]}",
            },
            "union": {"exact_recall": round(ex_u, 4), "word_recall": round(wr_u, 4)},
            "agreement_jaccard": round(jaccard, 4),
        }
        results.append(row)
        print(f"  {name:<26} docling ex={ex_d:.2f} wr={wr_d:.2f} {t_docling:6.2f}s  |  "
              f"easyocr ex={ex_e:.2f} wr={wr_e:.2f} {t_easyocr:6.2f}s "
              f"conf={row['easyocr']['mean_confidence']} agree={jaccard:.2f}")

    n = len(results)
    warm_d = [r["docling"]["seconds"] for r in results if not r["docling"]["cold"]]
    warm_e = [r["easyocr"]["seconds"] for r in results if not r["easyocr"]["cold"]]
    summary = {
        "n_documents": n,
        "device": args.device,
        "resource_state": args.resource_state,
        "docling": {
            "mean_exact_recall": round(sum(r["docling"]["exact_recall"] for r in results) / n, 4),
            "mean_word_recall": round(sum(r["docling"]["word_recall"] for r in results) / n, 4),
            "total_tokens_with_confidence": sum(r["docling"]["tokens_with_confidence"] for r in results),
            "cold_seconds": results[0]["docling"]["seconds"],
            "warm_seconds_mean": round(statistics.mean(warm_d), 3) if warm_d else None,
        },
        "easyocr": {
            "mean_exact_recall": round(sum(r["easyocr"]["exact_recall"] for r in results) / n, 4),
            "mean_word_recall": round(sum(r["easyocr"]["word_recall"] for r in results) / n, 4),
            "total_tokens_with_confidence": sum(r["easyocr"]["tokens_with_confidence"] for r in results),
            "cold_seconds": results[0]["easyocr"]["seconds"],
            "warm_seconds_mean": round(statistics.mean(warm_e), 3) if warm_e else None,
        },
        "union": {
            "mean_exact_recall": round(sum(r["union"]["exact_recall"] for r in results) / n, 4),
            "mean_word_recall": round(sum(r["union"]["word_recall"] for r in results) / n, 4),
        },
        "mean_agreement_jaccard": round(sum(r["agreement_jaccard"] for r in results) / n, 4),
    }

    print(f"\n=== summary (n={n}, device={args.device}, resource_state={args.resource_state}) ===")
    print(json.dumps(summary, indent=2))

    args.json.write_text(json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=2))
    print(f"\nwrote {args.json}")


if __name__ == "__main__":
    main()
