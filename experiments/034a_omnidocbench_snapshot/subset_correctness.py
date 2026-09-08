"""034a Phase 6 -- correctness baseline: config A (workaround, device="cuda"
literal, configs/gpu.yaml unmodified) vs config B (fixed, device="auto",
now safe after the process_file() guard). If the fix is semantically
no-op (as designed -- auto resolves to cuda under a CLEAR GPU, same string
reaches every backend either way), outputs should be identical.

    python experiments/034a_omnidocbench_snapshot/subset_correctness.py
"""
from __future__ import annotations
import hashlib, json
from pathlib import Path
HERE = Path(__file__).resolve().parent

DIR_A = HERE / "results" / "subset_A_workaround"
DIR_B = HERE / "results" / "subset_B_fixed_auto"


def load_predictions(d):
    preds = {}
    for f in sorted((d / "predictions").glob("*.md")):
        preds[f.name] = f.read_text(encoding="utf-8")
    return preds


def load_document_jsons(d):
    """Per-page canonical IR, from _doc_extraction_runs/<doc_id>/final/document.json
    (only present if prepare.py was run without deleting runs -- both A and B
    are run WITHOUT --keep-runs by default, so this may be empty; predictions/
    (the .md files actually scored) are the primary comparison)."""
    out = {}
    runs_dir = d / "_doc_extraction_runs"
    if not runs_dir.exists():
        return out
    for doc_dir in sorted(runs_dir.iterdir()):
        f = doc_dir / "final" / "document.json"
        if f.exists():
            out[doc_dir.name] = json.loads(f.read_text())
    return out


def main():
    if not (DIR_A / "predictions").exists() or not (DIR_B / "predictions").exists():
        print("both subset_A_workaround and subset_B_fixed_auto predictions must exist first")
        return 1

    preds_a = load_predictions(DIR_A)
    preds_b = load_predictions(DIR_B)

    names_a, names_b = set(preds_a), set(preds_b)
    only_a = names_a - names_b
    only_b = names_b - names_a
    common = names_a & names_b

    identical = []
    different = []
    for name in sorted(common):
        ha = hashlib.sha256(preds_a[name].encode()).hexdigest()[:16]
        hb = hashlib.sha256(preds_b[name].encode()).hexdigest()[:16]
        if ha == hb:
            identical.append(name)
        else:
            different.append({
                "name": name, "hash_a": ha, "hash_b": hb,
                "len_a": len(preds_a[name]), "len_b": len(preds_b[name]),
                "char_diff": len(preds_a[name]) - len(preds_b[name]),
            })

    runtime_a = json.loads((DIR_A / "runtime.json").read_text()) if (DIR_A / "runtime.json").exists() else {}
    runtime_b = json.loads((DIR_B / "runtime.json").read_text()) if (DIR_B / "runtime.json").exists() else {}
    meta_a = json.loads((DIR_A / "run_metadata.json").read_text()) if (DIR_A / "run_metadata.json").exists() else {}
    meta_b = json.loads((DIR_B / "run_metadata.json").read_text()) if (DIR_B / "run_metadata.json").exists() else {}

    payload = {
        "config_A": "config_A_workaround_cuda_literal.yaml (device: \"cuda\" literal, "
                   "configs/gpu.yaml unmodified -- the workaround used before the fix)",
        "config_B": "config_B_fixed_auto.yaml (device: \"auto\", configs/cpu.yaml + one "
                   "field -- the TRUE intended production config, now safe with the "
                   "process_file() guard fix)",
        "device_actually_resolved_A": meta_a.get("device"),
        "device_actually_resolved_B": meta_b.get("device"),
        "n_predictions_A": len(names_a), "n_predictions_B": len(names_b),
        "only_in_A": sorted(only_a), "only_in_B": sorted(only_b),
        "n_identical_byte_for_byte": len(identical),
        "n_different": len(different),
        "different_predictions": different,
        "runtime_A": {k: runtime_a.get(k) for k in
                     ("succeeded", "failed", "mean_seconds_per_page", "total_runtime_seconds")},
        "runtime_B": {k: runtime_b.get(k) for k in
                     ("succeeded", "failed", "mean_seconds_per_page", "total_runtime_seconds")},
        "verdict": (
            "SEMANTICALLY EQUIVALENT -- 100% byte-identical predictions, fix is a pure "
            "resolution-boundary correctness fix with zero output-affecting side effect"
            if not different and not only_a and not only_b and names_a == names_b
            else f"{len(different)} prediction(s) differ -- INVESTIGATE before treating the "
                 f"fix as semantically no-op (note: the visual/model route is NOT asserted "
                 f"deterministic across separate process runs even with identical config -- "
                 f"docs/production-contract.md -- so a small number of differences may "
                 f"reflect inherent model-kernel nondeterminism, not the fix itself; "
                 f"cross-check against known nondeterminism before concluding the fix is at fault)"
        ),
    }
    Path("subset_correctness.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False))
    print(f"identical: {len(identical)}/{len(common)}, different: {len(different)}")
    print(f"only_in_A: {only_a}, only_in_B: {only_b}")
    print(f"verdict: {payload['verdict'][:100]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
