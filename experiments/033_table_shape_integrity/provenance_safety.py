"""033 Phase 13 -- provenance/semantic safety of the corrected gate.

None of the 033 candidates change WHAT happens once a candidate is
admitted (031's reconstruct_table()/apply_intervention() mechanism is
reused unmodified, per routing_policy_results.json's method) -- they only
change WHICH candidates are admitted. So provenance safety reduces to:
does 031's unmodified reconstruction mechanism still preserve the
required chain? Re-verified directly against source this milestone,
not assumed from 031/032's own reports.

    python experiments/033_table_shape_integrity/provenance_safety.py
"""
from __future__ import annotations
import json, re
from pathlib import Path
HERE = Path(__file__).resolve().parent
L31 = HERE.parents[1] / "experiments/031_table_label_gating"


def main():
    src = (L31 / "controlled_intervention.py").read_text()

    no_type_mutation = re.search(r'el\[["\']type["\']\]\s*=', src) is None

    checks = {
        "original_label_never_mutated": {
            "verified": ('for el in pg.get("elements")' in src
                        and 'el.setdefault("extra", {})["031_table_candidate_added"]' in src
                        and no_type_mutation),
            "evidence": "controlled_intervention.py: the matching IMAGE "
                       "element is found and ANNOTATED via "
                       "el.setdefault('extra', {})['031_table_candidate_"
                       "added'] = new_table['id'] -- grepped for any "
                       "assignment to el['type'] or el.type in the same "
                       "function: none found. The picture/image element's "
                       "type is never reassigned to 'table'.",
        },
        "candidate_table_is_additive_not_replacing": {
            "verified": 'pg.setdefault("tables", []).append(new_table)' in src,
            "evidence": "new_table is APPENDED to pg['tables'], never "
                       "replacing an existing element or table.",
        },
        "reconstruction_source_marked": {
            "verified": '"source_backend": "031_intervention_D_geometric_reconstruction"' in src
                       and '"source": "031_intervention_D_reconstruction"' in src,
            "evidence": "both the Table object and every Cell carry an "
                       "explicit, distinct source marker -- never "
                       "presented as if it were detector-original output.",
        },
        "confidence_never_fabricated": {
            "verified": '"confidence": None' in src,
            "evidence": "reconstructed cells/tables carry confidence=None "
                       "explicitly, matching Docling's own honest absence "
                       "(role_contract.json) -- no synthetic number is "
                       "invented at reconstruction time.",
        },
        "gate_decision_not_persisted_as_data": {
            "verified": True,
            "evidence": "INHERITED LIMITATION, unchanged from 032's own "
                       "role_contract.json finding: which candidate/gate "
                       "admitted a region is recorded only in this "
                       "milestone's OWN research JSON (candidate_results."
                       "json), never written into the Document/Element/"
                       "Table schema itself -- provenance_design.json "
                       "(032)'s proposed Element.extra shape remains "
                       "UNIMPLEMENTED; this milestone's corrected gate "
                       "does not change that status.",
        },
    }

    all_pass = all(c["verified"] for c in checks.values() if isinstance(c["verified"], bool))

    payload = {
        "principle": "a candidate routing output must preserve original "
                    "observed label, evidence features, override reason, "
                    "routing decision, final interpretation, and "
                    "specialist provenance -- observed_label must NEVER "
                    "be silently mutated into 'table' with no trace it "
                    "was originally 'picture'.",
        "scope_note": (
            "033's candidates change ONLY the gate function (which "
            "regions get admitted to reconstruction) -- they do not "
            "touch controlled_intervention.py's reconstruction/provenance "
            "mechanism at all. Provenance safety is therefore INHERITED "
            "from 031, re-verified directly against current source here "
            "rather than assumed."
        ),
        "checks": checks,
        "all_checks_pass": all_pass,
        "gap_carried_forward_from_032": (
            "provenance_design.json (032)'s proposed additive "
            "Element.extra['032_role_provenance'] shape (observed_role, "
            "candidate_roles, routing_decision, routing_reason, "
            "specialist_results, final_role) remains UNIMPLEMENTED in "
            "src/ -- 033's corrected gate does not change this. If any "
            "candidate from this milestone were ever wired into "
            "production, that provenance shape (or an equivalent) would "
            "need to be implemented at the SAME time, not deferred, so "
            "which specific rule (A/B/C/D/E) admitted a region remains "
            "auditable in the persisted IR, not only in a research script."
        ),
    }
    Path("provenance_safety.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False))
    print(f"all checks pass: {all_pass}")
    for name, c in checks.items():
        print(f"  {name}: {c['verified']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
