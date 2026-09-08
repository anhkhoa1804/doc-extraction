"""033 Phase 3 -- minimal correction candidates for table_shape_score's
row-AND-column conjunction gap (known_failure.json).

Every candidate is derived directly from the 5 existing criteria in
031/table_shape_probe.py's table_shape_score -- no new signal is
invented that isn't already computed by compute_signals(). Each is
implemented as a real, importable function so Phase 4/5 can run them
against real and synthetic data without re-deriving logic.

    python experiments/033_table_shape_integrity/candidate_designs.py
"""
from __future__ import annotations
import json
from pathlib import Path
HERE = Path(__file__).resolve().parent


def candidate_A_conjunctive_gate(sig):
    """Keep the existing additive score UNCHANGED; add a hard prerequisite
    that BOTH axes show independent multi-band evidence before the score
    is even consulted. Minimal diff from the current rule -- one extra
    boolean AND on the final decision, no change to point accumulation."""
    score, reasons = 0, []
    if sig["row_bands"] and sig["row_bands"] >= 2:
        score += 1; reasons.append("multi-row")
    if sig["col_bands"] and sig["col_bands"] >= 2:
        score += 1; reasons.append("multi-column")
    if sig["children_per_row_band"] and sig["children_per_row_band"] >= 2:
        score += 1; reasons.append("multiple children per row (grid, not a list)")
    if sig["row_regularity_cv"] is not None and sig["row_regularity_cv"] < 0.5:
        score += 1; reasons.append("regular row spacing")
    if sig["n_nested_text_regions"] >= 6:
        score += 1; reasons.append("high nested-text-region count")
    row_evidence = bool(sig["row_bands"] and sig["row_bands"] >= 2)
    col_evidence = bool(sig["col_bands"] and sig["col_bands"] >= 2)
    two_axis_gate = row_evidence and col_evidence
    passes = (score >= 3) and two_axis_gate
    return passes, score, reasons, {"two_axis_gate": two_axis_gate,
                                    "row_evidence": row_evidence, "col_evidence": col_evidence}


def candidate_B_2d_or_strict_column(sig):
    """OR of (A's two-axis gate) with a STRICTER column-only fallback for
    genuinely column-dominant structures the row-band clustering might
    under-count rows for (e.g. a single-row, many-column header-only
    fragment) -- explicitly does NOT relax the row-only side, only adds a
    column-dominant escape hatch, since row-only evidence is exactly
    what known_failure.json shows is unsafe."""
    passes_a, score, reasons, detail = candidate_A_conjunctive_gate(sig)
    strong_column_fallback = bool(
        sig["col_bands"] and sig["col_bands"] >= 3
        and sig["col_regularity_cv"] is not None and sig["col_regularity_cv"] < 0.3
        and sig["children_per_row_band"] and sig["children_per_row_band"] >= 2
    )
    passes = passes_a or strong_column_fallback
    detail = {**detail, "strong_column_fallback": strong_column_fallback}
    return passes, score, reasons, detail


def candidate_C_pure_structural_predicate(sig):
    """Drop the point system entirely for the GATING decision. Only 3
    structural predicates matter: row_bands>=2, col_bands>=2,
    children_per_row_band>=1.5 (a real grid needs items actually shared
    across BOTH axes, not merely counted bands). row_regularity_cv and
    n_nested_text_regions become DIAGNOSTIC ONLY (still computed and
    reported, never gate the decision) -- tests whether the corpus-tuned
    regularity/count thresholds were adding real signal or just
    coincidentally correlated with the known positives."""
    row_evidence = bool(sig["row_bands"] and sig["row_bands"] >= 2)
    col_evidence = bool(sig["col_bands"] and sig["col_bands"] >= 2)
    grid_density = bool(sig["children_per_row_band"] and sig["children_per_row_band"] >= 1.5)
    passes = row_evidence and col_evidence and grid_density
    reasons = [r for r, ok in [("multi-row", row_evidence), ("multi-column", col_evidence),
                               ("grid-density>=1.5", grid_density)] if ok]
    return passes, None, reasons, {"row_evidence": row_evidence, "col_evidence": col_evidence,
                                   "grid_density": grid_density}


