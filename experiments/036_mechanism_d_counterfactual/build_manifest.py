#!/usr/bin/env python
"""Freeze 036 inputs from the completed 035 evidence, without inference."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
E035 = ROOT / "experiments" / "035_mechanism_d_gating"
FULL = ROOT / "experiments" / "034a_omnidocbench_snapshot" / "dataset" / "full"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def bbox_for_region(record: dict, index: int, regions: list[dict]) -> dict:
    if 0 <= index < len(regions):
        return regions[index]["bbox"]
    for candidate in record["top_candidates"]:
        if candidate["region_index"] == index:
            return candidate["bbox"]
    raise ValueError(f"region {index} absent for {record['image']}")


def run_for_identity(root: Path, image: str) -> Path:
    """Find exactly one complete run under a root selected by 035's ledger."""
    matches = []
    for run_dir in root.iterdir():
        required = ("metadata.json", "layout/page-001.json", "final/document.json")
        if not run_dir.is_dir() or not all((run_dir / item).is_file() for item in required):
            continue
        if json.loads((run_dir / "metadata.json").read_text())["input_filename"] == image:
            matches.append(run_dir)
    if len(matches) != 1:
        raise RuntimeError(f"expected one complete preserved run for {image} under {root}, found {len(matches)}")
    return matches[0]


def treatment_runs() -> dict[str, Path]:
    """Use exactly the validation-gated GT roots selected by 035 itself."""
    import sys

    sys.path.insert(0, str(E035))
    import matching_lib as matching  # noqa: PLC0415

    result: dict[str, Path] = {}
    for root in matching.gt_table_run_roots(E035):
        for run_dir in root.iterdir():
            required = ("metadata.json", "layout/page-001.json", "final/document.json")
            if not run_dir.is_dir() or not all((run_dir / item).is_file() for item in required):
                continue
            image = json.loads((run_dir / "metadata.json").read_text())["input_filename"]
            if image in result:
                raise RuntimeError(f"duplicate validated GT identity: {image}")
            result[image] = run_dir
    return result


def control_runs() -> dict[str, Path]:
    """Use the Phase 13 identity ledger, not a broad results-tree glob."""
    ledger = json.loads((E035 / "phase13_identity_ledger.json").read_text())
    result = {}
    for identity in ledger["identities"]:
        root = E035 / identity["run_root"] / "_doc_extraction_runs"
        result[identity["image_name"]] = run_for_identity(root, identity["image_name"])
    if len(result) != 150:
        raise RuntimeError(f"Phase 13 ledger produced {len(result)} controls, expected 150")
    return result


def is_strict_d2(record: dict) -> bool:
    if record["verdict"] == "MULTIPLE_MATCH":
        contributors = record.get("multiple_match_contributors") or []
        return bool(contributors) and any(not item["table_gate_pass"] for item in contributors)
    region = record.get("matched_region")
    # 035's closure explicitly establishes no wrong-label recovery path.
    return region is not None and not region["table_gate_pass"] and record["final_table_object"] is None


def main() -> int:
    matching_path = E035 / "table_region_matching.json"
    phase13_path = E035 / "non_table_sample_manifest.json"
    matching = json.loads(matching_path.read_text())
    phase13 = json.loads(phase13_path.read_text())
    treatments_by_image = treatment_runs()
    controls_by_image = control_runs()

    treatments: list[dict] = []
    for record in matching["records"]:
        if not is_strict_d2(record):
            continue
        run = treatments_by_image[record["image"]]
        layout = json.loads((run / "layout/page-001.json").read_text())
        regions = layout["regions"]
        targets: list[dict] = []
        if record["verdict"] == "MULTIPLE_MATCH":
            candidates = [item for item in record["multiple_match_contributors"] if not item["table_gate_pass"]]
        else:
            candidates = [record["matched_region"]]
        for item in candidates:
            index = item["region_index"]
            targets.append({
                "region_index": index,
                "label": item["internal_label_raw"],
                "bbox": bbox_for_region(record, index, regions),
            })
        image_path = FULL / "images" / record["image"]
        if not image_path.is_file():
            raise FileNotFoundError(image_path)
        treatments.append({
            "case_id": f"d2-{len(treatments):02d}",
            "image": record["image"],
            "gt_table_anno_id": record["gt_table_anno_id"],
            "gt_bbox_px": record["gt_bbox_px"],
            "match_verdict": record["verdict"],
            "route": record["route"],
            "layout_backend": record["layout_backend"],
            "targets": targets,
            "source_image_sha256": sha256(image_path),
            "source_run": str(run.relative_to(ROOT)),
            "source_layout_sha256": sha256(run / "layout/page-001.json"),
            "source_document_sha256": sha256(run / "final/document.json"),
        })
    if len(treatments) != 34:
        raise RuntimeError(f"035 D2 identity reconstruction yielded {len(treatments)}, expected 34")

    # One fixed primary non-table region from every pre-existing, stratified
    # Phase 13 no-GT-table page. Largest area gives a meaningful opportunity
    # for a false table while avoiding outcome-dependent selection.
    controls: list[dict] = []
    excluded_controls: list[dict] = []
    for image in sorted(phase13["image_names"]):
        run = controls_by_image[image]
        regions = json.loads((run / "layout/page-001.json").read_text())["regions"]
        eligible = [
            (index, region) for index, region in enumerate(regions)
            if region.get("label", "").lower() != "table"
            and region["bbox"]["x1"] > region["bbox"]["x0"]
            and region["bbox"]["y1"] > region["bbox"]["y0"]
        ]
        if not eligible:
            # A no-GT-table page with only table-labelled layout regions is
            # Phase 13's distinct false-positive finding, not a valid
            # non-table-region crop for this arm. Preserve rather than
            # silently discard this pre-inference exclusion.
            excluded_controls.append({"image": image, "reason": "no_non_table_layout_region"})
            continue
        index, region = max(
            eligible,
            key=lambda item: (
                (item[1]["bbox"]["x1"] - item[1]["bbox"]["x0"])
                * (item[1]["bbox"]["y1"] - item[1]["bbox"]["y0"]),
                -item[0],
            ),
        )
        image_path = FULL / "images" / image
        controls.append({
            "case_id": f"control-{len(controls):03d}", "image": image,
            "region_index": index, "label": region["label"], "bbox": region["bbox"],
            "source_image_sha256": sha256(image_path),
            "source_run": str(run.relative_to(ROOT)),
            "source_layout_sha256": sha256(run / "layout/page-001.json"),
            "source_document_sha256": sha256(run / "final/document.json"),
        })
    if len(controls) + len(excluded_controls) != 150:
        raise RuntimeError("frozen Phase 13 control accounting does not sum to 150")

    artifacts = {path.name: sha256(path) for path in (matching_path, phase13_path, E035 / "final_evidence_index.json")}
    payload = {
        "experiment": "036_mechanism_d_counterfactual",
        "source_commit": "877d834ef11d4536fc443b83762ffc39d1fd9806",
        "source_artifact_sha256": artifacts,
        "selection": {
            "treatment": "all strict D2 identities reconstructed from frozen 035 matching evidence",
            "control": "largest-area non-table-labelled region per sorted frozen Phase 13 no-GT-table page",
        },
        "treatment_cases": treatments,
        "control_cases": controls,
        "excluded_control_pages": excluded_controls,
    }
    output = HERE / "population_manifest.json"
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {output}: 34 treatment cases, {len(controls)} eligible controls, "
          f"{len(excluded_controls)} explicit exclusions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
