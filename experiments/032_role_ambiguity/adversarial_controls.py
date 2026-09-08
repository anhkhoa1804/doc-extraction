"""032 Phase 12 -- 20 synthetic adversarial role cases.

Explicitly SYNTHETIC -- unlike role_ambiguity_population.json (real
corpus data, no invented ground truth), every case here is constructed
geometry with ground truth defined BY CONSTRUCTION, run through the REAL
table_shape_score/compute_signals functions (031's actual code, not a
reimplementation). Each case is tagged with the KIND of ambiguity it
tests:

  evidence_ambiguity  -- the score sits genuinely near the decision
                        boundary for this specific evidence vector
  semantic_ambiguity  -- a reasonable human could classify this case
                        either way even with full information
  evaluator_uncertainty -- THIS SCRIPT's own ground-truth assignment is
                        the uncertain part, not the domain fact

    python experiments/032_role_ambiguity/adversarial_controls.py
"""
from __future__ import annotations
import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
L31 = HERE.parents[1] / "experiments/031_table_label_gating"
sys.path.insert(0, str(L31))
from table_shape_probe import compute_signals, table_shape_score  # noqa: E402


def box(x0, y0, x1, y1, text=""):
    return {"bbox": {"x0": x0, "y0": y0, "x1": x1, "y1": y1}, "text": text}


def grid(n_rows, n_cols, x0=0, y0=0, cell_w=80, cell_h=30, gap=4, text="x", skip=()):
    children = []
    for r in range(n_rows):
        for c in range(n_cols):
            if (r, c) in skip:
                continue
            bx0 = x0 + c * (cell_w + gap)
            by0 = y0 + r * (cell_h + gap)
            children.append(box(bx0, by0, bx0 + cell_w, by0 + cell_h, text))
    return children


CASES = []


def case(n, name, group, ambiguity_kind, region_bbox, children, ground_truth, reasoning):
    CASES.append({
        "n": n, "name": name, "group": group, "ambiguity_kind": ambiguity_kind,
        "region_bbox": region_bbox, "children": children,
        "ground_truth_by_construction": ground_truth, "reasoning": reasoning,
    })


# --- CLEAR (1-3) ---
case(1, "obvious table", "clear", "none",
     {"x0": 0, "y0": 0, "x1": 344, "y1": 154}, grid(4, 4),
     "table", "regular 4x4 grid, every cell populated, no occlusion")

case(2, "obvious picture", "clear", "none",
     {"x0": 0, "y0": 0, "x1": 400, "y1": 250}, [],
     "picture", "zero nested text children -- a genuine photo/graphic")

case(3, "obvious paragraph", "clear", "none",
     {"x0": 0, "y0": 0, "x1": 400, "y1": 60}, [box(0, 0, 400, 60, "one wrapped paragraph")],
     "text", "single text child, no internal structure")


# --- AMBIGUOUS (4-10) ---
case(4, "table under stamp", "ambiguous", "evidence_ambiguity",
     {"x0": 0, "y0": 0, "x1": 344, "y1": 154},
     grid(4, 4, skip={(1, 1), (1, 2), (2, 1)}),  # a stamp occludes a 2x2-ish patch
     "table", "regular grid with a contiguous missing patch -- occlusion, "
     "not a different structure; a human recognizes this as a partially "
     "occluded table")

case(5, "table under heavy occlusion", "ambiguous", "evidence_ambiguity",
     {"x0": 0, "y0": 0, "x1": 344, "y1": 154},
     grid(4, 4, skip={(r, c) for r in range(4) for c in range(4) if (r + c) % 2 == 0}),
     "table", "checkerboard-pattern occlusion leaves only 8/16 cells -- "
     "genuinely marginal: row/col band counts may still register, but "
     "children_per_row_band drops sharply. Tests whether the score "
     "degrades gracefully or falls off a cliff.")

