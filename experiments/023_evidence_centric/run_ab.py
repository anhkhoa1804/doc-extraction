"""Milestone A/B — does heterogeneous OCR evidence improve the extraction system?

Every condition runs through the *same* production `process_file`, so tables,
reading order, assembled IR and hallucination all come from the real
pipeline rather than a text-only side channel. Conditions C-F satisfy the
`OCRBackend` protocol and are injected into `cli._COMPONENT_BACKEND_CACHE`,
which is why no production code needed a research branch.

Conditions
----------
    A  easyocr          single source, the stronger of the two shipped paths
    B  tesseract        single source, genuinely independent (exp 021/022)
    C  selection        both, pick one page-wide by mean confidence
    U  union            both, naive concatenation (the crude control fusion
                        claims to beat -- exp 012 measured union > either)
    D  fusion           both, geometry- and conflict-aware evidence_fusion
    E  fusion_recovery  D + order_recovery's decision rule per region

Strategies
----------
    visual    force render+OCR on every page. Isolates the recognizer: this
              is where A-E can actually differ.
    adaptive  the shipped router. Most corpus PDFs have a usable text layer
              and never reach OCR at all, so this measures the *production*
              delta, which is the number that decides promotion -- and is
              expected to be far smaller than `visual`. Reporting only
              `visual` would overstate the production win; reporting only
              `adaptive` would hide the recognizer effect entirely.

Fairness
--------
No condition sees `must_contain`. Scoring happens strictly after extraction,
and the same rendered pixels at the same DPI feed every arm. `_norm` and
`document_text` are imported from the production corpus benchmark rather
than reimplemented, so these numbers are directly comparable to every other
result in this repository.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "research/production_corpus"))
sys.path.insert(0, str(Path(__file__).parent))

from doc_extraction import cli  # noqa: E402
from doc_extraction.backends.easyocr_backend import EasyOCRBackend  # noqa: E402
from doc_extraction.backends.tesseract_backend import TesseractBackend  # noqa: E402
from doc_extraction.config import PipelineConfig  # noqa: E402

from composite_backends import (  # noqa: E402
    FusionBackend,
    FusionRecoveryBackend,
    SelectionBackend,
    UnionBackend,
)
from run_benchmark import _norm, document_text  # noqa: E402

CORPUS = REPO / "research/production_corpus/corpus"
CONDITIONS = ("easyocr", "tesseract", "selection", "union", "fusion", "fusion_recovery")


def gpu_state() -> dict:
    """Recorded in every result file per the milestone's resource policy:
    a timing is meaningless without the contention it was measured under."""
    try:
        q = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total,utilization.gpu",
             "--format=csv,noheader,nounits"], capture_output=True, text=True, check=True)
        used, total, util = (x.strip() for x in q.stdout.strip().splitlines()[0].split(","))
        apps = subprocess.run(
            ["nvidia-smi", "--query-compute-apps=pid,used_memory", "--format=csv,noheader"],
            capture_output=True, text=True, check=True).stdout.strip()
        procs = [ln for ln in apps.splitlines() if ln.strip()]
        return {"memory_used_mib": int(used), "memory_total_mib": int(total),
                "utilization_pct": int(util), "compute_processes": len(procs),
                "process_rows": procs,
                "classification": "CLEAR" if not procs else "LIMITED_OR_PROTECTED"}
    except Exception as exc:  # noqa: BLE001 - provenance only
        return {"error": str(exc)}


def cpu_state() -> dict:
    load1, load5, load15 = os.getloadavg()
    n = os.cpu_count() or 1
    return {"loadavg": [round(load1, 2), round(load5, 2), round(load15, 2)],
            "cpu_count": n,
            "classification": "CONTENDED" if load1 > n * 0.5 else "CLEAN"}


class MemoizedLayout:
    """Caches layout results across conditions, keyed by image *content*.

    Layout runs on the rendered page before OCR and does not depend on which
    OCR backend follows it, so its result is identical in all six
    conditions -- and at ~17 s/page on a contended CPU it is ~70% of this
    experiment's total runtime. Keying on the file's sha256 rather than its
    path is what makes the cache hit at all: each condition renders into its
    own output directory, so the paths differ while the pixels do not.

    This changes runtime only. If it changed results, the layout backend
    would be non-deterministic, which would invalidate the whole A/B --
    `hits`/`misses` are reported so that assumption stays visible.
    """

    def __init__(self, inner) -> None:
        self.inner = inner
        self.name = inner.name
        self._cache: dict[str, object] = {}
        self.hits = 0
        self.misses = 0

    def is_available(self) -> bool:
        return self.inner.is_available()

    def analyze(self, page: PageInput):
        key = None
        if page.image_path is not None:
            try:
                key = hashlib.sha256(Path(page.image_path).read_bytes()).hexdigest()
            except OSError:
                key = None
        if key is not None and key in self._cache:
            self.hits += 1
            return self._cache[key]
        result = self.inner.analyze(page)
        self.misses += 1
        if key is not None:
            self._cache[key] = result
        return result


def build_ocr_backend(condition: str, device: str, langs: list[str]):
    if condition == "easyocr":
        return EasyOCRBackend(device=device, languages=langs)
    if condition == "tesseract":
        return TesseractBackend(device=device, languages=langs)
    easy = EasyOCRBackend(device=device, languages=langs)
    tess = TesseractBackend(device=device, languages=langs)
    return {"selection": SelectionBackend, "union": UnionBackend,
            "fusion": FusionBackend, "fusion_recovery": FusionRecoveryBackend}[condition](easy, tess)


def configure(strategy: str, device: str) -> PipelineConfig:
    """Mirrors `research/production_corpus/run_benchmark.configure` exactly,
    so a strategy means the same thing here as in the corpus benchmark."""
    config = PipelineConfig()
    config.device = device
    if strategy == "native":
        config.digital_pdf_page_fallback = False
        config.text_quality_max_suspicious_page_ratio = 1.01
        config.digital_pdf_page_ratio = 0.0
    elif strategy == "visual":
        config.digital_pdf_page_ratio = 1.01
    return config


def char_recall(needle: str, haystack: str) -> float:
    """Fraction of the required string's characters found, in order, in the
    extraction. Exact recall is all-or-nothing per string and hides the
    difference between "read with one wrong tone mark" and "not read at
    all" -- the exact distinction experiment 021 turned on."""
    if not needle:
        return 1.0
    sm = difflib.SequenceMatcher(None, needle, haystack, autojunk=False)
    return sum(b.size for b in sm.get_matching_blocks()) / len(needle)


