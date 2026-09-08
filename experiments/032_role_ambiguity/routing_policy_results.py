"""032 Phase 9/10 -- compare 4 offline routing policies using 031's already-
executed intervention arms, rather than re-implementing and re-running
extraction. Where a policy has no direct 031 analog, this is stated
explicitly rather than silently substituted.

  Policy 0 -- current hard gate: label == table -> table, else no table.
              == 031's CONTROL arm exactly.
  Policy 1 -- evidence override: strong table evidence -> table
              (unconditionally, no defer). NOT directly tested by 031 in
              its literal "replace/override" form (031's own Phase 9
              rejected Option A -- label relaxation -- specifically
              because it destroys the original label with no fallback).
              031's AGGRESSIVE arm is the closest available proxy: it acts
              on any evidence (>=1 nested child) with NO ambiguity gate,
              but -- unlike a true override -- still preserves the
              original picture label alongside the new table, so it is a
              LOWER-RISK proxy for Policy 1, not an exact implementation.
  Policy 2 -- ambiguity-aware defer: clear role -> normal route; ambiguous
              role -> targeted specialist. == 031's CONSERVATIVE arm
              (probe-gated at threshold 3) exactly.
  Policy 3 -- candidate-role routing: region -> candidate roles ->
              specialist selected by evidence. 031's CONSERVATIVE arm's
              actual IMPLEMENTATION already does this in miniature (keeps
              the original picture element AND adds a table candidate
              alongside, provenance-marked) -- so Policy 2 and Policy 3
              are THE SAME TESTED MECHANISM in this repository's existing
              artifacts. This is reported explicitly, not hidden: 031
              never built a policy that picks ONE specialist to the
              exclusion of the other.

    python experiments/032_role_ambiguity/routing_policy_results.py
"""
from __future__ import annotations
import json
from pathlib import Path
HERE = Path(__file__).resolve().parent
L31 = HERE.parents[1] / "experiments/031_table_label_gating"


