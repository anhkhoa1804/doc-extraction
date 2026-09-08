"""033 Phase 12 -- out-of-population generalization test, structured as a
DOCUMENT-FAMILY holdout (not a random page split, per this milestone's
own rule #10).

Family A ("in-population"): the stamp-vi synthetic corpus (023-025) --
the population every candidate design in this milestone was informally
tuned against (row_bands/col_bands/density values were chosen by looking
at exactly these documents' signals).

Family B ("held out"): experiments/024_ocr_fidelity_recovery/_runs/
realscan_probe/ -- 7 genuinely different real-world documents (2
scientific papers, 2 textbook/math-book excerpts, 1 newspaper page, 1
slide-deck page, plus jiaocai_needrop_en) that NO candidate design in
this milestone was tuned against. This is exactly the population that
originally falsified 031's "100% precision" claim (the Chapter9 case),
so it is the correct holdout to re-test against.

    python experiments/033_table_shape_integrity/out_of_population_results.py
"""
from __future__ import annotations
import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
L31 = REPO / "experiments/031_table_label_gating"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(L31))
from candidate_designs import CANDIDATES  # noqa: E402
from table_shape_probe import compute_signals, table_shape_score  # noqa: E402


def overlap_frac(a, b):
    ix0, iy0 = max(a["x0"], b["x0"]), max(a["y0"], b["y0"])
    ix1, iy1 = min(a["x1"], b["x1"]), min(a["y1"], b["y1"])
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    inter = (ix1 - ix0) * (iy1 - iy0)
    area_b = max(1.0, (b["x1"] - b["x0"]) * (b["y1"] - b["y0"]))
    return inter / area_b


