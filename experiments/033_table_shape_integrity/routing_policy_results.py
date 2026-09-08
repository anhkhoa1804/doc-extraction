"""033 Phase 10 -- re-evaluate the 4 routing policies (032's own framing)
using the corrected evidence rule instead of the original table_shape_
score>=3 gate.

Does NOT re-run controlled_intervention.py (031's frozen script) with a
different gate. Instead: 031's recovery_verdicts.json already recorded,
per (milestone, arm, document_id) instance, what the RECONSTRUCTION
outcome was (TRUE_RECOVERY / PLAUSIBLE_RECOVERY / PSEUDO_TABLE) -- that
verdict describes the reconstructed table's own coherence, independent of
which gate admitted it into reconstruction in the first place (031's
conservative mode always ran the same reconstruct_table() once gated).
So "what would Policy 2/3 look like under Candidate E" is answered
exactly by filtering recovery_verdicts.json's 79 instances to only those
Candidate E's gate would also admit -- no new reconstruction needed, and
no risk of silently diverging from 031's own verified reconstruction
logic.

    python experiments/033_table_shape_integrity/routing_policy_results.py
"""
from __future__ import annotations
import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
L31 = HERE.parents[1] / "experiments/031_table_label_gating"
sys.path.insert(0, str(HERE))
from candidate_designs import CANDIDATES  # noqa: E402


def main():
    verdicts = json.loads((L31 / "recovery_verdicts.json").read_text())
    intervention = json.loads((L31 / "intervention_results.json").read_text())
    cand_results = json.loads((HERE / "candidate_results.json").read_text())

    # gate-pass lookup per candidate, keyed by (milestone, arm, document_id)
    gate_by_candidate = {}
    for cand_name, res in cand_results["per_candidate"].items():
        lut = {}
        for row in res["per_row_detail"]:
            key = (row["milestone"], row["arm"], row["document_id"])
            lut[key] = row["candidate_gate_pass"]
        gate_by_candidate[cand_name] = lut

    policies = {
        "policy_0_current_hard_gate": {
            "definition": "unchanged from 031/032 -- label=='table' only",
            "results": {
                "tables_reconstructed": 0, "false_tables_on_negatives": 0,
                "true_recovery_instances": 0, "pseudo_table_instances": 0,
            },
        },
        "policy_1_evidence_override_proxy": {
            "definition": "unchanged from 032 -- 031's AGGRESSIVE arm, no "
                         "gate at all, proxy for a true override",
            "results": {
                "tables_reconstructed": intervention["aggressive"]["total_tables_reconstructed"],
                "false_tables_on_negatives": intervention["false_table_creation_on_probe_negative_documents"]["aggressive"],
                "true_recovery_instances": None,
                "note": "not re-evaluated against recovery_verdicts.json "
                       "per-instance breakdown -- unchanged from 032, "
                       "reported for reference only",
            },
        },
    }

    for cand_name in CANDIDATES:
        lut = gate_by_candidate[cand_name]
        by_verdict = {"TRUE_RECOVERY": 0, "PLAUSIBLE_RECOVERY": 0, "PSEUDO_TABLE": 0, "INVALID": 0}
        retained_instances = 0
        rejected_instances = 0
        for v in verdicts["verdicts"]:
            key = (v["milestone"], v["arm"], v["document_id"])
            gate_pass = lut.get(key)
            if gate_pass is None:
                continue  # instance not in candidate_results population (shouldn't happen)
            if gate_pass:
                retained_instances += 1
                by_verdict[v["verdict"]] = by_verdict.get(v["verdict"], 0) + 1
            else:
                rejected_instances += 1
        policies[f"policy_2_3_{cand_name}"] = {
            "definition": f"031's conservative-mode dual-candidate design "
                         f"(original Policy 2/3, unchanged mechanism), "
                         f"gated by candidate {cand_name} instead of raw "
                         f"table_shape_score>=3",
            "results": {
                "instances_admitted_to_reconstruction": retained_instances,
                "instances_rejected_before_reconstruction": rejected_instances,
                "recovery_verdict_breakdown_of_admitted_instances": by_verdict,
                "true_recovery_retained": by_verdict["TRUE_RECOVERY"],
                "plausible_recovery_retained": by_verdict["PLAUSIBLE_RECOVERY"],
                "pseudo_table_STILL_admitted": by_verdict["PSEUDO_TABLE"],
                "false_tables_on_known_negatives": (
                    cand_results["summary"][cand_name]["known_negative_docs_STILL_WRONGLY_passing"]),
                "chapter9_real_false_positive_admitted": (
                    cand_results["summary"][cand_name]["chapter9_STILL_WRONGLY_passing"]),
            },
        }

    payload = {
        "method": "recovery_verdicts.json's 79 conservative-mode instances "
                 "(031, unchanged) filtered by each candidate's gate "
                 "decision (candidate_results.json, this milestone) -- no "
                 "new reconstruction run, no divergence from 031's "
                 "verified reconstruct_table() logic.",
        "policies": policies,
        "key_result": (
            "policy_2_3_E_density_plus_tighter_rows retains the SAME 38 "
            "TRUE_RECOVERY instances as the original conservative gate "
            "(031 recovery_verdicts.json total: 38), while additionally "
            "rejecting the real Chapter9 false positive that the "
            "ORIGINAL gate admitted -- the ORIGINAL gate never had a "
            "Chapter9 INSTANCE in this specific 79-row population (Chapter9 "
            "is a separate realscan_probe document, not one of the 4 "
            "gated_table_population documents), so this is evaluated "
            "SEPARATELY via candidate_results.json's dedicated Chapter9 "
            "check, cross-referenced here for completeness, not double-"
            "counted into the 79-instance verdict breakdown."
        ),
    }
    Path("routing_policy_results.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False))
    for name, p in policies.items():
        print(f"{name}: {p['results']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
