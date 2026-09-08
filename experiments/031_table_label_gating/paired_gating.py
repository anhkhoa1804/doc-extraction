"""031 Phase 3 -- paired same-document forensics: the central experiment.

Read-only, CPU-only. For every document that appears BOTH in
gated_table_population.json (picture-labelled, table-shaped) AND in 029's
all_tables.json (table-labelled, reached table_transformer), compare the
region geometry immediately before the gate to find what changed.

    python experiments/031_table_label_gating/paired_gating.py
"""
from __future__ import annotations
import json
from collections import defaultdict
from pathlib import Path
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
L29 = REPO / "experiments/029_deep_forensic_replay"


def iou(a, b):
    ix0, iy0 = max(a["x0"], b["x0"]), max(a["y0"], b["y0"])
    ix1, iy1 = min(a["x1"], b["x1"]), min(a["y1"], b["y1"])
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    inter = (ix1 - ix0) * (iy1 - iy0)
    ua = (a["x1"] - a["x0"]) * (a["y1"] - a["y0"])
    ub = (b["x1"] - b["x0"]) * (b["y1"] - b["y0"])
    union = ua + ub - inter
    return inter / union if union > 0 else 0.0


def main():
    pop = json.loads((HERE / "gated_table_population.json").read_text())
    all_tables = json.loads((L29 / "results/all_tables.json").read_text())

    gated_docs = {c["document_id"] for c in pop["candidates"] if c["classification"] == "CONFIRMED"}
    tabled_docs = {t["document_id"] for t in all_tables}
    overlap_docs = gated_docs & tabled_docs
    print(f"documents with BOTH a confirmed gated-picture AND a real table-labelled "
          f"instance somewhere in the corpus: {sorted(overlap_docs)}")

    # For each such document, group candidates and tables by (milestone, arm), and
    # compare bbox geometry to see if it's the SAME physical region flipping label,
    # or genuinely different regions on different pages.
    cand_by_key = defaultdict(list)
    for c in pop["candidates"]:
        if c["document_id"] in overlap_docs:
            cand_by_key[(c["milestone"], c["arm"], c["document_id"])].append(c)

    table_by_key = defaultdict(list)
    for t in all_tables:
        if t["document_id"] in overlap_docs:
            table_by_key[(t["milestone"], t["arm"], t["document_id"])].append(t)

    all_keys_for_doc = defaultdict(set)
    for k in list(cand_by_key) + list(table_by_key):
        all_keys_for_doc[k[2]].add((k[0], k[1]))

    paired_cases = []
    for did in sorted(overlap_docs):
        arms_gated = {(m, a) for (m, a, d) in cand_by_key if d == did}
        arms_tabled = {(m, a) for (m, a, d) in table_by_key if d == did}
        both = arms_gated & arms_tabled
        gated_only = arms_gated - arms_tabled
        tabled_only = arms_tabled - arms_gated

        # for arms in "both", check if the picture-labelled region's bbox is
        # spatially close to the table's bbox (same physical location) --
        # would mean picture AND table coexist on the page (different regions,
        # e.g. a genuine picture next to a genuine table), vs the SAME region
        # appearing gated in one page-variant but tabled in another -- checked
        # via arms_gated XOR arms_tabled instead (cleaner signal: flips)
        same_region_coexist = []
        for (m, arm) in both:
            cands = cand_by_key.get((m, arm, did), [])
            tabs = table_by_key.get((m, arm, did), [])
            for c in cands:
                for t in tabs:
                    # t doesn't carry bbox in all_tables.json summary; skip IoU here,
                    # record co-occurrence only
                    same_region_coexist.append({"milestone": m, "arm": arm})

        paired_cases.append({
            "document_id": did,
            "arms_where_gated_as_picture": sorted(f"{m}/{a}" for m, a in arms_gated),
            "arms_where_reached_table_transformer": sorted(f"{m}/{a}" for m, a in arms_tabled),
            "arms_in_both_states_simultaneously": sorted(f"{m}/{a}" for m, a in both),
            "arms_ONLY_gated_never_tabled": sorted(f"{m}/{a}" for m, a in gated_only),
            "arms_ONLY_tabled_never_gated": sorted(f"{m}/{a}" for m, a in tabled_only),
            "interpretation": (
                "arms_in_both_states means the picture-labelled candidate and the "
                "real table coexist -- likely a DIFFERENT region on the page (e.g. a "
                "genuine picture next to the table) rather than the same region "
                "flipping label. arms_ONLY_gated vs arms_ONLY_tabled are the "
                "genuinely interesting flip cases: same document, gate outcome "
                "differs by arm/configuration."
            ),
        })

    payload = {
        "documents_with_both_states_anywhere": sorted(overlap_docs),
        "paired_cases": paired_cases,
    }
    Path("paired_gating_cases.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False))
    for pc in paired_cases:
        print(f"\n{pc['document_id']}")
        print(f"  gated-only arms:  {pc['arms_ONLY_gated_never_tabled']}")
        print(f"  tabled-only arms: {pc['arms_ONLY_tabled_never_gated']}")
        print(f"  both simultaneously: {pc['arms_in_both_states_simultaneously']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
