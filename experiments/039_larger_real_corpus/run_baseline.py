#!/usr/bin/env python
"""Run the unchanged production baseline over the frozen 039 image slice.

This runner is pre-treatment only.  It does not read GT annotations, invoke
the 036 forced-crop path, or route records based on any outcome.  Each record
is checkpointed atomically so an interrupted CPU run can resume safely.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))

from doc_extraction.cli import process_file  # noqa: E402
from doc_extraction.config import load_config  # noqa: E402


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def atomic_write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def complete(run_dir: Path) -> bool:
    required = (
        run_dir / "metadata.json",
        run_dir / "layout" / "page-001.json",
        run_dir / "ocr" / "page-001.json",
        run_dir / "final" / "document.json",
    )
    if not all(path.is_file() for path in required):
        return False
    try:
        metadata = json.loads((run_dir / "metadata.json").read_text())
        document = json.loads((run_dir / "final" / "document.json").read_text())
    except (OSError, json.JSONDecodeError):
        return False
    return not metadata.get("errors") and bool(document.get("pages"))


def free_bytes(path: Path) -> int:
    return shutil.disk_usage(path).free


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--document", action="append", dest="documents")
    parser.add_argument("--max-records", type=int)
    args = parser.parse_args()

    manifest_path = HERE / "population_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    records = manifest["records"]
    if len(records) != 269:
        raise SystemExit(f"expected frozen 039 population of 269 records, found {len(records)}")

    result_root = HERE / "results" / "baseline_runs"
    result_root.mkdir(parents=True, exist_ok=True)
    index_path = HERE / "results" / "baseline_run_index.json"
    manifest_hash = digest(manifest_path)
    prior = json.loads(index_path.read_text()) if index_path.is_file() else {
        "experiment": "039_larger_real_corpus",
        "phase": "unchanged_production_baseline",
        "manifest_sha256": manifest_hash,
        "records": [],
    }
    if prior.get("manifest_sha256") != manifest_hash:
        raise SystemExit("baseline index was made from a different population manifest")
    prior_by_id = {item["image_id"]: item for item in prior.get("records", [])}
    config = load_config(ROOT / "configs" / "cpu.yaml")
    config.device = "cpu"

    selected = records
    if args.documents:
        wanted = set(args.documents)
        selected = [
            item for item in records
            if str(item["image_id"]) in wanted or item["file_name"] in wanted
        ]
    if args.max_records is not None:
        selected = selected[:args.max_records]

    def checkpoint() -> None:
        ordered = [
            prior_by_id[item["image_id"]]
            for item in records
            if item["image_id"] in prior_by_id
        ]
        atomic_write(index_path, {**prior, "records": ordered})

    for ordinal, item in enumerate(selected, 1):
        image = HERE / "results" / "doclaynet" / "PNG" / item["file_name"]
        run_dir = result_root / str(item["image_id"])
        row = {
            "image_id": item["image_id"],
            "file_name": item["file_name"],
            "doc_group": item["doc_group"],
            "split": item["split"],
            "doc_category": item["doc_category"],
            "page_no": item["page_no"],
            "role": item["role"],
            "image_sha256": item["image_sha256"],
            "run": str(run_dir.relative_to(ROOT)),
        }
        if not image.is_file():
            row.update({"status": "failure", "error": f"missing input image: {image}"})
            prior_by_id[item["image_id"]] = row
            checkpoint()
            print(f"[{ordinal}/{len(selected)}] FAILED {item['image_id']}: missing image", flush=True)
            continue
        if complete(run_dir):
            row.update({"status": "complete", "resumed": True})
            prior_by_id[item["image_id"]] = row
            checkpoint()
            print(f"[{ordinal}/{len(selected)}] existing {item['image_id']} ({item['doc_group']})", flush=True)
            continue
        if run_dir.exists():
            incident = result_root / "interrupted_attempts" / f"{item['image_id']}-{int(time.time())}"
            incident.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(run_dir), str(incident))
            row["preserved_incomplete_attempt"] = str(incident.relative_to(ROOT))

        started = datetime.now(timezone.utc).isoformat()
        print(f"[{ordinal}/{len(selected)}] running {item['image_id']} ({item['doc_group']})", flush=True)
        try:
            document = process_file(image, config=config, output_dir=run_dir)
            row.update({
                "status": "complete",
                "started_at": started,
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "runtime_seconds": document.metadata.runtime_seconds,
                "n_pages": len(document.pages),
                "n_elements": sum(len(page.elements) for page in document.pages),
                "n_tables": sum(len(page.tables) for page in document.pages),
            })
        except Exception as exc:  # noqa: BLE001 - preserve operational failures
            row.update({
                "status": "failure",
                "started_at": started,
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "error": f"{type(exc).__name__}: {exc}",
            })
        prior_by_id[item["image_id"]] = row
        checkpoint()
        print(
            f"  {row['status']}; free_disk_bytes={free_bytes(ROOT)}",
            file=sys.stderr if row["status"] == "failure" else sys.stdout,
            flush=True,
        )

    target_ids = {item["image_id"] for item in selected}
    target_complete = all(prior_by_id.get(image_id, {}).get("status") == "complete" for image_id in target_ids)
    complete_total = sum(
        prior_by_id.get(item["image_id"], {}).get("status") == "complete" for item in records
    )
    print(json.dumps({
        "selected": len(selected),
        "indexed": len(prior_by_id),
        "complete": complete_total,
        "total": len(records),
    }))
    return 0 if target_complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
