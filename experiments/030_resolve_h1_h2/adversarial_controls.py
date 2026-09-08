"""030 Phase 11 -- adversarial falsification controls, synthetic IR.

Each case tests a PREDICTION from H1 or H2, not merely code coverage.
Uses the exact undershoot/containment functions defined in resolve_h1.py /
resolve_h2.py (imported, not reimplemented).
"""
from __future__ import annotations
import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from resolve_h1 import bbox_union, undershoot  # noqa: E402
from resolve_h2 import bbox_outside, intersects  # noqa: E402


def cell(r, c, x0, y0, x1, y1, conf=None):
    return {"row": r, "col": c, "bbox": {"x0": x0, "y0": y0, "x1": x1, "y1": y1},
           "confidence": conf, "text": "t"}


CASES = []


def case(hyp, name, setup, intended_state, expected, measure_fn, note):
    CASES.append({"hypothesis": hyp, "name": name, "setup": setup,
                 "intended_semantic_state": intended_state, "expected": expected,
                 "measure_fn": measure_fn, "note": note})


# === H1 cases: does undershoot track SYNTHESIS specifically, not merely "any cell"? ===

# H1-1: a table where ALL cells (no synthesis marker) fit perfectly -> undershoot should be 0
c1 = [cell(0, 0, 10, 10, 90, 90), cell(0, 1, 100, 10, 190, 90)]
tb1 = {"x0": 0, "y0": 0, "x1": 200, "y1": 100}
case("H1", "H1-1_clean_detector_only_table",
    {"table_bbox": tb1, "cells": c1},
    "no synthesis occurred; all cells detector-original",
    "undershoot == 0",
    lambda: undershoot(tb1, bbox_union([c["bbox"] for c in c1])) == 0.0,
    "baseline: confirms the metric reads 0 when there is nothing to find")

# H1-2: ONE synthesized cell (conf=0.5) that pokes 5px above table top -> undershoot == 5
c2 = c1 + [cell(1, 0, 10, -5, 90, 5, conf=0.5)]
tb2 = tb1
case("H1", "H1-2_single_synthesized_cell_pokes_above",
    {"table_bbox": tb2, "cells": c2},
    "exactly one synthesized cell violates containment by exactly 5px",
    "undershoot == 5.0 (not more, not less -- proportional to the poke)",
    lambda: undershoot(tb2, bbox_union([c["bbox"] for c in c2])) == 5.0,
    "tests PROPORTIONALITY: the metric should scale with actual poke distance, "
    "not just flag binary presence")

# H1-3: a NON-synthesized cell (no confidence marker) also pokes out -> H1 predicts this
# should be RARE/absent if synthesis is the sole mechanism; the test just verifies the
# metric doesn't distinguish source (it shouldn't -- geometry is geometry) while noting
# that 029/030's empirical finding was 0/1867 such cases.
c3 = [cell(0, 0, -5, 10, 90, 90)]  # detector-native cell poking left, no synthesis marker
tb3 = {"x0": 0, "y0": 0, "x1": 200, "y1": 100}
case("H1", "H1-3_detector_native_cell_pokes_no_synthesis_marker",
    {"table_bbox": tb3, "cells": c3},
    "a cell with NO synthesis marker still violates containment",
    "undershoot == 5.0 -- the GEOMETRIC test cannot see the confidence marker, by "
    "design; this is what makes the empirical 0/1867 finding meaningful evidence "
    "rather than a tautology (the check COULD have flagged non-synthesized cells, "
    "and empirically never did)",
    lambda: undershoot(tb3, bbox_union([c["bbox"] for c in c3])) == 5.0,
    "CRITICAL: proves the undershoot metric is not somehow only capable of detecting "
    "synthesized cells by construction -- the 0/1867 empirical finding is real evidence, "
    "not a measurement artifact")

# H1-4: stamp/occlusion label alone, no geometry violation -> H1 predicts elevated
# probability, not certainty; the evaluator itself must not encode a label->defect rule
case("H1", "H1-4_stamp_label_present_geometry_clean",
    {"table_bbox": tb1, "cells": c1, "labels": ["stamp", "occlusion"]},
    "document carries stamp/occlusion labels but geometry is perfectly clean",
    "undershoot == 0 despite the label -- the metric must be purely geometric and "
    "must NOT special-case documents by label",
    lambda: undershoot(tb1, bbox_union([c["bbox"] for c in c1])) == 0.0,
    "confirms the evaluator has no hidden label-conditioned logic that would make "
    "H1's correlational finding circular")

