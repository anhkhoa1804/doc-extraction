#!/usr/bin/env python
"""Run the unchanged production baseline over the frozen 038 image slice.

This runner is pre-treatment only.  It never calls the 036 forced-crop helper
or reads a counterfactual outcome.  The per-record index is written
atomically after each attempt so an interrupted process can resume without
guessing which complete runs survived.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
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
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def atomic_write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    os.replace(temporary, path)


def group_splits(records: list[dict]) -> dict[str, str]:
    groups = list(dict.fromkeys(item["doc_group"] for item in records))
    if len(groups) != 20:
        raise ValueError(f"expected 20 frozen groups, found {len(groups)}")
    return {group: "development" if index < 10 else "held_out_test"
            for index, group in enumerate(groups)}


def complete(run_dir: Path) -> bool:
    required = (run_dir / "metadata.json", run_dir / "layout" / "page-001.json",
                run_dir / "ocr" / "page-001.json", run_dir / "final" / "document.json")
    if not all(path.is_file() for path in required):
        return False
    try:
        metadata = json.loads((run_dir / "metadata.json").read_text())
        document = json.loads((run_dir / "final" / "document.json").read_text())
    except (OSError, json.JSONDecodeError):
        return False
    return not metadata.get("errors") and bool(document.get("pages"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--document", action="append", dest="documents")
    parser.add_argument("--max-records", type=int)
    args = parser.parse_args()

    manifest_path = HERE / "population_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    records = manifest["records"]
    splits = group_splits(records)
    result_root = HERE / "results" / "baseline_runs"
    result_root.mkdir(parents=True, exist_ok=True)
    index_path = HERE / "results" / "baseline_run_index.json"
    prior = json.loads(index_path.read_text()) if index_path.is_file() else {
        "experiment": "038_independent_real_corpus",
        "phase": "unchanged_production_baseline",
        "manifest_sha256": digest(manifest_path),
        "records": [],
    }
    if prior.get("manifest_sha256") != digest(manifest_path):
        raise SystemExit("baseline index was made from a different population manifest")
    prior_by_id = {item["image_id"]: item for item in prior.get("records", [])}
    config = load_config(ROOT / "configs" / "cpu.yaml")
    config.device = "cpu"

    selected = records
    if args.documents:
        wanted = set(args.documents)
        selected = [item for item in records if str(item["image_id"]) in wanted or item["file_name"] in wanted]
    if args.max_records is not None:
        selected = selected[:args.max_records]

    for ordinal, item in enumerate(selected, 1):
        image = HERE / "results" / "doclaynet" / "PNG" / item["file_name"]
        run_dir = result_root / str(item["image_id"])
        row = {
            "image_id": item["image_id"], "file_name": item["file_name"],
            "doc_group": item["doc_group"], "split": splits[item["doc_group"]],
            "page_no": item["page_no"], "role": item["role"],
            "image_sha256": item["image_sha256"],
            "run": str(run_dir.relative_to(ROOT)),
        }
        if complete(run_dir):
            row.update({"status": "complete", "resumed": True})
            prior_by_id[item["image_id"]] = row
            atomic_write(index_path, {**prior, "records": [prior_by_id[x["image_id"]] for x in records if x["image_id"] in prior_by_id]})
            print(f"[{ordinal}/{len(selected)}] existing {item['image_id']}", flush=True)
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
                "status": "complete", "started_at": started,
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "runtime_seconds": document.metadata.runtime_seconds,
                "n_pages": len(document.pages),
                "n_elements": sum(len(page.elements) for page in document.pages),
                "n_tables": sum(len(page.tables) for page in document.pages),
            })
        except Exception as exc:  # noqa: BLE001 - preserve operational failures
            row.update({
                "status": "failure", "started_at": started,
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "error": f"{type(exc).__name__}: {exc}",
            })
        prior_by_id[item["image_id"]] = row
        atomic_write(index_path, {**prior, "records": [prior_by_id[x["image_id"]] for x in records if x["image_id"] in prior_by_id]})
        if row["status"] != "complete":
            print(f"  FAILED: {row['error']}", file=sys.stderr, flush=True)

    completed = sum(item.get("status") == "complete" for item in prior_by_id.values())
    print(json.dumps({"selected": len(selected), "indexed": len(prior_by_id), "complete": completed}))
    return 0 if all(item.get("status") == "complete" for item in prior_by_id.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
