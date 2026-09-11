#!/usr/bin/env python3
"""Summarize 042 observational baseline telemetry without GT or treatment."""
from __future__ import annotations

import argparse
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
EXPECTED_POPULATION_HASH = "4d2ff975ec30d3c5c074bc858620dab856decbcabfdcd751c3861d8cdea0655e"


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


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


def summarize(mode: str) -> dict[str, Any]:
    index_name = "BASELINE_PROVENANCE_SAMPLE_INDEX.json" if mode == "group_sample" else "BASELINE_PROVENANCE_INDEX.json"
    index = read(HERE / index_name)
    population = read(POPULATION)
    if population.get("population_hash") != EXPECTED_POPULATION_HASH:
        raise RuntimeError("042 population hash mismatch")
    if index.get("population_hash") != EXPECTED_POPULATION_HASH:
        raise RuntimeError("baseline index population hash mismatch")
    if index.get("status") != "BASELINE_PROVENANCE_COMPLETE":
        raise RuntimeError(f"baseline index is not complete: {index.get('status')}")
    if index.get("heldout_accessed") is not False or index.get("treatment_executed") is not False:
        raise RuntimeError("heldout or treatment flag is unsafe")

    pages = []
    role_counts: Counter[str] = Counter()
    role_pages: defaultdict[str, set[int]] = defaultdict(set)
    role_groups: defaultdict[str, set[str]] = defaultdict(set)
    mode_counts: Counter[str] = Counter()
    table_count = cell_count = 0
    warnings = 0
    errors = 0
    failed_units: list[str] = []
    for unit_id, entry in sorted(index["records"].items()):
        result_path = HERE / "results" / "baseline_provenance" / unit_id / "result.json"
        telemetry_path = HERE / "results" / "baseline_provenance" / unit_id / "table_telemetry.json"
        result = read(result_path)
        telemetry = read(telemetry_path)
        if result.get("split") != "development" or telemetry.get("context", {}).get("split") != "development":
            raise RuntimeError(f"non-development baseline record: {unit_id}")
        if result.get("status") != "COMPLETE":
            failed_units.append(unit_id)
            continue
        invocations = [item for item in telemetry.get("records", []) if item.get("record_kind") == "specialist_invocation"]
        modes = {item.get("invocation_mode") for item in invocations}
        page_mode = "BOTH" if len(modes & {"PAGE_WIDE", "LABELLED_CROP"}) == 2 else next(iter(modes), "NONE")
        mode_counts[page_mode] += 1
        page_tables = sum(item.get("output", {}).get("table_count", 0) for item in invocations)
        page_cells = sum(sum(table.get("cell_count", 0) for table in item.get("output", {}).get("tables", [])) for item in invocations)
        table_count += page_tables
        cell_count += page_cells
        for item in invocations:
            warnings += len(item.get("output", {}).get("warnings", []))
            errors += len(item.get("output", {}).get("errors", []))
            for region in item.get("regions", []):
                role = str(region.get("raw_region_label", "")).strip().lower()
                role_counts[role] += 1
                image_id = int(result["image_id"])
                role_pages[role].add(image_id)
                role_groups[role].add(result["source_group"])
        pages.append({
            "unit_id": unit_id,
            "image_id": result["image_id"],
            "source_group": result["source_group"],
            "doc_category": result["doc_category"],
            "invocation_mode": page_mode,
            "specialist_invocation_count": len(invocations),
            "table_count": page_tables,
            "cell_count": page_cells,
            "region_count": sum(item.get("page_region_count", 0) for item in invocations),
        })

    all_records = list(index["records"].values())
    payload = {
        "experiment": "042_doclaynet_disjoint_scout",
        "status": "BASELINE_PROVENANCE_COMPLETE",
        "mode": mode,
        "code_commit": git_head(),
        "population_hash": EXPECTED_POPULATION_HASH,
        "heldout_accessed": False,
        "treatment_executed": False,
        "gt_used": False,
        "treatment_output_used": False,
        "counts": {
            "requested_pages": len(all_records),
            "complete_pages": len(pages),
            "operational_failures": len(failed_units),
            "page_wide": mode_counts["PAGE_WIDE"],
            "labelled_crop": mode_counts["LABELLED_CROP"],
            "both": mode_counts["BOTH"],
            "none": mode_counts["NONE"],
            "table_objects": table_count,
            "table_cells": cell_count,
            "telemetry_warnings": warnings,
            "telemetry_errors": errors,
        },
        "role_counts": dict(sorted(role_counts.items())),
        "role_page_counts": {role: len(values) for role, values in sorted(role_pages.items())},
        "role_source_group_counts": {role: len(values) for role, values in sorted(role_groups.items())},
        "natural_document_index_candidates": [],
        "failed_units": failed_units,
        "pages": pages,
        "interpretation_boundary": "Invocation mode is observed from telemetry; it is not inferred from D2 or table output. Role candidates are pre-treatment layout facts only.",
    }
    output_name = "BASELINE_PROVENANCE_SAMPLE.json" if mode == "group_sample" else "BASELINE_PROVENANCE.json"
    atomic_write_json(HERE / output_name, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("group_sample", "all"), default="group_sample")
    args = parser.parse_args()
    payload = summarize(args.mode)
    print(json.dumps({"status": payload["status"], "mode": payload["mode"], **payload["counts"], "role_counts": payload["role_counts"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