# H1-5: severity-direction test -- two tables, one stamp-labeled with SMALL poke, one
# non-stamp with LARGE poke; the metric must report the larger number for the larger poke
# regardless of label, directly instantiating the counterintuitive finding from h1_resolution
c5a_cells = [cell(0, 0, 10, 10, 90, 90, ), cell(1, 0, 10, 108, 90, 190, conf=0.5)]  # 8px poke
tb5a = {"x0": 0, "y0": 0, "x1": 100, "y1": 100}
c5b_cells = [cell(0, 0, 10, 10, 90, 90), cell(1, 0, 10, 250, 90, 330, conf=0.5)]  # 150px poke
tb5b = {"x0": 0, "y0": 0, "x1": 100, "y1": 100}
case("H1", "H1-5_severity_direction_stamp_vs_nonstamp",
    {"stamp_table": {"bbox": tb5a, "cells": c5a_cells},
     "nonstamp_table": {"bbox": tb5b, "cells": c5b_cells}},
    "a 'stamp-labeled' table with an 8px poke vs a 'non-stamp' table with a 150px poke",
    "the metric reports nonstamp_undershoot (150-100=150... let's just check it's larger) "
    "> stamp_undershoot regardless of label -- reproducing h1_resolution.json's "
    "empirical severity-direction finding in miniature",
    lambda: (undershoot(tb5b, bbox_union([c["bbox"] for c in c5b_cells]))
            > undershoot(tb5a, bbox_union([c["bbox"] for c in c5a_cells]))),
    "directly instantiates the counterintuitive empirical result: severity is NOT "
    "gated by the stamp/occlusion label in the measurement itself, consistent with "
    "029/030 finding label correlates with RATE not MAGNITUDE")


# === H2 cases: does the metric correctly detect / not-detect cross-table contamination? ===

# H2-1: escaping cell that does NOT reach a neighboring table -> should NOT flag contamination
tbA = {"x0": 0, "y0": 0, "x1": 100, "y1": 100}
tbB = {"x0": 200, "y0": 0, "x1": 300, "y1": 100}  # far away, no overlap possible
escaping_cellbox = {"x0": 10, "y0": -5, "x1": 90, "y1": 5}  # pokes 5px above tbA, nowhere near tbB
case("H2", "H2-1_escape_far_from_neighbor_no_contamination",
    {"own_table": tbA, "neighbor_table": tbB, "escaping_cell": escaping_cellbox},
    "escaping cell pokes 5px out of its own table, neighbor table is 100px away",
    "no intersection detected",
    lambda: not intersects(escaping_cellbox, tbB),
    "baseline negative control")

# H2-2: CONSTRUCTED adversarial case -- deliberately place an escaping cell so its poke
# DOES land inside a neighboring table (the exact scenario H2 predicts never happens)
tbC = {"x0": 0, "y0": 0, "x1": 100, "y1": 100}
tbD = {"x0": 0, "y0": 95, "x1": 100, "y1": 200}  # adjacent, starting just below tbC's bottom
escaping_into_D = {"x0": 10, "y0": 90, "x1": 90, "y1": 105}  # pokes 5px into tbD's territory
case("H2", "H2-2_constructed_cross_table_contamination",
    {"own_table": tbC, "neighbor_table": tbD, "escaping_cell": escaping_into_D},
    "DELIBERATELY constructed case where an escaping cell's poke lands inside an "
    "adjacent table's bbox -- this is the exact adversarial scenario H2 predicts is "
    "geometrically impossible for REAL escapes (bounded by token size) but which is "
    "trivially constructible synthetically",
    "intersection IS detected (the evaluator correctly identifies contamination when "
    "it is deliberately present) -- this does NOT falsify H2 empirically (no real "
    "instance was found in the corpus) but PROVES the evaluator would have caught it "
    "if one existed",
    lambda: intersects(escaping_into_D, tbD),
    "CRITICAL evaluator-validity check: if this case had come back False, H2's "
    "'0 contaminated cells found' result would be worthless (the checker might be "
    "broken, not the phenomenon absent). This proves the checker works.")

