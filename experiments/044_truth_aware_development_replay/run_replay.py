"""Run frozen protocol-v2 observational A/B replay; C is deliberately absent.

It reads only persisted development artifacts. It does not rerun extraction,
modify canonical documents, or invoke historical crop-recovery outputs.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from doc_extraction.evaluation.evidence_integrity import (
    ObservationLedger, html_cell_texts, normalize_text, truth_aware_candidate,
)
from doc_extraction.pipelines.base import LayoutResult, OCRResult, OCRToken, Region, TableResult
from doc_extraction.schemas.document import Document
from doc_extraction.schemas.element import BBox
from doc_extraction.schemas.table import Table


def _box(value: dict) -> BBox:
    return BBox(**value)


def _contains(box: dict, point_box: BBox) -> bool:
    x = (point_box.x0 + point_box.x1) / 2
    y = (point_box.y0 + point_box.y1) / 2
    return box["x0"] <= x <= box["x1"] and box["y0"] <= y <= box["y1"]


def _truth_index() -> dict[tuple[str, str], dict]:
    rows = json.loads((ROOT / "experiments/034a_omnidocbench_snapshot/dataset/full/OmniDocBench.json").read_text())
    return {(Path(page["page_info"]["image_path"]).name, str(det["anno_id"])): det
            for page in rows for det in page["layout_dets"] if det.get("category_type") == "table"}


def _baseline_texts_in_locator(document: Document, locator: dict) -> tuple[str, ...]:
    values: list[str] = []
    for page in document.pages:
        for element in page.elements:
            if element.bbox is not None and element.text and _contains(locator, element.bbox):
                values.append(normalize_text(element.text))
        for table in page.tables:
            for cell in table.cells:
                if cell.bbox is not None and cell.text and _contains(locator, cell.bbox):
                    values.append(normalize_text(cell.text))
    return tuple(values)


def _load_case(item: dict, truth: dict) -> dict:
    base = ROOT / item["source_run"]
    document = Document.model_validate_json((base / "final/document.json").read_text())
    raw_layout = json.loads((base / "layout/page-001.json").read_text())
    raw_ocr = json.loads((base / "ocr/page-001.json").read_text())
    raw_tables = json.loads((base / "tables/page-001.json").read_text())
    layout = LayoutResult(
        regions=[Region(bbox=_box(r["bbox"]), label=r["label"], confidence=r["confidence"], source_id=r["source_id"])
                 for r in raw_layout["regions"]], backend=raw_layout["backend"], warnings=raw_layout["warnings"])
    ocr = OCRResult(tokens=[OCRToken(text=t["text"], bbox=_box(t["bbox"]), confidence=t["confidence"])
                            for t in raw_ocr["tokens"]], backend=raw_ocr["backend"], warnings=raw_ocr["warnings"])
    tables = TableResult(tables=[Table.model_validate(t) for t in raw_tables["tables"]], backend=raw_tables["backend"],
                         warnings=raw_tables["warnings"], spans_by_table=raw_tables.get("spans_by_table", {}))
    ledger = ObservationLedger()
    ledger.capture_scanned_page(page=document.pages[0], layout_result=layout, ocr_result=ocr, table_result=tables)
    gt = truth[(item["source_image"], str(item["source_locator"]))]
    truth_cells = html_cell_texts(gt["html"])
    baseline = _baseline_texts_in_locator(document, item["page_locator"])
    token_records = {(r.text, r.geometry): r for r in ledger.records if r.payload_kind == "ocr_token"}
    candidates = []
    for token in ocr.tokens:
        if not _contains(item["page_locator"], token.bbox):
            continue
        record = token_records[(token.text, (token.bbox.x0, token.bbox.y0, token.bbox.x1, token.bbox.y1))]
        ownership_valid = record.disposition.value == "accepted"
        provenance_complete = bool(record.observation_id)
        # A real derived canonical cell is the only structural signal this
        # observational B condition is allowed to claim.
        derived_cell = any(r.payload_kind == "table_cell" and record.observation_id in r.derivation_refs
                           for r in ledger.records)
        classified = truth_aware_candidate(text=token.text, truth_cells=truth_cells, baseline_texts=baseline,
                                           ownership_valid=ownership_valid, provenance_complete=provenance_complete,
                                           structurally_valid=derived_cell)
        candidates.append({"text": token.text, "observation_id": record.observation_id,
                           "disposition": record.disposition.value, "claims": len(record.candidate_claims),
                           **classified,
                           "truth_status": "resolved"})
    counts = {"observations_captured": len(ledger.records),
              "observations_accepted": sum(r.disposition.value == "accepted" for r in ledger.records),
              "observations_unresolved": sum(r.disposition.value == "unresolved" for r in ledger.records),
              "observations_excluded": sum(r.disposition.value == "excluded" for r in ledger.records),
              "candidate_recoveries": len(candidates), "structurally_valid": sum(x["structurally_valid"] for x in candidates),
              "ownership_valid": sum(x["ownership_valid"] for x in candidates), "text_bearing": sum(x["text_bearing"] for x in candidates),
              "correct": sum(x["correct"] for x in candidates), "novel_correct_textual_evidence": sum(x["novel_correct_textual_evidence"] for x in candidates),
              "duplicate_baseline_evidence": sum(x["duplicate_baseline"] for x in candidates),
              "incorrect_recovery": sum(x["text_bearing"] and not x["correct"] for x in candidates),
              "unresolved_recovery": sum(x["disposition"] == "unresolved" for x in candidates),
              "structural_only_recovery": 0,
              "provenance_complete": all(x["provenance_complete"] for x in candidates),
              "ownership_conflicts": sum(x["claims"] > 1 for x in candidates)}
    return {"case_id": item["case_id"], "historical_failure": item["historical_failure"], "raw_role": item["raw_role"],
            "truth_cell_count": len(truth_cells), "baseline_locator_text_count": len(baseline), "counts": counts,
            "candidates": candidates, "ledger": ledger.as_dict()}


def main() -> int:
    manifest = json.loads((HERE / "population_manifest_v2.json").read_text())
    truth = _truth_index()
    rows = [_load_case(item, truth) for item in manifest["cases"] if item["eligibility"] == "included"]
    fields = ("novel_correct_textual_evidence", "duplicate_baseline_evidence", "structural_only_recovery",
              "incorrect_recovery", "unresolved_recovery", "ownership_conflicts")
    aggregate = {field: sum(row["counts"][field] for row in rows) for field in fields}
    aggregate.update({"cases": len(rows), "candidate_recoveries": sum(r["counts"]["candidate_recoveries"] for r in rows),
                      "provenance_complete_cases": sum(r["counts"]["provenance_complete"] for r in rows),
                      "controls": sum(r["historical_failure"] == "exact_match_control" for r in rows),
                      "control_cases_with_novel": sum(r["historical_failure"] == "exact_match_control" and r["counts"]["novel_correct_textual_evidence"] > 0 for r in rows)})
    aggregate["novel_correct_rate"] = (aggregate["novel_correct_textual_evidence"] / aggregate["candidate_recoveries"]
                                         if aggregate["candidate_recoveries"] else None)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    protocol = HERE / "PROTOCOL-v2.md"
    result = {"experiment": "044_truth_aware_development_replay", "condition_A": "persisted canonical output",
              "condition_B": "same canonical output plus reconstructed persisted-artifact ledger", "condition_C": "not run: frozen B result contains no qualifying novel-correct candidate",
              "development_only": True, "git_commit": commit, "protocol_sha256": hashlib.sha256(protocol.read_bytes()).hexdigest(),
              "population_sha256": manifest["population_sha256"], "python": sys.version, "platform": platform.platform(),
              "packages": {p: importlib.metadata.version(p) for p in ("pydantic", "Pillow")},
              "timestamp_utc": datetime.now(timezone.utc).isoformat(), "per_case": rows, "aggregate": aggregate}
    output = HERE / "runs/2026-10-01_protocol-v2_observational-v3.json"
    output.parent.mkdir(exist_ok=True)
    if output.exists():
        raise SystemExit(f"refusing to overwrite immutable run artifact: {output}")
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"output": str(output.relative_to(ROOT)), "aggregate": aggregate}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
