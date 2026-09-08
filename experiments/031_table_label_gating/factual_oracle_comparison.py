"""031 Phase 12 -- factual oracle comparison.

For every CONFIRMED gated-picture document, find every historical FACTUAL
table (a Table object produced by the real production pipeline in some
arm -- NOT a 031 reconstruction) anywhere in the replayed 023-025 corpus,
and compare it against the picture-gated candidate for the same document.

Two comparison regimes, kept explicitly distinct:

  SAME_ARM   : the picture-labelled region and a factual table coexist in
               the SAME arm (same coordinate system, same render). bbox
               IoU/containment is a direct, valid geometric test of
               physical-region identity.

  CROSS_ARM  : the factual table only exists in a DIFFERENT arm (e.g.
               adaptive/native-PDF-point coordinates) than the picture-gated
               region (e.g. scan_cohort/rasterized-pixel coordinates).
               Geometric IoU is NOT meaningful across these coordinate
               systems -- same_physical_region is instead judged from
               table SHAPE agreement and TEXT TOKEN overlap between the
               factual cells and the candidate's own nested-text children
               (reusing controlled_intervention's text-attachment fix).

Never invents a GT metric when physical-region identity is not
demonstrable: same_physical_region is reported as YES / PROBABLE / UNKNOWN
per case, never assumed.

    python experiments/031_table_label_gating/factual_oracle_comparison.py
"""
from __future__ import annotations
import json, re, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
from controlled_intervention import overlap_frac, bbox_iou, attach_text_from_elements  # noqa: E402

ARM_ROOTS = {
    "023": REPO / "experiments/023_evidence_centric/_runs",
    "024": REPO / "experiments/024_ocr_fidelity_recovery/_runs",
    "025": REPO / "experiments/025_layout_evidence_recall/_runs",
}


def doc_dir_for(milestone, arm, document_id):
    base = ARM_ROOTS[milestone] / arm
    if not base.exists():
        return None
    for d in base.iterdir():
        if d.is_dir() and d.name.rsplit("-", 1)[0] == document_id:
            return d
    return None


def tokenize(text):
    return set(re.findall(r"[\wÀ-ỹ]+", (text or "").lower()))


def load_final(doc_dir):
    f = doc_dir / "final" / "document.json"
    return json.loads(f.read_text()) if f.exists() else None


def load_layout_regions(doc_dir, page_index):
    f = doc_dir / "layout" / f"page-{page_index+1:03d}.json"
    if not f.exists():
        return None
    return (json.loads(f.read_text()).get("regions") or [])


def factual_tables_for(doc_dir):
    """Real tables recorded in a HISTORICAL arm's own final/document.json --
    never a 031 reconstruction, since this reads the untouched historical
    artifact directly, not an apply_intervention() output."""
    doc = load_final(doc_dir)
    if doc is None:
        return []
    out = []
    for pg in doc.get("pages") or []:
        for tb in pg.get("tables") or []:
            out.append({"page_index": pg.get("index"), "table": tb,
                       "page_elements": pg.get("elements") or []})
    return out


def picture_candidates_for(doc_dir, page_index):
    regions = load_layout_regions(doc_dir, page_index)
    if not regions:
        return []
    out = []
    for r in regions:
        if (r.get("label") or "").lower() not in ("picture", "chart"):
            continue
        pbb = r.get("bbox")
        if pbb is None:
            continue
        children = [c for c in regions if c is not r and c.get("bbox")
                   and overlap_frac(pbb, c["bbox"]) > 0.5
                   and (c.get("label") or "").lower() not in ("picture", "chart", "table")]
        if children:
            out.append({"region": r, "children": children})
    return out


def cell_texts(tb):
    return [c.get("text") or "" for c in (tb.get("cells") or [])]


