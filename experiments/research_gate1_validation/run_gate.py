"""Bounded Gate 1 validity analysis over completed 046 artifacts.

This script performs no extraction.  It deliberately distinguishes a truth
unit with no token centre from a truth unit proven never acquired: the latter
cannot be inferred from an acquisition ledger alone.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from doc_extraction.evaluation.evidence_integrity import classify_loss_boundary


RUN = ROOT / "experiments/046_independent_corpus_challenge/runs/2026-10-01_protocol-v2_independent-corpus.json"
MANIFEST = ROOT / "experiments/046_independent_corpus_challenge/population_manifest.json"
STAGES = ROOT / "experiments/046_independent_corpus_challenge/runs/2026-10-01_protocol-v2_stage_outputs"
OUT = HERE / "gate1_results_v2.json"


def _intersects(a: dict, b: dict) -> bool:
    return max(a["x0"], b["x0"]) < min(a["x1"], b["x1"]) and max(a["y0"], b["y0"]) < min(a["y1"], b["y1"])


def _faults() -> list[dict]:
    # Each row removes exactly one stage signal from an otherwise preserved
    # observation. This validates functional discrimination, not causal
    # identification of a real pipeline boundary.
    states = [
        ("FI-ACQ", "acquisition", dict(acquisition_present=False, canonical_exact_present=False, canonical_normalized_present=False, serialized_present=False, ownership_conflict=False)),
        ("FI-OWN", "ownership", dict(acquisition_present=True, canonical_exact_present=False, canonical_normalized_present=False, serialized_present=False, ownership_conflict=True)),
        ("FI-REC", "reconciliation", dict(acquisition_present=True, canonical_exact_present=False, canonical_normalized_present=False, serialized_present=False, ownership_conflict=False, reconciliation_missing=True)),
        ("FI-PROJ", "canonical_projection", dict(acquisition_present=True, canonical_exact_present=False, canonical_normalized_present=False, serialized_present=False, ownership_conflict=False)),
        ("FI-SER", "serialization", dict(acquisition_present=True, canonical_exact_present=True, canonical_normalized_present=True, serialized_present=False, ownership_conflict=False)),
        ("FI-NORM", "normalization", dict(acquisition_present=True, canonical_exact_present=False, canonical_normalized_present=True, serialized_present=True, ownership_conflict=False)),
    ]
    rows = []
    for identifier, intended, kwargs in states:
        detected = classify_loss_boundary(**kwargs).value
        rows.append({"id": identifier, "intended_boundary": intended, "detected_boundary": detected,
                     "correct": intended == detected,
                     "ambiguity": "functional-only: state inputs are injected, not independently observed pipeline events"})
    return rows


def main() -> int:
    run = json.loads(RUN.read_text())
    manifest = {row["case_id"]: row for row in json.loads(MANIFEST.read_text())["cases"]}
    units, no_centre = [], []
    for case in run["per_case"]:
        item = manifest[case["case_id"]]
        candidates = case["candidates"]
        any_candidate = bool(candidates)
        correct = [row for row in candidates if row["truth_correct"]]
        valid = [row for row in correct if row["ownership_valid"]]
        canonical = [row for row in correct if row["duplicate_baseline"]]
        serialized = [row for row in canonical if row["loss_boundary"] != "serialization"]
        provenance = [row for row in correct if row["provenance_complete"]]
        unit = {
            "case_id": case["case_id"], "case_role": case["case_role"], "source_group_id": case["source_group_id"],
            "truth_unit": f"{case['source_image']}:{case['truth']['annotation_id']}", "truth_exists": True,
            "ocr_token_centre_in_truth_locator": any_candidate,
            "acquired_exact_truth_text": bool(correct), "ownership_valid": bool(valid),
            "canonical_text_present": bool(canonical), "serialized": bool(serialized),
            "provenance_complete": bool(provenance), "candidate_count": len(candidates),
        }
        units.append(unit)
        if case["case_role"] != "challenge" or any_candidate:
            continue
        truth = item["truth"]["locator"]
        ocr = json.loads((STAGES / case["case_id"] / "B/ocr/page-001.json").read_text())["tokens"]
        layout = json.loads((STAGES / case["case_id"] / "B/layout/page-001.json").read_text())["regions"]
        overlaps = [token for token in ocr if _intersects(truth, token["bbox"])]
        role_overlaps = [region["label"] for region in layout if _intersects(truth, region["bbox"])]
        dimensions = Image.open(ROOT / item["input_path"]).size
        within_image = 0 <= truth["x0"] < truth["x1"] <= dimensions[0] and 0 <= truth["y0"] < truth["y1"] <= dimensions[1]
        if not within_image:
            explanation = "LIKELY truth-locator coordinate/clipping mismatch"
            basis = "truth locator exceeds rendered image bounds; no centre-based acquisition conclusion is valid"
        elif overlaps:
            explanation = "LIKELY evaluator geometry/annotation-segmentation mismatch"
            basis = "OCR and layout spans intersect truth, but their centres are outside the truth box"
        else:
            explanation = "LIKELY insufficient OCR coverage at truth region"
            basis = "no OCR or layout span intersects the valid image-coordinate truth box"
        no_centre.append({"case_id": case["case_id"], "explanation": explanation, "evidence": basis,
                          "confidence": "LIKELY", "image_dimensions": dimensions, "truth_within_image": within_image,
                          "ocr_token_count": len(ocr), "intersecting_ocr_tokens": len(overlaps),
                          "intersecting_layout_roles": role_overlaps, "ocr_examples": [token["text"] for token in overlaps[:2]]})
    totals = {key: sum(unit[key] for unit in units) for key in (
        "truth_exists", "ocr_token_centre_in_truth_locator", "acquired_exact_truth_text", "ownership_valid",
        "canonical_text_present", "serialized", "provenance_complete")}
    conflicts = [case for case in run["per_case"] for row in case["candidates"]
                 if row["truth_correct"] and (row["ownership_claims"] or 0) > 1]
    baseline = sum(unit["ownership_valid"] for unit in units)
    oracle = baseline + len({case["case_id"] for case in conflicts})
    result = {
        "experiment": "research_gate1_validation", "source_run": str(RUN.relative_to(ROOT)),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(), "truth_unit_definition": "one frozen OmniDocBench text annotation selected per 046 case",
        "units": units, "totals": totals, "challenge_no_token_centre": no_centre,
        "prompt_count_reconciliation": {"prompt_claim": 8, "stored_v2_artifact_count": len(no_centre),
                                        "note": "stored v2 run is authoritative; no additional cases meet its no-centre predicate"},
        "fault_injection": _faults(),
        "oracle_reconciliation": {"unit_denominator": len(units), "baseline_truth_correct_uniquely_owned": baseline,
                                  "liberal_truth_oracle": oracle, "gap": oracle - baseline,
                                  "conflicted_truth_correct_candidates": len(conflicts),
                                  "limitation": "truth annotations do not label a canonical owner; oracle only establishes existence of a claim, not a uniquely correct owner"},
        "limitations": [
            "A no-token-centre event is not proof of acquisition loss.",
            "Fault injection tests deterministic classifier discrimination, not causal stage identification in a live pipeline.",
            "The truth unit does not contain owner identity, so a true ownership oracle is unavailable.",
        ],
    }
    result["script_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    if OUT.exists():
        raise SystemExit(f"refusing to overwrite immutable analysis: {OUT}")
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"totals": totals, "no_token_centre": len(no_centre), "oracle": result["oracle_reconciliation"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