def main():
    corpus_recheck = json.loads((HERE / "corpus_recheck.json").read_text())
    probe = json.loads((L31 / "table_shape_probe.json").read_text())

    # Family A: in-population confirmed positives (already fully
    # characterized -- reused, not recomputed)
    family_a_positive = [r for r in probe["all_positive_rows"] if r.get("is_table_ground_truth")]
    family_a_docs = sorted({r["document_id"] for r in family_a_positive})

    # Family B: every realscan_probe document, both its known
    # picture-with-children candidates (Chapter9, en_1898 -- already
    # scored in 031/032) and a fresh whole-page text sweep of its OTHER
    # 5 documents (no picture-candidate involvement at all)
    realscan_root = REPO / "experiments/024_ocr_fidelity_recovery/_runs/realscan_probe"
    family_b_docs = sorted(d.name.rsplit("-", 1)[0] for d in realscan_root.iterdir() if d.is_dir())

    family_b_page_sweep = []
    for doc_dir in sorted(realscan_root.iterdir()):
        if not doc_dir.is_dir():
            continue
        did = doc_dir.name.rsplit("-", 1)[0]
        layout_dir = doc_dir / "layout"
        if not layout_dir.exists():
            continue
        for lf in sorted(layout_dir.glob("*.json")):
            layout = json.loads(lf.read_text())
            regions = layout.get("regions") or []
            text_regions = [r for r in regions if (r.get("label") or "").lower()
                            in ("text", "section_header", "paragraph", "caption",
                               "footnote", "list_item")]
            if len(text_regions) < 2:
                continue
            xs = [r["bbox"]["x0"] for r in text_regions] + [r["bbox"]["x1"] for r in text_regions]
            ys = [r["bbox"]["y0"] for r in text_regions] + [r["bbox"]["y1"] for r in text_regions]
            page_bbox = {"x0": min(xs), "y0": min(ys), "x1": max(xs), "y1": max(ys)}
            sig = compute_signals(page_bbox, text_regions)
            orig_score, orig_reasons = table_shape_score(sig)
            row = {"document_id": did, "page_file": lf.name, "n_text_regions": len(text_regions),
                  "signals": sig, "original_score": orig_score,
                  "original_gate_pass": orig_score >= 3}
            for cand_name, cand in CANDIDATES.items():
                passes, score, reasons, detail = cand["fn"](sig)
                row[f"{cand_name}_gate_pass"] = passes
            family_b_page_sweep.append(row)

    # pull Chapter9/en_1898's known picture-candidate results directly
    # from corpus_recheck's Part 1/negative_controls (already computed,
    # reused not recomputed)
    negctl = json.loads((L31 / "negative_controls.json").read_text())
    family_b_picture_candidates = negctl["realscan_probe_population"]["regions_scored"]

    def summarize(rows, gate_key_fn):
        n = len(rows)
        n_pass = sum(1 for r in rows if gate_key_fn(r))
        return {"n": n, "n_gate_pass": n_pass,
               "rate": round(n_pass / n, 4) if n else None}

    generalization = {"ORIGINAL_rule": summarize(family_b_page_sweep, lambda r: r["original_gate_pass"])}
    for cand_name in CANDIDATES:
        generalization[cand_name] = summarize(
            family_b_page_sweep, lambda r, c=cand_name: r[f"{c}_gate_pass"])

    payload = {
        "family_A_in_population": {
            "corpus": "stamp-vi synthetic (023-025)",
            "documents": family_a_docs,
            "n_documents": len(family_a_docs),
            "role": "the population every candidate design in this "
                   "milestone was informally tuned against (structural "
                   "floors chosen by inspecting exactly these documents' "
                   "signals) -- retention here (candidate_results.json: "
                   "100% for all candidates) is NOT independent evidence "
                   "of generalization.",
        },
        "family_B_held_out": {
            "corpus": "experiments/024_ocr_fidelity_recovery/_runs/"
                     "realscan_probe/ -- genuinely diverse real-world "
                     "documents (scientific papers, textbook/math "
                     "excerpts, newspaper, slide deck)",
            "documents": family_b_docs,
            "n_documents": len(family_b_docs),
            "role": "NO candidate design in this milestone was tuned "
                   "against ANY document in this family -- this is the "
                   "correct holdout, and is the SAME family that "
                   "originally falsified 031's precision claim.",
            "known_picture_candidates": family_b_picture_candidates,
            "whole_page_text_sweep": {
                "n_pages_scored": len(family_b_page_sweep),
                "generalization_by_rule": generalization,
                "sample_rows": family_b_page_sweep[:5],
            },
        },
        "qualitative_note": (
            "sample size on Family B is small (7 documents, "
            f"{len(family_b_page_sweep)} pages with >=2 text regions) -- "
            "per this milestone's own rule against fake statistical "
            "confidence with insufficient sample size, rates here are "
            "reported as exact counts over this specific small "
            "population, NOT generalized into a production false-"
            "positive-rate estimate."
        ),
        "finding": (
            f"On Family B's known picture-candidates: the ORIGINAL rule "
            f"wrongly admits Chapter9 (region 0); Candidates D and E "
            f"correctly reject it, A/B/C do not (candidate_results.json). "
            f"On Family B's whole-page text sweep ({len(family_b_page_sweep)} "
            f"pages): ORIGINAL rule triggers on "
            f"{generalization['ORIGINAL_rule']['n_gate_pass']}/{generalization['ORIGINAL_rule']['n']}; "
            f"Candidate E triggers on "
            f"{generalization['E_density_plus_tighter_rows']['n_gate_pass']}/{generalization['E_density_plus_tighter_rows']['n']} "
            f"-- a real reduction, though not to zero, on a family none of "
            f"the candidates were tuned against."
        ),
    }
    Path("out_of_population_results.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False))
    print(f"Family A (in-population): {len(family_a_docs)} documents")
    print(f"Family B (held out): {len(family_b_docs)} documents, "
          f"{len(family_b_page_sweep)} pages scored")
    for name, s in generalization.items():
        print(f"  {name}: {s}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
