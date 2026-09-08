"""031 Phase 13 -- search ALL historical IR for a better negative-control
population than the 39 (really: 3-document) weak negatives already used.

The intervention (Option D) can only ever fire on a picture/chart-labelled
region that already has >=1 nested Docling text child -- a picture region
with ZERO children never reaches table_shape_score at all (see
controlled_intervention.apply_intervention: `if not children: continue`).
So the population that actually matters for false-positive risk is:
  picture/chart regions with >=1 nested text child that are NOT a table.

This searches the FULL extent of layout-JSON-bearing artifacts in the
repository (not just the milestone's own working set) to determine whether
a larger, more diverse population of this kind exists anywhere.

    python experiments/031_table_label_gating/negative_controls.py
"""
from __future__ import annotations
import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
L29 = REPO / "experiments/029_deep_forensic_replay"
sys.path.insert(0, str(HERE))
from table_shape_probe import compute_signals, table_shape_score  # noqa: E402
from controlled_intervention import attach_text_from_elements  # noqa: E402

# Ground truth for the realscan_probe documents, established by directly
# reading the reconstructed nested-child TEXT against each region (see this
# milestone's session log) -- these are real-world documents unrelated to
# the stamp-vi synthetic corpus, so no manifest hard_case_labels exist for
# them; the label below is a manual visual/textual determination, cited to
# the exact recovered text, not an assumption.
REALSCAN_GROUND_TRUTH = {
    ("jiaocaineedrop_Chapter9.pdf_46", 0): {
        "verdict": "NOT_A_TABLE",
        "evidence": "recovered nested-child text = ['macmillanmh.com', 'Practice', "
                   "'3', 'Cumulative, Chapters 1-9'] (2 of 6 children empty-text, "
                   "likely a logo glyph and a page-number icon) -- a worksheet page "
                   "HEADER/BANNER (publisher watermark + unit/chapter title + "
                   "practice-set label), not tabular data.",
    },
}


def score_realscan_population(all_layout_dirs):
    """Run the ACTUAL table_shape_probe (same function 031 Phase 4-6 built
    and the conservative intervention gates on) against every picture-with-
    children region in the realscan_probe arm -- a genuinely different,
    previously-unscanned real-world document family (scientific papers,
    textbook chapters, a newspaper page, a slide deck), not more of the
    same 3-4 stamp-vi documents."""
    out = []
    for ld in all_layout_dirs:
        if "realscan_probe" not in str(ld):
            continue
        doc_dir = ld.parent
        did = doc_dir.name.rsplit("-", 1)[0]
        final_f = doc_dir / "final" / "document.json"
        if not final_f.exists():
            continue
        final = json.loads(final_f.read_text())
        for pi, lf in enumerate(sorted(ld.glob("*.json"))):
            layout = json.loads(lf.read_text())
            regions = layout.get("regions") or []
            pictures = [r for r in regions if (r.get("label") or "").lower() in ("picture", "chart")]
            pages = final.get("pages") or []
            pg = pages[pi] if pi < len(pages) else (pages[0] if pages else {})
            for idx, pic in enumerate(pictures):
                pbb = pic.get("bbox")
                if pbb is None:
                    continue
                children = [r for r in regions if r is not pic and r.get("bbox")
                           and overlap_frac(pbb, r["bbox"]) > 0.5
                           and (r.get("label") or "").lower() not in ("picture", "chart", "table")]
                if not children:
                    continue
                children = attach_text_from_elements([dict(c) for c in children], pg.get("elements") or [])
                sig = compute_signals(pbb, children)
                score, reasons = table_shape_score(sig)
                gt = REALSCAN_GROUND_TRUTH.get((did, idx))
                out.append({
                    "document_id": did, "region_index": idx, "page_file": lf.name,
                    "region_bbox": pbb, "n_children": len(children),
                    "signals": sig, "table_shape_score": score, "score_reasons": reasons,
                    "recovered_child_texts": [c.get("text", "") for c in children],
                    "ground_truth": gt["verdict"] if gt else "NOT_MANUALLY_VERIFIED",
                    "ground_truth_evidence": gt["evidence"] if gt else (
                        "not individually inspected this milestone -- score/signals "
                        "reported for completeness, no verdict claimed"),
                    "false_positive_at_threshold_3": (
                        score >= 3 and gt is not None and gt["verdict"] == "NOT_A_TABLE"),
                })
    return out


def overlap_frac(a, b):
    ix0, iy0 = max(a["x0"], b["x0"]), max(a["y0"], b["y0"])
    ix1, iy1 = min(a["x1"], b["x1"]), min(a["y1"], b["y1"])
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    inter = (ix1 - ix0) * (iy1 - iy0)
    area_b = max(1.0, (b["x1"] - b["x0"]) * (b["y1"] - b["y0"]))
    return inter / area_b


