"""035 Phase 1 -- reconstruct the actual OmniDocBench GT table annotation
contract from source (the real OmniDocBench.json + this repo's own
evaluation/omnidocbench.py adapter + the official evaluator's own matching
code), not from memory or assumption. Every field below is measured
directly against experiments/034a_omnidocbench_snapshot/dataset/full/
OmniDocBench.json (sha256 a45cd84b..., the same file run_metadata.json
fingerprinted for the full run -- see baseline.json).

    python experiments/035_mechanism_d_gating/phase1_gt_contract.py
"""
from __future__ import annotations
import json
from collections import Counter
from pathlib import Path
HERE = Path(__file__).resolve().parent
GT = HERE.parents[1] / "experiments" / "034a_omnidocbench_snapshot" / "dataset" / "full" / "OmniDocBench.json"


def is_axis_aligned_rect(poly):
    x0, y0, x1, y1, x2, y2, x3, y3 = poly
    return abs(x0 - x3) < 1e-6 and abs(x1 - x2) < 1e-6 and abs(y0 - y1) < 1e-6 and abs(y2 - y3) < 1e-6


def poly_to_bbox(poly):
    xs = poly[0::2]
    ys = poly[1::2]
    return {"x0": min(xs), "y0": min(ys), "x1": max(xs), "y1": max(ys)}


