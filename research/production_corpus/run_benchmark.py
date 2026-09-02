#!/usr/bin/env python
"""Run the shipped pipeline over the production corpus and classify failures.

This is the measurement mission §5 asks for, and it deliberately does more
than score. A mean recall tells you how well the system did; it does not tell
you *what to build next*. Ranking work by evidence (§6) needs, for every
document that came out wrong, a named failure class and a severity — so the
output here is a failure table first and an aggregate second.

Two disciplines carried over from the earlier experiments:

* **Resource state is recorded per run.** A timing taken while another project
  is using this shared VM is not a benchmark. The classification is written
  into the results file so a reader can tell which numbers to trust.
* **Quality and timing are separated.** Experiment 006 showed CPU and GPU
  outputs are identical to 0.000 px, so recall is device-independent and stays
  valid under contention. Runtime does not.

    python research/production_corpus/run_benchmark.py --strategy adaptive
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

# NOTE: process_file and resolve_device live in cli.py rather than in a core
# module. Every entrypoint therefore imports the CLI to get the engine, which
# is the coupling mission §24 flags. Importing them here rather than
# reimplementing keeps this runner on the same engine as the CLI.
from doc_extraction.cli import process_file, resolve_device  # noqa: E402
from doc_extraction.config import PipelineConfig, load_config  # noqa: E402
from doc_extraction.utils import resources as res  # noqa: E402

# Severity is about consequence, not size of the diff. Silent garbage outranks
# a visible miss, because nothing downstream can detect it.
SEV_CRITICAL = "critical"
SEV_HIGH = "high"
SEV_MEDIUM = "medium"


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


def _routes(document) -> list[str]:
    out = []
    for page in document.pages:
        out.append(getattr(page, "source_route", None)
                   or getattr(page, "source_backend", None) or "?")
    return out


def classify_failure(entry: dict[str, Any], recall: float, hallucinated: list[str],
                     tables_ok: bool) -> list[tuple[str, str]]:
    """Map an observed failure onto the taxonomy.

    Returns (failure_type, severity) pairs. The document's declared
    `hard_case_labels` name the mechanisms present; the *observation* decides
    whether they actually broke anything. A document with labels that scored
    1.0 produces no rows — a mechanism being present is not a failure.
    """
    rows: list[tuple[str, str]] = []
    labels = entry["hard_case_labels"]

    if hallucinated:
        # The worst outcome in the whole taxonomy: confident, undetectable.
        rows.append(("encoding" if "encoding" in labels else "other", SEV_CRITICAL))

    if recall < 1.0:
        sev = (SEV_CRITICAL if recall == 0.0
               else SEV_HIGH if recall < 0.5 else SEV_MEDIUM)
        text_labels = [x for x in labels if x not in
                       ("table_detection", "table_structure", "merged_cells",
                        "borderless_table")]
        if text_labels:
            rows.extend((lbl, sev) for lbl in text_labels)
        elif labels:
            rows.extend((lbl, sev) for lbl in labels)
        else:
            # No declared mechanism, yet it failed. This is the most valuable
            # kind of row: an unmodelled production failure.
            rows.append(("other", sev))

    if not tables_ok:
        tbl_labels = [x for x in labels if x in
                      ("table_detection", "table_structure", "merged_cells",
                       "borderless_table")] or ["table_detection"]
        rows.extend((lbl, SEV_HIGH) for lbl in tbl_labels)

    # de-duplicate, keeping the highest severity seen per type
    order = {SEV_CRITICAL: 0, SEV_HIGH: 1, SEV_MEDIUM: 2}
    best: dict[str, str] = {}
    for t, s in rows:
        if t not in best or order[s] < order[best[t]]:
            best[t] = s
    return sorted(best.items(), key=lambda kv: order[kv[1]])


def configure(strategy: str, config_path: Path | None, device: str | None) -> PipelineConfig:
    config = load_config(config_path) if config_path else PipelineConfig()
    if device:
        config.device = device
    config = resolve_device(config)
    if strategy == "native":
        config.digital_pdf_page_fallback = False
        config.text_quality_max_suspicious_page_ratio = 1.01
        config.digital_pdf_page_ratio = 0.0
    elif strategy == "visual":
        config.digital_pdf_page_ratio = 1.01
    return config


def cpu_state() -> dict[str, Any]:
    load1, load5, load15 = os.getloadavg()
    n = os.cpu_count() or 1
    contended = load1 > n * 0.5
    return {"loadavg": [round(load1, 2), round(load5, 2), round(load15, 2)],
            "cpu_count": n,
            "classification": "CONTENDED" if contended else "CLEAN",
            "note": ("timings under contention are upper bounds, not benchmarks; "
                     "recall is device- and contention-independent")}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--strategy", default="adaptive",
                    choices=["adaptive", "native", "visual"])
    ap.add_argument("--corpus", default=str(Path(__file__).resolve().parent / "corpus"))
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent / "_runs"))
    ap.add_argument("--config", default=None)
    ap.add_argument("--device", default=None)
    ap.add_argument("--skip", default="", help="comma-separated document_ids to skip")
    ap.add_argument("--only-labels", default="",
                    help="comma-separated hard_case_labels; run only matching documents")
    args = ap.parse_args(argv)

    corpus = Path(args.corpus)
    manifest = json.loads((corpus / "manifest.json").read_text(encoding="utf-8"))
    docs = manifest["documents_list"]
    skip = {s for s in args.skip.split(",") if s}
    if skip:
        docs = [d for d in docs if d["document_id"] not in skip]
    if args.only_labels:
        want = {s for s in args.only_labels.split(",") if s}
        docs = [d for d in docs if want & set(d["hard_case_labels"])]

    config = configure(args.strategy, Path(args.config) if args.config else None, args.device)
    out_root = Path(args.out) / args.strategy
    out_root.mkdir(parents=True, exist_ok=True)

    gpu_before = res.query_gpu(samples=5)
    gpu_cls, gpu_why = res.classify_gpu(gpu_before)
    cpu_before = cpu_state()
    print(f"resource preflight: GPU {gpu_cls} ({gpu_why}) | CPU {cpu_before['classification']} "
          f"loadavg {cpu_before['loadavg'][0]}")
    print(f"device: {config.device}\n")

    rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    total_rt = 0.0

    for entry in docs:
        path = corpus / entry["filename"]
        started = time.perf_counter()
        error = None
        try:
            document = process_file(path, config, output_root=out_root)
            elapsed = time.perf_counter() - started
            text = document_text(document)
            routes = _routes(document)
            n_tables = sum(len(getattr(p, "tables", []) or []) for p in document.pages)
        except Exception as exc:  # noqa: BLE001 - a crash is a result, not an abort
            elapsed = time.perf_counter() - started
            error = f"{type(exc).__name__}: {exc}"
            text, routes, n_tables = "", ["ERROR"], 0

        required = entry["must_contain"] or []
        found = [s for s in required if _norm(s) in text]
        missing = [s for s in required if _norm(s) not in text]
        hallucinated = [s for s in entry.get("must_not_contain", []) if _norm(s) in text]
        recall = len(found) / (len(required) or 1)
        tables_ok = n_tables >= entry.get("expected_tables", 0)

        row = {
            "document_id": entry["document_id"],
            "format": entry["format"], "language": entry["language"],
            "document_type": entry["document_type"],
            "pages": entry["page_count"], "labels": entry["hard_case_labels"],
            "difficulty": entry["difficulty"],
            "routes": routes, "device": config.device,
            "text_recall": round(recall, 4),
            "found": len(found), "required": len(required), "missing": missing,
            "hallucinated": hallucinated,
            "tables_found": n_tables, "tables_expected": entry.get("expected_tables", 0),
            "tables_ok": tables_ok,
            "runtime_s": round(elapsed, 3),
            "chars": len(text),
            "error": error,
        }
        rows.append(row)
        total_rt += elapsed

        for ftype, sev in classify_failure(entry, recall, hallucinated, tables_ok):
            failures.append({
                "document_id": entry["document_id"],
                "pages": entry["page_count"],
                "failure_type": ftype,
                "severity": sev,
                "current_strategy": args.strategy,
                "route": routes[0] if routes else "?",
                "recovered": False,
                "text_recall": round(recall, 4),
                "hallucinated": bool(hallucinated),
                "runtime_s": round(elapsed, 3),
                "language": entry["language"],
                "format": entry["format"],
            })

        flag = "" if recall >= 1.0 and tables_ok and not hallucinated else "  <-- FAILURE"
        print(f"{entry['document_id']:32s} recall {recall:5.2f}  tables {n_tables}/"
              f"{entry.get('expected_tables',0)}  {elapsed:7.2f}s  {routes[0] if routes else '?':12s}{flag}")

    recalls = sorted(r["text_recall"] for r in rows)
    runtimes = sorted(r["runtime_s"] for r in rows)

    def pct(vals: list[float], p: float) -> float:
        if not vals:
            return 0.0
        return round(vals[min(len(vals) - 1, int(p * len(vals)))], 4)

    summary = {
        "documents": len(rows),
        "pages": sum(r["pages"] for r in rows),
        "mean_text_recall": round(sum(recalls) / len(recalls), 4) if recalls else 0.0,
        "p50_text_recall": pct(recalls, 0.50),
        "p10_text_recall": pct(recalls, 0.10),
        "worst_text_recall": recalls[0] if recalls else 0.0,
        "fully_recovered": sum(1 for r in rows if r["text_recall"] >= 1.0),
        "total_failures": sum(1 for r in rows if r["text_recall"] == 0.0),
        "hallucinations": sum(1 for r in rows if r["hallucinated"]),
        "errors": sum(1 for r in rows if r["error"]),
        "tables_ok": sum(1 for r in rows if r["tables_ok"]),
        "total_runtime_s": round(total_rt, 2),
        "runtime_p50_s": pct(runtimes, 0.50),
        "runtime_p90_s": pct(runtimes, 0.90),
        "runtime_p95_s": pct(runtimes, 0.95),
        "runtime_p99_s": pct(runtimes, 0.99),
        "runtime_max_s": runtimes[-1] if runtimes else 0.0,
        "runtime_mean_s": round(statistics.mean(runtimes), 3) if runtimes else 0.0,
    }

    by_type: dict[str, dict[str, Any]] = {}
    for f in failures:
        d = by_type.setdefault(f["failure_type"],
                               {"count": 0, "critical": 0, "high": 0, "medium": 0,
                                "documents": [], "runtime_s": 0.0})
        d["count"] += 1
        d[f["severity"]] += 1
        d["documents"].append(f["document_id"])
        d["runtime_s"] = round(d["runtime_s"] + f["runtime_s"], 2)

    import hashlib
    corpus_hash = hashlib.sha256(
        (corpus / "manifest.json").read_bytes()).hexdigest()
    payload = {
        "corpus": manifest["corpus"],
        "corpus_version": manifest["version"],
        # Ties a result to the exact corpus it was measured on. The manifest
        # carries a per-document sha256, so this one hash pins all 58.
        "corpus_manifest_sha256": corpus_hash,
        "documents_run": len(docs),
        "strategy": args.strategy,
        "device": config.device,
        "resource_state": {
            "gpu_preflight": {"classification": gpu_cls, "reason": gpu_why,
                              "util_samples": gpu_before.utilization_samples,
                              "used_mib": gpu_before.used_mib,
                              "free_mib": gpu_before.free_mib},
            "cpu_preflight": cpu_before,
            "cpu_postflight": cpu_state(),
        },
        "summary": summary,
        "failure_by_type": dict(sorted(by_type.items(),
                                       key=lambda kv: -kv[1]["count"])),
        "failures": failures,
        "documents": rows,
    }
    out_json = Path(args.out) / f"results_{args.strategy}.json"
    out_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")

    print(f"\nmean recall {summary['mean_text_recall']}  "
          f"fully recovered {summary['fully_recovered']}/{summary['documents']}  "
          f"failures {summary['total_failures']}  halluc {summary['hallucinations']}")
    print(f"runtime p50 {summary['runtime_p50_s']}s  p90 {summary['runtime_p90_s']}s  "
          f"p99 {summary['runtime_p99_s']}s  max {summary['runtime_max_s']}s")
    print("\nfailure classes by frequency:")
    for t, d in payload["failure_by_type"].items():
        print(f"  {t:20s} n={d['count']:3d}  crit={d['critical']} high={d['high']} "
              f"med={d['medium']}")
    print(f"\n-> {out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
