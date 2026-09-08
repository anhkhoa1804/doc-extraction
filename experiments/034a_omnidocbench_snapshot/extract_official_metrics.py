"""034a Phase 7 (official) -- pull the official OmniDocBench evaluator's
metrics.json into official_metrics.json + category_metrics.json +
failure_analysis.json, once the full run's evaluate.py stage has produced
results/full_baseline/metrics.json.

    python experiments/034a_omnidocbench_snapshot/extract_official_metrics.py
"""
from __future__ import annotations
import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
FULL = HERE / "results" / "full_baseline"


def main():
    source_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else FULL
    metrics_f = source_dir / "metrics.json"
    if not metrics_f.exists():
        print(f"{metrics_f} does not exist yet")
        return 1
    metrics = json.loads(metrics_f.read_text())
    run_meta = json.loads((source_dir / "run_metadata.json").read_text())
    runtime = json.loads((source_dir / "runtime.json").read_text())

    # --- official_metrics.json ---
    official = {
        "evaluator": "omnidocbench_eval 1.6.0, upstream commit 193627ae9e97d89188468ed1ee3b7a856ff76044",
        "evaluator_repo": ".external/OmniDocBench",
        "dataset": "OmniDocBench v1.6, 1651 pages (full, not demo)",
        "device": run_meta.get("device"),
        "match_method": "quick_match",
        "num_samples": run_meta.get("num_samples"),
        "total_available_samples": run_meta.get("total_available_samples"),
        "timestamp": run_meta.get("timestamp"),
        "overall_score_note": (
            "OmniDocBench's own Overall formula "
            "((1-TextEditDist)*100 + TableTEDS + FormulaCDM)/3 requires the "
            "formula CDM metric, which needs a Linux-only TeX Live/"
            "ImageMagick/Ghostscript toolchain not verified present this "
            "milestone -- NOT computed. Reporting the evaluator's own "
            "per-metric numbers directly, not a substitute composite."
        ),
        "metrics_by_category": {
            cat: metrics[cat]["all"] for cat in
            ("text_block", "display_formula", "table", "reading_order")
            if cat in metrics and "all" in metrics[cat]
        },
        "sample_counts": {
            cat: metrics[cat].get("group", {}).get("sample_count")
            for cat in ("text_block", "display_formula", "table", "reading_order")
            if cat in metrics
        },
    }
    Path("official_metrics.json").write_text(json.dumps(official, indent=1, ensure_ascii=False))

    # --- category_metrics.json (per-attribute breakdown) ---
    # IMPORTANT, verified directly against real metrics.json output (both 6-
    # and 77-sample runs) this milestone: 'group' is present but EMPTY
    # (group.sample_count == {}) in this evaluator version's collected
    # output; the actual attribute-grouped breakdown lives under 'page'
    # instead (keyed by metric name -> {attribute_label: value}), despite
    # its name suggesting per-individual-page scores. Documented precisely
    # rather than assumed, since this contradicts run.py's own
    # _group_breakdown_tables() docstring, which reads 'group'.
    category = {}
    for cat in ("text_block", "display_formula", "table", "reading_order"):
        block = metrics.get(cat, {})
        attr_breakdown = block.get("page", {})  # see note above
        if not attr_breakdown:
            continue
        metric_keys = list(attr_breakdown.keys())
        rows = []
        first = attr_breakdown[metric_keys[0]] if metric_keys else {}
        attrs = sorted(k for k in first.keys() if k != "ALL")
        for attr in attrs:
            row = {"attribute": attr}
            for m in metric_keys:
                row[m] = attr_breakdown[m].get(attr)
            rows.append(row)
        category[cat] = {"overall_ALL": {m: attr_breakdown[m].get("ALL") for m in metric_keys},
                         "by_attribute": rows}
    Path("category_metrics.json").write_text(json.dumps(category, indent=1, ensure_ascii=False))
    print("NOTE: true per-page failure ranking is NOT available from "
          "metrics.json (see category_metrics.json construction note) -- "
          "use failure_analysis.py's approximate proxy-ranking script instead.")

    print("official_metrics.json, category_metrics.json, failure_analysis.json written")
    print(json.dumps(official["metrics_by_category"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