def order_ok(found_positions: list[int]) -> bool:
    """Did the strings that were found appear in the manifest's own order?
    The manifest lists `must_contain` in document order, so an extraction
    that returns them out of sequence has a reading-order defect even at
    full recall -- invisible to a set-based recall metric."""
    return found_positions == sorted(found_positions)


def score(entry: dict, text: str) -> dict:
    required = entry["must_contain"] or []
    forbidden = entry.get("must_not_contain", []) or []

    positions, found, missing = [], [], []
    for s in required:
        idx = text.find(_norm(s))
        (found if idx >= 0 else missing).append(s)
        if idx >= 0:
            positions.append(idx)

    chars = [char_recall(_norm(s), text) for s in required] or [1.0]
    return {
        "text_recall": round(len(found) / (len(required) or 1), 4),
        "char_recall": round(sum(chars) / len(chars), 4),
        "found": len(found), "required": len(required), "missing": missing,
        "hallucinated": [s for s in forbidden if _norm(s) in text],
        "order_ok": order_ok(positions),
        "chars": len(text),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--conditions", nargs="*", default=list(CONDITIONS))
    ap.add_argument("--strategy", default="visual", choices=["visual", "adaptive", "native"])
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--limit", type=int, default=0, help="first N documents only (smoke)")
    ap.add_argument("--out", type=Path, default=Path(__file__).parent)
    args = ap.parse_args(argv)

    manifest = json.loads((CORPUS / "manifest.json").read_text())
    docs = [d for d in manifest["documents_list"]
            if d["must_contain"] and (CORPUS / d["filename"]).exists()
            and d["filename"].lower().endswith(".pdf")]
    if args.limit:
        docs = docs[:args.limit]

    results = {
        "commit": subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                                 text=True, cwd=REPO).stdout.strip(),
        "strategy": args.strategy, "device": args.device,
        "render_dpi": PipelineConfig().render_dpi,
        "n_documents": len(docs),
        "gpu_state_start": gpu_state(), "cpu_state_start": cpu_state(),
        "conditions": {},
    }
    print(f"corpus: {len(docs)} PDFs | strategy={args.strategy} | device={args.device}")
    print(f"GPU: {results['gpu_state_start'].get('classification')} "
          f"({results['gpu_state_start'].get('compute_processes')} compute proc)")

    # One layout backend, shared and memoized across every condition (see
    # MemoizedLayout): identical work, ~70% of the runtime.
    from doc_extraction.backends.docling_backend import DoclingBackend
    from doc_extraction.backends.table_backend import TableTransformerBackend
    shared_layout = MemoizedLayout(
        DoclingBackend(device=args.device, ocr_languages=PipelineConfig().ocr_languages))
    shared_tables = TableTransformerBackend(device=args.device)

    for condition in args.conditions:
        config = configure(args.strategy, args.device)
        config.ocr_backend = f"__ab_{condition}"  # never a production name
        backend = build_ocr_backend(condition, args.device, config.ocr_languages)

        # Inject so `_get_component_backends` finds a cache hit and never
        # calls `_build_ocr_backend` -- keeps research backends entirely out
        # of production selection logic.
        key = (config.device, tuple(config.ocr_languages), config.ocr_backend)
        cli._COMPONENT_BACKEND_CACHE[key] = (shared_layout, backend, shared_tables)

        out_root = args.out / "_runs" / args.strategy / condition
        rows, t_start = [], time.perf_counter()
        print(f"\n=== {condition} ===")
        for entry in docs:
            started = time.perf_counter()
            try:
                document = process_file_safe(entry, config, out_root)
                text = document_text(document)
                n_tables = sum(len(getattr(p, "tables", []) or []) for p in document.pages)
                routes = sorted({getattr(p, "route", "?") or "?" for p in document.pages})
                error = None
            except Exception as exc:  # noqa: BLE001 - a crash is a result
                text, n_tables, routes, error = "", 0, ["ERROR"], f"{type(exc).__name__}: {exc}"
            elapsed = time.perf_counter() - started

            row = {"document_id": entry["document_id"], "language": entry["language"],
                   "difficulty": entry["difficulty"], "pages": entry["page_count"],
                   "labels": entry["hard_case_labels"], "routes": routes,
                   "tables_found": n_tables,
                   "tables_expected": entry.get("expected_tables", 0),
                   "runtime_s": round(elapsed, 3), "error": error}
            row.update(score(entry, text))
            row["tables_ok"] = row["tables_found"] >= row["tables_expected"]
            rows.append(row)
            flag = "!" if row["hallucinated"] else (" " if row["text_recall"] == 1.0 else ".")
            print(f"  {flag} {entry['document_id']:<32}{entry['language']}  "
                  f"recall {row['text_recall']:.3f}  char {row['char_recall']:.3f}  "
                  f"{elapsed:6.2f}s", flush=True)

        stats = getattr(backend, "stats", [])
        results["conditions"][condition] = {
            "rows": rows,
            "wall_s": round(time.perf_counter() - t_start, 1),
            "ocr_invocations": sum(s.invocations for s in stats) if stats else None,
            "pages_ocred": len(stats) if stats else None,
            "easyocr_s": round(sum(s.easyocr_s for s in stats), 2) if stats else None,
            "tesseract_s": round(sum(s.tesseract_s for s in stats), 2) if stats else None,
            "page_stats": [s.__dict__ for s in stats] if stats else [],
            "aggregate": aggregate(rows),
        }
        print(f"  -> {summary_line(condition, results['conditions'][condition])}")

    results["gpu_state_end"] = gpu_state()
    results["cpu_state_end"] = cpu_state()
    results["layout_cache"] = {"hits": shared_layout.hits, "misses": shared_layout.misses,
                               "note": "layout is identical across conditions; cached by "
                                       "image content hash. Runtime effect only."}
    out = args.out / f"ab_{args.strategy}.json"
    out.write_text(json.dumps(results, indent=1, ensure_ascii=False))

    print("\n=== AGGREGATE ===")
    print(f"{'condition':<18}{'recall':>8}{'char':>8}{'halluc':>8}{'order':>7}"
          f"{'tables':>8}{'perfect':>9}{'zero':>6}{'wall_s':>9}")
    for c, data in results["conditions"].items():
        a = data["aggregate"]
        print(f"{c:<18}{a['mean_text_recall']:>8.4f}{a['mean_char_recall']:>8.4f}"
              f"{a['docs_hallucinated']:>8}{a['docs_order_ok']:>7}{a['docs_tables_ok']:>8}"
              f"{a['docs_perfect']:>9}{a['docs_zero']:>6}{data['wall_s']:>9.1f}")
    print(f"\nwrote {out}")
    return 0


