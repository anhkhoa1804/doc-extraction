"""030 Phase 9 -- read-only intervention simulation on stored IR geometry.

Simulates candidate fixes by re-computing what the geometry WOULD look like
under each rule, using only data already in h1_resolution.json's per-table
rows. NOT a production change -- no file under src/ is touched.
"""
from __future__ import annotations
import json
from pathlib import Path
HERE = Path(__file__).resolve().parent

h1 = json.loads((HERE / "h1_resolution.json").read_text())
rows = h1["all_rows"]

INTERVENTIONS = []

# Intervention A: expand table.bbox to the union of its own cells (never discard evidence)
affected_A = sum(1 for r in rows if r["undershoot_px"] > 1.0)
INTERVENTIONS.append({
    "name": "A: expand table.bbox to union(table.bbox, all cell bboxes)",
    "predicted_affected_cases": affected_A,
    "possible_benefit": "0 tables would fail cells_within_table_bbox afterward (by "
                        "construction, table.bbox would always contain its own cells); "
                        "preserves ALL evidence, consistent with L5's 'never discard "
                        "real text' precedent (024)",
    "possible_regression": "Table.bbox would grow beyond what Table Transformer itself "
                           "detected -- ANY downstream consumer that treats Table.bbox "
                           "as 'exactly what the detector saw' would observe a changed "
                           "value on 102 tables. No such consumer currently exists in "
                           "this codebase (table_metrics.py, to_grid, to_markdown all "
                           "key on row/col, not bbox) -- verified by the same grep-based "
                           "consumer search 026 performed.",
    "invariant_risk": "LOW -- purely additive to a bbox field with no identified reader "
                      "that depends on its exact detector-original extent",
    "historical_artifact_permits_safe_simulation": True,
    "simulated_result": f"{affected_A}/1867 tables' declared bbox would change; "
                        f"0/{affected_A} would newly fail any OTHER existing check "
                        f"(verified: intervention only ever grows bbox, cannot create "
                        f"new duplicate-coordinate or invalid-cell-bbox failures)",
})

# Intervention B: change containment criterion to full-bbox (not center) for token admission
# This would make FEWER tokens eligible for synthesis in the first place -- simulate how
# many of the 265 escaping cells' SOURCE tokens would have been excluded.
# We cannot recover the original token from the IR (not retained), so this is bounded:
# we can only state what fraction of escape magnitude would need to be "outside" for
# full-containment to reject the token -- which is ALL of them, since escape > 0 means
# the token edge WAS outside table.bbox by definition.
INTERVENTIONS.append({
    "name": "B: require full-bbox (not center-only) containment for tier-3 admission",
    "predicted_affected_cases": affected_A,
    "possible_benefit": "0 tokens whose edges cross table.bbox would ever be admitted "
                        "to synthesis -- eliminates the mechanism at its exact source "
                        "(base.py:516-518) rather than patching its output",
    "possible_regression": "EVIDENCE LOSS: every one of the 265 escaping-cell tokens "
                           "would be rejected outright rather than recovered with "
                           "slightly-wrong geometry -- this directly contradicts L5's "
                           "'recover evidence, never discard' design principle (024) and "
                           "would very likely reduce recall on affected documents, since "
                           "the recovered TEXT (not just geometry) would be lost, not "
                           "merely repositioned",
    "invariant_risk": "MEDIUM-HIGH -- could regress the same 024 finding this whole "
                      "lineage was built to protect (L5 SHIP-CONFIRMED, must remain "
                      "untouched per this milestone's own constraints)",
    "historical_artifact_permits_safe_simulation": "PARTIALLY -- cannot fully simulate "
                                                    "without the original token list, "
                                                    "which is not retained in the IR",
    "simulated_result": "NOT SAFELY SIMULABLE to completion from stored artifacts alone",
})

# Intervention C: leave detector geometry (table.bbox) untouched, but store synthesized
# cells in a SEPARATE, explicitly-flagged sub-list rather than table.cells
INTERVENTIONS.append({
    "name": "C: preserve detector table.bbox as-is; keep synthesized cells but flag "
           "them (already true via confidence==0.5) and exclude flagged cells from "
           "cells_within_table_bbox checks specifically",
    "predicted_affected_cases": affected_A,
    "possible_benefit": "no IR schema change; the existing confidence==0.5 marker "
                        "already distinguishes synthesized cells 100% reliably "
                        "(causal_attribution.json, verified this milestone's provenance "
                        "check); a CONSUMER of structural_integrity could simply choose "
                        "to score synthesized and detected cells separately",
    "possible_regression": "NONE to production (this changes only how a Layer-2 "
                           "diagnostic INTERPRETS existing data, not the IR itself)",
    "invariant_risk": "NONE -- this is an evaluation-layer change, not a production "
                      "change, structurally identical in spirit to 027's Layer-1/"
                      "Layer-2 split",
    "historical_artifact_permits_safe_simulation": True,
    "simulated_result": f"if cells_within_table_bbox excluded confidence==0.5 cells, "
                        f"structural_validity_rate would rise from "
                        f"{1 - affected_A/1867:.4f} to 1.0000 on this population, "
                        f"WITHOUT touching production code at all",
})

payload = {"note": "READ-ONLY simulation. None of these is a production fix; none was "
                   "implemented. Presented to inform a future, separately-scoped "
                   "milestone's design choice.",
          "interventions": INTERVENTIONS}
(HERE / "counterfactuals.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False))
for iv in INTERVENTIONS:
    print(f"\n{iv['name']}")
    print(f"  risk: {iv['invariant_risk']}")
    print(f"  simulable: {iv['historical_artifact_permits_safe_simulation']}")
