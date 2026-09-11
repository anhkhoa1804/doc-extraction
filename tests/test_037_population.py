"""Regression locks for the pre-treatment 037 corpus contract."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "experiments/037_selective_policy_validation/population_manifest.json"


def test_037_population_is_document_group_disjoint_and_fixed():
    payload = json.loads(MANIFEST.read_text())
    records = payload["records"]
    assert payload["n_documents"] == 15
    assert payload["split_counts"] == {"development": 7, "held_out_test": 8}
    assert len({r["document_id"] for r in records}) == 15
    assert len({r["source_document_group"] for r in records}) == 15
    assert {r["split"] for r in records} == {"development", "held_out_test"}
    ordered = sorted(records, key=lambda r: hashlib.sha256(
        ("037-split-v1:" + r["document_id"]).encode()).hexdigest())
    assert [r["split"] for r in ordered] == ["development"] * 7 + ["held_out_test"] * 8


def test_037_population_has_only_source_side_table_geometry():
    for record in json.loads(MANIFEST.read_text())["records"]:
        assert record["source_file"].endswith(".pdf")
        assert record["gt_table_id"].endswith(":table:0")
        box = record["source_table_bbox_points"]
        assert box["x0"] < box["x1"] and box["y0"] < box["y1"]
        # No extractor output can appear in the pre-treatment manifest.
        assert not any("detector" in key or "structure" in key or "ownership" in key for key in record)
