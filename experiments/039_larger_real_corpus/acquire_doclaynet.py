#!/usr/bin/env python
"""Acquire the frozen 039 DocLayNet remainder without retaining the archive."""
from __future__ import annotations

import hashlib
import json
import os
import struct
import tempfile
import urllib.request
import zlib
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SOURCE = ROOT / "experiments/038_independent_real_corpus/results/doclaynet/val.json"
OUT = HERE / "results" / "doclaynet"
URL = "https://codait-cos-dax.s3.us.cloud-object-storage.appdomain.cloud/dax-doclaynet/1.0.0/DocLayNet_core.zip"
ZIP_SIZE = 30_012_083_650
CD_START, CD_SIZE = 29_999_021_762, 13_061_790
GROUP_PREFIX = "039-group-v1:"
TABLE_PAGE_PREFIX = "039-table-page-v1:"
CONTROL_PAGE_PREFIX = "039-control-page-v1:"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def get_range(start: int, end: int) -> bytes:
    request = urllib.request.Request(URL, headers={"Range": f"bytes={start}-{end}"})
    with urllib.request.urlopen(request, timeout=180) as response:
        data = response.read()
    expected = end - start + 1
    if len(data) != expected:
        raise IOError(f"short range: {len(data)} != {expected}")
    return data


def central_directory() -> dict[str, tuple[int, int, int]]:
    data = get_range(CD_START, CD_START + CD_SIZE - 1)
    entries: dict[str, tuple[int, int, int]] = {}
    offset = 0
    while offset < len(data) and data[offset:offset + 4] == b"PK\x01\x02":
        values = struct.unpack_from("<4s6H3L5H2L", data, offset)
        name_len, extra_len, comment_len = values[10:13]
        compressed_size, uncompressed_size, local_offset = values[8], values[9], values[16]
        name = data[offset + 46:offset + 46 + name_len].decode("utf-8", "replace")
        extra = data[offset + 46 + name_len:offset + 46 + name_len + extra_len]
        zip64: list[int] = []
        cursor = 0
        while cursor + 4 <= len(extra):
            tag, size = struct.unpack_from("<HH", extra, cursor)
            body = extra[cursor + 4:cursor + 4 + size]
            if tag == 1:
                zip64 = [struct.unpack_from("<Q", body, i)[0] for i in range(0, len(body), 8)]
                break
            cursor += 4 + size
        zip64_index = 0
        if uncompressed_size == 0xFFFFFFFF:
            uncompressed_size, zip64_index = zip64[zip64_index], zip64_index + 1
        if compressed_size == 0xFFFFFFFF:
            compressed_size, zip64_index = zip64[zip64_index], zip64_index + 1
        if local_offset == 0xFFFFFFFF:
            local_offset = zip64[zip64_index]
        entries[name] = (local_offset, compressed_size, uncompressed_size)
        offset += 46 + name_len + extra_len + comment_len
    return entries


def member_bytes(entries: dict[str, tuple[int, int, int]], name: str) -> bytes:
    local_offset, compressed_size, uncompressed_size = entries[name]
    header = get_range(local_offset, local_offset + 29)
    _, _, _, method, _, _, _, _, _, name_len, extra_len = struct.unpack("<4s5H3L2H", header)
    start = local_offset + 30 + name_len + extra_len
    compressed = get_range(start, start + compressed_size - 1)
    data = zlib.decompress(compressed, -15) if method == 8 else compressed
    if len(data) != uncompressed_size:
        raise IOError(f"size mismatch for {name}")
    return data


