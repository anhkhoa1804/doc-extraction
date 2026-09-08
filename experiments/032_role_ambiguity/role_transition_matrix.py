"""032 Phase 6 -- historical route-flip transition matrix.

Built from 031's paired_gating_cases.json (already the authoritative,
verified per-arm classification for the documents that have BOTH a
picture-gated arm and a table-transformer-reaching arm somewhere in the
replayed corpus) plus causal_models.json's route-family attribution.
Does not re-derive the underlying per-arm classification -- that would
risk silently diverging from 031's already-verified numbers; this phase
reshapes them into a transition-matrix view and adds the EARLIEST-
DIVERGENCE attribution (A-E per the milestone's own taxonomy).

    python experiments/032_role_ambiguity/role_transition_matrix.py
"""
from __future__ import annotations
import json
from pathlib import Path
HERE = Path(__file__).resolve().parent
L31 = HERE.parents[1] / "experiments/031_table_label_gating"


def route_family(arm):
    if "scan_cohort" in arm or "coverage" in arm or "intervention" in arm:
        return "scan_cohort/coverage (rasterized)"
    if "adaptive" in arm:
        return "adaptive (native, non-rasterized)"
    if "visual" in arm:
        return "visual (forced-OCR, not rasterized)"
    return "other"


def main():
    paired = json.loads((L31 / "paired_gating_cases.json").read_text())
    causal = json.loads((L31 / "causal_models.json").read_text())

    transitions = []
    for pc in paired["paired_cases"]:
        did = pc["document_id"]
        gated_only = pc["arms_ONLY_gated_never_tabled"]
        tabled_only = pc["arms_ONLY_tabled_never_gated"]
        both = pc["arms_in_both_states_simultaneously"]

        gated_families = sorted({route_family(a) for a in gated_only})
        tabled_families = sorted({route_family(a) for a in tabled_only})
        both_families = sorted({route_family(a) for a in both})

        clean_flip = bool(gated_only) and bool(tabled_only) and set(gated_families).isdisjoint(tabled_families)

        transitions.append({
            "document_id": did,
            "observed_picture_stays_picture": len(gated_only),
            "observed_picture_becomes_table_ONLY_no_coexist": 0,  # never happens: a
                                                                   # picture-labelled region that becomes
                                                                   # table-only-with-no-duplicate is not
                                                                   # observed anywhere in this corpus
            "observed_table_and_picture_coexist": len(both),
            "table_only_never_gated": len(tabled_only),
            "gated_only_route_families": gated_families,
            "tabled_only_route_families": tabled_families,
            "coexist_route_families": both_families,
            "clean_route_driven_flip": clean_flip,
            "stability_classification": (
                "STABLE_PICTURE" if gated_only and not tabled_only and not both else
                "STABLE_TABLE" if tabled_only and not gated_only and not both else
                "UNSTABLE_CLEAN_FLIP" if clean_flip else
                "UNSTABLE_COEXISTENCE" if both else
                "MIXED"
            ),
        })

    # aggregate matrix: for the 4 documents with a picture-gated instance
    # anywhere, what state does each arm-family tend toward?
    matrix = {
        "adaptive (native, non-rasterized)": {"table_only": 0, "picture_only": 0, "coexist": 0},
        "scan_cohort/coverage (rasterized)": {"table_only": 0, "picture_only": 0, "coexist": 0},
        "visual (forced-OCR, not rasterized)": {"table_only": 0, "picture_only": 0, "coexist": 0},
    }
    for t in transitions:
        for fam in t["tabled_only_route_families"]:
            if fam in matrix:
                matrix[fam]["table_only"] += 1
        for fam in t["gated_only_route_families"]:
            if fam in matrix:
                matrix[fam]["picture_only"] += 1
        for fam in t["coexist_route_families"]:
            if fam in matrix:
                matrix[fam]["coexist"] += 1

    earliest_divergence = {
        "question": "for the same document, at what stage does a "
                    "table-producing arm first diverge from a "
                    "picture-gated arm?",
        "answer": "ROUTE (whether the page is rasterized before Docling "
                 "sees it), which acts BEFORE Docling's own layout "
                 "classification runs -- not at the OCR-recognizer stage.",
        "classification": "routing-driven, with a layout-driven mediating "
                          "step (rasterization changes what Docling's "
                          "layout model sees; the recognizer identity used "
                          "afterward to fill in text does not change the "
                          "picture-vs-table classification within a route "
                          "family in any paired case examined).",
        "evidence": "031 FINAL_REPORT.md section 10; causal_models.json "
                   "Model C SUPPORTED, Model A REJECTED.",
        "caveat": "NOT independently re-traced to Docling's internal model "
                 "at the pixel level this milestone either -- carried "
                 "forward from 031 as INFERENCE, not re-elevated to FACT.",
    }

    payload = {
        "source": "reshaped from 031/paired_gating_cases.json and "
                 "031/causal_models.json -- no new per-arm classification "
                 "computed, only re-presented as a transition matrix.",
        "per_document_transitions": transitions,
        "route_family_outcome_matrix": matrix,
        "earliest_observable_divergence": earliest_divergence,
        "note_on_reverse_direction": (
            "no case exists anywhere in the replayed corpus of a "
            "genuinely table-labelled region becoming picture-labelled in "
            "a DIFFERENT arm while no picture-labelled duplicate ever "
            "coexists -- the only observed direction is "
            "picture-only <-> {picture+table coexisting, table-only}. "
            "This is consistent with Docling's traverse_pictures=True "
            "behavior (031 gating_contract.json) always being the "
            "SOURCE of the ambiguity: a table region can additionally "
            "spawn a duplicate picture-labelled superset, but the reverse "
            "(a table spontaneously vanishing into a picture with no "
            "trace) was not observed."
        ),
    }
    Path("role_transition_matrix.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False))
    print("per-document stability:")
    for t in transitions:
        print(f"  {t['document_id']:<25} {t['stability_classification']}")
    print(f"\nroute family outcome matrix: {json.dumps(matrix, indent=1)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