def main():
    pop = json.loads((HERE / "gated_table_population.json").read_text())
    confirmed_docs = sorted({c["document_id"] for c in pop["candidates"]
                             if c["classification"] == "CONFIRMED"})

    # every (milestone, arm) actually replayed, from the population itself
    # plus every arm under each of the 3 milestone roots for these docs, so
    # we search the FULL historical surface, not just the picture-gated arms
    all_arms = set()
    for milestone, root in ARM_ROOTS.items():
        if not root.exists():
            continue
        def walk(p, prefix):
            for child in sorted(p.iterdir()):
                if not child.is_dir():
                    continue
                sub = f"{prefix}/{child.name}" if prefix else child.name
                doc_children = [d for d in child.iterdir() if d.is_dir()
                                and "-" in d.name and d.name.rsplit("-", 1)[-1].isdigit()]
                if doc_children:
                    all_arms.add((milestone, sub))
                else:
                    walk(child, sub)
        walk(root, "")

    comparisons = []
    for did in confirmed_docs:
        gated_arms, tabled_arms = [], []
        for milestone, arm in sorted(all_arms):
            d = doc_dir_for(milestone, arm, did)
            if d is None:
                continue
            pics = picture_candidates_for(d, 0)
            if pics:
                gated_arms.append((milestone, arm, d, pics))
            facts = factual_tables_for(d)
            if facts:
                tabled_arms.append((milestone, arm, d, facts))

        if not tabled_arms:
            comparisons.append({
                "document_id": did,
                "factual_oracle_exists": False,
                "note": "no factual (historically-produced) table exists for this "
                       "document in ANY replayed arm -- any reconstruction is a "
                       "geometric simulation only, consistent with counterfactual_"
                       "replay.json's SIMULATED_COUNTERFACTUAL classification",
                "same_arm_pairs": [], "cross_arm_pairs": [],
            })
            continue

        same_arm_pairs = []
        cross_arm_pairs = []
        gated_arm_keys = {(m, a) for m, a, _, _ in gated_arms}
        tabled_arm_keys = {(m, a) for m, a, _, _ in tabled_arms}

        # SAME_ARM: an arm that has both a picture-gated candidate AND a
        # factual table -- direct geometric identity test in one coordinate
        # system
        for (m, a) in sorted(gated_arm_keys & tabled_arm_keys):
            _, _, d, pics = next(x for x in gated_arms if x[0] == m and x[1] == a)
            _, _, _, facts = next(x for x in tabled_arms if x[0] == m and x[1] == a)
            for pic in pics:
                pbb = pic["region"]["bbox"]
                for fe in facts:
                    tb = fe["table"]
                    tbb = tb.get("bbox")
                    if tbb is None:
                        continue
                    iou = bbox_iou(pbb, tbb)
                    contain_frac = overlap_frac(pbb, tbb)  # table area covered by picture bbox
                    if iou > 0.3:
                        same_physical_region = "YES"
                    elif contain_frac > 0.7:
                        same_physical_region = "PROBABLE"
                    else:
                        same_physical_region = "UNKNOWN"
                    same_arm_pairs.append({
                        "milestone": m, "arm": a,
                        "picture_bbox": pbb, "table_bbox": tbb,
                        "bbox_iou": round(iou, 4),
                        "table_contained_in_picture_frac": round(contain_frac, 4),
                        "same_physical_region": same_physical_region,
                        "factual_table_shape": [tb.get("n_rows"), tb.get("n_cols")],
                        "factual_table_n_cells": len(tb.get("cells") or []),
                        "factual_table_populated_cells": sum(
                            1 for c in (tb.get("cells") or []) if c.get("text")),
                        "reasoning": (
                            "bbox_iou>0.3 -> direct overlap in the SAME "
                            "coordinate system (strong identity evidence); "
                            "else table>70% contained within the picture's own "
                            "bbox -> PROBABLE (table is a narrower sub-region of "
                            "the picture block, consistent with 025's known "
                            "picture/nested-text duplication); else UNKNOWN"
                        ),
                    })

        # CROSS_ARM: picture-only-observed arms vs table-only-observed arms,
        # different coordinate systems -- compare shape + text token overlap
        gated_only = gated_arm_keys - tabled_arm_keys
        tabled_only = tabled_arm_keys - gated_arm_keys
        if gated_only and tabled_only:
            # representative pairing: first gated-only arm vs first tabled-only
            # arm (deterministic: sorted order), not all-pairs (same physical
            # table repeats across sibling arms of one route family)
            m_g, a_g = sorted(gated_only)[0]
            m_t, a_t = sorted(tabled_only)[0]
            d_g, pics = next((d, p) for m, a, d, p in gated_arms if m == m_g and a == a_g)
            d_t, facts = next((d, f) for m, a, d, f in tabled_arms if m == m_t and a == a_t)
            doc_g = load_final(d_g)
            pg_g = (doc_g.get("pages") or [{}])[0]
            for pic in pics:
                children = attach_text_from_elements(
                    [dict(c) for c in pic["children"]], pg_g.get("elements") or [])
                cand_tokens = set()
                for c in children:
                    cand_tokens |= tokenize(c.get("text", ""))
                for fe in facts:
                    tb = fe["table"]
                    fact_tokens = set()
                    for t in cell_texts(tb):
                        fact_tokens |= tokenize(t)
                    overlap_tok = cand_tokens & fact_tokens
                    recall = len(overlap_tok) / len(fact_tokens) if fact_tokens else None
                    shape_match = [tb.get("n_rows"), tb.get("n_cols")]
                    n_children = len(children)
                    if recall is not None and recall >= 0.5:
                        same_physical_region = "PROBABLE"
                    elif recall is not None and recall > 0:
                        same_physical_region = "UNKNOWN"
                    else:
                        same_physical_region = "UNKNOWN"
                    cross_arm_pairs.append({
                        "gated_arm": f"{m_g}/{a_g}", "tabled_arm": f"{m_t}/{a_t}",
                        "coordinate_systems_comparable": False,
                        "factual_table_shape": shape_match,
                        "factual_table_token_count": len(fact_tokens),
                        "candidate_nested_children": n_children,
                        "candidate_token_count": len(cand_tokens),
                        "shared_token_count": len(overlap_tok),
                        "shared_tokens_sample": sorted(overlap_tok)[:12],
                        "factual_text_token_recall_in_candidate": (
                            round(recall, 4) if recall is not None else None),
                        "same_physical_region": same_physical_region,
                        "reasoning": (
                            "different arms use different coordinate systems "
                            "(native PDF points vs rasterized pixels) so bbox "
                            "IoU is not meaningful here; token-overlap recall "
                            ">=0.5 -> PROBABLE (majority of the factual table's "
                            "own text content is present among the candidate's "
                            "nested children); otherwise UNKNOWN, not NO -- "
                            "absence of token overlap can also mean the OCR/"
                            "recognizer differs between arms, not that the "
                            "region differs"
                        ),
                    })

        comparisons.append({
            "document_id": did,
            "factual_oracle_exists": True,
            "gated_arms_observed": len(gated_arm_keys),
            "tabled_arms_observed": len(tabled_arm_keys),
            "arms_overlap_same_arm_pair_available": len(gated_arm_keys & tabled_arm_keys) > 0,
            "same_arm_pairs": same_arm_pairs,
            "cross_arm_pairs": cross_arm_pairs,
        })

    Path("factual_oracle_comparison.json").write_text(
        json.dumps({"documents": comparisons}, indent=1, ensure_ascii=False))

    for c in comparisons:
        print(f"\n{c['document_id']}: oracle_exists={c['factual_oracle_exists']}")
        for p in c.get("same_arm_pairs", []):
            print(f"  SAME_ARM  {p['milestone']}/{p['arm']:<12} iou={p['bbox_iou']:<7} "
                  f"contain={p['table_contained_in_picture_frac']:<7} "
                  f"-> {p['same_physical_region']}")
        for p in c.get("cross_arm_pairs", []):
            print(f"  CROSS_ARM {p['gated_arm']:<25} vs {p['tabled_arm']:<20} "
                  f"token_recall={p['factual_text_token_recall_in_candidate']} "
                  f"-> {p['same_physical_region']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