def main():
    intervention = json.loads((L31 / "intervention_results.json").read_text())
    verdicts = json.loads((L31 / "recovery_verdicts.json").read_text())

    def agg(mode_rows):
        n = len(mode_rows) or 1
        return {
            "n_rows": len(mode_rows),
            "mean_text_recall": round(sum(r["layer1"]["text_recall"] for r in mode_rows) / n, 4),
            "mean_char_recall": round(sum(r["layer1"]["char_recall"] for r in mode_rows) / n, 4),
            "docs_hallucinated": sum(1 for r in mode_rows if r["layer1"]["hallucinated"]),
        }

    policies = {
        "policy_0_current_hard_gate": {
            "definition": "label == 'table' -> table pipeline; else -> no "
                         "table, ever, for that region.",
            "implementation_status": "PRODUCTION, as-is",
            "031_analog": "control arm, exact match",
            "results": {
                **agg(intervention["rows"]["control"]),
                "tables_reconstructed": intervention["control"]["total_tables_reconstructed"],
                "false_tables_on_negatives": intervention["false_table_creation_on_probe_negative_documents"]["control"],
                "true_recovery_on_confirmed_docs": intervention["true_table_recovery_on_confirmed_gated_documents"]["control"],
            },
        },
        "policy_1_evidence_override": {
            "definition": "strong table evidence -> table, UNCONDITIONALLY "
                         "(no ambiguity defer, no dual-candidate retention "
                         "-- a true override would REPLACE the label).",
            "implementation_status": "NEVER IMPLEMENTED as literally "
                                     "specified -- 031 Phase 9 explicitly "
                                     "rejected this (Option A, 'label "
                                     "relaxation') on provenance grounds "
                                     "before any implementation was "
                                     "attempted.",
            "031_analog": "AGGRESSIVE arm is the closest PROXY (acts on "
                         "any evidence >=1 child, no ambiguity gate) but "
                         "is NOT a true override -- it still preserves "
                         "the original picture label, so its false-"
                         "positive numbers UNDERSTATE what a true Policy 1 "
                         "override would risk (a true override could not "
                         "be walked back; the aggressive arm's mistakes "
                         "can be, since the original label survives).",
            "results": {
                **agg(intervention["rows"]["aggressive"]),
                "tables_reconstructed": intervention["aggressive"]["total_tables_reconstructed"],
                "false_tables_on_negatives": intervention["false_table_creation_on_probe_negative_documents"]["aggressive"],
                "true_recovery_on_confirmed_docs": intervention["true_table_recovery_on_confirmed_gated_documents"]["aggressive"],
            },
            "caveat": "39/39 false tables on known negatives under this "
                     "proxy -- and a TRUE override (no fallback label) "
                     "would make every one of those 39 a silent, "
                     "unrecoverable mislabeling, not merely an added "
                     "(reversible) candidate.",
        },
        "policy_2_ambiguity_aware_defer": {
            "definition": "clear role -> normal route; ambiguous role "
                         "(evidence conflicts with label, score >= "
                         "threshold) -> targeted specialist, ORIGINAL "
                         "LABEL PRESERVED.",
            "implementation_status": "IMPLEMENTED AND TESTED -- 031 "
                                     "CONSERVATIVE arm, probe threshold=3.",
            "031_analog": "conservative arm, exact match",
            "results": {
                **agg(intervention["rows"]["conservative"]),
                "tables_reconstructed": intervention["conservative"]["total_tables_reconstructed"],
                "false_tables_on_negatives": intervention["false_table_creation_on_probe_negative_documents"]["conservative"],
                "true_recovery_on_confirmed_docs": intervention["true_table_recovery_on_confirmed_gated_documents"]["conservative"],
                "recovery_verdict_breakdown": verdicts["counts"],
            },
        },
        "policy_3_candidate_role_routing": {
            "definition": "region -> candidate roles (evidence-ranked) -> "
                         "specialist(s) selected by evidence, BOTH "
                         "surviving results kept with provenance.",
            "implementation_status": "IDENTICAL MECHANISM to Policy 2 in "
                                     "this repository's actual artifacts "
                                     "-- 031's conservative-mode "
                                     "reconstruction ALREADY keeps the "
                                     "original picture element AND adds a "
                                     "provenance-marked table candidate "
                                     "alongside it (controlled_"
                                     "intervention.py: pg.setdefault"
                                     "('tables', []).append(...), plus "
                                     "el.extra['031_table_candidate_"
                                     "added']). Policy 2 and Policy 3 are "
                                     "NOT two different tested mechanisms "
                                     "-- 031 never built a version of "
                                     "Policy 2 that discards the runner-up.",
            "031_analog": "conservative arm, same underlying result as Policy 2",
            "results": "IDENTICAL to policy_2_ambiguity_aware_defer -- see "
                      "above; not restated to avoid implying a second, "
                      "independent measurement exists.",
        },
    }

    payload = {
        "method": "reuse 031's already-executed control/conservative/"
                 "aggressive intervention arms as the offline test of "
                 "each policy, rather than re-running extraction. Where a "
                 "policy has no faithful 031 analog (Policy 1's literal "
                 "override semantics), this is stated explicitly, and the "
                 "closest available proxy is used with its limitations "
                 "named, not hidden.",
        "policies": policies,
        "stability_across_arms": (
            "all 4 policies were evaluated over the IDENTICAL 118-row "
            "population (031 intervention_results.json), so a policy's "
            "behavior is directly comparable across the SAME documents "
            "and arms -- not measured on different samples."
        ),
        "verdict": (
            "Policy 2/3 (evidence-gated, dual-candidate, provenance-"
            "preserving) is the only policy tested this milestone or 031 "
            "that shows zero false tables on the known negative population "
            "while recovering true structure on the confirmed documents. "
            "Policy 1 (proxy) shows real recall gain but 39/39 false "
            "positives on the same negatives -- and, taken literally "
            "(actual label override, not the tested proxy), would make "
            "every one of those unrecoverable. Policy 0 recovers nothing. "
            "Policy 3 is not a distinct measurement from Policy 2 in this "
            "repository's history -- an important finding in itself: the "
            "'candidate-role routing' architecture this milestone set out "
            "to evaluate as a NEW idea (Phase 9's framing) was already "
            "implicitly built by 031, under a different name."
        ),
    }
    Path("routing_policy_results.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False))
    print("Policy 0 (control):", policies["policy_0_current_hard_gate"]["results"])
    print("Policy 1 (aggressive proxy):", policies["policy_1_evidence_override"]["results"])
    print("Policy 2/3 (conservative, dual-candidate):", policies["policy_2_ambiguity_aware_defer"]["results"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
