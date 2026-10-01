"""Execute frozen A/B acquisition-time capture using current component backends."""
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
    ObservationLedger, classify_loss_boundary, html_cell_texts, normalize_text, truth_aware_candidate,
)
from doc_extraction.pipelines.base import run_scanned_page_pipeline
from doc_extraction.schemas.document import Document, RunMetadata


def _truth_index() -> dict[tuple[str, str], dict]:
    rows = json.loads((ROOT / "experiments/034a_omnidocbench_snapshot/dataset/full/OmniDocBench.json").read_text())
    return {(Path(page["page_info"]["image_path"]).name, str(det["anno_id"])): det
            for page in rows for det in page["layout_dets"] if det.get("category_type") == "table"}


def _contains(locator: dict, bbox) -> bool:
    x, y = (bbox.x0 + bbox.x1) / 2, (bbox.y0 + bbox.y1) / 2
    return locator["x0"] <= x <= locator["x1"] and locator["y0"] <= y <= locator["y1"]


def _phrase(value: str, container: str) -> bool:
    return f" {value} " in f" {container} "


def _page_texts(page, locator: dict) -> tuple[list[str], list[str]]:
    raw: list[str] = []
    for element in page.elements:
        if element.text and element.bbox is not None and _contains(locator, element.bbox):
            raw.append(element.text)
    for table in page.tables:
        for cell in table.cells:
            if cell.text and cell.bbox is not None and _contains(locator, cell.bbox):
                raw.append(cell.text)
    return raw, [normalize_text(text) for text in raw]


def _markdown(page) -> str:
    metadata = RunMetadata(input_filename="acquisition-page", input_path="", file_hash_sha256="", file_type="image",
                           route="image", pipeline="baseline", backend="docling", timestamp="2026-10-01T00:00:00Z")
    return Document(document_id="acquisition-page", metadata=metadata, pages=[page]).to_markdown()


def _run_case(item: dict, truth: dict, docling: DoclingBackend, table: TableTransformerBackend, output: Path) -> dict:
    image = ROOT / item["input_path"]
    # B first: the opt-in hook sees result objects from the actual fresh
    # backend conversion, before canonical page projection.
    ledger = ObservationLedger()
    b_page = run_scanned_page_pipeline(image, 0, 200, docling, docling, table, output / item["case_id"] / "B",
                                       observation_ledger=ledger)
    a_page = run_scanned_page_pipeline(image, 0, 200, docling, docling, table, output / item["case_id"] / "A")
    equivalent = a_page.model_dump(mode="json") == b_page.model_dump(mode="json")
    gt = truth[(item["source_image"], str(item["source_locator"]))]
    cells = html_cell_texts(gt["html"])
    raw_baseline, normalized_baseline = _page_texts(a_page, item["page_locator"])
    markdown = _markdown(a_page)
    projection = {r.observation_id: r for r in ledger.records}
    candidates = []
    for raw in ledger.acquisition_records:
        if raw.payload_kind != "ocr_token" or raw.geometry is None:
            continue
        from doc_extraction.schemas.element import BBox
        box = BBox(x0=raw.geometry[0], y0=raw.geometry[1], x1=raw.geometry[2], y1=raw.geometry[3])
        if not _contains(item["page_locator"], box):
            continue
        reconciled = projection.get(raw.observation_id)
        exact = bool(raw.text) and any(_phrase(raw.text, value) for value in raw_baseline)
        normalized = bool(raw.text) and any(_phrase(normalize_text(raw.text), value) for value in normalized_baseline)
        serialized = bool(raw.text) and _phrase(normalize_text(raw.text), normalize_text(markdown))
        ownership_conflict = bool(reconciled and len(reconciled.candidate_claims) > 1)
        ownership_valid = bool(reconciled and reconciled.disposition.value == "accepted")
        provenance_complete = reconciled is not None
        classification = truth_aware_candidate(text=raw.text, truth_cells=cells, baseline_texts=tuple(normalized_baseline),
                                               ownership_valid=ownership_valid, provenance_complete=provenance_complete,
                                               structurally_valid=False)
        boundary = classify_loss_boundary(acquisition_present=True, canonical_exact_present=exact,
                                          canonical_normalized_present=normalized, serialized_present=serialized,
                                          ownership_conflict=ownership_conflict).value
        candidates.append({"observation_id": raw.observation_id, "text": raw.text, "capture_stage": raw.capture_stage,
                           "ownership_claims": len(reconciled.candidate_claims) if reconciled else None,
                           "loss_boundary": boundary, "baseline_missing": not normalized, **classification})
    counts = {"acquisition_observations": len(ledger.acquisition_records), "projection_observations": len(ledger.records),
              "baseline_missing_observations": sum(x["baseline_missing"] for x in candidates),
              "truth_correct": sum(x["correct"] for x in candidates),
              "novel_correct_textual_evidence": sum(x["novel_correct_textual_evidence"] for x in candidates),
              "duplicate_baseline_evidence": sum(x["duplicate_baseline"] for x in candidates),
              "ownership_conflicts": sum((x["ownership_claims"] or 0) > 1 for x in candidates),
              "unresolved": sum(x["ownership_claims"] and x["ownership_claims"] > 1 for x in candidates),
              "provenance_complete": all(x["provenance_complete"] for x in candidates),
              "candidate_observations": len(candidates)}
    boundary_counts = Counter(x["loss_boundary"] for x in candidates)
    for boundary in ("acquisition", "normalization", "ownership", "reconciliation", "canonical_projection", "serialization", "unknown"):
        counts[f"{boundary}_loss"] = boundary_counts[boundary]
    return {"case_id": item["case_id"], "historical_failure": item["historical_failure"], "raw_role": item["raw_role"],
            "canonical_equivalent": equivalent, "truth_cell_count": len(cells), "counts": counts,
            "candidates": candidates, "ledger": ledger.as_dict()}


