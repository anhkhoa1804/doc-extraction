"""030 Phase 14 -- append to (never rewrite) the research lineage."""
from __future__ import annotations
import json
from pathlib import Path
HERE = Path(__file__).resolve().parent

LINEAGE_030 = {
    "milestone": "030",
    "029_observation": "H1 (stamp/occlusion elevates row-synthesis escape via detector "
        "bbox undershoot) and H2 (escape is spatially bounded, never crosses tables) "
        "were formulated as falsifiable but unresolved hypotheses",
    "H": "H1, H2 (H3 explicitly out of scope per user instruction)",
    "discriminating_experiment": "corpus-wide undershoot measurement on all 1,867 "
        "table_transformer instances (H1, an adaptation of 029's SCAN-49-only IoU "
        "proposal); per-cell cross-table intersection test on all 265 escaping cells "
        "(H2, exactly as 029 specified)",
    "evidence": "h1_resolution.json, h2_resolution.json, paired_comparisons.json, "
               "negative_evidence.json, adversarial_controls.json (10/10 pass)",
    "verdict": "H1: PARTIALLY_SUPPORTED (confidence MEDIUM) -- rate-elevation "
              "confirmed, severity-direction prediction contradicted. "
              "H2: SUPPORTED (confidence HIGH) -- no cross-table contamination found, "
              "evaluator independently validated capable of detecting it",
    "surviving_mechanism": "tier-3 row synthesis (base.py:505-576) remains the sole "
        "traced IMMEDIATE MECHANISM (029, reconfirmed here); its TRIGGER is now known "
        "to include OCR-recognizer choice (030, new finding, hc_encoding_vi natural "
        "experiment) at least as strongly as stamp/occlusion labeling (029's original "
        "candidate trigger, now shown to affect RATE but not SEVERITY)",
    "next_target": "029's priority stands: table-label gating under stamp/occlusion "
        "(025's Class D) remains the higher-value research target, unaffected by 030's "
        "findings since it is a structurally separate code path (base.py:747) from "
        "tier-3 synthesis. H3 (reading_order blindness co-occurring with gating "
        "failure) remains the recommended follow-up to test that specific connection, "
        "not yet attempted.",
    "new_findings_not_anticipated_by_029": [
        "OCR-recognizer choice (not document visual properties) is a clean, "
        "unconfounded trigger for tier-3 synthesis firing, demonstrated on a "
        "non-stamp document (hc_encoding_vi)",
        "stamp/occlusion documents show SMALLER defect magnitude than non-stamp "
        "documents when the defect fires -- opposite of H1's severity prediction",
        "2 of 025's 3 named picture-gated documents never reach table_transformer in "
        "any replayed arm -- H1's test population and 025's gated-table population "
        "are almost disjoint by construction",
        "the corpus contains 25 same-page multi-table instances (1 document) "
        "unrelated to any escaping-cell page -- H2's test was non-vacuous but the "
        "specific adversarial co-occurrence was never naturally available to test",
    ],
}

(HERE / "research_lineage_update.json").write_text(json.dumps(LINEAGE_030, indent=1, ensure_ascii=False))
print("029 lineage.json is NOT modified -- this is an append-only companion file")
print(json.dumps({"verdict": LINEAGE_030["verdict"]}, indent=1))
