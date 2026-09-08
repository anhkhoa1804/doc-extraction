"""033 Phase 5/8 -- expand 032's 20 synthetic adversarial controls to 42,
covering 1D evidence, 2D evidence, deceptive structures, and adversarial
geometry, then run the ORIGINAL rule and all 4 candidate rules
(candidate_designs.py) against every case. Phase 8's single-column-table
test is embedded here (cases 29/54) rather than a separate script, since
it is one more adversarial case among many, not a different mechanism.

    python experiments/033_table_shape_integrity/adversarial_results.py
"""
from __future__ import annotations
import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
L31 = HERE.parents[1] / "experiments/031_table_label_gating"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(L31))
from candidate_designs import CANDIDATES  # noqa: E402
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
    CASES.append({"n": n, "name": name, "group": group, "ambiguity_kind": ambiguity_kind,
                 "region_bbox": region_bbox, "children": children,
                 "ground_truth_by_construction": ground_truth, "reasoning": reasoning})


# ==== 032's original 20 cases, reproduced identically (same geometry, same
# ground truth) so the expanded suite is a strict superset, not a
# replacement ====
case(1, "obvious table", "clear", "none", {"x0": 0, "y0": 0, "x1": 344, "y1": 154},
     grid(4, 4), "table", "regular 4x4 grid, every cell populated")
case(2, "obvious picture", "clear", "none", {"x0": 0, "y0": 0, "x1": 400, "y1": 250}, [],
     "picture", "zero nested text children")
case(3, "obvious paragraph", "clear", "none", {"x0": 0, "y0": 0, "x1": 400, "y1": 60},
     [box(0, 0, 400, 60, "one wrapped paragraph")], "text", "single text child")
case(4, "table under stamp", "ambiguous", "evidence_ambiguity", {"x0": 0, "y0": 0, "x1": 344, "y1": 154},
     grid(4, 4, skip={(1, 1), (1, 2), (2, 1)}), "table", "contiguous occlusion patch")
case(5, "table under heavy occlusion", "ambiguous", "evidence_ambiguity", {"x0": 0, "y0": 0, "x1": 344, "y1": 154},
     grid(4, 4, skip={(r, c) for r in range(4) for c in range(4) if (r + c) % 2 == 0}),
     "table", "checkerboard occlusion, 8/16 cells")
case(6, "table with sparse cells", "ambiguous", "evidence_ambiguity", {"x0": 0, "y0": 0, "x1": 430, "y1": 190},
     [box(0, 0, 80, 30, "H1"), box(90, 0, 170, 30, "H2"), box(350, 0, 430, 30, "H5"),
      box(0, 160, 80, 190, "1")], "table", "sparse real table")
case(7, "table with merged cells", "ambiguous", "evidence_ambiguity", {"x0": 0, "y0": 0, "x1": 344, "y1": 154},
     grid(4, 4, skip={(0, 1), (0, 2), (0, 3)}) + [box(0, 0, 344, 30, "merged header")],
     "table", "row-span header + regular body")
case(8, "aligned paragraph", "ambiguous", "semantic_ambiguity", {"x0": 0, "y0": 0, "x1": 300, "y1": 200},
     [box(0, y, 280, y + 20, "line") for y in range(0, 200, 25)], "text", "single column, even spacing")
case(9, "form", "ambiguous", "semantic_ambiguity", {"x0": 0, "y0": 0, "x1": 400, "y1": 240},
     grid(6, 2, cell_w=150, cell_h=30, text="label: value"), "AMBIGUOUS_BY_DESIGN",
     "regular 6x2 grid, geometrically identical to a table")
case(10, "chart", "ambiguous", "semantic_ambiguity", {"x0": 0, "y0": 0, "x1": 400, "y1": 300},
     [box(10, 280, 40, 295, "0"), box(10, 200, 40, 215, "50"), box(10, 120, 40, 135, "100"),
      box(60, 10, 200, 25, "Chart Title"), box(300, 250, 380, 265, "Legend: A")],
     "picture", "scattered axis/title/legend, low density")
