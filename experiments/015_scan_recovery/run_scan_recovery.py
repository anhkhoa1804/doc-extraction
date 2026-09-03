#!/usr/bin/env python
"""015 -- Scan Recovery v1: run `scan_recovery.recover_page_elements` against
the 6 real `scan_quality` documents in the production corpus, through the
*actual* production route (`process_file`, strategy `adaptive`, default
config -- `ocr_backend: docling`), not a synthetic OCR-only harness.

This is the live-corpus step experiments 013/014 explicitly deferred:
013/014 measured OCR-stage fusion/recovery against isolated backend output;
this milestone measures the shipped `scan_recovery` orchestration against
real `Page`/`Element` objects as the pipeline actually produces them
(`ROUTE_SCANNED_PDF`/`ROUTE_IMAGE`, Docling as both layout+OCR backend,
`coordinate_unit="px"`, a real `rendered_image_path` on disk) -- the exact
preconditions `recover_page_elements` was written against.

    python experiments/015_scan_recovery/run_scan_recovery.py --device cuda --resource-state CLEAR
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import unicodedata
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "research" / "production_corpus"))
CORPUS = REPO / "research/production_corpus/corpus"

DOCS = [
    "hc_scan_vi", "hc_scan_en", "cmb_scan_multicol_en",
    "cmb_scan_stamp_table_vi", "cmb_scan_tiny_vi", "ord_invoice_png_vi",
]


def _norm(s: str) -> str:
    return unicodedata.normalize("NFC", s).strip()


def document_text(document) -> str:
    # Identical methodology to run_benchmark.document_text -- elements +
    # table cell text, NFC-normalized -- so recall numbers here are directly
    # comparable to the production-corpus run this milestone re-runs below.
    parts: list[str] = []
    for page in document.pages:
        for el in getattr(page, "elements", []) or []:
            t = getattr(el, "text", None)
            if t:
                parts.append(t)
        for tbl in getattr(page, "tables", []) or []:
            for row in getattr(tbl, "cells", []) or []:
                for cell in row if isinstance(row, list) else [row]:
                    t = getattr(cell, "text", None) if not isinstance(cell, str) else cell
                    if t:
                        parts.append(t)
    return _norm("\n".join(parts))


def recall(text: str, must: list[str]) -> tuple[float, list[str]]:
    found = [s for s in must if _norm(s) in text]
    return (len(found) / len(must) if must else 1.0), found


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--resource-state", default="unspecified")
    ap.add_argument("--json", type=Path, default=Path(__file__).parent / "results.json")
    args = ap.parse_args()

    from doc_extraction.backends.easyocr_backend import EasyOCRBackend
    from doc_extraction.cli import process_file
    from doc_extraction.ingest.scan_recovery import recover_page_elements
    from run_benchmark import configure  # same "adaptive" strategy config as production runs

    scratch_out = Path("/tmp/claude-1002/-home-leanhkhoa150204/53135489-765a-4c07-8a55-7b281fb97758/scratchpad/scan_recovery_015")
    scratch_out.mkdir(parents=True, exist_ok=True)

    manifest = json.loads((CORPUS / "manifest.json").read_text())
    by_id = {d["document_id"]: d for d in manifest["documents_list"]}

    config = configure("adaptive", None, args.device)
    print(f"device: {config.device}, ocr_backend: {config.ocr_backend}, render_dpi: {config.render_dpi}\n")

    easyocr_backend = EasyOCRBackend(device=config.device, languages=config.ocr_languages)

    cases = []
    for name in DOCS:
        meta = by_id[name]
        src = CORPUS / meta["filename"]
        must = meta["must_contain"]

        t0 = time.perf_counter()
        document = process_file(src, config, output_root=scratch_out)
        t_process = time.perf_counter() - t0

        page = document.pages[0]

        baseline_text = document_text(document)
        baseline_recall, baseline_found = recall(baseline_text, must)

        old_texts = {el.id: el.text for el in page.elements if el.text}

        # cli.py's baseline route (pipelines/image.py, pipelines/pdf.py)
        # writes rendered_image_path via output_dir / "rendered" / ..., and
        # output_dir itself is always absolute (process_file builds it from
        # output_root.resolve()-derived paths) -- no relative-path handling
        # needed here.
        image_path = Path(page.rendered_image_path) if page.rendered_image_path else None
        if image_path is None or not image_path.exists():
            raise RuntimeError(f"{name}: no rendered_image_path on page (got {page.rendered_image_path!r})")

        t0 = time.perf_counter()
        summary = recover_page_elements(
            page, image_path, easyocr_backend,
            page_width=page.width, page_height=page.height, dpi=page.dpi,
        )
        triggered = any(r.trigger == "agreement_low" for r in summary.records)
        t_recovery = time.perf_counter() - t0

        final_text = document_text(document)
        final_recall, final_found = recall(final_text, must)

        changed = [r for r in summary.records if r.decision == "replaced"]

        case = {
            "document": name,
            "baseline_recall": round(baseline_recall, 4),
            "final_recall": round(final_recall, 4),
            "triggered": triggered,
            "n_elements_checked": len(old_texts),
            "n_triggered": sum(1 for r in summary.records if r.trigger == "agreement_low"),
            "n_replaced": len(changed),
            "changes": [
                {"element_id": r.element_id, "old_text": r.old_text, "new_text": r.new_text,
                 "decision": r.decision, "reasons": r.reasons}
                for r in summary.records
            ],
            "process_seconds": round(t_process, 3),
            "recovery_seconds": round(t_recovery, 3),
            "rendered_image_path": page.rendered_image_path,
        }
        cases.append(case)

        flag = " <-- RECALL CHANGED" if abs(final_recall - baseline_recall) > 1e-9 else ""
        print(f"{name:<26} baseline={baseline_recall:.3f} final={final_recall:.3f} "
              f"triggered={triggered} replaced={len(changed)} "
              f"process={t_process:.2f}s recovery={t_recovery:.2f}s{flag}")

    args.json.write_text(json.dumps({"device": config.device, "resource_state": args.resource_state,
                                      "cases": cases}, ensure_ascii=False, indent=2))
    print(f"\nwrote {args.json}")


if __name__ == "__main__":
    main()
