"""Validate the local OmniDocBench snapshot and freeze a stratified subset."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

from PIL import Image

from doc_extraction.evaluation.omnidocbench import dataset_semantic_hash, load_dataset

MANIFEST_SCHEMA = "omnidocbench-subset/1"
DEFAULT_TARGET = 180
DEFAULT_SEED = 4601


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _region_counts(record: dict[str, Any]) -> Counter[str]:
    return Counter(str(item.get("category_type", "unknown")) for item in record.get("layout_dets", []))


def _dangling_relations(record: dict[str, Any]) -> list[dict[str, Any]]:
    """Find relation records whose endpoint IDs do not resolve on the page.

    OmniDocBench's checked-in data uses both integer annotation IDs and
    ``box_id_N`` string IDs. The official relation examples use integers, so
    the integer-to-``box_id_N`` alias is accepted only when that exact box ID
    exists in the same page's layout detections.
    """
    annotation_ids = {item.get("anno_id") for item in (record.get("layout_dets") or [])}

    def exists(reference: Any) -> bool:
        return reference in annotation_ids or f"box_id_{reference}" in annotation_ids

    unresolved = []
    for relation in (record.get("extra") or {}).get("relation") or []:
        source = relation.get("source_anno_id")
        target = relation.get("target_anno_id")
        if not exists(source) or not exists(target):
            unresolved.append(relation)
    return unresolved


def _dangling_endpoint_count(record: dict[str, Any]) -> int:
    annotation_ids = {item.get("anno_id") for item in (record.get("layout_dets") or [])}
    count = 0
    for relation in (record.get("extra") or {}).get("relation") or []:
        for field in ("source_anno_id", "target_anno_id"):
            reference = relation.get(field)
            if reference not in annotation_ids and f"box_id_{reference}" not in annotation_ids:
                count += 1
    return count


def _record_labels(record: dict[str, Any], text_heavy_threshold: int) -> set[str]:
    page = record["page_info"]
    attrs = page.get("page_attribute") or {}
    regions = _region_counts(record)
    labels = {
        f"source:{attrs.get('data_source', 'unknown')}",
        f"language:{attrs.get('language', 'unknown')}",
        f"layout:{attrs.get('layout', 'unknown')}",
        f"subset:{attrs.get('subset', 'unknown')}",
    }
    special = attrs.get("special_issue") or []
    if isinstance(special, str):
        special = [special]
    labels.update(f"special:{item}" for item in special)
    table_count = regions["table"]
    formula_count = regions["equation_isolated"] + regions["equation_semantic"]
    text_count = regions["text_block"]
    labels.add("content:table" if table_count else "content:no_table")
    labels.add("content:formula" if formula_count else "content:no_formula")
    labels.add("content:text_heavy" if text_count >= text_heavy_threshold else "content:other_text_density")
    layout = str(attrs.get("layout", "unknown"))
    labels.add("layout:complex" if layout != "single_column" else "layout:simple")
    labels.add("content:mixed" if sum(bool(regions[name]) for name in ("text_block", "table", "figure", "equation_isolated")) >= 3 else "content:not_mixed")
    return labels


def _stable_rank(seed: int, image_name: str) -> str:
    return hashlib.sha256(f"{seed}:{image_name}".encode()).hexdigest()


def stratified_indices(records: list[dict[str, Any]], target: int, seed: int) -> tuple[list[int], dict[str, Any]]:
    if target <= 0 or target > len(records):
        raise ValueError(f"target must be in 1..{len(records)}, got {target}")
    region_counts = [_region_counts(record) for record in records]
    text_values = sorted(counts["text_block"] for counts in region_counts)
    text_heavy_threshold = text_values[math.floor(0.75 * (len(text_values) - 1))]
    labels_by_index = [_record_labels(record, text_heavy_threshold) for record in records]
    population_counts: Counter[str] = Counter(label for labels in labels_by_index for label in labels)
    target_counts = {
        label: max(1, round(target * count / len(records)))
        for label, count in population_counts.items()
    }
    selected: list[int] = []
    selected_set: set[int] = set()
    current: Counter[str] = Counter()
    ranks = {
        i: _stable_rank(seed, str(records[i]["page_info"]["image_path"]))
        for i in range(len(records))
    }

    while len(selected) < target:
        best_index: int | None = None
        best_score = -1.0
        for index, labels in enumerate(labels_by_index):
            if index in selected_set:
                continue
            score = sum(
                max(0, target_counts[label] - current[label]) / target_counts[label]
                for label in labels
            )
            if score > best_score or (score == best_score and best_index is not None and ranks[index] < ranks[best_index]):
                best_score = score
                best_index = index
        if best_index is None:
            break
        selected.append(best_index)
        selected_set.add(best_index)
        current.update(labels_by_index[best_index])

    selected.sort()
    composition = {
        "target_counts": dict(sorted(target_counts.items())),
        "selected_counts": dict(sorted(Counter(label for i in selected for label in labels_by_index[i]).items())),
        "text_heavy_threshold_text_block_regions": text_heavy_threshold,
        "label_definition": {
            "source": "page_info.page_attribute.data_source",
            "language": "page_info.page_attribute.language",
            "layout": "page_info.page_attribute.layout",
            "subset": "page_info.page_attribute.subset",
            "special": "page_info.page_attribute.special_issue",
            "table": "at least one layout_dets.category_type == table",
            "formula": "at least one equation_isolated or equation_semantic layout region",
            "text_heavy": "text_block region count >= population 75th percentile",
            "layout_complex": "layout metadata value other than single_column",
            "mixed": "at least three of text_block/table/figure/equation_isolated region kinds present",
        },
    }
    return selected, composition


def build_manifest(
    dataset_root: Path,
    target: int = DEFAULT_TARGET,
    seed: int = DEFAULT_SEED,
    *,
    max_image_pixels: int | None = None,
    policy_config: str | None = None,
    policy_config_sha256: str | None = None,
) -> dict[str, Any]:
    dataset_root = dataset_root.resolve()
    gt_path, samples = load_dataset(dataset_root)
    raw_records = json.loads(gt_path.read_text(encoding="utf-8"))
    if len(raw_records) != len(samples):
        raise ValueError("dataset loader did not resolve every ground-truth record")

    image_names = [sample.image_name for sample in samples]
    if len(image_names) != len(set(image_names)):
        raise ValueError("duplicate image filename in ground truth")
    sample_ids = [record["page_info"].get("sample_id") for record in raw_records]
    present_ids = [str(value) for value in sample_ids if value is not None]
    if len(present_ids) != len(set(present_ids)):
        raise ValueError("duplicate non-null sample_id in ground truth")
    page_ids = [(sample.image_name, sample.page_no) for sample in samples]
    if len(page_ids) != len(set(page_ids)):
        raise ValueError("duplicate image/page identity in ground truth")
    annotation_count = 0
    relation_count = 0
    dangling_relation_count = 0
    dangling_endpoint_count = 0
    null_annotation_ids = 0
    dangling_relations: list[dict[str, Any]] = []
    for index, record in enumerate(raw_records):
        detections = record.get("layout_dets") or []
        annotation_ids = [item.get("anno_id") for item in detections]
        null_annotation_ids += sum(value is None for value in annotation_ids)
        if null_annotation_ids:
            raise ValueError(f"record {index} contains an annotation without anno_id")
        if len(annotation_ids) != len(set(annotation_ids)):
            raise ValueError(f"record {index} contains duplicate anno_id values")
        annotation_count += len(annotation_ids)
        relations = (record.get("extra") or {}).get("relation") or []
        relation_count += len(relations)
        unresolved = _dangling_relations(record)
        dangling_relation_count += len(unresolved)
        dangling_endpoint_count += _dangling_endpoint_count(record)
        dangling_relations.extend(
            {
                "dataset_index": index,
                "image_name": samples[index].image_name,
                "page_no": samples[index].page_no,
                "unresolved_relations": unresolved,
            }
            for _ in [0]
            if unresolved
        )

    image_root = dataset_root / "images"
    referenced = set(image_names)
    actual_paths = sorted(
        path for path in image_root.rglob("*") if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg"}
    )
    actual_names = {path.name for path in actual_paths}
    if actual_names != referenced:
        raise ValueError(
            f"image inventory mismatch: {len(referenced - actual_names)} referenced images missing, "
            f"{len(actual_names - referenced)} unreferenced images present"
        )

    image_inventory = []
    for path in actual_paths:
        image_inventory.append({
            "path": path.relative_to(dataset_root).as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        })
    inventory_hash = canonical_sha256(image_inventory)
    excluded_indices = {entry["dataset_index"] for entry in dangling_relations}
    dataset_valid_indices = [index for index in range(len(raw_records)) if index not in excluded_indices]
    policy_rejections: list[dict[str, Any]] = []
    dimensions: dict[int, tuple[int, int]] = {}
    if max_image_pixels is not None:
        if max_image_pixels <= 0:
            raise ValueError("max_image_pixels must be positive")
        for index in dataset_valid_indices:
            sample = samples[index]
            with Image.open(sample.image_path) as image:
                width, height = image.size
            dimensions[index] = (width, height)
            pixels = width * height
            if pixels > max_image_pixels:
                attrs = raw_records[index]["page_info"].get("page_attribute") or {}
                policy_rejections.append({
                    "dataset_index": index,
                    "sample_id": raw_records[index]["page_info"].get("sample_id"),
                    "page_id": f"{sample.image_name}#{sample.page_no}",
                    "page_no": sample.page_no,
                    "image_name": sample.image_name,
                    "image_sha256": sha256_file(sample.image_path),
                    "width": width,
                    "height": height,
                    "pixels": pixels,
                    "reason": "max_image_pixels",
                    "source": attrs.get("data_source", "unknown"),
                    "language": attrs.get("language", "unknown"),
                    "layout": attrs.get("layout", "unknown"),
                })
    policy_rejected_indices = {entry["dataset_index"] for entry in policy_rejections}
    eligible_indices = [index for index in dataset_valid_indices if index not in policy_rejected_indices]
    if target > len(eligible_indices):
        raise ValueError(f"target {target} exceeds production-policy-eligible population {len(eligible_indices)}")
    eligible_records = [raw_records[index] for index in eligible_indices]
    chosen_positions, composition = stratified_indices(eligible_records, target, seed)
    chosen_indices = [eligible_indices[position] for position in chosen_positions]
    by_index = {sample.index: sample for sample in samples}
    selected = []
    for index in chosen_indices:
        sample = by_index[index]
        record = raw_records[index]
        selected.append({
            "dataset_index": index,
            "sample_id": record["page_info"].get("sample_id"),
            "page_id": f"{sample.image_name}#{sample.page_no}",
            "page_no": sample.page_no,
            "image_path": sample.image_path.relative_to(dataset_root).as_posix(),
            "image_name": sample.image_name,
            "image_sha256": sha256_file(sample.image_path),
            "page_attribute": record["page_info"].get("page_attribute") or {},
            "annotation_counts": dict(sorted(_region_counts(record).items())),
        })
        if max_image_pixels is not None:
            width, height = dimensions[index]
            selected[-1]["image_dimensions"] = {"width": width, "height": height, "pixels": width * height}

    subset_name = "representative-v2" if max_image_pixels is not None else "representative-v1"
    manifest: dict[str, Any] = {
        "schema_version": MANIFEST_SCHEMA,
        "benchmark": {"name": "OmniDocBench", "version": "1.6", "upstream_evaluator_commit": "193627ae9e97d89188468ed1ee3b7a856ff76044"},
        "dataset_identity": {
            "dataset_root": "experiments/034a_omnidocbench_snapshot/dataset/full",
            "annotation_file": gt_path.name,
            "annotation_sha256": sha256_file(gt_path),
            "annotation_semantic_sha256": dataset_semantic_hash(gt_path),
            "image_inventory_count": len(image_inventory),
            "image_inventory_sha256": inventory_hash,
            "integrity_summary": {
                "annotation_records": len(raw_records),
                "resolved_images": len(samples),
                "orphan_images": len(actual_paths) - len(referenced),
                "duplicate_image_names": 0,
                "nonnull_sample_ids": len(present_ids),
                "records_without_sample_id": len(sample_ids) - len(present_ids),
                "layout_annotations": annotation_count,
                "relations": relation_count,
                "dangling_relation_records": dangling_relation_count,
                "dangling_relation_endpoints": dangling_endpoint_count,
                "affected_pages": len(dangling_relations),
            },
        },
        "subset": {
            "name": subset_name,
            "target_size": target,
            "actual_size": len(selected),
            "selection_method": "deterministic iterative marginal-stratification; choose the remaining page maximizing normalized deficits across source, language, layout, hard subset, special issue, table/formula presence, text density, and mixed-content labels; SHA256(seed,image_path) breaks ties; final list sorted by dataset index",
            "seed": seed,
            "composition": composition,
            "eligibility_exclusions": dangling_relations,
            "samples": selected,
        },
    }
    if max_image_pixels is not None:
        def group_counts(field: str) -> dict[str, int]:
            return dict(sorted(Counter(str(entry[field]) for entry in policy_rejections).items()))

        manifest["production_policy"] = {
            "config_file": policy_config,
            "config_sha256": policy_config_sha256,
            "max_image_pixels": max_image_pixels,
            "eligibility_rule": "dataset-valid image header pixel product <= configured max_image_pixels; boundary equals limit is eligible",
            "coverage_population_count": len(dataset_valid_indices),
            "policy_eligible_count": len(eligible_indices),
            "policy_rejected_count": len(policy_rejections),
            "rejected_by_reason": dict(sorted(Counter(entry["reason"] for entry in policy_rejections).items())),
            "rejected_by_source": group_counts("source"),
            "rejected_by_language": group_counts("language"),
            "rejected_by_layout": group_counts("layout"),
            "rejections": policy_rejections,
        }
    manifest["subset_identity"] = {
        "algorithm": "sha256(canonical JSON of manifest excluding subset_identity)",
        "sha256": canonical_sha256(manifest),
    }
    return manifest


def verify_manifest(dataset_root: Path, manifest_path: Path) -> tuple[list[int], list[dict[str, Any]], dict[str, Any]]:
    """Validate full dataset identity and return selected indexes/records.

    Full image inventory hashing is intentional here: manifest identity is a
    gate, not a best-effort hint. This prevents running against a changed local
    data directory under the frozen subset name.
    """
    dataset_root = dataset_root.resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != MANIFEST_SCHEMA:
        raise ValueError("unsupported representative manifest schema")
    manifest_hash = manifest.get("subset_identity", {}).get("sha256")
    body = {key: value for key, value in manifest.items() if key != "subset_identity"}
    if manifest_hash != canonical_sha256(body):
        raise ValueError("manifest subset identity hash mismatch")
    gt_path, samples = load_dataset(dataset_root)
    identity = manifest["dataset_identity"]
    if sha256_file(gt_path) != identity.get("annotation_sha256"):
        raise ValueError("ground-truth annotation hash differs from frozen manifest")
    if dataset_semantic_hash(gt_path) != identity.get("annotation_semantic_sha256"):
        raise ValueError("ground-truth semantic hash differs from frozen manifest")
    if len(samples) != identity.get("image_inventory_count"):
        raise ValueError("image count differs from frozen manifest")
    raw = json.loads(gt_path.read_text(encoding="utf-8"))
    by_index = {sample.index: sample for sample in samples}
    expected_inventory = []
    actual_paths = sorted(path for path in (Path(dataset_root) / "images").rglob("*") if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg"})
    names = {sample.image_name for sample in samples}
    actual_names = {path.name for path in actual_paths}
    if names != actual_names:
        raise ValueError("referenced image set differs from on-disk image inventory")
    for path in actual_paths:
        expected_inventory.append({"path": path.relative_to(dataset_root).as_posix(), "size_bytes": path.stat().st_size, "sha256": sha256_file(path)})
    if canonical_sha256(expected_inventory) != identity.get("image_inventory_sha256"):
        raise ValueError("image inventory hash differs from frozen manifest")

    entries = manifest["subset"]["samples"]
    indices = [entry.get("dataset_index") for entry in entries]
    if len(indices) != manifest["subset"].get("actual_size") or len(set(indices)) != len(indices):
        raise ValueError("manifest has invalid or duplicate selected indexes")
    expected_exclusions = {
        index for index, record in enumerate(raw) if _dangling_relations(record)
    }
    recorded_exclusions = {
        entry.get("dataset_index")
        for entry in manifest["subset"].get("eligibility_exclusions", [])
    }
    if expected_exclusions != recorded_exclusions:
        raise ValueError("manifest exclusion set does not match current truth-side integrity checks")
    if expected_exclusions.intersection(indices):
        raise ValueError("manifest selected a page with dangling relation annotations")
    production_policy = manifest.get("production_policy")
    if production_policy is not None:
        max_pixels = production_policy.get("max_image_pixels")
        if not isinstance(max_pixels, int) or max_pixels <= 0:
            raise ValueError("manifest has invalid production max_image_pixels")
        dataset_valid = [index for index in range(len(raw)) if index not in expected_exclusions]
        rejected = []
        measured: dict[int, tuple[int, int]] = {}
        for index in dataset_valid:
            with Image.open(by_index[index].image_path) as image:
                width, height = image.size
            measured[index] = width, height
            if width * height > max_pixels:
                rejected.append(index)
        recorded_rejected = [entry.get("dataset_index") for entry in production_policy.get("rejections", [])]
        if recorded_rejected != rejected:
            raise ValueError("policy rejection population differs from current image dimensions")
        if production_policy.get("coverage_population_count") != len(dataset_valid):
            raise ValueError("coverage population count differs from dataset-valid population")
        if production_policy.get("policy_eligible_count") != len(dataset_valid) - len(rejected):
            raise ValueError("policy eligible count is inconsistent")
        if set(indices).intersection(rejected):
            raise ValueError("manifest selected a production-policy-ineligible image")
    for entry in entries:
        index = entry["dataset_index"]
        if index not in by_index or not 0 <= index < len(raw):
            raise ValueError(f"manifest dataset index is invalid: {index}")
        sample = by_index[index]
        if entry.get("image_name") != sample.image_name or entry.get("page_no") != sample.page_no:
            raise ValueError(f"manifest sample mapping differs at dataset index {index}")
        if entry.get("page_id") != f"{sample.image_name}#{sample.page_no}":
            raise ValueError(f"manifest page identity differs at dataset index {index}")
        if entry.get("sample_id") != raw[index]["page_info"].get("sample_id"):
            raise ValueError(f"manifest source sample ID differs at dataset index {index}")
        if entry.get("image_sha256") != sha256_file(sample.image_path):
            raise ValueError(f"selected image hash differs at dataset index {index}")
        if production_policy is not None:
            width, height = measured[index]
            if entry.get("image_dimensions") != {"width": width, "height": height, "pixels": width * height}:
                raise ValueError(f"selected image dimensions differ at dataset index {index}")
    return indices, raw, manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--target", type=int, default=DEFAULT_TARGET)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--config", type=Path, default=None,
                        help="Production config; when supplied, freezes image-pixel eligibility from its limits")
    args = parser.parse_args()
    policy_kwargs: dict[str, Any] = {}
    if args.config is not None:
        from doc_extraction.config import load_config

        config_path = args.config.resolve()
        config = load_config(config_path)
        policy_kwargs = {
            "max_image_pixels": config.limits.max_image_pixels,
            "policy_config": config_path.name,
            "policy_config_sha256": sha256_file(config_path),
        }
    manifest = build_manifest(args.dataset, args.target, args.seed, **policy_kwargs)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {len(manifest['subset']['samples'])} samples to {args.output}")
    print(f"subset identity: {manifest['subset_identity']['sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