case(6, "table with sparse cells", "ambiguous", "evidence_ambiguity",
     {"x0": 0, "y0": 0, "x1": 430, "y1": 190},
     [box(0, 0, 80, 30, "H1"), box(90, 0, 170, 30, "H2"),
      box(350, 0, 430, 30, "H5"), box(0, 160, 80, 190, "1")],
     "table", "a real but very sparse table (mostly-empty cells) -- few "
     "children relative to declared shape; tests whether low child count "
     "alone suppresses recovery of a genuinely sparse table")

case(7, "table with merged cells", "ambiguous", "evidence_ambiguity",
     {"x0": 0, "y0": 0, "x1": 344, "y1": 154},
     grid(4, 4, skip={(0, 1), (0, 2), (0, 3)}) + [box(0, 0, 344, 30, "merged header")],
     "table", "row 0 is one wide merged header cell (col-span), rows 1-3 "
     "are a normal 4-col grid -- children_per_row_band varies sharply by "
     "row, which the CURRENT rank-based reconstruction (031 controlled_"
     "intervention.py) is known to handle poorly (cols_horizontally_"
     "coherent failures, 73/79 in 031's real population)")

case(8, "aligned paragraph", "ambiguous", "semantic_ambiguity",
     {"x0": 0, "y0": 0, "x1": 300, "y1": 200},
     [box(0, y, 280, y + 20, "line") for y in range(0, 200, 25)],
     "text", "justified prose wraps into short lines of similar width -- "
     "single column (col_bands=1), so table_shape_score's multi-column "
     "criterion should reject it, but a POORLY chosen column-band "
     "tolerance could conceivably misfire; ground truth is text by "
     "construction (only one 'column' of content exists)")

case(9, "form", "ambiguous", "semantic_ambiguity",
     {"x0": 0, "y0": 0, "x1": 400, "y1": 240},
     grid(6, 2, cell_w=150, cell_h=30, text="label: value"),
     "AMBIGUOUS_BY_DESIGN", "a label/value form is STRUCTURALLY "
     "indistinguishable from a genuine 2-column table using ONLY "
     "geometric evidence (regular 6x2 grid) -- this is exactly Phase 2's "
     "'form' category, and this repository's evidence model (031 Phase "
     "4-6, 032 role_evidence_schema.json) has NO signal that "
     "distinguishes 'table' from 'form' when both are regular grids. "
     "Reported as genuinely ambiguous, not resolved by fiat.")

case(10, "chart", "ambiguous", "semantic_ambiguity",
     {"x0": 0, "y0": 0, "x1": 400, "y1": 300},
     [box(10, 280, 40, 295, "0"), box(10, 200, 40, 215, "50"), box(10, 120, 40, 135, "100"),
      box(60, 10, 200, 25, "Chart Title"), box(300, 250, 380, 265, "Legend: A")],
     "picture", "axis labels + title + legend are scattered, LOW density, "
     "irregular spacing -- geometrically closer to the confirmed-negative "
     "population (table_shape_probe.json) than to the confirmed-table "
     "population; ground truth: chart, not table, by construction")


# --- MISLEADING (11-20) ---
case(11, "stamp with aligned text", "misleading", "semantic_ambiguity",
     {"x0": 0, "y0": 0, "x1": 200, "y1": 200},
     [box(20, 20, 180, 40, "COMPANY NAME"), box(20, 160, 180, 180, "AUTHORIZED"),
      box(60, 90, 140, 110, "SEAL")],
     "picture", "circular/ring text around a seal graphic -- only 3 "
     "children, row_bands likely <2 given the ring layout -- should score "
     "low; ground truth picture")

case(12, "photo containing text", "misleading", "semantic_ambiguity",
     {"x0": 0, "y0": 0, "x1": 400, "y1": 300},
     [box(150, 250, 350, 280, "STOP")],
     "picture", "a photograph with one embedded sign/label -- 1 child, "
     "should score 0 (below AMBIGUOUS threshold in Phase 2's own scheme)")

