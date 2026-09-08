"""034a Phase 17/19/20 -- research interpretation, four dimensions
(accuracy, reliability, generalization, efficiency), and the final
VALIDATES/PARTIALLY_VALIDATES/CHALLENGES/INCONCLUSIVE decision.

    python experiments/034a_omnidocbench_snapshot/recommendation.py
"""
from __future__ import annotations
import json
from pathlib import Path
HERE = Path(__file__).resolve().parent


def safe_load(name):
    p = HERE / name
    return json.loads(p.read_text()) if p.exists() else None


def main():
    subset_metrics = safe_load("results/subset_B_fixed_auto/metrics.json")
    failure = safe_load("failure_analysis_subset_B_fixed_auto.json")
    cross = safe_load("cross_research_comparison.json")
    diag = safe_load("device_resolution_diagnosis.json")
    selected = safe_load("selected_benchmark_config.json")
    full_runtime = safe_load("results/full_baseline/runtime.json")

    tb = subset_metrics["text_block"]["all"]["Edit_dist"]["ALL_page_avg"]
    ro = subset_metrics["reading_order"]["all"]["Edit_dist"]["ALL_page_avg"]
    teds = subset_metrics["table"]["all"]["TEDS"]["all"]

    payload = {
        "phase_17_four_dimensions": {
            "1_accuracy": {
                "question": "How good is the system externally?",
                "answer": (
                    f"MIXED, sharply language-dependent. text_block Edit_dist "
                    f"(subset, 77 pages) = {tb:.4f}; by language: english "
                    f"mean approx-similarity 0.5028, simplified_chinese "
                    f"0.0301 (failure_analysis_subset_B_fixed_auto.json) -- a "
                    f"16.7x gap. Table TEDS = {teds:.4f}, but computed from "
                    f"only 11/37 samples due to a confirmed evaluator-side "
                    f"multiprocessing bug (cross_research_comparison.json "
                    f"mechanism E), not a clean number. reading_order "
                    f"Edit_dist = {ro:.4f}."
                ),
                "caveat": "subset-based (77/1651 pages) at the time this was "
                        "written -- see full_baseline status for the "
                        "complete-corpus numbers once available.",
            },
            "2_reliability": {
                "question": "What failure mechanisms remain?",
                "answer": (
                    "A genuine, previously-latent production bug was found "
                    "and fixed this milestone (process_file() never resolved "
                    "device='auto', device_resolution_diagnosis.json) -- "
                    "zero prior callers had ever triggered it. Separately, "
                    "the OFFICIAL EVALUATOR ITSELF has a reliability bug "
                    "(TEDS worker-pool race, 26/37 samples failing with "
                    "'AssertionError: can only join a started process') -- "
                    "external to this project, but materially corrupts the "
                    "table accuracy signal any consumer of this benchmark "
                    "would report."
                ),
            },
            "3_generalization": {
                "question": "Which 023-033 findings reproduce?",
                "answer": cross["headline_finding"] if cross else None,
            },
            "4_efficiency": {
                "question": "What is the cost of achieving current performance?",
                "answer": (
                    "Layout (Docling) dominates end-to-end latency at ~89% "
                    "of total pipeline time (pipeline_timing json). GPU "
                    "concurrency gives real, measured speedups (C2: 1.71x, "
                    "C4: 2.60x) but both push VRAM to within 1-4% of total "
                    "capacity on just a 77-page sample -- not selected for "
                    "the full run out of caution (selected_benchmark_"
                    "config.json). The GPU was also legitimately PROTECTED "
                    "mid-milestone by another project's training job "
                    "(Research-No.1), requiring an immediate, clean switch "
                    "to CPU-only and back -- a real, live test of this "
                    "system's own GPU-sharing policy, not a hypothetical one."
                ),
            },
        },
        "phase_19_core_question": {
            "question": "Does OmniDocBench validate the current architecture, "
                       "challenge it, or reveal it measures a materially "
                       "different problem?",
            "answer": (
                "MATERIALLY DIFFERENT PROBLEM, primarily. OmniDocBench is an "
                "output-text-comparison benchmark over a Chinese/English "
                "general-document corpus; this system is built and "
                "evaluated for English/Vietnamese enterprise-document "
                "evidence INTEGRITY (ownership, duplication, role "
                "ambiguity, label-gating -- the entire 023-033 research "
                "chain). Three of eight 023-033 failure mechanisms are "
                "structurally invisible to OmniDocBench's methodology no "
                "matter how the benchmark is run (cross_research_"
                "comparison.json); the benchmark's single largest measured "
                "effect (the english/chinese gap) is not a defect this "
                "research chain is trying to fix, but a known, deliberate, "
                "previously-documented scope boundary (007). Two mechanisms "
                "(text fidelity, reading order) DO reproduce directly and "
                "give real external signal."
            ),
        },
        "device_bug_disposition": {
            "classification": diag["phase_2_classification"] if diag else None,
            "recommendation": (
                "Prepare this as a SEPARATE, narrowly-scoped production "
                "commit -- NOT folded silently into a benchmark-snapshot "
                "commit. The fix (process_file() guards config.device==="
                "'auto' before backend construction) is minimal, has a "
                "passing regression test (tests/test_cli_device_"
                "resolution.py), is a strict no-op for all 15 already-"
                "protected callers, and closes a real gap in a documented, "
                "first-class config value ('auto') that any future caller "
                "could hit. Recommend committing it on its own, with its "
                "own commit message, reviewable independently of the "
                "OmniDocBench snapshot's research content."
            ),
        },
        "selected_config_for_record": selected["decision"] if selected else None,
    }

    Path("recommendation.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False))
    print(json.dumps(payload["phase_19_core_question"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