def main() -> int:
    manifest = json.loads((HERE / "population_manifest.json").read_text())
    output_root = HERE / "runs/2026-10-01_protocol-v1_stage_outputs"
    truth = _truth_index()
    docling = DoclingBackend(device="cpu", ocr_languages=["en", "vi"])
    table = TableTransformerBackend(device="cpu")
    rows = [_run_case(item, truth, docling, table, output_root) for item in manifest["cases"] if item["eligibility"] == "included"]
    keys = ("acquisition_observations", "baseline_missing_observations", "truth_correct", "novel_correct_textual_evidence",
            "duplicate_baseline_evidence", "ownership_conflicts", "unresolved", "acquisition_loss", "normalization_loss",
            "ownership_loss", "reconciliation_loss", "canonical_projection_loss", "serialization_loss")
    aggregate = {key: sum(row["counts"][key] for row in rows) for key in keys}
    aggregate.update({"cases": len(rows), "candidate_observations": sum(r["counts"]["candidate_observations"] for r in rows),
                      "provenance_complete_cases": sum(r["counts"]["provenance_complete"] for r in rows),
                      "canonical_equivalent_cases": sum(r["canonical_equivalent"] for r in rows),
                      "control_cases": sum(r["historical_failure"] == "exact_match_control" for r in rows),
                      "control_cases_with_novel": sum(r["historical_failure"] == "exact_match_control" and r["counts"]["novel_correct_textual_evidence"] for r in rows)})
    protocol = HERE / "PROTOCOL.md"
    result = {"experiment": "045_acquisition_time_observation_capture", "condition_A": "current uninstrumented scanned-page pipeline",
              "condition_B": "same pipeline plus acquisition-time ObservationLedger", "condition_C": "not authorized/not run",
              "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "population_sha256": manifest["population_sha256"], "protocol_sha256": hashlib.sha256(protocol.read_bytes()).hexdigest(),
              "timestamp_utc": datetime.now(timezone.utc).isoformat(), "python": sys.version, "platform": platform.platform(),
              "packages": {name: importlib.metadata.version(name) for name in ("docling", "easyocr", "transformers", "torch", "pydantic")},
              "per_case": rows, "aggregate": aggregate}
    final = HERE / "runs/2026-10-01_protocol-v1_acquisition_capture-v2.json"
    if final.exists():
        raise SystemExit(f"refusing to overwrite immutable run artifact: {final}")
    final.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"output": str(final.relative_to(ROOT)), "aggregate": aggregate}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
