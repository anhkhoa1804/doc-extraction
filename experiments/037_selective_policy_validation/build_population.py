#!/usr/bin/env python
"""Build 037's source-only, document-disjoint synthetic population manifest."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pymupdf

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CORPUS = ROOT / "research/production_corpus/corpus"
MANIFEST = CORPUS / "manifest.json"
RENDER_DPI = 200


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_table_bbox(pdf: Path) -> tuple[dict[str, float], str]:
    """Derive table bounds from source generator tokens, never model output."""
    doc = pymupdf.open(pdf)
    page = doc[0]
    words = page.get_text("words")
    # Exact distinctive table tokens from the generator; these span all rows.
    anchors = {"Item", "Mô", "Product", "Sản", "Installation", "Dịch"}
    hits = [w for w in words if w[4] in anchors]
    if len(hits) < 3:
        raise ValueError(f"insufficient source table token anchors in {pdf.name}: {len(hits)}")
    x0, y0 = min(w[0] for w in hits), min(w[1] for w in hits)
    x1, y1 = max(w[2] for w in hits), max(w[3] for w in hits)
    # Generator always starts at x=60.  Its normal primitive is 372 points
    # wide; tiny style is narrower.  Token height identifies the latter.
    tiny = max(w[3] - w[1] for w in hits) < 6
    width, row_height = (232.0, 9.0) if tiny else (372.0, 20.0)
    # Text is inset 2pt; top text baseline is within the header row.  Expand
    # to the fixed four-row primitive, not a prediction-dependent extent.
    table_y0 = min(y0 - (row_height - 3), y0 - 12)
    return ({"x0": 60.0, "y0": table_y0, "x1": 60.0 + width,
             "y1": table_y0 + 4 * row_height}, "tiny" if tiny else "normal")


def main() -> int:
    raw = json.loads(MANIFEST.read_text())
    included = []
    for entry in raw["documents_list"]:
        if entry["expected_tables"] != 1 or entry["format"] != "pdf" or entry["page_count"] != 1:
            continue
        path = CORPUS / entry["filename"]
        try:
            bbox, style = source_table_bbox(path)
        except ValueError:
            continue  # rasterized source has no committed vector geometry
        included.append({
            "document_id": entry["document_id"], "source_document_group": entry["document_id"],
            "source_file": entry["filename"], "source_sha256": digest(path),
            "source_table_bbox_points": bbox, "source_table_style": style,
            "hard_case_labels": entry["hard_case_labels"],
        })
    included.sort(key=lambda x: hashlib.sha256(("037-split-v1:" + x["document_id"]).encode()).hexdigest())
    cut = len(included) // 2
    for i, entry in enumerate(included):
        entry["split"] = "development" if i < cut else "held_out_test"
        entry["page_id"] = f"{entry['document_id']}:page:0"
        entry["gt_table_id"] = f"{entry['document_id']}:table:0"
        entry["render_dpi"] = RENDER_DPI
    payload = {
        "experiment": "037_selective_policy_validation",
        "status": "pre_treatment_population_frozen",
        "source_manifest": str(MANIFEST.relative_to(ROOT)), "source_manifest_sha256": digest(MANIFEST),
        "source_generator": "research/production_corpus/generate.py", "source_generator_seed": 20260902,
        "selection": "all one-page table-bearing PDFs with source-vector token geometry",
        "split_rule": "SHA256(037-split-v1:document_id), first floor(N/2) development",
        "n_documents": len(included),
        "split_counts": {"development": cut, "held_out_test": len(included) - cut},
        "records": included,
    }
    (HERE / "population_manifest.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"n": len(included), "development": cut, "held_out_test": len(included)-cut}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