def stable_key(prefix: str, *parts: object) -> str:
    return hashlib.sha256((prefix + "::" + "::".join(str(part) for part in parts)).encode()).hexdigest()


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load_annotations(entries: dict[str, tuple[int, int, int]] | None) -> tuple[Path, dict]:
    if SOURCE.is_file():
        path = SOURCE
    else:
        if entries is None:
            raise RuntimeError("archive index is required when the 038 annotation member is absent")
        path = OUT / "val.json"
        atomic_write(path, member_bytes(entries, "COCO/val.json"))
    return path, json.loads(path.read_text())


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    # The annotation member may be reused from 038, but new 039 page images
    # still require the official archive index.  Always build the index so a
    # resumed acquisition cannot confuse local annotation availability with
    # local image availability.
    entries = central_directory()
    annotation_path, raw = load_annotations(entries)
    categories = {item["id"]: item["name"] for item in raw["categories"]}
    images = {item["id"]: item for item in raw["images"] if item.get("precedence", 0) == 0}
    tables: dict[int, list[dict]] = defaultdict(list)
    for annotation in raw["annotations"]:
        if annotation.get("precedence", 0) == 0 and categories.get(annotation["category_id"]) == "Table":
            tables[annotation["image_id"]].append(annotation)

    old_manifest = json.loads(
        (ROOT / "experiments/038_independent_real_corpus/population_manifest.json").read_text()
    )
    old_groups = {item["doc_group"] for item in old_manifest["records"]}
    old_image_ids = {item["image_id"] for item in old_manifest["records"]}
    grouped: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for image_id, image in images.items():
        if image_id in tables:
            group = (image.get("doc_category", ""), image.get("collection", ""), image["doc_name"])
            grouped[group].append(image)
    eligible = {
        group: sorted(rows, key=lambda row: row["page_no"])
        for group, rows in grouped.items()
        if len(rows) >= 3
    }
    remaining = {
        group: rows for group, rows in eligible.items()
        if "::".join(group[1:]) not in old_groups and not any(row["id"] in old_image_ids for row in rows)
    }
    if not remaining:
        raise RuntimeError("no independent eligible DocLayNet groups remain")

    split_by_group: dict[tuple[str, str, str], str] = {}
    for category in sorted({group[0] for group in remaining}):
        category_groups = sorted(
            (group for group in remaining if group[0] == category),
            key=lambda group: stable_key(GROUP_PREFIX, *group),
        )
        development_count = (len(category_groups) + 1) // 2
        for index, group in enumerate(category_groups):
            split_by_group[group] = "development" if index < development_count else "held_out_test"

    records: list[dict] = []
    for group in sorted(remaining, key=lambda value: stable_key(GROUP_PREFIX, *value)):
        category, collection, doc_name = group
        split = split_by_group[group]
        table_pages = sorted(
            remaining[group], key=lambda image: stable_key(TABLE_PAGE_PREFIX, image["id"])
        )[:6]
        group_pages = sorted(
            (image for image in images.values()
             if (image.get("collection", ""), image["doc_name"]) == (collection, doc_name)),
            key=lambda image: stable_key(CONTROL_PAGE_PREFIX, image["id"]),
        )
        controls = [image for image in group_pages if image["id"] not in tables][:3]
        for role, selected in (("table_page", table_pages), ("non_table_control_page", controls)):
            for image in selected:
                image_id = image["id"]
                image_name = image["file_name"]
                path = OUT / "PNG" / image_name
                if path.is_file():
                    data = path.read_bytes()
                else:
                    if entries is None:
                        raise RuntimeError(f"missing local image and archive index: {image_name}")
                    data = member_bytes(entries, f"PNG/{image_name}")
                    atomic_write(path, data)
                records.append({
                    "image_id": image_id,
                    "file_name": image_name,
                    "source_document_id": "::".join((collection, doc_name)),
                    "doc_group": "::".join((collection, doc_name)),
                    "doc_name": doc_name,
                    "collection": collection,
                    "doc_category": category,
                    "page_no": image["page_no"],
                    "split": split,
                    "role": role,
                    "image_sha256": sha256_bytes(data),
                    "width": image["width"],
                    "height": image["height"],
                    "tables": tables.get(image_id, []) if role == "table_page" else [],
                })

    manifest = {
        "experiment": "039_larger_real_corpus",
        "dataset": "DocLayNet",
        "dataset_version": "1.0.0",
        "dataset_split": "validation",
        "license": "CDLA-Permissive-1.0 for dataset; source-image terms remain applicable",
        "archive_url": URL,
        "archive_size_bytes": ZIP_SIZE,
        "annotation_member": "COCO/val.json",
        "annotation_sha256": sha256_path(annotation_path),
        "selection_algorithm": {
            "eligible_group_minimum_table_pages": 3,
            "excluded_038_groups": sorted(old_groups),
            "excluded_038_image_count": len(old_image_ids),
            "selected_table_pages_per_group_max": 6,
            "selected_controls_per_group_max": 3,
            "table_page_key": TABLE_PAGE_PREFIX + "<image_id>",
            "control_page_key": CONTROL_PAGE_PREFIX + "<image_id>",
        },
        "split_algorithm": {
            "group_key": GROUP_PREFIX + "<doc_category>::<collection>::<doc_name>",
            "within_category": True,
            "development_rule": "first ceil(n/2) hash-ranked groups per category",
            "development_groups": sum(split == "development" for split in split_by_group.values()),
            "held_out_groups": sum(split == "held_out_test" for split in split_by_group.values()),
        },
        "records": records,
    }
    manifest_path = HERE / "population_manifest.json"
    atomic_write(manifest_path, (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode())
    print(json.dumps({
        "groups": len(split_by_group),
        "development_groups": manifest["split_algorithm"]["development_groups"],
        "held_out_groups": manifest["split_algorithm"]["held_out_groups"],
        "records": len(records),
        "table_pages": sum(item["role"] == "table_page" for item in records),
        "control_pages": sum(item["role"] == "non_table_control_page" for item in records),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
