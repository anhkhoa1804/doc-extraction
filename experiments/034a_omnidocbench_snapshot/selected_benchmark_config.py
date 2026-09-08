"""034a Phase 12 -- select the configuration for the final full benchmark,
based on measured correctness, determinism, throughput, peak VRAM,
stability, and failure rate. Fastest STABLE configuration, not fastest
unsafe configuration.

    python experiments/034a_omnidocbench_snapshot/selected_benchmark_config.py
"""
from __future__ import annotations
import json
from pathlib import Path
HERE = Path(__file__).resolve().parent


def main():
    c2 = json.loads((HERE / "concurrency_c2.json").read_text())
    c4 = json.loads((HERE / "concurrency_c4.json").read_text())
    b = json.loads((HERE / "results/subset_B_fixed_auto/runtime.json").read_text())
    correctness = json.loads((HERE / "subset_correctness.json").read_text())

    c1_pages_per_sec = round(b["succeeded"] / b["wall_clock_seconds"], 4)

    arms = {
        "C1_serial": {
            "n_processes": 1, "pages_per_second": c1_pages_per_sec,
            "peak_vram_fraction": "never observed above ~0.92 across ANY "
                                  "run this milestone (subset, smoke, or the "
                                  "earlier interrupted full run) -- the only "
                                  "arm with a comfortable, consistently "
                                  "observed safety margin",
            "failures": 0, "determinism": "baseline (all other arms compared against this)",
        },
        "C2": {
            "n_processes": 2, "pages_per_second": c2["pages_per_second_aggregate"],
            "speedup_vs_c1": round(c2["pages_per_second_aggregate"] / c1_pages_per_sec, 3),
            "peak_vram_fraction": c2["gpu"]["peak_vram_fraction_of_total"],
            "peak_vram_free_mib_observed_minimum": "~218-292 MiB (real-time monitoring, this milestone)",
            "failures": 0, "determinism_mismatches": c2["determinism_vs_serial_baseline"]["n_mismatches"],
        },
        "C4": {
            "n_processes": 4, "pages_per_second": c4["pages_per_second_aggregate"],
            "speedup_vs_c1": round(c4["pages_per_second_aggregate"] / c1_pages_per_sec, 3),
            "peak_vram_fraction": c4["gpu"]["peak_vram_fraction_of_total"],
            "peak_vram_free_mib_observed_minimum": "~96 MiB (real-time monitoring, this milestone) "
                                                   "-- touched multiple times, not a single transient dip",
            "failures": 0, "determinism_mismatches": c4["determinism_vs_serial_baseline"]["n_mismatches"],
        },
    }

    decision = {
        "selected_for_final_full_benchmark": "C1_serial",
        "device": "auto (resolves to cuda given the CLEAR GPU state confirmed at every "
                 "check this milestone)",
        "config_file": "config_B_fixed_auto.yaml (configs/cpu.yaml + device: auto, "
                       "now safe end-to-end after the process_file() fix)",
        "concurrency": 1,
        "batch_size": "N/A -- no batching capability exists in the current backend "
                     "architecture (batching_results.json)",
        "reasoning": (
            "C2 and C4 are REAL, measured, zero-failure, zero-determinism-mismatch "
            "throughput improvements (1.70x and 2.58x respectively) on THIS 77-page "
            "subset -- not rejected as invalid. But both were observed touching "
            "critically thin VRAM margins (as low as 218-292 MiB for C2, 96 MiB for "
            "C4, out of 23034 MiB total -- under 1.3% and 0.4% free respectively) "
            "MULTIPLE TIMES during a single 77-page run. The full OmniDocBench "
            "dataset is 1651 pages (21.4x larger) and was explicitly NOT filtered "
            "for maximum image size when this subset was built (build_subset.py "
            "stratified for CONTENT diversity, not size) -- so the full corpus may "
            "well contain individual pages larger than anything tested in the "
            "concurrency experiment. Per this milestone's own explicit design "
            "principle ('the selected config should be the fastest STABLE "
            "configuration, not the fastest unsafe configuration' and 'correctness "
            "and reproducibility take priority over maximum throughput'), a "
            "configuration that has been observed within single-digit percent of "
            "total VRAM capacity is not treated as safely stable at 21x the scale "
            "it was validated on. C1 (serial) is the ONLY arm with a consistently "
            "comfortable margin across every run this milestone performed "
            "(including the original interrupted full-run attempt, which reached "
            "up to ~21 GB but never approached the true ceiling before being "
            "stopped for unrelated methodology reasons, not instability)."
        ),
        "not_a_rejection_of_concurrency": (
            "C2/C4's measured speedups are reported as real findings "
            "(concurrency_c2.json, concurrency_c4.json) and represent a "
            "genuine, quantified opportunity for a FUTURE milestone that adds "
            "a memory-aware safety check (e.g. skip/retry a chunk if free VRAM "
            "drops below a hard floor, mirroring select_device()'s own "
            "safety_margin_mib concept) before being used for a production-"
            "scale run -- not implemented here, out of scope for a benchmark "
            "snapshot per this milestone's own 'do not implement a large "
            "batching/concurrency architecture' instruction."
        ),
    }

    payload = {"arms_compared": arms, "decision": decision,
              "exact_command": (
                  "/home/leanhkhoa150204/.venvs/doc-extraction-gpu312/bin/python3 "
                  "experiments/005_omnidocbench/run.py "
                  "--dataset experiments/034a_omnidocbench_snapshot/dataset/full "
                  "--backend baseline "
                  "--output experiments/034a_omnidocbench_snapshot/results/full_baseline "
                  "--config experiments/034a_omnidocbench_snapshot/config_B_fixed_auto.yaml "
                  "--omnidoc-python /home/leanhkhoa150204/.venvs/omnidoc-evaluator/bin/python3"
              )}
    Path("selected_benchmark_config.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False))
    print(json.dumps(arms, indent=1))
    print("SELECTED:", decision["selected_for_final_full_benchmark"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
