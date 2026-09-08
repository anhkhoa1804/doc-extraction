"""025 line 1 -- region-coverage instrumentation. MEASUREMENT ONLY.

024 established that L5 rescues OCR tokens no layout region claims, and that
11.21% of recognised tokens on SCAN-49 need rescuing. It could not say *why*
the regions fail to cover them, because `audit_pages` recorded region COUNTS
and not region TYPES or GEOMETRY.

This records the missing information. It wraps `merge_regions_into_page` and
observes; it delegates to the real function unchanged, so extraction
behaviour is bit-identical to production. The check that this is true is
built in: every document's `text_sha` must equal the one 024's frozen `l5`
arm recorded at the same commit for the same file.

Ownership is decided by the PRODUCTION predicate `pbase._center_in` and the
production table/cell exclusion -- deliberately not a more generous rule
invented to make coverage look better.

Cohort: the frozen SCAN-49 stratum of `scan_cohort_manifest.json`,
sha256-verified per file before the run. CPU only, no GPU.

    python experiments/025_layout_evidence_recall/coverage_instrument.py

Writes `coverage_dataset.json` beside this file.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
E024 = REPO / "experiments/024_ocr_fidelity_recovery"
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "research/production_corpus"))
sys.path.insert(0, str(REPO / "experiments/023_evidence_centric"))

import run_ab  # noqa: E402
from doc_extraction import cli  # noqa: E402
from doc_extraction.backends.docling_backend import DoclingBackend  # noqa: E402
from doc_extraction.backends.table_backend import TableTransformerBackend  # noqa: E402
from doc_extraction.backends.tesseract_backend import TesseractBackend  # noqa: E402
from doc_extraction.config import PipelineConfig  # noqa: E402
from doc_extraction.pipelines import base as pbase  # noqa: E402
from run_benchmark import document_text  # noqa: E402

COHORT_MANIFEST = E024 / "scan_cohort_manifest.json"
CORPUS = E024 / "_runs" / "scan_cohort_corpus"
STRATUM = "SCAN-49"
STRATEGY, DEVICE = "adaptive", "cpu"

_REAL_MERGE = pbase.merge_regions_into_page
_CURRENT = [None]
_PAGES: list[dict] = []


def _bb(b) -> list[float] | None:
    return None if b is None else [round(b.x0, 2), round(b.y0, 2), round(b.x1, 2), round(b.y1, 2)]


def observing_merge(page_index, width, height, dpi, layout_result, ocr_result,
                    table_result, rendered_image_path):
    """Record, then delegate unchanged. No extraction behaviour is altered."""
    regions = layout_result.regions
    tables = list(table_result.tables) if table_result else []

    table_boxes = [t.bbox for t in tables if getattr(t, "bbox", None) is not None]
    cell_boxes = [c.bbox for t in tables for c in (getattr(t, "cells", None) or [])
                  if getattr(c, "bbox", None) is not None]

    tok_rows = []
    for tok in ocr_result.tokens:
        owners = [i for i, r in enumerate(regions) if pbase._center_in(tok.bbox, r.bbox)]
        in_cell = any(pbase._center_in(tok.bbox, b) for b in cell_boxes)
        in_table = any(pbase._center_in(tok.bbox, b) for b in table_boxes)
        if owners:
            claim = "region"
        elif in_cell:
            claim = "cell"
        elif in_table:
            claim = "table"
        else:
            claim = "orphan"
        tok_rows.append({
            "text": tok.text,
            "bbox": _bb(tok.bbox),
            "conf": None if tok.confidence is None else round(tok.confidence, 4),
            "claim": claim,
            "region_idx": owners[0] if owners else None,
            "n_owners": len(owners),
        })

    _PAGES.append({
        "document_id": _CURRENT[0],
        "page_index": page_index,
        "width": round(width, 2),
        "height": round(height, 2),
        "regions": [{
            "idx": i,
            "label": r.label,
            "bbox": _bb(r.bbox),
            "confidence": None if r.confidence is None else round(r.confidence, 4),
            "claimed_tokens": sum(1 for t in tok_rows if t["region_idx"] == i),
        } for i, r in enumerate(regions)],
        "tables": [{
            "bbox": _bb(getattr(t, "bbox", None)),
            "n_cells": len(getattr(t, "cells", None) or []),
            "n_rows": getattr(t, "n_rows", None),
            "n_cols": getattr(t, "n_cols", None),
            "cell_bboxes": [_bb(c.bbox) for c in (getattr(t, "cells", None) or [])
                            if getattr(c, "bbox", None) is not None],
        } for t in tables],
        "tokens": tok_rows,
    })
    return _REAL_MERGE(page_index, width, height, dpi, layout_result, ocr_result,
                       table_result, rendered_image_path)


def main() -> int:
    cohort = json.loads(COHORT_MANIFEST.read_text())
    docs = [d for d in cohort["documents_list"] if d["stratum"] == STRATUM]
    for d in docs:  # the frozen cohort is the contract
        p = CORPUS / d["filename"]
        got = hashlib.sha256(p.read_bytes()).hexdigest()
        if got != d["sha256"]:
            print(f"FATAL: {d['filename']} does not match the frozen manifest")
            return 1
    print(f"cohort verified: {len(docs)} documents, sha256 matched", flush=True)

    config = run_ab.configure(STRATEGY, DEVICE)
    config.ocr_backend = "__025_tesseract"
    layout = DoclingBackend(device=DEVICE, ocr_languages=PipelineConfig().ocr_languages)
    ocr = TesseractBackend(device=DEVICE, languages=config.ocr_languages)
    tables = TableTransformerBackend(device=DEVICE)
    cli._COMPONENT_BACKEND_CACHE[(config.device, tuple(config.ocr_languages),
                                  config.ocr_backend)] = (layout, ocr, tables)

    pbase.merge_regions_into_page = observing_merge
    out_root = HERE / "_runs" / "coverage"
    rows = []
    t0 = time.perf_counter()
    for entry in docs:
        _CURRENT[0] = entry["document_id"]
        started = time.perf_counter()
        try:
            document = cli.process_file(CORPUS / entry["filename"], config, output_root=out_root)
            text = document_text(document)
            n_tables = sum(len(getattr(p, "tables", []) or []) for p in document.pages)
            error = None
        except Exception as exc:  # noqa: BLE001
            text, n_tables, error = "", 0, f"{type(exc).__name__}: {exc}"
        row = {"document_id": entry["document_id"], "language": entry["language"],
               "document_type": entry["document_type"], "difficulty": entry["difficulty"],
               "labels": entry["hard_case_labels"], "pages": entry["page_count"],
               "must_contain": entry["must_contain"],
               "must_not_contain": entry.get("must_not_contain", []),
               "tables_found": n_tables, "tables_expected": entry.get("expected_tables", 0),
               "runtime_s": round(time.perf_counter() - started, 3), "error": error}
        row.update(run_ab.score(entry, text))
        row["tables_ok"] = row["tables_found"] >= row["tables_expected"]
        row["text_sha"] = hashlib.sha256(text.encode()).hexdigest()[:16]
        rows.append(row)
        print(f"  {entry['document_id']:<32} recall {row['text_recall']:.3f} "
              f"char {row['char_recall']:.3f}  {row['runtime_s']:6.2f}s", flush=True)
    pbase.merge_regions_into_page = _REAL_MERGE

    # Fidelity gate: identical output to 024's frozen l5 arm at this commit.
    ab = json.loads((E024 / "scan_cohort_ab.json").read_text())
    ref = {r["document_id"]: r["text_sha"] for r in ab["arms"]["l5"]["rows"]}
    mismatched = [r["document_id"] for r in rows if ref.get(r["document_id"]) != r["text_sha"]]

    payload = {
        "commit": _REPO_COMMIT,
        "stratum": STRATUM,
        "strategy": STRATEGY,
        "device": DEVICE,
        "cohort_manifest": str(COHORT_MANIFEST.relative_to(REPO)),
        "ownership_predicate": "pbase._center_in (production), table+cell boxes excluded (production)",
        "instrumentation": "merge_regions_into_page wrapped and delegated unchanged",
        "wall_s": round(time.perf_counter() - t0, 1),
        "n_documents": len(rows),
        "n_pages": len(_PAGES),
        "fidelity_vs_024_l5_arm": {
            "documents_compared": len(rows),
            "text_sha_mismatched": len(mismatched),
            "mismatched_ids": mismatched,
        },
        "documents": rows,
        "pages": _PAGES,
    }
    (HERE / "coverage_dataset.json").write_text(json.dumps(payload, ensure_ascii=False))
    print(f"\npages recorded: {len(_PAGES)}  tokens: {sum(len(p['tokens']) for p in _PAGES)}")
    print(f"text_sha mismatches vs 024 l5 arm: {len(mismatched)} {mismatched}")
    return 0


_REPO_COMMIT = __import__("subprocess").run(
    ["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True).stdout.strip()

if __name__ == "__main__":
    raise SystemExit(main())
