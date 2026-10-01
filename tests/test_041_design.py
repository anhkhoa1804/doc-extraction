"""Pre-execution safety tests for Experiment 041."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
E041 = ROOT / "experiments" / "041_role_signal_provenance"


def read(name: str):
    return json.loads((E041 / name).read_text(encoding="utf-8"))


def test_module_a_is_blocked_by_zero_same_role_controls():
    manifest = read("population_manifest.json")
    assert manifest["counts"]["document_index_candidates"] == 15
    assert manifest["counts"]["excluded_frozen_d2_identities"] == 15
    assert manifest["counts"]["eligible_same_role_controls"] == 0
    assert manifest["same_role_control_units"] == []
    assert manifest["treatment_executed"] is False


def test_all_frozen_targets_are_development_and_unique():
    manifest = read("population_manifest.json")
    target_ids = manifest["module_a_d2_target_unit_ids"]
    assert len(target_ids) == 15
    assert len(set(target_ids)) == 15
    assert manifest["split_guard"]["allowed"] == "development"
    assert manifest["split_guard"]["heldout_accessed"] is False


def test_feature_contract_has_no_post_treatment_or_gt_inputs():
    features = read("feature_manifest.json")
    forbidden = set(features["forbidden_features"])
    assert {"gt_bbox", "gt_iou", "treatment_recovery", "post_treatment_ownership"} <= forbidden
    assert features["heldout_accessed"] is False


def test_protocol_keeps_modes_and_modules_separate():
    protocol = read("protocol.json")
    assert protocol["module_a"]["required_invocation_mode"] == "LABELLED_CROP"
    assert protocol["module_b"]["kind"] == "observational_no_treatment_replay"
    assert protocol["module_c"]["kind"] == "offline_routing_only"
    assert protocol["module_c"]["specialist_invoked"] is False
    assert protocol["module_c"]["gt_used"] is False


def test_results_do_not_claim_nonexecution_as_scientific_outcome():
    results = read("results.json")
    assert results["treatment_executed"] is False
    assert results["records"] == []
    assert results["scientific_decision"] == "REFINE_EXPERIMENT"


def test_builder_guard_rejects_heldout_record():
    import importlib.util

    spec = importlib.util.spec_from_file_location("build_041", E041 / "build_population.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    with pytest.raises(RuntimeError, match="non-development"):
        module.require_development({"split": "held_out_test"})
