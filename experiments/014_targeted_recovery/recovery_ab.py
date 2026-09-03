"""013c — Targeted recovery prototype against the two real CONFLICT groups
this corpus produced (post the `keep_both_agree` fix). Not a hand-picked
"hard" set: these are the only two the fusion engine itself flagged.

    python experiments/013_evidence_fusion/recovery_ab.py --device cuda
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
CORPUS = REPO / "research/production_corpus/corpus"
DOCS = ["cmb_scan_tiny_vi", "cmb_multicol_table_en"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--dpi", type=int, default=200)
    ap.add_argument("--json", type=Path, default=Path(__file__).parent / "recovery_results.json")
    args = ap.parse_args()

    from doc_extraction.backends.docling_backend import DoclingBackend
    from doc_extraction.backends.easyocr_backend import EasyOCRBackend
    from doc_extraction.ingest.evidence_fusion import fuse_page
    from doc_extraction.ingest.targeted_recovery import recover_region
    from doc_extraction.pipelines.base import PageInput
    from doc_extraction.stages.render import render_image_passthrough, render_single_pdf_page
    from PIL import Image

    scratch = Path("/tmp/claude-1002/-home-leanhkhoa150204/015e597f-af8b-4e89-800b-931d0f18d3f8/scratchpad/fusion_ab")
    scratch.mkdir(parents=True, exist_ok=True)

    manifest = json.loads((CORPUS / "manifest.json").read_text())
    by_id = {d["document_id"]: d for d in manifest["documents_list"]}

    docling = DoclingBackend(device=args.device, ocr_languages=["en", "vi"])
    easyocr_backend = EasyOCRBackend(device=args.device, languages=["en", "vi"])

    all_rows = []
    for name in DOCS:
        meta = by_id[name]
        src = CORPUS / meta["filename"]
        is_pdf = src.suffix.lower() == ".pdf"
        page_dir = scratch / name
        img_path = (render_single_pdf_page(src, 0, page_dir, dpi=args.dpi) if is_pdf
                    else render_image_passthrough(src, page_dir))
        with Image.open(img_path) as im:
            pw, ph = float(im.size[0]), float(im.size[1])
            page_img = im.convert("RGB").copy()

        page_input = PageInput(page_index=0, width=pw, height=ph, image_path=img_path, dpi=args.dpi)
        d = docling.recognize(page_input)
        e = easyocr_backend.recognize(page_input)
        groups = fuse_page(d.tokens, e.tokens)
        conflicts = [g for g in groups if g.decision == "conflict"]

        print(f"\n=== {name}: {len(conflicts)} conflict group(s) ===")
        for k, g in enumerate(conflicts):
            recovery_dir = scratch / "_recovery" / f"{name}_{k}"
            result = recover_region(g, page_img, easyocr_backend, recovery_dir)

            print(f"  group {k} bbox={result.bbox}")
            print(f"    docling: {g.docling_text!r}")
            print(f"    easyocr: {g.easyocr_text!r}")
            for a in result.attempts:
                print(f"    [{a.method:>9}] {a.text!r} conf={a.mean_confidence} "
                      f"sim(d)={a.sim_to_docling:.2f} sim(e)={a.sim_to_easyocr:.2f}")
            print(f"    chosen={result.chosen.method if result.chosen else None} "
                  f"replaced={result.replaced} reasons={result.reasons}")

            all_rows.append({
                "document": name, "group_index": k,
                "docling_text": g.docling_text, "easyocr_text": g.easyocr_text,
                "original_agreement": g.text_similarity,
                "attempts": [
                    {"method": a.method, "text": a.text, "mean_confidence": a.mean_confidence,
                     "sim_to_docling": round(a.sim_to_docling, 4), "sim_to_easyocr": round(a.sim_to_easyocr, 4)}
                    for a in result.attempts
                ],
                "chosen_method": result.chosen.method if result.chosen else None,
                "replaced": result.replaced,
                "reasons": result.reasons,
            })

    args.json.write_text(json.dumps(all_rows, ensure_ascii=False, indent=2))
    n_replaced = sum(1 for r in all_rows if r["replaced"])
    print(f"\n{n_replaced}/{len(all_rows)} conflicts replaced by verified recovery")
    print(f"wrote {args.json}")


if __name__ == "__main__":
    main()
