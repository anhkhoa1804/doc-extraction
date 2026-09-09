"""035 Phase 0 -- freeze/baseline. Verifies the actual on-disk/git state
before any Mechanism-D matching work begins, and records source hashes for
the exact code paths this milestone treats as ground truth about the
production system (the table gate, the two label->ElementType maps, the
evaluator adapter). Read-only; writes nothing outside this experiment dir.

    python experiments/035_mechanism_d_gating/phase0_baseline.py
"""
from __future__ import annotations
import hashlib, json, subprocess, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def sh(*args: str) -> str:
    return subprocess.run(args, cwd=REPO, capture_output=True, text=True, check=True).stdout.strip()


def git_blob_hash(path: str) -> str:
    return sh("git", "hash-object", path)


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    head = sh("git", "rev-parse", "HEAD")
    branch = sh("git", "branch", "--show-current")
    origin_head = sh("git", "rev-parse", "origin/fix/table-text-ownership")
    status = sh("git", "status", "--short")

    frozen_dirs = [
        "experiments/029_deep_forensic_replay", "experiments/030_resolve_h1_h2",
        "experiments/031_table_label_gating", "experiments/032_role_ambiguity",
        "experiments/033_table_shape_integrity", "experiments/034a_omnidocbench_snapshot",
    ]
    last_touch = {d: sh("git", "log", "-1", "--format=%H", "--", d) for d in frozen_dirs}

    source_hashes = {
        "table_gate (pipelines/base.py:747, r.label.lower() == 'table')":
            git_blob_hash("src/doc_extraction/pipelines/base.py"),
        "table_backend.py (secondary gate at line 85)":
            git_blob_hash("src/doc_extraction/backends/table_backend.py"),
        "docling_backend.py (_LABEL_MAP, raw Docling label source)":
            git_blob_hash("src/doc_extraction/backends/docling_backend.py"),
        "evaluation/omnidocbench.py (dataset loader + evaluator adapter)":
            git_blob_hash("src/doc_extraction/evaluation/omnidocbench.py"),
    }

    frozen_artifacts = {}
    for rel in (
        "experiments/034a_omnidocbench_snapshot/results/full_baseline/metrics.json",
        "experiments/034a_omnidocbench_snapshot/results/full_baseline/run_metadata.json",
        "experiments/034a_omnidocbench_snapshot/results/full_baseline/runtime.json",
        "experiments/034a_omnidocbench_snapshot/official_metrics.json",
        "experiments/034a_omnidocbench_snapshot/dataset_manifest.json",
        "experiments/034a_omnidocbench_snapshot/selected_benchmark_config.json",
        "experiments/034a_omnidocbench_snapshot/dataset/full/OmniDocBench.json",
    ):
        frozen_artifacts[rel] = file_sha256(REPO / rel)

    baseline = {
        "phase": "0 -- freeze/baseline",
        "git": {
            "head": head,
            "branch": branch,
            "origin_head": origin_head,
            "local_eq_origin": head == origin_head,
            "status_short": status,
            "expected_untracked": "uv.lock only",
            "status_matches_expected": status.strip() in ("?? uv.lock", ""),
        },
        "frozen_milestones_last_touched_by": last_touch,
        "frozen_milestones_integrity": {
            "all_last_touched_by_034a_close_commit": all(
                v == "55d71cb2a9526eb4fc9eae177d09d958e8cee8c7" for v in last_touch.values()
            ),
        },
        "source_hashes_git_blob_sha1": source_hashes,
        "frozen_artifact_sha256": frozen_artifacts,
        "gpu_state_at_start": "PROTECTED -- Research-No.1's own process "
            "(tools/readout_v2_evaluate.py) observed at 100% utilization, "
            "4270 MiB used, PID 19811, at milestone start (2026-09-09 ~01:56). "
            "This milestone defaults to CPU/read-only analysis for exactly "
            "this reason -- verified, not assumed.",
        "full_run_summary": "1651/1651 pages succeeded, 0 failed (runtime.json); "
            "official evaluator completed (metrics.json); table.metric_debug."
            "TEDS.sample_count=665, error_case_count=94 (85.9% coverage).",
        "test_suite": "345 passed, 10 skipped -- reconfirm in Phase 23, not "
            "re-run here (Phase 0 is read-only/no source touched yet).",
        "known_gap_this_milestone_addresses": "results/full_baseline has no "
            "_doc_extraction_runs/ (no --keep-runs was used for the full "
            "run) -- per-page internal layout_result.regions (label, bbox, "
            "confidence) were never persisted for any of the 1651 pages. "
            "Phase 3 onward therefore requires a NEW, targeted, --keep-runs "
            "re-extraction limited to the population needed (see "
            "gt_table_dataset_manifest.json) -- not a re-run of the full "
            "1651-page corpus, and not GPU (see gpu_state_at_start).",
    }
    Path(HERE / "baseline.json").write_text(json.dumps(baseline, indent=1, ensure_ascii=False))
    print(json.dumps({k: v for k, v in baseline.items() if k not in ("frozen_artifact_sha256", "source_hashes_git_blob_sha1")}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
