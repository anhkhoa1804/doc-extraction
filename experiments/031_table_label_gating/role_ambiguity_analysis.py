"""031 Phase 16 -- does a hard single-label gate discard useful role
uncertainty?

`region.label == "table"` (gating_contract.json, base.py:747) is a hard,
mutually-exclusive classification: a region is either routed to the table
pipeline or it is not, with no representation of how confident that
decision was. Docling itself provides no confidence field to consult
(gating_contract.json stage 1: confidence=None is hardcoded, not a
discarded signal -- the stable API exposes none).

This computes, for every picture/chart-labelled region this milestone has
evidence for (the 4 CONFIRMED gated-table documents, the 3 weak negatives,
AND Phase 13's newly-found realscan_probe documents), the only LEGITIMATE
table-likelihood evidence available: `table_shape_evidence_score` --
deliberately NOT named "confidence" (Phase 17's explicit rule) because it
is a hand-authored geometric heuristic, not a model probability.

No picture-likelihood score is fabricated to sit alongside it: Docling
provides no such signal, and inventing one would violate the same rule
this analysis is trying to enforce. "Ambiguity" is instead reported as a
qualitative fact: does the hard label (picture) conflict with the
structural evidence (table_shape_evidence_score >= the conservative
threshold)? Both TRUE recoveries and the Chapter9 false positive
(negative_controls.json) satisfy this same conflict criterion, which is
itself the central finding: raw ambiguity-detection is not the same as
correct table/picture discrimination.

    python experiments/031_table_label_gating/role_ambiguity_analysis.py
"""
from __future__ import annotations
import json
from pathlib import Path
HERE = Path(__file__).resolve().parent

THRESHOLD = 3  # the conservative intervention's own gate, table_shape_probe.json


