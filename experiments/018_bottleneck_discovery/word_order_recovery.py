#!/usr/bin/env python
"""018 -- Word-order scrambling: trace, signal, and recovery test.

Docling's `recognize()` exposes only ITEM-level bbox+text, never per-word
geometry -- so a scrambled multi-line item cannot be re-sorted internally
by its own bboxes. What it CAN be compared against is EasyOCR's raw
tokens landing in the same region: EasyOCR detects per-line (not
per-paragraph) so it doesn't merge across physical lines the way
Docling's item grouping does here.

Reconstruction candidate: cluster EasyOCR tokens overlapping a suspect
Docling element into physical lines (by mutual y-overlap, not a naive
(y0,x0) tuple sort -- two tokens on the same line can have y0 values a
few px apart, which a raw tuple sort gets wrong, see hc_scan_vi's own
"cong no / phai / thu tai..." line below), sort tokens within a line by
x0, sort lines by mean y, and join.

Signal: word-Jaccard agreement (assess_ocr_agreement) is order-
insensitive BY DESIGN -- experiment 015 already established this cannot
catch pure reordering. This script tests a SEPARATE, order-sensitive
signal instead: map each word of Docling's sequence to its position in
the reconstruction's sequence (first unused occurrence), and compute the
normalized length of the Longest Increasing Subsequence (LIS) of that
index mapping. Two sequences with the same words in the same order have
LIS ratio 1.0; heavily reordered sequences score much lower. Cheap
(O(n log n)), deterministic, no model.

    python experiments/018_bottleneck_discovery/word_order_recovery.py --device cuda
"""
from __future__ import annotations

import bisect
import re
import sys
import unicodedata
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))


def words(s: str) -> list[str]:
    s = unicodedata.normalize("NFC", s).lower()
    return [w for w in re.split(r"[^0-9a-zà-ỹăâđêôơư]+", s, flags=re.I) if w]


def word_jaccard(a: str, b: str) -> float:
    wa, wb = set(words(a)), set(words(b))
    return len(wa & wb) / len(wa | wb) if (wa or wb) else 1.0


def lis_length(seq: list[int]) -> int:
    """Standard O(n log n) longest increasing subsequence length."""
    tails: list[int] = []
    for x in seq:
        i = bisect.bisect_left(tails, x)
        if i == len(tails):
            tails.append(x)
        else:
            tails[i] = x
    return len(tails)


def order_consistency(a_text: str, b_text: str) -> float:
    """Normalized LIS ratio: maps each word of `a` (in its own emitted
    order) to the position of its first unused match in `b`, then scores
    how much of that index sequence is already increasing. 1.0 = same
    order; low = same words, different order (this is what word-Jaccard
    cannot see -- it does not look at position at all)."""
    a_words, b_words = words(a_text), words(b_text)
    if not a_words:
        return 1.0
    used = [False] * len(b_words)
    positions: list[int] = []
    for w in a_words:
        for j, bw in enumerate(b_words):
            if bw == w and not used[j]:
                used[j] = True
                positions.append(j)
                break
    if not positions:
        return 0.0
    return lis_length(positions) / len(a_words)


def line_cluster_reconstruction(tokens, region_bbox, y_overlap_min: float = 0.3) -> str:
    """Group tokens overlapping `region_bbox` into physical lines by
    mutual y-overlap (single-linkage), sort each line left-to-right, sort
    lines top-to-bottom, join. `tokens` is any object with `.text`/`.bbox`
    (OCRToken-shaped)."""
    def center_in(inner, outer) -> bool:
        cx, cy = (inner.x0 + inner.x1) / 2, (inner.y0 + inner.y1) / 2
        return outer.x0 <= cx <= outer.x1 and outer.y0 <= cy <= outer.y1

    def y_overlap(a, b) -> float:
        inter = max(0.0, min(a.y1, b.y1) - max(a.y0, b.y0))
        shorter = min(max(1e-6, a.y1 - a.y0), max(1e-6, b.y1 - b.y0))
        return inter / shorter

    matched = [t for t in tokens if center_in(t.bbox, region_bbox)]
    remaining = list(matched)
    lines: list[list] = []
    while remaining:
        cluster = [remaining.pop(0)]
        changed = True
        while changed:
            changed = False
            still = []
            for t in remaining:
                if any(y_overlap(t.bbox, m.bbox) >= y_overlap_min for m in cluster):
                    cluster.append(t)
                    changed = True
                else:
                    still.append(t)
            remaining = still
        lines.append(cluster)
    lines.sort(key=lambda ln: sum(t.bbox.y0 for t in ln) / len(ln))
    parts = []
    for ln in lines:
        ln.sort(key=lambda t: t.bbox.x0)
        parts.append(" ".join(t.text for t in ln if t.text))
    return " ".join(parts).strip()


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default="cuda")
    args = ap.parse_args()

    from doc_extraction.backends.docling_backend import DoclingBackend
    from doc_extraction.backends.easyocr_backend import EasyOCRBackend
    from doc_extraction.pipelines.base import PageInput

    IMAGES = {
        "hc_scan_vi": "/tmp/claude-1002/-home-leanhkhoa150204/53135489-765a-4c07-8a55-7b281fb97758/scratchpad/scan_failure_boundary_016/hc_scan_vi-55bd89b9/rendered/page-001.png",
        "hc_scan_en": "/tmp/claude-1002/-home-leanhkhoa150204/53135489-765a-4c07-8a55-7b281fb97758/scratchpad/scan_failure_boundary_016/hc_scan_en-94c7b3ec/rendered/page-001.png",
        "cmb_scan_multicol_en": "/tmp/claude-1002/-home-leanhkhoa150204/53135489-765a-4c07-8a55-7b281fb97758/scratchpad/scan_failure_boundary_016/cmb_scan_multicol_en-a04e841f/rendered/page-001.png",
    }

    docling = DoclingBackend(device=args.device, ocr_languages=["en", "vi"])
    easyocr = EasyOCRBackend(device=args.device, languages=["en", "vi"])

    from PIL import Image

    for name, img_str in IMAGES.items():
        img_path = Path(img_str)
        with Image.open(img_path) as im:
            w, h = im.size
        pi = PageInput(page_index=0, width=float(w), height=float(h), image_path=img_path, dpi=200)

        d_result = docling.recognize(pi)
        e_result = easyocr.recognize(pi)

        print(f"\n=== {name} ===")
        for i, tok in enumerate(d_result.tokens):
            recon = line_cluster_reconstruction(e_result.tokens, tok.bbox)
            if not recon:
                continue
            jac = word_jaccard(tok.text, recon)
            order = order_consistency(tok.text, recon)
            exact = " ".join(unicodedata.normalize("NFC", recon).split()) == \
                    " ".join(unicodedata.normalize("NFC", tok.text).split())
            flag = " <-- ORDER-INCONSISTENT (would trigger REORDER)" if (jac > 0.7 and order < 0.85) else ""
            print(f"  item {i}: jaccard={jac:.3f} order_consistency={order:.3f}{flag}")
            print(f"    docling:        {tok.text!r}")
            print(f"    reconstruction: {recon!r}")
            print(f"    reconstruction == docling (post-normalize)? {exact}")


if __name__ == "__main__":
    main()
