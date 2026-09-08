"""030 Phase 7 -- exact code provenance for every mechanism-level claim."""
from __future__ import annotations
import hashlib, json, subprocess
from pathlib import Path
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]

def sha(path):
    return hashlib.sha256((REPO / path).read_bytes()).hexdigest()[:16]

CLAIMS = [
    {"claim": "row synthesis admits tokens by CENTER containment, not full-bbox containment",
     "file": "src/doc_extraction/pipelines/base.py", "function": "_center_in",
     "lines": "161-164", "condition": "outer.x0 <= cx <= outer.x1 and outer.y0 <= cy <= outer.y1",
     "field": "n/a (geometry predicate)", "resulting_ir_artifact": "n/a (used as a gate, not stored)"},
    {"claim": "orphan tokens eligible for row synthesis are those inside table.bbox by center",
     "file": "src/doc_extraction/pipelines/base.py", "function": "_fill_table_cell_text",
     "lines": "516-518", "condition": "_center_in(t.bbox, table.bbox)",
     "field": "n/a", "resulting_ir_artifact": "orphans list (intermediate, not persisted)"},
    {"claim": "a synthesized row requires corroboration across >=2 columns",
     "file": "src/doc_extraction/pipelines/base.py", "function": "module constant",
     "lines": "394", "condition": "MIN_CORROBORATING_COLUMNS = 2",
     "field": "n/a", "resulting_ir_artifact": "n/a (threshold)"},
    {"claim": "synthesized cell bbox is built from RAW TOKEN EDGES (min/max), not centers",
     "file": "src/doc_extraction/pipelines/base.py", "function": "_fill_table_cell_text",
     "lines": "559-567", "condition": "y0 = min(t.bbox.y0 for t in cluster); "
                                      "y1 = max(t.bbox.y1 for t in cluster)",
     "field": "Cell.bbox (of the synthesized cell)", "resulting_ir_artifact": "Table.cells[i].bbox"},
    {"claim": "the synthesis marker is Cell.confidence == 0.5, set at exactly one line",
     "file": "src/doc_extraction/pipelines/base.py", "function": "_fill_table_cell_text",
     "lines": "567", "condition": "confidence=0.5",
     "field": "Cell.confidence", "resulting_ir_artifact": "Table.cells[i].confidence",
     "verification": "grep -n 'confidence=0.5' src/doc_extraction/pipelines/base.py -> exactly 1 hit"},
    {"claim": "table.bbox is never reassigned after synthesis (no expansion)",
     "file": "src/doc_extraction/pipelines/base.py", "function": "_fill_table_cell_text",
     "lines": "505-580 (full function body)", "condition": "grep for 'table.bbox =' in this range: 0 hits",
     "field": "Table.bbox", "resulting_ir_artifact": "Table.bbox (unchanged from detector output)"},
    {"claim": "row/col VALUES are corrected after synthesis via _renumber_rows_by_position, "
             "but this does not touch cell bbox",
     "file": "src/doc_extraction/pipelines/base.py", "function": "_renumber_rows_by_position",
     "lines": "460-478 (called at 573)", "condition": "reassigns c.row from sorted y0 bands; "
                                                       "no bbox mutation in the function body",
     "field": "Cell.row, Table.n_rows", "resulting_ir_artifact": "Table.cells[*].row, Table.n_rows"},
    {"claim": "Table Transformer's structure-recognition backend takes no OCR input "
             "(rules out OCR-backend as a direct cause of geometry differences)",
     "file": "src/doc_extraction/backends/table_backend.py", "function": "module docstring",
     "lines": "1-14", "condition": "\"identical across whether it's fed OCR'd\" "
                                   "(documented design invariant)",
     "field": "n/a", "resulting_ir_artifact": "n/a"},
]

def main():
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True).stdout.strip()
    payload = {"commit": commit,
              "file_hashes": {c["file"]: sha(c["file"]) for c in {c["file"] for c in CLAIMS}
                              } if False else {f: sha(f) for f in sorted({c["file"] for c in CLAIMS})},
              "claims": CLAIMS}
    (HERE / "provenance.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False))
    for c in CLAIMS:
        print(f"  {c['file'].split('/')[-1]}:{c['lines']:<12} {c['function']:<28} {c['claim'][:60]}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
