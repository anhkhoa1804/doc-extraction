"""Why does Tesseract lose on exactly four documents?

Experiment 022 measured Tesseract beating EasyOCR overall while regressing
`hc_rotation_vi` (0.333 -> 0.000), `hc_tiny_cells_vi`, `cmb_tiny_table_en`
and `cmb_lowcontrast_stamp_vi`. The milestone is explicit that these are not
nuisances: if the two engines fail on *disjoint* mechanisms, that
complementarity is the entire argument for adaptive heterogeneous OCR. If
instead Tesseract is simply misconfigured on these pages, the right answer
is to fix the configuration and use one engine.

So each regression is assigned a mechanism, from evidence:

    orientation        fixed by running orientation detection (--psm 0/1)
    layout assumption  fixed by a different page segmentation mode
    tiny text          token count collapses; confidence stays high
    low contrast       token count collapses; confidence also collapses
    segmentation       tokens found but merged/split vs the other engine
    confidence calib.  right answer present but scored below the other

PSM variants are *configuration*, not preprocessing -- no image is
modified, per the milestone's "no preprocessing yet" constraint. Any
preprocessing result here would be diagnosis only and is labelled as such.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "research/production_corpus"))

from doc_extraction.backends.easyocr_backend import EasyOCRBackend  # noqa: E402
from doc_extraction.backends.tesseract_backend import (  # noqa: E402
    TesseractBackend,
    to_tesseract_langs,
)
from doc_extraction.pipelines.base import PageInput  # noqa: E402
from doc_extraction.stages.render import render_single_pdf_page  # noqa: E402

from run_benchmark import _norm  # noqa: E402

CORPUS = REPO / "research/production_corpus/corpus"

REGRESSIONS = ["hc_rotation_vi", "hc_tiny_cells_vi", "cmb_tiny_table_en",
               "cmb_lowcontrast_stamp_vi"]
# Controls: documents where Tesseract won decisively. A mechanism that also
# fires on these is not what distinguishes the regressions.
CONTROLS = ["ord_contract_vi", "hc_scan_vi", "cmb_scan_tiny_vi"]

# 3 = default automatic. 1 = automatic *with* orientation+script detection.
# 4 = single column of variable-size text. 6 = a single uniform block.
PSM_VARIANTS = [3, 1, 4, 6]


def recall(text: str, must: list[str]) -> float:
    n = _norm(text)
    return sum(1 for s in must if _norm(s) in n) / (len(must) or 1)


def tess_run(img: Path, langs: str, psm: int) -> tuple[str, int, float | None]:
    """Returns (text, n_word_tokens, mean_confidence)."""
    txt = subprocess.run(["tesseract", str(img), "stdout", "-l", langs,
                          "--psm", str(psm)], capture_output=True, text=True,
                         check=False).stdout
    tsv = subprocess.run(["tesseract", str(img), "stdout", "-l", langs,
                          "--psm", str(psm), "tsv"], capture_output=True,
                         text=True, check=False).stdout
    toks = TesseractBackend._tokens_from_tsv(tsv)
    confs = [t.confidence for t in toks if t.confidence is not None]
    return txt, len(toks), (sum(confs) / len(confs) if confs else None)


def osd(img: Path) -> dict:
    """Tesseract's own orientation/script detection verdict for the page."""
    proc = subprocess.run(["tesseract", str(img), "stdout", "--psm", "0"],
                          capture_output=True, text=True, check=False)
    out: dict[str, str] = {}
    for line in proc.stdout.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return out or {"error": (proc.stderr or "").strip().splitlines()[-1:] or ["no OSD"]}


def classify(row: dict) -> str:
    """Assign a mechanism from the measured evidence, not from the label."""
    best_psm = row["best_psm"]
    if best_psm["psm"] != 3 and best_psm["recall"] > row["psm_3"]["recall"]:
        rotated = row["osd"].get("Orientation in degrees") not in (None, "0")
        return "orientation" if rotated else "layout assumption"
    e, t3 = row["easyocr"], row["psm_3"]
    if t3["tokens"] < e["tokens"] * 0.6:
        if t3["mean_conf"] is not None and t3["mean_conf"] < 0.6:
            return "low contrast (detection collapses, confidence collapses)"
        return "tiny text (detection collapses, confidence stays high)"
    if t3["recall"] < e["recall"]:
        return "segmentation or confidence calibration (text found, not assembled)"
    return "no regression reproduced at this configuration"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dpi", type=int, default=200)
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--out", type=Path,
                    default=Path(__file__).parent / "regression_analysis.json")
    args = ap.parse_args()

    manifest = json.loads((CORPUS / "manifest.json").read_text())
    by_id = {d["document_id"]: d for d in manifest["documents_list"]}
    langs = to_tesseract_langs(["en", "vi"])
    tmp = Path(tempfile.mkdtemp(prefix="regression_"))
    easy = EasyOCRBackend(device=args.device, languages=["en", "vi"])

    rows = []
    for doc_id in REGRESSIONS + CONTROLS:
        entry = by_id[doc_id]
        must = entry["must_contain"]
        img = render_single_pdf_page(CORPUS / entry["filename"], 0, tmp, args.dpi)

        e_result = easy.recognize(PageInput(page_index=0, width=595, height=842,
                                            image_path=img, dpi=args.dpi))
        e_confs = [t.confidence for t in e_result.tokens if t.confidence is not None]
        e_row = {"recall": round(recall(" ".join(t.text for t in e_result.tokens), must), 4),
                 "tokens": len(e_result.tokens),
                 "mean_conf": round(sum(e_confs) / len(e_confs), 4) if e_confs else None}

        per_psm = {}
        for psm in PSM_VARIANTS:
            txt, n, conf = tess_run(img, langs, psm)
            per_psm[f"psm_{psm}"] = {"psm": psm, "recall": round(recall(txt, must), 4),
                                     "tokens": n,
                                     "mean_conf": round(conf, 4) if conf else None}
        best = max(per_psm.values(), key=lambda r: (r["recall"], r["tokens"]))

        row = {"document_id": doc_id,
               "is_regression": doc_id in REGRESSIONS,
               "labels": entry["hard_case_labels"],
               "language": entry["language"],
               "easyocr": e_row, "osd": osd(img),
               **per_psm, "best_psm": best}
        row["mechanism"] = classify(row)
        row["psm_fixes_it"] = best["recall"] > per_psm["psm_3"]["recall"]
        rows.append(row)

        print(f"{doc_id:<28}{'REGRESSION' if row['is_regression'] else 'control':<11}"
              f"easy {e_row['recall']:.3f}({e_row['tokens']:>3}t)  "
              f"tess@3 {per_psm['psm_3']['recall']:.3f}({per_psm['psm_3']['tokens']:>3}t)  "
              f"best psm{best['psm']} {best['recall']:.3f}  "
              f"| {row['mechanism']}", flush=True)

    args.out.write_text(json.dumps({"dpi": args.dpi, "langs": langs, "rows": rows},
                                   indent=1, ensure_ascii=False))
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
