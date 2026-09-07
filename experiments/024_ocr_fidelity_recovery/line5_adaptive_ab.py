"""LINE 5 under the SHIPPED ROUTER -- what production actually gets.

`line5_production_e2e.py` measured line 5 with `--strategy visual`, which
forces render+OCR on every page. That isolates the recogniser and is the
right way to see the mechanism; it is not what production does. The shipped
router sends a page to OCR only when its text layer is absent or fails the
quality gate, so most corpus pages never reach `merge_regions_into_page` at
all -- and line 5 lives inside `merge_regions_into_page`.

This measures the same production implementation under `--strategy
adaptive`: same corpus, same 49 documents, same scorer, same thresholds,
same router, same `tesseract` arm built exactly as production builds it,
same layout and table backends. The ONLY difference between the two arms is
whether `_orphan_tokens` returns the orphans it finds or an empty list --
which is precisely the pre-`1ae81e0` behaviour, since an empty orphan list
appends no element and leaves `notes` at `table_result.warnings`.

No production code is modified. The baseline arm is produced by patching
`base._orphan_tokens` at the module boundary, and the scorer, `configure`,
`aggregate` and `score` are imported from experiment 023's `run_ab` so
these numbers are directly comparable to every A/B in this repository.

Phases
------
    0  warmup       one scanned document, discarded -- so arm 1 does not pay
                    model load that arm 2 gets for free
    1  baseline     L5 off, timed, minimal instrumentation
    2  l5           L5 on, timed, minimal instrumentation
    3  audit        L5 on, UNTIMED, full recording: per-page orphan
                    accounting, table exclusions, duplication check,
                    isolated L5 CPU cost

Layout is NOT shared between arms (unlike `run_ab`'s cross-condition
memoization): sharing would give arm 2 free layout that arm 1 paid for and
destroy the wall-time comparison. Under `adaptive` only a handful of pages
reach layout at all, so paying twice is cheap. A per-page region fingerprint
is recorded in both arms to prove layout was in fact identical.

`_runs/` is excluded by `experiments/**/_runs/`. CPU only. Writes `line5_adaptive_ab.json` beside this file.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
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
from run_benchmark import _norm, document_text  # noqa: E402

CORPUS = REPO / "research/production_corpus/corpus"
STRATEGY = "adaptive"
DEVICE = "cpu"

_REAL_ORPHAN_TOKENS = pbase._orphan_tokens
_REAL_MERGE = pbase.merge_regions_into_page


# --- instrumentation ---------------------------------------------------------

class CountingOCR:
    """Counts and times every OCR invocation the router actually makes.

    A single backend has no `stats` attribute, which is why `run_ab`'s
    adaptive result recorded `pages_ocred: null` -- the adaptive workload
    was never measured. This wrapper is the measurement: `recognize` is the
    one entry point `stages/ocr.py` calls, so a call here is an OCR
    invocation and nothing else is."""

    def __init__(self, inner) -> None:
        self.inner = inner
        self.name = inner.name
        self.calls: list[dict] = []
        self.current_doc: str | None = None

    def is_available(self) -> bool:
        return self.inner.is_available()

    def recognize(self, page):
        t0 = time.perf_counter()
        result = self.inner.recognize(page)
        dt = time.perf_counter() - t0
        self.calls.append({
            "document_id": self.current_doc,
            "page_index": page.page_index,
            "seconds": round(dt, 4),
            "tokens": len(result.tokens),
        })
        return result


class LayoutFingerprint:
    """Wraps the layout backend to record what it produced per call, so the
    claim 'layout was identical in both arms' is measured, not assumed."""

    def __init__(self, inner) -> None:
        self.inner = inner
        self.name = inner.name
        self.prints: list[str] = []

    def is_available(self) -> bool:
        return self.inner.is_available()

    def analyze(self, page):
        result = self.inner.analyze(page)
        payload = "|".join(
            f"{r.label}:{r.bbox.x0:.2f},{r.bbox.y0:.2f},{r.bbox.x1:.2f},{r.bbox.y1:.2f}"
            for r in result.regions
        )
        self.prints.append(hashlib.sha256(payload.encode()).hexdigest()[:16])
        return result


def make_orphan_hook(enabled: bool, record: list | None):
    """The single switch between the two arms.

    `enabled=False` reproduces pre-`1ae81e0` `merge_regions_into_page`
    exactly: with no orphans, the recovery loop appends nothing and `notes`
    stays `list(table_result.warnings)`.
    """
    def hook(regions, ocr_result, tables):
        orphans = _REAL_ORPHAN_TOKENS(regions, ocr_result, tables)
        if record is not None:
            unclaimed = [
                t for t in ocr_result.tokens
                if not any(pbase._center_in(t.bbox, r.bbox) for r in regions)
            ]
            t0 = time.perf_counter()
            blocks = pbase._cluster_orphans(_REAL_ORPHAN_TOKENS(regions, ocr_result, tables))
            l5_s = time.perf_counter() - t0
            record.append({
                "tokens_recognised": len(ocr_result.tokens),
                "regions": len(regions),
                "tables": len(tables),
                "unclaimed_by_region": len(unclaimed),
                "orphans": len(orphans),
                "table_excluded": len(unclaimed) - len(orphans),
                "blocks": len(blocks),
                "l5_isolated_s": round(l5_s, 6),
                "region_boxes": [[r.bbox.x0, r.bbox.y0, r.bbox.x1, r.bbox.y1] for r in regions],
                "table_boxes": (
                    [[t.bbox.x0, t.bbox.y0, t.bbox.x1, t.bbox.y1]
                     for t in tables if getattr(t, "bbox", None) is not None]
                    + [[c.bbox.x0, c.bbox.y0, c.bbox.x1, c.bbox.y1]
                       for t in tables for c in (getattr(t, "cells", None) or [])
                       if getattr(c, "bbox", None) is not None]
                ),
                "orphan_texts": [t.text for t in orphans],
                "claimed_texts": [
                    t.text for t in ocr_result.tokens
                    if any(pbase._center_in(t.bbox, r.bbox) for r in regions)
                ],
            })
        return orphans if enabled else []
    return hook


def install(enabled: bool, record: list | None) -> None:
    pbase._orphan_tokens = make_orphan_hook(enabled, record)


def restore() -> None:
    pbase._orphan_tokens = _REAL_ORPHAN_TOKENS


# --- per-document capture ----------------------------------------------------

def capture(document) -> dict:
    """Everything the regression audit needs, taken from the produced IR."""
    pages, recovered = [], []
    for page in document.pages:
        els = list(page.elements or [])
        rec = [e for e in els if (e.extra or {}).get("recovered") == "orphan_ocr_tokens"]
        native = [e for e in els if (e.extra or {}).get("recovered") != "orphan_ocr_tokens"]
        pages.append({
            "index": page.index,
            "route": page.source_route,
            "n_elements": len(els),
            "n_native_elements": len(native),
            "n_recovered_elements": len(rec),
            "n_tables": len(page.tables or []),
            "n_cells": sum(len(t.cells or []) for t in (page.tables or [])),
            "native_text_sha": hashlib.sha256(
                "\n".join(e.text or "" for e in native).encode()).hexdigest()[:16],
            "table_text_sha": hashlib.sha256(
                "\n".join(c.text or "" for t in (page.tables or [])
                          for c in (t.cells or [])).encode()).hexdigest()[:16],
            "reading_order": list(page.reading_order or []),
            "notes": list(page.notes or []),
        })
        for e in rec:
            pages_ro = list(page.reading_order or [])
            recovered.append({
                "document_id": document.document_id,
                "page_index": page.index,
                "element_id": e.id,
                "text": e.text,
                "type": e.type.value if hasattr(e.type, "value") else str(e.type),
                "bbox": [e.bbox.x0, e.bbox.y0, e.bbox.x1, e.bbox.y1] if e.bbox else None,
                "confidence": e.confidence,
                "source_backend": e.source_backend,
                "token_count": (e.extra or {}).get("token_count"),
                "order_index": e.order_index,
                "reading_order_position": (
                    pages_ro.index(e.id) if e.id in pages_ro else None),
                "reading_order_len": len(pages_ro),
            })
    return {"pages": pages, "recovered": recovered}


def run_arm(name: str, enabled: bool, docs: list[dict], record: list | None,
            timed: bool) -> dict:
    config = run_ab.configure(STRATEGY, DEVICE)
    config.ocr_backend = "__ab_tesseract"  # never a production name
    layout = LayoutFingerprint(
        DoclingBackend(device=DEVICE, ocr_languages=PipelineConfig().ocr_languages))
    ocr = CountingOCR(TesseractBackend(device=DEVICE, languages=config.ocr_languages))
    tables = TableTransformerBackend(device=DEVICE)
    key = (config.device, tuple(config.ocr_languages), config.ocr_backend)
    cli._COMPONENT_BACKEND_CACHE[key] = (layout, ocr, tables)

    install(enabled, record)
    out_root = HERE / "_runs" / "adaptive" / name
    rows, captures = [], {}
    print(f"\n=== {name} (L5 {'ON' if enabled else 'OFF'}) ===", flush=True)
    t_start = time.perf_counter()
    for entry in docs:
        ocr.current_doc = entry["document_id"]
        started = time.perf_counter()
        try:
            from doc_extraction.cli import process_file
            document = process_file(CORPUS / entry["filename"], config, output_root=out_root)
            text = document_text(document)
            n_tables = sum(len(getattr(p, "tables", []) or []) for p in document.pages)
            routes = sorted({p.source_route or "?" for p in document.pages})
            cap = capture(document)
            error = None
        except Exception as exc:  # noqa: BLE001 - a crash is a result
            text, n_tables, routes, error = "", 0, ["ERROR"], f"{type(exc).__name__}: {exc}"
            cap = {"pages": [], "recovered": []}
        elapsed = time.perf_counter() - started

        row = {"document_id": entry["document_id"], "language": entry["language"],
               "difficulty": entry["difficulty"], "pages": entry["page_count"],
               "labels": entry["hard_case_labels"], "routes": routes,
               "tables_found": n_tables,
               "tables_expected": entry.get("expected_tables", 0),
               "runtime_s": round(elapsed, 3), "error": error}
        row.update(run_ab.score(entry, text))
        row["tables_ok"] = row["tables_found"] >= row["tables_expected"]
        row["text_sha"] = hashlib.sha256(text.encode()).hexdigest()[:16]
        row["n_recovered_elements"] = len(cap["recovered"])
        rows.append(row)
        captures[entry["document_id"]] = cap
        flag = "!" if row["hallucinated"] else (" " if row["text_recall"] == 1.0 else ".")
        print(f"  {flag} {entry['document_id']:<32}{entry['language']}  "
              f"recall {row['text_recall']:.3f}  char {row['char_recall']:.3f}  "
              f"{elapsed:6.2f}s", flush=True)
    wall = time.perf_counter() - t_start
    restore()

    return {
        "rows": rows,
        "captures": captures,
        "timed": timed,
        "wall_s": round(wall, 1),
        "ocr_invocations": len(ocr.calls),
        "ocr_pages": len({(c["document_id"], c["page_index"]) for c in ocr.calls}),
        "ocr_documents": len({c["document_id"] for c in ocr.calls}),
        "ocr_seconds": round(sum(c["seconds"] for c in ocr.calls), 3),
        "ocr_calls": ocr.calls,
        "layout_calls": len(layout.prints),
        "layout_fingerprint": hashlib.sha256(
            "|".join(layout.prints).encode()).hexdigest()[:16],
        "layout_prints": layout.prints,
        "aggregate": run_ab.aggregate(rows),
    }


def main() -> int:
    manifest = json.loads((CORPUS / "manifest.json").read_text())
    docs = [d for d in manifest["documents_list"]
            if d["must_contain"] and (CORPUS / d["filename"]).exists()
            and d["filename"].lower().endswith(".pdf")]

    results = {
        "commit": run_ab.subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True,
            cwd=REPO).stdout.strip(),
        "strategy": STRATEGY, "device": DEVICE,
        "render_dpi": PipelineConfig().render_dpi,
        "ocr_languages": PipelineConfig().ocr_languages,
        "n_documents": len(docs),
        "n_pages": sum(d["page_count"] for d in docs),
        "cpu_state_start": run_ab.cpu_state(),
        "gpu_state_start": run_ab.gpu_state(),
        "arms": {},
    }

    # Phase 0 -- warmup so arm 1 does not pay model load arm 2 avoids.
    warm = next(d for d in docs if "scan" in d["document_id"])
    print(f"warmup: {warm['document_id']}", flush=True)
    run_arm("_warmup", True, [warm], None, timed=False)

    results["arms"]["baseline"] = run_arm("baseline", False, docs, None, timed=True)
    results["arms"]["l5"] = run_arm("l5", True, docs, None, timed=True)

    audit_record: list = []
    results["arms"]["l5_audit"] = run_arm("l5_audit", True, docs, audit_record, timed=False)
    results["audit_pages"] = audit_record

    results["cpu_state_end"] = run_ab.cpu_state()
    out = HERE / "line5_adaptive_ab.json"
    out.write_text(json.dumps(results, indent=1, ensure_ascii=False))
    print(f"\nwrote {out}")

    for name in ("baseline", "l5"):
        a = results["arms"][name]["aggregate"]
        d = results["arms"][name]
        print(f"{name:<10} recall {a['mean_text_recall']:.4f} char {a['mean_char_recall']:.4f} "
              f"perfect {a['docs_perfect']} order {a['docs_order_ok']} "
              f"tables {a['docs_tables_ok']} ocr_pages {d['ocr_pages']} "
              f"inv {d['ocr_invocations']} wall {d['wall_s']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
