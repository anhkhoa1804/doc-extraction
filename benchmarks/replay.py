"""Strict, local-only replay benchmark manifest validation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .registry import BenchmarkError, deterministic_subset


@dataclass(frozen=True)
class ReplayCase:
    case_id: str
    seeds: tuple[str, ...]
    routes: tuple[dict[str, object], ...]
    expected_acquired: tuple[str, ...]


def load_replay_cases(path: Path) -> list[ReplayCase]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BenchmarkError("cannot read replay corpus") from exc
    if raw.get("schema_version") != "web-acquisition-replay/1" or not isinstance(raw.get("cases"), list):
        raise BenchmarkError("invalid replay corpus schema")
    result: list[ReplayCase] = []
    for item in raw["cases"]:
        if not isinstance(item, dict):
            raise BenchmarkError("invalid replay case")
        required = {"case_id", "seeds", "routes", "expected_acquired"}
        if set(item) != required or not all(isinstance(item[key], list) for key in required - {"case_id"}):
            raise BenchmarkError("invalid replay case fields")
        result.append(
            ReplayCase(
                str(item["case_id"]), tuple(str(value) for value in item["seeds"]),
                tuple(item["routes"]), tuple(str(value) for value in item["expected_acquired"]),
            )
        )
    deterministic_subset([case.case_id for case in result])
    return result
