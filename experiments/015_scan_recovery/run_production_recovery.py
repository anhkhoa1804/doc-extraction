#!/usr/bin/env python
"""015 -- Scan Recovery v1, full 58-document production-shaped corpus.

Re-runs the standard production-corpus benchmark (`process_file`, strategy
`adaptive`, default config) and, for every page that has a rendered image
(the scanned-page route only -- `coordinate_unit="px"` + a real
`rendered_image_path`; digital-PDF/office pages have neither and are left
untouched by construction), applies `scan_recovery.recover_page_elements`
as an extra pass. Reports mean recall before/after across the whole corpus,
not just the 6 scan_quality documents experiment 015's first script
targeted -- the point is to catch any regression this recovery step might
introduce on documents where recovery was never meant to fire.

    python experiments/015_scan_recovery/run_production_recovery.py --device cuda --resource-state CLEAR
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
    found = sum(1 for s in must if _norm(s) in text)
    return found / len(must)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--resource-state", default="unspecified")
    ap.add_argument("--json", type=Path, default=Path(__file__).parent / "production_results.json")
    args = ap.parse_args()

    from doc_extraction.backends.easyocr_backend import EasyOCRBackend
    from doc_extraction.cli import process_file
    from doc_extraction.ingest.scan_recovery import recover_page_elements
    from run_benchmark import configure

    scratch_out = Path("/tmp/claude-1002/-home-leanhkhoa150204/53135489-765a-4c07-8a55-7b281fb97758/scratchpad/scan_recovery_015_prod")
    scratch_out.mkdir(parents=True, exist_ok=True)

    manifest = json.loads((CORPUS / "manifest.json").read_text())
    docs = manifest["documents_list"]

    config = configure("adaptive", None, args.device)
    print(f"device: {config.device}, ocr_backend: {config.ocr_backend}, render_dpi: {config.render_dpi}")
    print(f"{len(docs)} documents\n")

    easyocr_backend = EasyOCRBackend(device=config.device, languages=config.ocr_languages)

    rows = []
    t_start = time.perf_counter()
    for entry in docs:
        name = entry["document_id"]
        src = CORPUS / entry["filename"]
        must = entry["must_contain"] or []

        t0 = time.perf_counter()
        try:
            document = process_file(src, config, output_root=scratch_out)
        except Exception as exc:  # noqa: BLE001 - a crash is a result, not an abort
            rows.append({"document": name, "error": f"{type(exc).__name__}: {exc}"})
            print(f"{name:<30} ERROR: {exc}")
            continue
        t_process = time.perf_counter() - t0

        baseline_recall = recall(document_text(document), must)

        n_pages_with_image = 0
        n_triggered = 0
        n_replaced = 0
        t0 = time.perf_counter()
        for page in document.pages:
            if not page.rendered_image_path or not Path(page.rendered_image_path).exists():
                continue
            n_pages_with_image += 1
            summary = recover_page_elements(
                page, Path(page.rendered_image_path), easyocr_backend,
                page_width=page.width, page_height=page.height, dpi=page.dpi,
            )
            n_triggered += sum(1 for r in summary.records if r.trigger == "agreement_low")
            n_replaced += summary.replaced
        t_recovery = time.perf_counter() - t0

        final_recall = recall(document_text(document), must)

        row = {
            "document": name,
            "labels": entry["hard_case_labels"],
            "baseline_recall": round(baseline_recall, 4),
            "final_recall": round(final_recall, 4),
            "delta": round(final_recall - baseline_recall, 4),
            "pages": entry["page_count"],
            "n_pages_with_rendered_image": n_pages_with_image,
            "n_triggered": n_triggered,
            "n_replaced": n_replaced,
            "process_seconds": round(t_process, 3),
            "recovery_seconds": round(t_recovery, 3),
        }
        rows.append(row)
        flag = " <-- CHANGED" if abs(row["delta"]) > 1e-9 else ""
        print(f"{name:<30} baseline={baseline_recall:.3f} final={final_recall:.3f} "
              f"imgpages={n_pages_with_image} triggered={n_triggered} replaced={n_replaced} "
              f"proc={t_process:.2f}s rec={t_recovery:.2f}s{flag}")

    t_total = time.perf_counter() - t_start
    ok_rows = [r for r in rows if "error" not in r]
    n = len(ok_rows)
    mean_baseline = sum(r["baseline_recall"] for r in ok_rows) / n if n else 0.0
    mean_final = sum(r["final_recall"] for r in ok_rows) / n if n else 0.0
    changed = [r for r in ok_rows if abs(r["delta"]) > 1e-9]
    regressed = [r for r in changed if r["delta"] < 0]
    improved = [r for r in changed if r["delta"] > 0]

    summary = {
        "n_documents": len(rows),
        "n_ok": n,
        "n_errors": len(rows) - n,
        "mean_baseline_recall": round(mean_baseline, 4),
        "mean_final_recall": round(mean_final, 4),
        "n_documents_changed": len(changed),
        "n_documents_improved": len(improved),
        "n_documents_regressed": len(regressed),
        "improved_documents": [r["document"] for r in improved],
        "regressed_documents": [r["document"] for r in regressed],
        "total_pages_recovery_attempted": sum(r["n_pages_with_rendered_image"] for r in ok_rows),
        "total_triggered": sum(r["n_triggered"] for r in ok_rows),
        "total_replaced": sum(r["n_replaced"] for r in ok_rows),
        "total_process_seconds": round(sum(r["process_seconds"] for r in ok_rows), 2),
        "total_recovery_seconds": round(sum(r["recovery_seconds"] for r in ok_rows), 2),
        "wall_clock_seconds": round(t_total, 2),
        "device": config.device,
        "resource_state": args.resource_state,
    }
    print("\n=== summary ===")
    print(json.dumps(summary, indent=2))

    args.json.write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2))
    print(f"\nwrote {args.json}")


if __name__ == "__main__":
    main()
