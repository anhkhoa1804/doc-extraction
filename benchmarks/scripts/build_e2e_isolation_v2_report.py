"""Build compact, source-linked reports for the isolated PaddleOCR-VL run."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / ".benchmarks/runs/omnidocbench"
E2E_ID = "e2e-paddleocr-vl16-isolation-full180-v2-20261002T115500Z"
CLASSIC_ID = "representative-v2-full-20261002T080500Z"
OUT = ROOT / "benchmarks/reports/omnidocbench"
METRIC_FILES = {
    "text_edit_distance": "text_block_per_page_edit.json",
    "formula_edit_distance": "display_formula_per_page_edit.json",
    "table_edit_distance": "table_per_page_edit.json",
    "reading_order_edit_distance": "reading_order_per_page_edit.json",
}


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def paired_map(folder: Path) -> dict[str, dict[str, float]]:
    result = {}
    for key, suffix in METRIC_FILES.items():
        matches = list(folder.glob(f"*{suffix}"))
        if len(matches) != 1:
            raise ValueError(f"expected one {suffix} in {folder}, found {len(matches)}")
        result[key] = load(matches[0])
    return result


def metric_record(metrics: dict[str, Any], summary: dict[str, Any], key: str, direction: str) -> dict[str, Any]:
    group, field = {
        "text_edit_distance": ("text_block", "Edit_dist"),
        "formula_edit_distance": ("display_formula", "Edit_dist"),
        "table_edit_distance": ("table", "Edit_dist"),
        "table_teds": ("table", "TEDS"),
        "table_structure_teds": ("table", "TEDS_structure_only"),
        "reading_order_edit_distance": ("reading_order", "Edit_dist"),
    }[key]
    return {
        "value": metrics[group]["page"][field]["ALL"],
        "n": summary["page_denominators"][group][field]["ALL"],
        "aggregation": "pinned OmniDocBench official ALL page aggregation",
        "direction": direction,
        "status": "MEASURED_CONDITIONAL" if key else "MEASURED",
    }


def distribution(values: list[float]) -> dict[str, Any]:
    values = sorted(values)
    if not values:
        return {"n": 0}
    return {
        "n": len(values),
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "min": values[0],
        "max": values[-1],
        "p95_nearest_rank": values[math.ceil(len(values) * 0.95) - 1],
    }


def write(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default=E2E_ID)
    parser.add_argument("--classic-run-id", default=CLASSIC_ID)
    args = parser.parse_args()
    e2e_dir, classic_dir = RUNS / args.run_id, RUNS / args.classic_run_id
    conditional = e2e_dir / "conditional-completed-178"
    runtime = load(e2e_dir / "runtime.json")
    classic_runtime = load(classic_dir / "runtime.json")
    metadata = load(e2e_dir / "run_metadata.json")
    source = load(e2e_dir / "source_attestation.json")
    gt_rows = load(e2e_dir / "ground_truth_subset.json")
    gt = {row["page_info"]["image_path"]: row for row in gt_rows}
    e2e_metrics, classic_metrics = load(conditional / "eval-e2e/metrics.json"), load(conditional / "eval-classic/metrics.json")
    e2e_summary, classic_summary = load(conditional / "eval-e2e/run_summary.json"), load(conditional / "eval-classic/run_summary.json")
    e_maps, c_maps = paired_map(conditional / "eval-e2e"), paired_map(conditional / "eval-classic")
    e_teds = load(next((conditional / "eval-e2e").glob("*table_per_table_TEDS.json")))
    c_teds = load(next((conditional / "eval-classic").glob("*table_per_table_TEDS.json")))

    per_page = []
    for item in runtime["per_page"]:
        row = gt[item["image_name"]]
        attrs = row["page_info"].get("page_attribute", {})
        prediction_path = e2e_dir / metadata["prediction_directory"] / item["prediction_id"]
        prediction_hash = hashlib.sha256(prediction_path.read_bytes()).hexdigest() if prediction_path.is_file() else None
        per_page.append({
            "page_id": item["page_id"], "sample_id": item["sample_id"],
            "dataset_index": item["dataset_index"], "page_no": item["page_no"],
            "image_name": item["image_name"], "input_sha256": item["input_sha256"],
            "source_category": attrs.get("data_source"), "language": attrs.get("language"),
            "layout": attrs.get("layout"), "special_issue": attrs.get("special_issue", []),
            "subset": attrs.get("subset"), "route": item["route"], "status": item["status"],
            "warnings_count": item["warnings_count"], "warnings": item["warnings"],
            "errors": item["errors"], "runtime_seconds": item["runtime_seconds"],
            "failure_kind": "runtime_timeout" if item["status"] == "failed" and any("max_runtime_seconds" in e for e in item["errors"]) else None,
            "prediction_id": item["prediction_id"],
            "prediction_sha256": prediction_hash,
            "metric_values": {key: values.get(item["image_name"]) for key, values in e_maps.items()},
        })

    metrics = {}
    for key, direction in (("text_edit_distance", "lower"), ("formula_edit_distance", "lower"),
                           ("table_edit_distance", "lower"), ("table_teds", "higher"),
                           ("table_structure_teds", "higher"), ("reading_order_edit_distance", "lower")):
        metrics[key] = {
            "classic": metric_record(classic_metrics, classic_summary, key, direction),
            "e2e": metric_record(e2e_metrics, e2e_summary, key, direction),
        }

    paired = {}
    for key, e_values in e_maps.items():
        c_values = c_maps[key]
        ids = sorted(e_values.keys() & c_values.keys())
        deltas = [float(e_values[i]) - float(c_values[i]) for i in ids]
        paired[key] = {
            "n_paired": len(ids), "direction": "lower is better",
            "classic_mean": statistics.fmean(float(c_values[i]) for i in ids),
            "e2e_mean": statistics.fmean(float(e_values[i]) for i in ids),
            "delta_e2e_minus_classic": distribution(deltas),
            "e2e_better_count": sum(d < 0 for d in deltas),
            "classic_better_count": sum(d > 0 for d in deltas),
            "tie_count": sum(d == 0 for d in deltas),
            "per_page": {i: {"classic": float(c_values[i]), "e2e": float(e_values[i]),
                             "delta": float(e_values[i]) - float(c_values[i])} for i in ids},
        }

    paired_tables = {}
    table_ids = sorted(e_teds.keys() & c_teds.keys())
    for field, higher in (("TEDS", True), ("TEDS_structure_only", True)):
        deltas = [float(e_teds[i][field]) - float(c_teds[i][field]) for i in table_ids]
        paired_tables[field] = {
            "n_paired_instances": len(table_ids), "direction": "higher is better",
            "classic_mean": statistics.fmean(float(c_teds[i][field]) for i in table_ids),
            "e2e_mean": statistics.fmean(float(e_teds[i][field]) for i in table_ids),
            "delta_e2e_minus_classic": distribution(deltas),
            "e2e_better_count": sum(d > 0 for d in deltas),
            "classic_better_count": sum(d < 0 for d in deltas),
            "tie_count": sum(d == 0 for d in deltas),
        }

    # Group by dataset-provided source category; only expose groups with N >= 5.
    source_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for page in per_page:
        if page["status"] == "success":
            source_groups[page["source_category"] or "unknown"].append(page)
    stratified = []
    for category, pages in sorted(source_groups.items()):
        text = [float(e_maps["text_edit_distance"][p["image_name"]]) for p in pages
                if p["image_name"] in e_maps["text_edit_distance"]]
        reading = [float(e_maps["reading_order_edit_distance"][p["image_name"]]) for p in pages
                   if p["image_name"] in e_maps["reading_order_edit_distance"]]
        if len(pages) >= 5:
            stratified.append({"source_category": category, "n_pages": len(pages),
                               "text_n": len(text), "text_edit_distance_mean": statistics.fmean(text) if text else None,
                               "reading_order_n": len(reading),
                               "reading_order_edit_distance_mean": statistics.fmean(reading) if reading else None})

    failed = [p for p in per_page if p["status"] != "success"]
    subset_hash = metadata["sample_manifest_sha256"]
    attestation = {"git_commit": source["git_commit"], "working_tree_clean": source["working_tree_clean"],
                   "source_snapshot_sha256": source["source_snapshot_sha256"],
                   "lockfile_sha256": source["root_uv_lock_sha256"], "config_sha256": metadata["config_sha256"],
                   "manifest_sha256": subset_hash, "evaluator_revision": metadata["upstream_commit"],
                   "model_versions": metadata["model_versions"], "python": metadata["python"],
                   "platform": metadata["platform"], "device": "NVIDIA L4; 23,034 MiB; CUDA 12.6"}

    full = {
        "report_schema": "internal-e2e-full-v2", "run_id": args.run_id,
        "dataset": "OmniDocBench 1.6 local snapshot", "dataset_pages": 1651,
        "subset": "representative-v2", "population_count": 180, "manifest_sha256": subset_hash,
        "ground_truth_sha256": metadata["ground_truth_sha256"],
        "quality_status": "NO FULL PAIRED QUALITY BASELINE",
        "operational": {"success": runtime["succeeded"], "timeouts": runtime["failed"],
                         "other_failures": 0, "warnings": runtime["warning_count"],
                         "success_rate": runtime["succeeded"] / runtime["total_pages"],
                         "timeout_rate": runtime["failed"] / runtime["total_pages"],
                         "wall_clock_seconds": runtime["wall_clock_seconds"],
                         "runtime_seconds": {k: runtime[src] for k, src in (("mean", "mean_seconds_per_page"),
                             ("median", "median_seconds_per_page"), ("p95", "p95_seconds_per_page"),
                             ("min", "min_seconds_per_page"), ("max", "max_seconds_per_page"))},
                         "max_runtime_seconds": 300, "gpu_peak_mib_observed": 20580,
                         "gpu_memory_after_run_mib": 0},
        "failures": failed, "attestation": attestation,
        "post_run_source_changes": [
            "Corrected timeout diagnostic to report whole guarded-operation elapsed time rather than worker-request elapsed time.",
            "Applied Ruff import sorting.",
        ],
        "raw_run_relative_path": f".benchmarks/runs/omnidocbench/{args.run_id}",
        "metrics_conditional_completed_pages": metrics, "stratified_source_category": stratified,
        "per_page": per_page,
    }
    write(OUT / "e2e-full-v2.json", full)

    isolation = {
        "report_schema": "internal-e2e-isolation-v2", "run_id": args.run_id,
        "architecture": "persistent isolated POSIX worker process group, parent-supervised bounded framed JSON IPC",
        "worker_lifecycle_states": ["starting", "ready", "running", "completed", "failed", "timed_out", "terminated"],
        "timeout_semantics": "300s existing page operation limit covers cold startup/model load, preprocessing, inference, postprocessing, IPC and parent validation; terminate group at deadline; page wall time also includes teardown.",
        "five_page_smoke": {"run_id": "e2e-paddleocr-vl16-isolation-smoke-v2-20261002T113350Z", "success": 5,
                            "failed": 0, "warnings": 0, "wall_clock_seconds": 270.481, "quality_diagnostic_only": True},
        "twenty_page_preflight": {"run_id": "e2e-paddleocr-vl16-isolation-preflight20-v2-20261002T113950Z",
                                  "success": 20, "failed": 0, "warnings": 0, "wall_clock_seconds": 841.741,
                                  "median_seconds_per_page": 29.2274, "p95_seconds_per_page": 81.9641,
                                  "exact_gt_prediction_alignment": True},
        "focused_test_counts": {"worker_tests": "5 passed", "worker_and_backend_tests": "14 passed"},
        "timeout_cleanup": {"worker_group_gone": True, "descendant_pid_gone_tested": True,
                            "scratch_cleaned_tested": True, "restarted_for_following_page": True,
                            "post_run_worker_processes": 0, "post_run_gpu_memory_mib": 0},
        "limits": ["not an OS sandbox", "aggregate scratch limit is sampled, not kernel quota",
                   "two pages exceeded the hard operation deadline"],
        "attestation": attestation,
    }
    write(OUT / "e2e-isolation-v2.json", isolation)

    comparison = {
        "report_schema": "internal-classic-vs-e2e-v2",
        "full_population": {"status": "NOT AVAILABLE: 2/180 E2E predictions missing",
                            "classic_run_id": args.classic_run_id, "e2e_run_id": args.run_id,
                            "classic_full_metrics": load(classic_dir / "metrics.json"), "e2e_full_metrics": None},
        "conditional_population": {"label": "CONDITIONAL QUALITY — COMPLETED E2E PAGES ONLY", "n": 178,
                                   "outcome_conditioned": True,
                                   "ground_truth_subset_sha256": hashlib.sha256((conditional / "ground_truth.json").read_bytes()).hexdigest(),
                                   "sample_ids": [p["sample_id"] for p in per_page if p["status"] == "success"],
                                   "exact_alignment": {"ground_truth": 178, "classic": 178, "e2e": 178}},
        "metrics": metrics, "paired_page_deltas": paired, "paired_table_instance_deltas": paired_tables,
        "runtime": {"classic_full": {k: classic_runtime[k] for k in ("total_pages", "wall_clock_seconds",
                          "mean_seconds_per_page", "median_seconds_per_page", "p95_seconds_per_page")},
                    "e2e_full": full["operational"]},
        "comparability": "The conditional runs use identical 178-page GT and the same pinned evaluator. Successful-page membership depends on E2E completion; this is not an unbiased full-manifest estimate. The full Classic 180-page run is kept separate.",
    }
    write(OUT / "classic-vs-e2e-v2.json", comparison)

    table = "| Metric | Classic | E2E | Delta | N | Status |\n|---|---:|---:|---:|---:|---|\n"
    for label, key in (("Text ED", "text_edit_distance"), ("Table ED", "table_edit_distance"),
                       ("Table TEDS", "table_teds"), ("Table structure TEDS", "table_structure_teds"),
                       ("Reading-order ED", "reading_order_edit_distance"), ("Formula ED", "formula_edit_distance")):
        a, b = metrics[key]["classic"], metrics[key]["e2e"]
        table += f"| {label} | {a['value']:.6f} | {b['value']:.6f} | {b['value']-a['value']:+.6f} | {b['n']} | CONDITIONAL |\n"
    fail_md = "\n".join(f"- `{p['image_name']}` page {p['page_no']}: runtime limit; {p['runtime_seconds']:.3f}s page wall; no prediction accepted." for p in failed)
    source_md = "\n".join(f"| {p['source_category']} | {p['n_pages']} | {p['text_n']} | {p['text_edit_distance_mean']:.4f} | {p['reading_order_n']} | {p['reading_order_edit_distance_mean']:.4f} |" for p in stratified)
    full_md = f'''# E2E Inference Isolation and Paired Baseline

| Dimension | Classic | E2E | Status |
|---|---:|---:|---|
| Success rate | 180/180 (100%) | 178/180 (98.889%) | two hard timeouts |
| Timeout rate | 0% | 1.111% | measured |
| Text ED | 0.573988 (N=168) | 0.044909 (N=166 conditional) | not same full denominator |
| Table TEDS | 0.413877 (N=50) | 0.842940 (N=50 conditional) | conditional |
| Table structure TEDS | 0.673171 (N=50) | 0.872107 (N=50 conditional) | conditional |
| Reading-order ED | 0.584992 (N=178) | 0.165855 (N=176 conditional) | not same full denominator |
| Formula ED | 0.985389 (N=35) | 0.079500 (N=35 conditional) | conditional |
| Runtime/page | mean 6.609 s | mean 41.977 s | E2E ~6.35x slower mean |

## 1. Repository state
Inference HEAD `{source['git_commit']}`; worktree dirty and recorded in `e2e-full-v2.json`. Source snapshot SHA-256 `{source['source_snapshot_sha256']}`. After inference, the timeout diagnostic was corrected to report elapsed time for the whole guarded operation (the run artifact had displayed worker-request elapsed against the full configured limit), and Ruff import sorting was applied. Neither change affects inference, predictions, mapping, or the 300-second policy.

## 2. Inference isolation architecture
Parent supervises one persistent worker in a private POSIX process group using bounded framed JSON IPC. Worker cannot publish predictions or mutate run metadata. Timeout kills only the owned group and the next page restarts a clean worker.

## 3. Hard timeout semantics
Existing `max_runtime_seconds=300` covers cold model startup, preprocessing, inference, postprocessing, IPC and parent validation. The parent does not rely on cooperative model cancellation. Page wall time includes teardown after the operation deadline.

## 4. Worker lifecycle
Startup/ready/completed/failure/timeout and restart paths are covered by deterministic fixture tests. A timed-out worker is not reused.

## 5. Cleanup verification
Tests verify descendant PID disappearance and scratch cleanup. After the full run no worker/fixture process remained and L4 memory returned to 0 MiB.

## 6. Reproducibility attestation
Run `{args.run_id}`; manifest SHA `{subset_hash}`; config SHA `{metadata['config_sha256']}`; evaluator `{metadata['upstream_commit']}`. Model hashes and package versions are recorded in JSON. Device L4, CUDA 12.6; model `PaddlePaddle/PaddleOCR-VL-1.6`.

## 7. Five-page smoke
5/5 completed, zero warnings, 270.481 s; diagnostic only, not a quality comparison.

## 8. Timeout stress test
5 worker-specific tests and 14 combined worker/backend tests pass. Forced timeout, group cleanup, child disappearance, scratch cleanup, restart, output cap and failure behavior exercised.

## 9. 20-page preflight
20/20 completed, zero warnings, 841.741 s; exact prediction/GT alignment and evaluator execution passed.

## 10. Full 180-page E2E run
178 success; two timeouts. The frozen set is incomplete, so **NO FULL PAIRED QUALITY BASELINE**.

## 11. Operational coverage
Success 98.889%; timeout 1.111%; other failures 0; warnings 0; policy rejections 0.

## 12. Official quality metrics
Conditional only; see table below. No missing page was replaced with empty output; exact 178 prediction/GT alignment passed.

{table}
Table values are official page-level `ALL` aggregation across 50 table-bearing pages. Separately, 64 matched table instances yield TEDS Classic {paired_tables['TEDS']['classic_mean']:.6f}, E2E {paired_tables['TEDS']['e2e_mean']:.6f}; structure-only {paired_tables['TEDS_structure_only']['classic_mean']:.6f} vs {paired_tables['TEDS_structure_only']['e2e_mean']:.6f}. Formula CDM was not run.

## 13. Classic vs E2E
Only conditional 178-page results share the exact filtered ground truth, outputs, and pinned evaluator. Do not subtract conditional E2E from the full 180-page Classic score.

## 14. Paired page-level analysis
Text ED lower for {paired['text_edit_distance']['e2e_better_count']}/{paired['text_edit_distance']['n_paired']} pages; formula lower for {paired['formula_edit_distance']['e2e_better_count']}/{paired['formula_edit_distance']['n_paired']}; reading-order lower for {paired['reading_order_edit_distance']['e2e_better_count']}/{paired['reading_order_edit_distance']['n_paired']}; table edit lower for {paired['table_edit_distance']['e2e_better_count']}/{paired['table_edit_distance']['n_paired']}. All per-page paired values are in JSON. One large text/reading-order regression remains unexplained.

## 15. Failure-mode comparison
OBSERVED: two timeouts; one completed yanbaoppt page has E2E text/reading-order ED 1.0 despite nonempty Markdown with some overlapping prose and near-zero Classic error. HYPOTHESIS: reading-order or sequence alignment/serializer interaction; not confirmed. Timed-out page quality is unknown.

## 16. Runtime/resource comparison
E2E wall {runtime['wall_clock_seconds']:.3f}s (~2h 5m 57s); mean {runtime['mean_seconds_per_page']:.3f}s, median {runtime['median_seconds_per_page']:.3f}s, p95 {runtime['p95_seconds_per_page']:.3f}s, range {runtime['min_seconds_per_page']:.3f}–{runtime['max_seconds_per_page']:.3f}s. Classic wall {classic_runtime['wall_clock_seconds']:.3f}s. E2E peak GPU use observed ~20,580/23,034 MiB; 0 MiB after exit.

## 17. Production viability
**PROMISING BUT NEEDS OPTIMIZATION.** Conditional quality is materially better on most measured tasks, but 2 timeouts and ~6.35x mean runtime remain; this is not production approval.

## 18. Fine-tuning decision
**FINE-TUNING NOT YET JUSTIFIED.** Complete paired coverage has not been achieved; first investigate the timeout pages and the large paired regression.

## 19. Tests
Focused worker/backend/attestation tests: 16 passed before the diagnostic correction; the new elapsed-time helper has its own deterministic clock test. Changed-file Ruff passes. Full suite/build results are recorded in final validation.

## 20. Remaining risks
Two unscored timeout pages; process isolation is not an OS sandbox; scratch size is polled rather than kernel quota; one substantial page regression is uncharacterized. This measures one pretrained model revision and adapter, not broad generalization.

### Timed-out pages
{fail_md}

### Source category analysis (successful pages, groups N >= 5)
| Source | N pages | Text N | Text ED | Reading N | Reading-order ED |
|---|---:|---:|---:|---:|---:|
{source_md}
'''
    (OUT / "e2e-full-v2.md").write_text(full_md, encoding="utf-8")
    (OUT / "e2e-isolation-v2.md").write_text(
        f'''# E2E Inference Isolation v2

Persistent supervised worker uses a private POSIX process group and bounded framed JSON IPC. On timeout the parent kills the owned process group, waits, verifies termination, cleans private scratch and rejects any result; next page gets a fresh worker. The worker is process-isolated, not an OS sandbox. Scratch aggregate usage is sampled rather than kernel quota-enforced.

The existing 300-second operation limit includes cold startup/model initialization, preprocessing, inference, postprocessing, IPC and parent validation. Wall time can include bounded teardown after the deadline. No policy override was introduced.

- Five-page smoke: 5/5 success, zero warnings, 270.481 s; diagnostic only.
- Twenty-page preflight: 20/20 success, zero warnings, exact GT alignment, 841.741 s; median 29.227 s/page, p95 81.964 s/page.
- Timeout fixture: 5 worker-specific tests pass; combined backend/worker suite 14 pass. Child process disappearance, process-group cleanup, scratch cleanup, timeout state, and restart tested.
- 180-page run: 178 success, two runtime timeouts; no worker remained afterward; L4 returned to 0 MiB.

Run `{args.run_id}`; source snapshot `{source['source_snapshot_sha256']}`; source HEAD `{source['git_commit']}` (dirty tree recorded); subset `{subset_hash}`; model/layout weight hashes and package versions are in `e2e-isolation-v2.json`.
''', encoding="utf-8")
    comparison_rows = "".join(
        f"| {label} | {metrics[key]['classic']['value']:.6f} | {metrics[key]['e2e']['value']:.6f} | "
        f"{metrics[key]['e2e']['value']-metrics[key]['classic']['value']:+.6f} | "
        f"{metrics[key]['e2e']['n']} | CONDITIONAL |\n"
        for label, key in (("Text ED", "text_edit_distance"), ("Table ED", "table_edit_distance"),
                           ("Table TEDS", "table_teds"), ("Table structure TEDS", "table_structure_teds"),
                           ("Reading-order ED", "reading_order_edit_distance"), ("Formula ED", "formula_edit_distance"))
    )
    (OUT / "classic-vs-e2e-v2.md").write_text(
        f'''# Conditional Classic vs E2E v2

**Full 180-page paired quality is unavailable**: two E2E predictions are missing. The values below condition on E2E completing, so the population is outcome-conditioned and not an unbiased estimate of the frozen manifest.

| Metric | Classic | E2E | Delta (E2E − Classic) | N | Status |
|---|---:|---:|---:|---:|---|
{comparison_rows}
Per-page edit-distance deltas use the exact same success-conditioned predictions and GT; negative favors E2E. Text: {paired['text_edit_distance']['e2e_better_count']} pages improve, {paired['text_edit_distance']['classic_better_count']} regress, {paired['text_edit_distance']['tie_count']} tie (N={paired['text_edit_distance']['n_paired']}). Formula: {paired['formula_edit_distance']['e2e_better_count']} improve of {paired['formula_edit_distance']['n_paired']}. Reading order: {paired['reading_order_edit_distance']['e2e_better_count']} improve of {paired['reading_order_edit_distance']['n_paired']}. Table edit: {paired['table_edit_distance']['e2e_better_count']} improve of {paired['table_edit_distance']['n_paired']}.

Across 64 exactly paired table instances, mean TEDS was {paired_tables['TEDS']['classic_mean']:.6f} Classic vs {paired_tables['TEDS']['e2e_mean']:.6f} E2E; structure-only was {paired_tables['TEDS_structure_only']['classic_mean']:.6f} vs {paired_tables['TEDS_structure_only']['e2e_mean']:.6f}. No composite score or significance test is reported.

Frozen manifest SHA `{subset_hash}`, evaluator `{metadata['upstream_commit']}`. Full Classic 180-page metrics remain separate; no cross-population score delta is presented.
''', encoding="utf-8")
    print(f"wrote reports; per-page={len(per_page)} paired={ {k:v['n_paired'] for k,v in paired.items()} } table_instances={len(table_ids)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
