"""035 -- deterministic regression tests for two real bugs found during
this milestone's own preflight audit. Synthetic/minimal data only, no
extraction or --keep-runs output required. Each test is verified to FAIL
against the old buggy behavior (reconstructed inline, not reimported --
the point is to prove the fix changes something observable, not just that
the new code runs).

    python experiments/035_mechanism_d_gating/test_matching_lib_regressions.py
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import matching_lib as ml

_spec = importlib.util.spec_from_file_location("p4", HERE / "phase4_9_14_funnel.py")
p4 = importlib.util.module_from_spec(_spec)
sys.modules["p4"] = p4
_spec.loader.exec_module(p4)


def _matched_region(region_index, label, gate_pass, element_type="picture"):
    return {
        "region_index": region_index, "internal_label_raw": label, "label_lower": label.lower(),
        "table_gate_pass": gate_pass, "confidence": None, "final_ir_element_type": element_type,
        "final_ir_table_id": None, "source_backend": "docling", "nested_regions_within_match_bbox": 0,
    }


def test_region_reuse_across_two_gt_tables_is_flagged():
    """Bug A: nothing previously ruled out the SAME internal region being
    matched_region for two different GT tables on one page -- each GT
    table is matched independently. Left unflagged, one extracted table
    could silently count as 'recovered' for both. detect_region_reuse()
    must catch this."""
    records = [
        {"image": "pageX.png", "gt_table_anno_id": "t1", "matched_region": _matched_region(3, "table", True)},
        {"image": "pageX.png", "gt_table_anno_id": "t2", "matched_region": _matched_region(3, "table", True)},
        {"image": "pageX.png", "gt_table_anno_id": "t3", "matched_region": _matched_region(7, "table", True)},
        {"image": "pageY.png", "gt_table_anno_id": "t4", "matched_region": _matched_region(3, "table", True)},
    ]

    # Sanity: the "old" behavior (before this fix existed) never populated
    # shared_region_with_other_gt_tables at all -- simulate that absence.
    for r in records:
        assert "shared_region_with_other_gt_tables" not in r, "test setup must start unflagged"

    n = ml.detect_region_reuse(records)

    assert n == 1, f"expected exactly 1 colliding (image, region_index) pair (pageX/3), got {n}"
    by_id = {r["gt_table_anno_id"]: r for r in records}
    assert by_id["t1"]["shared_region_with_other_gt_tables"] == ["t2"], by_id["t1"]
    assert by_id["t2"]["shared_region_with_other_gt_tables"] == ["t1"], by_id["t2"]
    assert by_id["t3"]["shared_region_with_other_gt_tables"] == [], "region 7 is unique, must not be flagged"
    assert by_id["t4"]["shared_region_with_other_gt_tables"] == [], (
        "pageY region 3 must NOT collide with pageX region 3 -- collision key is (image, region_index), not region_index alone"
    )

    # Verdict/threshold/classification must be UNCHANGED by this function --
    # it must be purely additive. Nothing in the record besides the new
    # field may differ from what was passed in.
    for r in records:
        assert set(r.keys()) - {"shared_region_with_other_gt_tables"} == {"image", "gt_table_anno_id", "matched_region"}
    print("PASS: test_region_reuse_across_two_gt_tables_is_flagged")


def test_multiple_match_mixed_labels_counted_in_effective_loss():
    """Bug B: the ORIGINAL gating_impact.json filter was
    `matched_region and not table_gate_pass`, which is None for every
    MULTIPLE_MATCH record (those populate multiple_match_contributors
    instead -- see phase3_region_matching.py's schema). A MULTIPLE_MATCH
    case classify_stage() stages as D2 would therefore silently vanish
    from Phase 7's effective_loss count while still appearing in Phase 5's
    mechanism_d_population.json (which counts _stage=='D2' directly) --
    the two artifacts would disagree. The fix defines effective_loss
    directly from _stage=='D2', which by construction cannot miss any
    verdict shape."""
    rec = {
        "verdict": "MULTIPLE_MATCH",
        "matched_region": None,  # MULTIPLE_MATCH records NEVER populate this -- the crux of the bug
        "multiple_match_contributors": [
            {"region_index": 2, "internal_label_raw": "table", "table_gate_pass": True, "final_ir_element_type": "table"},
            {"region_index": 5, "internal_label_raw": "picture", "table_gate_pass": False, "final_ir_element_type": "image"},
        ],
        "final_table_object": None,
    }

    stage, detail = p4.classify_stage(rec)
    assert stage == "D2", f"a MULTIPLE_MATCH with a non-gated fragment must stage as D2, got {stage} ({detail})"

    # Reconstruct the OLD buggy filter exactly as it was before the fix and
    # prove it excludes this record -- this is the failure this test guards.
    old_buggy_wrong_label_recs = [r for r in [rec] if r["matched_region"] and not r["matched_region"]["table_gate_pass"]]
    assert old_buggy_wrong_label_recs == [], (
        "sanity check: the OLD filter must indeed miss this record (matched_region is None for "
        "MULTIPLE_MATCH) -- if this assertion ever fails, the 'old buggy behavior' this test "
        "documents no longer matches phase4_9_14_funnel.py's git history and the test itself needs updating"
    )

    # The FIXED definition: effective_loss is every record with _stage == "D2",
    # regardless of verdict shape -- must include this record.
    rec["_stage"] = stage
    fixed_effective_loss = [r for r in [rec] if r.get("_stage") == "D2"]
    assert fixed_effective_loss == [rec], "fixed effective_loss must include the MULTIPLE_MATCH D2 case the old filter missed"
    print("PASS: test_multiple_match_mixed_labels_counted_in_effective_loss")


def test_multiple_match_all_gated_is_not_d2():
    """Negative control: a MULTIPLE_MATCH where EVERY fragment IS
    table-labelled must not be D2 (no label error occurred) -- staged D0
    or D6 depending on structural validity, never D2. Guards against an
    over-broad fix that flags every MULTIPLE_MATCH as D2 regardless of
    labels."""
    rec_valid = {
        "verdict": "MULTIPLE_MATCH", "matched_region": None,
        "multiple_match_contributors": [
            {"region_index": 1, "internal_label_raw": "table", "table_gate_pass": True, "final_ir_element_type": "table"},
            {"region_index": 2, "internal_label_raw": "table", "table_gate_pass": True, "final_ir_element_type": "table"},
        ],
        "final_table_object": {"n_rows": 3, "n_cols": 2, "bbox": {"x0": 0, "y0": 0, "x1": 100, "y1": 100},
                                "cells": [{"bbox": {"x0": 0, "y0": 0, "x1": 50, "y1": 50}, "text": "a"}]},
    }
    stage, _ = p4.classify_stage(rec_valid)
    assert stage in ("D0", "D6"), f"all-gated MULTIPLE_MATCH must never be D2, got {stage}"
    assert stage != "D2"
    print("PASS: test_multiple_match_all_gated_is_not_d2")


def test_empty_raw_table_list_is_not_missing_data():
    """Bug C: [] means the specialist ran and found no table; None means
    the raw artifact is unavailable.  The funnel must keep D4/D5 distinct."""
    base = {
        "verdict": "EXACT_MATCH",
        "matched_region": _matched_region(1, "table", True),
        "top_candidates": [{"region_index": 1, "bbox": {"x0": 0, "y0": 0, "x1": 100, "y1": 100}}],
        "final_table_object": None,
    }
    empty = {**base, "_tables_raw_for_page": []}
    missing = {**base, "_tables_raw_for_page": None}
    assert p4.classify_stage(empty)[0] == "D4"
    assert p4.classify_stage(missing)[0] == "D5"
    print("PASS: test_empty_raw_table_list_is_not_missing_data")


def test_incomplete_page_run_is_rejected():
    """An interrupted page must not enter any phase as a valid run."""
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp) / "page-interrupted"
        (run_dir / "layout").mkdir(parents=True)
        (run_dir / "final").mkdir()
        (run_dir / "metadata.json").write_text("{}")
        (run_dir / "layout" / "page-001.json").write_text("{}")
        assert ml.load_page_run(run_dir) is None
    print("PASS: test_incomplete_page_run_is_rejected")


def test_recovery_roots_are_discovered():
    """Recovered batches belong to the same analytical population as the
    original chunk trees and must be discoverable without manual merging."""
    with tempfile.TemporaryDirectory() as tmp:
        experiment_dir = Path(tmp)
        for relative in (
            "results/gt_tables_chunk0/_doc_extraction_runs",
            "results/gt_tables_chunk0_recovery/batch1/_doc_extraction_runs",
            "results/gt_tables_chunk0_recovery/batch0/_doc_extraction_runs",
            "results/gt_tables_chunk1/_doc_extraction_runs",
        ):
            (experiment_dir / relative).mkdir(parents=True)
        roots = ml.gt_table_run_roots(experiment_dir)
        assert [p.relative_to(experiment_dir).as_posix() for p in roots] == [
            "results/gt_tables_chunk0/_doc_extraction_runs",
            "results/gt_tables_chunk0_recovery/batch0/_doc_extraction_runs",
            "results/gt_tables_chunk0_recovery/batch1/_doc_extraction_runs",
            "results/gt_tables_chunk1/_doc_extraction_runs",
        ]
    print("PASS: test_recovery_roots_are_discovered")


def test_recovery_root_comes_from_passed_validation_not_interrupted_attempt():
    """A preserved interrupted attempt must not enter Phase 3 just because
    its directory happens to be named batch<N>. The PASS validation is the
    source of truth and may designate a separate retry root."""
    with tempfile.TemporaryDirectory() as tmp:
        experiment_dir = Path(tmp)
        (experiment_dir / "results/gt_tables_chunk0_recovery/batch7/_doc_extraction_runs").mkdir(parents=True)
        retry_root = experiment_dir / "results/gt_tables_chunk0_recovery/batch7_retry0/_doc_extraction_runs"
        retry_root.mkdir(parents=True)
        (experiment_dir / "recovery_batches_manifest.json").write_text(
            '{"batches": [{"batch_index": 7}]}'
        )
        (experiment_dir / "batch7_validation.json").write_text(
            '{"PASS": true, "runs_dir": "results/gt_tables_chunk0_recovery/batch7_retry0/_doc_extraction_runs"}'
        )
        roots = ml.gt_table_run_roots(experiment_dir, source_names=("chunk0",))
        assert roots == [retry_root]
    print("PASS: test_recovery_root_comes_from_passed_validation_not_interrupted_attempt")


def test_phase13_roots_exclude_unvalidated_resume_attempts():
    """Phase 13 must keep valid original pages but ingest resumed pages only
    from roots selected by a PASS validation, never from an interrupted root."""
    with tempfile.TemporaryDirectory() as tmp:
        experiment_dir = Path(tmp)
        original = experiment_dir / "results/non_table_sample/_doc_extraction_runs"
        original.mkdir(parents=True)
        interrupted = experiment_dir / "results/non_table_sample_recovery/batch0/_doc_extraction_runs"
        interrupted.mkdir(parents=True)
        retry = experiment_dir / "results/non_table_sample_recovery/batch0_retry0/_doc_extraction_runs"
        retry.mkdir(parents=True)
        (experiment_dir / "non_table_recovery_batches_manifest.json").write_text(
            '{"batches": [{"batch_index": 0}]}'
        )
        (experiment_dir / "non_table_batch0_validation.json").write_text(
            '{"PASS": true, "runs_dir": "results/non_table_sample_recovery/batch0_retry0/_doc_extraction_runs"}'
        )
        assert ml.phase13_run_roots(experiment_dir) == [original, retry]
    print("PASS: test_phase13_roots_exclude_unvalidated_resume_attempts")


def main():
    test_region_reuse_across_two_gt_tables_is_flagged()
    test_multiple_match_mixed_labels_counted_in_effective_loss()
    test_multiple_match_all_gated_is_not_d2()
    test_empty_raw_table_list_is_not_missing_data()
    test_incomplete_page_run_is_rejected()
    test_recovery_roots_are_discovered()
    test_recovery_root_comes_from_passed_validation_not_interrupted_attempt()
    test_phase13_roots_exclude_unvalidated_resume_attempts()
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
