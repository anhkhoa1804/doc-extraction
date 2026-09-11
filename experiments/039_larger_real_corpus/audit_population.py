#!/usr/bin/env python
"""Offline audit for the frozen 039 acquisition checkpoint."""
from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SOURCE = ROOT / "experiments/038_independent_real_corpus/results/doclaynet/val.json"
SPLIT_PREFIX = "039-group-v1:"
TABLE_PAGE_PREFIX = "039-table-page-v1:"
CONTROL_PAGE_PREFIX = "039-control-page-v1:"


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def stable_key(prefix: str, *parts: object) -> str:
    text = prefix + "::" + "::".join(str(part) for part in parts)
    return hashlib.sha256(text.encode()).hexdigest()


def names_from_json(path: Path, *paths: tuple[str, ...]) -> set[str]:
    data = json.loads(path.read_text())
    values = set()
    for path_parts in paths:
        rows = data
        for part in path_parts:
            rows = rows[part]
        for row in rows:
            value = row.get("image") if isinstance(row, dict) else row
            if value:
                values.add(Path(value).name)
    return values


def main() -> int:
    manifest_path = HERE / "population_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    source = json.loads(SOURCE.read_text())
    categories = {item["id"]: item["name"] for item in source["categories"]}
    images = {item["id"]: item for item in source["images"] if item.get("precedence", 0) == 0}
    tables: dict[int, list[dict]] = defaultdict(list)
    for annotation in source["annotations"]:
        if annotation.get("precedence", 0) == 0 and categories.get(annotation["category_id"]) == "Table":
            tables[annotation["image_id"]].append(annotation)

    errors: list[str] = []
    groups: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for image_id, image in images.items():
        if image_id in tables:
            group = (image.get("doc_category", ""), image.get("collection", ""), image["doc_name"])
            groups[group].append(image)
    eligible = {group: rows for group, rows in groups.items() if len(rows) >= 3}
    old_manifest = json.loads(
        (ROOT / "experiments/038_independent_real_corpus/population_manifest.json").read_text()
    )
    old_group_names = {row["doc_group"] for row in old_manifest["records"]}
    old_image_ids = {row["image_id"] for row in old_manifest["records"]}
    remaining = {
        group: rows for group, rows in eligible.items()
        if "::".join(group[1:]) not in old_group_names and not any(row["id"] in old_image_ids for row in rows)
    }
    split_by_group = {}
    for category in sorted({group[0] for group in remaining}):
        ranked = sorted(
            (group for group in remaining if group[0] == category),
            key=lambda group: stable_key(SPLIT_PREFIX, *group),
        )
        for index, group in enumerate(ranked):
            split_by_group[group] = "development" if index < (len(ranked) + 1) // 2 else "held_out_test"

    manifest_ids = {row["image_id"] for row in manifest["records"]}
    if len(manifest["records"]) != len(manifest_ids):
        errors.append("duplicate image_id")
    if len(manifest["records"]) != len({row["file_name"] for row in manifest["records"]}):
        errors.append("duplicate file_name")
    if digest(SOURCE) != manifest["annotation_sha256"]:
        errors.append("annotation SHA-256 mismatch")
    if len(split_by_group) != manifest["split_algorithm"]["development_groups"] + manifest["split_algorithm"]["held_out_groups"]:
        errors.append("split group count mismatch")

    missing = 0
    image_mismatches = 0
    source_mismatches = 0
    for row in manifest["records"]:
        source_image = images.get(row["image_id"])
        image_path = HERE / "results/doclaynet/PNG" / row["file_name"]
        if not image_path.is_file():
            missing += 1
        elif digest(image_path) != row["image_sha256"]:
            image_mismatches += 1
        if not source_image or source_image.get("file_name") != row["file_name"]:
            source_mismatches += 1
        expected_group = (row["doc_category"], row["collection"], row["doc_name"])
        if row["split"] != split_by_group.get(expected_group):
            errors.append(f"split mismatch for image {row['image_id']}")
        if row["role"] == "table_page" and [x["id"] for x in row["tables"]] != [x["id"] for x in tables.get(row["image_id"], [])]:
            errors.append(f"table annotation mismatch for image {row['image_id']}")
        if row["role"] == "non_table_control_page" and row["tables"]:
            errors.append(f"control contains table annotations for image {row['image_id']}")
    if missing or image_mismatches or source_mismatches:
        errors.append(
            f"image/source integrity failures: missing={missing}, "
            f"image_hash={image_mismatches}, source_links={source_mismatches}"
        )

    current_names = {row["file_name"] for row in manifest["records"]}
    prior_035 = names_from_json(ROOT / "experiments/035_mechanism_d_gating/table_region_matching.json", ("records",))
    prior_036 = names_from_json(
        ROOT / "experiments/036_mechanism_d_counterfactual/population_manifest.json",
        ("treatment_cases",), ("control_cases",),
    )
    prior_037 = {
        Path(row["rendered_image"]).name
        for row in json.loads((ROOT / "experiments/037_selective_policy_validation/population_manifest.json").read_text())["records"]
    }
    prior_038 = {row["file_name"] for row in old_manifest["records"]}
    overlaps = {
        "035_filename": sorted(current_names & prior_035),
        "036_filename": sorted(current_names & prior_036),
        "037_filename": sorted(current_names & prior_037),
        "038_filename": sorted(current_names & prior_038),
        "038_image_id": sorted(manifest_ids & old_image_ids),
    }
    for label, values in overlaps.items():
        if values:
            errors.append(f"identity overlap {label}: {len(values)}")

    payload = {
        "experiment": "039_larger_real_corpus",
        "status": "population_audited" if not errors else "population_audit_failed",
        "manifest_sha256": digest(manifest_path),
        "annotation_sha256": digest(SOURCE),
        "population": {
            "records": len(manifest["records"]),
            "groups": len(split_by_group),
            "development_groups": manifest["split_algorithm"]["development_groups"],
            "held_out_groups": manifest["split_algorithm"]["held_out_groups"],
            "table_pages": sum(row["role"] == "table_page" for row in manifest["records"]),
            "control_pages": sum(row["role"] == "non_table_control_page" for row in manifest["records"]),
            "categories": dict(Counter(row["doc_category"] for row in manifest["records"])),
        },
        "integrity": {
            "errors": errors,
            "missing_images": missing,
            "image_hash_mismatches": image_mismatches,
            "source_link_mismatches": source_mismatches,
            "identity_overlaps": overlaps,
        },
    }
    output = HERE / "population_audit.json"
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"status": payload["status"], "errors": errors, "records": len(manifest["records"])}))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
