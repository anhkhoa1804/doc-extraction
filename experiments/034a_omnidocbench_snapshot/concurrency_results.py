"""034a Phase 7/8/9 -- analyze one concurrency arm's results: throughput,
GPU VRAM/utilization over time, determinism (hash comparison against the
serial/C1 baseline for pages present in both).

    python experiments/034a_omnidocbench_snapshot/concurrency_results.py <label> <n_chunks> <wall_seconds>
"""
from __future__ import annotations
import hashlib, json, statistics, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent


def load_gpu_csv(path):
    if not path.exists():
        return []
    rows = []
    lines = path.read_text().splitlines()[1:]
    for line in lines:
        parts = line.split(",")
        if len(parts) != 4:
            continue
        ts, used, free, util = parts
        try:
            rows.append({"ts": float(ts), "used_mib": float(used), "free_mib": float(free), "util_pct": float(util)})
        except ValueError:
            continue
    return rows


def main():
    label = sys.argv[1]
    n_chunks = int(sys.argv[2])
    wall_seconds = float(sys.argv[3])

    total_pages, total_succeeded, total_failed = 0, 0, 0
    chunk_runtimes = []
    predictions = {}
    for c in range(n_chunks):
        out = HERE / "results" / f"conc_{label}_chunk{c}"
        rt_f = out / "runtime.json"
        if rt_f.exists():
            rt = json.loads(rt_f.read_text())
            total_pages += rt.get("total_pages", 0)
            total_succeeded += rt.get("succeeded", 0)
            total_failed += rt.get("failed", 0)
            chunk_runtimes.append(rt)
        preds_dir = out / "predictions"
        if preds_dir.exists():
            for f in preds_dir.glob("*.md"):
                predictions[f.name] = hashlib.sha256(f.read_bytes()).hexdigest()[:16]

    gpu_rows = load_gpu_csv(HERE / "results" / f"gpu_{label}.csv")
    peak_vram = max((r["used_mib"] for r in gpu_rows), default=None)
    mean_util = round(statistics.mean(r["util_pct"] for r in gpu_rows), 2) if gpu_rows else None
    max_util = max((r["util_pct"] for r in gpu_rows), default=None)

    pages_per_sec = round(total_succeeded / wall_seconds, 4) if wall_seconds > 0 else None

    # determinism check against the C1/serial baseline (config B single-process
    # run over the SAME 77-page subset), if it exists
    baseline_dir = HERE / "results" / "subset_B_fixed_auto" / "predictions"
    determinism = None
    if baseline_dir.exists():
        mismatches = []
        checked = 0
        for name, h in predictions.items():
            base_f = baseline_dir / name
            if base_f.exists():
                checked += 1
                base_h = hashlib.sha256(base_f.read_bytes()).hexdigest()[:16]
                if base_h != h:
                    mismatches.append(name)
        determinism = {"n_checked_against_serial_baseline": checked,
                       "n_mismatches": len(mismatches), "mismatches": mismatches}

    payload = {
        "label": label, "n_concurrent_processes": n_chunks,
        "wall_seconds": wall_seconds,
        "total_pages": total_pages, "total_succeeded": total_succeeded, "total_failed": total_failed,
        "pages_per_second_aggregate": pages_per_sec,
        "sec_per_page_effective": round(wall_seconds / total_succeeded, 4) if total_succeeded else None,
        "gpu": {
            "n_samples": len(gpu_rows), "peak_vram_mib": peak_vram,
            "mean_utilization_pct": mean_util, "max_utilization_pct": max_util,
            "vram_total_mib": 23034,
            "peak_vram_fraction_of_total": round(peak_vram / 23034, 3) if peak_vram else None,
        },
        "determinism_vs_serial_baseline": determinism,
        "any_chunk_failed": total_failed > 0,
    }
    Path(f"concurrency_{label}.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False))
    print(f"label={label} n={n_chunks} pages/sec={pages_per_sec} peak_vram={peak_vram}MiB "
          f"({payload['gpu']['peak_vram_fraction_of_total']}) mean_util={mean_util}% "
          f"failed={total_failed} determinism_mismatches={determinism['n_mismatches'] if determinism else 'N/A'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
