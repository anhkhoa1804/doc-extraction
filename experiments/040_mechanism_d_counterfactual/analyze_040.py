#!/usr/bin/env python3
"""Analyze only completed Experiment 040 development outputs."""
from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
import sys

sys.path.insert(0, str(HERE))
from protocol import (
    CONTROL_KIND,
    TARGET_KIND,
    atomic_write_json,
    atomic_write_text,
    policy_fires,
)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def wilson(successes: int, total: int, z: float = 1.96) -> list[float] | None:
    if total == 0:
        return None
    p = successes / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    radius = z * ((p * (1 - p) / total + z * z / (4 * total * total)) ** 0.5) / denominator
    return [round(max(0.0, centre - radius), 6), round(min(1.0, centre + radius), 6)]


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    if len(values) == 1:
        return values[0]
    position = (len(values) - 1) * fraction
    lo, hi = int(position), min(len(values) - 1, int(position) + 1)
    weight = position - lo
    return values[lo] * (1 - weight) + values[hi] * weight


def load_phase(phase: str) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    manifest = read_json(HERE / "population_manifest.json")
    root = HERE / "results" / phase
    index = read_json(root / "run_index.json")
    records = []
    for unit in manifest["units"]:
        row = next((item for item in index.get("records", []) if item["unit_id"] == unit["unit_id"]), None)
        if row is None:
            continue
        path = HERE / row["result"]
        if path.is_file():
            records.append(read_json(path))
    return manifest, records, index


def require_pilot_integrity(manifest: dict[str, Any], records: list[dict[str, Any]], index: dict[str, Any]) -> dict[str, Any]:
    expected = list(manifest["pilot_unit_ids"])
    got = [record["unit"]["unit_id"] for record in records]
    checks = {
        "exact_pilot_ids": sorted(expected) == sorted(got),
        "all_complete": all(record.get("status") == "complete" for record in records),
        "all_development": all(record["unit"].get("split") == "development" for record in records),
        "all_labelled_crop": all(record.get("treatment", {}).get("specialist", {}).get("invocation_mode") == "LABELLED_CROP" for record in records),
        "bbox_matches_manifest": all(record.get("treatment", {}).get("treatment_input", {}).get("bbox_equal_to_frozen_manifest") is True for record in records),
        "crop_identity_present": all(bool(record.get("treatment", {}).get("treatment_input", {}).get("crop_sha256")) for record in records),
        "d2_count_at_least_two": sum(record["unit"]["kind"] == TARGET_KIND for record in records) >= 2,
        "control_count_at_least_two": sum(record["unit"]["kind"] == CONTROL_KIND for record in records) >= 2,
        "document_index_present": any(record["unit"].get("baseline_features", {}).get("normalized_role") == "document_index" for record in records),
        "non_document_index_d2_present": any(record["unit"]["kind"] == TARGET_KIND and record["unit"].get("baseline_features", {}).get("normalized_role") != "document_index" for record in records),
        "no_heldout_index_rows": all(row.get("split") == "development" for row in index.get("records", [])),
    }
    result = {"status": "PASS" if all(checks.values()) else "FAIL", "checks": checks, "records": len(records), "population_hash": manifest["population_hash"]}
    atomic_write_json(HERE / "results" / "pilot" / "pilot_integrity.json", result)
    if result["status"] != "PASS":
        raise SystemExit(f"pilot integrity failed: {json.dumps(result, sort_keys=True)}")
    return result


