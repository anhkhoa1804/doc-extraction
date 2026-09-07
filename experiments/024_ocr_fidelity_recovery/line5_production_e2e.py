"""LINE 5 -- the real production implementation, measured on the frozen contract.

`composite.py` measured orphan recovery as a text-level proxy: unclaimed
tokens appended to the assembled document. That is enough to show the
evidence returns and not enough to show it returns *correctly* -- with page
association, provenance, reading order and table boundaries intact.

This runs the same corpus through the actual pipeline, with the recovery
implemented in `merge_regions_into_page`, using experiment 023's own
`run_ab` so the scorer, assembly and conditions machinery are byte-identical
to the frozen baseline. Nothing is substituted: the `tesseract` arm is built
exactly as production builds it (psm 3, `vie+eng`).

The comparison is therefore three-way and honest about what each side is:

    frozen baseline   023 ab_visual.json, tesseract arm      0.6038 / 0.9857
    proxy             024 composite.json, line 5 alone       0.6514 / 0.9857
    production        this run                               measured here

Writes into `_l5prod/` so the psm=1 run's artifacts are not overwritten.
CPU only.
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

if __name__ == "__main__":
    out = HERE / "_l5prod"
    out.mkdir(exist_ok=True)
    raise SystemExit(run_ab.main([
        "--strategy", "visual", "--conditions", "tesseract",
        "--device", "cpu", "--out", str(out),
    ]))
