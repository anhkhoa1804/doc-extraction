#!/usr/bin/env python
"""E11 — what render DPI does small text actually need, and what does it cost?

The question
------------
`render_dpi: 200` is the shipped default and, as far as the repository records
show, was never derived from a measurement. Small print is where that choice
bites: legal fine print, footnotes and dense invoice cells are routinely 4-6pt,
and at 200 DPI a 4pt glyph is roughly 11 pixels tall — near the floor of what a
recognizer can resolve.

Rendering everything at 600 DPI would fix it and cost ~9x the pixels (and
therefore roughly that much OCR time and memory). The production question is
not "which DPI is best" but:

    is a targeted second pass on the small-text region cheaper than
    globally raising DPI, for the same recovery?

That is the cheapest-first recovery ladder (§30) stated as a measurement.

What this measures
------------------
For a page containing text at several point sizes, at each DPI:

* pixels rendered and render time  — the cost that scales
* per-glyph pixel height           — the physical quantity that determines
                                     whether recognition is even possible
* crop cost                        — what a targeted region pass would cost
                                     instead of a full-page re-render

Deliberately *not* measured here: OCR accuracy. Running EasyOCR at four DPIs
over several pages is a model-heavy job, and on a shared GPU-protected machine
it is the expensive half. The geometry below is device-independent, costs
seconds, and is enough to size the decision — a crop that is 3% of the page
area cannot cost more than a full-page render at the same DPI, whatever the
recognizer does with it. The accuracy half is left as a follow-up with its
command recorded.

    python research/experiments/dpi_recovery.py
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import pymupdf

REPO_ROOT = Path(__file__).resolve().parents[2]

# Point sizes spanning the range real enterprise documents use, from body text
# down to the fine print this experiment exists for.
FONT_SIZES = (12, 8, 6, 4)
DPIS = (150, 200, 300, 400, 600)

# Rough floor for reliable recognition of Latin/Vietnamese glyphs. Vietnamese
# matters here specifically: its diacritics sit above the x-height and are the
# first thing lost when a glyph is under-resolved, so a size that is marginal
# for English is already failing for Vietnamese.
MIN_GLYPH_PX_RELIABLE = 20
MIN_GLYPH_PX_MARGINAL = 12

VN_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def build_probe(path: Path) -> dict:
    """A page with the same sentence at several sizes, so size is the only
    variable. Includes Vietnamese diacritics on purpose."""
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    regions = {}
    y = 80
    for size in FONT_SIZES:
        text = f"[{size}pt] Phí dịch vụ 2.500.000 đồng - late interest 1.5% per month"
        page.insert_text((50, y), text, fontsize=size, fontfile=VN_FONT, fontname="dv")
        # Region a targeted second pass would crop, with a little padding.
        regions[size] = (45, y - size - 2, 550, y + 4)
        y += size * 3 + 18
    doc.subset_fonts()
    doc.save(path, garbage=4, deflate=True)
    doc.close()
    return regions


def measure(path: Path, regions: dict) -> list[dict]:
    doc = pymupdf.open(path)
    page = doc[0]
    rows: list[dict] = []
    for dpi in DPIS:
        zoom = dpi / 72.0
        matrix = pymupdf.Matrix(zoom, zoom)

        started = time.perf_counter()
        pixmap = page.get_pixmap(matrix=matrix)
        full_render_s = time.perf_counter() - started
        full_px = pixmap.width * pixmap.height
        full_bytes = len(pixmap.samples)

        for size, rect in regions.items():
            glyph_px = size * zoom          # cap height in device pixels
            clip = pymupdf.Rect(*rect)

            started = time.perf_counter()
            crop = page.get_pixmap(matrix=matrix, clip=clip)
            crop_render_s = time.perf_counter() - started
            crop_px = crop.width * crop.height

            rows.append({
                "dpi": dpi,
                "font_pt": size,
                "glyph_px": round(glyph_px, 1),
                "legible": ("reliable" if glyph_px >= MIN_GLYPH_PX_RELIABLE
                            else "marginal" if glyph_px >= MIN_GLYPH_PX_MARGINAL
                            else "below-floor"),
                "full_page_px": full_px,
                "full_page_mb": round(full_bytes / 2**20, 2),
                "full_render_s": round(full_render_s, 4),
                "crop_px": crop_px,
                "crop_render_s": round(crop_render_s, 4),
                "crop_fraction_of_page": round(crop_px / full_px, 4),
            })
    doc.close()
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    work = Path(args.out) if args.out else REPO_ROOT / "research" / "experiments" / "_dpi"
    work.mkdir(parents=True, exist_ok=True)
    probe = work / "dpi_probe.pdf"
    regions = build_probe(probe)
    rows = measure(probe, regions)

    print("Glyph height in pixels by DPI and font size")
    print(f"{'pt':>5s}" + "".join(f"{d:>12d}" for d in DPIS))
    print("-" * (5 + 12 * len(DPIS)))
    for size in FONT_SIZES:
        cells = ""
        for dpi in DPIS:
            r = next(x for x in rows if x["dpi"] == dpi and x["font_pt"] == size)
            tag = {"reliable": " ", "marginal": "~", "below-floor": "!"}[r["legible"]]
            cells += f"{r['glyph_px']:>11.1f}{tag}"
        print(f"{size:>5d}{cells}")
    print(f"\n  reliable >= {MIN_GLYPH_PX_RELIABLE}px    ~ marginal >= {MIN_GLYPH_PX_MARGINAL}px"
          f"    ! below floor")

    print("\nCost of a full-page render vs a targeted crop of the 4pt line")
    print(f"{'dpi':>5s}{'page Mpx':>11s}{'page MB':>10s}{'render s':>10s}"
          f"{'crop Mpx':>11s}{'crop s':>9s}{'crop % page':>13s}")
    print("-" * 69)
    for dpi in DPIS:
        r = next(x for x in rows if x["dpi"] == dpi and x["font_pt"] == 4)
        print(f"{dpi:>5d}{r['full_page_px']/1e6:>11.2f}{r['full_page_mb']:>10.2f}"
              f"{r['full_render_s']:>10.4f}{r['crop_px']/1e6:>11.3f}"
              f"{r['crop_render_s']:>9.4f}{r['crop_fraction_of_page']:>12.1%}")

    # The decision this experiment exists to inform.
    r200 = next(x for x in rows if x["dpi"] == 200 and x["font_pt"] == 4)
    r600 = next(x for x in rows if x["dpi"] == 600 and x["font_pt"] == 4)
    global_cost = r600["full_page_px"] / r200["full_page_px"]
    targeted_cost = (r200["full_page_px"] + r600["crop_px"]) / r200["full_page_px"]
    print(f"\nTo bring 4pt text from {r200['glyph_px']:.0f}px to {r600['glyph_px']:.0f}px:")
    print(f"  raise DPI globally 200 -> 600 : {global_cost:.2f}x the pixels of a 200 DPI page")
    print(f"  keep 200 DPI + 600 DPI crop   : {targeted_cost:.2f}x")
    print(f"  targeted pass is {global_cost/targeted_cost:.1f}x cheaper for the same glyph size")

    out_json = work / "results.json"
    out_json.write_text(json.dumps({
        "font_sizes": list(FONT_SIZES), "dpis": list(DPIS),
        "min_glyph_px_reliable": MIN_GLYPH_PX_RELIABLE,
        "min_glyph_px_marginal": MIN_GLYPH_PX_MARGINAL,
        "rows": rows,
        "conclusion": {
            "global_600dpi_cost_x": round(global_cost, 3),
            "targeted_crop_cost_x": round(targeted_cost, 3),
            "targeted_cheaper_by_x": round(global_cost / targeted_cost, 2),
        },
    }, indent=2), encoding="utf-8")
    print(f"\n-> {out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
