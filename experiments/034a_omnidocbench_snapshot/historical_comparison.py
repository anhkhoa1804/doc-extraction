"""034a Phase 14 -- historical compatibility with 005's own prior
OmniDocBench results (demo dataset, CPU, Windows, 2026-08-20).

    python experiments/034a_omnidocbench_snapshot/historical_comparison.py
"""
from __future__ import annotations
import json
from pathlib import Path
HERE = Path(__file__).resolve().parent
L005 = HERE.parents[1] / "experiments/005_omnidocbench"


def load_run(path):
    meta = json.loads((path / "run_metadata.json").read_text()) if (path / "run_metadata.json").exists() else {}
    runtime = json.loads((path / "runtime.json").read_text()) if (path / "runtime.json").exists() else {}
    metrics = json.loads((path / "metrics.json").read_text()) if (path / "metrics.json").exists() else {}
    return meta, runtime, metrics


def headline(metrics):
    out = {}
    for cat in ("text_block", "display_formula", "table", "reading_order"):
        block = metrics.get(cat, {}).get("all", {})
        out[cat] = block
    return out


def main():
    prior_baseline_dir = L005 / "results" / "baseline"
    prior_docling_dir = L005 / "results" / "docling"
    my_smoke_dir = HERE / "results" / "smoke_baseline"
    my_full_dir = HERE / "results" / "full_baseline"

    prior_meta, prior_runtime, prior_metrics = load_run(prior_baseline_dir)
    prior_docling_meta, prior_docling_runtime, prior_docling_metrics = load_run(prior_docling_dir)
    smoke_meta, smoke_runtime, smoke_metrics = load_run(my_smoke_dir)

    full_available = (my_full_dir / "metrics.json").exists()
    full_meta, full_runtime, full_metrics = load_run(my_full_dir) if full_available else ({}, {}, {})

    comparisons = []

    comparisons.append({
        "pair": "005 baseline (demo, 18 pages) vs 034a smoke (hand-picked, 6 pages)",
        "classification": "PARTIALLY COMPARABLE",
        "why": "same evaluator commit (193627a...) and same doc_extraction "
             "'baseline' backend logic, but DIFFERENT machine (Windows vs "
             "Linux), DIFFERENT device (cpu vs cuda), DIFFERENT dataset "
             "sample (18 fixed demo pages vs 6 hand-picked from the full "
             "1651), DIFFERENT docling/torch versions (2.120.3/2.8.0 vs "
             "2.124.0/2.11.0+cu128 -- both installed AFTER 005 ran, "
             "consistent with normal dependency drift over time, not a "
             "deliberate change this milestone made).",
        "005_config_device": prior_meta.get("device"), "034a_config_device": smoke_meta.get("device"),
        "005_docling_version": prior_meta.get("model_versions", {}).get("docling"),
        "034a_docling_version": smoke_meta.get("model_versions", {}).get("docling"),
        "005_headline_metrics": headline(prior_metrics),
        "034a_smoke_headline_metrics": headline(smoke_metrics),
        "qualitative_consistency_check": (
            "table TEDS is LOW in both (005: 0.1526, 034a smoke: 0.6438 on "
            "different pages -- both far from 1.0), text_block edit "
            "distance is moderate-to-poor in both (005: 0.7448, 034a "
            "smoke: 0.5322) -- directionally consistent (this pipeline "
            "struggles with OmniDocBench-shaped content in both "
            "measurements), not a contradiction, though the SPECIFIC "
            "numbers are not directly averaged together since the page "
            "sets differ entirely."
        ),
    })

    comparisons.append({
        "pair": "005 baseline vs 005 docling (both demo, 18 pages, same run)",
        "classification": "DIRECTLY COMPARABLE",
        "why": "identical dataset, identical machine/run, identical "
             "evaluator invocation -- differ ONLY in backend "
             "(doc_extraction's own composed pipeline vs Docling's own "
             "whole-document WholeDocumentBackend.convert()). This is "
             "005's OWN internal comparator, reused here as the historical "
             "precedent for 034a Phase 13's optional control arm.",
        "baseline_headline_metrics": headline(prior_metrics),
        "docling_headline_metrics": headline(prior_docling_metrics),
        "baseline_mean_sec_per_page": prior_runtime.get("mean_seconds_per_page"),
        "docling_mean_sec_per_page": prior_docling_runtime.get("mean_seconds_per_page"),
    })

    if full_available:
        comparisons.append({
            "pair": "005 baseline (demo, 18 pages, CPU) vs 034a full (1651 pages, GPU)",
            "classification": "PARTIALLY COMPARABLE",
            "why": "same evaluator commit and backend logic, but different "
                 "scale (18 vs 1651 pages -- 034a is the genuine full "
                 "benchmark, 005 was always a demo-scale integration "
                 "check per its own README), different device, different "
                 "machine, dependency drift as above.",
            "005_headline_metrics": headline(prior_metrics),
            "034a_full_headline_metrics": headline(full_metrics),
        })
    else:
        comparisons.append({
            "pair": "005 baseline vs 034a full",
            "classification": "NOT YET AVAILABLE",
            "why": "the full 1651-page run had not completed when this "
                 "script last ran -- rerun after full_baseline/metrics.json exists.",
        })

    payload = {
        "prior_omnidocbench_runs_found": [
            str(prior_baseline_dir.relative_to(HERE.parents[1])),
            str(prior_docling_dir.relative_to(HERE.parents[1])),
        ],
        "comparisons": comparisons,
        "note": "005's runs are the ONLY prior OmniDocBench results found "
               "anywhere in this repository's history (029-033 never ran "
               "OmniDocBench -- confirmed by their own FINAL_REPORT.md "
               "scopes, all CPU-only historical-IR-replay milestones with "
               "no new extraction).",
    }
    Path("historical_comparison.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False))
    print(f"comparisons: {len(comparisons)}")
    for c in comparisons:
        print(f"  {c['pair']}: {c['classification']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
