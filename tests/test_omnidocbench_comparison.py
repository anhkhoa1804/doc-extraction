from __future__ import annotations

from benchmarks.scripts.compare_omnidocbench import compare_metric


def _record(*, sample_ids=None, errors=0):
    return {
        "dataset_identity": "dataset-hash",
        "sample_ids": sample_ids or ["p1", "p2"],
        "evaluator_commit": "evaluator-revision",
        "metric": "text_block.Edit_dist",
        "aggregation": "ALL_page_avg",
        "value": 0.5,
        "evaluator_errors": errors,
    }


def test_comparison_refuses_full_vs_subset_populations():
    result = compare_metric(_record(), _record(sample_ids=["p1"]))
    assert result["directly_comparable"] is False
    assert result["absolute_delta"] is None
    assert "sample_ids differs" in result["reasons"]


def test_comparison_refuses_evaluator_error_contaminated_metric():
    result = compare_metric(_record(errors=94), _record())
    assert result["directly_comparable"] is False
    assert result["absolute_delta"] is None


def test_comparison_returns_delta_only_for_identical_metric_protocol():
    previous = _record()
    current = _record()
    previous["value"] = 0.4
    current["value"] = 0.35
    result = compare_metric(previous, current)
    assert result["directly_comparable"] is True
    assert round(result["absolute_delta"], 2) == -0.05
