"""031 Phase 11 -- TRUE_RECOVERY / PLAUSIBLE_RECOVERY / PSEUDO_TABLE / INVALID.

A rectangular reconstructed structure is NOT automatically a successful
table recovery. This classifies every CONSERVATIVE-mode reconstruction
from Phase 10 (controlled_intervention.py) using THREE independent inputs,
never structural shape alone:

  1. structural_integrity (028) -- does the reconstruction violate a known
     geometric invariant (INVALID), or only fail column-band coherence
     under the reconstruction's own deliberately naive rank-based column
     assignment (a reconstruction-algorithm artifact, not proof the region
     isn't a table -- see controlled_intervention.py's reconstruct_table
     docstring)?
  2. factual_oracle_comparison (031 Phase 12) -- does independent evidence
     (a REAL historically-produced table for the SAME document, same-arm
     bbox overlap or cross-arm text-token recall) say this corresponds to
     an actual table, and does row count agree?
  3. Phase 6/13 negative-control status -- is this one of the documents
     the 39-negative population already characterized as non-table stamp
     fragments? If so, PSEUDO_TABLE regardless of reconstructed shape.

    python experiments/031_table_label_gating/recovery_verdicts.py
"""
from __future__ import annotations
import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
L28 = REPO / "experiments/028_layer2_evaluation"
sys.path.insert(0, str(L28))
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "research/production_corpus"))
sys.path.insert(0, str(REPO / "experiments/023_evidence_centric"))
sys.path.insert(0, str(HERE))

from structural_integrity import structural_integrity  # noqa: E402
from controlled_intervention import apply_intervention, find_layout_and_doc  # noqa: E402

HARD_INVARIANT_CHECKS = {
    "coords_in_declared_range", "no_duplicate_coordinates", "rows_contiguous",
    "cols_contiguous", "row_order_matches_geometry", "col_order_matches_geometry",
    "all_cell_bboxes_valid", "cells_within_table_bbox",
}
NEGATIVE_DOCS = {"cmb_lowcontrast_stamp_vi", "hc_stamp_text_vi", "hc_transparent_seal_vi"}


def oracle_lookup(oracle_data):
    """document_id -> best available same_physical_region signal + oracle
    row count, preferring a same-arm pair (direct geometric evidence) over
    a cross-arm pair (indirect text-token evidence)."""
    out = {}
    for doc in oracle_data["documents"]:
        did = doc["document_id"]
        if not doc["factual_oracle_exists"]:
            out[did] = {"exists": False}
            continue
        same_arm = doc.get("same_arm_pairs") or []
        cross_arm = doc.get("cross_arm_pairs") or []
        if same_arm:
            best = max(same_arm, key=lambda p: p["bbox_iou"])
            out[did] = {
                "exists": True, "regime": "SAME_ARM",
                "same_physical_region": best["same_physical_region"],
                "oracle_shape": best["factual_table_shape"],
                "bbox_iou": best["bbox_iou"],
                "table_contained_in_picture_frac": best["table_contained_in_picture_frac"],
            }
        elif cross_arm:
            best = max(cross_arm, key=lambda p: (p["factual_text_token_recall_in_candidate"] or 0))
            out[did] = {
                "exists": True, "regime": "CROSS_ARM",
                "same_physical_region": best["same_physical_region"],
                "oracle_shape": best["factual_table_shape"],
                "token_recall": best["factual_text_token_recall_in_candidate"],
            }
        else:
            out[did] = {"exists": True, "regime": "NONE_OBSERVED",
                        "same_physical_region": "UNKNOWN", "oracle_shape": None}
    return out


