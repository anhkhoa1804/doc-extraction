"""031 Phase 1 -- reconstruct the table-gating contract from actual source.

Read-only. Traces: page image -> Docling layout analysis -> Region objects
-> table_regions selection -> TableTransformer invocation -> Table IR.
Every claim here is verified against the CURRENT source file, not quoted
from 025's report.

    python experiments/031_table_label_gating/gating_contract.py
"""
from __future__ import annotations
import hashlib, json, subprocess
from pathlib import Path
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]

def sha(p): return hashlib.sha256((REPO / p).read_bytes()).hexdigest()[:16]

GATES = [
    {
        "stage": "1. Page rasterization -> Docling conversion",
        "file": "src/doc_extraction/backends/docling_backend.py",
        "function": "DoclingBackend.analyze",
        "lines": "308-322",
        "input": "PageInput.image_path (a rendered page image)",
        "condition": "docling_doc.iterate_items(traverse_pictures=True)",
        "output": "one Region per Docling doc item, each with bbox + label + "
                 "confidence=None (HARDCODED, not a discarded value -- see verification)",
        "downstream_consequence": "traverse_pictures=True means Docling's OWN "
                                  "internal traversal descends into picture-labelled "
                                  "blocks and emits their child text items as separate "
                                  "top-level Region objects too -- this is why nested "
                                  "'text' regions appear alongside a 'picture' region "
                                  "at the same bbox area (025's finding), and it is "
                                  "Docling's behavior, not custom code in this repo.",
        "gate_type": "structural (iteration behavior, not a filter)",
        "verified_this_milestone": "docling_core.types.doc.TextItem.model_fields and "
                                   "ProvenanceItem.model_fields both inspected directly: "
                                   "neither exposes any confidence/score field. "
                                   "confidence=None at line 322 is not a discarded "
                                   "signal -- Docling's stable API provides none to read.",
    },
    {
        "stage": "2. Region label assignment",
        "file": "src/doc_extraction/backends/docling_backend.py",
        "function": "_label_str",
        "lines": "70-72",
        "input": "a Docling doc item",
        "condition": "str(getattr(item.label, 'value', item.label)).lower()",
        "output": "one of Docling's own label vocabulary strings (e.g. 'table', "
                 "'picture', 'text', 'chart', ...) -- entirely Docling's model output, "
                 "not post-processed or thresholded by this repo",
        "downstream_consequence": "whatever label Docling's layout model assigns is "
                                  "trusted verbatim; there is no confidence threshold "
                                  "or secondary check applied at this stage",
        "gate_type": "label-based (verbatim passthrough of an upstream model's "
                     "classification decision)",
    },
    {
        "stage": "3. Table-region selection (THE GATE)",
        "file": "src/doc_extraction/pipelines/base.py",
        "function": "run_scanned_page_pipeline",
        "lines": "747",
        "input": "layout_result.regions (all Region objects from stage 1-2)",
        "condition": 'table_regions = [r for r in layout_result.regions if '
                     'r.label.lower() == "table"]',
        "output": "a filtered list containing ONLY regions whose label is exactly "
                 "the string 'table'",
        "downstream_consequence": "a region labelled 'picture', 'chart', 'text', or "
                                  "anything else is PERMANENTLY EXCLUDED from ever "
                                  "reaching TableTransformer for this page -- there is "
                                  "no fallback, no confidence check, no geometric "
                                  "override",
        "gate_type": "label-based, EXACT STRING EQUALITY. Not geometric, not "
                     "confidence-based, not semantic beyond the single label string.",
    },
    {
        "stage": "4. Table structure recognition (only reached if stage 3 passed)",
        "file": "src/doc_extraction/stages/table.py",
        "function": "run_table",
        "lines": "14-",
        "input": "table_regions (the filtered list from stage 3)",
        "condition": "table_backend.is_available() and table_regions non-empty",
        "output": "TableResult with Table.cells, Table.bbox, etc. via "
                 "TableTransformerBackend",
        "downstream_consequence": "if table_regions is empty (stage 3 filtered "
                                  "everything out), this stage produces no tables at "
                                  "all for the page, regardless of what the page "
                                  "visually contains",
        "gate_type": "routing-based (invocation is conditional on stage 3's output "
                     "being non-empty)",
    },
    {
        "stage": "5. Element type mapping for excluded regions",
        "file": "src/doc_extraction/pipelines/base.py",
        "function": "merge_regions_into_page (via _LABEL_TO_ELEMENT_TYPE)",
        "lines": "125-160 (dict), consumed ~591-650",
        "input": "a Region with label != 'table'",
        "condition": '_LABEL_TO_ELEMENT_TYPE.get(region.label.lower(), "other")',
        "output": "'picture' -> ElementType.IMAGE; the region's OWN geometry and any "
                 "OCR text under it (via _gather_region_text) becomes a plain IMAGE "
                 "element's text -- readable, but never becomes table cells",
        "downstream_consequence": "this is where 025 found duplication -- child text "
                                  "regions nested inside the picture ALSO get their own "
                                  "text elements (because Docling emitted them as "
                                  "separate top-level regions per stage 1's traversal "
                                  "behavior), so the same OCR tokens can appear in both "
                                  "the picture element's gathered text AND a nested "
                                  "text element's text",
        "gate_type": "label-based (dictionary lookup, default fallback to 'other')",
    },
]

def main():
    commit = subprocess.run(["git","rev-parse","HEAD"], cwd=REPO, capture_output=True, text=True).stdout.strip()
    payload = {
        "commit": commit,
        "summary": "The ENTIRE gate is one line: base.py:747, an exact string "
                  "equality test on r.label.lower() == 'table'. It is label-based, "
                  "not geometric, not confidence-based (no confidence field exists "
                  "to check), not semantic beyond trusting Docling's own layout "
                  "model's classification verbatim. Once a region is labelled "
                  "anything other than 'table', it is permanently excluded from "
                  "table processing for that page -- there is no fallback path.",
        "gate_classification": {
            "semantic": False,
            "geometric": False,
            "label_based": True,
            "confidence_based": "NOT POSSIBLE -- no confidence field exists in the "
                                "upstream data model (verified: docling_core TextItem/"
                                "ProvenanceItem)",
            "type_based": True,
            "routing_based": "downstream only (stage 4's invocation is conditional on "
                             "stage 3's output)",
        },
        "gates": GATES,
        "file_hashes": {f: sha(f) for f in sorted({g["file"] for g in GATES})},
    }
    Path("gating_contract.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False))
    print(f"commit {commit}")
    for g in GATES:
        print(f"  {g['stage']:<55} {g['file'].split('/')[-1]}:{g['lines']}")
    print(f"\nTHE GATE: {payload['summary'][:200]}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
