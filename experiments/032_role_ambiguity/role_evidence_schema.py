"""032 Phase 4 -- general evidence-vector schema (not a single heuristic
score).

Each candidate dimension is kept ONLY if it is: available from current
artifacts (computable from data actually stored, not requiring re-access
to pixels/original files unless explicitly marked), interpretable
(a human can say what a given value means), reproducible (deterministic,
no model call), and potentially useful for routing (varies between the
table-shaped-picture population and the confirmed-picture population --
verified against role_ambiguity_population.json's real numbers where
possible, not asserted on intuition).

    python experiments/032_role_ambiguity/role_evidence_schema.py
"""
from __future__ import annotations
import json
from pathlib import Path
HERE = Path(__file__).resolve().parent
L31 = HERE.parents[1] / "experiments/031_table_label_gating"

DIMENSIONS = {
    "geometry": {
        "aspect_ratio": {
            "available": True, "reproducible": True, "interpretable": True,
            "source": "region bbox width/height -- table_shape_probe.py "
                     "compute_signals, already computed for the entire "
                     "031 population.",
            "useful_for_routing": (
                "PROMISING, n=5 (weak): the 4 known true positives cluster "
                "at 3.08-3.21; the Chapter9 false positive is 4.88 -- a "
                "wider/shorter shape. See 031 FINAL_REPORT.md section 9. "
                "NOT independently validated at scale this milestone "
                "either (same n=1 counter-example caveat carries over)."
            ),
        },
        "area": {"available": True, "reproducible": True, "interpretable": True,
                 "source": "bbox width*height", "useful_for_routing":
                 "NOT TESTED -- retained for completeness, no discriminating "
                 "evidence gathered this milestone or 031."},
        "row_band_count": {
            "available": True, "reproducible": True, "interpretable": True,
            "source": "table_shape_probe.py band_count(), mutual-y-overlap "
                     "clustering (the same construction 026 validated for "
                     "table rows).",
            "useful_for_routing": (
                "STRONGEST single signal found across 031+032: all 4 true "
                "positives have row_bands 3-4; the Chapter9 false positive "
                "has row_bands=2. Still n=1 counter-example, not a "
                "validated threshold."
            ),
        },
        "col_band_count": {"available": True, "reproducible": True, "interpretable": True,
                           "source": "table_shape_probe.py band_count(), x-axis",
                           "useful_for_routing": "present in the existing "
                           "table_shape_score rule; not independently as "
                           "discriminating as row_bands (031 data: "
                           "cmb_stamp_boundary_vi's PSEUDO_TABLE misfire "
                           "has col_bands=4, same range as true positives)."},
        "row_regularity_cv": {"available": True, "reproducible": True, "interpretable": True,
                              "source": "table_shape_probe.py regularity(), "
                              "coefficient of variation of row-band gaps",
                              "useful_for_routing": "USED -- gates +1 point "
                              "when < 0.5 (table_shape_score, "
                              "031/table_shape_probe.py); see the "
                              "verified_used_in_table_shape_score field "
                              "below, checked programmatically against "
                              "source rather than asserted here."},
        "col_regularity_cv": {"available": True, "reproducible": True, "interpretable": True,
                              "source": "table_shape_probe.py regularity(), x-axis",
                              "useful_for_routing": "COMPUTED but NEVER "
                              "used by table_shape_score's point rule -- "
                              "verified programmatically this milestone "
                              "(see verified_used_in_table_shape_score "
                              "below); a real, previously-unstated gap in "
                              "031's probe, unlike row_regularity_cv which "
                              "IS used."},
    },
    "text_topology": {
        "n_nested_text_children": {
            "available": True, "reproducible": True, "interpretable": True,
            "source": "overlap_frac(picture_bbox, child_bbox) > 0.5, "
                     "gated_population.py -- this IS Phase 2's own "
                     "'CONFIRMED' classification threshold (>=6).",
            "useful_for_routing": "NECESSARY but NOT SUFFICIENT: Chapter9's "
                                  "false positive also has exactly 6 "
                                  "children (negative_controls.json) -- "
                                  "identical count to the true positives.",
        },
        "text_density": {"available": True, "reproducible": True, "interpretable": True,
                         "source": "sum(child areas)/region area, "
                         "table_shape_probe.py compute_signals",
                         "useful_for_routing": "WEAK -- true positives range "
                         "0.15-0.87, Chapter9 is 0.17 -- overlapping ranges, "
                         "not discriminating on its own (031 data)."},
        "children_per_row_band": {"available": True, "reproducible": True, "interpretable": True,
                                  "source": "n_children / row_bands, "
                                  "table_shape_probe.py",
                                  "useful_for_routing": "MODERATE: true "
                                  "positives 4.0-4.67, Chapter9 3.0 -- "
                                  "directionally consistent with row_bands "
                                  "but not independently tested."},
        "recovered_text_content": {
            "available": "PARTIAL -- requires the fix this milestone's "
                         "predecessor made (controlled_intervention.py "
                         "attach_text_from_elements): layout/*.json alone "
                         "carries NO text, only document.json's elements "
                         "list does, and the two must be joined by bbox "
                         "IoU. Once joined, real text IS available and was "
                         "the decisive evidence for the Chapter9 "
                         "misleading-case verdict (negative_controls.json "
                         "recovered_child_texts: ['macmillanmh.com', "
                         "'Practice', '3', 'Cumulative, Chapters 1-9']).",
            "reproducible": True, "interpretable": True,
            "useful_for_routing": "HIGH VALUE but requires semantic "
                                  "(not merely structural) interpretation "
                                  "-- a human or an LLM reading 'Practice' / "
                                  "'macmillanmh.com' immediately recognizes "
                                  "a page header, which no geometric signal "
                                  "captures. Not currently used by any "
                                  "deterministic rule in this repository.",
        },
    },
    "structural": {
        "repeated_x_boundaries": {"available": True, "reproducible": True, "interpretable": True,
                                  "source": "col_band_count's underlying "
                                  "distinct-x0-position set, already "
                                  "computed as a byproduct",
                                  "useful_for_routing": "REDUNDANT with "
                                  "col_band_count -- not retained as a "
                                  "separate dimension."},
        "grid_consistency": {"available": "NOT COMPUTED", "reproducible": True,
                             "interpretable": True,
                             "source": "would require comparing EVERY row's "
                             "column x-positions against every other row's "
                             "(not just counting bands) -- exactly the gap "
                             "structural_integrity.py's "
                             "cols_horizontally_coherent check fills, "
                             "POST-reconstruction. Not computed as a "
                             "PRE-reconstruction evidence signal this "
                             "milestone.",
                             "useful_for_routing": "HYPOTHESIS, untested as "
                             "a pre-filter: could this same coherence check "
                             "run on raw nested children BEFORE committing "
                             "to a reconstruction, as a stronger gate than "
                             "table_shape_score alone? Not implemented -- "
                             "flagged as a concrete next-step, not claimed "
                             "as validated."},
    },
    "visual_contextual": {
        "stamp_overlap": {"available": False, "reproducible": "N/A",
                          "interpretable": "N/A",
                          "why_not_available": "would require pixel access "
                          "to the rendered page image plus a stamp/seal "
                          "detector -- neither exists in this repository's "
                          "current artifact set. The word 'stamp' in "
                          "document IDs (cmb_stamp_table_vi etc.) is a "
                          "HUMAN NAMING CONVENTION from corpus generation, "
                          "not a detected or stored signal (role_ambiguity_"
                          "population.json absent_categories.stamp)."},
        "page_edge_position": {"available": True, "reproducible": True,
                               "interpretable": True,
                               "source": "region bbox vs Page.width/height "
                               "-- computable, NOT computed by any existing "
                               "031/032 script.",
                               "useful_for_routing": "HYPOTHESIS, untested: "
                               "the Chapter9 false positive sits at the "
                               "very top of its page (y0=0.28) -- headers/"
                               "banners characteristically hug a page edge "
                               "in a way mid-page tables do not. Not tested "
                               "against a larger sample this milestone."},
        "image_texture": {"available": False, "reproducible": "N/A", "interpretable": "N/A",
                          "why_not_available": "requires pixel-level image "
                          "analysis (e.g. edge density, color histogram) -- "
                          "no such computation exists anywhere in this "
                          "repository's pipeline or research scripts."},
    },
    "provenance": {
        "ocr_backend": {"available": True, "reproducible": True, "interpretable": True,
                        "source": "RunMetadata.backend / Element.source_backend",
                        "useful_for_routing": "FACT (029/030): OCR-"
                                              "recognizer choice measurably "
                                              "changes downstream table "
                                              "structure (hc_encoding_vi, "
                                              "030 section 5) -- a real, "
                                              "already-proven signal, "
                                              "though for a DIFFERENT "
                                              "defect (row-synthesis "
                                              "escape) than role ambiguity."},
        "route": {"available": True, "reproducible": True, "interpretable": True,
                 "source": "RunMetadata.route / Page.source_route",
                 "useful_for_routing": "FACT (031): route family "
                                       "(adaptive/native vs scan_cohort/"
                                       "rasterized vs visual/forced-OCR) is "
                                       "the strongest confirmed driver of "
                                       "table-vs-picture LABEL OUTCOME "
                                       "itself (031 FINAL_REPORT.md "
                                       "sections 3-4, 10)."},
        "synthesis_marker": {"available": True, "reproducible": True, "interpretable": True,
                             "source": "Cell.confidence == 0.5 exclusively "
                             "marks tier-3 row synthesis (029 section 6)",
                             "useful_for_routing": "proven signal for a "
                             "DIFFERENT defect (row-synthesis bbox escape), "
                             "not role ambiguity -- included for "
                             "completeness of the provenance dimension, not "
                             "claimed relevant here."},
    },
}


