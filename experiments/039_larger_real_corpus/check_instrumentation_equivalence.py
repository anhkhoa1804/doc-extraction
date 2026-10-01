#!/usr/bin/env python
"""Prove that optional table telemetry does not change production output.

This is a no-treatment engineering check.  It runs the unchanged baseline
path twice, once without a recorder and once with the recorder, over a small
fixed development-only sample.  The frozen ``results/baseline_runs`` tree is
never used as an output target and held-out records are rejected before any
processing begins.

The fixed IDs are all development records selected to exercise the visual
039 path: a known development D2 page, labelled-crop pages, a page-wide
detector/no-structure control, and a labelled-crop warning control.  They are
not selector labels and no treatment outcome is read.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))

DEFAULT_DEVELOPMENT_IDS = (2819, 2788, 2673, 2780)


def atomic_json(path: Path, payload: Any) -> None:
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


def digest(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def canonical_document(document: dict[str, Any]) -> dict[str, Any]:
    """Remove only execution-identity fields that must differ between arms."""
    value = json.loads(json.dumps(document))
    metadata = value["metadata"]
    metadata.pop("timestamp", None)
    metadata.pop("runtime_seconds", None)
    for page in value.get("pages", []):
        # The two arms intentionally write to separate output directories.
        # The path is not semantic IR; all other page and element fields are
        # compared exactly, including tables, ownership ids, notes and order.
        if "rendered_image_path" in page:
            page["rendered_image_path"] = "<rendered-image>"
    return value


def git_head() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def load_development_rows(ids: tuple[int, ...]) -> dict[int, dict[str, Any]]:
    manifest = json.loads((HERE / "population_manifest.json").read_text(encoding="utf-8"))
    by_id = {int(row["image_id"]): row for row in manifest["records"]}
    missing = [image_id for image_id in ids if image_id not in by_id]
    if missing:
        raise SystemExit(f"equivalence IDs are absent from the frozen manifest: {missing}")
    non_development = [image_id for image_id in ids if by_id[image_id]["split"] != "development"]
    if non_development:
        raise SystemExit(f"held-out IDs are forbidden in equivalence sample: {non_development}")
    return {image_id: by_id[image_id] for image_id in ids}


def run_pair(row: dict[str, Any], output_root: Path, config: Any) -> dict[str, Any]:
    from doc_extraction.cli import clear_component_backend_cache, process_file
    from doc_extraction.utils.hashing import sha256_file
    from doc_extraction.utils.ids import document_id as make_document_id
    from doc_extraction.utils.table_telemetry import TableTelemetryRecorder

    image = HERE / "results" / "doclaynet" / "PNG" / row["file_name"]
    image_id = int(row["image_id"])
    pair_root = output_root / str(image_id)
    if pair_root.exists():
        raise SystemExit(f"refusing to reuse equivalence output directory: {pair_root}")

    arms: dict[str, dict[str, Any]] = {}
    expected_document_id = make_document_id(image, sha256_file(image))
    for arm in ("un-instrumented", "instrumented"):
        # Do not let cached model/backend state make the comparison one-sided.
        clear_component_backend_cache()
        arm_root = pair_root / arm
        recorder = (
            TableTelemetryRecorder(
                experiment_id="039-instrumentation-equivalence",
                run_id=f"039-equivalence-{image_id}",
                context={"sample_split": "development"},
            )
            if arm == "instrumented"
            else None
        )
        try:
            document = process_file(
                image,
                config=config,
                output_root=arm_root,
                backend_name="baseline",
                table_telemetry=recorder,
            )
            status = "complete"
            error = None
            document_dir = arm_root / document.document_id
            document_json = json.loads((document_dir / "final" / "document.json").read_text(encoding="utf-8"))
        except Exception as exc:
            status = "failure"
            error = f"{type(exc).__name__}: {exc}"
            document_dir = arm_root / expected_document_id
            document_json = None
        if recorder is not None:
            recorder.write_atomic(
                document_dir / "table_telemetry.json",
                status=status,
                error=error,
            )
        arms[arm] = {
            "status": status,
            "error": error,
            "canonical": canonical_document(document_json) if document_json is not None else None,
            "canonical_sha256": digest(canonical_document(document_json)) if document_json is not None else None,
        }

    left = arms["un-instrumented"]
    right = arms["instrumented"]
    equivalent = (
        left["status"] == "complete"
        and right["status"] == "complete"
        and left["canonical"] == right["canonical"]
    )
    telemetry_path = pair_root / "instrumented" / expected_document_id / "table_telemetry.json"
    telemetry = json.loads(telemetry_path.read_text(encoding="utf-8")) if telemetry_path.exists() else None
    records = telemetry.get("records", []) if telemetry else []
    mode_counts: dict[str, int] = {}
    for record in records:
        if record.get("record_kind") != "specialist_invocation":
            continue
        mode = record.get("invocation_mode")
        mode_counts[mode] = mode_counts.get(mode, 0) + 1
    return {
        "image_id": image_id,
        "file_name": row["file_name"],
        "doc_group": row["doc_group"],
        "doc_category": row["doc_category"],
        "split": row["split"],
            "role": row["role"],
            "document_id": expected_document_id,
        "equivalent": equivalent,
        "arms": arms,
        "instrumented_telemetry_status": telemetry.get("status") if telemetry else None,
        "instrumented_record_count": len(records),
        "instrumented_invocation_mode_counts": mode_counts,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image-id", action="append", type=int, dest="image_ids")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=HERE / "results" / "instrumentation_equivalence",
    )
    args = parser.parse_args()
    ids = tuple(args.image_ids) if args.image_ids else DEFAULT_DEVELOPMENT_IDS
    if not ids or len(set(ids)) != len(ids):
        raise SystemExit("equivalence sample must contain at least one unique image ID")

    rows = load_development_rows(ids)
    from doc_extraction.config import load_config

    config = load_config(ROOT / "configs" / "cpu.yaml")
    config.device = "cpu"
    results = [run_pair(rows[image_id], args.output_dir, config) for image_id in ids]
    payload = {
        "experiment": "039-instrumentation-equivalence",
        "status": "PASS" if all(result["equivalent"] for result in results) else "FAIL",
        "treatment_executed": False,
        "heldout_accessed": False,
        "commit_sha": git_head(),
        "device": config.device,
        "sample_ids": list(ids),
        "results": results,
    }
    atomic_json(args.output_dir / "equivalence_summary.json", payload)
    print(json.dumps({
        "status": payload["status"],
        "sample_ids": list(ids),
        "pairs": len(results),
        "equivalent_pairs": sum(result["equivalent"] for result in results),
        "invocation_modes": [result["instrumented_invocation_mode_counts"] for result in results],
    }))
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