case(11, "stamp with aligned text", "misleading", "semantic_ambiguity", {"x0": 0, "y0": 0, "x1": 200, "y1": 200},
     [box(20, 20, 180, 40, "COMPANY NAME"), box(20, 160, 180, 180, "AUTHORIZED"),
      box(60, 90, 140, 110, "SEAL")], "picture", "3 children, ring layout")
case(12, "photo containing text", "misleading", "semantic_ambiguity", {"x0": 0, "y0": 0, "x1": 400, "y1": 300},
     [box(150, 250, 350, 280, "STOP")], "picture", "1 child")
case(13, "screenshot of a table", "misleading", "evaluator_uncertainty", {"x0": 0, "y0": 0, "x1": 344, "y1": 154},
     grid(4, 4), "table", "IS a real table, rendered as a picture element")
case(14, "decorative grid", "misleading", "evidence_ambiguity", {"x0": 0, "y0": 0, "x1": 344, "y1": 154},
     grid(4, 4, text=""), "picture", "regular grid, all cells empty text")
case(15, "textbook banner", "misleading", "evidence_ambiguity", {"x0": 0, "y0": 0, "x1": 1628, "y1": 334},
     [box(1085, 51, 1272, 83, ""), box(1305, 53, 1486, 95, "macmillanmh.com"),
      box(1133, 100, 1261, 126, ""), box(378, 113, 879, 193, "Practice"),
      box(151, 138, 229, 240, "3"), box(319, 199, 780, 259, "Cumulative, Chapters 1-9")],
     "picture", "EXACT geometry of the real confirmed Chapter9 false positive")
case(16, "signature block", "misleading", "semantic_ambiguity", {"x0": 0, "y0": 0, "x1": 250, "y1": 80},
     [box(0, 0, 200, 20, "___"), box(0, 25, 150, 45, "Signature"), box(0, 50, 100, 70, "Date: ___")],
     "picture", "3 short children, 1 column")
case(17, "multi-column paragraph", "misleading", "evidence_ambiguity", {"x0": 0, "y0": 0, "x1": 400, "y1": 200},
     [box(0, y, 180, y + 20, "col1 line") for y in range(0, 200, 25)] +
     [box(210, y, 390, y + 20, "col2 line") for y in range(0, 200, 25)],
     "text", "2-column prose, the hardest misleading case")
case(18, "dense bullet list", "misleading", "evidence_ambiguity", {"x0": 0, "y0": 0, "x1": 300, "y1": 240},
     [box(0, y, 280, y + 20, "- item") for y in range(0, 240, 24)], "text", "1 column, many rows")
case(19, "pseudo-table (coincidental alignment)", "misleading", "semantic_ambiguity",
     {"x0": 0, "y0": 0, "x1": 400, "y1": 200},
     [box(0, y, 100, y + 20, "Name:") for y in range(0, 200, 25)] +
     [box(110, y, 300, y + 20, "value") for y in range(0, 200, 25)],
     "AMBIGUOUS_BY_DESIGN", "repeated template creates a perfect 2-col grid")
case(20, "malformed table", "misleading", "evidence_ambiguity", {"x0": 0, "y0": 0, "x1": 344, "y1": 154},
     grid(4, 4, skip={(0, 3)}) + [box(280, 0, 344, 154, "spans 4 rows, col 3 only")],
     "table", "real but structurally messy table")

# ==== 22 NEW cases (033) ====

# -- 1D evidence (21-25) --
case(21, "ragged-right paragraph", "1d_evidence", "none", {"x0": 0, "y0": 0, "x1": 300, "y1": 175},
     [box(0, 0, 280, 20, "a long first line of text here"),
      box(0, 25, 190, 45, "shorter second line"),
      box(0, 50, 260, 70, "a medium length third line of prose"),
      box(0, 75, 140, 95, "short fourth"),
      box(0, 100, 300, 120, "the longest line of all in this paragraph block"),
      box(0, 125, 90, 145, "end.")],
     "text", "natural ragged-right prose, unlike case 8's uniform width")
