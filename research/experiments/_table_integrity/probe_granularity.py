"""Phase 5 — what is the strongest reliable unit of text ownership?

Three candidate granularities, measured on the same tables rather than argued
about:

  span      the PyMuPDF span, as the current fix uses. Safe against
            interleaving, but a span is not always one drawing operation:
            two adjacent `insert_text` calls sharing a baseline are merged
            into one span, so a span can straddle a cell boundary
            legitimately.

  char      individual characters, assigned by centre. Finest possible, and
            exactly how the original bug happened: characters from an overlay
            and characters from a cell interleave by x-position.

  subrun    a span cut at *advance discontinuities* — points where the next
            character's box starts before the previous one's ends (two draw
            calls merged), or after an abnormal gap. This is the hypothesis:
            it recovers the true drawing operations without ever mixing two
            of them.

The discontinuity test comes from measured geometry. In `ord_invoice_vi` the
header span is 'Số lượngThành tiền' with chars:

    'g'  x=[337.85, 344.29]
    'T'  x=[342.00, 348.14]      <- starts 2.29pt BEFORE 'g' ends

A genuine single run advances monotonically; overlapping advance boxes mean
two runs were merged. The cell boundary sits at x=340, between them.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pymupdf

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "src"))

CORPUS = REPO / "research/production_corpus/corpus"

# A character whose box starts more than this far before the previous
# character's box ends is not a continuation — the two were drawn separately.
OVERLAP_TOL = 0.5
# A gap larger than this multiple of the font size is also a break. A normal
# inter-word space is ~0.35 em; 1.2 em is comfortably past any real space.
GAP_EM = 1.2


def split_subruns(span: dict) -> list[dict]:
    """Cut one span into maximal monotonically-advancing character sequences."""
    chars = span.get("chars", [])
    if not chars:
        return []
    size = span.get("size", 9.0) or 9.0
    groups: list[list[dict]] = [[chars[0]]]
    for prev, cur in zip(chars, chars[1:]):
        overlap = cur["bbox"][0] < prev["bbox"][2] - OVERLAP_TOL
        gap = cur["bbox"][0] - prev["bbox"][2] > GAP_EM * size
        # A newline / baseline change also breaks a run.
        newline = abs(cur["origin"][1] - prev["origin"][1]) > 0.5
        if overlap or gap or newline:
            groups.append([cur])
        else:
            groups[-1].append(cur)
    out = []
    for g in groups:
        text = "".join(c["c"] for c in g)
        if not text.strip():
            continue
        out.append({
            "text": text,
            "bbox": (min(c["bbox"][0] for c in g), min(c["bbox"][1] for c in g),
                     max(c["bbox"][2] for c in g), max(c["bbox"][3] for c in g)),
            "size": span.get("size"), "color": span.get("color"),
            "chars": g,
        })
    return out


def units(page, granularity: str) -> list[dict]:
    raw = page.get_text("rawdict")
    out: list[dict] = []
    for b in raw.get("blocks", []):
        for line in b.get("lines", []):
            for s in line.get("spans", []):
                chars = s.get("chars", [])
                text = "".join(c["c"] for c in chars)
                if not text.strip():
                    continue
                if granularity == "span":
                    out.append({"text": text, "bbox": tuple(s["bbox"]),
                                "size": s.get("size"), "color": s.get("color")})
                elif granularity == "char":
                    for c in chars:
                        if c["c"].strip():
                            out.append({"text": c["c"], "bbox": tuple(c["bbox"]),
                                        "size": s.get("size"), "color": s.get("color")})
                elif granularity == "subrun":
                    out.extend(split_subruns(s))
    return out


def containment(box, cell) -> float:
    ix = max(0.0, min(box[2], cell[2]) - max(box[0], cell[0]))
    iy = max(0.0, min(box[3], cell[3]) - max(box[1], cell[1]))
    a = max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])
    return (ix * iy) / a if a > 0 else 0.0


def assign(cell_boxes: dict, us: list[dict]) -> dict:
    """Give each unit to its best-containing cell; order by run, then position."""
    owned: dict = {}
    for i, u in enumerate(us):
        best, frac = None, 0.0
        for pos, cb in cell_boxes.items():
            f = containment(u["bbox"], cb)
            if f > frac:
                best, frac = pos, f
        if best is not None and frac > 0.0:
            owned.setdefault(best, []).append((i, u))
    grid = {}
    for pos, items in owned.items():
        items.sort(key=lambda t: (round(t[1]["bbox"][1], 1), t[1]["bbox"][0], t[0]))
        # Characters from the same source unit stay adjacent by construction
        # for span/subrun; for char granularity this is where interleaving
        # becomes possible, which is the point of the comparison.
        grid[pos] = "".join(u["text"] for _, u in items) if len(items[0][1]["text"]) == 1 \
            else " ".join(u["text"].strip() for _, u in items)
    return grid


CASES = {
    "ord_invoice_vi":        [("r0c3", "Số lượng"), ("r0c4", "Thành tiền")],
    "ord_invoice_en":        [("r0c3", "Qty"), ("r0c4", "Amount")],
    "hc_stamp_table_vi":     [("r2c2", "Bộ"), ("r3c2", "Gói")],
    "cmb_stamp_boundary_vi": [("r1c2", "Cái")],
    "hc_merged_en":          [("r1c3", "Qty / Amount")],
}


def main() -> None:
    results = {}
    for name, checks in CASES.items():
        path = CORPUS / f"{name}.pdf"
        if not path.exists():
            continue
        doc = pymupdf.open(path)
        page = doc[0]
        tb = max(page.find_tables().tables, key=lambda t: t.row_count * t.col_count)
        cell_boxes = {(r_i, c_i): tuple(float(v) for v in c)
                      for r_i, row in enumerate(tb.rows)
                      for c_i, c in enumerate(row.cells) if c is not None}
        rec = {}
        for g in ("span", "char", "subrun"):
            grid = assign(cell_boxes, units(page, g))
            rec[g] = {k: grid.get((int(k[1]), int(k[3])), "") for k, _ in checks}
        results[name] = {"expected": dict(checks), **rec}
        doc.close()

    print(f"{'document / cell':<34} {'expected':<22} {'span':<22} {'char':<22} subrun")
    print("=" * 122)
    for name, rec in results.items():
        for cell, want in rec["expected"].items():
            print(f"{name+' '+cell:<34} {want!r:<22} {rec['span'][cell]!r:<22} "
                  f"{rec['char'][cell]!r:<22} {rec['subrun'][cell]!r}")

    print("\nper-granularity exact-match count over the probed cells:")
    for g in ("span", "char", "subrun"):
        ok = sum(1 for rec in results.values()
                 for cell, want in rec["expected"].items()
                 if rec[g][cell].strip() == want)
        total = sum(len(rec["expected"]) for rec in results.values())
        print(f"  {g:<8} {ok}/{total}")

    out = Path(__file__).parent / "phase5_granularity.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