def main():
    probe = json.loads((HERE / "table_shape_probe.json").read_text())
    neg = json.loads((HERE / "negative_controls.json").read_text())
    verdicts = json.loads((HERE / "recovery_verdicts.json").read_text())

    verdict_by_doc = {}
    for v in verdicts["verdicts"]:
        verdict_by_doc.setdefault(v["document_id"], set()).add(v["verdict"])

    rows = []
    seen_docs = set()
    for r in probe["all_positive_rows"] + probe["all_negative_rows"]:
        did = r["document_id"]
        if did in seen_docs:
            continue
        seen_docs.add(did)
        score = r["table_shape_score"]
        rows.append({
            "document_id": did,
            "source_corpus": "031_known_population (stamp-vi synthetic + scan_cohort)",
            "original_docling_label": r.get("region_label", "picture"),
            "docling_confidence_available": False,
            "table_shape_evidence_score": score,
            "score_reasons": r["score_reasons"],
            "label_vs_evidence_conflict": score >= THRESHOLD,
            "recovery_verdicts_observed": sorted(verdict_by_doc.get(did, [])) or None,
            "ground_truth": (
                "CONFIRMED_TABLE (factual oracle or TRUE_RECOVERY/PLAUSIBLE_RECOVERY "
                "verdict exists)" if did in verdict_by_doc and
                verdict_by_doc[did] & {"TRUE_RECOVERY", "PLAUSIBLE_RECOVERY"}
                else "CONFIRMED_NOT_TABLE (Phase 4-6 negative population / "
                     "PSEUDO_TABLE verdict)" if score < THRESHOLD or
                     (did in verdict_by_doc and verdict_by_doc[did] == {"PSEUDO_TABLE"})
                else "UNVERIFIED"
            ),
        })

    for r in neg["realscan_probe_population"]["regions_scored"]:
        did = f"{r['document_id']}#region{r['region_index']}"
        rows.append({
            "document_id": did,
            "source_corpus": "realscan_probe (Phase 13 discovery -- genuinely diverse "
                             "real-world documents, no relation to the stamp-vi corpus)",
            "original_docling_label": "picture",
            "docling_confidence_available": False,
            "table_shape_evidence_score": r["table_shape_score"],
            "score_reasons": r["score_reasons"],
            "label_vs_evidence_conflict": r["table_shape_score"] >= THRESHOLD,
            "recovery_verdicts_observed": None,
            "ground_truth": (
                f"CONFIRMED_NOT_TABLE ({r['ground_truth_evidence']})"
                if r["ground_truth"] == "NOT_A_TABLE" else r["ground_truth"]),
        })

    conflicts = [r for r in rows if r["label_vs_evidence_conflict"]]
    conflicts_confirmed_table = [r for r in conflicts if "CONFIRMED_TABLE" in r["ground_truth"]]
    conflicts_confirmed_not_table = [r for r in conflicts if "CONFIRMED_NOT_TABLE" in r["ground_truth"]]

    payload = {
        "concept": (
            "region -> role_candidates(evidence) -> routing, instead of "
            "region.label == 'table' -> table_pipeline. This is an OFFLINE "
            "CONCEPTUAL EXPERIMENT ONLY -- not implemented in production."
        ),
        "legitimate_evidence_available": {
            "table_likelihood": "table_shape_evidence_score (0-5), a deterministic "
                               "geometric heuristic over Docling's own nested-child "
                               "regions -- named to NEVER be confused with a model "
                               "confidence (Phase 17 rule).",
            "picture_likelihood": "NONE -- Docling's stable API exposes no confidence "
                                  "field for the 'picture' label either (same gap "
                                  "documented in gating_contract.json stage 1). No "
                                  "synthetic picture-confidence is fabricated here.",
        },
        "conservative_threshold_used": THRESHOLD,
        "rows": rows,
        "summary": {
            "n_regions_evaluated": len(rows),
            "n_label_vs_evidence_conflicts": len(conflicts),
            "conflicts_that_were_confirmed_tables": len(conflicts_confirmed_table),
            "conflicts_that_were_confirmed_NOT_tables": len(conflicts_confirmed_not_table),
        },
        "finding": (
            f"{len(conflicts)} of {len(rows)} evaluated picture-labelled regions "
            f"produce a label/evidence conflict (hard label says 'picture', "
            f"structural evidence exceeds the conservative threshold). Of these, "
            f"{len(conflicts_confirmed_table)} were independently confirmed as "
            f"actual missed tables (factual_oracle_comparison.json / "
            f"recovery_verdicts.json) and {len(conflicts_confirmed_not_table)} "
            f"were independently confirmed NOT to be tables "
            f"(negative_controls.json's realscan_probe false positive, and/or "
            f"the PSEUDO_TABLE-verdict document). This is the central Phase 16 "
            f"result: the hard single-label gate DOES discard a real, recoverable "
            f"uncertainty signal (evidence conflicts with the label on genuine "
            f"tables) -- but the CURRENT evidence set is not yet sufficient to "
            f"cleanly separate those conflicts into 'promote' vs 'leave alone' "
            f"(the SAME conflict pattern fires on a confirmed non-table). This "
            f"argues for keeping role uncertainty VISIBLE (e.g. a role_candidates "
            f"list carried alongside the primary label) rather than either (a) "
            f"collapsing it to a single hard label as today, or (b) automatically "
            f"resolving it to a second hard label (promote-to-table) without a "
            f"stronger discriminating signal than exists today."
        ),
        "architectural_recommendation": (
            "Option B/D from intervention_candidates.json (031 Phase 9) is already "
            "evidence-based routing in miniature: it does not replace the label, "
            "it adds a table CANDIDATE alongside it, gated by evidence -- this is "
            "structurally closer to 'region -> role_candidates -> routing' than to "
            "the current hard gate, without requiring an IR schema change. A full "
            "role_candidates redesign of the IR schema is a LARGER change than "
            "this milestone's evidence justifies shipping; recorded here as a "
            "architecture-level finding for future work, not a Phase-031 "
            "implementation target."
        ),
    }
    Path("role_ambiguity_analysis.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False))
    print(f"regions evaluated: {len(rows)}")
    print(f"label/evidence conflicts: {len(conflicts)} "
          f"(confirmed table: {len(conflicts_confirmed_table)}, "
          f"confirmed NOT table: {len(conflicts_confirmed_not_table)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
