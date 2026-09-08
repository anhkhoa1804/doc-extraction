"""033 Phase 11 -- threshold sensitivity study, done ONLY after fixing the
structural conjunction issue (per this milestone's own ordering
requirement). Sweeps Candidate E's three structural floors (row_bands,
col_bands, children_per_row_band) across a reasonable range around their
chosen values, NOT to optimize against this corpus, but to check whether
the corrected rule sits in a wide safe region or balances on a knife edge.

    python experiments/033_table_shape_integrity/threshold_robustness.py
"""
from __future__ import annotations
import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
L31 = HERE.parents[1] / "experiments/031_table_label_gating"
sys.path.insert(0, str(HERE))
from adversarial_results import CASES  # noqa: E402
sys.path.insert(0, str(L31))
from table_shape_probe import compute_signals  # noqa: E402


def variant(sig, row_floor, col_floor, density_floor):
    row_evidence = bool(sig["row_bands"] and sig["row_bands"] >= row_floor)
    col_evidence = bool(sig["col_bands"] and sig["col_bands"] >= col_floor)
    grid_density = bool(sig["children_per_row_band"] and sig["children_per_row_band"] >= density_floor)
    return row_evidence and col_evidence and grid_density


def main():
    probe = json.loads((L31 / "table_shape_probe.json").read_text())
    negctl = json.loads((L31 / "negative_controls.json").read_text())

    confirmed_positive_rows = [r for r in probe["all_positive_rows"] if r.get("is_table_ground_truth")]
    known_negative_rows = [r for r in probe["all_positive_rows"] if not r.get("is_table_ground_truth")]
    chapter9_row = next(r for r in negctl["realscan_probe_population"]["regions_scored"]
                        if r["document_id"] == "jiaocaineedrop_Chapter9.pdf_46" and r["region_index"] == 0)

    # pre-compute synthetic case signals once
    synth_sigs = [(c, compute_signals(c["region_bbox"], c["children"])) for c in CASES]

    row_range = [2, 3, 4, 5]
    col_range = [2, 3, 4]
    density_range = [1.0, 1.5, 2.0, 2.5]

    sweep = []
    for rf in row_range:
        for cf in col_range:
            for df in density_range:
                true_recovery_pass = sum(1 for r in confirmed_positive_rows
                                        if variant(r["signals"], rf, cf, df))
                known_negative_pass = sum(1 for r in known_negative_rows
                                         if variant(r["signals"], rf, cf, df))
                chapter9_pass = variant(chapter9_row["signals"], rf, cf, df)
                synth_correct = 0
                synth_undecidable = 0
                for c, sig in synth_sigs:
                    gt = c["ground_truth_by_construction"]
                    if gt == "AMBIGUOUS_BY_DESIGN":
                        synth_undecidable += 1
                        continue
                    expected = gt == "table"
                    if variant(sig, rf, cf, df) == expected:
                        synth_correct += 1
                sweep.append({
                    "row_floor": rf, "col_floor": cf, "density_floor": df,
                    "true_recovery_retained": true_recovery_pass,
                    "true_recovery_total": len(confirmed_positive_rows),
                    "true_recovery_retention_rate": round(true_recovery_pass / len(confirmed_positive_rows), 4),
                    "known_negative_false_positives": known_negative_pass,
                    "chapter9_false_positive": chapter9_pass,
                    "synthetic_correct": synth_correct,
                    "synthetic_total_decidable": len(synth_sigs) - synth_undecidable,
                    "synthetic_accuracy": round(synth_correct / (len(synth_sigs) - synth_undecidable), 4),
                })

    # the chosen operating point (Candidate E)
    chosen = next(s for s in sweep if s["row_floor"] == 3 and s["col_floor"] == 2 and s["density_floor"] == 1.5)

    # stability check: how many of the 48 grid points achieve BOTH full
    # true-recovery retention AND zero Chapter9/known-negative FPs?
    fully_safe_points = [s for s in sweep if s["true_recovery_retention_rate"] == 1.0
                         and s["known_negative_false_positives"] == 0
                         and s["chapter9_false_positive"] is False]

    payload = {
        "method": "grid sweep over Candidate E's 3 structural floors "
                 "(row_bands, col_bands, children_per_row_band) across a "
                 f"{len(row_range)}x{len(col_range)}x{len(density_range)}="
                 f"{len(row_range)*len(col_range)*len(density_range)}-point "
                 "grid, measured against the REAL confirmed-positive "
                 "population (79 instances, 031), the REAL known-negative "
                 "population (39 instances, 031), the REAL Chapter9 false "
                 "positive (031/032), and the 46-case synthetic "
                 "adversarial suite (Phase 5) -- not optimized against any "
                 "single one of these.",
        "sweep": sweep,
        "chosen_operating_point_candidate_E": chosen,
        "fully_safe_region": {
            "n_points_out_of": f"{len(fully_safe_points)}/{len(sweep)}",
            "points": fully_safe_points,
        },
        "finding": (
            f"{len(fully_safe_points)} of {len(sweep)} grid points achieve "
            f"simultaneously: 100% true-recovery retention on the real "
            f"79-instance confirmed population, 0 false positives on the "
            f"real 39-instance known-negative population, AND correct "
            f"rejection of the real Chapter9 case. "
            + ("This is a WIDE safe region, not a knife-edge threshold -- "
               "the corrected rule's behavior is stable across a "
               "meaningful range of the 3 structural floors."
               if len(fully_safe_points) >= len(sweep) * 0.25 else
               "This is a NARROW safe region -- small changes to any of "
               "the 3 floors move the rule out of the safe zone, which is "
               "itself a finding: the corrected rule may be more fragile "
               "than its single chosen operating point suggests.")
        ),
    }
    Path("threshold_robustness.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False))
    print(f"grid points: {len(sweep)}")
    print(f"fully safe (100% TP retention + 0 known FP + Chapter9 rejected): "
          f"{len(fully_safe_points)}")
    print(f"chosen point (row>=3,col>=2,density>=1.5): {chosen}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