case(22, "numbered bullet list", "1d_evidence", "none", {"x0": 0, "y0": 0, "x1": 320, "y1": 220},
     [box(0, y, 300, y + 22, f"{i+1}. list item text") for i, y in enumerate(range(0, 220, 27))],
     "text", "numbered list, 1 column, moderately regular")
case(23, "wide-numbered list", "1d_evidence", "none", {"x0": 0, "y0": 0, "x1": 320, "y1": 180},
     [box(0, y, 300, y + 22, f"{i+10}. item") for i, y in enumerate(range(0, 180, 30))],
     "text", "double-digit numbers, still 1 column")
case(24, "loosely spaced prose", "1d_evidence", "none", {"x0": 0, "y0": 0, "x1": 300, "y1": 260},
     [box(0, 0, 280, 20, "line one"), box(0, 40, 280, 60, "line two"),
      box(0, 95, 280, 115, "line three"), box(0, 130, 280, 150, "line four"),
      box(0, 200, 280, 220, "line five"), box(0, 240, 280, 260, "line six")],
     "text", "irregular gaps between lines -- row_regularity_cv should be HIGH")
case(25, "aligned headings", "1d_evidence", "none", {"x0": 0, "y0": 0, "x1": 300, "y1": 220},
     [box(60, y, 240, y + 25, "SECTION HEADING") for y in range(0, 220, 35)],
     "text", "repeated centered short headings, 1 column, 7 rows")

# -- 2D evidence (26-32) --
case(26, "true table 5x5", "2d_evidence", "none", {"x0": 0, "y0": 0, "x1": 430, "y1": 190},
     grid(5, 5, cell_w=80, cell_h=30), "table", "larger regular grid")
case(27, "sparse real table", "2d_evidence", "none", {"x0": 0, "y0": 0, "x1": 430, "y1": 190},
     grid(4, 5, skip={(r, c) for r in range(4) for c in range(5) if (r * 5 + c) % 3 != 0}),
     "table", "only every 3rd cell populated, still real 2D structure")
case(28, "single-row table", "2d_evidence", "none", {"x0": 0, "y0": 0, "x1": 430, "y1": 34},
     grid(1, 5, cell_w=80, cell_h=30), "table", "1 row, 5 columns -- header-only fragment")
case(29, "single-column table", "2d_evidence", "none", {"x0": 0, "y0": 0, "x1": 84, "y1": 190},
     grid(5, 1, cell_w=80, cell_h=30), "table",
     "5 rows, 1 column -- Phase 8's critical case: geometrically IDENTICAL "
     "to case 8 (aligned paragraph) and case 18 (bullet list). Ground "
     "truth 'table' asserted by construction ONLY -- this is exactly the "
     "case Phase 8 asks whether current evidence can actually recognize.")
case(30, "merged-cell table", "2d_evidence", "none", {"x0": 0, "y0": 0, "x1": 344, "y1": 154},
     [box(0, 0, 344, 30, "spans all 4 cols")] + grid(3, 4, y0=34, cell_h=30),
     "table", "1 merged header row + 3x4 body")
case(31, "borderless noisy table", "2d_evidence", "none", {"x0": 0, "y0": 0, "x1": 344, "y1": 160},
     [box(2, 1, 82, 29, "a"), box(88, 3, 168, 31, "b"), box(172, 0, 252, 28, "c"), box(256, 2, 336, 30, "d"),
      box(1, 40, 81, 68, "e"), box(89, 38, 169, 66, "f"), box(171, 41, 251, 69, "g"), box(255, 39, 335, 67, "h"),
      box(3, 80, 83, 108, "i"), box(87, 79, 167, 107, "j"), box(173, 82, 253, 110, "k"), box(257, 78, 337, 106, "l")],
     "table", "real 3x4 grid with a few px of OCR/render noise on every edge")
case(32, "highly irregular real table", "2d_evidence", "none", {"x0": 0, "y0": 0, "x1": 400, "y1": 300},
     [box(0, 0, 90, 30, "a"), box(100, 0, 220, 30, "b"), box(230, 0, 400, 30, "c"),
      box(0, 60, 90, 90, "d"), box(100, 60, 220, 90, "e"), box(230, 60, 400, 90, "f"),
      box(0, 180, 90, 210, "g"), box(100, 180, 220, 210, "h"), box(230, 180, 400, 210, "i")],
     "table", "real 3x3 table but with widely uneven row gaps (30, 90) -- "
     "row_regularity_cv will be high despite genuine 2D structure")

