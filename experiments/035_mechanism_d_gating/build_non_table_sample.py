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
    completed = complete_run_names(HERE / "results" / "non_table_sample" / "_doc_extraction_runs")
    unknown = completed - set(names)
    if unknown:
        raise SystemExit(f"FATAL: preserved Phase 13 runs not in frozen sample: {sorted(unknown)[:3]}")
    remaining = [name for name in names if name not in completed]

    (HERE / "phase13_inventory_at_interrupt.json").write_text(json.dumps({
        "completed": sorted(completed), "expected": names,
        "n_completed": len(completed), "n_remaining": len(remaining),
        "reason": "process-recycled execution of the unchanged frozen Phase 13 sample",
    }, indent=1, ensure_ascii=False))

    by_name = {r["page_info"]["image_path"]: r for r in records}
    batches = [remaining[i:i + BATCH_SIZE] for i in range(0, len(remaining), BATCH_SIZE)]
    batch_info = []
    for bi, batch_names in enumerate(batches):
        out = HERE / "dataset" / f"non_table_recovery_batch{bi}"
        (out / "images").mkdir(parents=True, exist_ok=True)
        batch_records = [by_name[name] for name in batch_names]
        for name in batch_names:
            src, dst = OUT / "images" / name, out / "images" / name
            if not dst.exists():
                shutil.copy2(src, dst)
        (out / "OmniDocBench.json").write_text(json.dumps(batch_records, ensure_ascii=False))
        batch_info.append({
            "batch_index": bi, "n_pages": len(batch_names),
            "dataset_dir": str(out.relative_to(HERE)),
            "output_dir": f"results/non_table_sample_recovery/batch{bi}",
            "image_names": batch_names,
        })
    (HERE / "non_table_recovery_batches_manifest.json").write_text(json.dumps({
        "purpose": "process-recycled continuation of the unchanged frozen Phase 13 sample",
        "n_batches": len(batch_info), "batch_size_nominal": BATCH_SIZE,
        "sample_size": len(names), "preserved_completed": len(completed),
        "remaining_pages": len(remaining), "batches": batch_info,
    }, indent=1, ensure_ascii=False))
    print(f"Phase 13 resume: preserved={len(completed)}, remaining={len(remaining)}, batches={len(batch_info)}")
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", action="store_true", help="batch only the missing pages from the frozen sample")
    args = parser.parse_args()
    return build_resume_batches() if args.resume else build_initial_sample()


if __name__ == "__main__":
    raise SystemExit(main())
