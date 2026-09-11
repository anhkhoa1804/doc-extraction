from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
E040 = REPO / "experiments" / "040_mechanism_d_counterfactual"
if str(E040) not in sys.path:
    sys.path.insert(0, str(E040))

from protocol import (
    HeldoutAccessError,
    atomic_write_json,
    bbox_equal,
    crop_png_bytes,
    policy_fires,
    pre_treatment_features,
    require_development,
    structure_validity,
)


def load_runner():
    path = E040 / "run_counterfactual.py"
    spec = importlib.util.spec_from_file_location("experiment040_runner", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_runtime_guard_rejects_heldout_before_treatment():
    with pytest.raises(HeldoutAccessError):
        require_development({"unit_id": "heldout", "split": "held_out_test"})
    with pytest.raises(HeldoutAccessError):
        require_development({"unit_id": "missing", "split": None})


def test_exact_bbox_and_crop_identity_are_deterministic(tmp_path):
    from PIL import Image

    image_path = tmp_path / "source.png"
    Image.new("RGB", (40, 30), color=(10, 20, 30)).save(image_path)
    bbox = {"x0": 3.0, "y0": 4.0, "x1": 27.0, "y1": 22.0}
    first, width, height = crop_png_bytes(image_path, bbox)
    second, width2, height2 = crop_png_bytes(image_path, bbox)
    assert first == second
    assert (width, height) == (width2, height2)
    assert bbox_equal(bbox, {"x0": 3, "y0": 4, "x1": 27, "y1": 22})


def test_pre_treatment_features_do_not_accept_gt_or_treatment_fields():
    region = {"label": "document_index", "confidence": None, "source_id": None, "bbox": {"x0": 0, "y0": 0, "x1": 20, "y1": 10}}
    features = pre_treatment_features(
        region=region,
        page_width=100,
        page_height=100,
        region_index=2,
        page_region_count=5,
        ocr_tokens=[{"text": "index", "bbox": {"x0": 1, "y0": 1, "x1": 5, "y1": 4}}],
    )
    assert features["normalized_role"] == "document_index"
    assert features["ocr_child_count"] == 1
    assert "gt_bbox" not in features
    assert "treatment_recovery" not in features
    assert policy_fires(features)["POLICY_1_ROLE_ONLY_DOCUMENT_INDEX"] is True


def test_structure_validity_keeps_frozen_boundary():
    table = {
        "n_rows": 1,
        "n_cols": 1,
        "bbox": {"x0": 0, "y0": 0, "x1": 10, "y1": 10},
        "cells": [{"bbox": {"x0": -1, "y0": 0, "x1": 10, "y1": 10}}],
    }
    assert structure_validity(table)["valid"] is True
    table["cells"][0]["bbox"]["x0"] = -2
    assert structure_validity(table)["valid"] is False


def test_atomic_result_write_never_requires_partial_file(tmp_path):
    path = tmp_path / "nested" / "result.json"
    atomic_write_json(path, {"status": "complete", "records": [1]})
    assert json.loads(path.read_text()) == {"status": "complete", "records": [1]}
    assert not list(path.parent.glob(".*.tmp"))


def test_frozen_population_has_shared_region_unit_and_no_heldout():
    manifest = json.loads((E040 / "population_manifest.json").read_text())
    assert manifest["counts"]["d2_unique_region_units"] == 28
    assert manifest["counts"]["control_region_units"] == 766
    assert manifest["heldout_guard"]["heldout_units"] == 0
    assert all(unit["split"] == "development" for unit in manifest["units"])
    shared = [unit for unit in manifest["units"] if len(unit.get("linked_gt_tables", [])) > 1]
    assert shared
    assert all(unit["kind"] == "d2_region" for unit in shared)


def test_specialist_call_contract_enforces_labelled_crop():
    runner = load_runner()

    class FakeResult:
        def __init__(self):
            self.forced_crop_table = None
            self.detector_tables = []
            self.detected_boxes = []
            self.detected_scores = []
            self.stage_timings = {"forced_structure_seconds": 0.1, "crop_detector_seconds": 0.2, "detector_structure_seconds": []}

    calls = runner.specialist_call_payload(FakeResult())
    assert calls[0]["mode"] == "LABELLED_CROP"
    assert calls[1]["mode"] == "LABELLED_CROP"
    assert all(call["mode"] != "PAGE_WIDE" for call in calls)
