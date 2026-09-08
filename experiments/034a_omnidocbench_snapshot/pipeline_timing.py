"""034a Phase 11 -- pipeline stage breakdown from prepare.py's own
StageLogger output (logs/pipeline.jsonl per document, present when
prepare.py is run WITHOUT deleting _doc_extraction_runs -- pass
--keep-runs, or read mid-run before cleanup happens at the very end).

    python experiments/034a_omnidocbench_snapshot/pipeline_timing.py <results_dir>
"""
from __future__ import annotations
import json, statistics, sys
from collections import defaultdict
from pathlib import Path


def main():
    results_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("results/subset_B_fixed_auto")
    runs_dir = results_dir / "_doc_extraction_runs"
    if not runs_dir.exists():
        print(f"no _doc_extraction_runs under {results_dir} -- rerun prepare.py directly "
              f"with --keep-runs to get per-stage timing")
        return 1

    stage_times = defaultdict(list)
    per_doc = []
    for doc_dir in sorted(runs_dir.iterdir()):
        log_f = doc_dir / "logs" / "pipeline.jsonl"
        if not log_f.exists():
            continue
        stages = {}
        for line in log_f.read_text().splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            stage = rec.get("stage")
            runtime = rec.get("runtime_seconds")
            if stage is not None and runtime is not None:
                stage_times[stage].append(runtime)
                stages[stage] = runtime
        per_doc.append({"document": doc_dir.name, "stages": stages,
                        "total": sum(stages.values())})

    def pctl(vals, p):
        if not vals:
            return None
        vals = sorted(vals)
        k = (len(vals) - 1) * p
        f, c = int(k), min(int(k) + 1, len(vals) - 1)
        return round(vals[f] + (vals[c] - vals[f]) * (k - f), 4)

    stage_summary = {}
    for stage, vals in stage_times.items():
        stage_summary[stage] = {
            "n": len(vals), "mean": round(statistics.mean(vals), 4),
            "median": round(statistics.median(vals), 4),
            "p90": pctl(vals, 0.90), "p95": pctl(vals, 0.95), "p99": pctl(vals, 0.99),
            "min": round(min(vals), 4), "max": round(max(vals), 4),
            "total": round(sum(vals), 4),
        }

    total_all_stages = sum(s["total"] for s in stage_summary.values())
    dominant = max(stage_summary.items(), key=lambda kv: kv[1]["total"])[0] if stage_summary else None

    payload = {
        "source": str(runs_dir),
        "n_documents": len(per_doc),
        "stage_summary": stage_summary,
        "dominant_stage_by_total_time": dominant,
        "dominant_stage_fraction_of_total": (
            round(stage_summary[dominant]["total"] / total_all_stages, 4) if dominant else None),
        "per_document": per_doc,
    }
    out_name = f"pipeline_timing_{results_dir.name}.json"
    Path(out_name).write_text(json.dumps(payload, indent=1, ensure_ascii=False))
    print(f"documents: {len(per_doc)}")
    for stage, s in sorted(stage_summary.items(), key=lambda kv: -kv[1]["total"]):
        print(f"  {stage:<15} mean={s['mean']:<8} p95={s['p95']:<8} total={s['total']}")
    print(f"dominant stage: {dominant}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
