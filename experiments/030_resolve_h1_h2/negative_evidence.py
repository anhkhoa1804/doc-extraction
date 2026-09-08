"""030 Phase 4 -- negative evidence, surfaced explicitly, not buried.

Every item here argues AGAINST H1 and/or H2 as stated, drawn from
h1_resolution.json / h2_resolution.json. Consolidated into one place per
the milestone's explicit requirement that negative evidence not be buried
in an appendix.
"""
from __future__ import annotations
import json
from pathlib import Path
HERE = Path(__file__).resolve().parent

h1 = json.loads((HERE / "h1_resolution.json").read_text())
h2 = json.loads((HERE / "h2_resolution.json").read_text())

items = []

# --- H1 negative evidence ---
b = h1["2_5_boundary_counterexamples"]
for ex in b["stamp_occlusion_tables_with_ZERO_undershoot"]["examples"]:
    items.append({
        "hypothesis": "H1", "document_id": ex["document_id"], "arm": f"{ex['milestone']}/{ex['arm']}",
        "expected_by_H": "undershoot > 0 (table.bbox undershoots real extent)",
        "observed": "undershoot == 0 (table.bbox fully contains its own cell geometry)",
        "why_this_matters": "document is stamp/occlusion-labeled and reached "
                            "table_transformer, yet shows no trace of the predicted defect",
        "falsifies_or_weakens": "weakens (sufficiency reading only; H1 does not claim "
                                "determinism)",
    })
for ex in b["non_stamp_tables_with_NOTABLE_undershoot_gt_10px"]["examples"]:
    items.append({
        "hypothesis": "H1", "document_id": ex["document_id"], "arm": f"{ex['milestone']}/{ex['arm']}",
        "expected_by_H": "no stamp/occlusion label -> undershoot should be rare/absent",
        "observed": f"undershoot = {ex['undershoot_px']}px, labels={ex['labels']}",
        "why_this_matters": "the mechanism clearly fires on documents with NO stamp or "
                            "occlusion label, at magnitudes as large as the worst "
                            "stamp/occlusion case -- the trigger is not specific to "
                            "the labeled condition",
        "falsifies_or_weakens": "weakens (necessity reading -- stamp/occlusion is not "
                                "the only or dominant trigger)",
    })

items.append({
    "hypothesis": "H1", "document_id": "(population-level)", "arm": "(all)",
    "expected_by_H": "stamp/occlusion undershoot magnitude should be LARGER than "
                     "non-stamp (more severe bbox undershoot)",
    "observed": "stamp/occlusion nonzero magnitudes: {1.10, 1.47}px; non-stamp nonzero "
               "magnitudes: up to 15.40px -- the OPPOSITE direction",
    "why_this_matters": "this is the single strongest piece of negative evidence in the "
                        "whole study -- it directly contradicts the SEVERITY component "
                        "of H1's mechanistic claim, not merely its frequency component",
    "falsifies_or_weakens": "falsifies the severity-elevation component specifically; "
                            "does not falsify the rate-elevation (correlational) component",
})

items.append({
    "hypothesis": "H1", "document_id": "cmb_scan_stamp_table_vi, hc_stamp_table_vi",
    "arm": "(all arms, all milestones)",
    "expected_by_H": "H1 is framed as being about how stamp/occlusion affects "
                     "table_transformer's bbox behavior",
    "observed": "2 of 025's 3 named picture-gated documents NEVER reach "
               "table_transformer at all in any replayed arm -- gating removes them "
               "before H1's mechanism can apply",
    "why_this_matters": "the corpus's most severe stamp/occlusion cases are structurally "
                        "excluded from H1's test population; H1 as tested only speaks to "
                        "documents where gating did NOT fully fail",
    "falsifies_or_weakens": "weakens (scope limitation, not a direct falsification)",
})

# --- H2 negative evidence ---
items.append({
    "hypothesis": "H2", "document_id": "(all 102 invalid tables)", "arm": "(all)",
    "expected_by_H": "if H2's bound is real, contamination should be geometrically "
                     "impossible regardless of corpus content",
    "observed": "100% (102/102) of pages with an escaping cell have ZERO other tables "
               "on that page -- H2's specific adversarial precondition never co-occurs "
               "with the defect in this corpus",
    "why_this_matters": "H2's '0 contaminated cells' result is not fully independent "
                        "evidence of the geometric bound -- it is partly explained by "
                        "the corpus never placing a second table on an affected page",
    "falsifies_or_weakens": "weakens confidence (does not falsify -- the geometric "
                            "argument in H2's own statement is untouched by this)",
})

payload = {"count": len(items), "items": items}
(HERE / "negative_evidence.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False))
print(f"{len(items)} negative-evidence items recorded")
for it in items:
    print(f"  [{it['hypothesis']}] {it['document_id'][:40]:<40} {it['falsifies_or_weakens'][:60]}")
