#!/usr/bin/env python3
"""Audit the frozen 042 scout population and acquired source bytes."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
POPULATION = HERE / "population_manifest.json"
ACQUISITION = HERE / "ACQUISITION_MANIFEST.json"
CANONICAL_ACQUISITION = HERE / "ACQUISITION_MANIFEST.json"
PNG_ROOT = HERE / "results" / "source" / "PNG"
EXPECTED_POPULATION_HASH = "4d2ff975ec30d3c5c074bc858620dab856decbcabfdcd751c3861d8cdea0655e"
HELDOUT_SPLITS = frozenset({"heldout", "held_out", "held_out_test", "test"})


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_population_hash(payload: dict[str, Any]) -> str:
    content = dict(payload)
    content.pop("population_hash", None)
    return hashlib.sha256(
        json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


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


def nested_values(value: Any, keys: set[str], out: set[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in keys and isinstance(child, str):
                out.add(child)
            nested_values(child, keys, out)
    elif isinstance(value, list):
        for child in value:
            nested_values(child, keys, out)


def prior_identity_sets() -> dict[str, dict[str, set[str]]]:
    """Collect only exact identity evidence; no treatment outcomes are read."""
    sets: dict[str, dict[str, set[str]]] = {}

    # 035 is a separate historical corpus. Its manifests expose source image
    # names, but do not provide a complete source-group key or universal hash.
    names: set[str] = set()
    hashes: set[str] = set()
    groups: set[str] = set()
    for path in (ROOT / "experiments/035_mechanism_d_gating").rglob("*.json"):
        try:
            data = read(path)
        except (OSError, json.JSONDecodeError):
            continue
        nested_values(data, {"image", "file_name", "rendered_image"}, names)
        nested_values(data, {"source_image_sha256", "image_sha256", "rendered_image_sha256"}, hashes)
        nested_values(data, {"doc_group", "source_group", "source_document_id"}, groups)
    sets["035"] = {"names": names, "hashes": hashes, "groups": groups}

    # 036's exact image hashes and source identities are available in its
    # frozen population.  037 is synthetic and contributes rendered hashes.
    for experiment in ("036_mechanism_d_counterfactual", "037_selective_policy_validation"):
        names, hashes, groups = set(), set(), set()
        for path in (ROOT / "experiments" / experiment).rglob("*.json"):
            try:
                data = read(path)
            except (OSError, json.JSONDecodeError):
                continue
            nested_values(data, {"image", "file_name", "rendered_image"}, names)
            nested_values(data, {"source_image_sha256", "image_sha256", "rendered_image_sha256"}, hashes)
            nested_values(data, {"doc_group", "source_group", "source_document_id"}, groups)
        sets[experiment[:3]] = {"names": names, "hashes": hashes, "groups": groups}

    # 038/039 are the source annotation populations; 040/041 are subsets or
    # derived units. Keep them separate so held-out overlap is reportable.
    for number, path in (
        ("038", ROOT / "experiments/038_independent_real_corpus/population_manifest.json"),
        ("039", ROOT / "experiments/039_larger_real_corpus/population_manifest.json"),
        ("040", ROOT / "experiments/040_mechanism_d_counterfactual/population_manifest.json"),
        ("041", ROOT / "experiments/041_role_signal_provenance/population_manifest.json"),
    ):
        data = read(path)
        names, hashes, groups = set(), set(), set()
        nested_values(data, {"image", "file_name", "rendered_image"}, names)
        nested_values(data, {"source_image_sha256", "image_sha256", "rendered_image_sha256"}, hashes)
        nested_values(data, {"doc_group", "source_group", "source_document_id"}, groups)
        sets[number] = {"names": names, "hashes": hashes, "groups": groups}
    return sets


def audit() -> dict[str, Any]:
    population = read(POPULATION)
    expected_hash = population.get("population_hash")
    recomputed_hash = canonical_population_hash(population)
    if expected_hash != EXPECTED_POPULATION_HASH or recomputed_hash != EXPECTED_POPULATION_HASH:
        raise RuntimeError("frozen 042 population hash mismatch")
    if len(population.get("records", [])) != 279:
        raise RuntimeError("frozen 042 population record count changed")

    acquisition = read(ACQUISITION)
    records = acquisition.get("records", [])
    by_unit = {record.get("unit_id"): record for record in records}
    pop_by_unit = {record.get("unit_id"): record for record in population["records"]}
    errors: list[str] = []
    if acquisition.get("population_hash") != EXPECTED_POPULATION_HASH:
        errors.append("acquisition population hash mismatch")
    if len(records) != 279 or set(by_unit) != set(pop_by_unit):
        errors.append("acquisition ledger does not cover exactly the frozen 279 units")
    if any(record.get("split") != "development" for record in records):
        errors.append("non-development acquisition record")
    if acquisition.get("heldout_accessed") is not False:
        errors.append("heldout_accessed is not false")

    actual_hashes: dict[str, str] = {}
    missing: list[str] = []
    hash_mismatches: list[str] = []
    identity_mismatches: list[str] = []
    for unit_id, record in by_unit.items():
        population_record = pop_by_unit.get(unit_id)
        if population_record is None:
            continue
        if any(record.get(key) != population_record.get(key) for key in ("image_id", "file_name", "source_group", "doc_category", "page_no", "split")):
            identity_mismatches.append(str(unit_id))
        path = PNG_ROOT / str(record.get("file_name"))
        if not path.is_file():
            missing.append(str(unit_id))
            continue
        actual = sha256_path(path)
        actual_hashes[str(unit_id)] = actual
        if actual != record.get("source_image_sha256"):
            hash_mismatches.append(str(unit_id))
    if len(actual_hashes) != 279:
        errors.append("not all frozen source images are present")
    if missing:
        errors.append(f"missing images: {len(missing)}")
    if hash_mismatches:
        errors.append(f"image hash mismatches: {len(hash_mismatches)}")
    if identity_mismatches:
        errors.append(f"source identity mismatches: {len(identity_mismatches)}")

    image_ids = [record.get("image_id") for record in records]
    file_names = [record.get("file_name") for record in records]
    groups = [record.get("source_group") for record in records]
    duplicates = {
        "image_id": sorted(value for value, count in __import__("collections").Counter(image_ids).items() if count > 1),
        "file_name": sorted(value for value, count in __import__("collections").Counter(file_names).items() if count > 1),
        "source_image_sha256": sorted(value for value, count in __import__("collections").Counter(actual_hashes.values()).items() if count > 1),
    }
    if any(duplicates.values()):
        errors.append("duplicate image identity")

    prior = prior_identity_sets()
    new_names = set(file_names)
    new_hashes = set(actual_hashes.values())
    new_groups = set(groups)
    overlaps: dict[str, dict[str, list[str]]] = {}
    for number, identity in prior.items():
        overlaps[number] = {
            "file_names": sorted(new_names & identity["names"]),
            "image_hashes": sorted(new_hashes & identity["hashes"]),
            "source_groups": sorted(new_groups & identity["groups"]),
        }
        if any(overlaps[number].values()):
            errors.append(f"identity overlap with {number}")

    heldout_039 = {
        record.get("image_id")
        for record in read(ROOT / "experiments/039_larger_real_corpus/population_manifest.json")["records"]
        if record.get("split") in HELDOUT_SPLITS
    }
    new_ids = set(image_ids)
    heldout_group = {
        record.get("doc_group")
        for record in read(ROOT / "experiments/039_larger_real_corpus/population_manifest.json")["records"]
        if record.get("split") in HELDOUT_SPLITS
    }
    heldout_overlap = {
        "image_ids": sorted(new_ids & heldout_039),
        "source_groups": sorted(new_groups & heldout_group),
    }
    if any(heldout_overlap.values()):
        errors.append("039 heldout identity overlap")

    payload = {
        "experiment": "042_doclaynet_disjoint_scout",
        "status": "PASS" if not errors else "FAIL",
        "code_commit": git_head(),
        "population_hash": EXPECTED_POPULATION_HASH,
        "heldout_accessed": False,
        "counts": {
            "frozen_population": len(population["records"]),
            "acquisition_records": len(records),
            "files_present": len(actual_hashes),
            "missing_images": len(missing),
            "image_hash_mismatches": len(hash_mismatches),
            "source_identity_mismatches": len(identity_mismatches),
            "source_groups": len(new_groups),
            "categories": len({record.get("doc_category") for record in records}),
        },
        "duplicates": duplicates,
        "identity_overlaps": overlaps,
        "039_heldout_overlap": heldout_overlap,
        "errors": errors,
        "audit_scope": {
            "source_hashes_are_sha256_of_exact_archive_member_bytes": True,
            "prior_outcomes_used": False,
            "gt_used_for_population_selection": False,
            "treatment_used": False,
        },
    }
    atomic_write_json(HERE / "ACQUISITION_INTEGRITY.json", payload)
    atomic_write_json(CANONICAL_ACQUISITION, acquisition)
    return payload


def main() -> int:
    payload = audit()
    print(json.dumps({"status": payload["status"], **payload["counts"], "errors": payload["errors"]}))
    return 0 if payload["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
