#!/usr/bin/env python
"""Bounded, reproducible acquisition of a small DocLayNet validation slice."""
from __future__ import annotations

import hashlib
import json
import struct
import urllib.request
import zlib
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
URL = "https://codait-cos-dax.s3.us.cloud-object-storage.appdomain.cloud/dax-doclaynet/1.0.0/DocLayNet_core.zip"
ZIP_SIZE = 30_012_083_650
CD_START, CD_SIZE = 29_999_021_762, 13_061_790
SPLIT = "038-split-v1:"


def get_range(start: int, end: int) -> bytes:
    req = urllib.request.Request(URL, headers={"Range": f"bytes={start}-{end}"})
    with urllib.request.urlopen(req, timeout=180) as response:
        data = response.read()
    expected = end - start + 1
    if len(data) != expected:
        raise IOError(f"short range: {len(data)} != {expected}")
    return data


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def central_directory() -> dict[str, tuple[int, int, int]]:
    data = get_range(CD_START, CD_START + CD_SIZE - 1)
    out: dict[str, tuple[int, int, int]] = {}
    p = 0
    while p < len(data):
        if data[p:p + 4] != b"PK\x01\x02":
            break
        values = struct.unpack_from("<4s6H3L5H2L", data, p)
        n, extra_len, comment_len = values[10:13]
        comp_size, uncomp_size, offset = values[8], values[9], values[16]
        name = data[p + 46:p + 46 + n].decode("utf-8", "replace")
        extra = data[p + 46 + n:p + 46 + n + extra_len]
        # ZIP64 extra (0x0001) carries 64-bit values replacing 0xffffffff.
        q = 0
        zvals = []
        while q + 4 <= len(extra):
            tag, size = struct.unpack_from("<HH", extra, q)
            body = extra[q + 4:q + 4 + size]
            if tag == 1:
                zvals = [struct.unpack_from("<Q", body, i)[0] for i in range(0, len(body), 8)]
                break
            q += 4 + size
        zi = 0
        if uncomp_size == 0xffffffff: uncomp_size, zi = zvals[zi], zi + 1
        if comp_size == 0xffffffff: comp_size, zi = zvals[zi], zi + 1
        if offset == 0xffffffff: offset = zvals[zi]
        out[name] = (offset, comp_size, uncomp_size)
        p += 46 + n + extra_len + comment_len
    return out


def member_bytes(entries: dict[str, tuple[int, int, int]], name: str) -> bytes:
    offset, comp_size, uncomp_size = entries[name]
    header = get_range(offset, offset + 29)
    _, _, _, method, _, _, _, _, _, n, extra_len = struct.unpack("<4s5H3L2H", header)
    start = offset + 30 + n + extra_len
    compressed = get_range(start, start + comp_size - 1)
    result = zlib.decompress(compressed, -15) if method == 8 else compressed
    if len(result) != uncomp_size:
        raise IOError(f"size mismatch for {name}")
    return result


def main() -> int:
    out = HERE / "results" / "doclaynet"
    out.mkdir(parents=True, exist_ok=True)
    entries = central_directory()
    annotation_name = "COCO/val.json"
    annotation = member_bytes(entries, annotation_name)
    ann_path = out / "val.json"
    ann_path.write_bytes(annotation)
    raw = json.loads(annotation)
    cats = {x["id"]: x["name"] for x in raw["categories"]}
    tables = defaultdict(list)
    for a in raw["annotations"]:
        if a.get("precedence", 0) == 0 and cats.get(a["category_id"]) == "Table":
            tables[a["image_id"]].append(a)
    images = {x["id"]: x for x in raw["images"] if x.get("precedence", 0) == 0}
    groups = defaultdict(list)
    for image_id, image in images.items():
        if image_id in tables:
            groups[(image.get("collection", ""), image["doc_name"])].append(image)
    eligible = {g: sorted(v, key=lambda x: x["page_no"]) for g, v in groups.items() if len(v) >= 3}
    ranked = sorted(eligible, key=lambda g: hashlib.sha256((SPLIT + "::".join(g)).encode()).hexdigest())
    chosen = ranked[:20]
    records = []
    for i, group in enumerate(chosen):
        split = "development" if i < 10 else "held_out_test"
        pages = eligible[group]
        table_pages = pages[:5]
        # Add up to three same-document non-table pages as controls.
        all_group = sorted((x for x in images.values() if (x.get("collection", ""), x["doc_name"]) == group), key=lambda x: x["page_no"])
        controls = [x for x in all_group if x["id"] not in tables][:3]
        for role, selected in (("table_page", table_pages), ("non_table_control_page", controls)):
            for image in selected:
                name = f"PNG/{image['file_name']}"
                path = out / "PNG" / image["file_name"]
                path.parent.mkdir(parents=True, exist_ok=True)
                data = path.read_bytes() if path.exists() else member_bytes(entries, name)
                if not path.exists():
                    path.write_bytes(data)
                records.append({
                    "image_id": image["id"], "file_name": image["file_name"],
                    "doc_group": "::".join(group), "doc_name": image["doc_name"],
                    "collection": image.get("collection"), "page_no": image["page_no"],
                    "doc_category": image.get("doc_category"), "role": role,
                    "image_sha256": sha256(data), "width": image["width"], "height": image["height"],
                    "tables": tables.get(image["id"], []),
                })
    manifest = {
        "experiment": "038_independent_real_corpus", "dataset": "DocLayNet",
        "dataset_version": "1.0.0", "split": "validation", "archive_url": URL,
        "archive_size_bytes": ZIP_SIZE, "annotation_member": annotation_name,
        "annotation_sha256": sha256(annotation), "selection_rule": "20 hash-ranked groups with >=3 table pages; <=5 table + <=3 controls",
        "split_rule": SPLIT + "::" + "collection::doc_name", "document_groups": len(chosen),
        "development_groups": 10, "held_out_groups": 10, "records": records,
    }
    (HERE / "population_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"groups": len(chosen), "records": len(records), "tables": sum(bool(x["tables"]) for x in records)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