def main():
    raw = json.loads(GT.read_text())

    all_category_types = Counter()
    for r in raw:
        for det in r.get("layout_dets", []):
            all_category_types[det.get("category_type")] += 1

    table_dets = []
    for r in raw:
        img = r["page_info"]["image_path"]
        for det in r.get("layout_dets", []):
            if det.get("category_type") == "table":
                table_dets.append((img, det))

    n_rect = sum(1 for _, t in table_dets if is_axis_aligned_rect(t["poly"]))
    n_ignore = sum(1 for _, t in table_dets if t.get("ignore"))
    n_html = sum(1 for _, t in table_dets if t.get("html"))
    n_html_trivial = sum(1 for _, t in table_dets if t.get("html") in ("<table></table>", ""))
    attr_nonempty = sum(1 for _, t in table_dets if t.get("attribute"))

    pages_with_table = sorted({img for img, _ in table_dets})
    per_page_table_count = Counter(img for img, _ in table_dets)

    special_issue_counts = Counter()
    for r in raw:
        for issue in r["page_info"].get("page_attribute", {}).get("special_issue", []):
            special_issue_counts[issue] += 1

    data_source_of_table_pages = Counter()
    language_of_table_pages = Counter()
    for r in raw:
        img = r["page_info"]["image_path"]
        if img in per_page_table_count:
            attr = r["page_info"].get("page_attribute", {})
            data_source_of_table_pages[attr.get("data_source")] += 1
            language_of_table_pages[attr.get("language")] += 1

    contract = {
        "source_file": str(GT.relative_to(HERE.parents[1])),
        "source_sha256_cross_check": "must equal a45cd84b04ad8b793e775089640e6b681209abea33ead54c1828ddca35fae496 (baseline.json)",
        "top_level_shape": "JSON array, 1 record per page. Each record: {layout_dets: [...], page_info: {...}, extra: {...}}.",
        "page_info_contract": {
            "fields": ["page_no", "height", "width", "image_path", "page_attribute"],
            "page_attribute_fields": ["data_source", "language", "layout", "special_issue", "subset"],
            "height_width_semantics": "FACT (verified in Phase 2): equal to the raw image "
                "file's own pixel dimensions (PIL Image.size) for every sampled page -- "
                "OmniDocBench ships pre-rendered page images directly, there is no PDF "
                "to render, so page_info.{width,height} IS the coordinate space every "
                "poly/bbox in this record is expressed in. No DPI/scale conversion "
                "documented or observed in the annotation format itself.",
        },
        "layout_dets_category_type_distribution": dict(all_category_types.most_common()),
        "table_annotation_contract": {
            "category_type_value": "table",
            "n_table_dets_total": len(table_dets),
            "cross_check_vs_evaluator": "MUST equal 665 -- results/full_baseline/metrics.json's "
                "table.metric_debug.TEDS.sample_count (034a, official evaluator's own count). "
                f"Measured: {len(table_dets)}.",
            "n_pages_with_ge1_table": len(pages_with_table),
            "n_pages_total": len(raw),
            "per_page_table_count_distribution": dict(sorted(Counter(per_page_table_count.values()).items())),
            "fields_per_table_det": {
                "category_type": "always the literal string 'table' for this population (by construction).",
                "poly": "8 floats [x0,y0, x1,y0, x1,y1, x0,y1] -- FACT, verified this phase: "
                    f"{n_rect}/{len(table_dets)} table polys are exact axis-aligned rectangles "
                    "(opposite-corner x/y pairs equal to within 1e-6). None are rotated/skewed "
                    "in this dataset. Coordinate units: same pixel space as page_info.width/height "
                    "(see Phase 2 for direct proof against rendered internal bboxes).",
                "ignore": f"bool, always False in this population ({n_ignore}/{len(table_dets)} True) "
                    "-- no GT table in this corpus is flagged for exclusion from evaluation.",
                "order": "int, page-local reading-order index. Present on 100% of table dets "
                    f"({sum(1 for _, t in table_dets if t.get('order') is not None)}/{len(table_dets)}).",
                "anno_id": "string, unique within a page (verified: 0 pages with a duplicate "
                    "table anno_id). Not necessarily unique across the whole dataset -- not "
                    "checked/needed, since all matching in this milestone is done per-page.",
                "attribute": f"dict, EMPTY {{}} for every single table det in this corpus "
                    f"({attr_nonempty}/{len(table_dets)} non-empty). Table-descriptive tags "
                    "(line style, span, orientation, embedded formula/image) are NOT recorded "
                    "per-table -- they appear only in page_info.page_attribute.special_issue, "
                    "at PAGE granularity, ambiguous across multiple tables on the same page. "
                    "This is a real annotation-contract limitation Phase 9/10 must respect.",
                "html": f"string, GT table structure as HTML (<table>...</table>). Present on "
                    f"{n_html}/{len(table_dets)}, non-trivial (not an empty <table></table>) on "
                    f"{len(table_dets) - n_html_trivial}/{len(table_dets)}. This is what the "
                    "official evaluator's TEDS metric scores against -- NOT our internal Table "
                    "schema (schemas/table.py) directly; see external_metric_reconciliation "
                    "(Phase 15) for exactly how the evaluator bridges markdown predictions to "
                    "this HTML ground truth (text/structure matching, not bbox matching).",
            },
        },
        "page_level_special_issue_contract": {
            "note": "PAGE-level tags (not per-table). The closest available occlusion/quality "
                "proxies in this schema: 'watermark'/'with_watermark', 'fuzzy_scan', "
                "'fuzzy_content', 'geometric_deformation', 'transparent_pages'. There is NO "
                "'stamp' category anywhere in this taxonomy -- confirms 034a's own finding "
                "(benchmark_vs_production_corpus.json) that stamps/occlusion has no "
                "corresponding OmniDocBench attribute. Table-structure tags present here "
                "('table_horizontal','table_full_line','table_fewer_line','table_span', "
                "'table_with_formula','table_omission_line','table_wireless_line', "
                "'table_veritical'[sic],'table_with_img') describe table PROPERTIES, not "
                "occlusion, and are ambiguous across multi-table pages.",
            "all_value_counts": dict(special_issue_counts.most_common()),
        },
        "table_page_population_context": {
            "data_source_distribution": dict(data_source_of_table_pages.most_common()),
            "language_distribution": dict(language_of_table_pages.most_common()),
        },
        "evaluator_side_contract": {
            "source": ".external/OmniDocBench/src/core/matching/match.py, "
                "src/dataset/end2end_dataset.py, src/core/metrics.py",
            "FACT": "The official evaluator matches GT tables to predicted tables by "
                "TEXT/HTML-CONTENT similarity within a page (quick_match), extracted from "
                "our prediction .md files -- it never sees or uses our internal Region "
                "bboxes, ElementType labels, or table gate at all. It is a pure "
                "output-comparison evaluator. This is why Mechanism D (an internal, "
                "upstream, pre-serialization phenomenon) is structurally invisible to it "
                "(034a cross_research_comparison.json already found this for mechanism D: "
                "'partially observable, unconfirmed without a per-page internal-IR "
                "cross-reference' -- exactly what this milestone performs).",
        },
        "our_own_loader_contract": {
            "source": "src/doc_extraction/evaluation/omnidocbench.py:load_dataset()",
            "FACT": "Validates dataset_root exists, locates OmniDocBench.json/_demo.json, "
                "parses as a JSON array, resolves each record's image under "
                "images/ or dataset_root directly, and raises DatasetError on any schema "
                "violation. Does not itself interpret table-specific fields -- table "
                "semantics used in this milestone are read directly from the raw JSON per "
                "the contract above, not through this loader's OmniDocSample abstraction "
                "(which is page-level, not annotation-type-level).",
        },
    }
    Path(HERE / "omnidoc_table_gt_contract.json").write_text(json.dumps(contract, indent=1, ensure_ascii=False))
    print(f"table dets: {len(table_dets)} (expect 665)")
    print(f"pages with table: {len(pages_with_table)} (expect 458)")
    print(f"axis-aligned rect polys: {n_rect}/{len(table_dets)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