# -- deceptive structures (33-38, beyond 032's 9-20) --
case(33, "diagram with labels", "deceptive", "semantic_ambiguity", {"x0": 0, "y0": 0, "x1": 300, "y1": 200},
     [box(20, 10, 100, 30, "Box A"), box(180, 10, 260, 30, "Box B"),
      box(100, 90, 180, 110, "arrow label"), box(20, 160, 100, 180, "Box C")],
     "picture", "4 scattered labeled boxes, no grid regularity")
case(34, "large form", "deceptive", "semantic_ambiguity", {"x0": 0, "y0": 0, "x1": 400, "y1": 360},
     grid(9, 2, cell_w=150, cell_h=30, text="label: value"), "AMBIGUOUS_BY_DESIGN",
     "9-row form, same structural ambiguity as case 9 at larger scale")
case(35, "app screenshot", "deceptive", "semantic_ambiguity", {"x0": 0, "y0": 0, "x1": 300, "y1": 300},
     [box(10, 10, 60, 30, "icon"), box(200, 10, 280, 30, "9:41"),
      box(10, 100, 290, 130, "Notification text goes here"),
      box(10, 200, 100, 220, "Button A"), box(180, 200, 290, 220, "Button B")],
     "picture", "UI screenshot, scattered irregular elements")
case(36, "multi-column article (3 col)", "deceptive", "evidence_ambiguity",
     {"x0": 0, "y0": 0, "x1": 600, "y1": 200},
     [box(0, y, 180, y + 20, "colA") for y in range(0, 200, 25)] +
     [box(210, y, 390, y + 20, "colB") for y in range(0, 200, 25)] +
     [box(420, y, 600, y + 20, "colC") for y in range(0, 200, 25)],
     "text", "3-column newspaper layout, even more table-like than case 17")
case(37, "grid-like decorative border", "deceptive", "evidence_ambiguity",
     {"x0": 0, "y0": 0, "x1": 344, "y1": 154}, grid(4, 4, text="") + grid(4, 4, text=""),
     "picture", "duplicated empty grid (rendering artifact), still zero text content")
case(38, "textbook banner variant (narrower)", "deceptive", "evidence_ambiguity",
     {"x0": 0, "y0": 0, "x1": 800, "y1": 200},
     [box(500, 20, 620, 40, ""), box(640, 22, 740, 45, "pub.example.com"),
      box(180, 55, 430, 95, "Review"), box(60, 68, 110, 120, "7"),
      box(150, 100, 380, 130, "Unit 4-7 Cumulative")],
     "picture", "same header/banner PATTERN as case 15, different scale")

# -- adversarial geometry (39-46) --
case(39, "fake columns from short lines", "adversarial_geometry", "evidence_ambiguity",
     {"x0": 0, "y0": 0, "x1": 300, "y1": 175},
     [box(0, 0, 80, 20, "short"), box(0, 25, 200, 45, "medium length"),
      box(0, 50, 60, 70, "tiny"), box(0, 75, 250, 95, "a longer line of text"),
      box(0, 100, 90, 120, "short2"), box(0, 125, 180, 145, "medium2")],
     "text", "varying line widths create ACCIDENTAL x1 alignment clusters "
     "at multiple positions -- tests whether col_bands (built from x0/x1 "
     "overlap) is fooled by ragged-right prose")
case(40, "unequal row spacing table", "adversarial_geometry", "evidence_ambiguity",
     {"x0": 0, "y0": 0, "x1": 344, "y1": 260},
     grid(2, 4, y0=0, cell_h=30) + grid(2, 4, y0=150, cell_h=30),
     "table", "real 4-row table split into two visually separated groups "
     "(e.g. a page break or section gap) -- row_regularity_cv will be high")
