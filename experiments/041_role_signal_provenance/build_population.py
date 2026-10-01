#!/usr/bin/env python3
"""Audit and freeze the Experiment 041 development population.

This builder deliberately stops before treatment when same-role controls are
unavailable. It reads frozen 039 layout artifacts only for development records
and never admits a held-out record.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
E039 = ROOT / "experiments" / "039_larger_real_corpus"
E040 = ROOT / "experiments" / "040_mechanism_d_counterfactual"
ALLOWED_SPLIT = "development"
HELDOUT_SPLITS = frozenset({"heldout", "held_out", "held_out_test", "test"})


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def git_head() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def require_development(record: dict[str, Any]) -> None:
    split = record.get("split")
    if split != ALLOWED_SPLIT:
        raise RuntimeError(f"Experiment 041 refuses non-development record: split={split!r}")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build(output: Path) -> dict[str, Any]:
    manifest = read(E039 / "population_manifest.json")
    records = manifest["records"]
    development = [record for record in records if record.get("split") == ALLOWED_SPLIT]
    if any(record.get("split") in HELDOUT_SPLITS for record in development):
        raise RuntimeError("held-out record entered development selection")
    if len(development) != 136:
        raise RuntimeError(f"039 development record count changed: {len(development)}")

    forensic = read(E039 / "039_D2_FORENSIC_CASES.json")["cases"]
    frozen_d2_keys = {
        (int(case["image_id"]), int(case["matched_region"]["region_index"]))
        for case in forensic
        if case.get("strict_d2") and case.get("split") == ALLOWED_SPLIT and case.get("matched_region")
    }
    if len(frozen_d2_keys) != 28:
        raise RuntimeError(f"frozen 039 development D2 identity count changed: {len(frozen_d2_keys)}")

    candidates: list[dict[str, Any]] = []
    for record in sorted(development, key=lambda item: int(item["image_id"])):
        require_development(record)
        image_id = int(record["image_id"])
        layout_path = E039 / "results" / "baseline_runs" / str(image_id) / "layout" / "page-001.json"
        if not layout_path.is_file():
            raise RuntimeError(f"missing frozen development layout: {layout_path}")
        layout = read(layout_path)
        for region_index, region in enumerate(layout.get("regions", [])):
            if str(region.get("label", "")).strip().lower() != "document_index":
                continue
            key = (image_id, region_index)
            candidates.append({
                "image_id": image_id,
                "file_name": record["file_name"],
                "source_document_id": record["source_document_id"],
                "doc_group": record["doc_group"],
                "doc_category": record["doc_category"],
                "page_no": record["page_no"],
                "split": record["split"],
                "region_index": region_index,
                "raw_role": region.get("label"),
                "region_bbox": region.get("bbox"),
                "baseline_layout_sha256": file_sha256(layout_path),
                "eligibility": "excluded_frozen_d2_identity" if key in frozen_d2_keys else "eligible_control",
            })

    eligible = [item for item in candidates if item["eligibility"] == "eligible_control"]
    if len(candidates) != 15:
        raise RuntimeError(f"document_index candidate count changed: {len(candidates)}")
    if len(eligible) != 0:
        raise RuntimeError("unexpected same-role controls appeared; review before proceeding")

    d2_targets = []
    d2_units = read(E040 / "population_manifest.json")["units"]
    for unit in d2_units:
        if unit["kind"] != "d2_region" or unit.get("raw_role", "").strip().lower() != "document_index":
            continue
        require_development(unit)
        d2_targets.append(unit["unit_id"])
    if len(d2_targets) != 15:
        raise RuntimeError(f"document_index D2 target count changed: {len(d2_targets)}")

    payload: dict[str, Any] = {
        "experiment": "041_role_signal_provenance",
        "status": "BLOCKED_BEFORE_EXECUTION_NO_SAME_ROLE_CONTROLS",
        "created_from_commit": git_head(),
        "source_manifest_sha256": file_sha256(E039 / "population_manifest.json"),
        "source_baseline_index_sha256": file_sha256(E039 / "results" / "baseline_run_index.json"),
        "source_040_population_hash": read(E040 / "population_manifest.json")["population_hash"],
        "split_guard": {"allowed": ALLOWED_SPLIT, "heldout_splits_rejected": sorted(HELDOUT_SPLITS), "heldout_accessed": False},
        "counts": {
            "039_total_records": len(records),
            "039_development_records": len(development),
            "039_heldout_records": sum(record.get("split") in HELDOUT_SPLITS for record in records),
            "document_index_candidates": len(candidates),
            "excluded_frozen_d2_identities": len(candidates) - len(eligible),
            "eligible_same_role_controls": len(eligible),
            "document_index_d2_targets": len(d2_targets),
        },
        "candidate_audit": candidates,
        "module_a_d2_target_unit_ids": sorted(d2_targets),
        "same_role_control_units": eligible,
        "module_b_sample": [],
        "module_c_cases": [],
        "treatment_executed": False,
        "heldout_accessed": False,
        "hard_stop": "No eligible same-role document_index development controls exist in the frozen 039 development baseline.",
    }
    payload["audit_hash"] = canonical_hash(payload)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(output)
    return payload


def main() -> int:
    payload = build(HERE / "population_manifest.json")
    print(json.dumps({"status": payload["status"], **payload["counts"], "treatment_executed": False}))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
