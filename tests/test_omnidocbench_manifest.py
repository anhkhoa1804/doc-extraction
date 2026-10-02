from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from benchmarks.scripts.build_omnidocbench_manifest import (
    build_manifest,
    stratified_indices,
    verify_manifest,
)


def _records() -> list[dict]:
    records = []
    for i in range(12):
        records.append({
            "page_info": {
                "image_path": f"page-{i}.png",
                "page_no": i,
                "width": 20,
                "height": 30,
                "page_attribute": {
                    "data_source": "book" if i < 6 else "exam_paper",
                    "language": "english" if i % 2 else "simplified_chinese",
                    "layout": "single_column" if i % 3 else "double_column",
                    "subset": "v1.5" if i < 10 else "table_hard",
                    "special_issue": ["fuzzy_scan"] if i == 11 else [],
                },
            },
            "layout_dets": [
                {"anno_id": 0, "category_type": "text_block"},
                *([{"anno_id": 1, "category_type": "table"}] if i % 2 else []),
                *([{"anno_id": 2, "category_type": "equation_isolated"}] if i % 3 else []),
            ],
            "extra": {"relation": []},
        })
    return records


def _dataset(tmp_path: Path, oversized_indexes: set[int] | None = None) -> Path:
    root = tmp_path / "dataset"
    (root / "images").mkdir(parents=True)
    records = _records()
    oversized_indexes = oversized_indexes or set()
    for index, record in enumerate(records):
        name = record["page_info"]["image_path"]
        size = (30, 30) if index in oversized_indexes else (20, 30)
        Image.new("RGB", size, "white").save(root / "images" / name)
    (root / "OmniDocBench.json").write_text(json.dumps(records), encoding="utf-8")
    return root


def test_stratification_is_deterministic_and_covers_source_and_special_labels():
    records = _records()
    selected_a, composition_a = stratified_indices(records, target=8, seed=7)
    selected_b, composition_b = stratified_indices(records, target=8, seed=7)
    assert selected_a == selected_b
    assert composition_a == composition_b
    assert len(selected_a) == len(set(selected_a)) == 8
    assert composition_a["selected_counts"]["source:book"] > 0
    assert composition_a["selected_counts"]["source:exam_paper"] > 0
    assert composition_a["selected_counts"]["special:fuzzy_scan"] > 0


def test_manifest_hash_and_dataset_pairing_are_reproducible(tmp_path):
    dataset = _dataset(tmp_path)
    output = tmp_path / "manifest.json"
    manifest = build_manifest(dataset, target=8, seed=12)
    output.write_text(json.dumps(manifest), encoding="utf-8")
    indices_a, records_a, verified = verify_manifest(dataset, output)
    indices_b, _composition = stratified_indices(records_a, target=8, seed=12)
    assert indices_a == indices_b
    assert len(records_a) == 12
    assert verified["subset_identity"]["sha256"] == manifest["subset_identity"]["sha256"]


def test_manifest_verification_rejects_changed_selected_image(tmp_path):
    dataset = _dataset(tmp_path)
    output = tmp_path / "manifest.json"
    output.write_text(json.dumps(build_manifest(dataset, target=8, seed=12)), encoding="utf-8")
    (dataset / "images" / "page-0.png").write_bytes(b"changed")
    try:
        verify_manifest(dataset, output)
    except ValueError as exc:
        assert "image inventory hash differs" in str(exc) or "image hash differs" in str(exc)
    else:
        raise AssertionError("modified dataset unexpectedly passed manifest verification")


def test_dangling_truth_relations_are_explicitly_excluded_before_sampling(tmp_path):
    dataset = _dataset(tmp_path)
    gt = dataset / "OmniDocBench.json"
    records = json.loads(gt.read_text(encoding="utf-8"))
    records[0]["extra"]["relation"] = [
        {"source_anno_id": 999, "target_anno_id": 0, "relation_type": "truncated"}
    ]
    gt.write_text(json.dumps(records), encoding="utf-8")

    manifest = build_manifest(dataset, target=8, seed=12)
    assert manifest["dataset_identity"]["integrity_summary"]["dangling_relation_records"] == 1
    assert manifest["dataset_identity"]["integrity_summary"]["dangling_relation_endpoints"] == 1
    exclusions = manifest["subset"]["eligibility_exclusions"]
    assert [item["dataset_index"] for item in exclusions] == [0]
    assert 0 not in {item["dataset_index"] for item in manifest["subset"]["samples"]}


def test_policy_aware_population_separates_rejections_before_sampling(tmp_path):
    dataset = _dataset(tmp_path, oversized_indexes={1, 4, 9})
    manifest = build_manifest(
        dataset,
        target=6,
        seed=22,
        max_image_pixels=600,
        policy_config="cpu.yaml",
        policy_config_sha256="config-hash",
    )
    output = tmp_path / "v2.json"
    output.write_text(json.dumps(manifest), encoding="utf-8")

    policy = manifest["production_policy"]
    selected = manifest["subset"]["samples"]
    assert policy["coverage_population_count"] == 12
    assert policy["policy_rejected_count"] == 3
    assert policy["policy_eligible_count"] == 9
    assert {item["dataset_index"] for item in policy["rejections"]} == {1, 4, 9}
    assert not ({item["dataset_index"] for item in selected} & {1, 4, 9})
    assert verify_manifest(dataset, output)[0] == [item["dataset_index"] for item in selected]


def test_policy_aware_manifest_is_deterministic(tmp_path):
    dataset = _dataset(tmp_path, oversized_indexes={2, 8})
    kwargs = {"target": 7, "seed": 22, "max_image_pixels": 600, "policy_config": "cpu.yaml"}
    first = build_manifest(dataset, **kwargs)
    second = build_manifest(dataset, **kwargs)
    assert first == second


def test_policy_aware_verifier_rejects_selected_oversized_image(tmp_path):
    dataset = _dataset(tmp_path, oversized_indexes={2})
    manifest = build_manifest(dataset, target=7, seed=22, max_image_pixels=600)
    output = tmp_path / "v2.json"
    output.write_text(json.dumps(manifest), encoding="utf-8")
    value = json.loads(output.read_text(encoding="utf-8"))
    rejected = value["production_policy"]["rejections"].pop()
    value["subset"]["samples"].append({
        "dataset_index": rejected["dataset_index"],
        "sample_id": rejected["sample_id"],
        "page_id": rejected["page_id"],
        "page_no": rejected["page_no"],
        "image_path": f"images/{rejected['image_name']}",
        "image_name": rejected["image_name"],
        "image_sha256": rejected["image_sha256"],
        "image_dimensions": {"width": rejected["width"], "height": rejected["height"], "pixels": rejected["pixels"]},
        "page_attribute": {},
        "annotation_counts": {},
    })
    value["subset"]["actual_size"] += 1
    body = {key: item for key, item in value.items() if key != "subset_identity"}
    from benchmarks.scripts.build_omnidocbench_manifest import canonical_sha256

    value["subset_identity"]["sha256"] = canonical_sha256(body)
    output.write_text(json.dumps(value), encoding="utf-8")
    try:
        verify_manifest(dataset, output)
    except ValueError as exc:
        assert "policy rejection population" in str(exc) or "policy-ineligible" in str(exc)
    else:
        raise AssertionError("policy-ineligible sample unexpectedly passed manifest verification")
