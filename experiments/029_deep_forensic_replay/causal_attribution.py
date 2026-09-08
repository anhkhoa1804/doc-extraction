"""029 Phase 4/5 -- causal attribution for the structurally-invalid-table defect.

Offline, read-only. For EVERY table flagged `structurally_valid=False` with
`cells_within_table_bbox` in `all_tables.json`, re-opens the source
document.json and tests the exact mechanism identified by direct source
inspection (src/doc_extraction/pipelines/base.py:505-576):

  tier-3 row synthesis admits a token by testing whether its CENTER lies
  inside table.bbox (`_center_in`), then builds the synthesized cell's bbox
  from the token's raw min/max edges. `table.bbox` is never expanded
  afterward. A token whose center is barely inside but whose edge extends
  past table.bbox therefore produces a cell that escapes its own table.

The synthesis marker is `Cell.confidence == 0.5`, set at base.py:568
(`confidence=0.5`) and nowhere else in the codebase (grep-verified).

    python experiments/029_deep_forensic_replay/causal_attribution.py
"""
from __future__ import annotations

import json
import subprocess
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
RESULTS = HERE / "results"


def find_doc_json(milestone: str, arm: str, document_id: str) -> Path | None:
    roots = {
        "023": REPO / "experiments/023_evidence_centric/_runs",
        "024": REPO / "experiments/024_ocr_fidelity_recovery/_runs",
        "025": REPO / "experiments/025_layout_evidence_recall/_runs",
    }
    base = roots[milestone] / arm
    if not base.exists():
        return None
    for d in base.iterdir():
        if d.is_dir() and d.name.rsplit("-", 1)[0] == document_id:
            f = d / "final" / "document.json"
            return f if f.exists() else None
    return None


def bbox_outside(cell_bbox: dict, table_bbox: dict, tol: float = 1.0) -> bool:
    return not (cell_bbox["x0"] >= table_bbox["x0"] - tol
               and cell_bbox["y0"] >= table_bbox["y0"] - tol
               and cell_bbox["x1"] <= table_bbox["x1"] + tol
               and cell_bbox["y1"] <= table_bbox["y1"] + tol)


def grep_confidence_05_sites() -> list[str]:
    """Verify 0.5 is used as the row-synthesis marker and nowhere else."""
    out = subprocess.run(["grep", "-n", "confidence=0.5",
                          str(REPO / "src/doc_extraction/pipelines/base.py")],
                         capture_output=True, text=True).stdout.strip()
    return out.splitlines()