def require_full_integrity(manifest: dict[str, Any], records: list[dict[str, Any]], index: dict[str, Any]) -> dict[str, Any]:
    expected = {unit["unit_id"] for unit in manifest["units"]}
    got = {record.get("unit", {}).get("unit_id") for record in records}
    checks = {
        "exact_population_ids": expected == got,
        "all_complete": len(records) == len(expected) and all(record.get("status") == "complete" for record in records),
        "all_development": all(record.get("unit", {}).get("split") == "development" for record in records),
        "all_labelled_crop": all(record.get("treatment", {}).get("specialist", {}).get("invocation_mode") == "LABELLED_CROP" for record in records),
        "bbox_matches_manifest": all(record.get("treatment", {}).get("treatment_input", {}).get("bbox_equal_to_frozen_manifest") is True for record in records),
        "crop_identity_present": all(bool(record.get("treatment", {}).get("treatment_input", {}).get("crop_sha256")) for record in records),
        "no_heldout_index_rows": all(row.get("split") == "development" for row in index.get("records", [])),
    }
    result = {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "records": len(records),
        "expected_records": len(expected),
        "population_hash": manifest["population_hash"],
    }
    atomic_write_json(HERE / "results" / "full" / "full_integrity.json", result)
    if result["status"] != "PASS":
        raise SystemExit(f"full integrity failed: {json.dumps(result, sort_keys=True)}")
    return result


def treatment_summary(record: dict[str, Any]) -> dict[str, Any]:
    unit = record["unit"]
    evaluation = record.get("evaluation", {})
    return {
        "unit": unit,
        "unit_id": unit["unit_id"],
        "kind": unit["kind"],
        "role": unit["baseline_features"]["normalized_role"],
        "doc_group": unit["doc_group"],
        "category": unit["doc_category"],
        "shared_region": len(unit.get("linked_gt_tables", [])) > 1,
        "linked_gt_count": len(unit.get("linked_gt_tables", [])),
        "primary_outcome": evaluation.get("primary_outcome", "OPERATIONAL_FAILURE"),
        "detector_success": evaluation.get("detector_success", False),
        "structure_valid": evaluation.get("structure", {}).get("valid", False),
        "unique_owner": evaluation.get("ownership", {}).get("unique_intended_owner", False),
        "conflict": evaluation.get("ownership", {}).get("material_production_conflict", False),
        "cross_table_contamination": evaluation.get("ownership", {}).get("cross_table_overlap_count", 0) > 0,
        "serialization_damage": bool(evaluation.get("serialization_delta", {}).get("changed_existing_element_ids") or evaluation.get("serialization_delta", {}).get("missing_existing_element_ids") or evaluation.get("serialization_delta", {}).get("reading_order_changed")),
        "valid_recovery": evaluation.get("valid_recovery", False),
        "runtime_seconds": record.get("treatment", {}).get("specialist", {}).get("total_runtime_seconds"),
        "policy_fires": evaluation.get("policy_fires") or policy_fires(unit["baseline_features"]),
        "gt_evaluations": evaluation.get("gt_evaluations", []),
        "failure_tags": evaluation.get("failure_tags", []),
    }


def policy_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    policies = sorted({key for row in rows for key in row["policy_fires"]})
    output: dict[str, Any] = {}
    for policy in policies:
        selected = [row for row in rows if row["policy_fires"].get(policy, False)]
        targets = [row for row in selected if row["kind"] == TARGET_KIND]
        controls = [row for row in selected if row["kind"] == CONTROL_KIND]
        harmful = {"FALSE_POSITIVE", "OWNERSHIP_CONFLICT", "DUPLICATION_DAMAGE", "CROSS_TABLE_CONTAMINATION", "OPERATIONAL_FAILURE"}
        output[policy] = {
            "selected_total": len(selected),
            "selected_d2": len(targets),
            "selected_controls": len(controls),
            "valid_recovery": sum(row["valid_recovery"] for row in targets),
            "d2_recovery_rate": (sum(row["valid_recovery"] for row in targets) / len(targets)) if targets else None,
            "control_material_fp": sum(row["primary_outcome"] == "FALSE_POSITIVE" for row in controls),
            "control_harmful_or_conflict": sum(row["primary_outcome"] in harmful for row in controls),
            "control_outcomes": dict(Counter(row["primary_outcome"] for row in controls)),
        }
    # A frozen geometry-only comparator, registered before the treatment run.
    geometry = [row for row in rows if (row["unit"].get("baseline_features", {}).get("region_area_fraction") or 0) >= 0.4]
    targets = [row for row in geometry if row["kind"] == TARGET_KIND]
    controls = [row for row in geometry if row["kind"] == CONTROL_KIND]
    output["FROZEN_GEOMETRY_AREA_GE_0_4_NEGATIVE_COMPARATOR"] = {
        "selected_total": len(geometry),
        "selected_d2": len(targets),
        "selected_controls": len(controls),
        "valid_recovery": sum(row["valid_recovery"] for row in targets),
        "d2_recovery_rate": (sum(row["valid_recovery"] for row in targets) / len(targets)) if targets else None,
        "control_material_fp": sum(row["primary_outcome"] == "FALSE_POSITIVE" for row in controls),
        "control_harmful_or_conflict": sum(row["primary_outcome"] in {"FALSE_POSITIVE", "OWNERSHIP_CONFLICT", "DUPLICATION_DAMAGE", "CROSS_TABLE_CONTAMINATION", "OPERATIONAL_FAILURE"} for row in controls),
        "control_outcomes": dict(Counter(row["primary_outcome"] for row in controls)),
    }
    return output


