#!/usr/bin/env python3
"""Freeze an outcome-independent, source-group-disjoint 042 scout cohort."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
E038 = ROOT / "experiments/038_independent_real_corpus"
E039 = ROOT / "experiments/039_larger_real_corpus"
SOURCE = E039 / "results/doclaynet/val.json"
EXPECTED_SOURCE_SHA256 = "eacd2ba2a32e6c2ebe2dc5ea1545f405d8461c46bba53e0c35d9c54fba0bcef6"
SCOUT_GROUP_COUNT = 40
MAX_PAGES_PER_GROUP = 10
DEVELOPMENT = "development"
HELDOUT = frozenset({"heldout", "held_out", "held_out_test", "test"})


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stable_hash(prefix: str, *parts: object) -> str:
    return hashlib.sha256((prefix + "::" + "::".join(str(part) for part in parts)).encode()).hexdigest()


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def git_head() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def require_development(record: dict[str, Any]) -> None:
    if record.get("split") != DEVELOPMENT:
        raise RuntimeError(f"042 refuses non-development record: split={record.get('split')!r}")


def group_key(image: dict[str, Any]) -> tuple[str, str, str]:
    return (str(image.get("doc_category", "")), str(image.get("collection", "")), str(image.get("doc_name", "")))


def source_group_id(group: tuple[str, str, str]) -> str:
    return "::".join((group[1], group[2]))


def prior_doclaynet_records(path: Path) -> list[dict[str, Any]]:
    return read(path).get("records", [])


def build(output: Path = HERE / "population_manifest.json") -> dict[str, Any]:
    if sha256_path(SOURCE) != EXPECTED_SOURCE_SHA256:
        raise RuntimeError("source DocLayNet annotation hash changed")
    raw = read(SOURCE)
    images = [image for image in raw["images"] if image.get("precedence", 0) == 0]

    # This set is identity-only.  It includes every 039 group, including its
    # held-out groups, so the candidate space can never admit the 039 holdout.
    prior_records = (
        prior_doclaynet_records(E038 / "population_manifest.json")
        + prior_doclaynet_records(E039 / "population_manifest.json")
    )
    excluded_groups = {str(item["doc_group"]) for item in prior_records if item.get("doc_group")}
    excluded_image_ids = {int(item["image_id"]) for item in prior_records if item.get("image_id") is not None}

    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for image in images:
        group = group_key(image)
        if source_group_id(group) in excluded_groups or int(image["id"]) in excluded_image_ids:
            continue
        grouped[group].append(image)
    ranked_groups = sorted(grouped, key=lambda group: stable_hash("042-group-v1", *group))
    selected_groups = ranked_groups[:SCOUT_GROUP_COUNT]
    if len(selected_groups) != SCOUT_GROUP_COUNT:
        raise RuntimeError(f"expected {SCOUT_GROUP_COUNT} new groups, found {len(selected_groups)}")

    records: list[dict[str, Any]] = []
    for group in selected_groups:
        pages = sorted(grouped[group], key=lambda image: stable_hash("042-page-v1", image["id"]))[:MAX_PAGES_PER_GROUP]
        for image in pages:
            records.append({
                "unit_id": f"scout-{int(image['id'])}",
                "split": DEVELOPMENT,
                "dataset": "DocLayNet",
                "dataset_version": "1.0.0",
                "image_id": int(image["id"]),
                "file_name": image["file_name"],
                "source_document_id": source_group_id(group),
                "source_group": source_group_id(group),
                "doc_category": group[0],
                "collection": group[1],
                "doc_name": group[2],
                "page_no": image["page_no"],
                "width": image["width"],
                "height": image["height"],
                "selection_rationale": "042 deterministic source-group/page hash scout; no GT table annotation used",
                "source_image_sha256": None,
            })
    if len({record["unit_id"] for record in records}) != len(records):
        raise RuntimeError("duplicate 042 scout unit identity")
    if any(record["split"] != DEVELOPMENT for record in records):
        raise RuntimeError("non-development record entered 042 scout")
    selected_source_groups = {record["source_group"] for record in records}
    if selected_source_groups & excluded_groups:
        raise RuntimeError("prior DocLayNet source group entered 042 scout")
    if {record["image_id"] for record in records} & excluded_image_ids:
        raise RuntimeError("prior DocLayNet image entered 042 scout")

    payload: dict[str, Any] = {
        "experiment": "042_doclaynet_disjoint_scout",
        "status": "SCOUT_DESIGN_FROZEN_ACQUISITION_PENDING",
        "created_from_commit": git_head(),
        "population_kind": "development_scout_pages_not_yet_control_population",
        "source": {
            "annotation_path": str(SOURCE.relative_to(ROOT)),
            "annotation_sha256": sha256_path(SOURCE),
            "full_precedence_zero_pages": len(images),
            "full_source_groups": len({source_group_id(group_key(image)) for image in images}),
        },
        "identity_exclusion": {
            "prior_doclaynet_groups": len(excluded_groups),
            "prior_doclaynet_image_ids": len(excluded_image_ids),
            "039_heldout_included_in_exclusion_set": True,
            "source_group_overlap": 0,
            "image_id_overlap": 0,
        },
        "selection": {
            "eligible_groups": len(ranked_groups),
            "eligible_pages": sum(len(grouped[group]) for group in ranked_groups),
            "selected_groups": len(selected_groups),
            "max_pages_per_group": MAX_PAGES_PER_GROUP,
            "selected_pages": len(records),
            "group_hash_prefix": "042-group-v1::",
            "page_hash_prefix": "042-page-v1::",
            "uses_gt_table_annotations": False,
            "uses_treatment_output": False,
        },
        "split_guard": {
            "allowed_split": DEVELOPMENT,
            "heldout_splits_rejected": sorted(HELDOUT),
            "heldout_accessed": False,
        },
        "records": records,
        "population_hash_scope": "canonical manifest content excluding population_hash",
    }
    payload["population_hash"] = canonical_hash(payload)
    atomic_write_json(output, payload)
    return payload


def main() -> int:
    payload = build()
    print(json.dumps({"status": payload["status"], "population_hash": payload["population_hash"], **payload["selection"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
