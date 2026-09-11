#!/usr/bin/env python
"""Audit the frozen 038 DocLayNet slice without running the extractor.

The acquisition script intentionally keeps the large archive out of the
repository.  This audit verifies the compact manifest against the downloaded
annotation member and selected page bytes, and makes the derived group split
explicit without changing the frozen population.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SPLIT_PREFIX = "038-split-v1:"


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def bbox_from_coco(box: list[float]) -> dict[str, float]:
    x, y, width, height = box
    return {"x0": x, "y0": y, "x1": x + width, "y1": y + height}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=HERE / "population_audit.json")
    args = parser.parse_args()

    manifest_path = HERE / "population_manifest.json"
    data_path = HERE / "results" / "doclaynet" / "val.json"
    image_root = HERE / "results" / "doclaynet" / "PNG"
    manifest = json.loads(manifest_path.read_text())
    raw = json.loads(data_path.read_text())
    categories = {item["id"]: item["name"] for item in raw["categories"]}
    annotations = [item for item in raw["annotations"] if item.get("precedence", 0) == 0]
    images = {item["id"]: item for item in raw["images"] if item.get("precedence", 0) == 0}

    tables_by_image: dict[int, list[dict]] = defaultdict(list)
    for annotation in annotations:
        if categories.get(annotation["category_id"]) == "Table":
            tables_by_image[annotation["image_id"]].append(annotation)

    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for image in images.values():
        if image["id"] in tables_by_image:
            group = (image.get("collection", ""), image["doc_name"])
            groups[group].append(image)
    eligible = {group: sorted(rows, key=lambda row: row["page_no"])
                for group, rows in groups.items() if len(rows) >= 3}
    ranked = sorted(
        eligible,
        key=lambda group: hashlib.sha256(
            (SPLIT_PREFIX + "::".join(group)).encode()
        ).hexdigest(),
    )
    chosen = ranked[:20]
    expected_groups = ["::".join(group) for group in chosen]
    actual_groups = list(dict.fromkeys(item["doc_group"] for item in manifest["records"]))

    errors: list[str] = []
    if actual_groups != expected_groups:
        errors.append("manifest group order does not reproduce the frozen ranking")
    if len(manifest["records"]) != len({item["image_id"] for item in manifest["records"]}):
        errors.append("duplicate image_id in manifest")
    if len(manifest["records"]) != len({item["file_name"] for item in manifest["records"]}):
        errors.append("duplicate file_name in manifest")
    if digest(data_path) != manifest["annotation_sha256"]:
        errors.append("annotation member SHA-256 mismatch")

    records = []
    missing = 0
    mismatched = 0
    annotation_mismatches = 0
    manifest_group_rank = {group: index for index, group in enumerate(expected_groups)}
    for item in manifest["records"]:
        image_path = image_root / item["file_name"]
        local_exists = image_path.is_file()
        local_hash = digest(image_path) if local_exists else None
        if not local_exists:
            missing += 1
        elif local_hash != item["image_sha256"]:
            mismatched += 1
        source = images.get(item["image_id"])
        source_tables = tables_by_image.get(item["image_id"], [])
        if source is None or source.get("file_name") != item["file_name"]:
            annotation_mismatches += 1
        if [table["id"] for table in source_tables] != [table["id"] for table in item["tables"]]:
            annotation_mismatches += 1
        group_rank = manifest_group_rank.get(item["doc_group"])
        records.append({
            "image_id": item["image_id"],
            "file_name": item["file_name"],
            "doc_group": item["doc_group"],
            "group_rank": group_rank,
            "split": "development" if group_rank is not None and group_rank < 10 else "held_out_test",
            "page_no": item["page_no"],
            "role": item["role"],
            "n_tables": len(item["tables"]),
            "local_exists": local_exists,
            "local_sha256": local_hash,
        })

    if missing or mismatched or annotation_mismatches:
        errors.append(
            f"local/source integrity failures: missing={missing}, "
            f"image_hash={mismatched}, annotation_links={annotation_mismatches}"
        )

    current_names = {item["file_name"] for item in manifest["records"]}
    previous_035 = json.loads(
        (ROOT / "experiments/035_mechanism_d_gating/table_region_matching.json").read_text()
    )
    previous_036 = json.loads(
        (ROOT / "experiments/036_mechanism_d_counterfactual/population_manifest.json").read_text()
    )
    previous_035_names = {item.get("image") for item in previous_035["records"]}
    previous_036_names = {
        item.get("image")
        for section in ("treatment_cases", "control_cases")
        for item in previous_036[section]
    }
    overlap_035 = sorted(current_names & previous_035_names)
    overlap_036 = sorted(current_names & previous_036_names)
    if overlap_035 or overlap_036:
        errors.append(
            f"prior identity overlap: 035={len(overlap_035)}, 036={len(overlap_036)}"
        )

    # This is a derived audit artifact, not a treatment result.  It records
    # the split explicitly because the frozen acquisition manifest stores the
    # selected groups in ranked order rather than repeating split on every row.
    payload = {
        "experiment": manifest["experiment"],
        "status": "population_audited" if not errors else "population_audit_failed",
        "manifest_sha256": digest(manifest_path),
        "annotation_sha256": digest(data_path),
        "acquisition_script_sha256": digest(HERE / "acquire_doclaynet.py"),
        "dataset": {
            "name": manifest["dataset"],
            "version": manifest["dataset_version"],
            "split": manifest["split"],
            "license": "CDLA-Permissive-1.0",
            "archive_url": manifest["archive_url"],
            "archive_sha256": None,
            "archive_hash_note": "archive was not retained; annotation and selected image member hashes are retained",
        },
        "population": {
            "records": len(records),
            "groups": len(expected_groups),
            "development_groups": 10,
            "held_out_groups": 10,
            "table_pages": sum(item["n_tables"] > 0 for item in records),
            "tables": sum(item["n_tables"] for item in records),
            "non_table_control_pages": sum(item["role"] == "non_table_control_page" for item in records),
            "group_order": expected_groups,
        },
        "integrity": {
            "errors": errors,
            "missing_images": missing,
            "image_hash_mismatches": mismatched,
            "annotation_link_mismatches": annotation_mismatches,
            "prior_identity_overlap": {
                "035_filename_overlap": overlap_035,
                "036_filename_overlap": overlap_036,
            },
        },
        "records": records,
    }
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"status": payload["status"], "errors": errors, "records": len(records)}))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
