"""035 Phase 1 support -- build a sub-dataset containing exactly the pages
that have >=1 GT table annotation (category_type == "table") in the full
OmniDocBench ground truth. This is the population Mechanism D's region
matcher (Phase 3) needs internal layout JSON for; that data was never
persisted for the full 1651-page run (no --keep-runs was used -- see
experiments/034a_omnidocbench_snapshot/results/full_baseline, which has
predictions/ only, no _doc_extraction_runs/), so it must be regenerated
via a targeted, --keep-runs re-run limited to this sub-dataset -- not a
re-run of the full corpus.

Mirrors experiments/034a_omnidocbench_snapshot/build_subset.py's own
convention (copy images + write a filtered OmniDocBench.json), applied to
the deterministic full population "GT table" rather than a stratified
sample.

    python experiments/035_mechanism_d_gating/build_gt_table_dataset.py
"""
from __future__ import annotations
import json, shutil
from pathlib import Path
HERE = Path(__file__).resolve().parent
FULL = HERE.parent / "034a_omnidocbench_snapshot" / "dataset" / "full"
OUT = HERE / "dataset" / "gt_tables"


def main():
    raw = json.loads((FULL / "OmniDocBench.json").read_text())

    table_pages = []
    no_table_pages = []
    for i, r in enumerate(raw):
        n_tables = sum(1 for d in r.get("layout_dets", []) if d.get("category_type") == "table")
        if n_tables > 0:
            table_pages.append((i, r, n_tables))
        else:
            no_table_pages.append((i, r))

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "images").mkdir(exist_ok=True)
    records = []
    for i, r, n in table_pages:
        name = Path(r["page_info"]["image_path"]).name
        src = FULL / "images" / name
        dst = OUT / "images" / name
        if not dst.exists():
            shutil.copy2(src, dst)
        records.append(r)
    (OUT / "OmniDocBench.json").write_text(json.dumps(records, ensure_ascii=False))

    manifest = {
        "method": "COMPLETE population, not a sample: every page in the full "
                 "1651-page OmniDocBench.json with >=1 layout_dets entry whose "
                 "category_type == 'table'.",
        "source": str((FULL / "OmniDocBench.json").resolve()),
        "n_total_pages_in_full_dataset": len(raw),
        "n_pages_with_gt_table": len(table_pages),
        "n_pages_without_gt_table": len(no_table_pages),
        "n_gt_table_instances": sum(n for _, _, n in table_pages),
        "cross_check": "n_gt_table_instances must equal 665 -- the evaluator's "
                       "own table.metric_debug.TEDS.sample_count in "
                       "results/full_baseline/metrics.json.",
        "page_indices_in_full_dataset": [i for i, _, _ in table_pages],
        "image_names": [Path(r["page_info"]["image_path"]).name for _, r, _ in table_pages],
    }
    Path(HERE / "gt_table_dataset_manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False))
    print(f"pages with GT table: {len(table_pages)} / {len(raw)}")
    print(f"GT table instances: {sum(n for _, _, n in table_pages)} (must equal 665)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
