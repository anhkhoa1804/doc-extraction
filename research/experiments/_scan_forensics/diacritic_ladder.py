"""Is `cmb_scan_tiny_vi` a tiny-text failure, or a Vietnamese-diacritic failure?

`cmb_scan_tiny_vi` is the production corpus's only 0.00-recall document and
the failure class with no recovery progress across milestones 014/015/018.
It is labelled `T-TINY` ("text below what the render DPI resolves"), and
every recovery attempt so far has followed from that label: higher global
DPI (300/400/600) and targeted 600-DPI region crops, all in
`recovery_dpi.py`, all failed -- 600 DPI scored *worse* than the 200 DPI
baseline.

That pattern is not what a resolution limit looks like. This script tests
the competing hypothesis: the text is read, and what fails is character
recovery -- specifically Vietnamese diacritics.

Method: a *normalization ladder*. Each rung folds away exactly one
hypothesised cause, cumulatively, and rescores. The rung where recall jumps
is the rung that owns the failure. If recall is 0.00 raw but high once
diacritics are folded, the content was present and the label is wrong.

`--fresh` re-renders and re-OCRs from the corpus PDF (GPU preflight is the
caller's responsibility); the default reads the text recorded by
`ocr_unbundle.py` so the ladder can be rerun with no GPU.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "src"))
CORPUS = REPO / "research/production_corpus/corpus"
DOC = "cmb_scan_tiny_vi"


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def collapse_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def strip_diacritics(s: str) -> str:
    """Remove combining marks; map Vietnamese đ/Đ (a distinct letter) to d/D."""
    s = s.replace("đ", "d").replace("Đ", "D")
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if not unicodedata.combining(c))


# Glyph pairs an OCR recognizer confuses at small sizes, folded to one form.
CONFUSABLE = str.maketrans({"l": "i", "1": "i", "I": "i", "|": "i",
                            "0": "o", "O": "o", "5": "s", "8": "b"})


def strip_punct(s: str) -> str:
    return re.sub(r"[^0-9a-zA-ZÀ-ỹ\s]+", "", s)


RUNGS = [
    ("raw", lambda s: s),
    ("+NFC", nfc),
    ("+casefold", lambda s: nfc(s).lower()),
    ("+whitespace", lambda s: collapse_ws(nfc(s).lower())),
    ("+punctuation", lambda s: collapse_ws(strip_punct(nfc(s).lower()))),
    ("+diacritics",
     lambda s: collapse_ws(strip_punct(strip_diacritics(nfc(s).lower())))),
    ("+confusables",
     lambda s: collapse_ws(strip_punct(strip_diacritics(nfc(s).lower()))
                           .translate(CONFUSABLE))),
]


def words(s: str) -> list[str]:
    return [w for w in re.split(r"\s+", s) if w]


def score(text: str, must: list[str], fn):
    t = fn(text)
    tw = set(words(t))
    hits = [fn(m) in t for m in must]
    wr = []
    for m in must:
        mw = words(fn(m))
        wr.append(sum(1 for w in mw if w in tw) / len(mw) if mw else 0.0)
    return sum(hits) / len(must), sum(wr) / len(wr), hits


def ladder(label: str, text: str, must: list[str]) -> dict:
    print(f"=== {label} ===")
    print(f"    {len(text)} chars: {text[:100]}...")
    print(f"    {'rung':<16}{'exact':>8}{'word':>8}   hits")
    out = {}
    for name, fn in RUNGS:
        ex, wr, hits = score(text, must, fn)
        out[name] = {"exact": round(ex, 4), "word": round(wr, 4), "hits": hits}
        print(f"    {name:<16}{ex:>8.3f}{wr:>8.3f}   "
              + " ".join("Y" if h else "." for h in hits))
    print()
    return out


def fresh_ocr(device: str, dpi: int) -> str:
    """Re-render the corpus PDF and read it with EasyOCR (vi+en) directly."""
    import tempfile

    import easyocr

    from doc_extraction.stages.render import render_single_pdf_page

    out = Path(tempfile.mkdtemp(prefix="diacritic_ladder_"))
    img = render_single_pdf_page(CORPUS / f"{DOC}.pdf", 0, out, dpi)
    reader = easyocr.Reader(["vi", "en"], gpu=(device == "cuda"), verbose=False)
    return " ".join(d[1] for d in reader.readtext(str(img)))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fresh", action="store_true",
                    help="re-render + re-OCR instead of reading recorded text")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--dpi", type=int, default=200)
    ap.add_argument("--json", type=Path,
                    default=Path(__file__).parent / "diacritic_ladder.json")
    args = ap.parse_args()

    recorded = json.loads(
        (Path(__file__).parent / "ocr_unbundle.json").read_text())
    entry = next(e for e in recorded["results"] if e["document"] == DOC)
    must = entry["must_contain"]

    print(f"document : {DOC}")
    print(f"must_contain ({len(must)}):")
    for m in must:
        print(f"    - {m}")
    print()

    results = {"document": DOC, "must_contain": must, "source": "recorded",
               "ladders": {}}
    for backend in ("docling", "easyocr"):
        results["ladders"][backend] = ladder(
            f"{backend} (recorded, dpi={recorded['dpi']})",
            entry[backend]["text"], must)

    if args.fresh:
        text = fresh_ocr(args.device, args.dpi)
        results["source"] = "fresh"
        results["fresh_device"] = args.device
        results["fresh_dpi"] = args.dpi
        results["fresh_text"] = text
        results["ladders"]["easyocr_fresh"] = ladder(
            f"easyocr (FRESH, device={args.device}, dpi={args.dpi})",
            text, must)

    args.json.write_text(json.dumps(results, indent=1, ensure_ascii=False))
    print(f"wrote {args.json}")


if __name__ == "__main__":
    main()
