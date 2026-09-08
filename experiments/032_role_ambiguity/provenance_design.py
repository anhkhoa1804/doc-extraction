"""032 Phase 15 -- research-only provenance representation.

Derived from repository conventions actually observed this milestone
(role_contract.json's provenance section) and 031's own working
precedent (Element.extra already used to mark a table candidate's
provenance without a schema change), not invented from scratch.

    python experiments/032_role_ambiguity/provenance_design.py
"""
from __future__ import annotations
import json
from pathlib import Path
HERE = Path(__file__).resolve().parent
L31 = HERE.parents[1] / "experiments/031_table_label_gating"


def main():
    contract = json.loads((HERE / "role_contract.json").read_text())

    design = {
        "principle": "never destroy the original detector observation; "
                    "carry evidence and routing outcome as ADDITIVE "
                    "metadata using fields this repository's schema "
                    "ALREADY has (Element.extra), not a new schema.",
        "existing_precedent": {
            "source": "031 controlled_intervention.py:210 -- "
                     "el.setdefault('extra', {})['031_table_candidate_"
                     "added'] = new_table['id']",
            "significance": "proves Element.extra is a VIABLE, ALREADY-"
                           "USED carrier for exactly this kind of "
                           "provenance, without any schema migration -- "
                           "not a new proposal, a generalization of an "
                           "existing one.",
        },
        "proposed_shape": {
            "observed_role": {
                "value": "picture",
                "source": "Region.label at detection time (currently "
                         "DISCARDED after the _LABEL_TO_ELEMENT_TYPE "
                         "collapse -- role_contract.json concepts."
                         "observed_role.persisted_to_canonical_IR=false). "
                         "This field would need to survive into "
                         "Element.extra to exist at all downstream.",
            },
            "candidate_roles": [
                {"role": "table", "evidence_score": 4,
                 "evidence_score_name": "table_shape_evidence_score",
                 "NOT": "confidence -- explicitly never given this name "
                       "(031 role_ambiguity_analysis.json's own naming "
                       "discipline, carried forward)"},
            ],
            "routing_decision": "table_specialist_invoked",
            "routing_reason": "table_shape_evidence_score >= conservative_threshold(3)",
            "specialist_results": {
                "table_reconstruction": {
                    "table_id": "<id, if produced>",
                    "structurally_valid": "<bool, from 028 structural_integrity>",
                },
            },
            "final_role": "picture",
            "final_role_reasoning": "ORIGINAL LABEL PRESERVED per 031's "
                                    "own established design (intervention "
                                    "candidate B/D) -- final_role is NOT "
                                    "auto-promoted to 'table' even when a "
                                    "candidate is produced, because "
                                    "adversarial_controls.json shows the "
                                    "current evidence model is not "
                                    "reliable enough to safely auto-"
                                    "resolve the conflict (6/20 synthetic "
                                    "misfires, including ordinary prose).",
            "provenance_carrier": "Element.extra['032_role_provenance'] = "
                                  "{...above fields...} -- additive, no "
                                  "schema migration, reversible (deleting "
                                  "the key fully restores current "
                                  "behavior).",
        },
        "what_this_design_deliberately_does_NOT_do": [
            "does not replace Element.type -- final_role stays exactly "
            "what production computes today",
            "does not fabricate a picture-side confidence to pair against "
            "table_shape_evidence_score (role_ambiguity_analysis.json: "
            "Docling provides none, and none is invented here either)",
            "does not require every Element to carry this metadata -- "
            "only regions that actually triggered SOME candidate-role "
            "evaluation would have a non-empty extra['032_role_"
            "provenance']; the overwhelming majority of elements (text, "
            "heading, etc.) would carry nothing new",
        ],
        "downstream_consumer_impact": {
            "existing_consumers": "UNAFFECTED -- Element.extra is already "
                                  "typed dict[str, Any] with default {} "
                                  "(schemas/element.py:95); no existing "
                                  "code path reads a '032_role_provenance' "
                                  "key, so this is a strict additive change "
                                  "with zero behavior change for anything "
                                  "that does not opt in.",
            "a_future_RAG/GraphRAG_consumer": "COULD read "
                                              "extra['032_role_provenance']"
                                              "['final_role_reasoning'] to "
                                              "decide whether to trust a "
                                              "picture-labelled region's "
                                              "gathered text as prose, or "
                                              "flag it for human/secondary "
                                              "review when candidate_roles "
                                              "shows a live conflict -- "
                                              "this is the concrete "
                                              "'prevent downstream systems "
                                              "from treating a false label "
                                              "as truth' value named in "
                                              "the milestone brief's Phase "
                                              "14 -- PROJECTION, no such "
                                              "consumer exists in this "
                                              "repository to test against.",
        },
    }
    Path("provenance_design.json").write_text(json.dumps(design, indent=1, ensure_ascii=False))
    print("provenance_design.json written")
    print(json.dumps(design["proposed_shape"], indent=1)[:600])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
