"""035 OOM recovery -- split a recovery manifest's population into batches
of <=20 pages for process-recycled recovery (Mode 2, authorized recovery
plan). Each batch gets its own dataset dir (images + filtered
OmniDocBench.json) and its own output dir under
results/<source>_recovery/batch<N>/ -- fully isolated per batch, never
overlapping the original chunk's output tree, never overlapping each other.

Generalized (2026-09-09, second termination event) to work for any source
chunk's recovery manifest, not just chunk0's -- reused for chunk1's 30-page
recovery rather than duplicated as a near-identical second script, per
this milestone's own repo-discipline rule.

    python experiments/035_mechanism_d_gating/build_recovery_batches.py [source_name] [manifest_file]

    source_name    default "chunk0" -- used only for output path naming
                   (dataset/<source_name>_recovery_batch<N>,
                   results/gt_tables_<source_name>_recovery/batch<N>)
    manifest_file  default "recovery_manifest.json"
"""
from __future__ import annotations
import json, shutil, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
FULL = HERE.parent / "034a_omnidocbench_snapshot" / "dataset" / "full"
BATCH_SIZE = 20


def main():
    source_name = sys.argv[1] if len(sys.argv) > 1 else "chunk0"
    manifest_file = sys.argv[2] if len(sys.argv) > 2 else "recovery_manifest.json"

    manifest = json.loads((HERE / manifest_file).read_text())
    target_names = [t["image"] for t in manifest["targets"]]
    reason_by_name = {t["image"]: t["reason"] for t in manifest["targets"]}

    raw = json.loads((FULL / "OmniDocBench.json").read_text())
    by_name = {r["page_info"]["image_path"]: r for r in raw}

    missing = [n for n in target_names if n not in by_name]
    if missing:
        raise SystemExit(f"FATAL: {len(missing)} recovery target(s) not found in GT JSON: {missing[:5]}")

    batches = [target_names[i:i + BATCH_SIZE] for i in range(0, len(target_names), BATCH_SIZE)]
    batch_info = []
    for bi, names in enumerate(batches):
        out = HERE / "dataset" / f"{source_name}_recovery_batch{bi}"
        (out / "images").mkdir(parents=True, exist_ok=True)
        recs = []
        for n in names:
            r = by_name[n]
            recs.append(r)
            src = FULL / "images" / n
            dst = out / "images" / n
            if not dst.exists():
                shutil.copy2(src, dst)
        (out / "OmniDocBench.json").write_text(json.dumps(recs, ensure_ascii=False))
        batch_info.append({
            "batch_index": bi, "n_pages": len(names),
            "reasons": {r: sum(1 for n in names if reason_by_name[n] == r) for r in ("NOT_STARTED", "INCOMPLETE_RETRY")},
            "dataset_dir": str(out.relative_to(HERE)),
            "output_dir": f"results/gt_tables_{source_name}_recovery/batch{bi}",
            "image_names": names,
        })

    total = sum(b["n_pages"] for b in batch_info)
    out_manifest_name = "recovery_batches_manifest.json" if source_name == "chunk0" else f"{source_name}_recovery_batches_manifest.json"
    Path(HERE / out_manifest_name).write_text(json.dumps({
        "source_name": source_name, "n_batches": len(batch_info), "batch_size_nominal": BATCH_SIZE,
        "total_pages": total, "matches_recovery_manifest": total == len(target_names),
        "batches": batch_info,
    }, indent=1, ensure_ascii=False))
    print(f"built {len(batch_info)} batches, total {total} pages (expect {len(target_names)}) -> {out_manifest_name}")
    for b in batch_info:
        print(f"  batch{b['batch_index']}: {b['n_pages']} pages, reasons={b['reasons']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
