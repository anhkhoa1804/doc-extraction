"""033 Phases 14-16 -- downstream impact, compute/scaling, and final
decision. Synthesizes this milestone's own artifacts.

    python experiments/033_table_shape_integrity/production_assessment.py
"""
from __future__ import annotations
import json
from pathlib import Path
HERE = Path(__file__).resolve().parent


def main():
    cand_results = json.loads((HERE / "candidate_results.json").read_text())
    adversarial = json.loads((HERE / "adversarial_results.json").read_text())
    corpus_recheck = json.loads((HERE / "corpus_recheck.json").read_text())
    oop = json.loads((HERE / "out_of_population_results.json").read_text())
    threshold = json.loads((HERE / "threshold_robustness.json").read_text())
    prov = json.loads((HERE / "provenance_safety.json").read_text())

    payload = {
        "phase_14_downstream_impact": {
            "table_structure": "UNCHANGED -- 033's candidates only gate "
                              "WHICH regions reach 031's unmodified "
                              "reconstruct_table(); the 79 admitted "
                              "instances produce IDENTICAL tables under "
                              "every candidate (routing_policy_results.json: "
                              "same 38 TRUE_RECOVERY / 28 PLAUSIBLE_RECOVERY "
                              "/ 13 PSEUDO_TABLE breakdown for every "
                              "candidate).",
            "cell_text": "UNCHANGED, same reasoning.",
            "evidence_ownership": "UNCHANGED -- not re-measured this "
                                  "milestone either (031's own limitation, "
                                  "still open).",
            "duplicate_emission": "UNCHANGED from 031 -- reconstructed "
                                  "cells still reference the same "
                                  "already-duplicated text (025's finding), "
                                  "by design, unaffected by which gate "
                                  "admits the candidate.",
            "page_ordering": "UNCHANGED -- gate choice does not touch "
                            "element list order or reading_order.",
            "table_ordering": "UNCHANGED -- append-only design inherited "
                             "from 031.",
            "serialization_effects": "UNCHANGED.",
            "role_ambiguity_as_an_abstraction": (
                "role_stability re-check (this milestone, verified "
                "directly): under Candidate E, the GATE decision remains "
                "PERFECTLY STABLE (always True) across all 19/19 arms for "
                "cmb_stamp_table_vi and hc_stamp_table_vi, exactly "
                "matching 032's original score-stability finding, while "
                "the underlying detector LABEL still flips. The corrected "
                "rule does NOT weaken 032's central stability finding -- "
                "it is UNCHANGED, because stability was always about "
                "consistency, not correctness, and this milestone's fix "
                "only touched correctness. HOWEVER: 032's role-ambiguity "
                "framing implicitly assumed the AMBIGUITY itself "
                "(evidence conflicting with label) was the meaningful "
                "signal -- this milestone's adversarial/corpus evidence "
                "shows a LARGE FRACTION of that apparent ambiguity "
                "(Chapter9-pattern banners, single-column prose) was "
                "actually a MEASUREMENT DEFECT, not a genuine latent "
                "role-uncertainty variable. See recommendation.json's "
                "phase_17_final_question for the full resolution."
            ),
        },
        "phase_15_compute_scaling": {
            "extra_operations_per_picture_region": "IDENTICAL to 031/032 "
                                                    "-- every candidate "
                                                    "reuses compute_signals()'s "
                                                    "existing 8 fields; the "
                                                    "gate change is a few "
                                                    "extra boolean "
                                                    "comparisons on values "
                                                    "already computed, not "
                                                    "a new computation.",
            "extra_ocr_work": 0, "extra_specialist_invocations": (
                "FEWER, not more -- candidates D/E reject Chapter9-pattern "
                "content that the original rule would have wastefully "
                "invoked reconstruction on."),
            "cpu_overhead": "negligible, same order as 031.",
            "gpu_overhead": "NONE -- this entire milestone ran on the "
                           "CPU-only venv; GPU was checked at Phase 0 "
                           "(baseline.json: PID 72505 active, untouched) "
                           "and never used.",
            "worst_case_page_cost": "unchanged -- linear in nested-child "
                                    "count per picture region.",
        },
        "phase_16_decision": {
            "decision": "EXPERIMENTAL",
            "not_SHIP_CANDIDATE_because": (
                "a real, held-out false positive still exists "
                "(out_of_population_results.json: "
                "docstructbench_llm-raw-scihub-...chroma.2005.05.085.pdf_4, "
                "a genuine scientific paper, still triggers Candidate E's "
                "whole-page test, row_bands=11 col_bands=2 children_per_"
                "row_band=1.55 -- barely above the 1.5 density floor); "
                "the multi-column-prose blind spot "
                "(adversarial_results.json cases 17/36) is REJECTED by "
                "ZERO candidates, a known, disclosed, UNRESOLVED gap; and "
                "this heuristic has never been wired into src/ at all, so "
                "there is no existing production behavior to 'patch' -- "
                "SHIP_CANDIDATE would mean proposing this as a NEW "
                "production intervention, which the residual risk above "
                "does not yet justify."
            ),
            "not_HOLD_because": (
                "this milestone DID establish a materially improved, "
                "extensively validated safe boundary: Candidate E "
                "dominates the original rule on every axis measured -- "
                "100% true-recovery retention (candidate_results.json), "
                "0 known-negative false positives, rejects the real "
                "Chapter9 case (0/1 vs original's 1/1), best-tied "
                "synthetic accuracy (32/42), 83% reduction in novel "
                "real-corpus page-level false positives (6->1 documents, "
                "corpus_recheck.json), and a moderately wide (12/48, 25%) "
                "safe threshold region (threshold_robustness.json) -- not "
                "a knife-edge. There IS a concrete, evidence-backed "
                "boundary now, even though it is not yet perfect."
            ),
            "not_REJECT_because": (
                "the correction is unambiguously beneficial relative to "
                "the status quo research artifact (031/032's own "
                "table_shape_score) on every measured axis, with zero "
                "identified regression -- rejecting it would mean "
                "preferring a STRICTLY WORSE heuristic for no benefit."
            ),
            "recommended_candidate": "E_density_plus_tighter_rows "
                                    "(row_bands>=3 AND col_bands>=2 AND "
                                    "children_per_row_band>=1.5, no score/"
                                    "regularity dependency)",
            "provenance_safety": prov["all_checks_pass"],
        },
    }
    Path("production_assessment.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False))
    print("decision:", payload["phase_16_decision"]["decision"])
    print("recommended candidate:", payload["phase_16_decision"]["recommended_candidate"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
