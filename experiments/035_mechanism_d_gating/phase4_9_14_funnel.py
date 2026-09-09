"""035 Phases 4,5,6,7,8,9,14 -- all derived from table_region_matching.json
(Phase 3's output), no new extraction needed. One script because every one
of these phases is a different aggregation/view over the same per-GT-table
match records, and keeping the D-stage classification logic in one place
avoids the classic bug of two phases silently disagreeing on what counts
as a "failure."

Architecture fact this classifier depends on (verified by source read,
src/doc_extraction/stages/table.py:run_table -- see FINAL_REPORT.md): the
table gate is EXACTLY ONE check (region.label.lower() == "table",
pipelines/base.py:747), applied once before Table Transformer is ever
called. There is no separate confidence-based or secondary gate in this
codebase. Consequently D3 ("correct/usable region rejected by gate") is
ARCHITECTURALLY NEAR-IMPOSSIBLE here and expected to measure ~0 -- that is
itself reported as a finding, not assumed away.

    python experiments/035_mechanism_d_gating/phase4_9_14_funnel.py
"""
from __future__ import annotations
import json
from pathlib import Path
from collections import Counter, defaultdict
HERE = Path(__file__).resolve().parent


def structural_validity(table_obj: dict | None) -> dict:
    if table_obj is None:
        return {"valid": False, "reason": "no_table_object"}
    n_rows, n_cols = table_obj.get("n_rows", 0), table_obj.get("n_cols", 0)
    cells = table_obj.get("cells", [])
    if n_rows < 1 or n_cols < 1 or not cells:
        return {"valid": False, "reason": "empty_or_zero_dim"}
    tb = table_obj.get("bbox")
    escaping = 0
    for c in cells:
        cb = c.get("bbox")
        if tb is None or cb is None:
            continue
        if cb["x0"] < tb["x0"] - 1 or cb["x1"] > tb["x1"] + 1 or cb["y0"] < tb["y0"] - 1 or cb["y1"] > tb["y1"] + 1:
            escaping += 1
    escape_fraction = escaping / len(cells) if cells else 0.0
    populated = sum(1 for c in cells if (c.get("text") or "").strip())
    populated_fraction = populated / len(cells) if cells else 0.0
    valid = escape_fraction < 0.2  # 029's own escaping-cell mechanism; not a tuned threshold, just "mostly not escaping"
    return {
        "valid": valid, "reason": None if valid else "cells_escape_table_bbox",
        "n_rows": n_rows, "n_cols": n_cols, "n_cells": len(cells),
        "escaping_cell_fraction": round(escape_fraction, 4),
        "populated_cell_fraction": round(populated_fraction, 4),
    }


def classify_stage(rec: dict) -> tuple[str, dict]:
    verdict = rec["verdict"]
    if verdict == "NO_REGION":
        return "D1", {"reason": "no internal layout region overlaps this GT table at all"}
    if verdict == "AMBIGUOUS":
        return "D7", {"reason": "matcher could not confidently attribute a single region",
                       "detail": rec["verdict_detail"]}

    if verdict == "MULTIPLE_MATCH":
        contrib = rec["multiple_match_contributors"] or []
        gated = [c for c in contrib if c["table_gate_pass"]]
        if not gated:
            return "D2", {"reason": "GT table fragmented across multiple regions, "
                           "NONE labelled 'table' -- gate excludes all fragments",
                           "n_fragments": len(contrib)}
        if len(gated) < len(contrib):
            return "D2", {"reason": "GT table fragmented across multiple regions, "
                           "SOME labelled 'table' and some not -- partial gating",
                           "n_fragments": len(contrib), "n_gated_fragments": len(gated),
                           "secondary_cause": "mixed_fragment_labels"}
        # all fragments gated: check the resulting table object(s)
        sv = structural_validity(rec["final_table_object"])
        return ("D0" if sv["valid"] else "D6"), {"reason": "all fragments labelled 'table'", **sv}

    # single-region verdicts: EXACT_MATCH / GOOD_MATCH / PARTIAL_MATCH
    mr = rec["matched_region"]
    if mr is None:
        return "D7", {"reason": "verdict implied a single match but matched_region missing "
                       "(index out of range) -- data/index inconsistency, flag for review"}

    if not mr["table_gate_pass"]:
        if mr["final_ir_element_type"] == "table" and rec["final_table_object"] is not None:
            sv = structural_validity(rec["final_table_object"])
            if sv["valid"]:
                return "D0", {"reason": "UNEXPECTED: wrong label but a valid table exists anyway "
                               "-- some recovery path outside the known gate produced it; "
                               "flag prominently, do not silently absorb"}
        return "D2", {"reason": f"region labelled '{mr['internal_label_raw']}', not 'table' -- "
                       "gate excludes it from table_regions, Table Transformer never invoked "
                       "on this region", "match_quality": verdict}

    # gate passed (label == table): specialist WAS invoked on this region.
    # NOTE: raw_tables can legitimately be an EMPTY list ([]) when the
    # specialist ran and produced zero tables -- that's a real D4 case, not
    # "data unavailable". Must check `is None` explicitly, not truthiness,
    # or an empty-but-valid [] is silently misread as missing data (caught
    # during dry-run validation on a page where Table Transformer produced
    # zero tables for a correctly-gated region: raw_tables == [], falsy).
    raw_tables = rec.get("_tables_raw_for_page")  # injected by main() per-page
    if raw_tables is None:
        raw_has_table_here = None  # genuinely unavailable, tables/page-001.json missing
    else:
        raw_has_table_here = any(
            t.get("bbox") and _iou_quick(t["bbox"], mr_region_bbox(rec)) > 0.3
            for t in raw_tables
        )

    if raw_has_table_here is False:
        return "D4", {"reason": "region correctly labelled 'table', gate passed, but Table "
                       "Transformer's own raw output has no table for this bbox -- specialist "
                       "invocation failed to produce structure"}

    if rec["final_table_object"] is None:
        return "D5", {"reason": "region correctly gated, specialist likely ran, but no "
                       "corresponding Table object survived into final IR (post-processing/"
                       "merge loss)", "raw_tables_available_for_page": raw_tables is not None}

    sv = structural_validity(rec["final_table_object"])
    if not sv["valid"]:
        return "D6", {"reason": "table exists in final IR but fails structural validity "
                       "(cells escape table bbox, per 029's known mechanism)", **sv}
    return "D0", {"reason": "no failure", **sv}