def process_file_safe(entry: dict, config: PipelineConfig, out_root: Path):
    from doc_extraction.cli import process_file
    return process_file(CORPUS / entry["filename"], config, output_root=out_root)


def aggregate(rows: list[dict]) -> dict:
    n = len(rows) or 1
    return {
        "n": len(rows),
        "mean_text_recall": round(sum(r["text_recall"] for r in rows) / n, 4),
        "mean_char_recall": round(sum(r["char_recall"] for r in rows) / n, 4),
        "docs_perfect": sum(1 for r in rows if r["text_recall"] == 1.0),
        "docs_zero": sum(1 for r in rows if r["text_recall"] == 0.0),
        "docs_hallucinated": sum(1 for r in rows if r["hallucinated"]),
        "docs_order_ok": sum(1 for r in rows if r["order_ok"]),
        "docs_tables_ok": sum(1 for r in rows if r["tables_ok"]),
        "errors": sum(1 for r in rows if r["error"]),
        "total_runtime_s": round(sum(r["runtime_s"] for r in rows), 1),
        "by_language": by_language(rows),
    }


def by_language(rows: list[dict]) -> dict:
    out: dict[str, dict] = {}
    for lang in sorted({r["language"] for r in rows}):
        sub = [r for r in rows if r["language"] == lang]
        out[lang] = {"n": len(sub),
                     "mean_text_recall": round(sum(r["text_recall"] for r in sub) / len(sub), 4),
                     "mean_char_recall": round(sum(r["char_recall"] for r in sub) / len(sub), 4)}
    return out


def summary_line(condition: str, data: dict) -> str:
    a = data["aggregate"]
    return (f"{condition}: recall {a['mean_text_recall']:.4f} "
            f"char {a['mean_char_recall']:.4f} perfect {a['docs_perfect']}/{a['n']} "
            f"halluc {a['docs_hallucinated']} in {data['wall_s']}s")


if __name__ == "__main__":
    raise SystemExit(main())