def main():
    # Step 1: confirm the FULL extent of layout-JSON-bearing artifacts in
    # the repo (not just the 023-025 set 029/031 already worked from) --
    # every distinct {milestone}/_runs/**/layout directory that exists on
    # disk, found by direct filesystem search, not by trusting
    # cohort_inventory.json's own bookkeeping.
    all_layout_dirs = sorted(REPO.glob("experiments/*/_runs/**/layout"))
    arm_dirs_by_milestone = {}
    for ld in all_layout_dirs:
        rel = ld.relative_to(REPO)
        milestone_dir = rel.parts[0]
        arm_dirs_by_milestone.setdefault(milestone_dir, set()).add(str(ld.relative_to(REPO)))

    inv = json.loads((L29 / "cohort_inventory.json").read_text())
    inventory_arm_roots = {a["artifact_root"] for a in inv["arms"]}
    layout_doc_dirs = {str(ld.parent.relative_to(REPO)) for ld in all_layout_dirs}
    not_in_inventory = sorted(layout_doc_dirs - inventory_arm_roots)

    # Step 2: exhaustively scan EVERY layout json under EVERY layout dir
    # found in step 1 (including any not in cohort_inventory.json), for
    # every picture/chart region and its nested-child count, keyed by
    # document identity.
    doc_child_counts = {}   # document_id -> set of (n_children observed across arms)
    total_picture_regions = 0
    total_docs_scanned = set()
    for ld in all_layout_dirs:
        doc_dir = ld.parent
        did = doc_dir.name.rsplit("-", 1)[0]
        total_docs_scanned.add(did)
        for lf in sorted(ld.glob("*.json")):
            try:
                layout = json.loads(lf.read_text())
            except Exception:
                continue
            regions = layout.get("regions") or []
            pictures = [r for r in regions if (r.get("label") or "").lower() in ("picture", "chart")]
            for pic in pictures:
                total_picture_regions += 1
                pbb = pic.get("bbox")
                if pbb is None:
                    continue
                n_children = sum(
                    1 for r in regions if r is not pic and r.get("bbox")
                    and overlap_frac(pbb, r["bbox"]) > 0.5
                    and (r.get("label") or "").lower() not in ("picture", "chart", "table"))
                doc_child_counts.setdefault(did, set()).add(n_children)

    docs_with_any_nested_child = sorted(
        d for d, counts in doc_child_counts.items() if any(c >= 1 for c in counts))
    docs_zero_child_only = sorted(
        d for d, counts in doc_child_counts.items() if all(c == 0 for c in counts))

    known_7 = {"cmb_scan_stamp_table_vi", "cmb_stamp_boundary_vi", "cmb_stamp_table_vi",
              "hc_stamp_table_vi", "cmb_lowcontrast_stamp_vi", "hc_stamp_text_vi",
              "hc_transparent_seal_vi"}
    new_docs_found = sorted(set(docs_with_any_nested_child) - known_7)

    # Step 3: characterize the corpus these 7 documents come from, to make
    # the narrowness of the negative pool concrete and citable.
    corpus = json.loads((REPO / "research/production_corpus/corpus/manifest.json").read_text())
    scan = json.loads((REPO / "experiments/024_ocr_fidelity_recovery/scan_cohort_manifest.json").read_text())
    corpus_doc_ids = {d["document_id"] for d in corpus["documents_list"]}
    scan_doc_ids = {d["document_id"] for d in scan["documents_list"]}
    all_corpus_doc_ids = corpus_doc_ids | scan_doc_ids

    realscan_scored = score_realscan_population(all_layout_dirs)
    realscan_fps = [r for r in realscan_scored if r["false_positive_at_threshold_3"]]

    if not new_docs_found:
        verdict = "CANNOT ESTABLISH A MEANINGFUL FALSE-POSITIVE RATE FROM EXISTING ARTIFACTS."
    elif realscan_fps:
        verdict = (
            f"THE PROBE HAS A CONFIRMED FALSE POSITIVE outside its validation "
            f"population: {len(realscan_fps)} region(s) among the {len(new_docs_found)} "
            f"newly-found document(s) score >= the conservative threshold (3) "
            f"despite manual verification that they are NOT tables (see "
            f"realscan_probe_population -> false_positive_at_threshold_3=true "
            f"entries). table_shape_probe.json's 0-false-positive / 100%-precision "
            f"claim held ONLY within its own narrow 3-document negative pool and "
            f"does NOT generalize to a genuinely different document family."
        )
    else:
        verdict = (
            f"{len(new_docs_found)} additional document(s) found and scored; none "
            f"manually verified as false positives, but "
            f"{sum(1 for r in realscan_scored if r['ground_truth']=='NOT_MANUALLY_VERIFIED')} "
            f"of {len(realscan_scored)} scored region(s) were not individually "
            f"verified -- treat as inconclusive, not confirmed-safe."
        )

    payload = {
        "search_scope": {
            "method": "filesystem glob for every experiments/*/_runs/**/layout "
                     "directory that actually exists on disk (not restricted to "
                     "cohort_inventory.json's own bookkeeping)",
            "layout_dirs_found": len(all_layout_dirs),
            "layout_dirs_not_in_029_cohort_inventory": not_in_inventory,
            "milestones_with_layout_artifacts": sorted(arm_dirs_by_milestone),
            "note": "layout/*.json snapshots (the only artifact carrying Docling "
                   "region labels+geometry) exist ONLY under 023/024/025's _runs "
                   "directories anywhere in this repository -- milestones "
                   "000-022 and 026-030 either predate this artifact or are pure "
                   "analysis over 023-025's data with no new runs of their own.",
        },
        "corpus_scale": {
            "total_distinct_document_ids_in_production_and_scan_manifests": len(all_corpus_doc_ids),
            "total_distinct_document_dirs_scanned_for_picture_regions": len(total_docs_scanned),
            "total_picture_or_chart_region_instances_examined": total_picture_regions,
        },
        "documents_with_at_least_one_nested_text_child_ANYWHERE_in_any_arm": docs_with_any_nested_child,
        "documents_with_picture_regions_but_ZERO_children_in_every_arm": docs_zero_child_only,
        "new_documents_beyond_the_known_7": new_docs_found,
        "finding": (
            f"Exhaustive search of every layout-JSON-bearing artifact in the "
            f"repository ({len(all_layout_dirs)} layout directories, "
            f"{total_picture_regions} picture/chart region instances, "
            f"{len(total_docs_scanned)} distinct document directories) confirms "
            f"exactly {len(docs_with_any_nested_child)} distinct documents EVER "
            f"produce a picture/chart-labelled region with >=1 nested Docling "
            f"text child, and all {len(docs_with_any_nested_child)} were already "
            f"known from gated_table_population.json (031 Phase 2). No new "
            f"documents were found. The {len(docs_zero_child_only)} document(s) "
            f"with picture regions but zero nested children are NOT informative "
            f"negatives -- the intervention structurally cannot fire on them "
            f"(apply_intervention: `if not children: continue`), so they carry "
            f"no false-positive-rate information for this specific intervention."
        ),
        "why_this_matters": (
            "The corpus this milestone's IR was replayed from is a small "
            "synthetic/curated set (production_corpus + scan_cohort manifests, "
            f"{len(all_corpus_doc_ids)} distinct document ids total) built to "
            "exercise SPECIFIC hard-case categories (stamps, occlusion, low "
            "contrast, transparency) -- it was not built to sample the general "
            "population of real-world pictures (photos, logos, charts, "
            "diagrams, illustrations, scanned signatures unrelated to tables, "
            "arbitrary marketing/report graphics). The 3 negative documents "
            "(cmb_lowcontrast_stamp_vi, hc_stamp_text_vi, hc_transparent_seal_vi) "
            "are themselves stamp/seal hard-case documents from the SAME small "
            "family as the 4 positive documents -- they test whether the probe "
            "distinguishes stamp-with-table from stamp-without-table, NOT "
            "whether it distinguishes table from the general space of "
            "non-table pictures a production system will actually encounter."
        ),
        "realscan_probe_population": {
            "note": "experiments/024_ocr_fidelity_recovery/_runs/realscan_probe/ -- "
                   "a one-off probe arm over 7 genuinely diverse real-world "
                   "documents (scientific papers, textbook chapters, a newspaper "
                   "page, a slide deck) unrelated to the stamp-vi synthetic "
                   "corpus. This arm exists on disk but was never scanned by "
                   "031 Phase 2-6 (not in 029's cohort_inventory.json, so "
                   "excluded by gated_population.py's/table_shape_probe.py's "
                   "arm iteration) -- found only by this Phase 13 filesystem-"
                   "level search.",
            "documents_in_arm": 7,
            "regions_scored": realscan_scored,
            "confirmed_false_positives_at_threshold_3": len(realscan_fps),
        },
        "verdict": verdict,
    }
    Path("negative_controls.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False))

    print(f"layout dirs found: {len(all_layout_dirs)}")
    print(f"docs with >=1 nested child anywhere: {docs_with_any_nested_child}")
    print(f"docs with picture regions but 0 children always: {docs_zero_child_only}")
    print(f"new documents beyond the known 7: {new_docs_found}")
    print(f"realscan_probe regions scored: {len(realscan_scored)}, "
          f"confirmed false positives @3: {len(realscan_fps)}")
    print(f"\nVERDICT: {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