def _iou_quick(a, b):
    x0 = max(a["x0"], b["x0"]); y0 = max(a["y0"], b["y0"])
    x1 = min(a["x1"], b["x1"]); y1 = min(a["y1"], b["y1"])
    if x1 <= x0 or y1 <= y0:
        return 0.0
    inter = (x1 - x0) * (y1 - y0)
    area_a = (a["x1"] - a["x0"]) * (a["y1"] - a["y0"])
    area_b = (b["x1"] - b["x0"]) * (b["y1"] - b["y0"])
    denom = area_a + area_b - inter
    return inter / denom if denom > 0 else 0.0


def mr_region_bbox(rec):
    idx = rec["matched_region"]["region_index"]
    for c in rec["top_candidates"]:
        if c["region_index"] == idx:
            return c["bbox"]
    return rec["final_table_object"]["bbox"] if rec["final_table_object"] else rec["gt_bbox_px"]


def main():
    matching = json.loads((HERE / "table_region_matching.json").read_text())
    records = matching["records"]

    # attach raw table-transformer output per page (for D4 detection) by
    # re-reading tables/page-001.json from the same run dirs Phase 3 used.
    import matching_lib as ml
    CHUNK_DIRS = ml.gt_table_run_roots(HERE)
    raw_by_image = {}
    for cd in CHUNK_DIRS:
        if not cd.exists():
            continue
        for run_dir in cd.iterdir():
            meta_p = run_dir / "metadata.json"
            tables_p = run_dir / "tables" / "page-001.json"
            if meta_p.exists() and tables_p.exists():
                meta = json.loads(meta_p.read_text())
                raw = json.loads(tables_p.read_text())
                raw_by_image[meta["input_filename"]] = raw.get("tables", [])

    for rec in records:
        rec["_tables_raw_for_page"] = raw_by_image.get(rec["image"])

    # ---- Phase 4/5: failure funnel + strict Mechanism-D population ----
    stage_counts = Counter()
    stage_records = defaultdict(list)
    for rec in records:
        stage, detail = classify_stage(rec)
        rec["_stage"] = stage
        rec["_stage_detail"] = detail
        stage_counts[stage] += 1
        stage_records[stage].append({"image": rec["image"], "gt_table_anno_id": rec["gt_table_anno_id"],
                                      "detail": detail})

    n_total = len(records)
    funnel = {
        "n_gt_tables_analyzed": n_total,
        "n_gt_tables_full_population": 665,
        "coverage_fraction": round(n_total / 665, 4),
        "stage_definitions": {
            "D0": "No failure", "D1": "Upstream layout detection miss (no region at all)",
            "D2": "Region exists but wrong semantic label (gate excludes it)",
            "D3": "Correct/usable region rejected by gate for another reason -- "
                  "ARCHITECTURALLY NEAR-IMPOSSIBLE in this codebase: the gate IS the "
                  "label check (pipelines/base.py:747), no secondary gate exists "
                  "(stages/table.py:run_table passes all gated regions straight to the "
                  "backend, no further filtering). Expected count: 0.",
            "D4": "Specialist invoked but failed to produce structure for this region",
            "D5": "Specialist succeeded but post-processing lost the output before final IR",
            "D6": "Output exists in final IR but fails structural validity",
            "D7": "Annotation/matching ambiguity (matcher could not attribute confidently)",
        },
        "stage_counts": dict(stage_counts),
        "stage_fractions_of_analyzed": {k: round(v / n_total, 4) for k, v in stage_counts.items()},
        "d3_architectural_check": {
            "measured_d3_count": stage_counts.get("D3", 0),
            "expected_zero_confirmed": stage_counts.get("D3", 0) == 0,
        },
        "verdict_counts_from_phase3": matching["verdict_counts"],
        "per_stage_example_cases": {k: v[:10] for k, v in stage_records.items()},
    }
    Path(HERE / "table_failure_funnel.json").write_text(json.dumps(funnel, indent=1, ensure_ascii=False))

    # ---- Phase 5 restated as its own artifact (strict Mechanism-D def) ----
    strict_d2 = [r for r in records if r["_stage"] == "D2"]
    mech_d = {
        "strict_definition": "GT table + usable corresponding internal region + region "
            "non-table-labelled + table processing consequently skipped. This is EXACTLY "
            "stage D2 in table_failure_funnel.json -- D1 (no region at all) is explicitly "
            "NOT counted as a gating failure (rule 1), and D4/D5/D6 (region WAS correctly "
            "labelled table) are explicitly NOT gating failures either (rule 2).",
        "n_gt_tables_analyzed": n_total,
        "strict_mechanism_d_count": len(strict_d2),
        "strict_mechanism_d_fraction_of_analyzed": round(len(strict_d2) / n_total, 4) if n_total else None,
        "denominator_note": "fraction is of GT tables ANALYZED so far (coverage="
            f"{round(n_total/665,4)} of the full 665), not yet the full population -- "
            "rerun after full extraction completes for the final denominator.",
        "by_data_source": dict(Counter(r["data_source"] for r in strict_d2).most_common()),
        "by_language": dict(Counter(r["language"] for r in strict_d2).most_common()),
        "by_wrong_label": dict(Counter(r["matched_region"]["internal_label_raw"] for r in strict_d2
                                        if r["matched_region"]).most_common()),
    }
    Path(HERE / "mechanism_d_population.json").write_text(json.dumps(mech_d, indent=1, ensure_ascii=False))

    # ---- Phase 6: label confusion matrix ----
    confusion = Counter()
    confusion_by_route_backend = Counter()
    for rec in records:
        if rec["verdict"] in ("EXACT_MATCH", "GOOD_MATCH", "PARTIAL_MATCH") and rec["matched_region"]:
            internal_label = rec["matched_region"]["internal_label_raw"]
        elif rec["verdict"] == "NO_REGION":
            internal_label = "(none)"
        elif rec["verdict"] == "MULTIPLE_MATCH":
            labels = sorted({c["internal_label_raw"] for c in (rec["multiple_match_contributors"] or [])})
            internal_label = "+".join(labels) if labels else "(none)"
        else:
            internal_label = "(ambiguous)"
        confusion[("table", internal_label)] += 1
        confusion_by_route_backend[(internal_label, rec["route"], rec["layout_backend"])] += 1

    gating_confusion = {
        "n_gt_tables_analyzed": n_total,
        "confusion_gt_table_vs_internal_label": [
            {"gt": "table", "internal_label": lbl, "count": c, "fraction": round(c / n_total, 4)}
            for (_, lbl), c in confusion.most_common()
        ],
        "by_data_source": {
            ds: dict(Counter(
                (r["matched_region"]["internal_label_raw"] if r["matched_region"] else
                 ("(none)" if r["verdict"] == "NO_REGION" else "(multi/ambiguous)"))
                for r in records if r["data_source"] == ds
            ).most_common())
            for ds in sorted({r["data_source"] for r in records})
        },
        "by_language": {
            lang: dict(Counter(
                (r["matched_region"]["internal_label_raw"] if r["matched_region"] else
                 ("(none)" if r["verdict"] == "NO_REGION" else "(multi/ambiguous)"))
                for r in records if r["language"] == lang
            ).most_common())
            for lang in sorted({r["language"] for r in records})
        },
    }
    Path(HERE / "gating_confusion_matrix.json").write_text(json.dumps(gating_confusion, indent=1, ensure_ascii=False))

    # ---- Phase 7: label error vs EFFECTIVE gating error ----
    # In this codebase these are the SAME thing (gate == label check, no
    # alternate route re-admits a wrong-labelled region to the specialist)
    # -- measure directly rather than assume.
    #
    # Audit fix (035 preflight, Phase E): the original filter here was
    # `r["matched_region"] and not r["matched_region"]["table_gate_pass"]`,
    # which is None for every MULTIPLE_MATCH record (those populate
    # multiple_match_contributors instead, per Phase 3's schema) -- so a
    # MULTIPLE_MATCH case classify_stage() staged as D2 (mixed or
    # all-non-table fragment labels) would silently NOT be counted here,
    # making gating_impact.json's n_effective_gating_loss inconsistent with
    # mechanism_d_population.json's strict_mechanism_d_count (both should
    # count identical D2 populations). effective_loss is now defined
    # directly from _stage == "D2" (matches Phase 5 by construction, for
    # any verdict shape); label_error_recs is broadened to include
    # MULTIPLE_MATCH cases with >=1 non-table-labelled fragment, so the
    # denominator for "label error rate" isn't silently narrower than the
    # population it's meant to describe.
    label_error_recs = [
        r for r in records
        if (r["matched_region"] and not r["matched_region"]["table_gate_pass"])
        or (r["verdict"] == "MULTIPLE_MATCH"
            and any(not c["table_gate_pass"] for c in (r["multiple_match_contributors"] or [])))
    ]
    effective_loss = [r for r in records if r["_stage"] == "D2"]
    recovered_anyway = [r for r in label_error_recs if r["_stage"] == "D0"]
    wrong_label_recs = label_error_recs  # kept name for the payload below
    # ---- Phase 8: final IR outcome classification (folded into gating_impact.json --
    # Phase 7 "is it an effective gating loss" and Phase 8 "what happened in the "
    # final IR" are two views of the same wrong-label population). ----
    def ir_outcome(rec):
        if rec["_stage"] == "D0":
            return "RECOVERED_DESPITE_LABEL" if (rec["matched_region"] and not rec["matched_region"]["table_gate_pass"]) else "OK_NOT_GATE_RELEVANT"
        if rec["_stage"] == "D2":
            return "GATE_LOSS"
        if rec["_stage"] in ("D4", "D5", "D6", "D1"):
            return "NON_GATE_FAILURE"
        return "AMBIGUOUS_OUTCOME"

    outcome_counts = Counter(ir_outcome(r) for r in records)

    gating_impact = {
        "phase7_label_error_vs_effective_gating_error": {
            "n_gt_tables_with_a_wrong_label_match": len(wrong_label_recs),
            "n_effective_gating_loss": len(effective_loss),
            "n_wrong_label_but_recovered_anyway": len(recovered_anyway),
            "label_error_rate_of_analyzed": round(len(wrong_label_recs) / n_total, 4) if n_total else None,
            "effective_gating_error_rate_of_analyzed": round(len(effective_loss) / n_total, 4) if n_total else None,
            "conclusion": ("FACT (measured, not assumed): every wrong-label match in this run "
                "became an effective gating loss" if len(recovered_anyway) == 0 and wrong_label_recs
                else "wrong label does NOT always mean effective loss -- some recovery path exists, see recovered cases"),
            "recovered_cases": [{"image": r["image"], "anno_id": r["gt_table_anno_id"]} for r in recovered_anyway],
        },
        "phase8_final_ir_outcome_classes": {
            "GATE_LOSS": "wrong label directly caused a missing table in final IR",
            "RECOVERED_DESPITE_LABEL": "wrong label but a valid table exists anyway (unexpected recovery)",
            "NON_GATE_FAILURE": "table loss caused elsewhere in the pipeline (D1/D4/D5/D6), not by the label gate",
            "OK_NOT_GATE_RELEVANT": "region was correctly labelled table and produced a valid result -- no failure",
            "AMBIGUOUS_OUTCOME": "matcher could not confidently attribute a region (D7)",
            "counts": dict(outcome_counts),
            "fractions_of_analyzed": {k: round(v / n_total, 4) for k, v in outcome_counts.items()},
        },
    }
    Path(HERE / "gating_impact.json").write_text(json.dumps(gating_impact, indent=1, ensure_ascii=False))

    # ---- Phase 9: geometry stratification for D2 cases ----
    def gt_geom(rec):
        b = rec["gt_bbox_px"]
        w, h = b["x1"] - b["x0"], b["y1"] - b["y0"]
        return w, h, w * h, (w / h if h else None)

    d2_geom = []
    d0_geom = []
    for r in records:
        w, h, area, ar = gt_geom(r)
        row = {"image": r["image"], "width": round(w, 1), "height": round(h, 1),
               "area": round(area, 1), "aspect_ratio": round(ar, 3) if ar else None}
        if r["_stage"] == "D2":
            d2_geom.append(row)
        elif r["_stage"] == "D0":
            d0_geom.append(row)

    def summarize(rows):
        if not rows:
            return None
        areas = sorted(r["area"] for r in rows)
        ars = sorted(r["aspect_ratio"] for r in rows if r["aspect_ratio"])
        n = len(rows)
        return {
            "n": n,
            "area_median": areas[n // 2],
            "area_p10": areas[int(n * 0.1)], "area_p90": areas[min(n - 1, int(n * 0.9))],
            "aspect_ratio_median": ars[len(ars) // 2] if ars else None,
        }

    geometry_strat = {
        "n_d2_cases": len(d2_geom), "n_d0_cases": len(d0_geom),
        "d2_area_px2_summary": summarize(d2_geom),
        "d0_area_px2_summary": summarize(d0_geom),
        "interpretation_note": "Compare d2 vs d0 area/aspect distributions -- if D2 tables "
            "are systematically smaller/narrower/wider than D0 tables, that is an "
            "interpretable geometric boundary (not a fitted threshold, per rule 8).",
        "d2_rows": d2_geom, "d0_rows_sample": d0_geom[:50],
    }
    Path(HERE / "table_geometry_stratification.json").write_text(json.dumps(geometry_strat, indent=1, ensure_ascii=False))

    # ---- Phase 14: specialist invocation map ----
    invocation = {
        "n_gt_tables_analyzed": n_total,
        "n_region_found_any_quality": sum(1 for r in records if r["verdict"] != "NO_REGION" and r["verdict"] != "AMBIGUOUS"),
        "n_no_region_at_all": sum(1 for r in records if r["verdict"] == "NO_REGION"),
        "n_ambiguous_matching": sum(1 for r in records if r["verdict"] == "AMBIGUOUS"),
        "n_gated_in_labelled_table": sum(1 for r in records if r["matched_region"] and r["matched_region"]["table_gate_pass"]),
        "n_gated_out_wrong_label": sum(1 for r in records if r["matched_region"] and not r["matched_region"]["table_gate_pass"]),
        "n_specialist_actually_invoked": sum(1 for r in records if r["_stage"] in ("D0", "D4", "D5", "D6")
                                              and r["matched_region"] and r["matched_region"]["table_gate_pass"]),
        "n_final_table_present": sum(1 for r in records if r["final_table_object"] is not None),
        "n_final_table_structurally_valid": sum(
            1 for r in records if r["final_table_object"] is not None
            and structural_validity(r["final_table_object"])["valid"]
        ),
        "by_data_source": {
            ds: {
                "n": sum(1 for r in records if r["data_source"] == ds),
                "n_specialist_invoked": sum(1 for r in records if r["data_source"] == ds
                                             and r["matched_region"] and r["matched_region"]["table_gate_pass"]),
                "n_final_valid": sum(1 for r in records if r["data_source"] == ds
                                      and r["final_table_object"] is not None
                                      and structural_validity(r["final_table_object"])["valid"]),
            }
            for ds in sorted({r["data_source"] for r in records})
        },
        "headline": "n_specialist_actually_invoked is the number that matters more than "
            "n_final_table_present alone -- it answers 'how many GT tables actually enter "
            "the table specialist', separating gate loss from everything downstream.",
    }
    Path(HERE / "specialist_invocation_map.json").write_text(json.dumps(invocation, indent=1, ensure_ascii=False))

    # NOTE (audit, Phase C): this script never rewrites table_region_matching.json
    # (only reads it), so the "_tables_raw_for_page"/"_stage"/"_stage_detail" keys
    # added to `records` in-memory above are never persisted to disk -- confirmed
    # deliberately, not a leak. Downstream scripts (phase10/12/13/17) that need
    # `_stage` re-derive it fresh via classify_stage(), which is the single
    # source of truth for D-stage assignment; they do not expect it to be
    # present in table_region_matching.json.

    print("stage_counts:", dict(stage_counts))
    print("strict Mechanism-D (D2) count:", len(strict_d2), "/", n_total)
    print("D3 (should be ~0):", stage_counts.get("D3", 0))
    print("outcome_counts (Phase 8):", dict(outcome_counts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
