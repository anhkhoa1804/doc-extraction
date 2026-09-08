"""034a Phase 16 -- aggregate performance model from every measurement
taken this milestone: smoke, subset A/B (correctness), C2/C4
(concurrency), pipeline timing breakdown, and the full CPU run (appended
once available).

    python experiments/034a_omnidocbench_snapshot/performance.py
"""
from __future__ import annotations
import json
from pathlib import Path
HERE = Path(__file__).resolve().parent


def safe_load(name):
    p = HERE / name
    return json.loads(p.read_text()) if p.exists() else None


def main():
    smoke = safe_load("smoke_test.json")
    b_runtime = safe_load("results/subset_B_fixed_auto/runtime.json")
    a_runtime = safe_load("results/subset_A_workaround/runtime.json")
    c2 = safe_load("concurrency_c2.json")
    c4 = safe_load("concurrency_c4.json")
    timing = safe_load("pipeline_timing_results_timing_probe.json") or safe_load("pipeline_timing_timing_probe.json")
    full_runtime = safe_load("results/full_baseline/runtime.json")

    payload = {
        "smoke_6_pages_gpu_cuda": {
            "wall_seconds": smoke.get("smoke_runtime_seconds") if smoke else None,
            "mean_sec_per_page": smoke.get("smoke_mean_seconds_per_page") if smoke else None,
        },
        "subset_77_pages_serial_gpu": {
            "config_A_workaround_cuda_literal": {
                "wall_seconds": a_runtime.get("wall_clock_seconds") if a_runtime else None,
                "mean_sec_per_page": a_runtime.get("mean_seconds_per_page") if a_runtime else None,
                "pages_per_second": a_runtime.get("pages_per_second") if a_runtime else None,
            },
            "config_B_fixed_auto": {
                "wall_seconds": b_runtime.get("wall_clock_seconds") if b_runtime else None,
                "mean_sec_per_page": b_runtime.get("mean_seconds_per_page") if b_runtime else None,
                "pages_per_second": b_runtime.get("pages_per_second") if b_runtime else None,
            },
            "A_vs_B_byte_identical": True,
        },
        "concurrency_gpu": {
            "C1_serial": {"pages_per_second": round(b_runtime["succeeded"] / b_runtime["wall_clock_seconds"], 4)
                         if b_runtime else None},
            "C2": {"pages_per_second": c2["pages_per_second_aggregate"] if c2 else None,
                  "peak_vram_fraction": c2["gpu"]["peak_vram_fraction_of_total"] if c2 else None,
                  "determinism_mismatches": c2["determinism_vs_serial_baseline"]["n_mismatches"] if c2 else None},
            "C4": {"pages_per_second": c4["pages_per_second_aggregate"] if c4 else None,
                  "peak_vram_fraction": c4["gpu"]["peak_vram_fraction_of_total"] if c4 else None,
                  "determinism_mismatches": c4["determinism_vs_serial_baseline"]["n_mismatches"] if c4 else None},
            "C8": "NOT ATTEMPTED -- C4 already demonstrated VRAM free dropping to "
                 "as low as 96 MiB (0.4% of total capacity) multiple times on a "
                 "77-page subset; extrapolating to C8 would predict certain OOM, "
                 "and the milestone's own instruction gates C8 on headroom "
                 "'clearly supporting' it, which C4's data clearly does not.",
        },
        "pipeline_stage_breakdown_20_page_gpu_probe": timing.get("stage_summary") if timing else None,
        "dominant_stage": timing.get("dominant_stage_by_total_time") if timing else None,
        "dominant_stage_fraction": timing.get("dominant_stage_fraction_of_total") if timing else None,
        "full_benchmark_1651_pages": {
            "device_history": (
                "GPU (config_B_fixed_auto.yaml, device=auto -> cuda) from launch. "
                "Interrupted once mid-run: Research-No.1's training job "
                "(PID 99970, openvocab_rel.train) started actively computing on "
                "the shared L4 while this run was in progress; select_device"
                "('auto') re-classified the GPU as PROTECTED at that moment (100% "
                "utilization, 2 compute processes). The GPU run was stopped "
                "immediately (clean SIGTERM on this project's own PID only, no "
                "interference with PID 99970) and restarted CPU-only for the "
                "duration of that window. Once PID 99970 exited, select_device"
                "('auto') reconfirmed CLEAR and the run was switched back to GPU, "
                "where it has remained since (a second, single-poll Research-No.1 "
                "flicker was observed and resolved itself before any manual "
                "action was needed -- see FINAL_REPORT.md Sec. 8/12)."
            ),
            "device_current": "cuda (config_B_fixed_auto.yaml, device=auto)",
            "status": ("COMPLETE" if full_runtime and full_runtime.get("succeeded", 0) >= 1651
                      else "IN PROGRESS / PARTIAL -- see FINAL_REPORT.md for exact "
                          "page count reached and why"),
            "runtime": full_runtime,
        },
        "extrapolated_full_corpus_estimate_note": (
            None if not b_runtime else
            "not directly extrapolated from the 77-page subset (mixed CPU/GPU "
            "history, live GPU-sharing interruption -- see device_history above); "
            "see full_benchmark_1651_pages.runtime for actual measured throughput "
            "once available"
        ),
    }
    Path("performance.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False))
    print(json.dumps({k: v for k, v in payload.items() if k != "pipeline_stage_breakdown_20_page_gpu_probe"},
                     indent=1, default=str)[:2000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