def subgroup(rows: list[dict[str, Any]], field: str) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if field == "subtype":
            key = (row["unit"].get("d2_taxonomy") or {}).get("primary_mechanism_candidate") or "none"
        elif field == "ocr_bucket":
            count = row["unit"]["baseline_features"].get("ocr_child_count", 0)
            key = "0" if count == 0 else "1" if count == 1 else "2+"
        elif field == "shared_region":
            key = str(len(row["unit"].get("linked_gt_tables", [])) > 1).lower()
        elif field == "linked_gt_count":
            key = str(len(row["unit"].get("linked_gt_tables", [])))
        else:
            key = str(row["unit"].get(field))
        groups[key].append(row)
    output = {}
    for key, members in sorted(groups.items()):
        targets = [row for row in members if row["kind"] == TARGET_KIND]
        controls = [row for row in members if row["kind"] == CONTROL_KIND]
        output[key] = {
            "total": len(members),
            "d2_units": len(targets),
            "controls": len(controls),
            "valid_recovery": sum(row["valid_recovery"] for row in targets),
            "control_material_fp": sum(row["primary_outcome"] == "FALSE_POSITIVE" for row in controls),
            "outcomes": dict(Counter(row["primary_outcome"] for row in members)),
        }
    return output


def analyze_full(manifest: dict[str, Any], records: list[dict[str, Any]], index: dict[str, Any]) -> dict[str, Any]:
    # Operational failures remain in the experimental denominator and are
    # never relabelled as scientific no-effect outcomes.
    rows = [treatment_summary(record) for record in records]
    target_rows = [row for row in rows if row["kind"] == TARGET_KIND]
    control_rows = [row for row in rows if row["kind"] == CONTROL_KIND]
    runtimes = [float(row["runtime_seconds"]) for row in rows if row["runtime_seconds"] is not None]
    primary_counts = Counter(row["primary_outcome"] for row in rows)
    mode_counts = Counter(
        record.get("treatment", {}).get("specialist", {}).get("invocation_mode", "NOT_INVOKED")
        for record in records
    )
    detector_invocations = len(rows)
    structure_invocations = sum(
        1 + len(record.get("treatment", {}).get("specialist", {}).get("detector_tables", []))
        for record in records if record.get("status") == "complete"
    )
    valid = sum(row["valid_recovery"] for row in target_rows)
    control_fp = sum(row["primary_outcome"] == "FALSE_POSITIVE" for row in control_rows)
    harmful = {"FALSE_POSITIVE", "OWNERSHIP_CONFLICT", "DUPLICATION_DAMAGE", "CROSS_TABLE_CONTAMINATION", "OPERATIONAL_FAILURE"}
    control_harm = sum(row["primary_outcome"] in harmful for row in control_rows)
    operational = sum(record.get("status") != "complete" for record in records)
    groups_with_recovery = sorted({row["doc_group"] for row in target_rows if row["valid_recovery"]})
    shared_recovered = sum(row["valid_recovery"] and row["shared_region"] for row in target_rows)
    nonshared_recovered = sum(row["valid_recovery"] and not row["shared_region"] for row in target_rows)
    policy = policy_metrics(rows)
    geometry = policy["FROZEN_GEOMETRY_AREA_GE_0_4_NEGATIVE_COMPARATOR"]
    doc_policy = policy.get("POLICY_1_ROLE_ONLY_DOCUMENT_INDEX", {})
    falsification = {
        "A_document_index_vs_geometry": {
            "status": "PASS" if (doc_policy.get("control_material_fp", 0) <= geometry.get("control_material_fp", 0) and doc_policy.get("control_harmful_or_conflict", 0) <= geometry.get("control_harmful_or_conflict", 0)) else "FAIL",
            "evidence": {"document_index": doc_policy, "geometry": geometry},
        },
        "B_crop_specific_vs_page_wide": {
            "status": "INCONCLUSIVE",
            "evidence": "All 040 treatment calls were LABELLED_CROP; the frozen 039 baseline did not record invocation mode, so baseline page-wide absence cannot be inferred.",
        },
        "C_shared_region_concentration": {
            "status": "INCONCLUSIVE" if valid == 0 else ("FAIL" if nonshared_recovered == 0 else "PASS"),
            "evidence": {"shared_recoveries": shared_recovered, "nonshared_recoveries": nonshared_recovered},
        },
        "D_control_harm": {
            "status": "PASS" if control_harm == 0 else "FAIL",
            "evidence": {"harmful_or_conflict": control_harm, "denominator": len(control_rows), "outcomes": dict(Counter(row["primary_outcome"] for row in control_rows))},
        },
        "E_serialization_damage": {
            "status": "PASS" if not any(row["serialization_damage"] for row in rows) else "FAIL",
            "evidence": {"damaged_units": sum(row["serialization_damage"] for row in rows), "denominator": len(rows)},
        },
        "F_source_group_concentration": {
            "status": "INCONCLUSIVE" if valid == 0 else ("PASS" if len(groups_with_recovery) >= 2 else "FAIL"),
            "evidence": {"recovery_groups": groups_with_recovery},
        },
        "G_ocr_sparsity_confound": {
            "status": "INCONCLUSIVE",
            "evidence": "OCR buckets are reported descriptively; this study does not promote a bucket based on observed response.",
        },
        "H_duplicate_evidence": {
            "status": "PASS" if not any(row["serialization_damage"] for row in rows) else "FAIL",
            "evidence": {"damaged_or_duplicate_units": sum(row["serialization_damage"] for row in rows)},
        },
    }
    return {
        "status": "complete",
        "experiment": "040_mechanism_d_counterfactual",
        "population_hash": manifest["population_hash"],
        "records_loaded": len(records),
        "complete_records": sum(record.get("status") == "complete" for record in records),
        "d2_units": len(target_rows),
        "control_units": len(control_rows),
        "operational_failures": operational,
        "primary_outcomes": dict(primary_counts),
        "invocation": {
            "PAGE_WIDE": mode_counts.get("PAGE_WIDE", 0),
            "LABELLED_CROP": mode_counts.get("LABELLED_CROP", 0),
            "NOT_INVOKED": mode_counts.get("NOT_INVOKED", 0),
            "detector_invocations": detector_invocations,
            "structure_invocations": structure_invocations,
        },
        "d2_metrics": {
            "detector_success": sum(row["detector_success"] for row in target_rows),
            "structure_valid": sum(row["structure_valid"] for row in target_rows),
            "unique_owner": sum(row["unique_owner"] for row in target_rows),
            "conflict": sum(row["conflict"] for row in target_rows),
            "cross_table_contamination": sum(row["cross_table_contamination"] for row in target_rows),
            "valid_recovery": valid,
            "valid_recovery_rate": valid / len(target_rows) if target_rows else None,
            "valid_recovery_ci95": wilson(valid, len(target_rows)),
        },
        "control_metrics": {
            "NO_EFFECT": sum(row["primary_outcome"] == "NO_EFFECT" for row in control_rows),
            "FALSE_POSITIVE": control_fp,
            "OWNERSHIP_CONFLICT": sum(row["primary_outcome"] == "OWNERSHIP_CONFLICT" for row in control_rows),
            "DUPLICATION_DAMAGE": sum(row["primary_outcome"] == "DUPLICATION_DAMAGE" for row in control_rows),
            "CROSS_TABLE_CONTAMINATION": sum(row["primary_outcome"] == "CROSS_TABLE_CONTAMINATION" for row in control_rows),
            "OPERATIONAL_FAILURE": sum(row["primary_outcome"] == "OPERATIONAL_FAILURE" for row in control_rows),
            "material_fp_rate": control_fp / len(control_rows) if control_rows else None,
            "material_fp_ci95": wilson(control_fp, len(control_rows)),
            "harmful_or_conflict": control_harm,
            "harmful_or_conflict_rate": control_harm / len(control_rows) if control_rows else None,
        },
        "cost": {
            "total_runtime_seconds": round(sum(runtimes), 6),
            "median_runtime_seconds": statistics.median(runtimes) if runtimes else None,
            "mean_runtime_seconds": statistics.mean(runtimes) if runtimes else None,
            "p95_runtime_seconds": percentile(runtimes, 0.95),
            "runtime_denominator": len(runtimes),
            "device": "cpu",
        },
        "subgroups": {
            "raw_role": subgroup(rows, "raw_role"),
            "d2_subtype": subgroup(rows, "subtype"),
            "doc_group": subgroup(rows, "doc_group"),
            "category": subgroup(rows, "doc_category"),
            "shared_region": subgroup(rows, "shared_region"),
            "linked_gt_count": subgroup(rows, "linked_gt_count"),
            "ocr_bucket": subgroup(rows, "ocr_bucket"),
        },
        "policy_metrics": policy,
        "falsification": falsification,
        "heldout_accessed": False,
        "treatment_executed_on_heldout": False,
        "protocol_deviations": [],
    }