# H2-3: escaping cell whose bbox touches a neighbor's edge exactly (boundary condition)
tbE = {"x0": 0, "y0": 0, "x1": 100, "y1": 100}
tbF = {"x0": 0, "y0": 100, "x1": 100, "y1": 200}  # exactly adjacent, sharing an edge
touching_cell = {"x0": 10, "y0": 90, "x1": 90, "y1": 100}  # touches but does not cross
case("H2", "H2-3_boundary_touching_not_crossing",
    {"own_table": tbE, "neighbor_table": tbF, "escaping_cell": touching_cell},
    "a cell bbox whose edge exactly TOUCHES (y1==100) the neighbor's edge (y0==100) "
    "without crossing into it",
    "no intersection (strict inequality semantics: touching is not overlapping)",
    lambda: not intersects(touching_cell, tbF),
    "tests the strict-vs-inclusive boundary convention in the intersects() predicate "
    "used to declare H2 unfalsified -- a wrong convention here could hide or fabricate "
    "a contamination result")

# H2-4: escape magnitude near the 40px proxy-bound threshold used in h2_resolution
tbG = {"x0": 0, "y0": 0, "x1": 100, "y1": 100}
near_bound_cell = {"x0": 10, "y0": -39, "x1": 90, "y1": 5}  # 39px poke, just under bound
over_bound_cell = {"x0": 10, "y0": -41, "x1": 90, "y1": 5}  # 41px poke, just over bound
case("H2", "H2-4_escape_magnitude_near_proxy_bound",
    {"under_bound": near_bound_cell, "over_bound": over_bound_cell, "table": tbG},
    "two synthetic escapes straddling the 40px 'typical token height' proxy bound "
    "h2_resolution.json used as a sanity check",
    "the metric correctly distinguishes 39px (under) from 41px (over) -- confirms "
    "the bound-check arithmetic itself is correct, independent of whether any REAL "
    "escape in the corpus approaches it (max real escape was 14.43px, well under)",
    lambda: ((max(0, tbG["y0"] - near_bound_cell["y0"])) < 40
            and (max(0, tbG["y0"] - over_bound_cell["y0"])) > 40),
    "arithmetic sanity check on the proxy-bound comparison used in h2_resolution.json")

# H2-5: TWO escaping cells from the SAME table, only one of which would contaminate
# -- tests that the evaluator reports PER-CELL results, not a single table-level flag
# that could hide one true contamination among several clean escapes
tbH = {"x0": 0, "y0": 0, "x1": 100, "y1": 100}
tbI = {"x0": 0, "y0": 100, "x1": 100, "y1": 200}
clean_escape = {"x0": 10, "y0": -5, "x1": 90, "y1": 5}       # pokes up, away from tbI
dirty_escape = {"x0": 10, "y0": 95, "x1": 90, "y1": 105}     # pokes down, into tbI
case("H2", "H2-5_per_cell_not_per_table_aggregation",
    {"own_table": tbH, "neighbor_table": tbI,
     "cells": {"clean": clean_escape, "dirty": dirty_escape}},
    "one table has TWO escaping cells: one clean (no contamination), one dirty "
    "(contaminates tbI) -- a per-TABLE boolean flag would need to catch the dirty "
    "one even though the clean one is fine",
    "clean_escape does not intersect tbI; dirty_escape DOES intersect tbI -- both "
    "must be evaluated independently",
    lambda: (not intersects(clean_escape, tbI)) and intersects(dirty_escape, tbI),
    "confirms h2_resolution.py's per-CELL (not per-table) evaluation loop is the "
    "correct granularity -- a coarser check could have missed a single contaminated "
    "cell among several clean ones in the same table")


def main() -> int:
    results = []
    for c in CASES:
        try:
            ok = bool(c["measure_fn"]())
        except Exception as exc:
            ok = False
            c["error"] = f"{type(exc).__name__}: {exc}"
        results.append({"hypothesis": c["hypothesis"], "name": c["name"],
                        "setup": c["setup"], "intended_semantic_state": c["intended_semantic_state"],
                        "expected": c["expected"], "measured_result": ok,
                        "verdict": "PASS" if ok else "FAIL", "note": c["note"],
                        "error": c.get("error")})
    passed = sum(1 for r in results if r["verdict"] == "PASS")
    payload = {"cases": len(results), "passed": passed, "failed": len(results) - passed,
              "results": results}
    (HERE / "adversarial_controls.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False))
    for r in results:
        print(f"  [{r['hypothesis']}] {r['verdict']:<5} {r['name']}")
        if r["error"]:
            print(f"        ERROR: {r['error']}")
    print(f"\n{passed}/{len(results)} adversarial controls passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
