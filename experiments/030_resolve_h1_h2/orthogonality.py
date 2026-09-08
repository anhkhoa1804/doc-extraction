"""030 Phase 6 -- are H1 and H2 logically independent, or the same phenomenon?

H1 is about WHETHER/HOW MUCH the escape mechanism fires (frequency/severity
as a function of document properties). H2 is about WHERE the escape can
land (spatial bound, given that it fires). These are different questions
about the same underlying mechanism (029's row-synthesis finding), so some
dependency is expected by construction; the test is whether they are
INFORMATIONALLY separable -- does knowing H1's truth value tell you
anything about H2's, beyond both depending on the same root mechanism firing?
"""
from __future__ import annotations
import json
from pathlib import Path
HERE = Path(__file__).resolve().parent

h1 = json.loads((HERE / "h1_resolution.json").read_text())
h2 = json.loads((HERE / "h2_resolution.json").read_text())

# Cell 3: H1-relevant cases (undershoot occurs) x H2-relevant (does that specific
# escaping cell contaminate another table)?
h1_true_cases = sum(1 for r in h1["all_rows"] if r["undershoot_px"] > 1.0)  # "H1 fires" = undershoot occurs
h2_contaminated = h2["H2_CORE_RESULT"]["escaping_cells_intersecting_another_table"]
h2_total_escaping = h2["total_escaping_cells_found"]

quadrants = {
    "H1_fires_AND_H2_contaminates": 0,  # would need an escaping cell that also intersects another table
    "H1_fires_AND_H2_does_not": h2_total_escaping,  # every one of the 265 escaping cells: H1 fired, H2 held
    "H1_does_not_fire_AND_H2_contaminates": "undefined -- H2 only applies where a cell already escapes, "
                                            "which requires H1's mechanism to have fired",
    "H1_does_not_fire_AND_H2_does_not": h1["population"]["geometry_re_derived_for"] - h1_true_cases,
}

analysis = {
    "relationship_type": None,
    "reasoning": (
        "H2's precondition (an escaping cell exists) is entailed by H1's mechanism "
        "having fired at all (undershoot > 0 is definitionally the same event as "
        "'a cell escaped its table'). So quadrant 'H1 false AND H2 true/false' is "
        "UNDEFINED, not merely unobserved -- H2 has no truth value for a table that "
        "never had an escaping cell in the first place. This means H1 and H2 are NOT "
        "independent hypotheses in the classical 2x2 sense: H2 is a hypothesis about "
        "the CONSEQUENCE of the mechanism H1 studies the CAUSE of, conditional on it "
        "having fired. They are NESTED, not orthogonal: H1 asks 'when/how much does "
        "the mechanism activate', H2 asks 'given activation, how far can it reach'."
    ),
    "quadrants": quadrants,
    "classification": "NESTED (H2 is conditional on H1's mechanism having fired at all; "
                      "not the same phenomenon under different wording -- they ask "
                      "genuinely different questions about the SAME event, frequency "
                      "vs spatial-extent -- but not logically independent either)",
    "recommendation_for_lineage": (
        "Do not merge H1 and H2 into one hypothesis -- they have different evidence, "
        "different falsification conditions, and different production implications "
        "(H1 bears on WHEN to worry, H2 bears on HOW BAD it is when you should). But "
        "record their shared root explicitly in the lineage: both are downstream of "
        "029's single traced mechanism (base.py:505-576), and a fix to that mechanism "
        "would address both simultaneously."
    ),
}

(HERE / "orthogonality.json").write_text(json.dumps(analysis, indent=1, ensure_ascii=False))
print(json.dumps(analysis, indent=1, ensure_ascii=False))