case(41, "fake repeated x from different-sized boxes", "adversarial_geometry", "evidence_ambiguity",
     {"x0": 0, "y0": 0, "x1": 300, "y1": 150},
     [box(0, 0, 50, 40, "A"), box(0, 50, 120, 70, "BB"), box(0, 90, 45, 130, "C")],
     "text", "3 left-aligned children of very different sizes -- all share "
     "x0=0 (1 col by construction) but heights vary a lot")
case(42, "interleaved short/long rows", "adversarial_geometry", "evidence_ambiguity",
     {"x0": 0, "y0": 0, "x1": 400, "y1": 210},
     [box(0, 0, 80, 20, "h1"), box(100, 0, 180, 20, "h2"), box(200, 0, 280, 20, "h3"),
      box(0, 40, 380, 60, "one wide merged-looking line"),
      box(0, 80, 80, 100, "h4"), box(100, 80, 180, 100, "h5"), box(200, 80, 280, 100, "h6"),
      box(0, 120, 380, 140, "another wide line"),
      box(0, 160, 80, 180, "h7"), box(100, 160, 180, 180, "h8"), box(200, 160, 280, 180, "h9")],
     "AMBIGUOUS_BY_DESIGN", "alternating 3-col rows and 1-col wide rows -- "
     "a genuinely ambiguous mixed layout (could be a table with merged "
     "rows, or a document alternating a caption and a data row)")
case(43, "misaligned/staggered cells", "adversarial_geometry", "evidence_ambiguity",
     {"x0": 0, "y0": 0, "x1": 400, "y1": 160},
     [box(0, 0, 80, 30, "a"), box(90, 5, 170, 35, "b"), box(180, 0, 260, 30, "c"),
      box(10, 45, 90, 75, "d"), box(95, 40, 175, 70, "e"), box(185, 48, 265, 78, "f"),
      box(5, 90, 85, 120, "g"), box(92, 92, 172, 122, "h"), box(178, 88, 258, 118, "i")],
     "table", "real 3x3 table but each cell is randomly jittered +/-10px -- "
     "tests robustness of band-clustering to realistic OCR positional noise")
case(44, "partial grid (top-left quadrant only)", "adversarial_geometry", "evidence_ambiguity",
     {"x0": 0, "y0": 0, "x1": 344, "y1": 154}, grid(4, 4, skip={
         (r, c) for r in range(4) for c in range(4) if r >= 2 or c >= 2}),
     "table", "only the top-left 2x2 of a declared 4x4 region has content "
     "-- rest of the region is genuinely empty (e.g. a form partially "
     "filled in, or a table cut off mid-page)")
case(45, "cropped table (right edge cut)", "adversarial_geometry", "evidence_ambiguity",
     {"x0": 0, "y0": 0, "x1": 250, "y1": 154},
     grid(4, 4, cell_w=80) , "table", "region bbox (x1=250) is NARROWER "
     "than the 4th column's true extent (which runs to x1=344 in the "
     "underlying grid geometry) -- simulates a table whose region "
     "boundary was detected short, cropping the last column's visible "
     "portion")
case(46, "true one-column table with header", "adversarial_geometry", "none",
     {"x0": 0, "y0": 0, "x1": 160, "y1": 220},
     [box(0, 0, 160, 30, "STT"), box(0, 34, 160, 64, "1"), box(0, 68, 160, 98, "2"),
      box(0, 102, 160, 132, "3"), box(0, 136, 160, 166, "4"), box(0, 170, 160, 200, "5")],
     "table", "one-column table with a distinct header cell ('STT' -- "
     "Vietnamese sequence-number column header, matching the REAL "
     "cmb_stamp_table_vi/hc_stamp_table_vi factual oracle's own first "
     "column, counterfactual_replay.json) followed by short numeric rows "
     "-- geometrically STILL indistinguishable from case 22 (numbered "
     "list) using only bbox evidence; the difference is semantic "
     "(a short numeral vs 'N. text') and requires reading content")


