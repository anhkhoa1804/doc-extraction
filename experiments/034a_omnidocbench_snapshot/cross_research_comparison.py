"""034a Phase 10 (original) -- which 023-033 failure mechanisms are
observable in OmniDocBench?

    python experiments/034a_omnidocbench_snapshot/cross_research_comparison.py
"""
from __future__ import annotations
import json
from pathlib import Path
HERE = Path(__file__).resolve().parent


def main():
    failure = json.loads((HERE / "failure_analysis_subset_B_fixed_auto.json").read_text())
    metrics = json.loads((HERE / "results/subset_B_fixed_auto/metrics.json").read_text())

    rows = [
        {
            "mechanism": "A. OCR acquisition failure",
            "present_in_omnidocbench": "YES, dominant",
            "evidence": (
                f"failure_analysis_subset_B_fixed_auto.json: mean approx-"
                f"similarity by language -- english=0.5028 (n=29), "
                f"simplified_chinese=0.0301 (n=38), a 16.7x gap. ALL 10 "
                f"worst-ranked pages are simplified_chinese; ALL 10 best-"
                f"ranked pages are english. text_block Edit_dist (official "
                f"metric, aggregate) = {metrics['text_block']['all']['Edit_dist']['ALL_page_avg']:.4f}."
            ),
            "frequency": "~46% of the full dataset is Chinese-language "
                        "(dataset_manifest.json: simplified_chinese=765 + "
                        "traditional_chinese=13 of 1651)",
            "same_mechanism": "RELATED BUT DIFFERENT -- 023-033's OCR "
                             "acquisition findings concerned recognizer "
                             "choice/route/DPI within the EN/VI language "
                             "space this system targets; this is a "
                             "language-OUT-OF-SCOPE failure (no Chinese "
                             "OCR model configured at all, per docs/"
                             "production-contract.md and 007's own prior "
                             "finding) -- a categorically different, much "
                             "larger-magnitude version of the same general "
                             "phenomenon (missing/wrong recognition "
                             "evidence).",
        },
        {
            "mechanism": "B. orphan evidence",
            "present_in_omnidocbench": "NOT MEASURABLE from benchmark annotations",
            "evidence": "OmniDocBench's evaluator compares final predicted "
                       "text against ground truth text/table/formula "
                       "content -- it has no concept of 'a token no region "
                       "claimed'. This system's own internal IR (which DOES "
                       "carry orphan-recovery evidence, 024's L5) is never "
                       "inspected by the official evaluator.",
            "frequency": "N/A", "same_mechanism": "N/A",
        },
        {
            "mechanism": "C. ownership/duplication",
            "present_in_omnidocbench": "NOT MEASURABLE from benchmark annotations",
            "evidence": "same reasoning as B -- the evaluator sees only "
                       "final serialized text, with no ownership/"
                       "attribution model. A duplicated token could in "
                       "principle inflate text length and thus edit "
                       "distance, but the evaluator cannot attribute a "
                       "score change to duplication SPECIFICALLY versus "
                       "any other text-length discrepancy.",
            "frequency": "N/A", "same_mechanism": "N/A",
        },
        {
            "mechanism": "D. region-label gating (031's central finding)",
            "present_in_omnidocbench": "PARTIALLY OBSERVABLE, indirectly",
            "evidence": (
                f"table TEDS on the subset = "
                f"{metrics['table']['all']['TEDS']['all']:.4f} -- very low, but "
                f"NOT separable into 'table genuinely absent from ground "
                f"truth region' vs 'table present but gated to picture/"
                f"other by this system's own Docling call' vs 'table "
                f"structure simply wrong' without per-page inspection this "
                f"milestone did not perform (would require cross-"
                f"referencing this system's own layout/*.json intermediate "
                f"output per OmniDocBench page against ground truth table "
                f"bboxes -- not done, out of scope given the full-run time "
                f"budget)."
            ),
            "frequency": "unknown without the per-page cross-reference above",
            "same_mechanism": "POSSIBLY RELATED, UNCONFIRMED -- flagged as "
                             "the single most valuable follow-up analysis "
                             "if this milestone's artifacts are revisited.",
        },
        {
            "mechanism": "E. table structure/order (029's row-synthesis finding)",
            "present_in_omnidocbench": "PARTIALLY OBSERVABLE",
            "evidence": (
                f"TEDS_structure_only = "
                f"{metrics['table']['all']['TEDS_structure_only']['all']:.4f} vs "
                f"TEDS.all = {metrics['table']['all']['TEDS']['all']:.4f} -- "
                f"structure-only scores HIGHER than the content-inclusive "
                f"score, consistent with 029's own finding that this "
                f"system's table STRUCTURE (row/col assignment) is more "
                f"reliable than table cell TEXT content -- directionally "
                f"consistent with 026/029's finding that structural "
                f"metadata (row/col) was already correct 94/94 -- 1133/1133 "
                f"times historically, while cell text fidelity was never "
                f"the strong point. CAVEAT, a NEW finding this milestone: "
                f"metrics.json's own table.all.metric_debug.TEDS shows 26 "
                f"of 37 TEDS sample computations failed with the "
                f"EVALUATOR'S OWN internal error 'AssertionError: can only "
                f"join a started process' (a multiprocessing race in "
                f"omnidocbench_eval's own TEDS worker pool, not this "
                f"system's output) -- the reported TEDS numbers are "
                f"computed from the 11 (30%) samples that did NOT hit this "
                f"race, not the full 37. This is an EVALUATOR-SIDE "
                f"reliability bug, external to this project, and the table "
                f"TEDS numbers reported anywhere in this milestone's "
                f"artifacts should be read with that caveat, not treated "
                f"as clean."
            ),
            "frequency": "table category, n=28 subset pages with a table region "
                        "(but TEDS itself computed from only 11/37 "
                        "successfully-processed samples, see caveat above)",
            "same_mechanism": "RELATED, CONSISTENT DIRECTION -- not the "
                             "SAME specific bbox-escape mechanism (029's "
                             "1.1-14.4px row-synthesis escape is invisible "
                             "to a text-content-comparison evaluator), but "
                             "the general 'structure more reliable than "
                             "content' pattern reproduces.",
        },
        {
            "mechanism": "F. text fidelity",
            "present_in_omnidocbench": "YES, directly measured",
            "evidence": f"text_block.Edit_dist.ALL_page_avg = "
                       f"{metrics['text_block']['all']['Edit_dist']['ALL_page_avg']:.4f} "
                       f"(subset, 77 pages) -- this IS literally what OmniDocBench's "
                       f"primary metric measures.",
            "frequency": "every page", "same_mechanism": "SAME CONCEPT, "
                        "different measurement method (edit distance on "
                        "flattened output vs 023-033's own must_contain-"
                        "substring Layer-1 scorer) -- directly comparable "
                        "in KIND, not in exact number.",
        },
        {
            "mechanism": "G. page reading order",
            "present_in_omnidocbench": "YES, directly measured",
            "evidence": f"reading_order.Edit_dist.ALL_page_avg = "
                       f"{metrics['reading_order']['all']['Edit_dist']['ALL_page_avg']:.4f} "
                       f"(subset) -- OmniDocBench has a DEDICATED reading-"
                       f"order metric, something 027/028/029's own Layer-1 "
                       f"scorer was found to be BLIND to (027's central "
                       f"finding). This benchmark's own reading_order "
                       f"metric is closer in spirit to 028's Layer-2 "
                       f"page_order_ok (reads the production reading-order "
                       f"computation, not raw element-list order) than to "
                       f"Layer-1.",
            "frequency": "every page", "same_mechanism": "SAME CONCEPT -- "
                        "OmniDocBench's reading_order metric is a STRONGER, "
                        "external analog to 028's Layer-2 metric, not "
                        "Layer-1's blind one.",
        },
        {
            "mechanism": "H. role ambiguity (032/033's central finding)",
            "present_in_omnidocbench": "NOT MEASURABLE from benchmark annotations directly, "
                                       "but the label-collapsing MECHANISM is architecturally present",
            "evidence": "OmniDocBench's ground truth has its OWN rich "
                       "category_type vocabulary (text_block, title, table, "
                       "figure, equation_isolated, etc. -- 28 distinct "
                       "categories, role_contract-style) but the evaluator "
                       "scores against FINAL markdown/table/formula text, "
                       "never against this system's OWN internal "
                       "Region.label/ElementType decisions. Whether a "
                       "table-shaped OmniDocBench page got gated to "
                       "'picture' internally (032/033's mechanism) versus "
                       "correctly routed is invisible without inspecting "
                       "this system's own intermediate layout JSON per "
                       "page -- same limitation as mechanism D.",
            "frequency": "unknown without the same per-page cross-reference",
            "same_mechanism": "MECHANISM LIKELY PRESENT, UNCONFIRMED BY "
                             "THIS BENCHMARK RUN -- OmniDocBench was never "
                             "designed to expose an internal pipeline's "
                             "OWN label-routing decisions; it is fundamentally "
                             "an output-comparison benchmark, per "
                             "benchmark_vs_production_corpus.json's central "
                             "conclusion.",
        },
    ]

    payload = {
        "method": "cross-reference the 023-033 failure taxonomy (A-H) "
                 "against what OmniDocBench's official evaluator actually "
                 "measures, using the real 77-page subset's official "
                 "metrics.json and the approximate per-page failure "
                 "ranking (failure_analysis_subset_B_fixed_auto.json).",
        "rows": rows,
        "summary": {
            "directly_measured": ["F. text fidelity", "G. page reading order"],
            "partially_observable_indirect": ["D. region-label gating", "E. table structure/order"],
            "not_measurable_at_all": ["B. orphan evidence", "C. ownership/duplication", "H. role ambiguity"],
            "present_but_categorically_different": ["A. OCR acquisition failure "
                                                     "(language mismatch, not "
                                                     "recognizer/route choice)"],
        },
        "headline_finding": (
            "OmniDocBench reproduces (F, G) or is directionally consistent "
            "with (E) three of eight 023-033 failure mechanisms, is silent "
            "on three more that are structurally invisible to any output-"
            "text-comparison benchmark (B, C, H), and its single largest "
            "measured effect (the english/simplified_chinese 16.7x score "
            "gap) is NOT one of the eight mechanisms at all -- it is a "
            "language-coverage mismatch this research chain already "
            "identified and deliberately declined to fix (007)."
        ),
    }
    Path("cross_research_comparison.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False))
    print(json.dumps(payload["summary"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
