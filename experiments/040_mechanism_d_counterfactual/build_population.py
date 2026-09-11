#!/usr/bin/env python3
"""Freeze the development-only Experiment 040 population from 039 artifacts."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
E039 = ROOT / "experiments" / "039_larger_real_corpus"
sys.path.insert(0, str(HERE))
from protocol import (
    BASELINE_CHECKPOINT,
    CONTROL_KIND,
    DEVELOPMENT_SPLIT,
    EXPERIMENT_ID,
    TARGET_KIND,
    atomic_write_json,
    bbox_dict,
    canonical_json_hash,
    crop_png_bytes,
    pre_treatment_features,
    require_development,
    sha256_bytes,
    sha256_file,
)


def git_head() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def baseline_dir(image_id: int) -> Path:
    path = E039 / "results" / "baseline_runs" / str(image_id)
    required = [path / item for item in ("metadata.json", "layout/page-001.json", "ocr/page-001.json", "tables/page-001.json", "final/document.json")]
    missing = [str(item) for item in required if not item.is_file()]
    if missing:
        raise RuntimeError(f"incomplete frozen 039 baseline for image {image_id}: {missing}")
    return path


def verify_region(layout: dict[str, Any], index: int, expected_bbox: dict[str, float]) -> dict[str, Any]:
    regions = layout["regions"]
    if index < 0 or index >= len(regions):
        raise RuntimeError(f"region index {index} absent from frozen layout")
    region = regions[index]
    if bbox_dict(region["bbox"]) != bbox_dict(expected_bbox):
        raise RuntimeError(f"frozen region bbox mismatch at index {index}")
    return region


def source_record_lookup(manifest: dict[str, Any]) -> dict[int, dict[str, Any]]:
    result = {int(item["image_id"]): item for item in manifest["records"]}
    if len(result) != len(manifest["records"]):
        raise RuntimeError("duplicate 039 image identity")
    return result


def base_unit(
    *,
    image_id: int,
    record: dict[str, Any],
    run: Path,
    region_index: int,
    region: dict[str, Any],
    kind: str,
    gt_tables: list[dict[str, Any]],
    taxonomy: dict[str, Any] | None,
) -> dict[str, Any]:
    require_development(record)
    image_path = E039 / "results" / "doclaynet" / "PNG" / record["file_name"]
    if sha256_file(image_path) != record["image_sha256"]:
        raise RuntimeError(f"source image hash mismatch for {image_id}")
    final_page = read_json(run / "final/document.json")["pages"][0]
    layout = read_json(run / "layout/page-001.json")
    ocr = read_json(run / "ocr/page-001.json")
    expected = bbox_dict(region["bbox"])
    crop_bytes, crop_width, crop_height = crop_png_bytes(image_path, expected)
    features = pre_treatment_features(
        region=region,
        page_width=float(final_page["width"]),
        page_height=float(final_page["height"]),
        region_index=region_index,
        page_region_count=len(layout["regions"]),
        ocr_tokens=ocr.get("tokens", []),
    )
    unit_id = f"{'d2' if kind == TARGET_KIND else 'control'}-{image_id}-{region_index}"
    baseline_element = next(
        (element for element in final_page.get("elements", []) if element.get("order_index") == region_index),
        None,
    )
    return {
        "unit_id": unit_id,
        "kind": kind,
        "split": record["split"],
        "image_id": image_id,
        "file_name": record["file_name"],
        "source_document_id": record["source_document_id"],
        "doc_group": record["doc_group"],
        "doc_category": record["doc_category"],
        "page_no": record["page_no"],
        "page_index": int(final_page["index"]),
        "source_image_sha256": record["image_sha256"],
        "source_run": str(run.relative_to(ROOT)),
        "source_artifact_sha256": {
            "metadata": sha256_file(run / "metadata.json"),
            "layout": sha256_file(run / "layout/page-001.json"),
            "ocr": sha256_file(run / "ocr/page-001.json"),
            "tables": sha256_file(run / "tables/page-001.json"),
            "final": sha256_file(run / "final/document.json"),
        },
        "page": {
            "width": float(final_page["width"]),
            "height": float(final_page["height"]),
            "dpi": final_page.get("dpi"),
        },
        "region_index": region_index,
        "region_identity": {"image_id": image_id, "region_index": region_index},
        "raw_role": region["label"],
        "region_bbox": expected,
        "crop": {
            "sha256": sha256_bytes(crop_bytes),
            "width": crop_width,
            "height": crop_height,
            "encoding": "PIL RGB PNG bytes using exact baseline bbox",
        },
        "baseline_features": features,
        "baseline_state": {
            "specialist_mode": "NOT_RECORDED_IN_FROZEN_039_BASELINE",
            "element_type": baseline_element.get("type") if baseline_element else None,
            "element_id": baseline_element.get("id") if baseline_element else None,
            "element_table_id": baseline_element.get("table_id") if baseline_element else None,
            "page_table_count": len(final_page.get("tables", [])),
            "page_element_count": len(final_page.get("elements", [])),
            "page_reading_order": list(final_page.get("reading_order", [])),
            "page_notes": list(final_page.get("notes", [])),
            "table_ids": [table["id"] for table in final_page.get("tables", [])],
        },
        "linked_gt_tables": gt_tables,
        "d2_taxonomy": taxonomy,
    }


def build(output: Path) -> dict[str, Any]:
    source_manifest = read_json(E039 / "population_manifest.json")
    source_records = source_record_lookup(source_manifest)
    forensic = read_json(E039 / "039_D2_FORENSIC_CASES.json")
    taxonomy_cases = {
        (int(case["image_id"]), int(case["gt_table_id"])): case
        for case in read_json(E039 / "039_D2_TAXONOMY.json")["cases"]
    }

    d2_rows = [case for case in forensic["cases"] if case.get("strict_d2") and case.get("split") == DEVELOPMENT_SPLIT]
    if len(d2_rows) != 34:
        raise RuntimeError(f"expected 34 development strict-D2 rows, found {len(d2_rows)}")
    units_by_key: dict[tuple[int, int], dict[str, Any]] = {}
    for case in d2_rows:
        image_id = int(case["image_id"])
        record = source_records[image_id]
        run = baseline_dir(image_id)
        matched = case.get("matched_region")
        if matched is None:
            raise RuntimeError(f"D2 row {image_id}/{case['gt_table_id']} has no matched region")
        region_index = int(matched["region_index"])
        layout = read_json(run / "layout/page-001.json")
        region = verify_region(layout, region_index, matched["bbox"])
        key = (image_id, region_index)
        gt = {
            "gt_table_id": int(case["gt_table_id"]),
            "bbox": bbox_dict(case["gt_bbox_px"]),
            "match_verdict": case.get("verdict"),
        }
        if key not in units_by_key:
            tax = taxonomy_cases.get((image_id, int(case["gt_table_id"])))
            units_by_key[key] = base_unit(
                image_id=image_id,
                record=record,
                run=run,
                region_index=region_index,
                region=region,
                kind=TARGET_KIND,
                gt_tables=[gt],
                taxonomy=tax,
            )
        else:
            units_by_key[key]["linked_gt_tables"].append(gt)
            if units_by_key[key]["d2_taxonomy"] is None:
                units_by_key[key]["d2_taxonomy"] = taxonomy_cases.get((image_id, int(case["gt_table_id"])))

    control_units: list[dict[str, Any]] = []
    for record in sorted(source_manifest["records"], key=lambda item: int(item["image_id"])):
        if record["split"] != DEVELOPMENT_SPLIT or record["role"] != "non_table_control_page":
            continue
        image_id = int(record["image_id"])
        run = baseline_dir(image_id)
        if record.get("tables"):
            raise RuntimeError(f"control page {image_id} unexpectedly has GT tables")
        layout = read_json(run / "layout/page-001.json")
        for region_index, region in enumerate(layout["regions"]):
            if str(region.get("label", "")).strip().lower() == "table":
                continue
            box = bbox_dict(region["bbox"])
            if box["x1"] <= box["x0"] or box["y1"] <= box["y0"]:
                continue
            control_units.append(
                base_unit(
                    image_id=image_id,
                    record=record,
                    run=run,
                    region_index=region_index,
                    region=region,
                    kind=CONTROL_KIND,
                    gt_tables=[],
                    taxonomy=None,
                )
            )

    d2_units = sorted(units_by_key.values(), key=lambda unit: (unit["image_id"], unit["region_index"]))
    control_units.sort(key=lambda unit: (unit["image_id"], unit["region_index"]))
    if len(d2_units) != 28:
        raise RuntimeError(f"expected 28 unique development D2 regions, found {len(d2_units)}")
    if len(control_units) != 766:
        raise RuntimeError(f"expected 766 development controls, found {len(control_units)}")

    all_units = d2_units + control_units
    if len({unit["unit_id"] for unit in all_units}) != len(all_units):
        raise RuntimeError("duplicate Experiment 040 unit identity")
    if any(unit["split"] != DEVELOPMENT_SPLIT for unit in all_units):
        raise RuntimeError("held-out unit entered the frozen Experiment 040 population")

    document_index = next(unit for unit in d2_units if unit["baseline_features"]["normalized_role"] == "document_index")
    non_document = next(unit for unit in d2_units if unit["baseline_features"]["normalized_role"] != "document_index")
    pilot_ids = [document_index["unit_id"], non_document["unit_id"], control_units[0]["unit_id"], control_units[1]["unit_id"]]
    payload = {
        "experiment": EXPERIMENT_ID,
        "status": "frozen_development_population",
        "created_from_commit": git_head(),
        "baseline_checkpoint": BASELINE_CHECKPOINT,
        "source": {
            "experiment": source_manifest["experiment"],
            "manifest_sha256": sha256_file(E039 / "population_manifest.json"),
            "annotation_sha256": source_manifest["annotation_sha256"],
            "baseline_index_sha256": sha256_file(E039 / "results" / "baseline_run_index.json"),
        },
        "heldout_guard": {
            "allowed_split": DEVELOPMENT_SPLIT,
            "heldout_splits_rejected_before_treatment": sorted({"heldout", "held_out", "held_out_test", "test"}),
            "heldout_units": 0,
        },
        "counts": {
            "d2_rows_source": 34,
            "d2_unique_region_units": len(d2_units),
            "control_region_units": len(control_units),
            "total_units": len(all_units),
            "d2_source_groups": len({unit["doc_group"] for unit in d2_units}),
            "control_source_groups": len({unit["doc_group"] for unit in control_units}),
            "categories": len({unit["doc_category"] for unit in all_units}),
        },
        "unit_identity": "(kind, image_id, region_index); shared GT annotations remain one d2_region unit",
        "pilot_unit_ids": pilot_ids,
        "units": all_units,
    }
    payload["population_hash"] = canonical_json_hash(payload)
    atomic_write_json(output, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=HERE / "population_manifest.json")
    args = parser.parse_args()
    payload = build(args.output)
    print(json.dumps({"status": payload["status"], "population_hash": payload["population_hash"], **payload["counts"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
