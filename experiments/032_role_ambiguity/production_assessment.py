"""032 Phases 16-18 -- cost analysis, minimal architectural change, and
production readiness assessment. Synthesizes this milestone's own
artifacts; does not recompute geometry.

    python experiments/032_role_ambiguity/production_assessment.py
"""
from __future__ import annotations
import json
from pathlib import Path
HERE = Path(__file__).resolve().parent
L31 = HERE.parents[1] / "experiments/031_table_label_gating"


def main():
    adversarial = json.loads((HERE / "adversarial_controls.json").read_text())
    stability = json.loads((HERE / "role_stability.json").read_text())
    routing = json.loads((HERE / "routing_policy_results.json").read_text())

    payload = {
        "phase_16_cost": {
            "extra_cpu": "the evidence vector (table_shape_score's 5 "
                        "signals) is computed from data ALREADY in "
                        "layout/*.json + document.json -- pure Python "
                        "geometry over already-materialized objects, no "
                        "new model call, no new render, no new OCR pass "
                        "(unchanged from 031's own cost finding).",
            "extra_ocr_work": "NONE -- text attachment (this milestone's "
                             "own bug-fix precedent, controlled_"
                             "intervention.attach_text_from_elements) is "
                             "an IoU bbox join against text already "
                             "recognized, not a new recognition pass.",
            "extra_model_calls": 0,
            "worst_case_scaling": "linear in nested-child count per "
                                  "picture-labelled region per page -- "
                                  "same order as the existing region-merge "
                                  "loop (merge_regions_into_page). No "
                                  "quadratic or model-call-per-region term "
                                  "introduced by anything designed this "
                                  "milestone.",
            "gpu_cost": "NONE -- this entire milestone, like 031, ran "
                       "exclusively on the CPU-only venv (doc-extraction-"
                       "linux312); GPU was checked (baseline.json) and "
                       "never used.",
            "verdict": "cost is NOT a blocker for any option considered "
                      "this milestone -- the constraint is evidence "
                      "RELIABILITY (adversarial_controls.json), not compute.",
        },
        "phase_17_minimal_architectural_change": {
            "options_considered": {
                "A_no_change": "REJECTED as the sole answer -- 032's own "
                              "evidence (role_stability.json: evidence more "
                              "stable than label in 3/7 documents, 0 "
                              "reverse cases; routing_policy_results.json: "
                              "Policy 2/3 recovers 66 true-table instances "
                              "with zero false positives on the KNOWN "
                              "negative population) shows SOME signal "
                              "exists worth preserving, even though it is "
                              "not yet safe to act on unconditionally.",
                "B_role_candidates_plus_routing_reason": "CLOSEST TO "
                    "RECOMMENDED -- role_contract.json's own finding is "
                    "that Element.extra is ALREADY a viable, ALREADY-USED "
                    "carrier (031 precedent) for exactly this; "
                    "provenance_design.json specifies the concrete shape. "
                    "No IR schema migration required.",
                "C_ambiguity_field_in_IR": "LARGER than B -- would add a "
                    "new typed field to the Element/Table pydantic models "
                    "(a real schema version bump, schemas/version.py) "
                    "rather than reusing extra. Not justified by current "
                    "evidence: extra already does the job without a "
                    "migration; C is a future option if role provenance "
                    "becomes a FIRST-CLASS, widely-consumed concept "
                    "rather than an experimental annotation.",
                "D_dedicated_routing_layer": "REJECTED as premature -- "
                    "would introduce a new architectural component "
                    "(a role-router module, evidence-vector computation "
                    "wired into the main pipeline, not just research "
                    "scripts) before adversarial_controls.json's own "
                    "finding (6/20 synthetic misfires, including ordinary "
                    "single-column prose reaching the conservative "
                    "threshold via row-only evidence) is resolved. "
                    "Building infrastructure around an unreliable signal "
                    "is not justified.",
                "E_only_improve_table_gate": "TOO NARROW -- role_contract."
                    "json's Phase 2 finding (two independently-maintained "
                    "label-mapping tables, 18/28 keys disagree between "
                    "routes) shows the labeling inconsistency problem is "
                    "NOT specific to table/picture -- checkbox and chart "
                    "labels are affected too. A table-gate-only fix "
                    "would not address the general pattern.",
                "F_need_stronger_upstream_layout_model": "NOT SUPPORTED by "
                    "this milestone's evidence as the NEXT step -- the "
                    "existing evidence (row_bands, aspect_ratio) already "
                    "carries real signal (role_stability.json); the "
                    "problem demonstrated by adversarial_controls.json is "
                    "under-SPECIFIED scoring logic (an OR-of-5-criteria "
                    "point score, not requiring row+column evidence "
                    "jointly), not an absence of usable signal. Improving "
                    "the SCORING RULE is cheaper and more directly "
                    "targeted than waiting for a new upstream model.",
            },
            "chosen": "B, with an immediate, narrowly-scoped refinement to "
                    "the scoring rule itself (require row_bands>=2 AND "
                    "col_bands>=2 jointly, not as independently-scored "
                    "criteria among 5) BEFORE any production wiring -- "
                    "adversarial_controls.json case 8/18 (single-column "
                    "prose reaching threshold 3 via row-only evidence) is "
                    "a correctness bug in the CURRENT scoring rule, "
                    "independent of the architecture question.",
        },
        "phase_18_production_readiness": {
            "correctness": "NOT YET -- 6/20 adversarial misfires "
                          "(adversarial_controls.json), including a "
                          "severe one (ordinary prose/bullet lists can "
                          "reach the conservative threshold using only "
                          "row-based evidence, zero column evidence "
                          "required)",
            "observability": "GOOD IF SHIPPED -- provenance_design.json's "
                            "shape makes every routing decision inspectable "
                            "via Element.extra, additive and non-breaking",
            "explainability": "GOOD -- table_shape_evidence_score's 5 "
                             "components are individually named "
                             "(score_reasons), not a black-box number",
            "provenance": "GOOD -- 031's own precedent already validates "
                         "this pattern in production-adjacent code",
            "backward_compatibility": "FULL -- Element.extra is additive; "
                                     "existing consumers see no change "
                                     "unless they opt in to reading the "
                                     "new key",
            "latency": "NEGLIGIBLE -- pure geometry over already-"
                     "materialized data (phase_16_cost)",
            "memory": "NEGLIGIBLE -- one small dict per candidate region, "
                    "bounded by page element count",
            "failure_isolation": "GOOD BY DESIGN -- 031's own architecture "
                                "(candidate added ALONGSIDE, original "
                                "label never destroyed) means a wrong "
                                "candidate is a spurious EXTRA table "
                                "object, never a lost picture element",
            "deterministic_behavior": "YES -- verified this milestone: "
                                     "every script in 031 AND 032 "
                                     "reproduced byte-identical output "
                                     "across two consecutive runs "
                                     "(032 Phase 21)",
            "rollback": "TRIVIAL if shipped as extra-only metadata -- "
                       "deleting the annotation code path fully restores "
                       "current behavior with no data migration",
            "operational_complexity": "LOW for option B as scoped; the "
                                     "scoring-rule fix (row_bands>=2 AND "
                                     "col_bands>=2) is a small, testable "
                                     "code change, not new infrastructure",
            "decision": "EXPERIMENTAL",
            "decision_reasoning": (
                "Same category of decision as 031 (mechanism vs safety "
                "are separate). The mechanism -- evidence CAN be more "
                "stable than the raw label, and a dual-candidate, "
                "provenance-preserving policy (Policy 2/3) recovers real "
                "structure with zero regression on the KNOWN negative "
                "population -- is real and specifically demonstrated. But "
                "adversarial_controls.json found a NEW, more severe "
                "false-positive mode (ordinary prose passing the gate) "
                "that 031 never tested for, on top of 031's own two "
                "already-known failure modes (Chapter9, cmb_stamp_"
                "boundary_vi). SHIP is not justified with 3 independently-"
                "found gate failures and no corpus large enough to bound "
                "the true rate. REJECT is too strong -- the underlying "
                "evidence-vs-label stability finding "
                "(role_stability.json) is real, reproducible, and did "
                "not exist as a measurement before this milestone."
            ),
        },
    }
    Path("production_assessment.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False))
    print("decision:", payload["phase_18_production_readiness"]["decision"])
    print("chosen architecture:", payload["phase_17_minimal_architectural_change"]["chosen"][:80])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
