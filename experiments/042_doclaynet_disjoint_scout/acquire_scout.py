#!/usr/bin/env python3
"""Acquire the already-frozen 042 scout pages by bounded ZIP ranges."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import platform
import subprocess
import tempfile
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PNG_ROOT = HERE / "results" / "source" / "PNG"
MANIFEST = HERE / "population_manifest.json"
ACQUISITION_MANIFEST = HERE / "ACQUISITION_MANIFEST.json"


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


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_acquisition_helpers():
    path = ROOT / "experiments/039_larger_real_corpus/acquire_doclaynet.py"
    spec = importlib.util.spec_from_file_location("acquire_039_helpers", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load bounded DocLayNet acquisition helpers")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if manifest.get("status") != "SCOUT_DESIGN_FROZEN_ACQUISITION_PENDING":
        raise SystemExit("042 population manifest is not the frozen scout design")
    if any(record.get("split") != "development" for record in manifest["records"]):
        raise SystemExit("held-out or unknown split entered acquisition")
    helper = load_acquisition_helpers()
    entries = helper.central_directory()
    acquired: list[dict[str, Any]] = []
    for ordinal, record in enumerate(manifest["records"], 1):
        path = PNG_ROOT / record["file_name"]
        path.parent.mkdir(parents=True, exist_ok=True)
        existed = path.is_file()
        data = path.read_bytes() if existed else helper.member_bytes(entries, f"PNG/{record['file_name']}")
        if not existed:
            helper.atomic_write(path, data)
        actual = sha256_bytes(data)
        acquired.append({
            "unit_id": record["unit_id"],
            "split": record["split"],
            "image_id": record["image_id"],
            "file_name": record["file_name"],
            "source_group": record["source_group"],
            "doc_category": record["doc_category"],
            "page_no": record["page_no"],
            "source_image_sha256": actual,
            "bytes": len(data),
        })
        if ordinal % 25 == 0 or ordinal == len(manifest["records"]):
            print(json.dumps({"acquired": ordinal, "total": len(manifest["records"]), "free_bytes": __import__("shutil").disk_usage(ROOT).free}), flush=True)
    payload = {
        "experiment": "042_doclaynet_disjoint_scout",
        "status": "ACQUISITION_COMPLETE",
        "population_hash": manifest["population_hash"],
        "code_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "device": "cpu",
        "python": platform.python_version(),
        "heldout_accessed": False,
        "records": acquired,
    }
    atomic_write_json(ACQUISITION_MANIFEST, payload)
    print(json.dumps({"status": payload["status"], "records": len(acquired), "population_hash": payload["population_hash"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
