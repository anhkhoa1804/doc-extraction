"""035 Phase 10 -- stamp/occlusion test, using actual external benchmark
evidence (page_attribute.special_issue, captured per-record by Phase 3),
not assumed. OmniDocBench has NO 'stamp' category (Phase 1 GT contract) --
the closest proxies are 'watermark'/'with_watermark', 'fuzzy_scan',
'fuzzy_content', 'geometric_deformation', 'transparent_pages'. Table-
specific structural tags ('table_horizontal', 'table_full_line', etc.) are
NOT occlusion and are excluded from the "occlusion proxy" set here, kept
separate for comparison instead.

Question: does occlusion predict WRONG LABEL specifically (D2), or does it
merely predict general extraction difficulty (any non-D0 stage)? These are
different claims -- 030 already found stamp alone was NOT sufficient
explanation for the row-synthesis mechanism on the production corpus; this
phase checks whether the analogous pattern holds here.

    python experiments/035_mechanism_d_gating/phase10_stamp_occlusion.py
"""
from __future__ import annotations
import json, sys
from pathlib import Path
from collections import Counter
HERE = Path(__file__).resolve().parent

OCCLUSION_PROXY_TAGS = {"watermark", "with_watermark", "fuzzy_scan", "fuzzy_content", "geometric_deformation", "transparent_pages"}


def main():
    import importlib.util
    spec = importlib.util.spec_from_file_location("p4", HERE / "phase4_9_14_funnel.py")
    p4 = importlib.util.module_from_spec(spec)
    sys.modules["p4"] = p4
    spec.loader.exec_module(p4)

    matching = json.loads((HERE / "table_region_matching.json").read_text())
    records = matching["records"]

    import matching_lib as ml
    CHUNK_DIRS = ml.gt_table_run_roots(HERE)
    raw_by_image = {}
    for cd in CHUNK_DIRS:
        if not cd.exists():
            continue
        for run_dir in cd.iterdir():
            meta_p, tables_p = run_dir / "metadata.json", run_dir / "tables" / "page-001.json"
            if meta_p.exists() and tables_p.exists():
                meta = json.loads(meta_p.read_text())
                raw_by_image[meta["input_filename"]] = json.loads(tables_p.read_text()).get("tables", [])
    for rec in records:
        rec["_tables_raw_for_page"] = raw_by_image.get(rec["image"])
        rec["_stage"], _ = p4.classify_stage(rec)

    def has_occlusion(rec):
        return bool(set(rec.get("special_issue", [])) & OCCLUSION_PROXY_TAGS)

    occluded = [r for r in records if has_occlusion(r)]
    clean = [r for r in records if not has_occlusion(r)]

    def stage_rate(pop, stage):
        return round(sum(1 for r in pop if r["_stage"] == stage) / len(pop), 4) if pop else None

    def any_failure_rate(pop):
        return round(sum(1 for r in pop if r["_stage"] != "D0") / len(pop), 4) if pop else None

    result = {
        "occlusion_proxy_tags_used": sorted(OCCLUSION_PROXY_TAGS),
        "n_gt_tables_analyzed": len(records),
        "n_occluded": len(occluded), "n_clean": len(clean),
        "d2_rate_occluded": stage_rate(occluded, "D2"),
        "d2_rate_clean": stage_rate(clean, "D2"),
        "any_failure_rate_occluded": any_failure_rate(occluded),
        "any_failure_rate_clean": any_failure_rate(clean),
        "occluded_stage_distribution": dict(Counter(r["_stage"] for r in occluded).most_common()),
        "clean_stage_distribution": dict(Counter(r["_stage"] for r in clean).most_common()),
        "by_specific_tag": {
            tag: {
                "n": sum(1 for r in records if tag in r.get("special_issue", [])),
                "d2_rate": stage_rate([r for r in records if tag in r.get("special_issue", [])], "D2"),
                "any_failure_rate": any_failure_rate([r for r in records if tag in r.get("special_issue", [])]),
            }
            for tag in sorted(OCCLUSION_PROXY_TAGS)
        },
        "interpretation": {
            "note": "Compare d2_rate_occluded vs d2_rate_clean (does occlusion predict "
                "WRONG LABEL specifically) against any_failure_rate_occluded vs "
                "any_failure_rate_clean (does it predict general difficulty instead). "
                "030's own finding on the production corpus was that stamp/occlusion "
                "alone was NOT sufficient explanation (PARTIALLY_SUPPORTED, route/OCR/"
                "layout interaction mattered more) -- this phase checks whether the same "
                "qualitative pattern holds on an independent benchmark, without assuming "
                "it must.",
        },
        "caveat": "This benchmark has NO true stamp/occlusion category (Phase 1) -- "
            "these are the closest available proxies, at PAGE granularity (ambiguous "
            "across multi-table pages, per the GT contract's own limitation). A null "
            "result here does not prove occlusion is irrelevant to Mechanism D in "
            "general, only that these specific proxies on this benchmark don't show it.",
    }
    Path(HERE / "stamp_occlusion_analysis.json").write_text(json.dumps(result, indent=1, ensure_ascii=False))
    print(f"occluded n={len(occluded)} D2 rate={result['d2_rate_occluded']}, clean n={len(clean)} D2 rate={result['d2_rate_clean']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
