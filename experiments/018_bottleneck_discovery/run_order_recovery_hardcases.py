#!/usr/bin/env python
"""018 -- Order Recovery v1 against the 14-document hardcase corpus (real
process_file route), completing the same two-corpus validation pattern
experiments 015/017 already established.

    python experiments/018_bottleneck_discovery/run_order_recovery_hardcases.py --device cuda
"""
from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
CORPUS = REPO / "research/hardcases/corpus"


def _norm(s: str) -> str:
    return unicodedata.normalize("NFC", s).strip()


def document_text(document) -> str:
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


def recall(text: str, must: list[str]) -> float:
    if not must:
        return 1.0
    return sum(1 for s in must if _norm(s) in text) / len(must)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default="cuda")
    args = ap.parse_args()

    from doc_extraction.backends.easyocr_backend import EasyOCRBackend
    from doc_extraction.cli import process_file
    from doc_extraction.config import PipelineConfig
    from doc_extraction.ingest.order_recovery import recover_page_order

    scratch_out = Path("/tmp/claude-1002/-home-leanhkhoa150204/53135489-765a-4c07-8a55-7b281fb97758/scratchpad/order_recovery_018/hardcases")
    scratch_out.mkdir(parents=True, exist_ok=True)

    manifest = json.loads((CORPUS / "manifest.json").read_text())
    cases = manifest["cases"]

    config = PipelineConfig(device=args.device)
    easyocr_backend = EasyOCRBackend(device=config.device, languages=config.ocr_languages)

    print(f"device: {config.device}, n_cases: {len(cases)}\n")
    rows = []
    for case in cases:
        name = case["case_id"] if "case_id" in case else case.get("id", case.get("document_id"))
        filename = case.get("filename") or f"{name}.pdf"
        src = CORPUS / filename
        must = case.get("must_contain", [])

        document = process_file(src, config, output_root=scratch_out)
        baseline_recall = recall(document_text(document), must)

        n_replaced = 0
        for page in document.pages:
            if not page.rendered_image_path or not Path(page.rendered_image_path).exists():
                continue
            summary = recover_page_order(
                page, Path(page.rendered_image_path), easyocr_backend,
                page_width=page.width, page_height=page.height, dpi=page.dpi,
            )
            n_replaced += summary.replaced

        final_recall = recall(document_text(document), must)
        delta = round(final_recall - baseline_recall, 4)
        rows.append({"document": name, "baseline": baseline_recall, "final": final_recall,
                      "delta": delta, "n_replaced": n_replaced})
        flag = " <-- CHANGED" if abs(delta) > 1e-9 else ""
        print(f"{name:<24} baseline={baseline_recall:.3f} final={final_recall:.3f} replaced={n_replaced}{flag}")

    changed = [r for r in rows if abs(r["delta"]) > 1e-9]
    print(f"\ndocs changed: {len(changed)} / {len(rows)}")
    print(f"total replaced: {sum(r['n_replaced'] for r in rows)}")


if __name__ == "__main__":
    main()
