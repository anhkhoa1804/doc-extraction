"""031 Phase 8 -- counterfactual replay: what would recovery look like?

FACTUAL REPLAY: for cmb_stamp_table_vi and hc_stamp_table_vi, the SAME
document's adaptive-route arm already contains a real table_transformer
table for what is (by document identity) the same physical table. This is
not a simulation -- it is the recorded historical output of running the
production table pipeline on this content, just via a different route.

SIMULATED COUNTERFACTUAL: for cmb_scan_stamp_table_vi (no route in the
corpus ever recovers it as a table -- Phase 3 found it has ZERO
"tabled-only" arms), no factual replay exists. Any reconstruction for this
document is necessarily simulated from its own nested text-region geometry,
labelled as such.

    python experiments/031_table_label_gating/counterfactual_replay.py
"""
from __future__ import annotations
import json
from pathlib import Path
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
L29 = REPO / "experiments/029_deep_forensic_replay"


def find_table(milestone, arm, document_id):
    roots = {
        "023": REPO / "experiments/023_evidence_centric/_runs",
        "024": REPO / "experiments/024_ocr_fidelity_recovery/_runs",
        "025": REPO / "experiments/025_layout_evidence_recall/_runs",
    }
    base = roots[milestone] / arm
    if not base.exists():
        return None
    for d in base.iterdir():
        if d.is_dir() and d.name.rsplit("-", 1)[0] == document_id:
            f = d / "final" / "document.json"
            if f.exists():
                doc = json.loads(f.read_text())
                for pg in doc.get("pages") or []:
                    for tb in pg.get("tables") or []:
                        return tb
    return None


def main():
    results = []

    # FACTUAL REPLAY -- these two documents have a real table_transformer
    # table recorded in their adaptive-route arm (Phase 3 evidence)
    for did, arm in [("cmb_stamp_table_vi", ("023", "adaptive/tesseract")),
                     ("hc_stamp_table_vi", ("023", "adaptive/tesseract"))]:
        tb = find_table(arm[0], arm[1], did)
        results.append({
            "document_id": did, "type": "FACTUAL_REPLAY",
            "source": f"{arm[0]}/{arm[1]}, real production output, not simulated",
            "table_found": tb is not None,
            "table_summary": None if tb is None else {
                "n_rows": tb.get("n_rows"), "n_cols": tb.get("n_cols"),
                "n_cells": len(tb.get("cells") or []),
                "non_empty_cells": sum(1 for c in (tb.get("cells") or []) if c.get("text")),
                "sample_cell_texts": [c.get("text") for c in (tb.get("cells") or [])[:6]],
            },
        })

    # SIMULATED COUNTERFACTUAL -- cmb_scan_stamp_table_vi never has a
    # tabled-only arm anywhere; any reconstruction is a simulation from its
    # own nested-region geometry only
    pop = json.loads((HERE / "gated_table_population.json").read_text())
    sim_candidates = [c for c in pop["candidates"]
                      if c["document_id"] == "cmb_scan_stamp_table_vi"
                      and c["classification"] == "CONFIRMED"]
    results.append({
        "document_id": "cmb_scan_stamp_table_vi", "type": "SIMULATED_COUNTERFACTUAL",
        "source": "no factual table_transformer output exists for this document in "
                 "any replayed arm (Phase 3: zero tabled-only arms) -- this is a "
                 "GEOMETRIC SIMULATION from nested text-region positions only, not "
                 "historical behavior",
        "n_confirmed_picture_candidates": len(sim_candidates),
        "sample_candidate": sim_candidates[0] if sim_candidates else None,
    })

    Path("counterfactual_replay.json").write_text(json.dumps(results, indent=1, ensure_ascii=False))
    for r in results:
        print(f"\n[{r['type']}] {r['document_id']}")
        if r["type"] == "FACTUAL_REPLAY":
            print(f"  table found: {r['table_found']}  {r.get('table_summary')}")
        else:
            print(f"  confirmed picture candidates: {r['n_confirmed_picture_candidates']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
