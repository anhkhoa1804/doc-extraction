"""Phases 17-18 — does targeted high-DPI recovery rescue `cmb_scan_tiny_vi`?

Why re-run this
---------------
`research/experiments/_recovery` asked the same question and returned 0% in
all three arms, including full-page 600 DPI. Experiment 008 §6 established
that the result was invalidated by a coordinate-space defect underneath it,
not by the hypothesis being wrong, and recorded that the DPI question should
be re-run once the path worked. It also noted a second limitation: that
probe's baseline already scored 1.00, so it could not demonstrate *rescue* at
all — only that the global alternative regressed.

`cmb_scan_tiny_vi` is the case that fixes both problems. It is the corpus's
one genuine total failure (recall 0.00), it is a compound case — no text layer
*and* 4.5 pt body — and the coordinate defect is fixed.

Arms
----
    baseline_200     the shipped default
    global_300/400/600   raise render DPI for the whole page
    targeted_600     detect regions at 200, crop each at 600, read the crops

Measured per arm: recall (exact and word-level), megapixels rendered, layout
and OCR seconds, and peak VRAM where a GPU is used. Pixels are reported
because they are what the cost scales with, and the whole argument for
targeting is that a crop is a small fraction of a page.
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
               "17350d12-6add-4719-8ecd-40b53c80d434/scratchpad/recovery")


def words(s: str) -> list[str]:
    s = unicodedata.normalize("NFC", s).lower()
    return [w for w in re.split(r"[^0-9a-zà-ỹăâđêôơư]+", s, flags=re.I) if w]


def norm(s: str) -> str:
    return " ".join(unicodedata.normalize("NFC", s or "").split()).lower()


def score(text: str, must: list[str]) -> dict:
    tw = set(words(text))
    exact = sum(1 for s in must if norm(s) in norm(text))
    wr = []
    for s in must:
        sw = words(s)
        wr.append(sum(1 for w in sw if w in tw) / len(sw) if sw else 0.0)
    return {"exact_recall": round(exact / len(must), 4) if must else 0.0,
            "word_recall": round(sum(wr) / len(wr), 4) if wr else 0.0,
            "per_string": [{"string": s, "word_recall": round(r, 3)}
                           for s, r in zip(must, wr)]}


def gpu_peak_mib() -> int | None:
    try:
        import torch
        if torch.cuda.is_available():
            return int(torch.cuda.max_memory_allocated() / (1024 * 1024))
    except Exception:  # noqa: BLE001 - measurement only
        return None
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc", default="cmb_scan_tiny_vi")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--json", type=Path,
                    default=Path(__file__).parent / "recovery_dpi.json")
    args = ap.parse_args()

    import pymupdf
    from PIL import Image

    from doc_extraction.backends.docling_backend import DoclingBackend
    from doc_extraction.pipelines.base import PageInput

    manifest = json.loads((CORPUS / "manifest.json").read_text())
    meta = next(d for d in manifest["documents_list"] if d["document_id"] == args.doc)
    src = CORPUS / meta["filename"]
    must = meta["must_contain"]
    SCRATCH.mkdir(parents=True, exist_ok=True)

    backend = DoclingBackend(device=args.device, ocr_languages=["en", "vi"])
    print(f"{args.doc}: {len(must)} expected strings, device={args.device}")
    print(f"docling available: {backend.is_available()}\n")

    pdf = pymupdf.open(src)
    page = pdf[0]
    pw, ph = page.rect.width, page.rect.height
    pdf.close()

    def render(dpi: int, clip=None, tag: str = "") -> Path:
        d = pymupdf.open(src)
        zoom = dpi / 72.0
        pix = d[0].get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), clip=clip)
        out = SCRATCH / f"{args.doc}_{tag or dpi}.png"
        pix.save(out)
        d.close()
        return out

    def read(img: Path, w: float, h: float, dpi: int) -> tuple[str, dict, int]:
        pi = PageInput(page_index=0, width=w, height=h, image_path=img,
                       dpi=dpi, source_pdf_path=None)
        t0 = time.perf_counter()
        layout = backend.analyze(pi)
        t_layout = time.perf_counter() - t0
        t0 = time.perf_counter()
        ocr = backend.recognize(pi)
        t_ocr = time.perf_counter() - t0
        text = " ".join(tok.text for tok in ocr.tokens)
        with Image.open(img) as im:
            mp = im.size[0] * im.size[1] / 1e6
        return text, {"layout_s": round(t_layout, 2), "ocr_s": round(t_ocr, 2),
                      "megapixels": round(mp, 3), "n_regions": len(layout.regions),
                      "n_tokens": len(ocr.tokens),
                      "region_labels": sorted({r.label for r in layout.regions})}, len(layout.regions)

    arms: dict[str, dict] = {}

    # ---- global DPI sweep ------------------------------------------------
    for dpi in (200, 300, 400, 600):
        img = render(dpi)
        text, stats, _ = read(img, pw, ph, dpi)
        arms[f"global_{dpi}"] = {**stats, **score(text, must), "text_chars": len(text)}
        print(f"  global_{dpi:<4} regions={stats['n_regions']} "
              f"mp={stats['megapixels']:6.2f} layout={stats['layout_s']:6.2f}s "
              f"exact={arms[f'global_{dpi}']['exact_recall']:.2f} "
              f"word={arms[f'global_{dpi}']['word_recall']:.2f}")

    # ---- targeted: regions found at 200, re-read as 600 DPI crops --------
    base_img = render(200)
    pi = PageInput(page_index=0, width=pw, height=ph, image_path=base_img,
                   dpi=200, source_pdf_path=None)
    base_layout = backend.analyze(pi)
    print(f"\n  targeting {len(base_layout.regions)} region(s) found at 200 DPI")

    t0 = time.perf_counter()
    parts, mp_total = [], 0.0
    for i, r in enumerate(base_layout.regions):
        # Regions come back in the page's own coordinate space (pt here).
        pad = 4.0
        clip = pymupdf.Rect(max(0, r.bbox.x0 - pad), max(0, r.bbox.y0 - pad),
                            min(pw, r.bbox.x1 + pad), min(ph, r.bbox.y1 + pad))
        if clip.width < 2 or clip.height < 2:
            continue
        crop = render(600, clip=clip, tag=f"crop{i}")
        with Image.open(crop) as im:
            mp_total += im.size[0] * im.size[1] / 1e6
        cpi = PageInput(page_index=0, width=clip.width, height=clip.height,
                        image_path=crop, dpi=600, source_pdf_path=None)
        ocr = backend.recognize(cpi)
        parts.append(" ".join(t.text for t in ocr.tokens))
    t_targeted = time.perf_counter() - t0
    text = " ".join(parts)
    arms["targeted_600"] = {
        "layout_s": None, "ocr_s": round(t_targeted, 2),
        "megapixels": round(mp_total, 3),
        "n_regions": len(base_layout.regions), "n_tokens": len(parts),
        "region_labels": sorted({r.label for r in base_layout.regions}),
        **score(text, must), "text_chars": len(text)}
    print(f"  targeted_600 crops={len(parts)} mp={mp_total:6.2f} "
          f"total={t_targeted:6.2f}s exact={arms['targeted_600']['exact_recall']:.2f} "
          f"word={arms['targeted_600']['word_recall']:.2f}")

    peak = gpu_peak_mib()
    print(f"\n{'arm':<16} {'MP':>7} {'layout s':>9} {'ocr s':>7} {'regions':>8} "
          f"{'exact':>6} {'word':>6}")
    print("=" * 70)
    for k, v in arms.items():
        ls = f"{v['layout_s']:.2f}" if v["layout_s"] is not None else "—"
        print(f"{k:<16} {v['megapixels']:7.2f} {ls:>9} {v['ocr_s']:7.2f} "
              f"{v['n_regions']:8d} {v['exact_recall']:6.2f} {v['word_recall']:6.2f}")
    if peak is not None:
        print(f"\npeak VRAM allocated: {peak} MiB")

    print("\nper-string word recall by arm:")
    for i, s in enumerate(must):
        line = f"  {s[:40]!r:44}"
        for k, v in arms.items():
            line += f" {k.split('_')[-1]}={v['per_string'][i]['word_recall']:.2f}"
        print(line)

    args.json.write_text(json.dumps(
        {"document": args.doc, "device": args.device, "must_contain": must,
         "page_pt": [pw, ph], "peak_vram_mib": peak, "arms": arms},
        ensure_ascii=False, indent=2))
    print(f"\nwrote {args.json}")


if __name__ == "__main__":
    main()
