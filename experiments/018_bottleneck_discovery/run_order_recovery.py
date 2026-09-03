#!/usr/bin/env python
"""018 -- Order Recovery v1 against the 6 real scan documents, then the
58-document production corpus. Same methodology as experiment 015's
scan_recovery validation (real process_file route, not a synthetic
harness), for a fair PROMOTE/EXPERIMENTAL/REJECT decision on
order_recovery specifically.

    python experiments/018_bottleneck_discovery/run_order_recovery.py --device cuda --scope six
    python experiments/018_bottleneck_discovery/run_order_recovery.py --device cuda --scope corpus
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

SIX_DOCS = [
    "hc_scan_vi", "hc_scan_en", "cmb_scan_multicol_en",
    "cmb_scan_stamp_table_vi", "cmb_scan_tiny_vi", "ord_invoice_png_vi",
]


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
    ap.add_argument("--scope", choices=["six", "corpus"], default="six")
    ap.add_argument("--json", type=Path, default=None)
    args = ap.parse_args()

    from doc_extraction.backends.easyocr_backend import EasyOCRBackend
    from doc_extraction.cli import process_file
    from doc_extraction.ingest.order_recovery import recover_page_order
    from run_benchmark import configure

    scratch_out = Path("/tmp/claude-1002/-home-leanhkhoa150204/53135489-765a-4c07-8a55-7b281fb97758/scratchpad/order_recovery_018") / args.scope
    scratch_out.mkdir(parents=True, exist_ok=True)

    manifest = json.loads((CORPUS / "manifest.json").read_text())
    docs = manifest["documents_list"]
    if args.scope == "six":
        by_id = {d["document_id"]: d for d in docs}
        docs = [by_id[name] for name in SIX_DOCS]

    config = configure("adaptive", None, args.device)
    print(f"device: {config.device}, ocr_backend: {config.ocr_backend}, scope: {args.scope}, n_docs: {len(docs)}\n")

    easyocr_backend = EasyOCRBackend(device=config.device, languages=config.ocr_languages)

    rows = []
    for entry in docs:
        name = entry["document_id"]
        src = CORPUS / entry["filename"]
        must = entry["must_contain"] or []

        t0 = time.perf_counter()
        try:
            document = process_file(src, config, output_root=scratch_out)
        except Exception as exc:  # noqa: BLE001
            rows.append({"document": name, "error": f"{type(exc).__name__}: {exc}"})
            print(f"{name:<30} ERROR: {exc}")
            continue
        t_process = time.perf_counter() - t0

        baseline_recall = recall(document_text(document), must)

        n_pages_with_image = 0
        n_replaced = 0
        n_kept = 0
        changes = []
        t0 = time.perf_counter()
        for page in document.pages:
            if not page.rendered_image_path or not Path(page.rendered_image_path).exists():
                continue
            n_pages_with_image += 1
            summary = recover_page_order(
                page, Path(page.rendered_image_path), easyocr_backend,
                page_width=page.width, page_height=page.height, dpi=page.dpi,
            )
            n_replaced += summary.replaced
            n_kept += summary.kept
            changes.extend(
                {"element_id": r.element_id, "old_text": r.old_text, "new_text": r.reconstruction,
                 "jaccard": r.jaccard, "order_consistency": r.order_consistency, "decision": r.decision}
                for r in summary.records if r.decision == "replaced"
            )
        t_recovery = time.perf_counter() - t0

        final_recall = recall(document_text(document), must)

        row = {
            "document": name, "labels": entry["hard_case_labels"],
            "baseline_recall": round(baseline_recall, 4), "final_recall": round(final_recall, 4),
            "delta": round(final_recall - baseline_recall, 4),
            "n_pages_with_rendered_image": n_pages_with_image,
            "n_replaced": n_replaced, "n_kept": n_kept, "changes": changes,
            "process_seconds": round(t_process, 3), "recovery_seconds": round(t_recovery, 3),
        }
        rows.append(row)
        flag = " <-- CHANGED" if abs(row["delta"]) > 1e-9 else ""
        print(f"{name:<30} baseline={baseline_recall:.3f} final={final_recall:.3f} "
              f"replaced={n_replaced} kept={n_kept} proc={t_process:.2f}s rec={t_recovery:.2f}s{flag}")
        for c in changes:
            print(f"    REPLACED {c['element_id']}: jaccard={c['jaccard']:.3f} order={c['order_consistency']:.3f}")
            print(f"      old: {c['old_text']!r}")
            print(f"      new: {c['new_text']!r}")

    ok_rows = [r for r in rows if "error" not in r]
    n = len(ok_rows)
    mean_baseline = sum(r["baseline_recall"] for r in ok_rows) / n if n else 0.0
    mean_final = sum(r["final_recall"] for r in ok_rows) / n if n else 0.0
    changed = [r for r in ok_rows if abs(r["delta"]) > 1e-9]
    regressed = [r for r in changed if r["delta"] < 0]
    improved = [r for r in changed if r["delta"] > 0]

    summary = {
        "scope": args.scope, "n_documents": len(rows), "n_ok": n,
        "mean_baseline_recall": round(mean_baseline, 4), "mean_final_recall": round(mean_final, 4),
        "n_documents_changed": len(changed), "n_documents_improved": len(improved),
        "n_documents_regressed": len(regressed),
        "improved_documents": [r["document"] for r in improved],
        "regressed_documents": [r["document"] for r in regressed],
        "total_replaced": sum(r["n_replaced"] for r in ok_rows),
        "total_kept": sum(r["n_kept"] for r in ok_rows),
        "device": config.device,
    }
    print("\n=== summary ===")
    print(json.dumps(summary, indent=2, ensure_ascii=False))

    out = args.json or (Path(__file__).parent / f"order_recovery_{args.scope}_results.json")
    out.write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2))
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