def write_analysis(phase: str, manifest: dict[str, Any], records: list[dict[str, Any]], index: dict[str, Any]) -> int:
    if phase == "pilot":
        result = require_pilot_integrity(manifest, records, index)
        print(json.dumps(result, sort_keys=True))
        return 0
    require_full_integrity(manifest, records, index)
    analysis = analyze_full(manifest, records, index)
    root = HERE / "results" / phase
    result_payload = read_json(root / "results.json") if (root / "results.json").is_file() else {"records": records}
    result_payload["analysis"] = analysis
    atomic_write_json(root / "results.json", result_payload)
    failure_counts = Counter()
    for record in records:
        if record.get("status") != "complete":
            failure_counts[record.get("status", "unknown")] += 1
        for tag in record.get("evaluation", {}).get("failure_tags", []):
            failure_counts[tag] += 1
    atomic_write_json(root / "failure_taxonomy.json", {
        "experiment": "040_mechanism_d_counterfactual",
        "definitions": read_json(HERE / "protocol.json")["failure_tags"],
        "counts": dict(failure_counts),
        "operational_failure_rate": analysis["operational_failures"] / len(records) if records else None,
        "stop_condition_exceeded": bool(records and analysis["operational_failures"] / len(records) > 0.1),
    })
    markdown = render_markdown(analysis)
    atomic_write_text(root / "ANALYSIS.md", markdown)
    atomic_write_json(HERE / "results.json", analysis)
    atomic_write_json(HERE / "failure_taxonomy.json", {
        "experiment": "040_mechanism_d_counterfactual",
        "definitions": read_json(HERE / "protocol.json")["failure_tags"],
        "counts": dict(failure_counts),
        "operational_failure_rate": analysis["operational_failures"] / len(records) if records else None,
        "stop_condition_exceeded": bool(records and analysis["operational_failures"] / len(records) > 0.1),
    })
    print(json.dumps({"status": analysis["status"], "d2": analysis["d2_metrics"], "controls": analysis["control_metrics"], "cost": analysis["cost"]}, sort_keys=True))
    return 1 if analysis["operational_failures"] / max(1, len(records)) > 0.1 else 0