case(13, "screenshot of a table", "misleading", "evaluator_uncertainty",
     {"x0": 0, "y0": 0, "x1": 344, "y1": 154}, grid(4, 4),
     "table", "a screenshot of a REAL table, rendered as a picture "
     "element by the detector, but structurally IS a genuine table -- "
     "identical geometry to case 1. Ground truth 'table' is NOT "
     "evaluator-uncertain semantically (it really is a table), but "
     "WOULD be uncertain for a real detector deciding picture-vs-table "
     "from pixels alone -- the uncertainty here is about the DETECTOR's "
     "task, not this script's labeling.")

case(14, "decorative grid", "misleading", "evidence_ambiguity",
     {"x0": 0, "y0": 0, "x1": 344, "y1": 154},
     grid(4, 4, text="") + [],  # regular grid, but every cell is empty text (pure lines/decoration)
     "picture", "a regular 4x4 grid of EMPTY boxes (decorative table-look "
     "border, no text content at all) -- geometrically identical to case "
     "1 (obvious table), text-content-empty. This is the sharpest test of "
     "whether text CONTENT (not just geometry) should gate recovery -- "
     "031's actual reconstruct_table() does not check text emptiness at "
     "all, so this case would score identically to a real table and "
     "produce an all-empty pseudo-table if fired on.")

case(15, "textbook banner", "misleading", "evidence_ambiguity",
     {"x0": 0, "y0": 0, "x1": 1628, "y1": 334},
     [box(1085, 51, 1272, 83, ""), box(1305, 53, 1486, 95, "macmillanmh.com"),
      box(1133, 100, 1261, 126, ""), box(378, 113, 879, 193, "Practice"),
      box(151, 138, 229, 240, "3"), box(319, 199, 780, 259, "Cumulative, Chapters 1-9")],
     "picture", "EXACT geometry of the real confirmed false positive "
     "(jiaocaineedrop_Chapter9.pdf_46 region 0, negative_controls.json) "
     "-- included here as a synthetic control reproducing a REAL "
     "confirmed case, not a hypothetical one")

case(16, "signature block", "misleading", "semantic_ambiguity",
     {"x0": 0, "y0": 0, "x1": 250, "y1": 80},
     [box(0, 0, 200, 20, "___________________"), box(0, 25, 150, 45, "Signature"),
      box(0, 50, 100, 70, "Date: ___")],
     "picture", "3 short children, 3 row bands, 1 column -- low "
     "children_per_row_band (1.0), should score low despite multi-row")

case(17, "multi-column paragraph", "misleading", "evidence_ambiguity",
     {"x0": 0, "y0": 0, "x1": 400, "y1": 200},
     [box(0, y, 180, y + 20, "col1 line") for y in range(0, 200, 25)] +
     [box(210, y, 390, y + 20, "col2 line") for y in range(0, 200, 25)],
     "text", "2 newspaper-style columns of prose -- col_bands=2, "
     "row_bands could register as high as the line count (8), "
     "children_per_row_band=2.0 -- this is GENUINELY the hardest "
     "misleading case: it can satisfy every criterion in "
     "table_shape_score (multi-row, multi-column, multiple children per "
     "row, regular spacing, high count) while being pure prose. "
     "Ground truth text by construction; flagged as the single most "
     "concerning case in this control set -- see FINAL_REPORT.")

case(18, "dense bullet list", "misleading", "evidence_ambiguity",
     {"x0": 0, "y0": 0, "x1": 300, "y1": 240},
     [box(0, y, 280, y + 20, "- item") for y in range(0, 240, 24)],
     "text", "single column, many rows -- col_bands=1 should reject it "
     "via the multi-column criterion")

case(19, "pseudo-table (coincidental alignment)", "misleading", "semantic_ambiguity",
     {"x0": 0, "y0": 0, "x1": 400, "y1": 200},
     [box(0, y, 100, y + 20, "Name:") for y in range(0, 200, 25)] +
     [box(110, y, 300, y + 20, "value") for y in range(0, 200, 25)],
     "AMBIGUOUS_BY_DESIGN", "repeated 'Label: value' lines align into a "
     "perfect 2-column grid purely because every line uses the same "
     "template -- geometrically IDENTICAL to case 9 (form). This is "
     "exactly the milestone's own named alternative explanation "
     "('nested text children happen to form approximately aligned "
     "blocks... that does NOT prove they are table cells', 031's Phase "
     "13 instruction) -- reported as ambiguous, not resolved.")

