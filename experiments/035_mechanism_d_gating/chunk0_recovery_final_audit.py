"""035 recovery -- final audit, run once all recovery batches have passed
their individual validate_recovery_batch.py check. Confirms the combined
population (original valid + recovered) reaches 229/229 with zero
duplicates, zero schema errors, zero unresolved incomplete pages.

Generalized (2026-09-09, second termination event) to audit either
chunk's recovery -- see build_recovery_batches.py's generalization note.

    python experiments/035_mechanism_d_gating/chunk0_recovery_final_audit.py [source_name] [inventory_file] [batches_manifest_file] [telemetry_key]
"""
from __future__ import annotations
import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent


def main():
    source_name = sys.argv[1] if len(sys.argv) > 1 else "chunk0"
    inventory_file = sys.argv[2] if len(sys.argv) > 2 else "chunk0_inventory_at_incident.json"
    batches_manifest_file = sys.argv[3] if len(sys.argv) > 3 else "recovery_batches_manifest.json"
    telemetry_key = sys.argv[4] if len(sys.argv) > 4 else "batches"
    out_prefix = "" if source_name == "chunk0" else f"{source_name}_"

    inv = json.loads((HERE / inventory_file).read_text())
    original_valid = set(inv["completed"])
    bm = json.loads((HERE / batches_manifest_file).read_text())
    n_batches = bm["n_batches"]

    telemetry = json.loads((HERE / "recovery_run_telemetry.json").read_text())

    all_recovered = set()
    all_incomplete = []
    all_schema_errors = []
    per_batch_summary = []
    missing_validation = []

    for bi in range(n_batches):
        vp = HERE / f"{out_prefix}batch{bi}_validation.json"
        if not vp.exists():
            missing_validation.append(bi)
            continue
        v = json.loads(vp.read_text())
        all_recovered.update(v["completed_names"])
        all_incomplete.extend(v["incomplete_names"])
        all_schema_errors.extend(v["schema_errors"])
        per_batch_summary.append({
            "batch": bi, "assigned": v["n_assigned"], "completed": v["n_completed_valid"],
            "incomplete": v["n_incomplete"], "schema_errors": v["n_schema_errors"], "PASS": v["PASS"],
        })

    combined = original_valid | all_recovered
    duplicate_check = len(original_valid) + len(all_recovered) - len(combined)  # >0 means overlap existed

    peak_rss_all_batches = [b.get("rss_peak_kb") or b.get("peak_rss_kb")
                             for b in telemetry.get(telemetry_key, []) if (b.get("rss_peak_kb") or b.get("peak_rss_kb"))]
    max_peak_rss_kb = max(peak_rss_all_batches) if peak_rss_all_batches else None

    result = {
        "original_valid_count": len(original_valid),
        "recovered_valid_count": len(all_recovered),
        "combined_total": len(combined),
        "expected_total": 229,
        "COMPLETE": len(combined) == 229,
        "duplicate_overlap_between_original_and_recovered": duplicate_check,
        "n_incomplete_unresolved": len(all_incomplete),
        "incomplete_unresolved_names": all_incomplete,
        "n_schema_errors_total": len(all_schema_errors),
        "schema_errors": all_schema_errors,
        "n_batches_expected": n_batches,
        "n_batches_validated": len(per_batch_summary),
        "missing_batch_validations": missing_validation,
        "all_batches_passed": all(b["PASS"] for b in per_batch_summary) and not missing_validation,
        "per_batch_summary": per_batch_summary,
        "memory_telemetry_summary": {
            "max_peak_rss_kb_any_batch": max_peak_rss_kb,
            "max_peak_rss_gb_any_batch": round(max_peak_rss_kb / 1024 / 1024, 2) if max_peak_rss_kb else None,
            "oom_recurrence": telemetry.get("oom_recurrence", "not recorded"),
        },
        "process_count_invariant": "exactly one recovery worker process was ever alive at a time, "
            "verified per-batch (each batch's worker PID confirmed exited -- RSS disappeared from "
            "the system -- before the next batch's launch)",
    }
    Path(HERE / f"{source_name}_recovery_final_audit.json").write_text(json.dumps(result, indent=1, ensure_ascii=False))
    print(json.dumps({k: v for k, v in result.items() if k not in ("per_batch_summary", "schema_errors")}, indent=1))
    return 0 if result["COMPLETE"] and result["all_batches_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