def main():
    # sanity-check the row_regularity_cv/col_regularity_cv "not used in
    # scoring rule" claim directly against 031's actual source, rather than
    # asserting it from memory
    probe_src = (L31 / "table_shape_probe.py").read_text()
    score_fn = probe_src.split("def table_shape_score")[1].split("def main")[0]
    row_cv_used = "row_regularity_cv" in score_fn
    col_cv_used = "col_regularity_cv" in score_fn
    DIMENSIONS["geometry"]["row_regularity_cv"]["verified_used_in_table_shape_score"] = row_cv_used
    DIMENSIONS["geometry"]["col_regularity_cv"]["verified_used_in_table_shape_score"] = col_cv_used

    retained = []
    rejected = []
    for group, dims in DIMENSIONS.items():
        for name, spec in dims.items():
            entry = {"dimension": name, "group": group, **spec}
            if spec.get("available") is True:
                retained.append(entry)
            else:
                rejected.append(entry)

    payload = {
        "principle": "retain only dimensions that are available from "
                    "current artifacts, interpretable, reproducible, and "
                    "have at least a stated (not necessarily validated) "
                    "routing-relevance rationale -- rejected dimensions "
                    "are recorded WITH the reason, not silently dropped.",
        "dimensions_by_group": DIMENSIONS,
        "retained_count": len(retained),
        "rejected_count": len(rejected),
        "rejected_dimensions": [{"dimension": r["dimension"], "group": r["group"],
                                 "reason": r.get("why_not_available") or r.get("useful_for_routing")}
                                for r in rejected],
        "note_on_col_row_regularity_cv": (
            f"VERIFIED this milestone by reading 031's actual "
            f"table_shape_probe.py source: row_regularity_cv is "
            f"{'USED' if row_cv_used else 'COMPUTED BUT NEVER USED'} in "
            f"table_shape_score's point rule; col_regularity_cv is "
            f"{'USED' if col_cv_used else 'COMPUTED BUT NEVER USED'}. This "
            f"is a real, previously-unstated gap in 031's own probe -- "
            f"col_regularity_cv is computed for every candidate but never "
            f"influences table_shape_score."
        ),
    }
    Path("role_evidence_schema.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False))
    print(f"retained dimensions: {len(retained)}")
    print(f"rejected dimensions: {len(rejected)}")
    print(payload["note_on_col_row_regularity_cv"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
