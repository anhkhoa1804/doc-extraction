#!/usr/bin/env python
"""Aggregate per-stage timings from runs that already happened.

Why this reads logs instead of instrumenting the pipeline
---------------------------------------------------------
Every stage already writes a timed record to
``outputs/<document_id>/logs/pipeline.jsonl`` (see utils/logging.py). Adding
a second timing mechanism would mean two sources of truth that can disagree,
and would change the thing being measured. So this is a pure reader: it can
be pointed at any run, including ones finished weeks ago, and it never needs
the pipeline to be re-executed in a "profiling mode".

The cold/warm split
-------------------
This is the distinction that matters most here, and getting it wrong
misreports GPU speedups by roughly 6x on short runs.

Backends are cached per process (cli._COMPONENT_BACKEND_CACHE), and their
models load lazily on *first use*. So for a given (stage, backend) the first
observation in a process pays the model load and every later one does not.
Records are therefore ordered globally by timestamp and the first occurrence
of each (stage, backend) is reported as **cold**, the rest as **warm**.

Two consequences worth stating, because they bound what this tool can claim:

* Cold cost here is "first call including model load", not "model load"
  alone — the two differ by one inference, which is exactly the warm figure,
  so ``model_load ~= cold - warm`` is a derived estimate and is labelled as
  one rather than measured directly.
* If several runs are aggregated together, only the genuinely first call in
  each *process* is cold. Pass one run at a time when that distinction
  matters; ``--group-by-root`` keeps runs separate.

Usage
-----
    python scripts/profile_pipeline.py --input outputs/
    python scripts/profile_pipeline.py --input runA/ runB/ --group-by-root
    python scripts/profile_pipeline.py --input outputs/ --json profile.json
"""
from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any


def load_records(roots: list[Path]) -> list[dict[str, Any]]:
    """Every stage record under the given roots, ordered by timestamp.

    Ordering is what makes the cold/warm split meaningful, and timestamps are
    the only cross-document ordering available — the runner processes files
    sequentially, so wall-clock order is execution order.
    """
    records: list[dict[str, Any]] = []
    for root in roots:
        for path in sorted(root.rglob("logs/pipeline.jsonl")):
            for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    # A truncated final line is normal if a run was killed;
                    # skip it loudly rather than aborting the whole profile.
                    print(f"  ! skipping unparseable {path}:{line_no}")
                    continue
                record["_root"] = str(root)
                records.append(record)
    records.sort(key=lambda r: r.get("timestamp") or "")
    return records


def summarize(records: list[dict[str, Any]], group_by_root: bool = False) -> list[dict[str, Any]]:
    """One row per (stage, backend, device), with cold and warm separated."""
    buckets: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        if record.get("runtime_seconds") is None:
            continue
        key = (
            record.get("_root") if group_by_root else "",
            record.get("stage", "?"),
            record.get("backend", "?"),
            record.get("device") or "cpu",
        )
        buckets[key].append(record)

    total_runtime = sum(
        r["runtime_seconds"] for r in records if r.get("runtime_seconds") is not None
    )

    rows: list[dict[str, Any]] = []
    for (root, stage, backend, device), group in buckets.items():
        # Already globally time-ordered by load_records.
        times = [r["runtime_seconds"] for r in group]
        cold = times[0]
        warm = times[1:]
        failures = sum(1 for r in group if r.get("status") != "success")
        subtotal = sum(times)
        rows.append(
            {
                "root": root or None,
                "stage": stage,
                "backend": backend,
                "device": device,
                "calls": len(times),
                "failures": failures,
                "cold_s": round(cold, 4),
                "warm_mean_s": round(statistics.fmean(warm), 4) if warm else None,
                "warm_median_s": round(statistics.median(warm), 4) if warm else None,
                "warm_min_s": round(min(warm), 4) if warm else None,
                "warm_max_s": round(max(warm), 4) if warm else None,
                # Derived, not measured — see the module docstring. Only
                # meaningful when per-call cost is roughly homogeneous: the
                # estimate assumes the first call's excess over the others
                # *is* the model load. On a heterogeneous corpus (real
                # benchmark pages range over an order of magnitude) an easy
                # first page makes this negative, which is a signal that the
                # estimate does not apply — reported as None rather than
                # clamped to something that looks plausible.
                "implied_model_load_s": _implied_load(cold, warm),
                "load_estimate_unreliable": bool(warm)
                and (cold - statistics.fmean(warm)) < 0,
                "total_s": round(subtotal, 4),
                "share_of_logged_time": (
                    round(subtotal / total_runtime, 4) if total_runtime else None
                ),
            }
        )
    rows.sort(key=lambda r: r["total_s"], reverse=True)
    return rows


