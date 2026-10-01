"""Replay one frozen 035 development artifact through the A/B ledger evaluator.

This is an observational replay: A is the persisted canonical document; B
adds a ledger reconstructed from the persisted stage artifacts. No backend is
rerun, no selector changes, and no recovery treatment is invoked.
"""
from __future__ import annotations

import json
import platform
import subprocess
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from doc_extraction.evaluation.evidence_integrity import ObservationLedger, evaluate_evidence_integrity
from doc_extraction.pipelines.base import LayoutResult, OCRResult, OCRToken, Region, TableResult
from doc_extraction.schemas.document import Document
from doc_extraction.schemas.element import BBox

CASE_ID = "d2-00"
SOURCE = ROOT / "experiments/035_mechanism_d_gating/results/gt_tables_chunk0/_doc_extraction_runs/page-d5f79be0-5d57-4849-9897-6106dd32117a-dc35626b"


def box(value: dict) -> BBox:
    return BBox(**value)


def main() -> int:
    doc = Document.model_validate_json((SOURCE / "final/document.json").read_text())
    raw_layout = json.loads((SOURCE / "layout/page-001.json").read_text())
    raw_ocr = json.loads((SOURCE / "ocr/page-001.json").read_text())
    raw_tables = json.loads((SOURCE / "tables/page-001.json").read_text())
    layout = LayoutResult(regions=[Region(bbox=box(x["bbox"]), label=x["label"], confidence=x["confidence"], source_id=x["source_id"])
                                   for x in raw_layout["regions"]], backend=raw_layout["backend"], warnings=raw_layout["warnings"])
    ocr = OCRResult(tokens=[OCRToken(text=x["text"], bbox=box(x["bbox"]), confidence=x["confidence"])
                            for x in raw_ocr["tokens"]], backend=raw_ocr["backend"], warnings=raw_ocr["warnings"])
    tables = TableResult(tables=[], backend=raw_tables["backend"], warnings=raw_tables["warnings"])
    ledger = ObservationLedger()
    ledger.capture_scanned_page(page=doc.pages[0], layout_result=layout, ocr_result=ocr, table_result=tables)
    result = evaluate_evidence_integrity(baseline=doc, candidate=doc, ledger=ledger)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    run = {
        "experiment": "043_observation_ledger_vertical_slice", "condition_A": "persisted frozen canonical output",
        "condition_B": "same canonical output plus reconstructed private observation ledger",
        "case_id": CASE_ID, "source_run": str(SOURCE.relative_to(ROOT)), "source_hashes": {
            name: __import__("hashlib").sha256((SOURCE / name).read_bytes()).hexdigest()
            for name in ("final/document.json", "layout/page-001.json", "ocr/page-001.json", "tables/page-001.json")},
        "git_commit": commit, "python": sys.version, "platform": platform.platform(),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(), "evaluator": result,
        "ledger": ledger.as_dict(),
        "interpretation": "Observational only. Novel textual evidence is not correctness-scored because this replay has no token truth annotation.",
    }
    output = ROOT / "experiments/043_observation_ledger_vertical_slice/runs/2026-10-01_d2-00_observational_replay-v2.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise SystemExit(f"refusing to overwrite immutable run artifact: {output}")
    output.write_text(json.dumps(run, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"output": str(output.relative_to(ROOT)), "evaluator": result}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
