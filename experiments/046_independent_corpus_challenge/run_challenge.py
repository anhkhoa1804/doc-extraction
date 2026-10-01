"""Execute frozen Experiment 046 A/B acquisition-time challenge."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from doc_extraction.backends.docling_backend import DoclingBackend
from doc_extraction.backends.table_backend import TableTransformerBackend
from doc_extraction.evaluation.evidence_integrity import (
    Disposition, ObservationLedger, baseline_phrase_match, classify_loss_boundary,
    normalize_text, truth_exact_match,
)
from doc_extraction.pipelines.base import run_scanned_page_pipeline
from doc_extraction.schemas.document import Document, RunMetadata
from doc_extraction.schemas.element import BBox


def _contains(locator: dict[str, float], bbox: BBox) -> bool:
    x, y = (bbox.x0 + bbox.x1) / 2, (bbox.y0 + bbox.y1) / 2
    return locator["x0"] <= x <= locator["x1"] and locator["y0"] <= y <= locator["y1"]


def _page_texts(page, locator: dict[str, float]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    values = [element.text for element in page.elements if element.text and element.bbox and _contains(locator, element.bbox)]
    values.extend(cell.text for table in page.tables for cell in table.cells if cell.text and cell.bbox and _contains(locator, cell.bbox))
    raw = tuple(value for value in values if normalize_text(value))
    return raw, tuple(normalize_text(value) for value in raw)


def _raw_phrase(text: str | None, values: tuple[str, ...]) -> bool:
    return bool(text) and any(f" {text} " in f" {value} " for value in values)


def _markdown(page) -> str:
    metadata = RunMetadata(input_filename="e046-page", input_path="", file_hash_sha256="", file_type="image",
                           route="image", pipeline="baseline", backend="docling", timestamp="2026-10-01T00:00:00Z")
    return Document(document_id="e046-page", metadata=metadata, pages=[page]).to_markdown()


def _package_versions() -> dict[str, str | None]:
    result = {}
    for package in ("docling", "easyocr", "transformers", "torch", "pydantic"):
        try:
            result[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            result[package] = None
    return result


def _run_case(item: dict, docling: DoclingBackend, table: TableTransformerBackend, stage_root: Path) -> dict:
    image = ROOT / item["input_path"]
    ledger = ObservationLedger()
    # B captures real return objects; it makes no extraction decision.
    b_page = run_scanned_page_pipeline(image, 0, 200, docling, docling, table, stage_root / item["case_id"] / "B", observation_ledger=ledger)
    a_page = run_scanned_page_pipeline(image, 0, 200, docling, docling, table, stage_root / item["case_id"] / "A")
    equivalent = a_page.model_dump(mode="json") == b_page.model_dump(mode="json")
    locator = item["truth"]["locator"]
    truth = normalize_text(item["truth"]["text"])
    baseline_raw, baseline = _page_texts(a_page, locator)
    markdown = normalize_text(_markdown(a_page))
    projection = {record.observation_id: record for record in ledger.records}
    candidates = []
    for raw in ledger.acquisition_records:
        if raw.payload_kind != "ocr_token" or raw.geometry is None:
            continue
        bbox = BBox(x0=raw.geometry[0], y0=raw.geometry[1], x1=raw.geometry[2], y1=raw.geometry[3])
        if not _contains(locator, bbox):
            continue
        reconciled = projection.get(raw.observation_id)
        exact = _raw_phrase(raw.text, baseline_raw)
        normalized = baseline_phrase_match(raw.text, baseline)
        serialized = baseline_phrase_match(raw.text, (markdown,))
        claims = len(reconciled.candidate_claims) if reconciled else None
        ownership_valid = bool(reconciled and reconciled.disposition is Disposition.ACCEPTED and claims == 1)
        provenance_complete = reconciled is not None  # same deterministic raw observation id crosses the projection boundary
        correct = truth_exact_match(raw.text, (truth,))
        duplicate = normalized
        novel = bool(raw.text and correct and ownership_valid and provenance_complete and not duplicate)
        boundary = classify_loss_boundary(acquisition_present=True, canonical_exact_present=exact,
                                          canonical_normalized_present=normalized, serialized_present=serialized,
                                          ownership_conflict=bool(claims and claims > 1),
                                          reconciliation_missing=reconciled is None).value
        candidates.append({"observation_id": raw.observation_id, "text": raw.text, "capture_stage": raw.capture_stage,
                           "truth_correct": correct, "baseline_missing": not duplicate, "duplicate_baseline": duplicate,
                           "ownership_claims": claims, "ownership_valid": ownership_valid,
                           "provenance_complete": provenance_complete, "derivation_complete": provenance_complete,
                           "loss_boundary": boundary, "novel_correct_acquisition_evidence": novel})
    boundary_counts = Counter(candidate["loss_boundary"] for candidate in candidates)
    counts = {
        "acquisition_observations": len(ledger.acquisition_records), "projection_observations": len(ledger.records),
        "candidate_observations": len(candidates), "truth_correct": sum(x["truth_correct"] for x in candidates),
        "baseline_missing_observations": sum(x["baseline_missing"] for x in candidates),
        "novel_correct_acquisition_evidence": sum(x["novel_correct_acquisition_evidence"] for x in candidates),
        "duplicate_baseline_evidence": sum(x["duplicate_baseline"] for x in candidates),
        "ownership_conflicts": sum((x["ownership_claims"] or 0) > 1 for x in candidates),
        "unresolved": sum(not x["ownership_valid"] for x in candidates),
        "provenance_complete": sum(x["provenance_complete"] for x in candidates),
        "derivation_complete": sum(x["derivation_complete"] for x in candidates),
    }
    for boundary in ("acquisition", "normalization", "ownership", "reconciliation", "canonical_projection", "serialization", "unknown"):
        counts[f"{boundary}_loss"] = boundary_counts[boundary]
    return {"case_id": item["case_id"], "case_role": item["case_role"], "source_group_id": item["source_group_id"],
            "source_image": item["source_image"], "truth": item["truth"], "canonical_equivalent": equivalent,
            "counts": counts, "candidates": candidates, "ledger": ledger.as_dict()}


def main() -> int:
    manifest = json.loads((HERE / "population_manifest.json").read_text())
    protocol = HERE / "PROTOCOL.md"
    final = HERE / "runs/2026-10-01_protocol-v2_independent-corpus.json"
    if final.exists():
        raise SystemExit(f"refusing to overwrite immutable run artifact: {final}")
    stage_root = HERE / "runs/2026-10-01_protocol-v2_stage_outputs"
    docling = DoclingBackend(device="cpu", ocr_languages=["en", "vi"])
    table = TableTransformerBackend(device="cpu")
    rows = [_run_case(item, docling, table, stage_root) for item in manifest["cases"] if item["eligibility"] == "included"]
    sum_keys = ("acquisition_observations", "projection_observations", "candidate_observations", "truth_correct",
                "baseline_missing_observations", "novel_correct_acquisition_evidence", "duplicate_baseline_evidence",
                "ownership_conflicts", "unresolved", "provenance_complete", "derivation_complete", "acquisition_loss",
                "normalization_loss", "ownership_loss", "reconciliation_loss", "canonical_projection_loss", "serialization_loss", "unknown_loss")
    aggregate = {key: sum(row["counts"][key] for row in rows) for key in sum_keys}
    controls = [row for row in rows if row["case_role"] == "control"]
    aggregate.update({"cases": len(rows), "source_groups": len({row["source_group_id"] for row in rows}),
                      "canonical_equivalent_cases": sum(row["canonical_equivalent"] for row in rows),
                      "control_cases": len(controls),
                      "control_cases_with_novel": sum(bool(row["counts"]["novel_correct_acquisition_evidence"]) for row in controls),
                      "provenance_complete_cases": sum(all(x["provenance_complete"] for x in row["candidates"]) for row in rows)})
    result = {"experiment": "046_independent_corpus_challenge", "condition_A": "current uninstrumented scanned-page pipeline",
              "condition_B": "same pipeline plus acquisition-time ObservationLedger", "condition_C": "forbidden/not run",
              "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "branch": subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip(),
              "timestamp_utc": datetime.now(timezone.utc).isoformat(), "python": sys.version, "platform": platform.platform(),
              "packages": _package_versions(), "population_sha256": manifest["population_sha256"],
              "protocol_sha256": hashlib.sha256(protocol.read_bytes()).hexdigest(), "evaluator_identity": "evidence_integrity.py: normalized-exact v045",
              "per_case": rows, "aggregate": aggregate}
    final.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"output": str(final.relative_to(ROOT)), "aggregate": aggregate}, indent=2))
    return 0 if aggregate["canonical_equivalent_cases"] == len(rows) else 2


if __name__ == "__main__":
    raise SystemExit(main())