def classify(did, shape, checks, failed, oracle):
    """Returns (verdict, reasoning)."""
    if did in NEGATIVE_DOCS:
        return "PSEUDO_TABLE", (
            f"{did} is part of the Phase 4-6 negative-control population "
            f"(1-2 nested-text-child stamp fragments characterized as non-table "
            f"in table_shape_probe.json's negative_population) -- any reconstructed "
            f"structure here is imposed on a region independently known not to be "
            f"a table, regardless of its geometric shape.")

    hard_failed = [f for f in failed if f in HARD_INVARIANT_CHECKS]
    if hard_failed:
        return "INVALID", (
            f"reconstructed structure violates known geometric invariants: "
            f"{hard_failed} (structural_integrity checks from 028, not merely "
            f"the reconstruction's own column-assignment heuristic).")

    rows_ok = checks.get("rows_vertically_coherent", True)
    cols_ok = checks.get("cols_horizontally_coherent", True)

    if not rows_ok:
        return "PSEUDO_TABLE", (
            f"rows_vertically_coherent=False: cells assigned to the same row "
            f"index do not even share a common y-band. This is the reconstruction "
            f"imposing row/col structure on children whose geometry does not "
            f"actually support it -- not a column-assignment artifact, a row-level "
            f"failure. Consistent with factual_oracle_comparison.json showing the "
            f"real table for this document occupies only "
            f"{oracle.get('table_contained_in_picture_frac', '?')} of the "
            f"picture region's own area (region likely mixes table + non-table "
            f"content, e.g. a stamp/boundary block around a genuine but much "
            f"smaller table).")

    oracle_exists = oracle.get("exists", False)
    spr = oracle.get("same_physical_region", "UNKNOWN")
    oracle_shape = oracle.get("oracle_shape")
    row_match = oracle_shape is not None and shape[0] == oracle_shape[0]

    if oracle_exists and spr in ("YES", "PROBABLE") and row_match:
        return "TRUE_RECOVERY", (
            f"independent oracle evidence (factual_oracle_comparison.json, "
            f"same_physical_region={spr}) says this document's picture-gated "
            f"region corresponds to an actual historically-produced table with "
            f"row count {oracle_shape[0]}, matching this reconstruction's "
            f"{shape[0]} rows. cols_horizontally_coherent={cols_ok} -- if False, "
            f"column INDEX alignment is approximate (rank-based assignment, see "
            f"reconstruct_table docstring) and should not be read as cell-level "
            f"ground truth, but row-level recovery is supported by evidence "
            f"independent of the reconstruction itself.")

    if cols_ok and rows_ok and not oracle_exists:
        return "PLAUSIBLE_RECOVERY", (
            f"structure is fully coherent (rows and columns both pass "
            f"028's structural_integrity checks) but no factual oracle exists "
            f"for this document anywhere in the replayed corpus "
            f"(factual_oracle_exists=False) -- strongly table-like, cannot be "
            f"independently confirmed.")

    if not oracle_exists:
        return "PLAUSIBLE_RECOVERY", (
            f"rows_vertically_coherent=True (row bands are geometrically real) "
            f"but no factual oracle exists to confirm cell-level correctness; "
            f"cols_horizontally_coherent={cols_ok}.")

    return "PLAUSIBLE_RECOVERY", (
        f"rows coherent, oracle exists but same_physical_region={spr} or row "
        f"count does not match (reconstruction={shape}, oracle={oracle_shape}) "
        f"-- table-like structure present but oracle does not clearly confirm "
        f"THIS reconstruction represents the same content.")


def main():
    pop = json.loads((HERE / "gated_table_population.json").read_text())
    oracle_data = json.loads((HERE / "factual_oracle_comparison.json").read_text())
    oracle = oracle_lookup(oracle_data)

    test_keys = sorted({(c["milestone"], c["arm"], c["document_id"]) for c in pop["candidates"]})

    verdicts = []
    for milestone, arm, did in test_keys:
        doc_f, layout_dir = find_layout_and_doc(milestone, arm, did)
        if doc_f is None:
            continue
        raw = json.loads(doc_f.read_text())
        mod_doc, recon_log = apply_intervention(raw, layout_dir, "conservative")
        if not recon_log:
            continue
        si = structural_integrity(mod_doc)
        for t in si:
            if not t["table_id"].startswith("031-recon"):
                continue
            v, reasoning = classify(did, t["observed_shape"], t["checks"],
                                    t["failed_checks"], oracle.get(did, {"exists": False}))
            verdicts.append({
                "milestone": milestone, "arm": arm, "document_id": did,
                "table_id": t["table_id"], "observed_shape": t["observed_shape"],
                "n_cells": t["n_cells"], "structurally_valid": t["structurally_valid"],
                "failed_checks": t["failed_checks"],
                "oracle": oracle.get(did, {"exists": False}),
                "verdict": v, "reasoning": reasoning,
            })

    by_verdict = {}
    for v in verdicts:
        by_verdict.setdefault(v["verdict"], []).append(v)
    by_doc_verdict = {}
    for v in verdicts:
        by_doc_verdict.setdefault(v["document_id"], {}).setdefault(v["verdict"], 0)
        by_doc_verdict[v["document_id"]][v["verdict"]] += 1

    payload = {
        "method": "conservative-mode reconstructions only (probe-gated, the "
                 "candidate production design per intervention_candidates.json "
                 "'B'/'D'); classify() logic documented inline in this script's "
                 "module docstring and classify() function -- structural_"
                 "integrity (028) + factual_oracle_comparison (031 Phase 12) + "
                 "Phase 4-6 negative-control membership, never shape alone.",
        "total_classified": len(verdicts),
        "counts": {k: len(v) for k, v in by_verdict.items()},
        "counts_by_document": by_doc_verdict,
        "verdicts": verdicts,
    }
    Path("recovery_verdicts.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False))

    print(f"total classified: {len(verdicts)}")
    print(f"counts: { {k: len(v) for k, v in by_verdict.items()} }")
    for did, counts in sorted(by_doc_verdict.items()):
        print(f"  {did:<28} {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