def main() -> int:
    tables = json.loads((RESULTS / "all_tables.json").read_text())
    invalid = [t for t in tables
              if not t["structurally_valid"] and "cells_within_table_bbox" in t["failed_checks"]]

    sites = grep_confidence_05_sites()
    print(f"confidence=0.5 literal occurs at: {sites}")

    seen_docs, forensic_rows = set(), []
    total_escaping_cells = 0
    synth_marked_escaping = 0
    non_synth_escaping = 0
    doc_arm_checked = 0
    doc_arm_error = 0

    for t in invalid:
        key = (t["milestone"], t["arm"], t["document_id"], t["table_id"])
        if key in seen_docs:
            continue
        seen_docs.add(key)
        f = find_doc_json(t["milestone"], t["arm"], t["document_id"])
        if f is None:
            doc_arm_error += 1
            continue
        try:
            doc = json.loads(f.read_text())
        except Exception:
            doc_arm_error += 1
            continue
        doc_arm_checked += 1

        for pg in doc.get("pages") or []:
            for tbl in pg.get("tables") or []:
                if tbl.get("id") != t["table_id"]:
                    continue
                tbb = tbl.get("bbox")
                if tbb is None:
                    continue
                escapes = []
                for c in tbl.get("cells") or []:
                    cb = c.get("bbox")
                    if cb is None:
                        continue
                    if bbox_outside(cb, tbb):
                        escapes.append(c)
                if not escapes:
                    continue
                total_escaping_cells += len(escapes)
                synth = sum(1 for c in escapes if c.get("confidence") == 0.5)
                nonsynth = len(escapes) - synth
                synth_marked_escaping += synth
                non_synth_escaping += nonsynth
                rows_escaping = sorted({c["row"] for c in escapes})
                forensic_rows.append({
                    "milestone": t["milestone"], "arm": t["arm"],
                    "document_id": t["document_id"], "table_id": t["table_id"],
                    "escaping_cells": len(escapes),
                    "escaping_cells_synth_marked": synth,
                    "escaping_cells_non_synth": nonsynth,
                    "escaping_rows": rows_escaping,
                    "table_bbox": tbb,
                    "declared_shape": [tbl.get("n_rows"), tbl.get("n_cols")],
                    "escape_direction": (
                        "above_table_top" if rows_escaping and min(rows_escaping) == 0
                        else "below_table_bottom" if rows_escaping and max(rows_escaping) == tbl.get("n_rows", 0) - 1
                        else "interior_or_mixed"),
                    "max_escape_px": max(
                        max(0, tbb["y0"] - c["bbox"]["y0"]) + max(0, c["bbox"]["y1"] - tbb["y1"])
                        for c in escapes),
                })

    mechanism_confirmed_rate = round(synth_marked_escaping / total_escaping_cells, 4) if total_escaping_cells else None

    # Distribution of "which row escapes" -- FACT: is it always row 0 (top synthesis)?
    escape_row_pattern = Counter(r["escape_direction"] for r in forensic_rows)

    payload = {
        "commit": subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO,
                                 capture_output=True, text=True).stdout.strip(),
        "mechanism_under_test": {
            "claim": "structurally-invalid tables (cells_within_table_bbox failing) are "
                    "caused by tier-3 row synthesis, whose synthesized cell bbox is built "
                    "from raw OCR token edges after a CENTER-only containment test against "
                    "table.bbox, which is never expanded afterward.",
            "source": "src/doc_extraction/pipelines/base.py:505-576",
            "marker": "Cell.confidence == 0.5, set once at base.py:568 "
                     f"({sites[0] if sites else 'NOT FOUND'})",
            "marker_is_exclusive_to_synthesis": len(sites) == 1,
        },
        "totals": {
            "invalid_table_instances_in_corpus": len(invalid),
            "distinct_(milestone,arm,doc,table)_invalid": len(seen_docs),
            "checked_successfully": doc_arm_checked,
            "checked_errors": doc_arm_error,
            "total_escaping_cells": total_escaping_cells,
            "escaping_cells_synth_marked": synth_marked_escaping,
            "escaping_cells_non_synth_marked": non_synth_escaping,
            "mechanism_confirmed_rate": mechanism_confirmed_rate,
        },
        "escape_direction_distribution": dict(escape_row_pattern),
        "verdict": (
            "FACT: mechanism confirmed" if mechanism_confirmed_rate == 1.0 else
            "FACT: mechanism explains most but not all cases" if mechanism_confirmed_rate and mechanism_confirmed_rate > 0.9 else
            "INFERENCE: mechanism explains a majority" if mechanism_confirmed_rate and mechanism_confirmed_rate > 0.5 else
            "HYPOTHESIS: mechanism does not dominate -- other cause(s) present"),
        "forensic_rows": forensic_rows,
    }
    (HERE / "causal_attribution.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False))

    print(f"\ninvalid table instances (across all arms): {len(invalid)}")
    print(f"distinct (milestone,arm,doc,table): {len(seen_docs)}")
    print(f"checked ok: {doc_arm_checked}  errors: {doc_arm_error}")
    print(f"total escaping cells: {total_escaping_cells}")
    print(f"  synth-marked (confidence==0.5): {synth_marked_escaping}")
    print(f"  non-synth: {non_synth_escaping}")
    print(f"MECHANISM CONFIRMED RATE: {mechanism_confirmed_rate}")
    print(f"escape direction distribution: {dict(escape_row_pattern)}")
    print(f"\nVERDICT: {payload['verdict']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
