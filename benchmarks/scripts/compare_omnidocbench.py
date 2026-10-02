"""Conservative compatibility check for OmniDocBench metric deltas."""

from __future__ import annotations

from typing import Any


def compare_metric(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    """Return a numeric delta only when the compared metric populations match.

    Each record must contain ``dataset_identity``, ordered ``sample_ids``,
    ``evaluator_commit``, ``metric``, ``aggregation``, ``value``, and
    ``evaluator_errors``. This deliberately rejects full-vs-subset comparisons.
    """
    reasons = []
    for field in ("dataset_identity", "sample_ids", "evaluator_commit", "metric", "aggregation"):
        if previous.get(field) != current.get(field):
            reasons.append(f"{field} differs")
    if previous.get("evaluator_errors") != 0 or current.get("evaluator_errors") != 0:
        reasons.append("one or both metric runs contain evaluator errors")
    for label, record in (("previous", previous), ("current", current)):
        if not isinstance(record.get("value"), (int, float)):
            reasons.append(f"{label} metric value is not numeric")
    comparable = not reasons
    return {
        "directly_comparable": comparable,
        "reasons": reasons,
        "previous": previous.get("value"),
        "current": current.get("value"),
        "absolute_delta": current["value"] - previous["value"] if comparable else None,
    }
