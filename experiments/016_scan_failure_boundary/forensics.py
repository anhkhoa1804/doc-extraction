#!/usr/bin/env python
"""016 -- Scan Failure Boundary: forensic trace of the 5 real scan_quality
documents that experiment 015 found scan_recovery could not touch (agreement
never went low because Docling and EasyOCR failed the *same* way).

For each document this traces every must_contain ground-truth phrase through
every stage of the real production pipeline (process_file, strategy
adaptive, default config -- ocr_backend: docling):

    render -> layout (analyze) -> OCR (recognize) -> region/cell assignment
    (merge_regions_into_page / table cell fill) -> assembled IR

and classifies each miss as:

  * stage="ocr"          -- absent from BOTH raw Docling OCR tokens and raw
                             EasyOCR tokens (Class B: OCR never saw it)
  * stage="assignment"    -- present in raw Docling OCR tokens, but none of
                             those tokens' bbox centers fall inside any
                             detected layout region / table cell (Class A:
                             OCR had it, orchestration lost it)
  * stage="assembly"      -- present in raw OCR AND correctly assigned to a
                             region/cell, but the exact-substring metric
                             still misses it (word-level recall on the final
                             text is high) -- a metric/ordering artifact,
                             not real content loss
  * stage="present"       -- actually found in the final text (should not
                             occur for a "missing" phrase; kept as a check)

Also computes deterministic, backend-independent image-quality signals
(resolution, contrast, blur/sharpness, ink coverage, connected components)
per page, and the existing text_quality.assess_text plausibility report on
the final assembled text, purely to see whether any of them correlate with
the failures found -- no model, no training.

    python experiments/016_scan_failure_boundary/forensics.py --device cuda
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

import cv2
import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "research" / "production_corpus"))
CORPUS = REPO / "research/production_corpus/corpus"

DOCS = [
    "hc_scan_vi", "hc_scan_en", "cmb_scan_multicol_en",
    "cmb_scan_stamp_table_vi", "ord_invoice_png_vi",
]


def _norm(s: str) -> str:
    return unicodedata.normalize("NFC", s).strip()


def words(s: str) -> list[str]:
    s = unicodedata.normalize("NFC", s).lower()
    return [w for w in re.split(r"[^0-9a-zà-ỹăâđêôơư]+", s, flags=re.I) if w]


def word_recall(phrase: str, haystack_words: set[str]) -> float:
    ws = words(phrase)
    if not ws:
        return 1.0
    return sum(1 for w in ws if w in haystack_words) / len(ws)


def document_text(document) -> str:
    parts: list[str] = []
    for page in document.pages:
        for el in getattr(page, "elements", []) or []:
            t = getattr(el, "text", None)
            if t:
                parts.append(t)
        for tbl in getattr(page, "tables", []) or []:
            for row in getattr(tbl, "cells", []) or []:
                for cell in row if isinstance(row, list) else [row]:
                    t = getattr(cell, "text", None) if not isinstance(cell, str) else cell
                    if t:
                        parts.append(t)
    return _norm("\n".join(parts))


def center_in(inner_bbox, outer_bbox) -> bool:
    cx = (inner_bbox.x0 + inner_bbox.x1) / 2
    cy = (inner_bbox.y0 + inner_bbox.y1) / 2
    return outer_bbox.x0 <= cx <= outer_bbox.x1 and outer_bbox.y0 <= cy <= outer_bbox.y1


def image_quality_signals(image_path: Path) -> dict:
    img = cv2.imread(str(image_path))
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape

    # Sharpness: variance of the Laplacian -- a well-known cheap blur proxy
    # (low variance = few sharp edges = blurry). No model, closed-form.
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())

    # Contrast: simple global std-dev of intensity.
    contrast = float(gray.std())

    # Noise estimate: residual after a light Gaussian blur -- std of
    # (original - blurred) approximates high-frequency noise energy,
    # independent of the sharpness/blur measure above (that one measures
    # edge strength; this one measures texture not explained by edges).
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    noise = float((gray.astype(np.float32) - blurred.astype(np.float32)).std())

    # Otsu binarization -> ink coverage + connected components (proxy for
    # character/word fragment count and speckle noise).
    otsu_thresh, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    ink_coverage = float((binary > 0).mean())
    n_components, _, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    # component 0 is background; drop tiny 1-2px specks (noise, not glyphs)
    real_components = [s for s in stats[1:] if s[cv2.CC_STAT_AREA] >= 3]

    return {
        "width": w, "height": h,
        "sharpness_laplacian_var": round(sharpness, 2),
        "contrast_std": round(contrast, 2),
        "noise_residual_std": round(noise, 3),
        "otsu_threshold": int(otsu_thresh),
        "ink_coverage": round(ink_coverage, 4),
        "n_connected_components": len(real_components),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--json", type=Path, default=Path(__file__).parent / "forensics_results.json")
    args = ap.parse_args()

    from doc_extraction.backends.docling_backend import DoclingBackend
    from doc_extraction.backends.easyocr_backend import EasyOCRBackend
    from doc_extraction.cli import process_file
    from doc_extraction.ingest.targeted_recovery import segment_lines
    from doc_extraction.ingest.text_quality import assess_text
    from doc_extraction.pipelines.base import PageInput
    from run_benchmark import configure
    from PIL import Image

    scratch_out = Path("/tmp/claude-1002/-home-leanhkhoa150204/53135489-765a-4c07-8a55-7b281fb97758/scratchpad/scan_failure_boundary_016")
    scratch_out.mkdir(parents=True, exist_ok=True)

    manifest = json.loads((CORPUS / "manifest.json").read_text())
    by_id = {d["document_id"]: d for d in manifest["documents_list"]}

    config = configure("adaptive", None, args.device)
    print(f"device: {config.device}, ocr_backend: {config.ocr_backend}, render_dpi: {config.render_dpi}\n")

    docling_direct = DoclingBackend(device=config.device, ocr_languages=config.ocr_languages)
    easyocr_backend = EasyOCRBackend(device=config.device, languages=config.ocr_languages)
    assess = assess_text

    all_results = []
    for name in DOCS:
        meta = by_id[name]
        src = CORPUS / meta["filename"]
        must = meta["must_contain"]

        print(f"=== {name} ===")
        document = process_file(src, config, output_root=scratch_out)
        page = document.pages[0]
        image_path = Path(page.rendered_image_path)

        page_input = PageInput(page_index=0, width=page.width, height=page.height,
                                image_path=image_path, dpi=page.dpi)

        layout_result = docling_direct.analyze(page_input)
        ocr_result = docling_direct.recognize(page_input)
        easyocr_result = easyocr_backend.recognize(page_input)

        final_text = document_text(document)
        raw_docling_text = _norm(" ".join(t.text for t in ocr_result.tokens))
        raw_easyocr_text = _norm(" ".join(t.text for t in easyocr_result.tokens))
        final_words = set(words(final_text))

        img_signals = image_quality_signals(image_path)
        tq_report = assess(final_text)

        # Region coverage: fraction of page area covered by the union of
        # detected layout region bboxes (approximated by summed area minus
        # overlap -- overlap is small for a layout model's own regions, so
        # simple sum is a reasonable first-order estimate).
        page_area = page.width * page.height
        region_area = sum(max(0.0, r.bbox.x1 - r.bbox.x0) * max(0.0, r.bbox.y1 - r.bbox.y0)
                           for r in layout_result.regions if r.bbox is not None)
        region_coverage = round(min(1.0, region_area / page_area), 4) if page_area else 0.0

        raw_docling_words = set(words(raw_docling_text))
        raw_easyocr_words = set(words(raw_easyocr_text))

        phrase_traces = []
        for phrase in must:
            in_final = _norm(phrase) in final_text
            in_raw_docling = _norm(phrase) in raw_docling_text
            in_raw_easyocr = _norm(phrase) in raw_easyocr_text
            wr_final = round(word_recall(phrase, final_words), 3)
            wr_raw_docling = round(word_recall(phrase, raw_docling_words), 3)
            wr_raw_easyocr = round(word_recall(phrase, raw_easyocr_words), 3)
            wr_raw_best = max(wr_raw_docling, wr_raw_easyocr)

            if in_final:
                stage = "present"
            elif wr_raw_best < 0.8:
                # The words themselves never showed up in EITHER backend's
                # raw output -- true Class B, OCR never saw it. Distinct
                # from the exact-substring check: this is robust to word
                # order, so it is not fooled by the already-known
                # word-scrambling defect (docstring in scan_recovery.py).
                stage = "ocr_missing"
            elif wr_final < 0.8:
                # Words WERE recognized by at least one backend (wr_raw_best
                # >= 0.8) but did NOT survive into the assembled document
                # text (wr_final < 0.8) -- lost strictly between raw OCR and
                # final IR: a real region-/table-cell-assignment loss, not
                # an OCR-recognition problem. This must be checked before
                # the raw-substring test below, or a case where raw OCR had
                # the words but final assembly dropped them entirely gets
                # mislabeled as "scrambled" (which implies the words are
                # merely reordered, still present somewhere in the end).
                stage = "assignment"
            elif not in_raw_docling and not in_raw_easyocr:
                # Words present in raw OCR AND in the final text (wr_final
                # >= 0.8 above), but never as the correct contiguous phrase
                # at either stage -- the scrambling happened inside OCR/
                # recognition itself, before any assignment stage.
                stage = "ocr_scrambled"
            else:
                # Exact phrase existed in at least one backend's raw OCR
                # text and the words survived into final text, yet the
                # exact contiguous phrase did not -- something in
                # reassembly (element ordering/joining) broke it, or only
                # the non-production backend (EasyOCR) ever had it exactly.
                stage = "assembly"

            # For assignment-stage misses: which raw docling tokens overlap
            # this phrase's words, and were their centers inside ANY
            # detected region/table? (Only computed for the diagnostic case
            # -- cheap, a handful of phrases per document.)
            containment_detail = None
            if stage == "assignment":
                phrase_ws = set(words(phrase))
                matching_tokens = [t for t in ocr_result.tokens
                                    if phrase_ws & set(words(t.text))]
                contained_in_any_region = [
                    any(center_in(t.bbox, r.bbox) for r in layout_result.regions if r.bbox is not None)
                    for t in matching_tokens
                ]
                containment_detail = {
                    "n_matching_docling_tokens": len(matching_tokens),
                    "sample_token_texts": [t.text[:80] for t in matching_tokens[:3]],
                    "all_contained_in_some_region": (
                        all(contained_in_any_region) if contained_in_any_region else None
                    ),
                    "any_contained_in_some_region": (
                        any(contained_in_any_region) if contained_in_any_region else None
                    ),
                }

            # For any non-"present" phrase: find the raw docling OCR token(s)
            # whose words overlap the phrase, locate the enclosing layout
            # region (by bbox containment of the token's own bbox), crop the
            # rendered page to that region, and run the already-built
            # `segment_lines` projection-profile line detector on the crop
            # -- directly tests, rather than infers, whether the offending
            # region spans more than one physical text line.
            line_band_detail = None
            if True:  # compute for every phrase, incl. "present", as a control comparison
                phrase_ws = set(words(phrase))
                matching = [t for t in ocr_result.tokens if phrase_ws & set(words(t.text))]
                if matching:
                    token = matching[0]
                    enclosing = next(
                        (r for r in layout_result.regions
                         if r.bbox is not None and center_in(token.bbox, r.bbox)),
                        None,
                    )
                    if enclosing is not None:
                        with Image.open(image_path) as im:
                            pad = 4
                            crop = im.crop((
                                max(0, int(enclosing.bbox.x0) - pad), max(0, int(enclosing.bbox.y0) - pad),
                                min(im.width, int(enclosing.bbox.x1) + pad), min(im.height, int(enclosing.bbox.y1) + pad),
                            ))
                            bands = segment_lines(crop)
                        line_band_detail = {
                            "region_label": enclosing.label,
                            "region_bbox": [round(v, 1) for v in enclosing.bbox.as_tuple()],
                            "n_line_bands_detected": len(bands),
                            "spans_multiple_lines": len(bands) > 1,
                        }

            phrase_traces.append({
                "phrase": phrase, "stage": stage,
                "in_final": in_final, "in_raw_docling": in_raw_docling, "in_raw_easyocr": in_raw_easyocr,
                "word_recall_final": wr_final,
                "word_recall_raw_docling": wr_raw_docling, "word_recall_raw_easyocr": wr_raw_easyocr,
                "containment_detail": containment_detail,
                "line_band_detail": line_band_detail,
            })
            lb = f" lines={line_band_detail['n_line_bands_detected']}({line_band_detail['region_label']})" if line_band_detail else ""
            print(f"  [{stage:>13}] {phrase!r}  final={in_final} docling={in_raw_docling} "
                  f"easyocr={in_raw_easyocr} wr_final={wr_final} wr_raw_d={wr_raw_docling} wr_raw_e={wr_raw_easyocr}{lb}")

        result = {
            "document": name,
            "labels": meta["hard_case_labels"],
            "image_quality": img_signals,
            "region_coverage": region_coverage,
            "n_layout_regions": len(layout_result.regions),
            "region_labels": [r.label for r in layout_result.regions],
            "n_raw_docling_tokens": len(ocr_result.tokens),
            "n_raw_easyocr_tokens": len(easyocr_result.tokens),
            "easyocr_mean_confidence": (
                round(sum(t.confidence for t in easyocr_result.tokens if t.confidence is not None) /
                      max(1, sum(1 for t in easyocr_result.tokens if t.confidence is not None)), 4)
                if easyocr_result.tokens else None
            ),
            "text_quality": tq_report.as_dict(),
            "n_tables_expected": meta.get("expected_tables", 0),
            "n_tables_found": sum(len(getattr(p, "tables", []) or []) for p in document.pages),
            "phrase_traces": phrase_traces,
        }
        all_results.append(result)
        print()

    args.json.write_text(json.dumps(all_results, ensure_ascii=False, indent=2))
    print(f"wrote {args.json}")


if __name__ == "__main__":
    main()
