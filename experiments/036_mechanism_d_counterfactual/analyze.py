#!/usr/bin/env python
"""Aggregate immutable raw 036 case records into a compact tracked summary."""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent


def records(path: Path) -> list[dict]:
    return [json.loads(item.read_text()) for item in sorted(path.glob("*.json")) if item.name != "run_metadata.json"]


def rate(n: int, d: int) -> float | None:
    return round(n / d, 4) if d else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--treatment", type=Path, required=True)
    parser.add_argument("--control", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=HERE / "summary.json")
    args = parser.parse_args()
    treatment, control = records(args.treatment), records(args.control)
    manifest = json.loads((HERE / "population_manifest.json").read_text())
    expected_controls = len(manifest["control_cases"])
    if len(treatment) != 34 or len(control) != expected_controls:
        raise SystemExit(f"incomplete raw execution: treatments={len(treatment)}, controls={len(control)}")
    successful_treatment = [item for item in treatment if item["status"] == "success"]
    successful_control = [item for item in control if item["status"] == "success"]
    target_rows = [target for item in successful_treatment for target in item["targets"]]
    control_rows = [target for item in successful_control for target in item["targets"]]
    runtime = [item["case_runtime_seconds"] for item in treatment + control]
    payload = {
        "population": {"treatment_cases": 34, "control_cases": expected_controls,
                       "excluded_control_pages": len(manifest.get("excluded_control_pages", [])),
                       "treatment_targets": len(target_rows)},
        "execution": {
            "treatment_completed": len(successful_treatment), "treatment_failures": 34 - len(successful_treatment),
            "control_completed": len(successful_control), "control_failures": expected_controls - len(successful_control),
            "case_runtime_seconds": {"min": round(min(runtime), 4), "median": round(statistics.median(runtime), 4), "max": round(max(runtime), 4), "total": round(sum(runtime), 4)},
        },
        "treatment_case_level": {
            "specialist_invocation_success": sum(item["status"] == "success" for item in treatment),
            "crop_detector_found_table": sum(any(target["crop_detector_found_table"] for target in item.get("targets", [])) for item in treatment),
            "structurally_valid": sum(any(target["forced_crop_structural_validity"]["valid"] for target in item.get("targets", [])) for item in treatment),
            "ownership_established": sum(any(target["ownership_established_in_isolated_counterfactual"] for target in item.get("targets", [])) for item in treatment),
            "valid_recovery": sum(any(target["valid_recovery"] for target in item.get("targets", [])) for item in treatment),
            "duplicate_ownership": sum(any(target["duplicate_ownership"] for target in item.get("targets", [])) for item in treatment),
            "cross_region_conflict": sum(any(target["cross_region_conflict"] for target in item.get("targets", [])) for item in treatment),
        },
        "control_target_level": {
            "specialist_invocation_success": sum(target["specialist_invocation_success"] for target in control_rows),
            "crop_detector_found_table": sum(target["crop_detector_found_table"] for target in control_rows),
            "structurally_valid": sum(target["forced_crop_structural_validity"]["valid"] for target in control_rows),
            "ownership_established": sum(target["ownership_established_in_isolated_counterfactual"] for target in control_rows),
            "false_positive": sum(target["forced_crop_structural_validity"]["valid"] and target["ownership_established_in_isolated_counterfactual"] for target in control_rows),
            "duplicate_ownership": sum(target["duplicate_ownership"] for target in control_rows),
        },
    }
    for key in ("treatment_case_level", "control_target_level"):
        denominator = 34 if key == "treatment_case_level" else expected_controls
        payload[key]["rates"] = {name: rate(value, denominator) for name, value in payload[key].items() if isinstance(value, int)}
    args.output.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
