"""034a Phase 11 -- OmniDocBench vs the production-shaped 023-033 corpus.
Not "which is better" -- they answer different questions.

    python experiments/034a_omnidocbench_snapshot/benchmark_vs_production_corpus.py
"""
from __future__ import annotations
import json
from pathlib import Path
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def main():
    manifest = json.loads((HERE / "dataset_manifest.json").read_text())
    dist = manifest["distributions"]

    corpus = json.loads((REPO / "research/production_corpus/corpus/manifest.json").read_text())
    scan = json.loads((REPO / "experiments/024_ocr_fidelity_recovery/scan_cohort_manifest.json").read_text())
    corpus_docs = corpus["documents_list"]
    scan_docs = scan["documents_list"]
    all_prod_docs = corpus_docs + scan_docs

    prod_langs = {}
    for d in all_prod_docs:
        lang = d.get("language", "?")
        prod_langs[lang] = prod_langs.get(lang, 0) + 1

    prod_hard_case_labels = {}
    for d in all_prod_docs:
        for lbl in d.get("hard_case_labels", []):
            prod_hard_case_labels[lbl] = prod_hard_case_labels.get(lbl, 0) + 1

    n_expected_tables = sum(1 for d in all_prod_docs if d.get("expected_tables", 0) > 0)

    matrix = [
        {
            "property": "language",
            "omnidocbench": f"Chinese-dominant ({dist['language'].get('simplified_chinese',0)} "
                            f"simplified + {dist['language'].get('traditional_chinese',0)} traditional "
                            f"= {dist['language'].get('simplified_chinese',0)+dist['language'].get('traditional_chinese',0)}/1651), "
                            f"English {dist['language'].get('english',0)}/1651, "
                            f"mixed {dist['language'].get('en_ch_mixed',0)}/1651. "
                            f"ZERO Vietnamese.",
            "production_corpus": f"English/Vietnamese only ({prod_langs}), the system's "
                                 f"explicitly documented target population "
                                 f"(docs/production-contract.md).",
            "implication": "production's OCR is configured ocr_languages=[en,vi] "
                          "(no zh model) -- roughly half of OmniDocBench's "
                          "content is in a language this system's PRODUCTION "
                          "configuration was never built to recognize. This "
                          "is not a system weakness measured fairly; it is a "
                          "language mismatch, and per Phase 16/2's explicit "
                          "instruction, was NOT worked around by adding zh "
                          "(007 already showed that costs English 43.6% and "
                          "collapses English table structure).",
        },
        {
            "property": "document type",
            "omnidocbench": f"book, PPT2PDF, academic_literature, exam_paper, "
                            f"colorful_textbook, newspaper, magazine, "
                            f"research_report, note, historical_document "
                            f"({dist['data_source']})",
            "production_corpus": "enterprise business documents: invoices, "
                                 "contracts, business licenses, certificates, "
                                 "purchase orders, technical reports "
                                 "(docs/production-contract.md target population)",
            "implication": "almost entirely disjoint document TYPES -- "
                          "OmniDocBench measures general document "
                          "understanding across publishing/academic/media "
                          "genres; production measures enterprise "
                          "transactional-document extraction. A system "
                          "tuned for one is not expected to be optimal for "
                          "the other by construction.",
        },
        {
            "property": "table density",
            "omnidocbench": f"665 table regions across 1651 pages "
                            f"(~0.40/page), plus a dedicated table_hard "
                            f"subset (97 pages) with complex nested tables",
            "production_corpus": f"{n_expected_tables}/{len(all_prod_docs)} documents "
                                 f"have >=1 expected table -- tables are a "
                                 f"CENTRAL, deliberately-engineered hard-"
                                 f"case category (029-033's entire research "
                                 f"chain), not incidental content",
            "implication": "both corpora care about tables, but for "
                          "different reasons: OmniDocBench samples table "
                          "STRUCTURE diversity broadly; the production "
                          "corpus specifically engineers table+stamp/"
                          "occlusion INTERACTION, which OmniDocBench's "
                          "attribute schema does not label at all (see "
                          "'stamps/occlusion' row).",
        },
        {
            "property": "OCR difficulty",
            "omnidocbench": "varied print quality, some historical documents "
                            "with geometric_deformation/low-resolution "
                            "special_issue tags",
            "production_corpus": "deliberately engineered hard cases: "
                                 "corrupt CMap encoding, low contrast, "
                                 "watermarks, rotated regions, small text "
                                 "(research/hardcases/, 14 EN/VI cases)",
            "implication": "both stress OCR, via different, largely "
                          "non-overlapping mechanisms.",
        },
        {
            "property": "stamps/occlusion",
            "omnidocbench": "NOT a labelled attribute anywhere in the "
                            "page_attribute schema (data_source/language/"
                            "layout/special_issue/subset -- none of these "
                            "cover stamps or seals). special_issue values "
                            "observed: watermark, geometric_deformation, "
                            "others -- not stamp-specific.",
            "production_corpus": "THE central mechanism of 025/029/030/031's "
                                 "entire research chain -- 7 documents with "
                                 "table-shaped picture-labelled regions "
                                 "under stamps, 2 with a confirmed real "
                                 "route-driven table/picture flip (031).",
            "implication": "the single most production-critical phenomenon "
                          "this research chain has found (table-label "
                          "gating under stamps) has NO corresponding "
                          "ground-truth attribute in OmniDocBench -- "
                          "confirmed absent, not merely unmeasured (see "
                          "cross_research_comparison.json Phase 10).",
        },
        {
            "property": "forms",
            "omnidocbench": "not a distinct data_source or category_type "
                            "(closest: 'text_block'/'table' categories "
                            "generically) -- production-contract.md itself "
                            "notes forms are 'not implemented' in this "
                            "system, and 032/033 confirmed a real "
                            "checkbox_selected/unselected label-mapping "
                            "bug that has never manifested in any "
                            "historical experiment artifact",
            "production_corpus": "present as isolated hard-case documents "
                                 "(ord_form_vi, hc_checkbox_vi -- found by "
                                 "033's own negative_controls.json search) "
                                 "but NOT a scored capability",
            "implication": "neither corpus scores forms as a first-class "
                          "capability; both would need new evidence to "
                          "measure this properly.",
        },
        {
            "property": "multi-column text",
            "omnidocbench": "an explicit page_attribute value: layout in "
                            "{single_column, 1andmore_column, other_layout} "
                            "-- directly labelled and filterable",
            "production_corpus": "present but not a labelled attribute; "
                                 "production-contract.md rates multi-column "
                                 "'good (100% text; ordering is the open "
                                 "question)'",
            "implication": "OmniDocBench can isolate multi-column "
                          "performance directly via its own attribute "
                          "filter; the production corpus cannot without "
                          "manual re-labelling -- a genuine measurement "
                          "capability OmniDocBench has that the internal "
                          "corpus lacks.",
        },
        {
            "property": "layout complexity",
            "omnidocbench": "explicit layout_hard subset (99 pages) plus "
                            "the layout attribute field",
            "production_corpus": "not a labelled dimension; complexity is "
                                 "implicit in which hard_case_labels a "
                                 "document carries",
            "implication": "same asymmetry as multi-column: OmniDocBench "
                          "has a purpose-built difficulty axis here.",
        },
        {
            "property": "structural annotation",
            "omnidocbench": "rich: category_type per region (text_block, "
                            "title, table, figure, equation_*, header/"
                            "footer, etc.) -- OUTPUT-level (what SHOULD be "
                            "in the final document), not internal-pipeline-"
                            "level",
            "production_corpus": "no independent ground-truth region "
                                 "annotation at all -- 028-033's Layer-2 "
                                 "evaluation instead inspects THIS "
                                 "system's OWN produced IR directly "
                                 "(structural_integrity, recovery "
                                 "verdicts, etc.), with no external "
                                 "reference to compare against",
            "implication": "fundamentally different evaluation "
                          "philosophies: OmniDocBench validates against "
                          "an independent ground truth (external "
                          "validity); 023-033 validates the SYSTEM'S OWN "
                          "internal consistency and evidence integrity "
                          "(reliability under its own logic) -- see "
                          "cross_research_comparison.json.",
        },
        {
            "property": "evidence ownership annotation",
            "omnidocbench": "NONE -- the evaluator compares final "
                            "predicted markdown/table/formula text against "
                            "ground truth text; it has no concept of "
                            "'which token belongs to which region' "
                            "ownership, duplication, or orphan evidence "
                            "at all",
            "production_corpus": "THE central subject of 025/028/029's "
                                 "evidence-ownership research (orphan "
                                 "tokens, 82-token overlapping-ownership "
                                 "finding, duplicate emission)",
            "implication": "evidence ownership/duplication (Class B/C in "
                          "the 023-033 taxonomy) is STRUCTURALLY invisible "
                          "to OmniDocBench's methodology -- not a gap in "
                          "this run, a gap in what any output-text-"
                          "comparison benchmark CAN measure.",
        },
        {
            "property": "provenance",
            "omnidocbench": "none -- ground truth carries no notion of "
                            "'why' a region has its label; it IS the label",
            "production_corpus": "central to 031/032/033's provenance "
                                 "design work (source_backend, "
                                 "Element.extra, routing_decision) -- but "
                                 "this is a PRODUCTION IR property, not "
                                 "something any benchmark's ground truth "
                                 "would carry either",
            "implication": "not a meaningful comparison axis -- neither "
                          "corpus's GROUND TRUTH has provenance; "
                          "provenance is a property of THIS system's "
                          "output, orthogonal to which input corpus is used.",
        },
    ]

    payload = {
        "purpose": "determine why benchmark results might differ from "
                 "production-shaped reliability results -- NOT to declare "
                 "one corpus better than the other.",
        "matrix": matrix,
        "conclusion": (
            "OmniDocBench and the production-shaped corpus are almost "
            "entirely complementary, not overlapping: OmniDocBench "
            "provides external validity on OUTPUT accuracy across a "
            "language/genre/layout distribution the production corpus "
            "never samples; the production corpus provides internal "
            "evidence-integrity validation (ownership, duplication, "
            "label-gating, role ambiguity) that OmniDocBench's output-only "
            "methodology cannot see by construction. A strong result on "
            "one says little about the other axis."
        ),
    }
    Path("benchmark_vs_production_corpus.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False))
    print(f"matrix rows: {len(matrix)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