case(20, "malformed table", "misleading", "evidence_ambiguity",
     {"x0": 0, "y0": 0, "x1": 344, "y1": 154},
     grid(4, 4, skip={(0, 3)}) + [box(280, 0, 344, 154, "spans 4 rows, col 3 only")],
     "table", "a REAL table with inconsistent per-row cell counts "
     "(bad OCR fragmentation, not occlusion) -- structurally messy but "
     "genuinely a table; tests whether irregular-but-real tables score "
     "similarly to occluded-but-real tables (case 4/5) or get penalized "
     "differently")


def main():
    results = []
    for c in CASES:
        sig = compute_signals(c["region_bbox"], c["children"])
        score, reasons = table_shape_score(sig)
        results.append({
            **{k: c[k] for k in ("n", "name", "group", "ambiguity_kind",
                                 "ground_truth_by_construction", "reasoning")},
            "n_children": len(c["children"]),
            "computed_signals": sig,
            "table_shape_score": score,
            "score_reasons": reasons,
            "gate_passes_conservative_threshold_3": score >= 3,
            "gate_matches_ground_truth": (
                None if c["ground_truth_by_construction"] == "AMBIGUOUS_BY_DESIGN" else
                (score >= 3) == (c["ground_truth_by_construction"] == "table")
            ),
        })

    by_group = {}
    for r in results:
        by_group.setdefault(r["group"], {"n": 0, "gate_correct": 0, "gate_wrong": 0, "undecidable": 0})
        by_group[r["group"]]["n"] += 1
        if r["gate_matches_ground_truth"] is None:
            by_group[r["group"]]["undecidable"] += 1
        elif r["gate_matches_ground_truth"]:
            by_group[r["group"]]["gate_correct"] += 1
        else:
            by_group[r["group"]]["gate_wrong"] += 1

    misfires = [r for r in results if r["gate_matches_ground_truth"] is False]

    payload = {
        "method": "20 synthetic geometries run through the REAL "
                 "compute_signals/table_shape_score functions (031/"
                 "table_shape_probe.py, imported not reimplemented). "
                 "Ground truth is defined by construction and explicitly "
                 "marked AMBIGUOUS_BY_DESIGN for 2 cases where the milestone "
                 "brief's own instruction ('do not force a binary answer "
                 "where semantics are genuinely uncertain') applies.",
        "cases": results,
        "by_group": by_group,
        "gate_misfires": [{"n": r["n"], "name": r["name"], "group": r["group"],
                           "score": r["table_shape_score"],
                           "ground_truth": r["ground_truth_by_construction"]}
                         for r in misfires],
        "finding": (
            f"{len(misfires)} of {sum(1 for r in results if r['gate_matches_ground_truth'] is not None)} "
            f"decidable cases misfire against the current conservative "
            f"threshold (score>=3). The most important is case 17 "
            f"(multi-column paragraph): pure prose that satisfies every "
            f"criterion in table_shape_score. Cases 9 and 19 (form / "
            f"pseudo-table) are marked AMBIGUOUS_BY_DESIGN rather than "
            f"forced to a binary verdict, because this repository's "
            f"current evidence model genuinely cannot distinguish them "
            f"from a real table using only geometry -- this is not a "
            f"probe bug, it is a real limit of geometry-only evidence."
        ),
    }
    Path("adversarial_controls.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False))
    print(f"cases: {len(results)}")
    for g, s in by_group.items():
        print(f"  {g:<12} n={s['n']:<3} correct={s['gate_correct']:<3} "
              f"wrong={s['gate_wrong']:<3} undecidable={s['undecidable']}")
    print(f"\nmisfires: {[(m['n'], m['name']) for m in misfires]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
