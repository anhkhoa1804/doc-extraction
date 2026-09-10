"""035 Phase 13 support -- build a stratified sample of pages WITHOUT a GT
table, for the false-positive side (internal regions labelled 'table' that
overlap no GT table at all). Exhaustively processing all 1193 non-table
pages is not justified given this milestone's CPU-only constraint (the
458-page GT-table population already costs several hours) -- a stratified
sample large enough for a meaningful false-positive RATE estimate is used
instead, consistent with 033's own adversarial-suite sampling precedent.
Deliberately launched sequentially AFTER the gt_tables_chunk0/1 extraction
finishes, not concurrently, to avoid CPU contention with the primary
population.

Stratified by data_source (proportional, capped) so the false-positive
check isn't biased toward one genre.

    python experiments/035_mechanism_d_gating/build_non_table_sample.py
"""
from __future__ import annotations

import argparse
import json
import random
import shutil
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
FULL = HERE.parents[1] / "experiments" / "034a_omnidocbench_snapshot" / "dataset" / "full"
OUT = HERE / "dataset" / "non_table_sample"
SEED = 35
TARGET_N = 150
BATCH_SIZE = 20


def build_initial_sample():
    raw = json.loads((FULL / "OmniDocBench.json").read_text())
    no_table = [r for r in raw if not any(d.get("category_type") == "table" for d in r.get("layout_dets", []))]

    by_source = defaultdict(list)
    for r in no_table:
        by_source[r["page_info"].get("page_attribute", {}).get("data_source", "?")].append(r)

    rng = random.Random(SEED)
    per_source_target = max(1, TARGET_N // len(by_source))
    picked = []
    for source, recs in sorted(by_source.items()):
        k = min(per_source_target, len(recs))
        picked.extend(rng.sample(recs, k))
    # top up to TARGET_N if under, from the remaining pool
    if len(picked) < TARGET_N:
        remaining = [r for recs in by_source.values() for r in recs if r not in picked]
        rng.shuffle(remaining)
        picked.extend(remaining[:TARGET_N - len(picked)])

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "images").mkdir(exist_ok=True)
    for r in picked:
        name = Path(r["page_info"]["image_path"]).name
        src, dst = FULL / "images" / name, OUT / "images" / name
        if not dst.exists():
            shutil.copy2(src, dst)
    (OUT / "OmniDocBench.json").write_text(json.dumps(picked, ensure_ascii=False))

    manifest = {
        "method": f"stratified by data_source (seed={SEED}), proportional-capped sample "
            f"of pages WITHOUT any GT table, target n={TARGET_N}",
        "n_no_table_pages_in_full_dataset": len(no_table),
        "n_sampled": len(picked),
        "distribution": {s: sum(1 for r in picked if r["page_info"]["page_attribute"].get("data_source") == s)
                          for s in sorted(by_source)},
        "image_names": [Path(r["page_info"]["image_path"]).name for r in picked],
    }
    Path(HERE / "non_table_sample_manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False))
    print(f"sampled {len(picked)} / {len(no_table)} no-table pages")
    return 0


def complete_run_names(runs_dir: Path) -> set[str]:
    """Return only structurally complete preserved Phase 13 page-runs."""
    required = ("metadata.json", "layout/page-001.json", "ocr/page-001.json",
                "tables/page-001.json", "final/document.json")
    completed = set()
    if not runs_dir.is_dir():
        return completed
    for run_dir in runs_dir.iterdir():
        if not run_dir.is_dir() or not all((run_dir / rel).is_file() for rel in required):
            continue
        try:
            meta = json.loads((run_dir / "metadata.json").read_text())
            for rel in required:
                if rel != "metadata.json":
                    json.loads((run_dir / rel).read_text())
            completed.add(meta["input_filename"])
        except (KeyError, json.JSONDecodeError):
            continue
    return completed


def completed_recovery_roots() -> dict[int, tuple[Path, set[str], str | None]]:
    """Return only PASS-selected, structurally unchanged recovery cohorts.

    Completion alone is deliberately insufficient: an interrupted attempt can
    contain a complete-looking subset which must not affect resume planning
    until its batch validator has selected and passed that exact run root.
    The post-validation structural comparison also prevents a later partial
    rewrite from being silently treated as the cohort that was validated.
    """
    manifest_path = HERE / "non_table_recovery_batches_manifest.json"
    if not manifest_path.is_file():
        return {}
    manifest = json.loads(manifest_path.read_text())
    roots = {}
    for batch in sorted(manifest.get("batches", []), key=lambda b: b["batch_index"]):
        batch_index = batch["batch_index"]
        validation_path = HERE / batch.get(
            "validation_file", f"non_table_batch{batch_index}_validation.json"
        )
        if not validation_path.is_file():
            continue
        validation = json.loads(validation_path.read_text())
        if not validation.get("PASS"):
            continue
        runs_dir = HERE / validation.get(
            "runs_dir",
            f"results/non_table_sample_recovery/batch{batch_index}/_doc_extraction_runs",
        )
        names = complete_run_names(runs_dir)
        assigned = set(batch["image_names"])
        validated = set(validation.get("completed_names", []))
        if names != assigned or validated != assigned:
            raise SystemExit(
                f"FATAL: PASS Phase 13 batch{batch_index} no longer matches its "
                "validated assignment; inspect the preserved evidence before resuming"
            )
        roots[batch_index] = (runs_dir.parent, names, batch.get("validation_file"))
    return roots


def admit_salvage(batch_index: int):
    """Admit only a structurally complete subset of an interrupted attempt.

    The normal batch validation intentionally fails when an attempt has both
    complete and incomplete pages.  This command preserves that failed record
    and emits a separate PASS admission record for just its verified complete
    identities, then rebuilds the remaining <=20-page jobs.  It is an
    execution-recovery operation, not a change to the frozen sample.
    """
    manifest_path = HERE / "non_table_recovery_batches_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    batch = next((b for b in manifest["batches"] if b["batch_index"] == batch_index), None)
    if batch is None:
        raise SystemExit(f"FATAL: batch{batch_index} is not in the Phase 13 manifest")
    attempt_validation_path = HERE / f"non_table_batch{batch_index}_validation.json"
    if not attempt_validation_path.is_file():
        raise SystemExit(f"FATAL: validate interrupted batch{batch_index} before requesting salvage")
    attempt = json.loads(attempt_validation_path.read_text())
    completed = sorted(set(attempt.get("completed_names", [])))
    if attempt.get("PASS") or not completed:
        raise SystemExit(f"FATAL: batch{batch_index} has no failed-attempt subset eligible for salvage")
    disallowed = (
        attempt.get("unexpected_pages_not_in_assignment")
        or attempt.get("collision_with_original_32")
        or attempt.get("collision_with_prior_recovery_batches")
        or attempt.get("duplicate_within_batch")
        or attempt.get("schema_errors")
    )
    if disallowed:
        raise SystemExit(f"FATAL: batch{batch_index} has collision/schema evidence; do not salvage automatically")
    source_assignment = batch.get("source_attempt_image_names")
    if source_assignment is None:
        # A salvage invocation may be retried after a harness interruption
        # between writing its admission record and rebuilding the manifest.
        # Recover the immutable original attempt assignment from its prepared
        # dataset rather than mistaking the prior salvage subset for it.
        dataset_json = HERE / "dataset" / f"non_table_recovery_batch{batch_index}" / "OmniDocBench.json"
        if dataset_json.is_file():
            source_assignment = [r["page_info"]["image_path"] for r in json.loads(dataset_json.read_text())]
        else:
            source_assignment = batch["image_names"]
    assigned = set(source_assignment)
    if not set(completed) <= assigned:
        raise SystemExit(f"FATAL: batch{batch_index} completed identities are outside its assignment")

    salvage_file = f"non_table_batch{batch_index}_salvage_validation.json"
    salvage = {
        **attempt,
        "admission_kind": "structurally_complete_subset_of_failed_attempt",
        "failed_attempt_validation": attempt_validation_path.name,
        "n_assigned": len(completed),
        "n_completed_valid": len(completed),
        "n_incomplete": 0,
        "sum_check_ok": True,
        "assigned_pages_missing_entirely": [],
        "incomplete_names": [],
        "completed_names": completed,
        "PASS": True,
    }
    (HERE / salvage_file).write_text(json.dumps(salvage, indent=1, ensure_ascii=False))
    batch.update({
        "n_pages": len(completed), "kind": "preserved_salvage",
        "dataset_dir": None, "image_names": completed,
        "validation_file": salvage_file,
        "source_attempt_output_dir": attempt.get("output_dir"),
        "source_attempt_image_names": source_assignment,
    })
    manifest_path.write_text(json.dumps(manifest, indent=1, ensure_ascii=False))
    return build_resume_batches()


def restore_failed_attempt_assignment(batch_index: int):
    """Restore an attempt's full immutable assignment before revalidation.

    This is needed only if a harness interruption occurs while salvage
    bookkeeping is being written.  The prepared dataset is the authoritative
    copy of that attempt's original assignment; no pages are copied or run.
    """
    manifest_path = HERE / "non_table_recovery_batches_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    batch = next((b for b in manifest["batches"] if b["batch_index"] == batch_index), None)
    if batch is None:
        raise SystemExit(f"FATAL: batch{batch_index} is not in the Phase 13 manifest")
    dataset_dir = HERE / "dataset" / f"non_table_recovery_batch{batch_index}"
    dataset_json = dataset_dir / "OmniDocBench.json"
    if not dataset_json.is_file():
        raise SystemExit(f"FATAL: cannot restore batch{batch_index}; {dataset_json} is absent")
    image_names = [r["page_info"]["image_path"] for r in json.loads(dataset_json.read_text())]
    batch.update({
        "n_pages": len(image_names), "kind": "new",
        "dataset_dir": str(dataset_dir.relative_to(HERE)), "image_names": image_names,
        "output_dir": f"results/non_table_sample_recovery/batch{batch_index}",
    })
    for key in ("validation_file", "source_attempt_output_dir", "source_attempt_image_names"):
        batch.pop(key, None)
    manifest_path.write_text(json.dumps(manifest, indent=1, ensure_ascii=False))
    print(f"restored batch{batch_index} assignment: {len(image_names)} pages")
    return 0


def build_resume_batches():
    """Split only missing pages from the frozen sample into <=20-page jobs.

    This is an execution-safety mechanism after an intentional or external
    interruption. It neither redraws the stratified sample nor changes a
    backend/configuration/classification definition. Existing complete runs
    remain immutable and are excluded by input identity.
    """
    sample_path = OUT / "OmniDocBench.json"
    if not sample_path.is_file():
        raise SystemExit("FATAL: build the frozen Phase 13 sample before requesting --resume")
    records = json.loads(sample_path.read_text())
    names = [r["page_info"]["image_path"] for r in records]
    original_completed = complete_run_names(HERE / "results" / "non_table_sample" / "_doc_extraction_runs")
    recovery_roots = completed_recovery_roots()
    recovered_completed = set().union(*(root_names for _, root_names, _ in recovery_roots.values())) if recovery_roots else set()
    completed = original_completed | recovered_completed
    unknown = completed - set(names)
    if unknown:
        raise SystemExit(f"FATAL: preserved Phase 13 runs not in frozen sample: {sorted(unknown)[:3]}")
    if len(completed) != len(original_completed) + len(recovered_completed):
        raise SystemExit("FATAL: duplicate Phase 13 identities across preserved roots")
    remaining = [name for name in names if name not in completed]

    recovery_root_for_name = {
        name: str(root.relative_to(HERE))
        for _, (root, recovered_names, _) in recovery_roots.items()
        for name in recovered_names
    }
    identity_ledger = []
    for name in names:
        if name in original_completed:
            identity_ledger.append({"image_name": name, "status": "VALID_ORIGINAL",
                                    "run_root": "results/non_table_sample"})
        elif name in recovery_root_for_name:
            identity_ledger.append({"image_name": name, "status": "VALID_RECOVERY",
                                    "run_root": recovery_root_for_name[name]})
        else:
            identity_ledger.append({"image_name": name, "status": "NOT_STARTED", "run_root": None})
    (HERE / "phase13_identity_ledger.json").write_text(json.dumps({
        "frozen_sample_size": len(names), "n_valid_original": len(original_completed),
        "n_valid_recovery": len(recovered_completed), "n_not_started": len(remaining),
        "n_incomplete_unresolved": 0,
        "historical_incomplete_run_directories": [
            str(p.relative_to(HERE)) for p in
            (HERE / "results" / "non_table_sample" / "_doc_extraction_runs").iterdir()
            if p.is_dir() and not all((p / rel).is_file() for rel in (
                "metadata.json", "layout/page-001.json", "ocr/page-001.json",
                "tables/page-001.json", "final/document.json",
            ))
        ],
        "identities": identity_ledger,
    }, indent=1, ensure_ascii=False))

    (HERE / "phase13_inventory_at_interrupt.json").write_text(json.dumps({
        "completed": sorted(original_completed), "expected": names,
        "n_completed": len(original_completed), "n_preserved_recovery": len(recovered_completed),
        "n_total_preserved": len(completed), "n_remaining": len(remaining),
        "reason": "process-recycled execution of the unchanged frozen Phase 13 sample",
    }, indent=1, ensure_ascii=False))

    by_name = {r["page_info"]["image_path"]: r for r in records}
    batch_info = [
        {
            "batch_index": bi, "n_pages": len(batch_names), "kind": "preserved_salvage",
            "dataset_dir": None,
            "output_dir": str(batch_dir.relative_to(HERE)),
            "image_names": sorted(batch_names),
            **({"validation_file": validation_file} if validation_file else {}),
        }
        for bi, (batch_dir, batch_names, validation_file) in sorted(recovery_roots.items())
    ]
    next_index = max(recovery_roots, default=-1) + 1
    batches = [remaining[i:i + BATCH_SIZE] for i in range(0, len(remaining), BATCH_SIZE)]
    for offset, batch_names in enumerate(batches):
        bi = next_index + offset
        out = HERE / "dataset" / f"non_table_recovery_batch{bi}"
        (out / "images").mkdir(parents=True, exist_ok=True)
        batch_records = [by_name[name] for name in batch_names]
        for name in batch_names:
            src, dst = OUT / "images" / name, out / "images" / name
            if not dst.exists():
                shutil.copy2(src, dst)
        (out / "OmniDocBench.json").write_text(json.dumps(batch_records, ensure_ascii=False))
        batch_info.append({
            "batch_index": bi, "n_pages": len(batch_names), "kind": "new",
            "dataset_dir": str(out.relative_to(HERE)),
            "output_dir": f"results/non_table_sample_recovery/batch{bi}",
            "image_names": batch_names,
        })
    (HERE / "non_table_recovery_batches_manifest.json").write_text(json.dumps({
        "purpose": "process-recycled continuation of the unchanged frozen Phase 13 sample",
        "n_batches": len(batch_info), "batch_size_nominal": BATCH_SIZE,
        "sample_size": len(names), "preserved_original": len(original_completed),
        "preserved_recovery": len(recovered_completed), "preserved_completed": len(completed),
        "remaining_pages": len(remaining), "batches": batch_info,
    }, indent=1, ensure_ascii=False))
    print(f"Phase 13 resume: preserved={len(completed)}, remaining={len(remaining)}, batches={len(batch_info)}")
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", action="store_true", help="batch only the missing pages from the frozen sample")
    parser.add_argument("--admit-salvage", type=int, metavar="BATCH", help="admit complete pages from one failed validated attempt")
    parser.add_argument("--restore-attempt", type=int, metavar="BATCH", help="restore an interrupted salvage attempt's original assignment")
    args = parser.parse_args()
    selected = sum(x is not None for x in (args.admit_salvage, args.restore_attempt)) + int(args.resume)
    if selected > 1:
        parser.error("--resume, --admit-salvage, and --restore-attempt are mutually exclusive")
    if args.admit_salvage is not None:
        return admit_salvage(args.admit_salvage)
    if args.restore_attempt is not None:
        return restore_failed_attempt_assignment(args.restore_attempt)
    return build_resume_batches() if args.resume else build_initial_sample()


if __name__ == "__main__":
    raise SystemExit(main())
