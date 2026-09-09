"""035 Phase 17 -- intervention counterfactual, for confirmed/probable D2
cases only. Uses EXISTING factual evidence already measured (Phase 12's
table-shape rule applied to real D2 regions, Phase 13's false-positive
rate on real non-table regions) -- no new Table Transformer run, no
production change. Simulates: current (hard label gate) vs counterfactual
(admit table-shape-positive non-table regions to table processing).

    python experiments/035_mechanism_d_gating/phase17_counterfactual.py
"""
from __future__ import annotations
import json
from pathlib import Path
HERE = Path(__file__).resolve().parent


def main():
    mech_d = json.loads((HERE / "mechanism_d_population.json").read_text())
    shape = json.loads((HERE / "table_shape_on_gt.json").read_text())

    fp_path = HERE / "false_positive_tables.json"
    fp = json.loads(fp_path.read_text()) if fp_path.exists() else None

    n_d2 = shape["d2_population_size_this_run"]
    n_recognized = shape["n_d2_cases_rule_would_recognize"]
    recognition_fraction = shape["recognition_fraction"]

    n_fp_eligible = shape["false_positive_side"]["n_non_table_regions_with_ge4_tokens"]
    n_fp_fires = shape["false_positive_side"]["n_rule_fires_on_non_table_region"]
    fp_fire_fraction_on_d2_pages = round(n_fp_fires / n_fp_eligible, 4) if n_fp_eligible else None

    result = {
        "scope": "Confirmed D2 (strict Mechanism-D) cases only, per Phase 5's own "
            f"population ({mech_d['strict_mechanism_d_count']} of "
            f"{mech_d['n_gt_tables_analyzed']} analyzed).",
        "current_policy": "Hard label gate: only region.label.lower()=='table' ever "
            "reaches Table Transformer (pipelines/base.py:747).",
        "counterfactual_policy": "Admit any region for which 033's table-shape rule "
            "(row_bands>=3 AND col_bands>=2 AND children_per_row_band>=1.5) fires, "
            "REGARDLESS of its Docling label, to table processing.",
        "recovery_side": {
            "n_d2_cases_that_would_become_eligible": n_recognized,
            "n_d2_cases_total": n_d2,
            "recovery_fraction_of_d2": recognition_fraction,
            "note": "This is an UPPER BOUND on recovery: 'eligible for Table Transformer' "
                "is not the same as 'Table Transformer would succeed and produce a "
                "structurally valid table' -- D4/D5/D6 failure modes still apply to any "
                "newly-admitted region. No claim of guaranteed recovery is made.",
        },
        "false_positive_exposure_side": {
            "source": ("measured directly on Phase 13's non-table-page sample" if fp else
                       "PENDING -- Phase 13 (false_positive_tables.json) has not run yet; "
                       "this section uses the SMALLER within-Phase-12 check "
                       "(non-table regions on D2-relevant pages only) as a preliminary "
                       "lower-confidence estimate, NOT a substitute for Phase 13's full "
                       "sweep. Rerun this script after Phase 13 completes."),
            "n_eligible_non_table_regions_checked": n_fp_eligible,
            "n_would_newly_fire": n_fp_fires,
            "fire_fraction": fp_fire_fraction_on_d2_pages,
            "phase13_full_sample_result": (
                {
                    "n_findings_no_gt_overlap": fp["n_findings_no_gt_overlap"],
                    "classification_counts": fp["classification_counts"],
                } if fp else None
            ),
        },
        "specialist_cost_side": {
            "additional_specialist_invocations_per_665_gt_tables_at_full_scale":
                round(n_recognized / n_d2 * mech_d["strict_mechanism_d_count"], 1) if n_d2 else None,
            "note": "Table Transformer's own measured cost is small relative to layout "
                "(034a pipeline_timing.json: table stage ~4% of pipeline time, mean "
                "0.335s/page) -- compute cost of admitting more candidates is not "
                "expected to be the binding constraint; false-positive/structural-risk is.",
        },
        "net_assessment": (
            "PENDING full data" if (n_d2 < 5 or fp is None) else
            "See recovery_fraction_of_d2 vs false-positive fire_fraction: a rule that "
            "recovers most D2 cases while firing rarely on genuine non-table content "
            "supports Option A/B (Phase 18); one that fires broadly on ordinary prose "
            "does not, regardless of recovery fraction."
        ),
    }
    Path(HERE / "counterfactual_gating.json").write_text(json.dumps(result, indent=1, ensure_ascii=False))
    print(json.dumps(result["recovery_side"], indent=1))
    print(json.dumps(result["false_positive_exposure_side"], indent=1)[:500])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