def _implied_load(cold: float, warm: list[float]) -> float | None:
    """Estimated model-load cost, or None when the estimate does not apply.

    A negative result means the first call was *faster* than the average of
    the rest, so the first call's cost cannot be attributed to model loading.
    That happens whenever per-call cost varies more than the load cost does —
    which is the normal case on a real, heterogeneous document corpus.
    """
    if not warm:
        return None
    implied = cold - statistics.fmean(warm)
    return round(implied, 4) if implied >= 0 else None


def render_table(rows: list[dict[str, Any]]) -> str:
    header = (
        f"{'stage':<15}{'backend':<22}{'dev':<6}{'n':>4}{'cold s':>10}"
        f"{'warm s':>10}{'warm med':>10}{'load s':>9}{'total s':>10}{'share':>8}"
    )
    lines = [header, "-" * len(header)]
    for r in rows:
        warm = f"{r['warm_mean_s']:.3f}" if r["warm_mean_s"] is not None else "-"
        med = f"{r['warm_median_s']:.3f}" if r["warm_median_s"] is not None else "-"
        load = f"{r['implied_model_load_s']:.2f}" if r["implied_model_load_s"] is not None else "-"
        share = f"{r['share_of_logged_time']:.1%}" if r["share_of_logged_time"] is not None else "-"
        lines.append(
            f"{r['stage']:<15}{r['backend']:<22}{r['device']:<6}{r['calls']:>4}"
            f"{r['cold_s']:>10.3f}{warm:>10}{med:>10}{load:>9}{r['total_s']:>10.2f}{share:>8}"
        )
    return "\n".join(lines)


def latency_model(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Split total logged time into one-off startup vs per-call steady state.

    This is the number to quote for throughput planning: a benchmark whose
    pages each pay a share of model load has a very different cost curve from
    one where load is amortized over thousands of pages.
    """
    one_off = 0.0
    steady = 0.0
    unreliable: list[str] = []
    for r in rows:
        if r["warm_mean_s"] is None:
            one_off += r["cold_s"]
            continue
        if r.get("load_estimate_unreliable"):
            # This stage's per-call cost varies too much to attribute any of
            # it to model load. Count it all as steady state and say so,
            # rather than reporting a load of zero as though it were measured.
            unreliable.append(f"{r['stage']}/{r['backend']}")
            steady += r["total_s"]
            continue
        implied_load = r["implied_model_load_s"] or 0.0
        one_off += implied_load
        steady += r["total_s"] - implied_load
    total = one_off + steady
    return {
        "one_off_model_load_s": round(one_off, 3),
        "steady_state_s": round(steady, 3),
        "total_logged_s": round(total, 3),
        "one_off_fraction": round(one_off / total, 4) if total else None,
        "load_not_separable_for": unreliable,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--input", nargs="+", required=True, help="Output root(s) containing <doc>/logs/pipeline.jsonl")
    parser.add_argument("--json", default=None, help="Write the full profile as JSON here.")
    parser.add_argument("--group-by-root", action="store_true",
                        help="Keep runs separate instead of pooling them (correct cold/warm per run).")
    args = parser.parse_args(argv)

    roots = [Path(p).resolve() for p in args.input]
    missing = [r for r in roots if not r.exists()]
    if missing:
        print(f"no such path: {missing}")
        return 1

    records = load_records(roots)
    if not records:
        print(f"no pipeline.jsonl records found under {[str(r) for r in roots]}")
        return 1

    rows = summarize(records, group_by_root=args.group_by_root)
    model = latency_model(rows)

    devices = sorted({r["device"] for r in rows})
    print(f"records: {len(records)}   stages: {len(rows)}   device(s): {', '.join(devices)}")
    print()
    print(render_table(rows))
    print()
    print("latency model")
    print(f"  one-off model load : {model['one_off_model_load_s']:>10.2f} s  "
          f"({model['one_off_fraction']:.1%} of logged time)" if model["one_off_fraction"] is not None
          else f"  one-off model load : {model['one_off_model_load_s']:.2f} s")
    print(f"  steady state       : {model['steady_state_s']:>10.2f} s")
    print(f"  total logged       : {model['total_logged_s']:>10.2f} s")
    if model.get("load_not_separable_for"):
        print()
        print("  NOTE: model load could NOT be separated for: "
              + ", ".join(model["load_not_separable_for"]))
        print("        The first call was faster than the mean of the rest, so per-page")
        print("        cost varies more than load cost does and the split does not apply.")
        print("        Their time is counted entirely as steady state.")
    print()
    print("note: 'load s' is cold minus mean warm — an estimate of model-load cost,")
    print("      not a directly measured quantity. Failures are counted but their")
    print("      runtimes are included, since a failure still consumed time.")

    if args.json:
        out = Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(
                {"roots": [str(r) for r in roots], "record_count": len(records),
                 "stages": rows, "latency_model": model},
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"\n-> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
