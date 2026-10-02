"""Strict manifest, result, and task-local metric utilities.

This module describes evaluation inputs and records results.  It does not
define a document interchange schema and does not make benchmark-specific
ground truth claims beyond what each manifest explicitly records.
"""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import yaml


class BenchmarkError(ValueError):
    """Malformed manifests or evaluation inputs fail loudly."""


Task = Literal[
    "physical_document_extraction",
    "semantic_document_extraction",
    "web_structured_extraction",
    "web_acquisition",
]


@dataclass(frozen=True)
class BenchmarkManifest:
    name: str
    version: str
    task: Task
    source_url: str | None
    license_note: str | None
    usage_notes: str
    download_mode: Literal["existing_local", "manual", "opt_in"]
    local_path_candidates: tuple[str, ...]
    expected_file_types: tuple[str, ...]
    ground_truth: str | None
    evaluation_adapter: str
    metrics: tuple[str, ...]
    subset: str
    checksum: str | None = None
    live_evaluation: bool = False


_REQUIRED = {
    "schema_version",
    "name",
    "version",
    "task",
    "source",
    "download",
    "local_path_candidates",
    "expected_file_types",
    "ground_truth",
    "evaluation",
    "subset",
}
_TASKS = {
    "physical_document_extraction",
    "semantic_document_extraction",
    "web_structured_extraction",
    "web_acquisition",
}


def load_manifest(path: Path) -> BenchmarkManifest:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise BenchmarkError(f"cannot read manifest: {path}") from exc
    if not isinstance(raw, dict) or set(raw) != _REQUIRED:
        raise BenchmarkError("manifest must contain exactly the benchmark-manifest/1 fields")
    if raw["schema_version"] != "benchmark-manifest/1":
        raise BenchmarkError("unsupported manifest schema_version")
    source, download, evaluation = raw["source"], raw["download"], raw["evaluation"]
    if not all(isinstance(value, dict) for value in (source, download, evaluation)):
        raise BenchmarkError("source, download, and evaluation must be mappings")
    if raw["task"] not in _TASKS:
        raise BenchmarkError("unsupported benchmark task")
    candidates = raw["local_path_candidates"]
    types = raw["expected_file_types"]
    metrics = evaluation.get("metrics")
    if (
        not isinstance(candidates, list)
        or not candidates
        or not all(isinstance(item, str) and not Path(item).is_absolute() for item in candidates)
        or not isinstance(types, list)
        or not all(isinstance(item, str) for item in types)
        or not isinstance(metrics, list)
        or not metrics
        or download.get("mode") not in {"existing_local", "manual", "opt_in"}
        or not isinstance(evaluation.get("adapter"), str)
    ):
        raise BenchmarkError("invalid manifest field types")
    return BenchmarkManifest(
        name=str(raw["name"]),
        version=str(raw["version"]),
        task=raw["task"],
        source_url=source.get("url"),
        license_note=source.get("license_note"),
        usage_notes=str(source.get("usage_notes", "")),
        download_mode=download["mode"],
        local_path_candidates=tuple(candidates),
        expected_file_types=tuple(types),
        ground_truth=raw["ground_truth"],
        evaluation_adapter=evaluation["adapter"],
        metrics=tuple(str(item) for item in metrics),
        subset=str(raw["subset"]),
        checksum=download.get("checksum"),
        live_evaluation=bool(download.get("live_evaluation", False)),
    )


def resolve_local_dataset(manifest: BenchmarkManifest, repository_root: Path) -> Path | None:
    """Return an existing declared dataset only; never download implicitly."""
    for relative in manifest.local_path_candidates:
        candidate = repository_root / relative
        if not candidate.is_dir():
            continue
        if manifest.ground_truth and not (candidate / manifest.ground_truth).is_file():
            continue
        return candidate
    return None


def deterministic_subset(sample_ids: list[str], count: int | None = None) -> list[str]:
    if any(not value for value in sample_ids) or len(set(sample_ids)) != len(sample_ids):
        raise BenchmarkError("sample identifiers must be non-empty and unique")
    ordered = sorted(sample_ids)
    if count is not None and not 0 <= count <= len(ordered):
        raise BenchmarkError("subset count is outside the available sample range")
    return ordered if count is None else ordered[:count]


@dataclass(frozen=True)
class FieldRecord:
    sample_id: str
    fields: dict[str, str | None]
    site: str | None = None
    vertical: str | None = None


@dataclass(frozen=True)
class FieldMetrics:
    precision: float
    recall: float
    f1: float
    true_positive: int
    false_positive: int
    false_negative: int


