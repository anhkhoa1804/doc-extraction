"""029 Phase 11 -- definitive measurement matrix. No proxy silently called ground truth."""
from __future__ import annotations
import json
from pathlib import Path
HERE = Path(__file__).resolve().parent

MATRIX = [
    {"property": "text fidelity (document-level)", "layer1": "YES (exact/char recall)",
     "layer2": "NO (delegated to Layer 1)", "ground_truth_required": "document-level must_contain strings (have it)",
     "ir_evidence_required": "none beyond serialized text", "known_blind_spot": "order-sensitive char_recall (difflib); "
     "cannot see duplicated or dropped evidence outside must_contain (024/025)"},
    {"property": "text fidelity (per-cell)", "layer1": "NO", "layer2": "NO (UNMEASURABLE, reported explicitly)",
     "ground_truth_required": "per-cell ground truth grid (DO NOT HAVE -- corpus lacks it)",
     "ir_evidence_required": "n/a", "known_blind_spot": "no proxy invented; honestly unmeasurable"},
    {"property": "evidence coverage (region ownership)", "layer1": "NO", "layer2": "PARTIAL (borrowed from 025 token data, SCAN-49 only)",
     "ground_truth_required": "none -- computed from IR geometry directly", "ir_evidence_required": "OCR token bboxes + region bboxes (available only where 025's instrumentation ran)",
     "known_blind_spot": "not a native Layer-2 computation; not available for 023/024's non-SCAN-49 arms"},
    {"property": "evidence duplication (overlap)", "layer1": "NO", "layer2": "PARTIAL (same caveat as above)",
     "ground_truth_required": "none", "ir_evidence_required": "same as above",
     "known_blind_spot": "same SCAN-49-only scope limit"},
    {"property": "page order (element sequence)", "layer1": "PARTIAL (raw list order only, NOT reading_order)",
     "layer2": "YES (page_order_ok reads Page.reading_order directly)",
     "ground_truth_required": "must_contain string document-order (have it)",
     "ir_evidence_required": "Page.reading_order (present, 112/112 pages on SCAN-49; UNKNOWN coverage elsewhere -- not yet checked)",
     "known_blind_spot": "029 FACT: Layer 1 ignoring reading_order produces false negatives whenever list order "
     "coincidentally looks right (19 document-arm pairs found)"},
    {"property": "table cell order", "layer1": "PARTIAL (conflated into order_ok, table+page mixed)",
     "layer2": "YES (list_order_canonical, independent of page order)",
     "ground_truth_required": "none -- (row,col) IS the ground truth by IR definition",
     "ir_evidence_required": "Cell.row, Cell.col, Cell.bbox", "known_blind_spot": "none identified; this is the "
     "cleanest-measured property in the whole matrix"},
    {"property": "table structure (coherence)", "layer1": "NO", "layer2": "YES (8 independent checks + band coherence)",
     "ground_truth_required": "none -- coherence is self-consistency, not correctness against truth",
     "ir_evidence_required": "Table.n_rows/n_cols, Cell.row/col/bbox", "known_blind_spot": "coherent != correct: "
     "a table can be perfectly coherent and describe the wrong page region (028 limitation, still true)"},
    {"property": "table structure (bbox containment)", "layer1": "NO", "layer2": "YES (cells_within_table_bbox)",
     "ground_truth_required": "none", "ir_evidence_required": "Table.bbox, Cell.bbox",
     "known_blind_spot": "029 FACT: 100% of violations traced to one mechanism (tier-3 row synthesis); "
     "the check is sound, the PRODUCTION CODE has the escape, not the metric"},
    {"property": "cell geometry validity", "layer1": "NO", "layer2": "YES (all_cell_bboxes_valid)",
     "ground_truth_required": "none", "ir_evidence_required": "Cell.bbox", "known_blind_spot": "none identified"},
    {"property": "table-label correctness (picture vs table)", "layer1": "NO", "layer2": "NO",
     "ground_truth_required": "human-verified label per region (DO NOT HAVE)",
     "ir_evidence_required": "Region.label at detection time, which is DISCARDED before the final IR "
     "(base.py:747 gates on it but does not retain a 'this picture might be a table' flag)",
     "known_blind_spot": "029 control 09 demonstrates this formally: a picture-labelled region and a real "
     "table can have identical bbox geometry; nothing in the final IR can tell them apart post hoc"},
    {"property": "OCR correctness (recognized text vs source)", "layer1": "PARTIAL (via must_contain char_recall, "
     "sparse and order-sensitive)", "layer2": "NO", "ground_truth_required": "source-text ground truth beyond "
     "sparse must_contain (DO NOT HAVE)", "ir_evidence_required": "n/a", "known_blind_spot": "024/025's central "
     "finding: sparse must_contain massively under-samples OCR correctness"},
    {"property": "extraction completeness (nothing silently dropped)", "layer1": "NO",
     "layer2": "PARTIAL (evidence_coverage/orphan_rate, SCAN-49-only, token-level not cell-level)",
     "ground_truth_required": "none for the token-level check; would need full source text for a document-level guarantee",
     "ir_evidence_required": "OCR tokens + regions (SCAN-49 only)",
     "known_blind_spot": "no completeness guarantee exists outside SCAN-49; 029 did not extend this"},
]


def main() -> int:
    (HERE / "measurement_matrix.json").write_text(json.dumps(MATRIX, indent=1, ensure_ascii=False))
    print(f"{'property':<42}{'L1':<9}{'L2':<9}blind spot")
    for r in MATRIX:
        l1 = "YES" if r["layer1"].startswith("YES") else "PARTIAL" if r["layer1"].startswith("PARTIAL") else "NO"
        l2 = "YES" if r["layer2"].startswith("YES") else "PARTIAL" if r["layer2"].startswith("PARTIAL") else "NO"
        print(f"{r['property']:<42}{l1:<9}{l2:<9}{r['known_blind_spot'][:70]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
