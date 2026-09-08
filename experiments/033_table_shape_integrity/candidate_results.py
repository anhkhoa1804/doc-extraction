"""033 Phase 4/7 -- is each candidate measurement-safe? Test against every
REAL confirmed/factual case from 031/032 before any "better routing"
claim. Includes the paired historical evaluation (Phase 7): for every
document with a picture-gated arm AND a factual table-producing arm,
would the candidate reject the true table, correctly recover it, remain
ambiguous, or create a pseudo-table?

    python experiments/033_table_shape_integrity/candidate_results.py
"""
from __future__ import annotations
import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
L31 = HERE.parents[1] / "experiments/031_table_label_gating"
L32 = HERE.parents[1] / "experiments/032_role_ambiguity"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(L31))
from candidate_designs import CANDIDATES  # noqa: E402
from table_shape_probe import table_shape_score  # noqa: E402


def evaluate_population():
    probe = json.loads((L31 / "table_shape_probe.json").read_text())
    verdicts = json.loads((L31 / "recovery_verdicts.json").read_text())
    negctl = json.loads((L31 / "negative_controls.json").read_text())

    verdict_by_doc = {}
    for v in verdicts["verdicts"]:
        verdict_by_doc.setdefault(v["document_id"], set()).add(v["verdict"])

    # IMPORTANT (discovered this milestone by direct verification, not
    # assumed): 031's table_shape_probe.json field "all_negative_rows" is
    # an EMPTY LIST (0 items) despite negative_population.n=39 -- the real
    # 39-row negative/ambiguous population is embedded WITHIN
    # "all_positive_rows" (a misleadingly-named field: it actually holds
    # the FULL 118-candidate population, both CONFIRMED and AMBIGUOUS),
    # distinguished by is_table_ground_truth=False. Verified directly:
    # len(all_negative_rows)==0, len(all_positive_rows)==118, of which 79
    # have is_table_ground_truth=True and 39 have it False, and those 39
    # are exactly the 3 known negative documents (cmb_lowcontrast_stamp_vi,
    # hc_stamp_text_vi, hc_transparent_seal_vi).
    rows = []
    for r in probe["all_positive_rows"]:
        is_positive = bool(r.get("is_table_ground_truth"))
        rows.append({
            "source": "031_positive_population" if is_positive else "031_negative_population",
            "document_id": r["document_id"],
            "milestone": r["milestone"], "arm": r["arm"], "signals": r["signals"],
            "original_score": r["table_shape_score"],
            "original_gate_pass": r["table_shape_score"] >= 3,
            "recovery_verdicts": sorted(verdict_by_doc.get(r["document_id"], [])) if is_positive else [],
            "is_true_recovery_doc": is_positive and "TRUE_RECOVERY" in verdict_by_doc.get(r["document_id"], set()),
            "is_plausible_recovery_doc": is_positive and verdict_by_doc.get(r["document_id"], set()) == {"PLAUSIBLE_RECOVERY"},
            "is_pseudo_table_doc": is_positive and verdict_by_doc.get(r["document_id"], set()) == {"PSEUDO_TABLE"},
            "is_known_negative": not is_positive,
        })
    # probe["all_negative_rows"] is verified empty this milestone but kept
    # in the loop (no-op today) so a future corrected artifact is picked
    # up automatically without code changes.
    for r in probe["all_negative_rows"]:
        rows.append({
            "source": "031_negative_population", "document_id": r["document_id"],
            "milestone": r["milestone"], "arm": r["arm"], "signals": r["signals"],
            "original_score": r["table_shape_score"],
            "original_gate_pass": r["table_shape_score"] >= 3,
            "recovery_verdicts": [], "is_true_recovery_doc": False,
            "is_plausible_recovery_doc": False, "is_pseudo_table_doc": False,
            "is_known_negative": True,
        })
    for r in negctl["realscan_probe_population"]["regions_scored"]:
        rows.append({
            "source": "032_realscan_probe", "document_id": f"{r['document_id']}#region{r['region_index']}",
            "milestone": "realscan_probe", "arm": "n/a", "signals": r["signals"],
            "original_score": r["table_shape_score"],
            "original_gate_pass": r["table_shape_score"] >= 3,
            "recovery_verdicts": [], "is_true_recovery_doc": False,
            "is_plausible_recovery_doc": False, "is_pseudo_table_doc": False,
            "ground_truth": r["ground_truth"],
            "is_confirmed_false_positive": r["ground_truth"] == "NOT_A_TABLE",
        })
    return rows


