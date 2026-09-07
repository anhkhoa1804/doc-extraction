"""SCAN-DOMINANT generalization -- does line 5's value scale with OCR exposure?

`line5_adaptive_ab.py` measured line 5 on the shipped router over the
production corpus and found +0.0068 exact recall -- with the router sending
only 6.25% of pages to OCR. This asks the distributional question: the same
49 documents, the same ground truth, the same scorer, the same UNMODIFIED
adaptive router, but delivered as scans, so the router itself chooses OCR on
essentially every page.

The cohort is frozen by `scan_cohort_build.py` before this runs and admits no
selection freedom -- see `scan_cohort_manifest.json` for the rule. Nothing
here is a `--strategy visual` override: the cohort documents have no text
layer, so `--strategy adaptive` routes them to `scanned_pdf` on its own.
This is the production path.

Everything else is `line5_adaptive_ab.py` unchanged: two arms differing only
in whether `base._orphan_tokens` returns its orphans or an empty list (which
is exactly pre-`1ae81e0` behaviour), scorer/`configure`/`aggregate` imported
from experiment 023's `run_ab`, layout deliberately not shared between arms
with a per-page region fingerprint recorded to prove it was identical anyway.
No production code is modified.

Phases: warmup (discarded), baseline (timed), l5 (timed), l5_audit (untimed,
full per-page orphan accounting and isolated L5 cost).

`_runs/` is excluded by `experiments/**/_runs/`. CPU only. Writes
`scan_cohort_ab.json` beside this file.

    python experiments/024_ocr_fidelity_recovery/scan_cohort_ab.py [--stratum SCAN-49|IMAGE-2]
"""
from __future__ import annotations

import argparse
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

COHORT_MANIFEST = HERE / "scan_cohort_manifest.json"
CORPUS = HERE / "_runs" / "scan_cohort_corpus"
STRATEGY = "adaptive"
DEVICE = "cpu"
STRATUM = "SCAN-49"

_REAL_ORPHAN_TOKENS = pbase._orphan_tokens
_REAL_MERGE = pbase.merge_regions_into_page
# Set by CountingOCR immediately before the merge that consumes its result, so
# an audit row names its own page instead of relying on call ordering.
_CURRENT: tuple[str | None, int] = (None, -1)


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
        global _CURRENT
        _CURRENT = (self.current_doc, page.page_index)
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
                "document_id": _CURRENT[0],
                "page_index": _CURRENT[1],
                "tokens_recognised": len(ocr_result.tokens),
                "regions": len(regions),
                "tables": len(tables),
                "unclaimed_by_region": len(unclaimed),
                "orphans": len(orphans),
                "table_excluded": len(unclaimed) - len(orphans),
                "blocks": len(blocks),
                "l5_isolated_s": round(l5_s, 6),
                # Full token text is not retained: at 112 OCR'd pages it would
                # make this artifact unreviewable, and every claim it supports
                # (recovery rate, duplication, table exclusion) is a count. The
                # recovered text itself is kept per element in `captures`.
                "orphan_chars": sum(len(t.text or "") for t in orphans),
                "claimed_by_region": len(ocr_result.tokens) - len(unclaimed),
                "orphan_also_claimed": sum(
                    1 for t in orphans
                    if any(pbase._center_in(t.bbox, r.bbox) for r in regions)
                ),
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
    out_root = HERE / "_runs" / "scan_cohort" / STRATUM / name
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
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stratum", default="SCAN-49", choices=["SCAN-49", "IMAGE-2"])
    args = ap.parse_args()
    global STRATUM
    STRATUM = args.stratum

    cohort = json.loads(COHORT_MANIFEST.read_text())
    docs = [d for d in cohort["documents_list"]
            if d["stratum"] == STRATUM and (CORPUS / d["filename"]).exists()]
    for d in docs:  # the frozen cohort is the contract; verify it byte-for-byte
        got = hashlib.sha256((CORPUS / d["filename"]).read_bytes()).hexdigest()
        assert got == d["sha256"], f"cohort drift: {d['document_id']}"
    print(f"cohort {STRATUM}: {len(docs)} documents, "
          f"{sum(d['cohort_pages'] for d in docs)} pages, "
          f"{sum(d['cohort_image_only_pages'] for d in docs)} image-only")

    results = {
        "commit": run_ab.subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True,
            cwd=REPO).stdout.strip(),
        "strategy": STRATEGY, "device": DEVICE, "stratum": STRATUM,
        "cohort_rule": cohort["selection_rule"],
        "cohort_manifest": str(COHORT_MANIFEST.relative_to(REPO)),
        "render_dpi": PipelineConfig().render_dpi,
        "ocr_languages": PipelineConfig().ocr_languages,
        "n_documents": len(docs),
        "n_pages": sum(d["cohort_pages"] for d in docs),
        "n_image_only_pages": sum(d["cohort_image_only_pages"] for d in docs),
        "cpu_state_start": run_ab.cpu_state(),
        "gpu_state_start": run_ab.gpu_state(),
        "arms": {},
    }

    # Phase 0 -- warmup so arm 1 does not pay model load arm 2 avoids.
    warm = docs[0]
    print(f"warmup: {warm['document_id']}", flush=True)
    run_arm("_warmup", True, [warm], None, timed=False)

    results["arms"]["baseline"] = run_arm("baseline", False, docs, None, timed=True)
    results["arms"]["l5"] = run_arm("l5", True, docs, None, timed=True)

    audit_record: list = []
    results["arms"]["l5_audit"] = run_arm("l5_audit", True, docs, audit_record, timed=False)
    results["audit_pages"] = audit_record

    results["cpu_state_end"] = run_ab.cpu_state()
    out = HERE / f"scan_cohort_ab{'' if STRATUM == 'SCAN-49' else '_image2'}.json"
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
