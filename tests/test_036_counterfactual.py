from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from PIL import Image

from doc_extraction.backends.table_backend import TableTransformerBackend
from doc_extraction.pipelines.base import PageInput
from doc_extraction.schemas.element import BBox
from doc_extraction.schemas.table import Cell, Table


def test_counterfactual_crop_keeps_exact_crop_and_translates_detector_boxes(tmp_path):
    image = tmp_path / "page.png"
    Image.new("RGB", (100, 100), "white").save(image)
    backend = TableTransformerBackend()
    backend.is_available = lambda: True
    backend._lazy_load = lambda: None
    backend._detect_tables = lambda crop: [BBox(x0=1, y0=2, x1=11, y1=12)]

    def recognize(crop, bbox, page_index, table_id):
        return Table(
            id=table_id, bbox=bbox, page_number=page_index + 1, n_rows=1, n_cols=1,
            cells=[Cell(row=0, col=0, bbox=bbox)], source_backend="table_transformer",
        )

    backend._recognize_structure = recognize
    crop = BBox(x0=10, y0=20, x1=60, y1=80)
    result = backend.extract_crop_counterfactual(
        PageInput(page_index=0, width=100, height=100, image_path=image), crop, "test"
    )
    assert result.forced_crop_table.bbox == crop
    assert result.detected_boxes == [BBox(x0=11, y0=22, x1=21, y1=32)]
    assert result.detector_tables[0].bbox == BBox(x0=11, y0=22, x1=21, y1=32)


def test_036_manifest_contains_exact_frozen_population_and_control_count():
    root = Path(__file__).resolve().parents[1]
    spec = spec_from_file_location("build036", root / "experiments/036_mechanism_d_counterfactual/build_manifest.py")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.is_strict_d2({
        "verdict": "EXACT_MATCH", "matched_region": {"table_gate_pass": False}, "final_table_object": None,
    })
    assert module.is_strict_d2({
        "verdict": "MULTIPLE_MATCH", "multiple_match_contributors": [{"table_gate_pass": True}, {"table_gate_pass": False}],
    })
    assert not module.is_strict_d2({
        "verdict": "EXACT_MATCH", "matched_region": {"table_gate_pass": True}, "final_table_object": None,
    })


def test_036_structural_validation_and_output_root_are_isolated():
    root = Path(__file__).resolve().parents[1]
    spec = spec_from_file_location("run036", root / "experiments/036_mechanism_d_counterfactual/run_counterfactual.py")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    valid = {
        "n_rows": 1, "n_cols": 1, "bbox": {"x0": 0, "y0": 0, "x1": 10, "y1": 10},
        "cells": [{"bbox": {"x0": 0, "y0": 0, "x1": 10, "y1": 10}}],
    }
    escaped = {**valid, "cells": [{"bbox": {"x0": -2, "y0": 0, "x1": 10, "y1": 10}}]}
    assert module.structural_validity(valid)["valid"] is True
    assert module.structural_validity(escaped)["valid"] is False
    assert "036_mechanism_d_counterfactual/results" in (root / ".gitignore").read_text()


def test_036_recovery_thresholds_are_inclusive_for_gt_and_exclusive_for_conflict(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    spec = spec_from_file_location("run036", root / "experiments/036_mechanism_d_counterfactual/run_counterfactual.py")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    forced = {
        "n_rows": 1, "n_cols": 1, "bbox": {"x0": 0, "y0": 0, "x1": 10, "y1": 10},
        "cells": [{"bbox": {"x0": 0, "y0": 0, "x1": 10, "y1": 10}}],
    }
    values = iter((0.1, 0.3, 0.11))  # production overlap, GT IoU, owner IoU
    monkeypatch.setattr(module, "iou", lambda *_: next(values))
    outcome = module.assess_forced_crop(forced, forced["bbox"], forced["bbox"], [{"bbox": forced["bbox"]}])
    assert outcome["ownership_established_in_isolated_counterfactual"] is True
    assert outcome["duplicate_ownership"] is False
    assert outcome["valid_recovery"] is True

    values = iter((0.100001, 0.3, 0.11))
    monkeypatch.setattr(module, "iou", lambda *_: next(values))
    conflict = module.assess_forced_crop(forced, forced["bbox"], forced["bbox"], [{"bbox": forced["bbox"]}])
    assert conflict["duplicate_ownership"] is True
    assert conflict["valid_recovery"] is False


def test_036_structural_escape_boundary_is_not_valid():
    root = Path(__file__).resolve().parents[1]
    spec = spec_from_file_location("run036", root / "experiments/036_mechanism_d_counterfactual/run_counterfactual.py")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    table = {
        "n_rows": 1, "n_cols": 5, "bbox": {"x0": 0, "y0": 0, "x1": 10, "y1": 10},
        "cells": [{"bbox": {"x0": -2 if index == 0 else 0, "y0": 0, "x1": 10, "y1": 10}} for index in range(5)],
    }
    assert module.structural_validity(table)["valid"] is False
