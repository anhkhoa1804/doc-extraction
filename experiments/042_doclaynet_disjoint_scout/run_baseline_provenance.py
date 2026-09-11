#!/usr/bin/env python3
"""Run the unchanged 042 production baseline for a frozen provenance sample."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import tempfile
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
POPULATION = HERE / "population_manifest.json"
ACQUISITION = HERE / "ACQUISITION_MANIFEST.json"
INTEGRITY = HERE / "ACQUISITION_INTEGRITY.json"
RESULT_ROOT = HERE / "results" / "baseline_provenance"
EXPECTED_POPULATION_HASH = "4d2ff975ec30d3c5c074bc858620dab856decbcabfdcd751c3861d8cdea0655e"
PROVENANCE_PREFIX = "042-provenance-page-v1"


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stable_key(image_id: int) -> str:
    return hashlib.sha256(f"{PROVENANCE_PREFIX}::{image_id}".encode()).hexdigest()


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


def git_head() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def require_development(record: dict[str, Any]) -> None:
    if record.get("split") != "development":
        raise RuntimeError(f"042 baseline refuses non-development record: {record.get('split')!r}")


def validate_frozen_inputs() -> tuple[dict[str, Any], dict[str, Any]]:
    population = read(POPULATION)
    if population.get("population_hash") != EXPECTED_POPULATION_HASH:
        raise RuntimeError("042 frozen population hash mismatch")
    if any(record.get("split") != "development" for record in population["records"]):
        raise RuntimeError("held-out record entered baseline provenance")
    acquisition = read(ACQUISITION)
    if acquisition.get("population_hash") != EXPECTED_POPULATION_HASH or len(acquisition.get("records", [])) != 279:
        raise RuntimeError("042 acquisition ledger is not the frozen complete cohort")
    if read(INTEGRITY).get("status") != "PASS":
        raise RuntimeError("042 acquisition integrity is not PASS")
    by_unit = {record["unit_id"]: record for record in acquisition["records"]}
    for record in population["records"]:
        require_development(record)
        acquired = by_unit.get(record["unit_id"])
        if acquired is None or acquired.get("split") != "development":
            raise RuntimeError(f"missing or non-development acquisition unit: {record['unit_id']}")
        image_path = HERE / "results" / "source" / "PNG" / record["file_name"]
        if not image_path.is_file() or sha256_path(image_path) != acquired.get("source_image_sha256"):
            raise RuntimeError(f"source image failed frozen hash check: {record['unit_id']}")
    return population, acquisition


def select_group_sample(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_group: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        require_development(record)
        by_group[record["source_group"]].append(record)
    selected = [min(group, key=lambda record: stable_key(int(record["image_id"]))) for group in by_group.values()]
    selected.sort(key=lambda record: (record["source_group"], int(record["image_id"])))
    if len(selected) != 40:
        raise RuntimeError(f"frozen group sample expected 40 pages, found {len(selected)}")
    return selected


def result_path(unit_id: str) -> Path:
    return RESULT_ROOT / unit_id / "result.json"


def index_path(mode: str) -> Path:
    if mode == "group_sample":
        return HERE / "BASELINE_PROVENANCE_SAMPLE_INDEX.json"
    return HERE / "BASELINE_PROVENANCE_INDEX.json"


def initial_index(population_hash: str, mode: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "experiment": "042_doclaynet_disjoint_scout",
        "status": "BASELINE_PROVENANCE_RUNNING",
        "mode": mode,
        "population_hash": population_hash,
        "code_commit": git_head(),
        "device": "cpu",
        "python": platform.python_version(),
        "heldout_accessed": False,
        "treatment_executed": False,
        "records": {
            record["unit_id"]: {
                "unit_id": record["unit_id"],
                "image_id": record["image_id"],
                "source_group": record["source_group"],
                "status": "PENDING",
            }
            for record in records
        },
    }


def summarize_document(document: Any, output_dir: Path, elapsed: float) -> dict[str, Any]:
    pages = list(document.pages)
    tables = [table for page in pages for table in page.tables]
    elements = [element for page in pages for element in page.elements]
    metadata = document.metadata.model_dump(mode="json")
    final_path = output_dir / "final" / "document.json"
    return {
        "document_id": document.document_id,
        "page_count": len(pages),
        "table_count": len(tables),
        "cell_count": sum(len(table.cells) for table in tables),
        "element_count": len(elements),
        "final_ir_sha256": sha256_path(final_path) if final_path.is_file() else None,
        "metadata": metadata,
        "elapsed_seconds": elapsed,
    }


def run_record(record: dict[str, Any], config: Any, acquisition_by_unit: dict[str, Any]) -> dict[str, Any]:
    from doc_extraction.cli import process_file
    from doc_extraction.utils.table_telemetry import TableTelemetryRecorder

    require_development(record)
    unit_id = record["unit_id"]
    image_path = HERE / "results" / "source" / "PNG" / record["file_name"]
    run_dir = RESULT_ROOT / unit_id
    telemetry_path = run_dir / "table_telemetry.json"
    result_file = run_dir / "result.json"
    expected_hash = acquisition_by_unit[unit_id]["source_image_sha256"]
    actual_hash = sha256_path(image_path)
    if actual_hash != expected_hash:
        raise RuntimeError(f"frozen source hash changed for {unit_id}")

    recorder = TableTelemetryRecorder(
        experiment_id="042_doclaynet_disjoint_scout",
        run_id=f"baseline-{unit_id}",
        context={
            "unit_id": unit_id,
            "split": record["split"],
            "image_id": record["image_id"],
            "source_group": record["source_group"],
            "population_hash": EXPECTED_POPULATION_HASH,
            "treatment_executed": False,
            "baseline_only": True,
        },
    )
    start = time.perf_counter()
    try:
        document = process_file(
            image_path,
            config,
            backend_name="baseline",
            output_dir=run_dir,
            table_telemetry=recorder,
        )
        elapsed = time.perf_counter() - start
        recorder.write_atomic(telemetry_path, status="complete")
        summary = summarize_document(document, run_dir, elapsed)
        payload = {
            "unit_id": unit_id,
            "split": record["split"],
            "image_id": record["image_id"],
            "file_name": record["file_name"],
            "source_group": record["source_group"],
            "doc_category": record["doc_category"],
            "source_image_sha256": actual_hash,
            "status": "COMPLETE",
            "baseline_only": True,
            "treatment_executed": False,
            "telemetry_path": str(telemetry_path.relative_to(HERE)),
            "output_path": str(run_dir.relative_to(HERE)),
            "telemetry_record_count": len(recorder.records),
            "invocation_modes": sorted({item.get("invocation_mode") for item in recorder.records if item.get("record_kind") == "specialist_invocation"}),
            "summary": summary,
        }
    except Exception as exc:  # noqa: BLE001 - preserve operational evidence per page
        elapsed = time.perf_counter() - start
        recorder.write_atomic(telemetry_path, status="failure", error=f"{type(exc).__name__}: {exc}")
        payload = {
            "unit_id": unit_id,
            "split": record["split"],
            "image_id": record["image_id"],
            "file_name": record["file_name"],
            "source_group": record["source_group"],
            "doc_category": record["doc_category"],
            "source_image_sha256": actual_hash,
            "status": "OPERATIONAL_FAILURE",
            "baseline_only": True,
            "treatment_executed": False,
            "telemetry_path": str(telemetry_path.relative_to(HERE)),
            "output_path": str(run_dir.relative_to(HERE)),
            "telemetry_record_count": len(recorder.records),
            "invocation_modes": sorted({item.get("invocation_mode") for item in recorder.records if item.get("record_kind") == "specialist_invocation"}),
            "error": f"{type(exc).__name__}: {exc}",
            "elapsed_seconds": elapsed,
        }
    atomic_write_json(result_file, payload)
    return payload


def run(mode: str) -> int:
    population, acquisition = validate_frozen_inputs()
    if mode == "group_sample":
        records = select_group_sample(population["records"])
    elif mode == "all":
        records = sorted(population["records"], key=lambda record: (record["source_group"], int(record["image_id"])))
    else:
        raise ValueError(mode)

    RESULT_ROOT.mkdir(parents=True, exist_ok=True)
    index = initial_index(population["population_hash"], mode, records)
    current_index_path = index_path(mode)
    if current_index_path.is_file():
        old = read(current_index_path)
        if old.get("population_hash") != EXPECTED_POPULATION_HASH:
            raise RuntimeError("existing baseline index belongs to a different frozen population")
        if old.get("mode") != mode:
            raise RuntimeError("existing baseline index mode differs; use a separate output namespace")
        index = old
    atomic_write_json(current_index_path, index)
    from doc_extraction.config import load_config

    config = load_config(ROOT / "configs/cpu.yaml")
    if config.device != "cpu":
        raise RuntimeError(f"042 baseline requires CPU, got {config.device!r}")
    acquisition_by_unit = {item["unit_id"]: item for item in acquisition["records"]}
    for ordinal, record in enumerate(records, 1):
        unit_id = record["unit_id"]
        existing = index["records"].get(unit_id, {})
        existing_result = result_path(unit_id)
        if existing.get("status") == "COMPLETE" and existing_result.is_file() and (RESULT_ROOT / unit_id / "table_telemetry.json").is_file():
            print(json.dumps({"completed": ordinal, "total": len(records), "unit_id": unit_id, "resumed": True}), flush=True)
            continue
        payload = run_record(record, config, acquisition_by_unit)
        index["records"][unit_id] = {
            "unit_id": unit_id,
            "image_id": record["image_id"],
            "source_group": record["source_group"],
            "status": payload["status"],
            "error": payload.get("error"),
            "invocation_modes": payload.get("invocation_modes", []),
        }
        atomic_write_json(current_index_path, index)
        done = sum(item.get("status") in {"COMPLETE", "OPERATIONAL_FAILURE"} for item in index["records"].values())
        print(json.dumps({"completed": done, "total": len(records), "unit_id": unit_id, "status": payload["status"], "modes": payload.get("invocation_modes", [])}), flush=True)
    failures = sum(item.get("status") == "OPERATIONAL_FAILURE" for item in index["records"].values())
    index["status"] = "BASELINE_PROVENANCE_COMPLETE" if all(item.get("status") == "COMPLETE" for item in index["records"].values()) else "BASELINE_PROVENANCE_INCOMPLETE"
    index["operational_failures"] = failures
    index["completed_records"] = sum(item.get("status") == "COMPLETE" for item in index["records"].values())
    index["treatment_executed"] = False
    index["heldout_accessed"] = False
    atomic_write_json(current_index_path, index)
    print(json.dumps({"status": index["status"], "completed": index["completed_records"], "total": len(records), "failures": failures}), flush=True)
    return 0 if index["status"] == "BASELINE_PROVENANCE_COMPLETE" else 2


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("group_sample", "all"), default="group_sample")
    args = parser.parse_args()
    return run(args.mode)


if __name__ == "__main__":
    raise SystemExit(main())
