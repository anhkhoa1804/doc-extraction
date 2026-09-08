"""033 Phase 17 -- the key scientific question: is the remaining table/
picture ambiguity fundamentally a role-classification problem, or was a
significant portion caused by an inadequate table-shape evidence rule?

    python experiments/033_table_shape_integrity/recommendation.py
"""
from __future__ import annotations
import json
from pathlib import Path
HERE = Path(__file__).resolve().parent


def main():
    cand_results = json.loads((HERE / "candidate_results.json").read_text())
    adversarial = json.loads((HERE / "adversarial_results.json").read_text())
    oop = json.loads((HERE / "out_of_population_results.json").read_text())
    prod = json.loads((HERE / "production_assessment.json").read_text())

    payload = {
        "phase_17_final_question": {
            "question": "Is the remaining table/picture ambiguity "
                       "fundamentally a role-classification problem, or "
                       "was a significant portion of it caused by an "
                       "inadequate table-shape evidence rule?",
            "answer": "C -- BOTH survive, as genuinely SEPARATE "
                    "mechanisms, in different proportions for different "
                    "failure patterns. Not forced toward either extreme.",
            "evidence_for_measurement_defect_dominant_portion": [
                "candidate_results.json: Candidate E fixes the REAL "
                "Chapter9 false positive (1->0) while retaining 100% of "
                "true recoveries (38/38 TRUE_RECOVERY, 28/28 PLAUSIBLE_"
                "RECOVERY) -- a pure evidence-rule fix, zero role-"
                "architecture change, resolves this specific case "
                "completely.",
                "adversarial_results.json: the ORIGINAL rule scores "
                "23/42 correct on synthetic cases; Candidate E scores "
                "32/42 -- a 39% relative improvement from evidence "
                "correction alone.",
                "corpus_recheck.json: page-level real-prose false "
                "positives drop from 6 to 1 novel document (83% "
                "reduction) via evidence correction alone, no role-"
                "layer involved.",
            ],
            "evidence_for_genuine_residual_role_ambiguity": [
                "adversarial_results.json cases 17/36 (multi-column "
                "prose): misfire under EVERY candidate tested (A through "
                "E) -- this is not a threshold-tuning gap, it is a "
                "STRUCTURAL indistinguishability: 2-3 column prose "
                "genuinely satisfies row_bands>=2 AND col_bands>=2 AND "
                "children_per_row_band>=1.5 by construction. No pre-"
                "filter evidence rule built from the CURRENT retained "
                "dimensions (role_evidence_schema.json, 032) can "
                "separate this from a real table using bbox geometry "
                "alone.",
                "recovery_verdicts.json/candidate_results.json: "
                "cmb_stamp_boundary_vi (the PSEUDO_TABLE document) is "
                "STILL wrongly admitted by every candidate (13/13 arms, "
                "unchanged across A-E) -- its failure mode is POST-"
                "reconstruction (rows_vertically_coherent fails at "
                "reconstruction time), a fundamentally different "
                "mechanism than the PRE-filter question this milestone's "
                "candidates address at all.",
                "out_of_population_results.json: on the held-out realscan_"
                "probe family, Candidate E still wrongly admits a genuine "
                "scientific paper (docstructbench...chroma.2005.05.085.pdf_4, "
                "children_per_row_band=1.55, barely above the 1.5 floor) "
                "-- a real residual this milestone's evidence-only "
                "correction did not eliminate.",
                "Phase 8 (adversarial_results.json phase_8_single_column_"
                "table_finding): a genuine one-column table (case 29) and "
                "a one-column table WITH a semantically distinct header "
                "matching the real corpus's own STT-column pattern (case "
                "46) are BOTH rejected by every candidate -- current "
                "geometric evidence cannot recognize this class of real "
                "table AT ALL, a clean, disclosed limitation, not "
                "resolved by any threshold choice.",
            ],
            "conclusion": (
                "Case C is the honest answer: a SUBSTANTIAL, DEMONSTRATED "
                "portion of what 032 measured as 'role ambiguity' was in "
                "fact an artifact of an under-specified evidence rule "
                "(the row-AND-column conjunction gap), and is now largely "
                "resolved by Candidate E without any role-routing "
                "architecture change. But a GENUINE residual survives "
                "that no amount of threshold/predicate tuning on the "
                "CURRENT evidence dimensions can resolve (multi-column "
                "prose, one-column tables, and the separate post-"
                "reconstruction coherence question) -- these are places "
                "where either (a) a genuinely new evidence dimension is "
                "needed (e.g. actual grid-line/border pixel detection, "
                "which role_evidence_schema.json (032) already flagged "
                "as unavailable in this repository), or (b) preserving "
                "explicit uncertainty (032's role_candidates proposal) "
                "remains the right design for SPECIFICALLY these residual "
                "cases -- not for the table/picture question as a whole, "
                "which this milestone shows was mostly a measurement "
                "problem."
            ),
        },
        "next_milestone_candidates_ranked": [
            {"target": "resolve the multi-column-prose blind spot with a "
                     "genuinely new evidence dimension (not a threshold "
                     "tweak) -- e.g. right-edge (x1) alignment regularity, "
                     "which could distinguish justified/ragged prose "
                     "columns from true table columns with fixed cell "
                     "boundaries",
             "priority": 1,
             "rationale": "the SINGLE remaining case that survives every "
                        "candidate tested this milestone; adversarial_"
                        "results.json flagged it as the most concerning "
                        "case since 032"},
            {"target": "add a mandatory POST-reconstruction "
                     "rows_vertically_coherent gate (028's "
                     "structural_integrity, already exists) that DISCARDS "
                     "-- never merely flags -- incoherent candidates "
                     "before exposure, to resolve cmb_stamp_boundary_vi's "
                     "PSEUDO_TABLE pattern (a separate mechanism from "
                     "everything this milestone's pre-filter candidates "
                     "address)",
             "priority": 2,
             "rationale": "031's own recommendation, still unimplemented; "
                        "this milestone confirms no pre-filter fix "
                        "touches this failure mode at all"},
            {"target": "expand held-out real-world corpus beyond "
                     "realscan_probe's 7 documents before any production "
                     "consideration",
             "priority": 3,
             "rationale": "n=7 is too small for a real false-positive-"
                        "rate estimate (out_of_population_results.json's "
                        "own qualitative-evidence-only framing) -- 031/032's "
                        "own priority-1 recommendation, still valid"},
        ],
    }
    Path("recommendation.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False))
    print("ANSWER:", payload["phase_17_final_question"]["answer"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
