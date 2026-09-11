"""Pure regression checks for the 039 forensic-summary helpers."""

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "experiments/039_larger_real_corpus/forensic_review.py"


def load_review():
    spec = importlib.util.spec_from_file_location("forensic_review_039", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_039_coco_bbox_and_selected_label_are_deterministic():
    review = load_review()
    assert review.bbox_from_coco([10, 20, 30, 40]) == {
        "x0": 10,
        "y0": 20,
        "x1": 40,
        "y1": 60,
    }
    assert review.selected_region_label({
        "matched_region": {"raw_label": "document_index"},
        "matched_regions": [],
    }) == "document_index"
    assert review.selected_region_label({
        "matched_region": None,
        "matched_regions": [{"raw_label": "text"}, {"raw_label": "text"}],
    }) == "<multiple:text>"


def test_039_threshold_summary_is_descriptive_and_does_not_mutate_rows():
    review = load_review()
    rows = [
        {"strict_d2": True, "matched_region": {"ocr_child_count": 0, "region_area_fraction": 0.5, "aspect_ratio": 2, "page_region_count": 2}},
        {"strict_d2": False, "matched_region": {"ocr_child_count": 2, "region_area_fraction": 0.1, "aspect_ratio": 6, "page_region_count": 30}},
    ]
    summary = review.descriptive_thresholds(rows)
    assert summary["ocr_child_count_eq_0"]["d2_rows"] == 1
    assert summary["ocr_child_count_eq_0"]["non_d2_rows"] == 0
    assert rows[0]["strict_d2"] is True
