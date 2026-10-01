"""Functional discrimination checks used by the bounded Gate 1 analysis."""
from doc_extraction.evaluation.evidence_integrity import classify_loss_boundary


def test_gate1_fault_taxonomy_is_functionally_discriminant():
    cases = {
        "acquisition": {"acquisition_present": False, "canonical_exact_present": False, "canonical_normalized_present": False, "serialized_present": False, "ownership_conflict": False},
        "ownership": {"acquisition_present": True, "canonical_exact_present": False, "canonical_normalized_present": False, "serialized_present": False, "ownership_conflict": True},
        "reconciliation": {"acquisition_present": True, "canonical_exact_present": False, "canonical_normalized_present": False, "serialized_present": False, "ownership_conflict": False, "reconciliation_missing": True},
        "canonical_projection": {"acquisition_present": True, "canonical_exact_present": False, "canonical_normalized_present": False, "serialized_present": False, "ownership_conflict": False},
        "serialization": {"acquisition_present": True, "canonical_exact_present": True, "canonical_normalized_present": True, "serialized_present": False, "ownership_conflict": False},
        "normalization": {"acquisition_present": True, "canonical_exact_present": False, "canonical_normalized_present": True, "serialized_present": True, "ownership_conflict": False},
    }
    assert {expected: classify_loss_boundary(**state).value for expected, state in cases.items()} == {expected: expected for expected in cases}