def _normalize(value: str | None) -> str | None:
    return None if value is None else " ".join(value.casefold().split())


def exact_field_metrics(truth: list[FieldRecord], predicted: list[FieldRecord]) -> dict[str, Any]:
    truth_by_id = {record.sample_id: record for record in truth}
    prediction_by_id = {record.sample_id: record for record in predicted}
    if len(truth_by_id) != len(truth) or len(prediction_by_id) != len(predicted):
        raise BenchmarkError("duplicate sample identifier")
    field_names = sorted({name for row in truth for name in row.fields})
    per_field: dict[str, FieldMetrics] = {}
    for field_name in field_names:
        tp = fp = fn = 0
        for sample_id, expected in truth_by_id.items():
            actual = prediction_by_id.get(sample_id)
            target = _normalize(expected.fields.get(field_name))
            value = _normalize(actual.fields.get(field_name) if actual else None)
            if target is None and value is None:
                continue
            if target is not None and target == value:
                tp += 1
            else:
                fp += value is not None
                fn += target is not None
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        per_field[field_name] = FieldMetrics(
            precision, recall, 2 * precision * recall / (precision + recall) if precision + recall else 0.0, tp, fp, fn
        )
    total_tp = sum(metric.true_positive for metric in per_field.values())
    total_fp = sum(metric.false_positive for metric in per_field.values())
    total_fn = sum(metric.false_negative for metric in per_field.values())
    micro_precision = total_tp / (total_tp + total_fp) if total_tp + total_fp else 0.0
    micro_recall = total_tp / (total_tp + total_fn) if total_tp + total_fn else 0.0
    micro_f1 = 2 * micro_precision * micro_recall / (micro_precision + micro_recall) if micro_precision + micro_recall else 0.0
    return {
        "sample_count": len(truth),
        "micro": asdict(FieldMetrics(micro_precision, micro_recall, micro_f1, total_tp, total_fp, total_fn)),
        "macro_f1": sum(metric.f1 for metric in per_field.values()) / len(per_field) if per_field else 0.0,
        "per_field": {name: asdict(metric) for name, metric in per_field.items()},
        "missing_prediction_samples": deterministic_subset(list(set(truth_by_id) - set(prediction_by_id))),
    }


def grouped_field_metrics(
    truth: list[FieldRecord], predicted: list[FieldRecord], group: Literal["site", "vertical"]
) -> dict[str, dict[str, Any]]:
    """Report web-template groups separately; never hide them in a global score."""
    groups = sorted({getattr(row, group) for row in truth if getattr(row, group)})
    results: dict[str, dict[str, Any]] = {}
    for value in groups:
        truth_group = [row for row in truth if getattr(row, group) == value]
        ids = {row.sample_id for row in truth_group}
        results[str(value)] = exact_field_metrics(
            truth_group, [row for row in predicted if row.sample_id in ids]
        )
    return results


@dataclass(frozen=True)
class BenchmarkResult:
    benchmark: dict[str, str]
    system: dict[str, Any]
    runtime: dict[str, Any]
    dataset: dict[str, Any]
    metrics: dict[str, Any]
    failures: list[dict[str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    schema_version: Literal["benchmark-result/1"] = "benchmark-result/1"

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"


def build_result(
    manifest: BenchmarkManifest,
    *,
    component: str,
    git_commit: str,
    config: dict[str, Any],
    sample_count: int,
    metrics: dict[str, Any],
    duration_seconds: float,
    model_versions: dict[str, str] | None = None,
    failures: list[dict[str, str]] | None = None,
    warnings: list[str] | None = None,
) -> BenchmarkResult:
    config_hash = hashlib.sha256(
        json.dumps(config, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return BenchmarkResult(
        benchmark={"name": manifest.name, "version": manifest.version, "subset": manifest.subset},
        system={"git_commit": git_commit, "component": component, "config_hash": config_hash, "model_versions": model_versions or {}},
        runtime={
            "device": "not_recorded",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": duration_seconds,
            "python": platform.python_version(),
        },
        dataset={"sample_count": sample_count},
        metrics=metrics,
        failures=failures or [],
        warnings=warnings or [],
    )


def write_result(path: Path, result: BenchmarkResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise BenchmarkError(f"refusing to overwrite benchmark result: {path}")
    path.write_text(result.canonical_json(), encoding="utf-8")


def current_git_commit(repository_root: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(repository_root), "rev-parse", "HEAD"], text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise BenchmarkError("cannot identify git commit") from exc