def candidate_D_conjunctive_gate_tighter_rows(sig):
    """Candidate A's conjunctive gate, PLUS 031's own row_bands>=3
    HYPOTHESIS (031 FINAL_REPORT.md section 9: 'raising the probe's
    row_bands floor from >=2 to >=3 would exclude Chapter9 while
    retaining all 4 known positives' -- stated there as an n=1,
    unvalidated hypothesis). Added here because candidate_results.json's
    FIRST run showed A/B/C all still wrongly admit the REAL Chapter9 false
    positive (col_bands=4 there, so the row/col conjunction alone does not
    exclude it -- its actual anomaly is row_bands=2, too few rows, not too
    few columns). This directly tests 031's own hypothesis rather than
    leaving it unvalidated."""
    row_evidence = bool(sig["row_bands"] and sig["row_bands"] >= 3)
    col_evidence = bool(sig["col_bands"] and sig["col_bands"] >= 2)
    score, reasons = 0, []
    if sig["row_bands"] and sig["row_bands"] >= 2:
        score += 1; reasons.append("multi-row")
    if sig["col_bands"] and sig["col_bands"] >= 2:
        score += 1; reasons.append("multi-column")
    if sig["children_per_row_band"] and sig["children_per_row_band"] >= 2:
        score += 1; reasons.append("multiple children per row (grid, not a list)")
    if sig["row_regularity_cv"] is not None and sig["row_regularity_cv"] < 0.5:
        score += 1; reasons.append("regular row spacing")
    if sig["n_nested_text_regions"] >= 6:
        score += 1; reasons.append("high nested-text-region count")
    passes = (score >= 3) and row_evidence and col_evidence
    return passes, score, reasons, {"row_evidence_floor_3": row_evidence,
                                    "col_evidence": col_evidence}


def candidate_E_density_plus_tighter_rows(sig):
    """C's density predicate (children_per_row_band>=1.5, no score/
    regularity dependency -- best raw correctness in Phase 5's 42-case
    synthetic sweep, 32/42) combined with D's row_bands>=3 floor (the
    only candidate that rejects the REAL Chapter9 false positive).
    Added after Phase 5 found C and D each fix problems the other
    doesn't: C correctly handles sparse 2-row real tables (cases 6/44)
    that D's tighter row floor wrongly rejects; D correctly rejects the
    real Chapter9 case that C (row floor only >=2) does not. Tests
    whether combining them dominates both or just moves the trade-off."""
    row_evidence = bool(sig["row_bands"] and sig["row_bands"] >= 3)
    col_evidence = bool(sig["col_bands"] and sig["col_bands"] >= 2)
    grid_density = bool(sig["children_per_row_band"] and sig["children_per_row_band"] >= 1.5)
    passes = row_evidence and col_evidence and grid_density
    reasons = [r for r, ok in [("multi-row>=3", row_evidence), ("multi-column", col_evidence),
                               ("grid-density>=1.5", grid_density)] if ok]
    return passes, None, reasons, {"row_evidence_floor_3": row_evidence,
                                   "col_evidence": col_evidence, "grid_density": grid_density}


