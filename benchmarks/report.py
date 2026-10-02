"""Small task-separated benchmark report renderer."""

from __future__ import annotations

import json
from pathlib import Path

from .registry import BenchmarkError


def render_report(paths: list[Path]) -> str:
    rows: list[tuple[str, str, int, str]] = []
    for path in sorted(paths):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise BenchmarkError(f"cannot read result: {path}") from exc
        if raw.get("schema_version") != "benchmark-result/1":
            raise BenchmarkError(f"invalid result schema: {path}")
        benchmark, system, dataset, metrics = (
            raw.get("benchmark"), raw.get("system"), raw.get("dataset"), raw.get("metrics")
        )
        if not all(isinstance(value, dict) for value in (benchmark, system, dataset, metrics)):
            raise BenchmarkError(f"invalid result fields: {path}")
        rows.append(
            (
                str(system.get("component", "unknown")),
                str(benchmark.get("name", "unknown")),
                int(dataset.get("sample_count", 0)),
                ", ".join(f"{key}={value}" for key, value in sorted(metrics.items())),
            )
        )
    header = ("COMPONENT", "BENCHMARK", "SIZE", "METRICS")
    widths = [
        max(len(row[index]) if isinstance(row[index], str) else len(str(row[index])) for row in [header, *rows])
        for index in range(4)
    ]
    def format_row(row: tuple[str, str, int, str] | tuple[str, str, str, str]) -> str:
        return "  ".join(str(value).ljust(widths[index]) for index, value in enumerate(row))
    return "\n".join([format_row(header), "  ".join("-" * width for width in widths), *[format_row(row) for row in rows]])
