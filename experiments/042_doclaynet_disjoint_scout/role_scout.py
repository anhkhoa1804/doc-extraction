#!/usr/bin/env python3
"""Perform the cheap, annotation-only 042 role-availability scout."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
POPULATION = HERE / "population_manifest.json"
ANNOTATIONS = ROOT / "experiments/039_larger_real_corpus/results/doclaynet/val.json"
INTEGRITY = HERE / "ACQUISITION_INTEGRITY.json"
EXPECTED_POPULATION_HASH = "4d2ff975ec30d3c5c074bc858620dab856decbcabfdcd751c3861d8cdea0655e"
EXPECTED_ANNOTATION_SHA256 = "eacd2ba2a32e6c2ebe2dc5ea1545f405d8461c46bba53e0c35d9c54fba0bcef6"


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


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


def canonical_population_hash(payload: dict[str, Any]) -> str:
    content = dict(payload)
    content.pop("population_hash", None)
    return hashlib.sha256(
        json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def git_head() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def normalized_source_label(value: str) -> str:
    return "_".join(str(value).strip().casefold().replace("-", " ").split())


def discover_document_index_controls(
    baseline_pages: list[dict[str, Any]],
    excluded_region_ids: set[tuple[int, int]] | frozenset[tuple[int, int]] = frozenset(),
) -> list[dict[str, Any]]:
    """Select natural role candidates from baseline layout records only.

    This pure helper is deliberately independent of source annotations, GT,
    treatment output, and outcomes. ``baseline_pages`` is expected to contain
    the already-emitted layout regions and their pre-treatment features.
    """
    candidates: list[dict[str, Any]] = []
    for page in sorted(baseline_pages, key=lambda item: (str(item.get("source_group", "")), int(item["image_id"]))):
        if page.get("split") != "development":
            raise RuntimeError("042 control discovery refuses non-development page")
        for region in sorted(page.get("regions", []), key=lambda item: int(item["region_index"])):
            identity = (int(page["image_id"]), int(region["region_index"]))
            if identity in excluded_region_ids:
                continue
            if str(region.get("raw_role", "")).strip().lower() != "document_index":
                continue
            if region.get("role_source") != "baseline_layout":
                raise RuntimeError("document_index candidate lacks baseline-layout provenance")
            candidates.append({
                "image_id": int(page["image_id"]),
                "source_group": page["source_group"],
                "doc_category": page.get("doc_category"),
                "region_index": int(region["region_index"]),
                "raw_role": region["raw_role"],
                "normalized_role": str(region["raw_role"]).strip().lower(),
                "bbox": region.get("bbox"),
                "features": dict(region.get("features", {})),
                "selection_source": "baseline_layout_role_only",
            })
    return candidates


def scout() -> dict[str, Any]:
    population = read(POPULATION)
    if population.get("population_hash") != EXPECTED_POPULATION_HASH:
        raise RuntimeError("042 population hash does not match frozen cohort")
    if canonical_population_hash(population) != EXPECTED_POPULATION_HASH:
        raise RuntimeError("042 population hash recomputation failed")
    if any(record.get("split") != "development" for record in population["records"]):
        raise RuntimeError("held-out record entered role scout")
    integrity = read(INTEGRITY)
    if integrity.get("status") != "PASS":
        raise RuntimeError("role scout requires a passing acquisition audit")
    if sha256_path(ANNOTATIONS) != EXPECTED_ANNOTATION_SHA256:
        raise RuntimeError("source annotation hash changed")

    source = read(ANNOTATIONS)
    category_names = {int(item["id"]): str(item["name"]) for item in source["categories"]}
    selected_ids = {int(record["image_id"]) for record in population["records"]}
    selected = {int(image["id"]): image for image in source["images"] if int(image["id"]) in selected_ids}
    if len(selected) != len(selected_ids):
        raise RuntimeError("frozen scout page is missing from source metadata")

    annotations_by_image: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for annotation in source["annotations"]:
        image_id = int(annotation["image_id"])
        if image_id in selected_ids and annotation.get("precedence", 0) == 0:
            annotations_by_image[image_id].append(annotation)

    label_counts: Counter[str] = Counter()
    label_pages: defaultdict[str, set[int]] = defaultdict(set)
    label_groups: defaultdict[str, set[str]] = defaultdict(set)
    table_pages: set[int] = set()
    for image_id, annotations in annotations_by_image.items():
        image = selected[image_id]
        group = f"{image.get('collection', '')}::{image.get('doc_name', '')}"
        for annotation in annotations:
            label = category_names[int(annotation["category_id"])]
            label_counts[label] += 1
            label_pages[label].add(image_id)
            label_groups[label].add(group)
            if label == "Table":
                table_pages.add(image_id)

    exact_index_labels = {"document_index", "document index"}
    source_index_count = sum(
        count for label, count in label_counts.items() if normalized_source_label(label) in exact_index_labels
    )
    source_index_pages = sorted(
        image_id
        for image_id, annotations in annotations_by_image.items()
        if any(normalized_source_label(category_names[int(a["category_id"])]) in exact_index_labels for a in annotations)
    )
    source_index_groups = {
        f"{selected[image_id].get('collection', '')}::{selected[image_id].get('doc_name', '')}"
        for image_id in source_index_pages
    }
    source_index_categories = {
        selected[image_id].get("doc_category") for image_id in source_index_pages
    }

    payload = {
        "experiment": "042_doclaynet_disjoint_scout",
        "status": "CONTROL_SUPPLY_INADEQUATE_BUT_INFORMATIVE",
        "code_commit": git_head(),
        "population_hash": EXPECTED_POPULATION_HASH,
        "source_annotation_sha256": EXPECTED_ANNOTATION_SHA256,
        "heldout_accessed": False,
        "treatment_accessed": False,
        "gt_used_for_control_selection": False,
        "scout_kind": "annotation_only_no_layout_or_table_specialist",
        "population": {
            "pages": len(selected_ids),
            "source_groups": len({record["source_group"] for record in population["records"]}),
            "categories": len({record["doc_category"] for record in population["records"]}),
        },
        "source_annotation": {
            "selected_pages_with_any_precedence_zero_annotation": len(annotations_by_image),
            "selected_pages_with_table_annotation": len(table_pages),
            "category_counts": dict(sorted(label_counts.items())),
            "category_page_counts": {label: len(pages) for label, pages in sorted(label_pages.items())},
            "category_source_group_counts": {label: len(groups) for label, groups in sorted(label_groups.items())},
            "exact_document_index_annotation_regions": source_index_count,
            "exact_document_index_annotation_pages": len(source_index_pages),
            "exact_document_index_annotation_source_groups": len(source_index_groups),
            "exact_document_index_annotation_categories": len(source_index_categories),
            "production_role_mapping": "not defined; source labels are not silently converted to Region.label",
        },
        "production_role_observation": {
            "natural_document_index_regions_observed": 0,
            "eligible_controls_observed": 0,
            "reason": "No cached baseline layout exists for the new pages, and DocLayNet has no document_index category. The current production label can only be observed by an unchanged baseline replay.",
        },
        "decision": {
            "branch": "CONTROL_SUPPLY_INADEQUATE_BUT_INFORMATIVE",
            "full_baseline_justified": True,
            "justification": "Current production role emission and page-wide provenance cannot be recovered from the source annotation vocabulary; unchanged baseline replay is needed.",
            "control_adequacy_not_claimed": True,
        },
    }
    atomic_write_json(HERE / "ROLE_SCOUT.json", payload)
    return payload


def main() -> int:
    payload = scout()
    print(json.dumps({
        "status": payload["status"],
        "pages": payload["population"]["pages"],
        "source_document_index_annotations": payload["source_annotation"]["exact_document_index_annotation_regions"],
        "production_document_index_observed": payload["production_role_observation"]["natural_document_index_regions_observed"],
        "full_baseline_justified": payload["decision"]["full_baseline_justified"],
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