def main():
    rows = evaluate_population()
    results = {}
    for cand_name, cand in CANDIDATES.items():
        fn = cand["fn"]
        per_row = []
        for r in rows:
            passes, score, reasons, detail = fn(r["signals"])
            per_row.append({**{k: r[k] for k in
                              ("source", "document_id", "milestone", "arm",
                               "original_score", "original_gate_pass")},
                            "candidate_gate_pass": passes, "detail": detail})

        by_doc_pass = {}
        for r, p in zip(rows, per_row):
            by_doc_pass.setdefault(r["document_id"], []).append(p["candidate_gate_pass"])

        true_recovery_docs = {r["document_id"] for r in rows if r.get("is_true_recovery_doc")}
        plausible_docs = {r["document_id"] for r in rows if r.get("is_plausible_recovery_doc")}
        pseudo_docs = {r["document_id"] for r in rows if r.get("is_pseudo_table_doc")}
        known_negative_docs = {r["document_id"] for r in rows if r.get("is_known_negative")}
        chapter9_docs = {r["document_id"] for r in rows if r.get("is_confirmed_false_positive")}

        def retention(doc_set):
            if not doc_set:
                return None
            n_any_pass = sum(1 for d in doc_set if any(by_doc_pass.get(d, [False])))
            n_all_pass = sum(1 for d in doc_set if all(by_doc_pass.get(d, [False])))
            return {"n_documents": len(doc_set), "n_at_least_one_arm_passes": n_any_pass,
                   "n_every_arm_passes": n_all_pass}

        results[cand_name] = {
            "confirmed_true_recovery_retention": retention(true_recovery_docs),
            "plausible_recovery_retention": retention(plausible_docs),
            "pseudo_table_rejection": retention(pseudo_docs),  # "retention" here = still WRONGLY passes
            "known_negative_rejection": retention(known_negative_docs),
            "chapter9_false_positive_rejection": retention(chapter9_docs),
            "per_row_detail": per_row,
        }

    # summary table for quick reading
    summary = {}
    for cand_name, res in results.items():
        summary[cand_name] = {
            "true_recovery_docs_still_fully_passing": (
                res["confirmed_true_recovery_retention"]["n_every_arm_passes"]
                if res["confirmed_true_recovery_retention"] else None),
            "true_recovery_docs_total": (
                res["confirmed_true_recovery_retention"]["n_documents"]
                if res["confirmed_true_recovery_retention"] else None),
            "plausible_docs_still_passing_any_arm": (
                res["plausible_recovery_retention"]["n_at_least_one_arm_passes"]
                if res["plausible_recovery_retention"] else None),
            "pseudo_table_docs_STILL_WRONGLY_passing_any_arm": (
                res["pseudo_table_rejection"]["n_at_least_one_arm_passes"]
                if res["pseudo_table_rejection"] else None),
            "known_negative_docs_STILL_WRONGLY_passing": (
                res["known_negative_rejection"]["n_at_least_one_arm_passes"]
                if res["known_negative_rejection"] else None),
            "chapter9_STILL_WRONGLY_passing": (
                res["chapter9_false_positive_rejection"]["n_at_least_one_arm_passes"]
                if res["chapter9_false_positive_rejection"] else None),
        }

    payload = {
        "method": "every candidate from candidate_designs.py run against "
                 "the REAL signals already computed in 031's table_shape_"
                 "probe.json (all_positive_rows + all_negative_rows) and "
                 "032's negative_controls.json realscan_probe population "
                 "-- no re-derivation of signals, only re-application of "
                 "the gating decision.",
        "per_candidate": results,
        "summary": summary,
        "baseline_for_comparison": {
            "note": "the ORIGINAL rule (table_shape_score>=3, no AND-gate) "
                   "already retains all 4 confirmed documents (0/79 "
                   "conservative reconstructions failed the gate for the "
                   "wrong reason -- gate failures were never the issue, "
                   "structural coherence AFTER reconstruction was) and "
                   "wrongly passes the Chapter9 false positive AND (by "
                   "construction, known_failure.json) any long enough "
                   "single-column prose block.",
        },
    }
    Path("candidate_results.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False))
    print("SUMMARY:")
    for cand_name, s in summary.items():
        print(f"  {cand_name}:")
        for k, v in s.items():
            print(f"    {k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