def render_markdown(analysis: dict[str, Any]) -> str:
    d2 = analysis["d2_metrics"]
    control = analysis["control_metrics"]
    lines = [
        "# Experiment 040 analysis",
        "",
        "This report is a development-only paired counterfactual analysis. It does not evaluate held-out data or authorize production routing.",
        "",
        "## Integrity first",
        "",
        f"- Complete records: {analysis['complete_records']} (D2 units {analysis['d2_units']}; controls {analysis['control_units']}).",
        f"- Operational failures: {analysis['operational_failures']}; heldout_accessed = `{str(analysis['heldout_accessed']).lower()}`.",
        f"- Invocation modes: `{analysis['invocation']}`.",
        f"- Protocol deviations: `{analysis['protocol_deviations']}`.",
        "",
        "## D2 outcomes",
        "",
        f"- Detector success: {d2['detector_success']}/{analysis['d2_units']}",
        f"- Structure valid: {d2['structure_valid']}/{analysis['d2_units']}",
        f"- Unique owner: {d2['unique_owner']}/{analysis['d2_units']}",
        f"- Material conflict: {d2['conflict']}/{analysis['d2_units']}",
        f"- Cross-table contamination: {d2['cross_table_contamination']}/{analysis['d2_units']}",
        f"- Valid recovery: {d2['valid_recovery']}/{analysis['d2_units']} = {d2['valid_recovery_rate']}",
        f"- Approximate 95% binomial interval: {d2['valid_recovery_ci95']}",
        "",
        "## Control outcomes",
        "",
        f"- Material false positives: {control['FALSE_POSITIVE']}/{analysis['control_units']} = {control['material_fp_rate']}",
        f"- Harmful/conflict outcomes: {control['harmful_or_conflict']}/{analysis['control_units']} = {control['harmful_or_conflict_rate']}",
        f"- Primary outcomes: `{analysis['primary_outcomes']}`.",
        "",
        "## Cost",
        "",
        f"- Total runtime: {analysis['cost']['total_runtime_seconds']} seconds.",
        f"- Median / mean / p95 per unit: {analysis['cost']['median_runtime_seconds']} / {analysis['cost']['mean_runtime_seconds']} / {analysis['cost']['p95_runtime_seconds']} seconds.",
        f"- Detector invocations: {analysis['invocation']['detector_invocations']}; structure invocations: {analysis['invocation']['structure_invocations']}.",
        "",
        "## Policy evidence",
        "",
        "Policy indicators were frozen from pre-treatment features before outputs were read. The tables in `results.json` are descriptive development evidence only.",
        "",
        "## Falsification",
        "",
    ]
    for key, value in analysis["falsification"].items():
        lines.append(f"- **{key}**: {value['status']}; {value['evidence']}")
    lines += [
        "",
        "## Interpretation",
        "",
        "The treatment result is not a detector benchmark. A valid recovery requires structure, ownership, GT relevance, no production-table conflict, no duplication/damage, and the frozen crop-mode contract. Control outcomes and runtime are part of the decision; no held-out conclusion is permitted here.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("pilot", "full"), required=True)
    parser.add_argument("--require-pilot", action="store_true")
    args = parser.parse_args()
    manifest, records, index = load_phase(args.phase)
    if args.phase == "pilot":
        return write_analysis(args.phase, manifest, records, index)
    return write_analysis(args.phase, manifest, records, index)


if __name__ == "__main__":
    raise SystemExit(main())
