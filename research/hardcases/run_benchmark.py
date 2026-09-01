#!/usr/bin/env python
"""Score extraction strategies against the enterprise-hardcases corpus.

What this measures, and why it is shaped this way
-------------------------------------------------
The question a production system needs answered is not "what is the edit
distance" but:

    did the information survive, and what did it cost?

So each case declares a handful of short, distinctive strings that MUST appear
in the extraction (`must_contain`) and, where hallucination or duplication is
the risk, strings that must NOT (`must_not_contain`). Recall over those strings
is a blunt instrument, deliberately: it is unambiguous, needs no annotator, and
answers the production question directly. An edit-distance score of 0.55 does
not tell you whether the company registration number survived; this does.

Strategies compared
-------------------
* ``native``   — force the native/digital path, never render or OCR.
* ``visual``   — force the whole-page render + layout + OCR path.
* ``adaptive`` — the repository's current router, which chooses per document
                 and can fall back per page.

Comparing these three on identical inputs is the point: it isolates how much
the *routing decision* is worth, separately from how good any one backend is.

    python research/hardcases/run_benchmark.py --strategy adaptive
    python research/hardcases/run_benchmark.py --strategy native visual adaptive
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from doc_extraction.cli import process_file, resolve_device  # noqa: E402
from doc_extraction.config import load_config  # noqa: E402
from doc_extraction.utils.resources import query_gpu  # noqa: E402

STRATEGIES = ("native", "visual", "adaptive")


def _normalize(text: str) -> str:
    """Compare on NFC-normalized text.

    Vietnamese is the reason this exists: `ệ` can be represented as one
    codepoint or as `e` plus two combining marks, and an OCR engine may emit
    either. Treating those as different strings would score a correct
    extraction as a failure.
    """
    return unicodedata.normalize("NFC", text)


def document_text(document) -> str:
    """All recoverable text, including table cell contents.

    Table text lives in `Page.tables`, not in element `.text` — omitting it
    would score a perfectly extracted spreadsheet as having found nothing.
    """
    parts: list[str] = []
    for page in document.pages:
        for element in page.elements:
            if element.text:
                parts.append(element.text)
        for table in page.tables:
            for row in table.to_grid():
                parts.extend(cell for cell in row if cell)
    return _normalize("\n".join(parts))


def score_case(case: dict[str, Any], document, runtime_s: float) -> dict[str, Any]:
    text = document_text(document)
    found = [s for s in case["must_contain"] if _normalize(s) in text]
    missing = [s for s in case["must_contain"] if _normalize(s) not in text]
    forbidden_present = [s for s in case.get("must_not_contain", []) if _normalize(s) in text]

    n_required = len(case["must_contain"]) or 1
    recall = len(found) / n_required
    n_tables = sum(len(p.tables) for p in document.pages)

    return {
        "case_id": case["case_id"],
        "failure_mode": case["failure_mode"],
        "language": case["language"],
        "difficulty": case["difficulty"],
        "route": document.metadata.route,
        "device": document.metadata.device,
        "text_recall": round(recall, 4),
        "found": len(found),
        "required": len(case["must_contain"]),
        "missing": missing,
        "hallucinated": forbidden_present,
        "clean": not forbidden_present,
        "tables_found": n_tables,
        "tables_expected": case.get("expected_tables", 0),
        "tables_ok": n_tables >= case.get("expected_tables", 0),
        "runtime_s": round(runtime_s, 3),
        "chars_extracted": len(text),
    }


def run_strategy(strategy: str, corpus: Path, out_root: Path, config_path: Path,
                 device: str | None) -> dict[str, Any]:
    manifest = json.loads((corpus / "manifest.json").read_text(encoding="utf-8"))

    config = load_config(config_path)
    if device:
        config.device = device
    config = resolve_device(config)

    # The strategies differ only in how the router is constrained, so that any
    # difference in the results is attributable to routing rather than to a
    # different backend or config.
    if strategy == "native":
        # Never leave the text layer: disable the per-page visual fallback and
        # make the quality gate unable to reroute the document.
        config.digital_pdf_page_fallback = False
        config.text_quality_max_suspicious_page_ratio = 1.01
        config.digital_pdf_page_ratio = 0.0
    elif strategy == "visual":
        # Force every page down the render+OCR path regardless of text quality.
        config.digital_pdf_page_ratio = 1.01
    # "adaptive" leaves the shipped configuration untouched.

    results: list[dict[str, Any]] = []
    total_runtime = 0.0
    for case in manifest["cases"]:
        path = corpus / case["filename"]
        started = time.perf_counter()
        try:
            document = process_file(path, config, output_root=out_root / strategy)
            elapsed = time.perf_counter() - started
            row = score_case(case, document, elapsed)
        except Exception as exc:  # noqa: BLE001 - a crash is a result, not an abort
            elapsed = time.perf_counter() - started
            row = {
                "case_id": case["case_id"], "failure_mode": case["failure_mode"],
                "language": case["language"], "difficulty": case["difficulty"],
                "route": "ERROR", "device": config.device,
                "text_recall": 0.0, "found": 0, "required": len(case["must_contain"]),
                "missing": case["must_contain"], "hallucinated": [], "clean": True,
                "tables_found": 0, "tables_expected": case.get("expected_tables", 0),
                "tables_ok": False, "runtime_s": round(elapsed, 3), "chars_extracted": 0,
                "error": f"{type(exc).__name__}: {exc}",
            }
        total_runtime += elapsed
        results.append(row)

    recalls = [r["text_recall"] for r in results]
    recalls_sorted = sorted(recalls)
    n = len(recalls_sorted)

    def pct(p: float) -> float:
        # Tail quality is the production concern; the mean hides it.
        return round(recalls_sorted[min(n - 1, int(p * n))], 4) if n else 0.0

    return {
        "strategy": strategy,
        "device": config.device,
        "cases": len(results),
        "mean_text_recall": round(sum(recalls) / n, 4) if n else 0.0,
        "p50_text_recall": pct(0.50),
        "p10_text_recall": pct(0.10),
        "worst_text_recall": round(recalls_sorted[0], 4) if n else 0.0,
        "fully_recovered": sum(1 for r in results if r["text_recall"] >= 1.0),
        "total_failures": sum(1 for r in results if r["text_recall"] == 0.0),
        "hallucinations": sum(1 for r in results if not r["clean"]),
        "tables_ok": sum(1 for r in results if r["tables_ok"]),
        "errors": sum(1 for r in results if r.get("error")),
        "total_runtime_s": round(total_runtime, 2),
        "recall_per_second": round((sum(recalls)) / total_runtime, 4) if total_runtime else 0.0,
        "results": results,
    }


def render(summaries: list[dict[str, Any]]) -> str:
    lines = []
    hdr = (f"{'case':24s}{'mode':14s}" +
           "".join(f"{s['strategy'][:9]:>11s}" for s in summaries))
    lines.append(hdr)
    lines.append("-" * len(hdr))
    by_case: dict[str, list[dict]] = {}
    for s in summaries:
        for r in s["results"]:
            by_case.setdefault(r["case_id"], []).append(r)
    for case_id, rows in by_case.items():
        cells = ""
        for r in rows:
            mark = "!" if not r["clean"] else ("E" if r.get("error") else " ")
            cells += f"{r['text_recall']:>10.0%}{mark}"
        lines.append(f"{case_id:24s}{rows[0]['failure_mode']:14s}{cells}")
    lines.append("-" * len(hdr))
    for label, key, fmt in (("mean recall", "mean_text_recall", "{:>10.0%} "),
                            ("worst case", "worst_text_recall", "{:>10.0%} "),
                            ("full recovery", "fully_recovered", "{:>10d} "),
                            ("total failures", "total_failures", "{:>10d} "),
                            ("runtime (s)", "total_runtime_s", "{:>10.1f} ")):
        lines.append(f"{label:38s}" + "".join(fmt.format(s[key]) for s in summaries))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--corpus", default=str(Path(__file__).parent / "corpus"))
    parser.add_argument("--strategy", nargs="+", default=["adaptive"], choices=STRATEGIES)
    parser.add_argument("--config", default=str(REPO_ROOT / "configs" / "cpu.yaml"))
    parser.add_argument("--device", default=None, choices=["cpu", "cuda", "auto"])
    parser.add_argument("--out", default=None, help="Working dir for per-run artifacts.")
    parser.add_argument("--json", default=None, help="Write full results here.")
    args = parser.parse_args(argv)

    corpus = Path(args.corpus).resolve()
    if not (corpus / "manifest.json").exists():
        print(f"no corpus at {corpus} — run research/hardcases/generate.py first")
        return 1
    out_root = Path(args.out).resolve() if args.out else corpus.parent / "_runs"

    gpu = query_gpu()
    contention = {
        "gpu_free_mib": gpu.free_mib, "gpu_utilization_pct": gpu.utilization_pct,
        "gpu_compute_apps": [{"pid": p.pid, "used_mib": p.used_mib} for p in gpu.processes],
        "loadavg": Path("/proc/loadavg").read_text().split()[:3]
        if Path("/proc/loadavg").exists() else None,
    }

    summaries = [run_strategy(s, corpus, out_root, Path(args.config), args.device)
                 for s in args.strategy]

    print(render(summaries))
    print()
    for s in summaries:
        print(f"{s['strategy']:>9s}: recall/s={s['recall_per_second']:.3f}  "
              f"p10={s['p10_text_recall']:.0%}  hallucinations={s['hallucinations']}  "
              f"tables_ok={s['tables_ok']}  errors={s['errors']}  device={s['device']}")

    if args.json:
        payload = {"corpus": str(corpus.relative_to(REPO_ROOT)),
                   "contention": contention, "summaries": summaries}
        Path(args.json).write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                                   encoding="utf-8")
        print(f"\n-> {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
