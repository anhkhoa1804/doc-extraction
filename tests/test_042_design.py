"""Pre-execution safety tests for Experiment 042."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
E042 = ROOT / "experiments" / "042_doclaynet_disjoint_scout"


def load_builder():
    spec = importlib.util.spec_from_file_location("build_042_scout", E042 / "build_scout_manifest.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def read_json(name: str):
    return json.loads((E042 / name).read_text(encoding="utf-8"))


def test_scout_design_is_development_only_and_treatment_free():
    protocol = read_json("protocol.json")
    assert protocol["allowed_split"] == "development"
    assert protocol["heldout_accessed"] is False
    assert protocol["scout_selection"]["uses_table_annotations_for_selection"] is False
    assert protocol["scout_selection"]["uses_treatment_output_for_selection"] is False
    assert protocol["treatment"]["executed_in_042"] is False


def test_builder_guard_rejects_heldout_records():
    builder = load_builder()
    with pytest.raises(RuntimeError, match="non-development"):
        builder.require_development({"split": "heldout"})
    with pytest.raises(RuntimeError, match="non-development"):
        builder.require_development({"split": "held_out_test"})


def test_population_builder_is_deterministic_and_frozen_to_development(tmp_path):
    builder = load_builder()
    first_path = tmp_path / "first.json"
    second_path = tmp_path / "second.json"
    first = builder.build(first_path)
    second = builder.build(second_path)
    assert first["population_hash"] == second["population_hash"]
    assert first_path.read_bytes() == second_path.read_bytes()
    assert first["status"] == "SCOUT_DESIGN_FROZEN_ACQUISITION_PENDING"
    assert first["selection"]["selected_groups"] == 40
    assert first["selection"]["selected_pages"] == 279
    assert all(record["split"] == "development" for record in first["records"])
    assert len({record["source_group"] for record in first["records"]}) == 40
    assert len({record["unit_id"] for record in first["records"]}) == 279


def test_population_builder_excludes_prior_doclaynet_groups_and_images(tmp_path):
    builder = load_builder()
    payload = builder.build(tmp_path / "population.json")
    exclusion = payload["identity_exclusion"]
    selected_groups = {record["source_group"] for record in payload["records"]}
    selected_images = {record["image_id"] for record in payload["records"]}
    prior_records = (
        builder.prior_doclaynet_records(builder.E038 / "population_manifest.json")
        + builder.prior_doclaynet_records(builder.E039 / "population_manifest.json")
    )
    prior_groups = {str(record["doc_group"]) for record in prior_records if record.get("doc_group")}
    prior_images = {int(record["image_id"]) for record in prior_records if record.get("image_id") is not None}
    assert exclusion["039_heldout_included_in_exclusion_set"] is True
    assert not selected_groups & prior_groups
    assert not selected_images & prior_images


def test_selection_contract_has_no_gt_or_treatment_dependency():
    builder_source = (E042 / "build_scout_manifest.py").read_text(encoding="utf-8")
    protocol = read_json("protocol.json")
    assert "raw[\"annotations\"]" not in builder_source
    assert "treatment" not in builder_source.lower().replace("uses_treatment_output", "")
    assert protocol["scout_selection"]["uses_table_annotations_for_selection"] is False
    assert protocol["scout_selection"]["uses_treatment_output_for_selection"] is False


def test_natural_role_and_role_normalization_contracts_are_explicit():
    control_doc = (E042 / "CONTROL_POPULATION.md").read_text(encoding="utf-8")
    role_doc = (E042 / "ROLE_NORMALIZATION_DESIGN.md").read_text(encoding="utf-8")
    assert "raw role is exactly `document_index`" in control_doc
    assert "Do not relabel" in control_doc
    assert "document_index -> table" in role_doc
    assert "must not invoke TableTransformer" in role_doc
    assert "read GT" in role_doc


def test_role_normalization_is_routing_only_and_modes_are_distinct():
    protocol = read_json("protocol.json")
    assert protocol["role_normalization"]["specialist_invoked"] is False
    assert protocol["role_normalization"]["gt_used"] is False
    assert protocol["invocation_modes"] == ["PAGE_WIDE", "LABELLED_CROP", "NOT_INVOKED"]
    assert len(set(protocol["invocation_modes"])) == 3


def test_atomic_write_and_reproducible_identity_helpers(tmp_path):
    builder = load_builder()
    output = tmp_path / "nested" / "payload.json"
    payload = {"experiment": "042", "records": [1, 2, 3]}
    builder.atomic_write_json(output, payload)
    assert json.loads(output.read_text(encoding="utf-8")) == payload
    assert builder.stable_hash("042-page-v1", 123) == builder.stable_hash("042-page-v1", 123)
    assert builder.stable_hash("042-page-v1", 123) != builder.stable_hash("042-page-v1", 124)
    assert not list(output.parent.glob(f".{output.name}.*"))


def test_no_039_heldout_can_enter_scout_population(tmp_path):
    builder = load_builder()
    payload = builder.build(tmp_path / "population.json")
    assert payload["split_guard"]["heldout_accessed"] is False
    assert all(record["split"] == "development" for record in payload["records"])
    assert payload["identity_exclusion"]["source_group_overlap"] == 0
    assert payload["identity_exclusion"]["image_id_overlap"] == 0
