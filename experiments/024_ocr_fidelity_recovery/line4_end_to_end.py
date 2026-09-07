"""LINE 4 -- `--psm 1` measured through the full pipeline, on the frozen contract.

The screen (`line4_psm_screen.py`) showed `--psm 1` acquiring two more
strings on `hc_rotation_vi` and changing nothing on the other 48 documents,
at zero extra OCR invocations. Raw acquisition is not the contract's metric,
so this re-measures it end to end.

It reuses experiment 023's own `run_ab` -- same scorer, same assembly, same
conditions machinery -- with a single substitution: the `tesseract` arm is
built with `psm=1` instead of the backend default of 3. Everything else,
including `to_tesseract_langs`, the shared memoised layout and the corpus,
is untouched, so the difference between this run and 023's frozen
`ab_visual.json` tesseract arm is exactly the flag.

The psm=3 side of the comparison is NOT re-run: 023's `ab_visual.json` is
that measurement, at this commit, through this code path, and re-running it
would spend twenty minutes to reproduce a frozen number.

Writes into this experiment's own directory. 023's artifacts are read-only
here. CPU only.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "research/production_corpus"))
sys.path.insert(0, str(REPO / "experiments/023_evidence_centric"))

import run_ab  # noqa: E402
from doc_extraction.backends.tesseract_backend import TesseractBackend  # noqa: E402

PSM = 1


def build_tesseract_psm1(condition: str, device: str, langs: list[str]):
    if condition != "tesseract":
        raise SystemExit(f"this runner only builds the tesseract arm, got {condition!r}")
    return TesseractBackend(device=device, languages=langs, psm=PSM)


if __name__ == "__main__":
    run_ab.build_ocr_backend = build_tesseract_psm1
    raise SystemExit(run_ab.main([
        "--strategy", "visual", "--conditions", "tesseract",
        "--device", "cpu", "--out", str(HERE),
    ]))
