#!/usr/bin/env python
"""OmniDocBench experiment orchestrator: prepare (generate predictions) then
evaluate (invoke the official evaluator), then write a human-readable
report.md. Thin wrapper around prepare.py + evaluate.py — see those for the
independently-rerunnable steps this calls.

    python experiments/005_omnidocbench/run.py \\
        --dataset /path/to/OmniDocBench \\
        --backend baseline \\
        --output experiments/005_omnidocbench/results/baseline

    python experiments/005_omnidocbench/run.py \\
        --dataset /path/to/OmniDocBench \\
        --backend docling \\
        --output experiments/005_omnidocbench/results/docling

No path here is Kaggle-specific or otherwise hardcoded to one machine —
--dataset and --output are always explicit arguments. See
experiments/005_omnidocbench/kaggle/run_full_benchmark.ipynb for the same
commands wired to Kaggle's /kaggle/input and /kaggle/working paths.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT / "src"))
# Needed for `import evaluate` / `import prepare` below to find their
# sibling scripts. When run.py is executed directly (`python run.py`),
# Python already puts its own directory here automatically — this only
# matters when run.py is *imported* instead (e.g. by tests), where that
# auto-insertion doesn't happen. Doing it explicitly makes both paths work
# instead of one of them failing with a confusing ModuleNotFoundError.
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

import evaluate as evaluate_step  # noqa: E402
import prepare as prepare_step  # noqa: E402


_DEFAULTS_CONFIG_PATH = Path(__file__).resolve().parent / "config.yaml"


def _load_defaults(config_path: Path) -> dict[str, Any]:
    """Read experiments/005_omnidocbench/config.yaml, if present, to seed
    argparse defaults — so the common case is "edit the file once" rather
    than retyping flags every run, while every value stays a normal,
    Kaggle-friendly CLI override. Absence is not an error: a fresh clone
    without the file just gets the hardcoded fallbacks below."""
    if not config_path.exists():
        return {}
    import yaml

    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return {
        "config": raw.get("doc_extraction_config"),
        "omnidoc_repo": raw.get("omnidoc_repo"),
        "omnidoc_python": raw.get("omnidoc_python"),
        "match_method": raw.get("match_method"),
        "match_workers": raw.get("match_workers"),
        "include_cdm": raw.get("include_cdm"),
        "include_bleu_meteor": raw.get("include_bleu_meteor"),
    }


def build_parser(defaults: dict[str, Any] | None = None) -> argparse.ArgumentParser:
    d = {k: v for k, v in (defaults or {}).items() if v is not None}
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--backend", required=True, choices=["baseline", "docling"])
    parser.add_argument("--output", required=True)
    parser.add_argument("--config", default=d.get("config", str(REPO_ROOT / "configs" / "cpu.yaml")))
    parser.add_argument("--subset", type=int, default=None)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--omnidoc-repo", default=d.get("omnidoc_repo", str(REPO_ROOT / ".external" / "OmniDocBench")))
    parser.add_argument("--omnidoc-python", default=d.get("omnidoc_python", str(REPO_ROOT / ".venv-omnidoc" / "Scripts" / "python.exe")))
    parser.add_argument("--match-method", default=d.get("match_method", "quick_match"),
                         choices=["no_split", "simple_match", "quick_match"])
    parser.add_argument("--match-workers", type=int, default=d.get("match_workers", 4))
    parser.add_argument("--include-bleu-meteor", action="store_true", default=d.get("include_bleu_meteor", False))
    parser.add_argument("--include-cdm", action="store_true", default=d.get("include_cdm", False))
    parser.add_argument("--defaults-config", default=str(_DEFAULTS_CONFIG_PATH),
                         help="YAML file seeding these defaults (see experiments/005_omnidocbench/config.yaml).")
    parser.add_argument("--skip-prepare", action="store_true", help="Reuse existing predictions under <output>/predictions.")
    parser.add_argument("--skip-evaluate", action="store_true", help="Stop after generating predictions (e.g. to evaluate on another machine).")
    return parser


def _fmt(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def _headline_table(metrics: dict[str, Any]) -> list[str]:
    rows = ["| Category | Metric | Value |", "|---|---|---|"]
    for category in ("text_block", "display_formula", "table", "reading_order"):
        block = metrics.get(category)
        if not block or "all" not in block:
            continue
        for metric_name, values in block["all"].items():
            if isinstance(values, dict):
                for sub_name, sub_value in values.items():
                    rows.append(f"| {category} | {metric_name}.{sub_name} | {_fmt(sub_value)} |")
            else:
                rows.append(f"| {category} | {metric_name} | {_fmt(values)} |")
    return rows


def _group_breakdown_tables(metrics: dict[str, Any]) -> list[str]:
    """Attribute-level breakdown, straight from the evaluator's own `group`
    output — official OmniDocBench attribute labels (data_source,
    text_language, text_background, ...), never an invented category."""
    lines: list[str] = []
    for category in ("text_block", "display_formula", "table", "reading_order"):
        block = metrics.get(category)
        group = (block or {}).get("group")
        if not group:
            continue
        metric_keys = [k for k in group.keys() if k != "sample_count"]
        if not metric_keys:
            continue
        sample_counts = group.get("sample_count", {})
        attrs = sorted(group[metric_keys[0]].keys())
        lines.append(f"#### {category} — by attribute")
        lines.append("")
        header = "| attribute | " + " | ".join(metric_keys) + " | n |"
        lines.append(header)
        lines.append("|" + "---|" * (len(metric_keys) + 2))
        for attr in attrs:
            cells = [_fmt(group[m].get(attr)) for m in metric_keys]
            n = sample_counts.get(attr, "")
            lines.append(f"| {attr} | " + " | ".join(cells) + f" | {n} |")
        lines.append("")
    return lines


def write_report(output_root: Path, backend: str, dataset: str) -> Path:
    report_path = output_root / "report.md"
    metadata_path = output_root / "run_metadata.json"
    runtime_path = output_root / "runtime.json"
    metrics_path = output_root / "metrics.json"

    metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}
    runtime = json.loads(runtime_path.read_text(encoding="utf-8")) if runtime_path.exists() else {}

    lines = [f"# OmniDocBench report — {backend}", ""]
    lines.append(f"Dataset: `{dataset}`  ")
    lines.append(f"Backend: `{backend}`  ")
    if metadata:
        lines.append(f"Upstream evaluator commit: `{metadata.get('upstream_commit', '?')}`  ")
        lines.append(f"Device: `{metadata.get('device', '?')}`  ")
        lines.append(f"Samples evaluated: {metadata.get('num_samples', '?')} of {metadata.get('total_available_samples', '?')} available  ")
        if metadata.get("subset"):
            lines.append(f"Subset: {metadata['subset']} pages (seed={metadata.get('seed', 0)}) — **not the full benchmark**  ")
        lines.append(f"Timestamp: {metadata.get('timestamp', '?')}  ")
    lines.append("")

    lines.append("## Runtime")
    lines.append("")
    if runtime:
        lines.append(f"- Total: {runtime.get('total_runtime_seconds', '?')} s "
                      f"(wall clock: {runtime.get('wall_clock_seconds', '?')} s)")
        lines.append(f"- Pages: {runtime.get('succeeded', '?')} succeeded, {runtime.get('failed', '?')} failed, "
                      f"of {runtime.get('total_pages', '?')} total")
        lines.append(f"- Mean seconds/page: {runtime.get('mean_seconds_per_page', '?')}")
        lines.append(f"- Pages/second: {runtime.get('pages_per_second', '?')}")
        if runtime.get("routes"):
            lines.append(f"- Routes taken: {runtime['routes']}")
        if runtime.get("failures"):
            lines.append("")
            lines.append(f"**{len(runtime['failures'])} page(s) failed to produce a prediction:**")
            for fail in runtime["failures"][:20]:
                lines.append(f"  - {fail['image']}: {fail['error']}")
    else:
        lines.append("_No runtime.json found — prepare.py has not run._")
    lines.append("")

    lines.append("## End-to-end metrics")
    lines.append("")
    if metrics_path.exists():
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        lines.append(
            "No aggregate \"Overall\" score is reported: OmniDocBench's own Overall formula "
            "`((1 - TextEditDist) * 100 + TableTEDS + FormulaCDM) / 3` requires the formula CDM "
            "metric, which needs a Linux-only toolchain (TeX Live + ImageMagick 7.x + Ghostscript — "
            "stated by the upstream project itself, not assumed here) and was not run. Reporting the "
            "per-metric numbers the evaluator actually computed, not a substitute composite."
        )
        lines.append("")
        lines.extend(_headline_table(metrics))
        lines.append("")
        lines.append("### Attribute breakdown")
        lines.append("")
        lines.append("_Straight from the evaluator's own `group` output — official OmniDocBench "
                      "attribute labels, not a category we invented._")
        lines.append("")
        lines.extend(_group_breakdown_tables(metrics))
    else:
        lines.append("_No metrics.json found — evaluate.py has not run (or failed) for this backend._")
    lines.append("")

    lines.append("## Error summary")
    lines.append("")
    lines.append("Only evidence the pipeline/evaluator actually reported — no inferred causes.")
    lines.append("")
    if runtime.get("failures"):
        lines.append(f"- {len(runtime['failures'])} page(s) failed prediction generation (see Runtime above).")
    else:
        lines.append("- No prediction-generation failures.")
    lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def main(argv: list[str] | None = None) -> int:
    # Two-pass parse: find --defaults-config (if the caller overrode it)
    # before building the real parser, so its values can seed the other
    # flags' defaults.
    prelim = argparse.ArgumentParser(add_help=False)
    prelim.add_argument("--defaults-config", default=str(_DEFAULTS_CONFIG_PATH))
    known, _ = prelim.parse_known_args(argv)
    defaults = _load_defaults(Path(known.defaults_config))

    args = build_parser(defaults).parse_args(argv)
    output_root = Path(args.output).resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    if not args.skip_prepare:
        prepare_argv = [
            "--dataset", args.dataset, "--backend", args.backend, "--output", str(output_root),
            "--config", args.config,
        ]
        if args.subset is not None:
            prepare_argv += ["--subset", str(args.subset), "--seed", str(args.seed)]
        rc = prepare_step.main(prepare_argv)
        if rc != 0:
            print("prepare step failed; not evaluating", file=sys.stderr)
            return rc

    if not args.skip_evaluate:
        evaluate_argv = [
            "--dataset", args.dataset, "--output", str(output_root),
            "--omnidoc-repo", args.omnidoc_repo, "--omnidoc-python", args.omnidoc_python,
            "--match-method", args.match_method, "--match-workers", str(args.match_workers),
        ]
        if args.include_bleu_meteor:
            evaluate_argv.append("--include-bleu-meteor")
        if args.include_cdm:
            evaluate_argv.append("--include-cdm")
        rc = evaluate_step.main(evaluate_argv)
        if rc != 0:
            print("evaluate step failed", file=sys.stderr)
            # Still write a report from whatever prepare.py produced —
            # a partial result documented is better than nothing at all.
            write_report(output_root, args.backend, args.dataset)
            return rc

    report_path = write_report(output_root, args.backend, args.dataset)
    print(f"report -> {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