CANDIDATES = {
    "A_conjunctive_gate": {
        "fn": candidate_A_conjunctive_gate,
        "exact_rule": "table_shape_score (UNCHANGED, 5 additive criteria, "
                     "threshold>=3) AND row_bands>=2 AND col_bands>=2",
        "rationale": "smallest possible diff from the shipped 031 rule -- "
                    "adds exactly the AND-gate 031/032's own recommendation "
                    "already specified, changes nothing else",
        "expected_TP_impact": "should retain every known TRUE_RECOVERY/"
                             "PLAUSIBLE_RECOVERY case (031 recovery_"
                             "verdicts.json), since all 4 confirmed positive "
                             "documents have col_bands>=4 (table_shape_probe.json)",
        "expected_FP_impact": "should reject known_failure.json's single-"
                             "column prose case (col_bands=1 always) and "
                             "032's real Chapter9 case IF its col_bands<2 "
                             "-- Chapter9 actually has col_bands=4 "
                             "(negative_controls.json), so Candidate A "
                             "alone does NOT fix the Chapter9 false "
                             "positive, only the prose one. Tested in Phase 4.",
        "failure_modes": "does not address Chapter9-style false positives "
                        "that DO have genuine multi-column evidence "
                        "(banner/header layouts with multiple aligned "
                        "text blocks are not exclusively single-column)",
        "complexity": "LOW -- one boolean AND",
    },
    "B_2d_or_strict_column": {
        "fn": candidate_B_2d_or_strict_column,
        "exact_rule": "A's rule OR (col_bands>=3 AND col_regularity_cv<0.3 "
                     "AND children_per_row_band>=2)",
        "rationale": "handles a structural edge case A might unfairly "
                    "reject -- a real table fragment with very few rows "
                    "but strong, regular multi-column evidence",
        "expected_TP_impact": "same as A plus recovers any hypothetical "
                             "column-dominant fragment A would reject; no "
                             "such case is KNOWN to exist in the current "
                             "corpus (tested in Phase 4/6)",
        "expected_FP_impact": "HIGHER RISK than A -- the fallback clause "
                             "could admit a genuinely multi-column, "
                             "regularly-spaced NON-table (e.g. a real "
                             "multi-column newspaper layout, 032's own "
                             "case 17 'multi-column paragraph' from "
                             "adversarial_controls.json, flagged there as "
                             "'the single most concerning case')",
        "failure_modes": "multi-column prose is the direct adversarial "
                        "target this fallback is most likely to admit "
                        "incorrectly -- tested explicitly in Phase 5",
        "complexity": "MEDIUM -- two rule branches, more parameters",
    },
    "C_pure_structural_predicate": {
        "fn": candidate_C_pure_structural_predicate,
        "exact_rule": "row_bands>=2 AND col_bands>=2 AND "
                     "children_per_row_band>=1.5 (no point system, no "
                     "regularity/count criteria in the gate)",
        "rationale": "tests whether row_regularity_cv/n_nested_text_regions "
                    "were adding real discriminating signal beyond the two "
                    "structural axis checks, or were corpus-tuned "
                    "coincidence -- the milestone's own 'do not train a "
                    "black-box, prefer the smallest interpretable rule' "
                    "principle taken to its logical conclusion",
        "expected_TP_impact": "UNKNOWN without running it -- the 4 "
                             "confirmed positives all have children_per_"
                             "row_band 4.0-4.67 (table_shape_probe.json), "
                             "comfortably above 1.5, so likely retained; "
                             "tested in Phase 4",
        "expected_FP_impact": "removes regularity as a shield -- a "
                             "genuinely irregular but 2D-structured false "
                             "positive would pass here where A/B's "
                             "regularity criterion (inherited from the "
                             "original score) might have excluded it. "
                             "No point-count safety net at all.",
        "failure_modes": "the simplest rule, so the least defended against "
                        "any failure mode NOT captured by row+col+density "
                        "-- e.g. would not catch a chart with scattered "
                        "but coincidentally 2-banded annotations",
        "complexity": "LOWEST -- 3 boolean predicates, no scoring, no "
                     "point threshold to tune",
    },
    "D_conjunctive_gate_tighter_rows": {
        "fn": candidate_D_conjunctive_gate_tighter_rows,
        "exact_rule": "table_shape_score (unchanged) >= 3 AND row_bands>=3 "
                     "AND col_bands>=2",
        "rationale": "ADDED AFTER Phase 4's first run showed A/B/C all "
                    "still wrongly admit the REAL Chapter9 false positive "
                    "(negative_controls.json: row_bands=2, col_bands=4 -- "
                    "col evidence was never the missing piece for this "
                    "real case). Directly tests 031 FINAL_REPORT.md "
                    "section 9's own row_bands>=3 hypothesis, previously "
                    "unvalidated beyond n=1.",
        "expected_TP_impact": "031's own table_shape_probe.json shows all "
                             "4 confirmed positives have row_bands 3-4 -- "
                             "should retain all of them",
        "expected_FP_impact": "should reject Chapter9 (row_bands=2) where "
                             "A/B/C do not; still needs testing against "
                             "known_failure.json's prose case and the "
                             "expanded adversarial suite",
        "failure_modes": "raises the row floor specifically to exclude "
                        "ONE real observed case (n=1) -- exactly the kind "
                        "of narrow fit this milestone's own rule #9 warns "
                        "against optimizing for; reported with that "
                        "caveat explicitly, not hidden",
        "complexity": "LOW -- same shape as A, one constant changed",
    },
    "E_density_plus_tighter_rows": {
        "fn": candidate_E_density_plus_tighter_rows,
        "exact_rule": "row_bands>=3 AND col_bands>=2 AND "
                     "children_per_row_band>=1.5 (C's density predicate, "
                     "D's row floor, no score/regularity dependency at all)",
        "rationale": "ADDED AFTER Phase 5's 42-case synthetic sweep found "
                    "C and D each independently fix problems the other "
                    "does not (C: correctly handles sparse 2-row tables "
                    "D wrongly rejects; D: correctly rejects the REAL "
                    "Chapter9 false positive that C does not) -- tests "
                    "whether the combination dominates both.",
        "expected_TP_impact": "same as D on the real corpus (row_bands "
                             "3-4 for all 4 confirmed positives); may "
                             "still reject synthetic sparse 2-row cases "
                             "like D does, since it inherits D's row "
                             "floor -- tested directly, not assumed",
        "expected_FP_impact": "should match or beat both C and D "
                             "individually on the 42-case suite; tested "
                             "directly",
        "failure_modes": "inherits BOTH candidates' individual failure "
                        "modes where they overlap (multi-column prose, "
                        "empty-text decorative grids, sparse 2-row tables)",
        "complexity": "LOW-MEDIUM -- 3 predicates, no score",
    },
}


