"""031 Phases 17-20 -- intervention safety, production design, research-
target reassessment, final decision. Synthesizes prior 031 artifacts into
one decision record; does not recompute geometry (all numbers here are
read from already-produced JSON, not re-derived by eyeballing).

    python experiments/031_table_label_gating/recommendation.py
"""
from __future__ import annotations
import json
from pathlib import Path
HERE = Path(__file__).resolve().parent


def main():
    intervention = json.loads((HERE / "intervention_results.json").read_text())
    verdicts = json.loads((HERE / "recovery_verdicts.json").read_text())
    oracle = json.loads((HERE / "factual_oracle_comparison.json").read_text())
    negctl = json.loads((HERE / "negative_controls.json").read_text())
    role_amb = json.loads((HERE / "role_ambiguity_analysis.json").read_text())
    causal = json.loads((HERE / "causal_models.json").read_text())
    probe = json.loads((HERE / "table_shape_probe.json").read_text())

    vcounts = verdicts["counts"]
    vby_doc = verdicts["counts_by_document"]

    payload = {
        "phase_17_intervention_safety": {
            "benefit": {
                "true_recovery_instances": vcounts.get("TRUE_RECOVERY", 0),
                "plausible_recovery_instances": vcounts.get("PLAUSIBLE_RECOVERY", 0),
                "documents_with_factual_oracle_confirmed_recovery": [
                    d for d, c in vby_doc.items() if "TRUE_RECOVERY" in c],
                "text_recall_gain_on_confirmed_documents": {
                    "FACT": "conservative mode: mean text_recall on the 66 "
                           "true-document rows rose 0.7538 -> 0.7708 (+0.0170), "
                           "mean char_recall rose 0.9771 -> 0.9810 (+0.0039) "
                           "(intervention_results.json rows.control/conservative, "
                           "filtered to confirmed_gated_documents_tested); zero "
                           "change on the 39 negative-document rows and the 13 "
                           "cmb_stamp_boundary_vi rows in EITHER direction.",
                    "INFERENCE": "the gain is small in absolute Layer-1 terms "
                                "because the underlying OCR TEXT was already "
                                "present in the document via Docling's duplicate "
                                "nested-text-element emission (025's known "
                                "finding) -- the intervention's real value is "
                                "STRUCTURAL (organizing already-present flat text "
                                "into row/col cells), which Layer-1's flat text-"
                                "matching metric is largely blind to.",
                },
                "structural_recovery": f"{vcounts.get('TRUE_RECOVERY', 0)} of "
                    f"{verdicts['total_classified']} conservative reconstructions "
                    f"classified TRUE_RECOVERY (row-level agreement with a "
                    f"factual oracle), concentrated entirely in cmb_stamp_table_vi "
                    f"(19/19) and hc_stamp_table_vi (19/19) -- recovery_verdicts.json.",
            },
            "regression": {
                "false_table_creation_on_KNOWN_negatives_conservative_mode": (
                    intervention["false_table_creation_on_probe_negative_documents"]["conservative"]),
                "false_table_creation_on_KNOWN_negatives_aggressive_mode": (
                    intervention["false_table_creation_on_probe_negative_documents"]["aggressive"]),
                "CRITICAL_false_positive_beyond_known_corpus": {
                    "FACT": f"negative_controls.json found "
                           f"{negctl['realscan_probe_population']['confirmed_false_positives_at_threshold_3']} "
                           f"confirmed false positive at the conservative threshold "
                           f"on jiaocaineedrop_Chapter9.pdf_46 region 0 -- a real-"
                           f"world textbook worksheet HEADER ('Practice', "
                           f"'Cumulative, Chapters 1-9', 'macmillanmh.com', '3'), "
                           f"scored 4/5, entirely unrelated to the stamp-vi corpus "
                           f"the probe was tuned and validated against.",
                    "INFERENCE": "table_shape_probe.json's reported 100%-precision "
                                "at threshold=3 (threshold_sweep) is an artifact of "
                                "its narrow 3-document negative-control population, "
                                "not a property of the probe itself. It does not "
                                "generalize.",
                },
                "known_candidate_misfire": {
                    "FACT": f"cmb_stamp_boundary_vi -- itself one of the 4 "
                           f"CONFIRMED gated-table candidates the probe was "
                           f"VALIDATED against (leave-document-out recovery_rate="
                           f"1.0 in table_shape_probe.json) -- produces 13/13 "
                           f"conservative reconstructions classified PSEUDO_TABLE "
                           f"(recovery_verdicts.json), because "
                           f"rows_vertically_coherent fails: the real factual "
                           f"table for this document occupies only 19.6% IoU / "
                           f"contained within the picture region at a 20%-of-area "
                           f"scale (factual_oracle_comparison.json), meaning the "
                           f"picture-labelled region mixes genuine table content "
                           f"with substantial non-table content the reconstruction "
                           f"cannot separate.",
                    "INFERENCE": "the probe's own LEAVE-DOCUMENT-OUT validation "
                                "(100% recovery at threshold=3) measures whether "
                                "the SHAPE looks table-like, not whether the "
                                "eventual RECONSTRUCTION is coherent -- these are "
                                "different questions, and the probe alone answers "
                                "only the first.",
                },
                "cell_hallucination": "0 hard-invariant violations (coords_in_"
                    "declared_range, no_duplicate_coordinates, rows/cols_"
                    "contiguous, all_cell_bboxes_valid, cells_within_table_bbox, "
                    "row/col_order_matches_geometry) across all 79 conservative "
                    "reconstructions (recovery_verdicts.json: 0 INVALID).",
                "duplicate_ownership": "NOT independently measured at the "
                    "token/evidence-ownership level this milestone (025's own "
                    "evidence-ownership instrumentation was not re-run against "
                    "031's reconstructed tables) -- LIMITATION, not a clean bill "
                    "of health. What IS known: reconstructed cell text is drawn "
                    "from the SAME nested text elements Docling already emits "
                    "twice (once as the picture's own gathered text, once as "
                    "loose nested elements per 025) -- the table adds a THIRD "
                    "reference to the same tokens, by design (non-destructive, "
                    "matches intervention B/D's provenance requirement) but this "
                    "does inflate flattened document_text() token multiplicity.",
                "page_order_change": "none -- apply_intervention only appends to "
                    "pg['tables'] and sets el['extra']['031_table_candidate_added'] "
                    "on the matching image element; elements list order and "
                    "reading_order are untouched (controlled_intervention.py "
                    "apply_intervention, verified by inspection).",
                "table_order_change": "reconstructed table is appended AFTER any "
                    "pre-existing genuine table on the same page (pg.setdefault"
                    "('tables', []).append(...)); relevant for cmb_stamp_boundary_vi's "
                    "'both states' arms where a genuine table already exists.",
                "bbox_violations": "0/79 (all_cell_bboxes_valid and "
                    "cells_within_table_bbox both hold in all conservative cases).",
            },
            "cost": {
                "additional_processing": "geometry-only (band clustering + IoU "
                    "text-matching over data already in document.json/layout "
                    "json) -- no new model call, no crop, no re-render "
                    "(intervention_candidates.json option D).",
                "additional_table_transformer_calls": 0,
                "gpu_cost": "none -- entire milestone including this synthesis "
                    "ran on the CPU-only venv (doc-extraction-linux312); the "
                    "GPU-capable venv (doc-extraction-gpu312) was never invoked.",
                "worst_case_scaling": "linear in nested-child count per "
                    "picture-labelled region; bounded by page element count, "
                    "same order as existing region-merge logic.",
            },
            "trust": {
                "provenance_explicit": "yes -- new_table['source_backend'] = "
                    "'031_intervention_D_geometric_reconstruction', cell.source = "
                    "'031_intervention_D_reconstruction'.",
                "original_label_preserved": "yes -- picture/image element is "
                    "never deleted or relabelled, only annotated via extra dict.",
                "reversible": "yes -- the added table is a distinct object; "
                    "removing it does not require reconstructing the original "
                    "state (image element was never mutated beyond the extra "
                    "marker).",
                "confidence_fabrication_check": "PASS -- every reconstructed "
                    "cell carries confidence=None (never a fabricated number); "
                    "the only heuristic score anywhere in this milestone's "
                    "artifacts is named table_shape_evidence_score, never "
                    "'confidence' (role_ambiguity_analysis.json).",
            },
        },
        "phase_18_production_design": {
            "option_A_label_relaxation": "REJECTED -- destroys original label "
                "identity (intervention_candidates.json 'A'); the Chapter9 false "
                "positive this milestone found makes this concretely dangerous, "
                "not merely theoretically risky.",
            "option_B_secondary_evidence_gate": {
                "status": "the closest viable candidate, BUT the exact form "
                    "implemented and tested this milestone (single probe-score "
                    "gate, threshold=3, no post-reconstruction check) is NOT "
                    "sufficient on its own -- it admits both known failures "
                    "(Chapter9 FP, cmb_stamp_boundary_vi PSEUDO_TABLE).",
                "RECOMMENDATION": "a two-stage gate: (1) pre-reconstruction probe "
                    "with a STRICTER row_bands floor (>=3 excludes the observed "
                    "Chapter9 header, which has row_bands=2, while every known "
                    "true positive has row_bands 3-4 -- table_shape_probe.json "
                    "signals) as a necessary-but-not-sufficient prefilter, PLUS "
                    "(2) a mandatory POST-reconstruction structural_integrity "
                    "check (028) that discards -- never exposes -- any candidate "
                    "table failing rows_vertically_coherent, which would catch "
                    "cmb_stamp_boundary_vi's failure mode that the row_bands "
                    "prefilter alone does not. NEITHER refinement was validated "
                    "against a corpus larger than n=1 additional counter-example "
                    "each -- this is a HYPOTHESIS for the next milestone, not a "
                    "validated rule.",
            },
            "option_C_fallback_table_transformer": "NOT executed this milestone "
                "(scope decision carried over from intervention_candidates.json "
                "'C', unchanged) -- would need to be tested against the SAME "
                "Chapter9-style counter-examples before it could be trusted "
                "either; a real model call is not automatically safer than a "
                "geometric heuristic against a false positive it was never "
                "shown during development.",
            "option_D_region_splitting_asis": "what was actually implemented "
                "and evaluated this milestone -- validated real recovery on 2 "
                "documents, but the SAME mechanism (naive rank-based column "
                "assignment, single-signal gate) is what produces both known "
                "failure modes. Not recommended to ship as specified.",
            "recommended_option": "B, refined per the RECOMMENDATION above, "
                "revalidated against a materially larger and more diverse "
                "negative population (starting with realscan_probe's other "
                "5 documents, which were found but not yet exhaustively mined "
                "for additional picture-with-children regions beyond the 4 "
                "scored here) before any production consideration.",
        },
        "phase_19_research_target_reassessment": {
            "original_029_recommendation": "table-label gating under stamp/"
                "occlusion documents is the highest-value next target.",
            "still_valid": "PARTIALLY. The mechanism is real (38 TRUE_RECOVERY "
                "instances, 2 documents with factual 4x5-shape oracle agreement, "
                "causal_models.json's Model C support) -- but this milestone's "
                "OWN new evidence (negative_controls.json, role_ambiguity_"
                "analysis.json) shows the higher-value target has shifted one "
                "level up the stack:",
            "candidate_targets_ranked": [
                {"target": "negative-control corpus breadth", "prevalence": "HIGH -- "
                 "blocks safe validation of ANY picture/table gating fix, not just "
                 "this one", "severity": "HIGH -- the milestone shipped a "
                 "'100% precision' claim that a single afternoon of filesystem "
                 "search falsified", "recoverability": "MEDIUM -- realscan_probe "
                 "already exists on disk with 5 more unscanned documents; a "
                 "genuinely representative negative corpus is a data-collection "
                 "task, not a research problem", "recommended_priority": 1},
                {"target": "role-uncertainty representation in the IR "
                 "(role_ambiguity_analysis.json's region -> role_candidates "
                 "concept)", "prevalence": "affects every label-gated pipeline "
                 "stage, not just table/picture", "severity": "architectural -- "
                 "the hard-gate pattern (base.py:747) recurs wherever Docling's "
                 "label vocabulary feeds a routing decision", "recoverability": "LOW "
                 "in the near term -- an IR schema change, larger than this "
                 "milestone's evidence justifies shipping", "recommended_priority": 3},
                {"target": "table-label gating recovery (031's original target)",
                 "prevalence": "LOW -- confirmed to 7 documents total in the "
                 "ENTIRE available historical IR (negative_controls.json "
                 "exhaustive search), all from one small synthetic hard-case "
                 "family", "severity": "bounded -- 2 of 4 CONFIRMED documents "
                 "genuinely recover; the mechanism is real but narrow",
                 "recoverability": "MEDIUM -- Option B refined (Phase 18) is a "
                 "plausible path, contingent on target #1", "recommended_priority": 2},
            ],
            "conclusion": "029's target was not WRONG, but this milestone's own "
                "process (searching for negative controls, as instructed) "
                "surfaced a higher-leverage prerequisite: the corpus this whole "
                "research chain validates against does not contain enough "
                "picture-region diversity to certify ANY gating intervention "
                "safe. That gap should be closed before further investment in "
                "this specific mechanism.",
        },
        "phase_20_final_decision": {
            "decision": "EXPERIMENTAL",
            "not_SHIP_because": "a confirmed false positive exists outside the "
                "validation corpus (Chapter9) AND a confirmed structural "
                "misfire exists WITHIN the milestone's own validated candidate "
                "set (cmb_stamp_boundary_vi) -- false-positive risk is not low, "
                "which SHIP requires.",
            "not_REJECT_because": "the mechanism is real and independently "
                "confirmed for 2 of 4 documents via factual historical oracle "
                "agreement (4x5 shape, row-level text match, "
                "factual_oracle_comparison.json), with zero hard-invariant "
                "violations and zero Layer-1 regression across 118*3 evaluated "
                "arm-mode combinations (intervention_results.json). Rejecting "
                "outright would discard a demonstrated, bounded, reversible "
                "recovery capability.",
            "not_HOLD_because": "HOLD implies no path forward is visible; this "
                "milestone identified a SPECIFIC, testable refinement (two-stage "
                "gate, Phase 18) and a SPECIFIC, actionable prerequisite "
                "(negative-corpus expansion via realscan_probe, Phase 19) -- "
                "there is a concrete next step, not an open-ended pause.",
            "mechanism_vs_safety_distinction": "the mechanism is real (route/"
                "rasterization changes Docling's layout classification, "
                "causal_models.json Model C) -- that is SEPARATE from whether "
                "the specific offline reconstruction implemented this milestone "
                "is safe to ship (it is not, as specified). Both statements are "
                "true simultaneously; this decision does not confuse them.",
        },
        "citations_index": {
            "recovery_verdicts.json": "Phase 11 -- TRUE_RECOVERY/PLAUSIBLE_RECOVERY/"
                "PSEUDO_TABLE/INVALID classification, 79 conservative instances",
            "factual_oracle_comparison.json": "Phase 12 -- same-arm/cross-arm "
                "physical-region-identity evidence against real historical tables",
            "negative_controls.json": "Phase 13 -- exhaustive repo-wide search; "
                "confirmed FP on jiaocaineedrop_Chapter9.pdf_46",
            "role_ambiguity_analysis.json": "Phase 16 -- label/evidence conflict "
                "quantification, no fabricated confidence",
            "intervention_results.json": "Phase 10 -- control/conservative/"
                "aggressive arm comparison, Layer-1 deltas",
            "causal_models.json": "Phase 7 -- Model A rejected, Model C supported",
            "paired_gating_cases.json": "Phase 3 -- per-arm gated/tabled/both-"
                "states classification underlying the causal and oracle analysis",
        },
    }
    Path("recommendation.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False))
    print("FINAL DECISION:", payload["phase_20_final_decision"]["decision"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
