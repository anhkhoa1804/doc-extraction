"""029 Phase 9 -- cross-milestone research lineage.

Not a replay; a structured record of what each milestone actually claimed,
decided, and left open, built from this session's own record of each
milestone's frozen commit and verified findings (029's own replay data
where a milestone's claim is checked, not merely narrated).

    python experiments/029_deep_forensic_replay/lineage.py
"""
from __future__ import annotations
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

LINEAGE = [
    {"milestone": "023", "commit": "(evidence-centric A/B)",
     "hypothesis": "Which OCR backend/fusion strategy is best under the adaptive router?",
     "experiment": "18 arms x 49 docs, Tesseract vs EasyOCR vs fusion variants, adaptive+visual",
     "observation": "Tesseract >> EasyOCR on this corpus; reading-order fix separately "
                    "improved order_ok materially (42->46 in some arms)",
     "decision": "Tesseract adopted as primary recognizer",
     "surviving_open_problem": "Table cell evidence recovery hypothesis (renamed to OCR "
                               "fidelity/acquisition after audit)"},
    {"milestone": "024", "commit": "0355e79",
     "hypothesis": "OCR fidelity recovery (L5: recover orphan OCR tokens no region claims) "
                   "generalizes from the production router to a scan-dominant workload",
     "experiment": "SCAN-49 frozen cohort, 49 docs/112 pages, baseline vs L5 vs L5_audit",
     "observation": "L5 +0.0136 exact / +0.0115 char on SCAN-49; 664 orphan tokens recovered "
                    "(recomputed by 029: 667 in n_owners==0, 664 by claim==orphan, "
                    "3-token gap reconciled in 028)",
     "decision": "L5 SHIP -- CONFIRMED BUT LOW-SENSITIVITY",
     "surviving_open_problem": "Is layout-region coverage the dominant residual failure?"},
    {"milestone": "025", "commit": "c92eb8b",
     "hypothesis": "Missing layout-region coverage is the dominant residual bottleneck",
     "experiment": "gap_region intervention: synthesize a region for every orphan cluster",
     "observation": "Coverage 0.8874->0.9993, ALL output metrics delta exactly 0 -- L5 already "
                    "captures the entire coverage gap",
     "decision": "HYPOTHESIS REJECTED. Found instead: class C (82 multiply-owned tokens, 3 docs), "
                "class D (table-label gating -- picture-labelled table-shaped regions), "
                "class E (11/94 cell-list-order anomalies)",
     "surviving_open_problem": "Is class E (cell ordering) a production defect?"},
    {"milestone": "026", "commit": "271abf2 (part 1)",
     "hypothesis": "Deterministic geometric cell canonicalization is a valid production intervention",
     "experiment": "table_ir_diagnostic + adversarial controls on the frozen SCAN-49 IR",
     "observation": "94/94 tables ALREADY have correct row/col metadata -- only the cells LIST "
                    "was uncanonical (11/94), and no production consumer reads list order",
     "decision": "HYPOTHESIS FALSIFIED. HOLD -- the defect lives in evaluation code "
                "(run_benchmark.document_text), not production",
     "surviving_open_problem": "Is run_benchmark.document_text's raw-list-order table "
                               "serialization actually wrong?"},
    {"milestone": "027", "commit": "271abf2 (part 2)",
     "hypothesis": "run_benchmark.document_text incorrectly flattens tables by list order "
                   "when (row,col) is the canonical representation",
     "experiment": "Counterfactual serializer replayed over 37 frozen arms, 023-025",
     "observation": "56.1% of order_ok failures (28 arms, n>=10) were table serialization, not "
                    "page order; every headline delta (024 L5, 025 gap_region, 023 reading-order "
                    "fix) survives unchanged under the counterfactual",
     "decision": "ADOPT a two-layer contract (Layer 1 frozen, Layer 2 additive); no rebaseline",
     "surviving_open_problem": "Turn the contract into a working instrument"},
    {"milestone": "028", "commit": "b9b87d1",
     "hypothesis": "A Layer-2 evaluator can measure dimensions Layer 1 provably cannot",
     "experiment": "4 views (table_text, table_structure, page_order_ok, structural_integrity) "
                   "on SCAN-49; 12 evaluator controls; 7 anti-gaming attacks",
     "observation": "Found 4 structurally invalid tables (cells outside their own table bbox) "
                    "-- a defect class NO prior milestone measured; found a Layer-1 FALSE "
                    "NEGATIVE (cmb_stamp_boundary_vi, order_ok=True, page_order_ok=False)",
     "decision": "ADOPT Layer 2 as the standard research contract alongside frozen Layer 1",
     "surviving_open_problem": "Are the 028 findings SCAN-49-specific, or general? What CAUSES "
                               "the 4 invalid tables and the false negative?"},
    {"milestone": "029", "commit": "(this milestone, uncommitted at write time)",
     "hypothesis": "Structural/order/ownership defects are properties of the pipeline (backend-"
                   "and mechanism-dependent), not artifacts of SCAN-49",
     "experiment": "Layer 1+2 replayed over 31 arms / 1,378 document-arm pairs / 1,984 table "
                   "instances across 023-025; direct source-code + IR causal tracing",
     "observation": (
         "GENERALIZES, and a complete mechanism was found: ALL 102 structurally-invalid table "
         "instances (100%, not a sample) are produced by tier-3 row synthesis "
         "(base.py:505-576) admitting a token by CENTER containment against table.bbox, then "
         "building the synthesized cell from the token's raw edges, without ever expanding "
         "table.bbox. Invalidity is 0.00% under pymupdf_tables, 5.46% under table_transformer, "
         "29.31% under table_transformer+stamp/occlusion. The order_ok false negative "
         "generalizes to a THIRD blind spot: Layer 1 never reads Page.reading_order, only raw "
         "list order -- 19 document-arm pairs where list order coincidentally looks right while "
         "the actual computed reading order is wrong. Layer1's 107 order failures decompose "
         "60/31/16 into table-order / append-boundary / genuine-list-order causes."),
     "decision": "See FINAL_REPORT.md Phase 12/13",
     "surviving_open_problem": "See the 3 falsifiable hypotheses in FINAL_REPORT.md"},
]


def main() -> int:
    (HERE / "lineage.json").write_text(json.dumps(LINEAGE, indent=1, ensure_ascii=False))
    for m in LINEAGE:
        print(f"\n{m['milestone']}: {m['hypothesis'][:90]}")
        print(f"  -> {m['decision'][:110]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
