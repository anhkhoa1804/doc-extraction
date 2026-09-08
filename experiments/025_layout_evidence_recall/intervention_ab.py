"""025 line 5 -- falsifiable A/B for a deterministic layout-coverage fix.

One arm per `--intervention`, all else identical. An intervention is a pure
function `list[Region] -> list[Region]` applied to the layout backend's
output BEFORE `merge_regions_into_page` sees it. Production code is not
modified: the transform is installed by wrapping the layout backend object
this script constructs.

`none` is the control and must reproduce 024's frozen `l5` arm byte for byte
(`text_sha`), which is asserted, not assumed.

Every arm reports both halves of the 024 lesson (§15) -- coverage metrics
AND output metrics -- plus the §11 accounting that distinguishes a real
upstream fix from a relocated fallback:

    tokens claimed by layout   (up = the detector now covers them)
    tokens recovered by L5     (down = L5 no longer has to)
    orphans left               (the residue neither reached)

and the §12/§13 couplings: reading order and table structure are measured
for every arm, so an order gain cannot be silently credited to the ordering
algorithm when it came from segmentation.

    python experiments/025_layout_evidence_recall/intervention_ab.py \
        --intervention none [--intervention ...]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import Counter
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
from doc_extraction.pipelines.base import Region  # noqa: E402
from doc_extraction.schemas.element import BBox  # noqa: E402
from run_benchmark import document_text  # noqa: E402

import interventions  # noqa: E402

COHORT_MANIFEST = E024 / "scan_cohort_manifest.json"
CORPUS = E024 / "_runs" / "scan_cohort_corpus"
STRATUM, STRATEGY, DEVICE = "SCAN-49", "adaptive", "cpu"

_REAL_MERGE = pbase.merge_regions_into_page
_CURRENT = [None]


class InterveningLayout:
    """Wraps the layout backend and applies the intervention to its output.

    The OCR tokens the intervention needs are not available at layout time,
    so the transform is deferred: the wrapper stores the detector's regions
    and `observe_merge` applies it once the page's tokens and tables exist.
    That is also the honest place for it -- an intervention that needs OCR
    evidence is a post-detection correction, not a better detector.
    """

    def __init__(self, inner, transform):
        self.inner, self.transform = inner, transform
        self.name = inner.name

    def is_available(self):
        return self.inner.is_available()

    def analyze(self, page):
        return self.inner.analyze(page)


def make_merge(transform, record: list):
    def merge(page_index, width, height, dpi, layout_result, ocr_result,
              table_result, rendered_image_path):
        detected = list(layout_result.regions)
        tables = list(table_result.tables) if table_result else []
        added = transform(detected, ocr_result, tables, width, height) if transform else []
        layout_result.regions = detected + added

        regions = layout_result.regions
        tbox = [t.bbox for t in tables if getattr(t, "bbox", None) is not None]
        cbox = [c.bbox for t in tables for c in (getattr(t, "cells", None) or [])
                if getattr(c, "bbox", None) is not None]
        claim = Counter()
        for tok in ocr_result.tokens:
            if any(pbase._center_in(tok.bbox, r.bbox) for r in detected):
                claim["region_detected"] += 1
            elif any(pbase._center_in(tok.bbox, r.bbox) for r in added):
                claim["region_synthesized"] += 1
            elif any(pbase._center_in(tok.bbox, b) for b in cbox):
                claim["cell"] += 1
            elif any(pbase._center_in(tok.bbox, b) for b in tbox):
                claim["table"] += 1
            else:
                claim["orphan"] += 1
        page = _REAL_MERGE(page_index, width, height, dpi, layout_result, ocr_result,
                           table_result, rendered_image_path)
        rec = [e for e in page.elements
               if (e.extra or {}).get("recovered") == "orphan_ocr_tokens"]
        record.append({
            "document_id": _CURRENT[0], "page_index": page_index,
            "tokens": len(ocr_result.tokens),
            "regions_detected": len(detected), "regions_synthesized": len(added),
            "synthesized_labels": [r.label for r in added],
            "tables": len(tables),
            "table_cells": sum(len(getattr(t, "cells", None) or []) for t in tables),
            "claim": dict(claim),
            "l5_elements": len(rec),
            "l5_recovered_tokens": sum((e.extra or {}).get("token_count", 0) for e in rec),
        })
        return page
    return merge


def capture(document) -> dict:
    """Reading-order and table detail, from the produced IR (§12, §13)."""
    pages = []
    for p in document.pages:
        els = list(p.elements)
        ro = [e.id for e in sorted(els, key=lambda e: (e.order_index if e.order_index
                                                       is not None else 1e9))]
        pages.append({
            "page_index": p.index,
            "n_elements": len(els),
            "element_types": dict(Counter(str(e.type) for e in els)),
            "reading_order": ro[:80],
            "n_tables": len(getattr(p, "tables", []) or []),
            "table_rows": [getattr(t, "n_rows", None) for t in (getattr(p, "tables", []) or [])],
            "table_cols": [getattr(t, "n_cols", None) for t in (getattr(p, "tables", []) or [])],
            "table_cells": [len(getattr(t, "cells", None) or [])
                            for t in (getattr(p, "tables", []) or [])],
            "table_cell_chars": [sum(len(c.text or "") for c in (getattr(t, "cells", None) or []))
                                 for t in (getattr(p, "tables", []) or [])],
        })
    return {"pages": pages}


def run_arm(name: str, docs: list[dict]) -> dict:
    transform = interventions.REGISTRY[name]
    config = run_ab.configure(STRATEGY, DEVICE)
    config.ocr_backend = f"__025_{name}"
    layout = DoclingBackend(device=DEVICE, ocr_languages=PipelineConfig().ocr_languages)
    ocr = TesseractBackend(device=DEVICE, languages=config.ocr_languages)
    tables = TableTransformerBackend(device=DEVICE)
    cli._COMPONENT_BACKEND_CACHE[(config.device, tuple(config.ocr_languages),
                                  config.ocr_backend)] = (layout, ocr, tables)

    record: list = []
    pbase.merge_regions_into_page = make_merge(transform, record)
    out_root = HERE / "_runs" / "intervention" / name
    rows, caps = [], {}
    print(f"\n=== arm: {name} ===", flush=True)
    t0 = time.perf_counter()
    for entry in docs:
        _CURRENT[0] = entry["document_id"]
        started = time.perf_counter()
        try:
            doc = cli.process_file(CORPUS / entry["filename"], config, output_root=out_root)
            text = document_text(doc)
            n_tables = sum(len(getattr(p, "tables", []) or []) for p in doc.pages)
            cap, error = capture(doc), None
        except Exception as exc:  # noqa: BLE001 - a crash is a result
            text, n_tables, cap, error = "", 0, {"pages": []}, f"{type(exc).__name__}: {exc}"
        row = {"document_id": entry["document_id"], "language": entry["language"],
               "labels": entry["hard_case_labels"], "pages": entry["page_count"],
               "tables_found": n_tables, "tables_expected": entry.get("expected_tables", 0),
               "runtime_s": round(time.perf_counter() - started, 3), "error": error}
        row.update(run_ab.score(entry, text))
        row["tables_ok"] = row["tables_found"] >= row["tables_expected"]
        row["text_sha"] = hashlib.sha256(text.encode()).hexdigest()[:16]
        rows.append(row)
        caps[entry["document_id"]] = cap
        print(f"  {entry['document_id']:<32} recall {row['text_recall']:.3f} "
              f"char {row['char_recall']:.3f} {row['runtime_s']:6.2f}s", flush=True)
    pbase.merge_regions_into_page = _REAL_MERGE

    cl = Counter()
    for r in record:
        cl.update(r["claim"])
    tot = sum(cl.values())
    return {
        "arm": name,
        "wall_s": round(time.perf_counter() - t0, 1),
        "rows": rows, "captures": caps, "pages": record,
        "coverage": {
            "tokens": tot,
            "claimed_by_detected_region": cl["region_detected"],
            "claimed_by_synthesized_region": cl["region_synthesized"],
            "claimed_by_cell": cl["cell"], "inside_table_not_cell": cl["table"],
            "orphan": cl["orphan"],
            "region_coverage_recall": round((cl["region_detected"] + cl["region_synthesized"]) / tot, 4) if tot else None,
            "orphan_rate": round(cl["orphan"] / tot, 4) if tot else None,
            "regions_synthesized": sum(r["regions_synthesized"] for r in record),
            "l5_recovered_tokens": sum(r["l5_recovered_tokens"] for r in record),
            "l5_elements": sum(r["l5_elements"] for r in record),
        },
        "aggregate": run_ab.aggregate(rows),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--intervention", action="append", default=None,
                    choices=sorted(interventions.REGISTRY))
    ap.add_argument("--out", default="intervention_ab.json")
    args = ap.parse_args()
    arms = args.intervention or ["none"]

    cohort = json.loads(COHORT_MANIFEST.read_text())
    docs = [d for d in cohort["documents_list"] if d["stratum"] == STRATUM]
    for d in docs:
        got = hashlib.sha256((CORPUS / d["filename"]).read_bytes()).hexdigest()
        if got != d["sha256"]:
            print(f"FATAL: {d['filename']} does not match the frozen manifest")
            return 1
    print(f"cohort verified: {len(docs)} documents, sha256 matched", flush=True)

    commit = __import__("subprocess").run(["git", "rev-parse", "HEAD"], cwd=REPO,
                                          capture_output=True, text=True).stdout.strip()
    results = {"commit": commit, "stratum": STRATUM, "strategy": STRATEGY,
               "device": DEVICE, "arms": {}}
    for a in arms:
        results["arms"][a] = run_arm(a, docs)

    if "none" in results["arms"]:
        ab = json.loads((E024 / "scan_cohort_ab.json").read_text())
        ref = {r["document_id"]: r["text_sha"] for r in ab["arms"]["l5"]["rows"]}
        mism = [r["document_id"] for r in results["arms"]["none"]["rows"]
                if ref.get(r["document_id"]) != r["text_sha"]]
        results["control_fidelity_vs_024_l5"] = {"mismatched": len(mism), "ids": mism}
        print(f"\ncontrol vs 024 l5 arm: {len(mism)} text_sha mismatches {mism}")

    (HERE / args.out).write_text(json.dumps(results, ensure_ascii=False))
    for a, r in results["arms"].items():
        c, g = r["coverage"], r["aggregate"]
        print(f"\n[{a}] coverage {c['region_coverage_recall']} orphan {c['orphan_rate']} "
              f"synth {c['regions_synthesized']} L5 {c['l5_recovered_tokens']} | "
              f"exact {g['mean_text_recall']} char {g['mean_char_recall']} "
              f"perfect {g['docs_perfect']} order {g['docs_order_ok']} tables {g['docs_tables_ok']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
