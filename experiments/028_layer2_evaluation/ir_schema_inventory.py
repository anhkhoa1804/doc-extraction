"""028 Phase 1 -- inventory the ACTUAL production IR. Read only.

Introspects the live pydantic models rather than trusting any previous
report. Layer 2 must consume these fields and invent none; this file is what
the rest of the milestone is allowed to reference.

    python experiments/028_layer2_evaluation/ir_schema_inventory.py
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "src"))

from doc_extraction.schemas import BBox, Cell, Document, Element, Page, Table  # noqa: E402
from doc_extraction.schemas.element import ElementType  # noqa: E402
from doc_extraction.schemas.version import SCHEMA_VERSION  # noqa: E402

MODELS = {"Document": Document, "Page": Page, "Element": Element,
          "Table": Table, "Cell": Cell, "BBox": BBox}


def fields(model):
    out = {}
    for name, f in model.model_fields.items():
        ann = f.annotation
        out[name] = {
            "type": str(ann).replace("typing.", "").replace("doc_extraction.schemas.", ""),
            "required": f.is_required(),
            "default": None if f.is_required() else repr(f.get_default(call_default_factory=True)),
        }
    return out


def main() -> int:
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO,
                            capture_output=True, text=True).stdout.strip()
    inv = {name: fields(m) for name, m in MODELS.items()}

    payload = {
        "commit": commit,
        "schema_version": SCHEMA_VERSION,
        "schema_files": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()[:16]
            for p in sorted((REPO / "src/doc_extraction/schemas").glob("*.py"))
        },
        "models": inv,
        "element_types": [e.value for e in ElementType],
        "identity_and_semantics": {
            "Document": "identity = `document_id`; carries `schema_version` and "
                        "`metadata` (RunMetadata: route, backend, device, timings).",
            "Page": "identity = `index` (0-based, always present). NOT a rendered page "
                    "number -- `is_rendered_page` says whether one exists. Carries "
                    "`coordinate_unit` (pt|px|emu), `coordinate_origin` (top-left), "
                    "`dpi`, `source_route`, `source_backend`, `notes`.",
            "Page.reading_order": "list[Element.id] in reading order. THIS is production's "
                                  "page-order semantics and is what Layer 2's page_order "
                                  "view must consume. `Document.to_markdown` already uses "
                                  "`page.reading_order or [e.id for e in page.elements]`.",
            "Element": "identity = `id`. Has `type` (ElementType), `text`, `bbox`, "
                       "`page_number` (nullable), `confidence`, `source_backend`, "
                       "`source_id`, `parent_id`, `order_index`, `level`, `table_id`, "
                       "`extra`. A TABLE element carries no cells: `table_id` points into "
                       "the owning Page's `tables`.",
            "Table": "identity = `id`. Has `bbox` (nullable), `page_number` (nullable), "
                     "`n_rows`, `n_cols`, `cells`, `source_backend`, `confidence`. "
                     "`to_grid()` and `to_markdown()` materialize via (row, col).",
            "Cell": "NO independent id -- identity IS `(row, col)` within its table. Has "
                    "`row`, `col` (both required ints), `row_span`, `col_span` (default 1), "
                    "`bbox` (nullable), `text` (default \"\"), `is_header`, `confidence`.",
            "BBox": "`x0,y0,x1,y1` with x0<=x1 and y0<=y1, top-left origin, +y down, "
                    "units from the owning Page.",
        },
        "fields_layer2_may_use": {
            "table_text": ["Table.id", "Cell.row", "Cell.col", "Cell.text"],
            "table_structure": ["Table.id", "Table.bbox", "Table.n_rows", "Table.n_cols",
                                "Cell.row", "Cell.col", "Cell.row_span", "Cell.col_span",
                                "Cell.bbox", "Cell.text", "Cell.is_header"],
            "page_order": ["Page.index", "Page.reading_order", "Element.id",
                           "Element.type", "Element.text", "Element.order_index",
                           "Element.bbox", "Element.table_id"],
            "structural_integrity": ["Table.n_rows", "Table.n_cols", "Table.bbox",
                                     "Cell.row", "Cell.col", "Cell.bbox",
                                     "Cell.row_span", "Cell.col_span"],
        },
        "fields_layer2_must_not_invent": [
            "cell id (does not exist -- identity is (row, col))",
            "per-cell ground truth (the corpus carries document-level must_contain only)",
            "table-level ground truth grid (not present in the manifest)",
            "row/col confidence (Cell.confidence is a value confidence, not a "
            "structure confidence)",
        ],
    }
    (HERE / "ir_schema_inventory.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False))

    print(f"commit {commit}  schema_version {SCHEMA_VERSION}")
    for name, f in inv.items():
        req = [k for k, v in f.items() if v["required"]]
        print(f"  {name:<9} {len(f):>2} fields; required: {req}")
    print(f"\n  Page.reading_order present : {'reading_order' in inv['Page']}")
    print(f"  Cell identity              : (row, col) -- no id field")
    print(f"  Cell has spans             : row_span={('row_span' in inv['Cell'])} "
          f"col_span={('col_span' in inv['Cell'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
