"""031 Phase 9 -- intervention candidates, evaluated on paper before implementation."""
from __future__ import annotations
import json
from pathlib import Path
HERE = Path(__file__).resolve().parent

CANDIDATES = [
    {"id": "A", "name": "Label relaxation",
     "description": "certain picture-labelled table-shaped regions become table "
                    "candidates outright (change the label)",
     "recall_gain": "HIGH -- would recover every CONFIRMED candidate",
     "false_positive_exposure": "HIGH -- relabels based on a geometric heuristic with "
                                "NO validation against genuine non-table pictures with "
                                "similar child count (Phase 6 found none exist in this "
                                "corpus to test against)",
     "compute_cost": "same as normal table processing for relabelled regions only",
     "implementation_complexity": "LOW",
     "new_failure_modes": "a genuinely non-table picture wrongly relabelled would "
                          "permanently lose its IMAGE element identity",
     "provenance_implications": "the region's ORIGINAL label (Docling's own "
                                "classification) is destroyed, not merely overridden "
                                "-- no record that this was a picture originally",
     "interaction_with_adaptive_routing": "route-independent once applied"},
    {"id": "B", "name": "Secondary table gate",
     "description": "keep primary label unchanged; run a cheap STRUCTURAL test "
                    "(the table_shape_probe) on picture-labelled regions; only "
                    "SUSPICIOUS ones (score >= threshold) get a table candidate "
                    "built ALONGSIDE the original picture element, not replacing it",
     "recall_gain": "HIGH on CONFIRMED candidates (probe: 100% LDO recovery at "
                    "threshold=3, Phase 5) -- but this figure is from only 4 "
                    "positive documents",
     "false_positive_exposure": "LOWER than A -- gated by the probe, and the probe's "
                                "only tested negative population (1-2-child stamp "
                                "fragments) scores 0-1, well under threshold=3",
     "compute_cost": "near-zero -- probe uses only fields already in the layout JSON, "
                     "no new model call",
     "implementation_complexity": "LOW-MEDIUM (probe + reconstruction logic)",
     "new_failure_modes": "reconstructed cells could duplicate the original picture "
                          "element's gathered text if not mutually exclusive by "
                          "construction (same duplication risk 025 found for "
                          "picture-labelled table-shaped regions)",
     "provenance_implications": "GOOD -- original label preserved; a new Table object "
                                "carries its own source_backend marker distinguishing "
                                "it as probe-recovered, not detector-original",
     "interaction_with_adaptive_routing": "orthogonal -- operates after layout, "
                                          "before/independent of route selection"},
    {"id": "C", "name": "Fallback table recognition (invoke TableTransformer)",
     "description": "only SUSPICIOUS picture-labelled regions (probe-gated) get "
                    "cropped and run through the real TableTransformerBackend model",
     "recall_gain": "POTENTIALLY HIGHEST -- real structure recognition, not "
                    "geometric approximation",
     "false_positive_exposure": "gated the same way as B, so similar exposure -- but "
                                "a spurious TableTransformer detection on a non-table "
                                "crop is a NEW failure mode B does not have",
     "compute_cost": "one extra TableTransformer forward pass per gated region -- "
                     "CPU-feasible (024/025 ran it on CPU already) but not free; "
                     "NOT executed this milestone (see limitations) due to scope/"
                     "budget, not infeasibility",
     "implementation_complexity": "MEDIUM -- needs image cropping + model invocation "
                                  "path not currently exposed for a sub-region crop",
     "new_failure_modes": "model hallucination on a non-table crop; unpredictable "
                          "runtime cost per call",
     "provenance_implications": "GOOD if implemented like B",
     "interaction_with_adaptive_routing": "adds a NEW model dependency to routes that "
                                          "currently have none for this content"},
    {"id": "D", "name": "Region splitting / reinterpretation",
     "description": "use the picture region's OWN nested child text geometry "
                    "(already emitted by Docling per traverse_pictures=True) to "
                    "reconstruct row/col structure deterministically -- no new "
                    "model, no crop, no re-render",
     "recall_gain": "MEDIUM-HIGH -- limited by whatever geometric fidelity the "
                    "nested children already carry (no new detection, only "
                    "reorganization of evidence Docling already produced)",
     "false_positive_exposure": "SAME as B in principle (can be probe-gated "
                                "identically) but the RECONSTRUCTION itself, not just "
                                "the gate, could misfire on borderline geometry",
     "compute_cost": "ZERO new model calls -- pure geometry over already-emitted "
                     "regions",
     "implementation_complexity": "LOW-MEDIUM (band-clustering logic already "
                                  "written and validated in 026)",
     "new_failure_modes": "cell text/position could be WRONG if nested children are "
                          "coarser than true cells (Docling's traverse_pictures "
                          "children are its own text-block granularity, not "
                          "necessarily one child per true table cell)",
     "provenance_implications": "GOOD -- new Table carries a distinct source marker",
     "interaction_with_adaptive_routing": "orthogonal, same as B"},
    {"id": "E", "name": "Multi-signal recovery",
     "description": "combine OCR topology + geometry + region label + confidence "
                    "into one scoring/recovery pipeline",
     "recall_gain": "unclear without implementation -- NOT assumed superior to D "
                    "per the milestone's explicit instruction",
     "false_positive_exposure": "unknown -- more signals is not automatically safer",
     "compute_cost": "higher than D (more signals to compute)",
     "implementation_complexity": "HIGH",
     "new_failure_modes": "signal interaction effects not analyzed",
     "provenance_implications": "unclear",
     "interaction_with_adaptive_routing": "unclear",
     "note": "NOT selected for controlled implementation this milestone -- D "
            "(the geometrically simplest candidate that is fully offline and "
            "reuses validated 026 logic) is preferred as the more conservative, "
            "more interpretable first test, per the milestone's 'do not assume D "
            "or E is automatically superior' instruction being read as license to "
            "choose the SIMPLER of the two when both are plausible, not a "
            "requirement to test both"},
]


def main():
    Path("intervention_candidates.json").write_text(json.dumps(CANDIDATES, indent=1, ensure_ascii=False))
    for c in CANDIDATES:
        print(f"{c['id']}: {c['name']} -- recall {c['recall_gain'][:30]}")
    print("\nSELECTED FOR CONTROLLED IMPLEMENTATION (Phase 10):")
    print("  Control: current production behavior (no change)")
    print("  Intervention CONSERVATIVE = B+D combined, probe-gated at threshold=3")
    print("  Intervention AGGRESSIVE = D applied ungated (every picture region with "
          ">=1 nested text child gets reconstructed, no probe gate)")
    print("  C (real TableTransformer) NOT executed this milestone -- scope decision, "
          "recorded as a limitation, not a finding of infeasibility")


if __name__ == "__main__":
    raise SystemExit(main())
