"""035 OOM recovery -- post-batch structural validation. Run after EVERY
recovery batch, before starting the next one (per the recovery plan's
explicit "do not wait until all 197 pages are finished to discover
corruption").

Checks:
  - assigned == completed + incomplete (no page silently vanished)
  - every completed page-run has valid, parseable JSON in every stage file
  - page identity (input_filename) matches what was assigned to this batch
  - no collision with the original chunk's already-valid page identities
  - no duplicate page identity across batches already validated so far

Generalized (2026-09-09, second termination event) to work for any source
chunk's recovery, not just chunk0's -- see build_recovery_batches.py's
own generalization note.

    python experiments/035_mechanism_d_gating/validate_recovery_batch.py <batch_index> [source_name] [original_inventory_file] [batches_manifest_file] [output_dir]

``output_dir`` is normally omitted and resolves to the canonical
``results/gt_tables_<source>_recovery/batch<N>`` root.  A retry after an
interruption may use a separate root so the incomplete attempt remains
available as incident evidence; the validation JSON then records the exact
root that downstream analysis must use.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load_original_valid_names(inventory_file: str):
    inv = json.loads((HERE / inventory_file).read_text())
    return set(inv["completed"])


def load_batch_assignment(batch_index: int, batches_manifest_file: str):
    bm = json.loads((HERE / batches_manifest_file).read_text())
    b = next(x for x in bm["batches"] if x["batch_index"] == batch_index)
    return set(b["image_names"])


def already_recovered_names(up_to_batch_index: int, prefix: str):
    names = set()
    for bi in range(up_to_batch_index):
        p = HERE / f"{prefix}batch{bi}_validation.json"
        if p.exists():
            v = json.loads(p.read_text())
            names.update(v.get("completed_names", []))
    return names


def main():
    if len(sys.argv) < 2:
        print("usage: validate_recovery_batch.py <batch_index> [source_name] [original_inventory_file] [batches_manifest_file]", file=sys.stderr)
        return 2
    bi = int(sys.argv[1])
    source_name = sys.argv[2] if len(sys.argv) > 2 else "chunk0"
    inventory_file = sys.argv[3] if len(sys.argv) > 3 else "chunk0_inventory_at_incident.json"
    batches_manifest_file = sys.argv[4] if len(sys.argv) > 4 else "recovery_batches_manifest.json"
    out_prefix = "" if source_name == "chunk0" else f"{source_name}_"

    default_out_dir = HERE / "results" / f"gt_tables_{source_name}_recovery" / f"batch{bi}"
    out_dir = Path(sys.argv[5]) if len(sys.argv) > 5 else default_out_dir
    if not out_dir.is_absolute():
        out_dir = HERE / out_dir
    runs_dir = out_dir / "_doc_extraction_runs"
    assigned = load_batch_assignment(bi, batches_manifest_file)
    original_32 = load_original_valid_names(inventory_file)
    prior_recovered = already_recovered_names(bi, out_prefix)

    completed_names = []
    incomplete_names = []
    schema_errors = []

    if not runs_dir.exists():
        print(f"FATAL: {runs_dir} does not exist", file=sys.stderr)
        return 1

    for run_dir in sorted(runs_dir.iterdir()):
        meta_p = run_dir / "metadata.json"
        if not meta_p.exists():
            incomplete_names.append(f"(no metadata.json) {run_dir.name}")
            continue
        try:
            meta = json.loads(meta_p.read_text())
        except json.JSONDecodeError as e:
            schema_errors.append({"dir": run_dir.name, "file": "metadata.json", "error": str(e)})
            continue
        name = meta["input_filename"]

        required = ["layout/page-001.json", "ocr/page-001.json", "tables/page-001.json",
                    "final/document.json"]
        missing = [r for r in required if not (run_dir / r).exists()]
        if missing:
            incomplete_names.append(name)
            continue

        ok = True
        for r in required:
            try:
                json.loads((run_dir / r).read_text())
            except json.JSONDecodeError as e:
                schema_errors.append({"dir": run_dir.name, "file": r, "error": str(e)})
                ok = False
        if not ok:
            continue

        doc = json.loads((run_dir / "final" / "document.json").read_text())
        page = doc["pages"][0]
        if not all(k in page for k in ("width", "height", "elements")):
            schema_errors.append({"dir": run_dir.name, "file": "final/document.json",
                                   "error": "missing expected top-level Page keys"})
            continue

        completed_names.append(name)

    completed_set = set(completed_names)
    unexpected = completed_set - assigned
    missing_from_assigned = assigned - completed_set - {
        n.split(") ", 1)[-1] for n in incomplete_names
    }
    collision_with_original_32 = completed_set & original_32
    collision_with_prior_batches = completed_set & prior_recovered
    duplicate_within_batch = len(completed_names) != len(completed_set)

    result = {
        "batch_index": bi,
        "output_dir": str(out_dir.relative_to(HERE)),
        "runs_dir": str(runs_dir.relative_to(HERE)),
        "n_assigned": len(assigned),
        "n_completed_valid": len(completed_names),
        "n_incomplete": len(incomplete_names),
        "n_schema_errors": len(schema_errors),
        "sum_check_ok": len(completed_names) + len(incomplete_names) == len(assigned),
        "unexpected_pages_not_in_assignment": sorted(unexpected),
        "assigned_pages_missing_entirely": sorted(missing_from_assigned),
        "collision_with_original_32": sorted(collision_with_original_32),
        "collision_with_prior_recovery_batches": sorted(collision_with_prior_batches),
        "duplicate_within_batch": duplicate_within_batch,
        "schema_errors": schema_errors,
        "incomplete_names": incomplete_names,
        "completed_names": completed_names,
        "PASS": (
            len(completed_names) + len(incomplete_names) == len(assigned)
            and not unexpected and not collision_with_original_32
            and not collision_with_prior_batches and not duplicate_within_batch
            and not schema_errors
        ),
    }
    Path(HERE / f"{out_prefix}batch{bi}_validation.json").write_text(json.dumps(result, indent=1, ensure_ascii=False))
    print(f"batch{bi}: assigned={len(assigned)} completed={len(completed_names)} "
          f"incomplete={len(incomplete_names)} schema_errors={len(schema_errors)} PASS={result['PASS']}")
    if not result["PASS"]:
        print("VALIDATION FAILURES:", file=sys.stderr)
        for k in ("unexpected_pages_not_in_assignment", "assigned_pages_missing_entirely",
                  "collision_with_original_32", "collision_with_prior_recovery_batches", "schema_errors"):
            if result[k]:
                print(f"  {k}: {result[k]}", file=sys.stderr)
    return 0 if result["PASS"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