def main():
    payload = {
        "principle": "every candidate is derived from compute_signals()'s "
                    "EXISTING 8 fields -- no new geometric feature is "
                    "introduced. Candidates differ only in how those "
                    "fields combine into a decision.",
        "candidates": {k: {kk: vv for kk, vv in v.items() if kk != "fn"}
                      for k, v in CANDIDATES.items()},
        "not_selected_but_considered": {
            "raise_the_threshold_to_4_or_5": (
                "EXPLICITLY REJECTED per this milestone's non-negotiable "
                "rule #1 ('do not simply raise the threshold') -- also "
                "would not even fix known_failure.json's case, since a "
                "sufficiently long single-column block still accumulates "
                "the same 3 points regardless of threshold; a 4th/5th "
                "point never becomes available without column evidence "
                "existing as its own criterion, but raising the bar to "
                "4 would ALSO reject some genuine positives without "
                "addressing the mechanism."
            ),
            "require_n_cols_greater_than_1_alone": (
                "EXPLICITLY REJECTED per non-negotiable rule #2 -- this is "
                "literally Candidate A/B/C's col_bands>=2 term in "
                "isolation, without the row+density companions; tested "
                "separately in Phase 8 against synthetic one-column "
                "tables specifically to check whether it wrongly excludes "
                "legitimate one-column tables."
            ),
        },
    }
    Path("candidate_designs.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False))
    print(f"candidates: {list(CANDIDATES)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