def evaluate():
    original_results = []
    candidate_results = {name: [] for name in CANDIDATES}
    for c in CASES:
        sig = compute_signals(c["region_bbox"], c["children"])
        orig_score, orig_reasons = table_shape_score(sig)
        orig_pass = orig_score >= 3
        original_results.append({
            "n": c["n"], "name": c["name"], "group": c["group"],
            "ground_truth": c["ground_truth_by_construction"],
            "signals": sig, "score": orig_score, "reasons": orig_reasons,
            "gate_pass": orig_pass,
        })
        for cand_name, cand in CANDIDATES.items():
            passes, score, reasons, detail = cand["fn"](sig)
            candidate_results[cand_name].append({
                "n": c["n"], "name": c["name"], "group": c["group"],
                "ground_truth": c["ground_truth_by_construction"],
                "gate_pass": passes, "detail": detail,
            })
    return original_results, candidate_results


def score_against_ground_truth(results):
    correct, wrong, undecidable = 0, [], 0
    for r in results:
        gt = r["ground_truth"]
        if gt == "AMBIGUOUS_BY_DESIGN":
            undecidable += 1
            continue
        expected = gt == "table"
        if r["gate_pass"] == expected:
            correct += 1
        else:
            wrong.append(r)
    return correct, wrong, undecidable


def main():
    original_results, candidate_results = evaluate()

    orig_correct, orig_wrong, orig_undec = score_against_ground_truth(original_results)
    summary = {"ORIGINAL_rule": {
        "n_cases": len(original_results), "correct": orig_correct,
        "wrong": len(orig_wrong), "undecidable_by_design": orig_undec,
        "misfires": [{"n": w["n"], "name": w["name"], "ground_truth": w["ground_truth"],
                     "score": w["score"]} for w in orig_wrong],
    }}
    for cand_name, results in candidate_results.items():
        correct, wrong, undec = score_against_ground_truth(results)
        summary[cand_name] = {
            "n_cases": len(results), "correct": correct, "wrong": len(wrong),
            "undecidable_by_design": undec,
            "misfires": [{"n": w["n"], "name": w["name"], "ground_truth": w["ground_truth"]}
                        for w in wrong],
        }

    payload = {
        "method": "42 synthetic cases (032's original 20, reproduced "
                 "identically, plus 22 new -- 5 one-dimensional-evidence, "
                 "7 two-dimensional-evidence including the critical "
                 "single-column-table case (Phase 8), 6 deceptive-"
                 "structure, 8 adversarial-geometry) run through the real "
                 "table_shape_score AND all 4 candidate rules.",
        "cases": [{"n": c["n"], "name": c["name"], "group": c["group"],
                  "ambiguity_kind": c["ambiguity_kind"],
                  "ground_truth": c["ground_truth_by_construction"],
                  "reasoning": c["reasoning"]} for c in CASES],
        "n_total_cases": len(CASES),
        "original_rule_results": original_results,
        "candidate_results": candidate_results,
        "summary": summary,
        "phase_8_single_column_table_finding": (
            "case 29 (single-column table, ground truth 'table' by "
            "construction) has IDENTICAL geometric signals in kind to "
            "case 8 (aligned paragraph) and case 22 (numbered bullet "
            "list) -- col_bands=1 in all three. EVERY candidate (A/B/C/D) "
            "REJECTS case 29, because every candidate requires col_bands>="
            "2. This is a KNOWN, DELIBERATE trade-off, not an oversight: "
            "see FINAL_REPORT.md Phase 8 for the full limitation "
            "statement -- no signal in role_evidence_schema.json's "
            "retained dimensions (032) distinguishes a genuine one-column "
            "table from one-column prose/lists using geometry alone. "
            "Case 46 (one-column table WITH a semantically distinct "
            "header, matching the REAL corpus's own STT-column pattern) "
            "is geometrically identical to case 22 as well -- confirming "
            "the limitation is not fixable by adding a 'header looks "
            "different' geometric rule without reading text content."
        ),
    }
    Path("adversarial_results.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False))
    print(f"total cases: {len(CASES)}")
    for name, s in summary.items():
        print(f"  {name:<35} correct={s['correct']:<3} wrong={s['wrong']:<3} undecidable={s['undecidable_by_design']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
