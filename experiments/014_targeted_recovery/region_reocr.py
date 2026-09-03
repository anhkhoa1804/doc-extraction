"""013b — Does a CONFLICT region predict "worth reprocessing", and does a
targeted crop + re-OCR actually resolve it?

Smallest possible bridge to region-level recovery (mission section 11): not
a general recovery engine, just "for the actual CONFLICT groups this
corpus produced, what happens if we crop that bbox and re-OCR just the
crop?" Deliberately narrow -- a handful of real conflicts, not a sweep.

    python experiments/013_evidence_fusion/region_reocr.py --device cuda
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
CORPUS = REPO / "research/production_corpus/corpus"

# The two documents experiment 013's main run actually produced CONFLICT
# groups for (conflict_rate > 0): cmb_scan_tiny_vi (0.50) and
# cmb_multicol_table_en (0.05). Not a hand-picked "hard" set -- these are
# the only two documents in the 13-doc corpus where policy C's own decision
# engine raised a conflict at all.
DOCS = ["cmb_scan_tiny_vi", "cmb_multicol_table_en"]


def words(s: str) -> list[str]:
    s = unicodedata.normalize("NFC", s).lower()
    return [w for w in re.split(r"[^0-9a-zà-ỹăâđêôơư]+", s, flags=re.I) if w]


def word_overlap(a: str, b: str) -> float:
    wa, wb = set(words(a)), set(words(b))
    return len(wa & wb) / len(wa | wb) if (wa or wb) else 1.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--dpi", type=int, default=200)
    ap.add_argument("--pad", type=int, default=10, help="pixels of padding around each conflict bbox before cropping")
    ap.add_argument("--json", type=Path, default=Path(__file__).parent / "region_reocr_results.json")
    args = ap.parse_args()

    from doc_extraction.backends.docling_backend import DoclingBackend
    from doc_extraction.backends.easyocr_backend import EasyOCRBackend
    from doc_extraction.ingest.evidence_fusion import fuse_page
    from doc_extraction.pipelines.base import PageInput
    from doc_extraction.stages.render import render_image_passthrough, render_single_pdf_page
    from PIL import Image

    scratch = Path("/tmp/claude-1002/-home-leanhkhoa150204/015e597f-af8b-4e89-800b-931d0f18d3f8/scratchpad/fusion_ab")
    scratch.mkdir(parents=True, exist_ok=True)
    crop_dir = scratch / "_conflict_crops"
    crop_dir.mkdir(parents=True, exist_ok=True)

    manifest = json.loads((CORPUS / "manifest.json").read_text())
    by_id = {d["document_id"]: d for d in manifest["documents_list"]}

    docling = DoclingBackend(device=args.device, ocr_languages=["en", "vi"])
    easyocr_backend = EasyOCRBackend(device=args.device, languages=["en", "vi"])

    all_rows = []
    for name in DOCS:
        meta = by_id[name]
        src = CORPUS / meta["filename"]
        must = meta["must_contain"]
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
            x0 = max(0, int(g.bbox.x0) - args.pad)
            y0 = max(0, int(g.bbox.y0) - args.pad)
            x1 = min(int(pw), int(g.bbox.x1) + args.pad)
            y1 = min(int(ph), int(g.bbox.y1) + args.pad)
            crop = page_img.crop((x0, y0, x1, y1))
            crop_path = crop_dir / f"{name}_{k}.png"
            crop.save(crop_path)

            reader = easyocr_backend._get_reader()
            detections = reader.readtext(str(crop_path), detail=1)
            reocr_text = " ".join((t or "").strip() for _, t, _ in detections if (t or "").strip())
            reocr_confs = [float(c) for _, _, c in detections]

            # Does this region overlap a must_contain phrase at all? (word
            # overlap between the phrase and *either* original reading,
            # since we have no per-region ground truth, only page-level
            # phrases.)
            relevant = [m for m in must if word_overlap(m, g.docling_text) > 0 or word_overlap(m, g.easyocr_text) > 0]

            sim_docling_reocr = word_overlap(g.docling_text, reocr_text)
            sim_easyocr_reocr = word_overlap(g.easyocr_text, reocr_text)
            # Did re-OCR agree with one of the two original readings more
            # than they agreed with each other? That is the operational
            # question: did spending extra compute on this region actually
            # move the needle, or just produce a third opinion.
            original_agreement = g.text_similarity or 0.0
            resolved = max(sim_docling_reocr, sim_easyocr_reocr) > max(original_agreement, 0.5)

            row = {
                "document": name, "group_index": k,
                "bbox": [g.bbox.x0, g.bbox.y0, g.bbox.x1, g.bbox.y1],
                "docling_text": g.docling_text, "easyocr_text": g.easyocr_text,
                "original_agreement": round(original_agreement, 4),
                "reocr_text": reocr_text,
                "reocr_mean_confidence": round(sum(reocr_confs) / len(reocr_confs), 4) if reocr_confs else None,
                "sim_docling_vs_reocr": round(sim_docling_reocr, 4),
                "sim_easyocr_vs_reocr": round(sim_easyocr_reocr, 4),
                "relevant_must_contain_phrases": relevant,
                "resolved_toward_one_reading": resolved,
            }
            all_rows.append(row)
            print(f"  group {k}: bbox={row['bbox']}")
            print(f"    docling : {g.docling_text!r}")
            print(f"    easyocr : {g.easyocr_text!r}")
            print(f"    re-OCR  : {reocr_text!r}  (conf={row['reocr_mean_confidence']})")
            print(f"    sim(d,re)={sim_docling_reocr:.2f} sim(e,re)={sim_easyocr_reocr:.2f} "
                  f"original_agreement={original_agreement:.2f} resolved={resolved}")

    args.json.write_text(json.dumps(all_rows, ensure_ascii=False, indent=2))
    n_resolved = sum(1 for r in all_rows if r["resolved_toward_one_reading"])
    print(f"\n{n_resolved}/{len(all_rows)} conflict groups moved toward a reading after targeted re-OCR")
    print(f"wrote {args.json}")


if __name__ == "__main__":
    main()
