import json
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT = ROOT / "experiments/038_independent_real_corpus"


def load_module(name: str, path: Path):
    spec = spec_from_file_location(name, path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_038_population_audit_is_frozen_and_integrity_clean():
    audit = json.loads((EXPERIMENT / "population_audit.json").read_text())
    assert audit["status"] == "population_audited"
    assert audit["population"]["records"] == 149
    assert audit["population"]["groups"] == 20
    assert audit["population"]["development_groups"] == 10
    assert audit["population"]["held_out_groups"] == 10
    assert audit["population"]["tables"] == 137
    assert audit["integrity"]["errors"] == []
    assert audit["integrity"]["missing_images"] == 0
    assert audit["integrity"]["image_hash_mismatches"] == 0
    assert audit["integrity"]["annotation_link_mismatches"] == 0
    assert audit["integrity"]["prior_identity_overlap"] == {
        "035_filename_overlap": [],
        "036_filename_overlap": [],
    }


def test_038_baseline_is_pre_treatment_and_blocked_for_policy_selection():
    summary = json.loads((EXPERIMENT / "summary.json").read_text())
    analysis = json.loads((EXPERIMENT / "baseline_analysis.json").read_text())
    assert summary["status"] == "038_BLOCKED_INADEQUATE_DEVELOPMENT"
    assert analysis["baseline"]["forced_crop_invocations"] == 0
    assert analysis["strict_d2_counts"] == {"all": 18, "development": 6, "held_out_test": 12}
    assessment = analysis["development_activation_assessment"]
    assert assessment["source_group_count"] == 2
    assert assessment["raw_labels"] == ["document_index"]
    assert assessment["policy_selection_status"] == "038_BLOCKED_INADEQUATE_DEVELOPMENT"
    assert summary["decision"]["held_out_policy_evaluation"] is False


def test_038_coco_bbox_conversion_preserves_pixel_space():
    module = load_module("analyze038", EXPERIMENT / "analyze_baseline.py")
    assert module.bbox_from_coco([10, 20, 30, 40]) == {
        "x0": 10,
        "y0": 20,
        "x1": 40,
        "y1": 60,
    }
