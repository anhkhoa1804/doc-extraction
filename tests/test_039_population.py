import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT = ROOT / "experiments/039_larger_real_corpus"


def test_039_acquisition_checkpoint_is_complete_and_audited():
    manifest = json.loads((EXPERIMENT / "population_manifest.json").read_text())
    audit = json.loads((EXPERIMENT / "population_audit.json").read_text())
    assert len(manifest["records"]) == 269
    assert manifest["split_algorithm"] == {
        "group_key": "039-group-v1:<doc_category>::<collection>::<doc_name>",
        "within_category": True,
        "development_rule": "first ceil(n/2) hash-ranked groups per category",
        "development_groups": 17,
        "held_out_groups": 16,
    }
    assert audit["status"] == "population_audited"
    assert audit["population"]["table_pages"] == 174
    assert audit["population"]["control_pages"] == 95
    assert audit["integrity"]["errors"] == []
    assert all(not values for values in audit["integrity"]["identity_overlaps"].values())


def test_039_adequacy_gate_is_frozen_before_baseline():
    protocol = (EXPERIMENT / "CORPUS_PROTOCOL.md").read_text()
    preregistration = (EXPERIMENT / "PREREGISTRATION.md").read_text()
    for phrase in (
        "at least 12 strict-D2 GT-table cases",
        "at least 6 distinct source-document groups",
        "at least 3 distinct raw region labels",
        "at least 4 DocLayNet document categories",
        "more than half of development",
    ):
        assert phrase in protocol
    assert "**Status:** frozen before 039 baseline extraction" in preregistration
    assert "forced-crop detector or structure outcome" in preregistration
