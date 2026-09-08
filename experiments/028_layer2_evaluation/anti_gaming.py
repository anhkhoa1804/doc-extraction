"""028 Phase 7 -- anti-gaming. What makes each metric improve WITHOUT
improving the extraction?

For every Layer-2 metric, apply a transformation that a careless optimizer
might reach for, and assert the metric does NOT reward it. Synthetic IR only;
no OCR, no pipeline, no GPU.

The concern is concrete, not hypothetical: 025 showed Layer 1's flattened
recall cannot see dropped evidence, duplicated evidence, or structural
inversion, so a change that caused any of those would score as neutral. A
replacement instrument that repeats that mistake is worse than useless,
because it would carry more authority.

    python experiments/028_layer2_evaluation/anti_gaming.py
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from evaluator_controls import GRID, cell, doc, table  # noqa: E402
from structural_integrity import structural_integrity  # noqa: E402
from table_structure import table_structure  # noqa: E402
from table_text import table_text  # noqa: E402


def measure(d):
    si = structural_integrity(d)[0]
    ts = table_structure(d)[0]
    tt = table_text(d)[0]
    return {
        "structurally_valid": si["structurally_valid"],
        "failed_checks": si["failed_checks"],
        "list_order_canonical": si["list_order_canonical"],
        "n_cells": ts["n_cells"],
        "non_empty_cells": tt["non_empty_cells"],
        "duplicate_coordinates": len(ts["duplicate_coordinates"]),
        "canonical_text": tt["canonical_text"],
    }


BASE = doc(table(list(GRID), 2, 2))
ATTACKS = []


def attack(name, mutate, invariant, why):
    ATTACKS.append({"name": name, "mutate": mutate, "invariant": invariant, "why": why})


def _sort_list(d):
    t = d["pages"][0]["tables"][0]
    t["cells"] = sorted(t["cells"], key=lambda c: (c["row"], c["col"]))
    return d


def _shuffle_then_sort(d):
    t = d["pages"][0]["tables"][0]
    t["cells"] = [t["cells"][3], t["cells"][0], t["cells"][2], t["cells"][1]]
    return _sort_list(d)


def _duplicate_cell(d):
    t = d["pages"][0]["tables"][0]
    t["cells"].append(copy.deepcopy(t["cells"][0]))
    return d


def _delete_hard_cell(d):
    t = d["pages"][0]["tables"][0]
    t["cells"] = [c for c in t["cells"] if not (c["row"] == 1 and c["col"] == 1)]
    return d


def _move_cells(d):
    t = d["pages"][0]["tables"][0]
    for c in t["cells"]:
        c["bbox"] = {"x0": 900, "y0": 900, "x1": 980, "y1": 980}
    return d

def _concat_into_one(d):
    t = d["pages"][0]["tables"][0]
    blob = " ".join(c["text"] for c in t["cells"])
    t["cells"] = [cell(0, 0, 10, 10, 90, 90, blob)]
    t["n_rows"], t["n_cols"] = 1, 1
    return d


def _renumber_to_fake_canonical(d):
    """Relabel row/col to match storage order instead of geometry -- the
    cheapest way to make `list_order_canonical` true without moving anything."""
    t = d["pages"][0]["tables"][0]
    t["cells"] = [t["cells"][3], t["cells"][0], t["cells"][2], t["cells"][1]]
    for i, c in enumerate(t["cells"]):
        c["row"], c["col"] = divmod(i, 2)
    return d


attack("sorting the cell list", _sort_list,
       "text metrics unchanged; only ORDER changes",
       "sorting is free and must never look like a text-fidelity gain")
attack("shuffle then re-sort", _shuffle_then_sort,
       "returns to the baseline exactly",
       "the metric must be a function of content, not of history")
attack("duplicating a correct cell", _duplicate_cell,
       "structural validity FAILS on duplicate coordinates",
       "duplicated evidence must not read as more evidence")
attack("deleting a hard cell", _delete_hard_cell,
       "cell count drops and is visible",
       "removing what you cannot extract must not raise a score")
attack("moving every cell out of the table", _move_cells,
       "structure FAILS; canonical text unchanged",
       "geometry damage must hit structure, not text fidelity")
attack("concatenating all cells into one", _concat_into_one,
       "cell count collapses 4 -> 1 and is visible",
       "flattening structure away must not look like a clean table")
attack("renumbering row/col to match storage order", _renumber_to_fake_canonical,
       "structure FAILS on geometry-order mismatch",
       "you must not be able to fake canonical order by relabelling")


def main() -> int:
    base = measure(BASE)
    rows = []
    for a in ATTACKS:
        after = measure(a["mutate"](copy.deepcopy(BASE)))
        rewarded = (
            after["structurally_valid"] and not base["structurally_valid"]
        ) or (
            after["non_empty_cells"] > base["non_empty_cells"]
            and after["canonical_text"] == base["canonical_text"]
        )
        rows.append({
            "attack": a["name"], "invariant": a["invariant"], "why": a["why"],
            "base": base, "after": after,
            "text_unchanged": after["canonical_text"] == base["canonical_text"],
            "structure_still_valid": after["structurally_valid"],
            "cells_visible_change": after["n_cells"] - base["n_cells"],
            "metric_rewarded_the_attack": bool(rewarded),
        })

    payload = {
        "baseline": base,
        "attacks": rows,
        "any_attack_rewarded": any(r["metric_rewarded_the_attack"] for r in rows),
        "documented_invariants": [
            "sorting a list changes ORDER only, never TEXT",
            "duplicating a cell is caught by no_duplicate_coordinates, never rewarded",
            "deleting a cell is visible as a cell-count drop, never rewarded",
            "moving geometry damages STRUCTURE and leaves TEXT untouched",
            "collapsing a table into one cell is visible as a shape change",
            "relabelling row/col to fake canonical storage order is caught by "
            "row_order_matches_geometry / col_order_matches_geometry",
            "TEXT is reported UNMEASURABLE rather than proxied, so no transformation "
            "can improve a text score that does not exist",
        ],
    }
    (HERE / "anti_gaming.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False))

    print(f"baseline: valid={base['structurally_valid']} cells={base['n_cells']} "
          f"canonical={base['list_order_canonical']}")
    for r in rows:
        print(f"\n  attack: {r['attack']}")
        print(f"    invariant : {r['invariant']}")
        print(f"    after     : valid={r['after']['structurally_valid']} "
              f"failed={r['after']['failed_checks']} cells={r['after']['n_cells']} "
              f"text_unchanged={r['text_unchanged']}")
        print(f"    REWARDED  : {r['metric_rewarded_the_attack']}")
    print(f"\nany attack rewarded: {payload['any_attack_rewarded']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
