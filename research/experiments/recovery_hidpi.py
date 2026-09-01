#!/usr/bin/env python
"""E7 prototype — targeted high-DPI recovery for text that 200 DPI cannot resolve.

Hypothesis
----------
From E11 (`dpi_recovery.py`): at the shipped `render_dpi: 200`, a 4pt glyph is
~11 device pixels tall, below the floor for reliable recognition, and a 5pt
glyph is ~14px — marginal. From E3 (`run_benchmark.py`): the visual route
scores **0%** on `tiny_cells_table`, whose cells are 5pt.

Those two results predict each other, which is what makes the mechanism
credible rather than coincidental. So:

    A page whose small text is unreadable at 200 DPI should be recoverable by
    re-rendering ONLY the affected regions at high DPI, at a fraction of the
    cost of rendering the whole page that way (E11 measured 8.2x cheaper).

Why this needs a rasterized fixture
-----------------------------------
On the born-digital `tiny_cells_table.pdf` the *native* route already recovers
everything — the text layer is perfect and the router correctly never renders
it. That is the right production behaviour and it makes the file useless for
testing a visual-route recovery action.

So this experiment rasterizes the page first, producing a document with no text
layer at all. That is the honest analogue of a scanned invoice, and it is the
only condition under which high-DPI recovery is the *only* option rather than
an expensive way to reproduce what the text layer already had.

What is measured
----------------
Three arms over the same rasterized page:

* ``baseline_200``  — render the whole page at 200 DPI, OCR it.
* ``global_600``    — render the whole page at 600 DPI, OCR it.
* ``targeted_600``  — render at 200 DPI, then re-render only the small-text
                      region at 600 DPI and OCR that crop as well.

for recall of the known strings, wall time, and pixels processed.

    python research/experiments/recovery_hidpi.py
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import pymupdf

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from doc_extraction.backends.docling_backend import DoclingBackend  # noqa: E402
from doc_extraction.config import configure_caches  # noqa: E402
from doc_extraction.pipelines.base import PageInput  # noqa: E402

# Strings known to be on the page (drawn at 5pt by the corpus generator).
TARGETS = ["SKU-1001", "SKU-1005", "Mô tả", "Sản phẩm 1"]


@dataclass
class Arm:
    name: str
    recall: float
    found: list[str]
    missing: list[str]
    seconds: float
    megapixels: float
    ocr_chars: int


def _norm(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def rasterize(src: Path, dst: Path, dpi: int = 200) -> Path:
    """Render the PDF to an image-only PDF: no text layer survives.

    This is what a scanner produces, and what the visual route must cope with
    when there is nothing cheaper available.
    """
    doc = pymupdf.open(src)
    out = pymupdf.open()
    zoom = dpi / 72.0
    for page in doc:
        pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
        new = out.new_page(width=page.rect.width, height=page.rect.height)
        new.insert_image(new.rect, pixmap=pix)
    out.save(dst, garbage=4, deflate=True)
    out.close(); doc.close()
    return dst


def render_region(pdf: Path, page_index: int, dpi: int, out_png: Path,
                  clip: pymupdf.Rect | None = None) -> tuple[Path, float]:
    doc = pymupdf.open(pdf)
    zoom = dpi / 72.0
    pix = doc[page_index].get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), clip=clip)
    pix.save(out_png)
    mp = (pix.width * pix.height) / 1e6
    doc.close()
    return out_png, mp


def ocr_text(backend: DoclingBackend, image: Path, dpi: int) -> str:
    from PIL import Image
    with Image.open(image) as im:
        w, h = im.size
    result = backend.recognize(PageInput(page_index=0, width=w, height=h,
                                         image_path=image, dpi=dpi))
    return _norm(" ".join(t.text for t in result.tokens if t.text))


def score(name: str, text: str, seconds: float, megapixels: float) -> Arm:
    found = [t for t in TARGETS if _norm(t) in text]
    missing = [t for t in TARGETS if _norm(t) not in text]
    return Arm(name=name, recall=len(found) / len(TARGETS), found=found,
               missing=missing, seconds=round(seconds, 2),
               megapixels=round(megapixels, 3), ocr_chars=len(text))


def small_text_regions(source_pdf: Path, max_pt: float = 6.0) -> list[tuple[float, float, float, float]]:
    """Find regions whose text is too small to survive a 200 DPI render.

    Uses the *source* document's font sizes. In production this signal comes
    either from the text layer (born-digital) or from layout/OCR confidence on
    a scan; here the point is to show that a cheap signal is sufficient to aim
    the expensive pass, not to solve detection.
    """
    doc = pymupdf.open(source_pdf)
    boxes: list[tuple[float, float, float, float]] = []
    for page in doc:
        for block in page.get_text("dict")["blocks"]:
            if block.get("type") != 0:
                continue
            sizes = [s["size"] for line in block["lines"] for s in line["spans"]]
            if sizes and min(sizes) <= max_pt:
                boxes.append(tuple(block["bbox"]))
    doc.close()
    # Merge into one region: adjacent small-text blocks are one logical area,
    # and one crop is cheaper than many.
    if not boxes:
        return []
    x0 = min(b[0] for b in boxes); y0 = min(b[1] for b in boxes)
    x1 = max(b[2] for b in boxes); y1 = max(b[3] for b in boxes)
    pad = 4
    return [(x0 - pad, y0 - pad, x1 + pad, y1 + pad)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", default=str(REPO_ROOT / "research" / "hardcases" /
                                                "corpus" / "tiny_cells_table.pdf"))
    parser.add_argument("--work", default=str(REPO_ROOT / "research" / "experiments" / "_recovery"))
    parser.add_argument("--hidpi", type=int, default=600)
    args = parser.parse_args(argv)

    configure_caches(".cache")
    source = Path(args.source)
    work = Path(args.work); work.mkdir(parents=True, exist_ok=True)

    regions = small_text_regions(source)
    print(f"small-text regions detected in source: {len(regions)}")
    if not regions:
        print("no small text found — nothing for this experiment to recover")
        return 1

    scanned = rasterize(source, work / "scanned.pdf", dpi=200)
    print(f"rasterized to an image-only PDF: {scanned.name}")
    with pymupdf.open(scanned) as d:
        has_text = bool(d[0].get_text().strip())
    print(f"text layer present after rasterization: {has_text}  (must be False)")

    backend = DoclingBackend(device="cpu", ocr_languages=["en", "vi"])
    arms: list[Arm] = []

    # Arm 1 — the shipped default.
    t = time.perf_counter()
    png, mp = render_region(scanned, 0, 200, work / "full_200.png")
    text = ocr_text(backend, png, 200)
    arms.append(score("baseline_200", text, time.perf_counter() - t, mp))

    # Arm 2 — brute force: everything at high DPI.
    t = time.perf_counter()
    png, mp = render_region(scanned, 0, args.hidpi, work / f"full_{args.hidpi}.png")
    text = ocr_text(backend, png, args.hidpi)
    arms.append(score(f"global_{args.hidpi}", text, time.perf_counter() - t, mp))

    # Arm 3 — cheapest-first recovery: 200 DPI page, then a high-DPI crop.
    t = time.perf_counter()
    png_full, mp_full = render_region(scanned, 0, 200, work / "t_full_200.png")
    text_full = ocr_text(backend, png_full, 200)
    clip = pymupdf.Rect(*regions[0])
    png_crop, mp_crop = render_region(scanned, 0, args.hidpi, work / "t_crop_hi.png", clip=clip)
    text_crop = ocr_text(backend, png_crop, args.hidpi)
    combined = _norm(text_full + " " + text_crop)
    arms.append(score(f"targeted_{args.hidpi}", combined,
                      time.perf_counter() - t, mp_full + mp_crop))

    print(f"\n{'arm':>16s}{'recall':>9s}{'seconds':>10s}{'Mpx':>9s}{'chars':>8s}  missing")
    print("-" * 78)
    for a in arms:
        print(f"{a.name:>16s}{a.recall:>8.0%}{a.seconds:>10.2f}{a.megapixels:>9.2f}"
              f"{a.ocr_chars:>8d}  {a.missing}")

    base, glob, targ = arms
    print(f"\nrecall  : {base.recall:.0%} -> global {glob.recall:.0%} / targeted {targ.recall:.0%}")
    if base.seconds:
        print(f"cost    : global {glob.seconds/base.seconds:.2f}x baseline time, "
              f"targeted {targ.seconds/base.seconds:.2f}x")
    if glob.recall and targ.recall >= glob.recall and targ.seconds < glob.seconds:
        print("verdict : targeted recovery matches global high-DPI at lower cost")
    elif targ.recall > base.recall:
        print("verdict : targeted recovery improves on the baseline")
    else:
        print("verdict : targeted recovery did NOT help — negative result")

    (work / "results.json").write_text(json.dumps({
        "source": str(source.relative_to(REPO_ROOT)),
        "hidpi": args.hidpi, "targets": TARGETS,
        "regions": regions,
        "arms": [a.__dict__ for a in arms],
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n-> {work / 'results.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
