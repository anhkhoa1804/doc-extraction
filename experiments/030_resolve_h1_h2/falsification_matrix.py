"""030 Phase 1 -- falsification matrix. Built AFTER h1/h2 resolution so every
row cites an actual measured result, not a plan."""
from __future__ import annotations
import json
from pathlib import Path
HERE = Path(__file__).resolve().parent

h1 = json.loads((HERE / "h1_resolution.json").read_text())
h2 = json.loads((HERE / "h2_resolution.json").read_text())

MATRIX = [
    # H1 rows
    {"hypothesis": "H1", "prediction": "stamp/occlusion tables show a MATERIALLY "
     "elevated INVALID RATE (binary) vs non-stamp",
     "evidence_source": "h1_resolution.json: h1_core_test distributions (tol=1.0px)",
     "observable": True,
     "current_result": "29.31% (17/58 instances, 4 distinct docs) vs 4.70% (85/1809, 7 docs)",
     "supports_H": True, "falsifies_H": False,
     "discriminating": "PARTIALLY -- elevated rate is real but the underlying document "
     "sample is only 4 vs 7 distinct documents (pseudo-replication caveat)"},
    {"hypothesis": "H1", "prediction": "stamp/occlusion tables show MORE SEVERE "
     "(larger magnitude) undershoot when it occurs, not merely more frequent",
     "evidence_source": "h1_resolution.json: critical_caveat_pseudo_replication.magnitude_finding",
     "observable": True,
     "current_result": "stamp/occlusion nonzero magnitudes: {1.10, 1.47}px only. "
     "non-stamp nonzero magnitudes range up to 15.40px",
     "supports_H": False, "falsifies_H": "PARTIALLY -- contradicts the severity "
     "component of H1's mechanistic claim specifically",
     "discriminating": "YES -- this is the discriminating result 029's binary-rate "
     "test could not see"},
    {"hypothesis": "H1", "prediction": "undershoot requires tier-3 synthesis to have "
     "fired (synthesis is the proximate mechanism, stamp/occlusion the trigger)",
     "evidence_source": "h1_resolution.json: 2_2_component_attribution",
     "observable": True,
     "current_result": "0 tables show undershoot without synthesis, out of 1867 checked",
     "supports_H": True, "falsifies_H": False,
     "discriminating": "YES -- rules out an alternative mechanism (bbox undershoot "
     "independent of synthesis)"},
    {"hypothesis": "H1", "prediction": "stamp/occlusion is SUFFICIENT to trigger "
     "undershoot whenever table_transformer runs on such a document",
     "evidence_source": "h1_resolution.json: 2_5_boundary_counterexamples",
     "observable": True,
     "current_result": "41/58 (71%) stamp/occlusion instances show ZERO undershoot",
     "supports_H": False, "falsifies_H": True,
     "discriminating": "YES -- direct counterexample to a sufficiency reading of H1"},
    {"hypothesis": "H1", "prediction": "non-stamp/occlusion documents should rarely or "
     "never show notable undershoot",
     "evidence_source": "h1_resolution.json: 2_5_boundary_counterexamples",
     "observable": True,
     "current_result": "38/1809 (2.1%) non-stamp instances show undershoot >10px, "
     "tracing to 7 distinct documents with NO stamp/occlusion label",
     "supports_H": False, "falsifies_H": "PARTIALLY -- the mechanism clearly operates "
     "on non-stamp documents too, at meaningful (even larger) magnitude",
     "discriminating": "YES -- direct counterexample to stamp/occlusion being the "
     "necessary trigger"},
    # H2 rows
    {"hypothesis": "H2", "prediction": "NO escaping cell's bbox intersects a table "
     "other than its own",
     "evidence_source": "h2_resolution.json: H2_CORE_RESULT",
     "observable": True,
     "current_result": "0/265 escaping cells intersect another table",
     "supports_H": True, "falsifies_H": False,
     "discriminating": "PARTIALLY -- true wherever tested, but the corpus's escaping "
     "cells all happen to sit on single-table pages (see precondition check)"},
    {"hypothesis": "H2", "prediction": "the corpus contains a genuine (non-vacuous) "
     "opportunity for cross-table contamination to have been observed",
     "evidence_source": "h2_resolution.json: same_page_multi_table_precondition_check",
     "observable": True,
     "current_result": "25 same-page multi-table instances exist (1 distinct document), "
     "0 overlap with escaping-cell pages",
     "supports_H": "NEITHER -- precondition exists elsewhere in corpus but not "
     "co-located with the defect",
     "falsifies_H": False,
     "discriminating": "NO -- confirms the test was not meaningless, but does not "
     "itself discriminate H2 from its alternative"},
    {"hypothesis": "H2", "prediction": "escape magnitude never exceeds roughly one "
     "OCR token's own dimension (the theoretical bound H2's mechanism implies)",
     "evidence_source": "h2_resolution.json: escape_magnitude_bound_check",
     "observable": True,
     "current_result": "max escape 14.43px; 0/265 cells exceed the 40px proxy bound",
     "supports_H": True, "falsifies_H": False,
     "discriminating": "YES -- consistent with the stated geometric bound, and no "
     "outlier breaks it"},
]

def main():
    (HERE / "falsification_matrix.json").write_text(json.dumps(MATRIX, indent=1, ensure_ascii=False))
    for r in MATRIX:
        print(f"[{r['hypothesis']}] supports={r['supports_H']!s:<30} falsifies={r['falsifies_H']!s:<10} "
              f"{r['prediction'][:70]}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
