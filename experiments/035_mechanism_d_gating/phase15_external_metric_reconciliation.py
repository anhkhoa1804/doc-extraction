"""035 Phase 15 -- reconcile this milestone's internal funnel against the
external OmniDocBench evaluator's own numbers (034a, frozen, not
recomputed here). Explicitly states which parts of the funnel TEDS can and
cannot observe, and does NOT silently treat the evaluator's 571-surviving-
of-665 TEDS sample as if it were 665 (the evaluator's own known
multiprocessing-race bug, 034a FINAL_REPORT.md Sec.11).

    python experiments/035_mechanism_d_gating/phase15_external_metric_reconciliation.py
"""
from __future__ import annotations
import json
from pathlib import Path
HERE = Path(__file__).resolve().parent
FULL_METRICS = HERE.parents[1] / "experiments" / "034a_omnidocbench_snapshot" / "results" / "full_baseline" / "metrics.json"


def main():
    full_metrics = json.loads(FULL_METRICS.read_text())
    teds_debug = full_metrics["table"]["metric_debug"]["TEDS"]

    funnel = json.loads((HERE / "table_failure_funnel.json").read_text())
    invocation = json.loads((HERE / "specialist_invocation_map.json").read_text())
    mech_d = json.loads((HERE / "mechanism_d_population.json").read_text())
    gating_confusion = json.loads((HERE / "gating_confusion_matrix.json").read_text())

    n_analyzed = funnel["n_gt_tables_analyzed"]

    result = {
        "funnel_chain_this_milestone_measured": {
            "1_gt_table_count_full_population": 665,
            "2_gt_table_count_analyzed_this_run": n_analyzed,
            "3_n_matched_to_some_internal_region": invocation["n_region_found_any_quality"],
            "4_n_gated_into_table_labelled_region": invocation["n_gated_in_labelled_table"],
            "5_n_gated_out_wrong_label": invocation["n_gated_out_wrong_label"],
            "6_n_specialist_actually_invoked": invocation["n_specialist_actually_invoked"],
            "7_n_final_table_present_in_ir": invocation["n_final_table_present"],
            "8_n_final_table_structurally_valid": invocation["n_final_table_structurally_valid"],
        },
        "evaluator_own_numbers_034a_frozen_not_recomputed": {
            "source": "experiments/034a_omnidocbench_snapshot/results/full_baseline/metrics.json (frozen)",
            "table_sample_count_official": teds_debug["sample_count"],
            "table_TEDS_error_case_count": teds_debug["error_case_count"],
            "table_TEDS_timeout_case_count": teds_debug["timeout_case_count"],
            "n_TEDS_samples_actually_scored": teds_debug["sample_count"] - teds_debug["error_case_count"],
            "CAUTION": "571 of 665 TEDS samples survived scoring (85.9%) -- the reported "
                "TEDS.all=0.3224 (official_metrics.json) is computed from 571, NOT 665. "
                "This milestone's own funnel counts (above) are over ALL matched GT tables "
                "regardless of whether the evaluator's own TEDS computation happened to "
                "succeed for that sample -- the two 'coverage' numbers (evaluator's 571/665 "
                "and this milestone's own extraction coverage) are UNRELATED and must not "
                "be added, multiplied, or otherwise combined.",
        },
        "what_TEDS_can_and_cannot_observe": {
            "TEDS_CAN_see": "Whether the FINAL markdown prediction contains table-shaped "
                "content whose HTML structure resembles the GT table's HTML, extracted "
                "via the evaluator's own quick_match text-similarity matching "
                "(.external/OmniDocBench/src/core/matching/match.py) -- it operates "
                "entirely on serialized output text, never on this system's internal "
                "Region/Element/Table objects.",
            "TEDS_CANNOT_see": [
                "WHERE in the funnel a table was lost (D1 upstream miss vs D2 wrong label "
                "vs D4 specialist failure vs D5 post-processing loss vs D6 structural "
                "invalidity) -- a low TEDS score is consistent with any of D1/D2/D4/D5/D6, "
                "and TEDS cannot distinguish them.",
                "Whether a wrong-labelled region's content leaked into the final markdown "
                "as unstructured text (still potentially raising a text-similarity metric "
                "even though the table structure itself is gone) -- meaning even TEDS=0 "
                "does not guarantee zero content recall, and a non-zero text_block score "
                "on a D2 page does not mean the table survived.",
                "The internal gate mechanism itself (region.label) at all -- this is "
                "exactly why 034a's own cross_research_comparison.json (mechanism D row) "
                "said 'partially observable, unconfirmed without a per-page internal-IR "
                "cross-reference' -- this milestone IS that cross-reference.",
            ],
        },
        "cross_check_gt_table_count": {
            "phase1_gt_contract_count": 665,
            "evaluator_own_sample_count": teds_debug["sample_count"],
            "match": 665 == teds_debug["sample_count"],
        },
        "note_on_coverage": f"This reconciliation reflects {n_analyzed}/665 "
            f"({round(n_analyzed/665*100,1)}%) of the GT table population analyzed so far "
            "by this milestone's own extraction -- rerun after full extraction completes.",
    }
    Path(HERE / "external_metric_reconciliation.json").write_text(json.dumps(result, indent=1, ensure_ascii=False))
    print(f"GT count cross-check: {result['cross_check_gt_table_count']['match']}")
    print(f"TEDS coverage: {teds_debug['sample_count'] - teds_debug['error_case_count']}/{teds_debug['sample_count']} "
          f"(NOT the same as this milestone's own {n_analyzed}/665 extraction coverage)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
