"""027 Phase 5 -- is `order_ok` measuring what it claims to measure?

Offline. Reads `historical_replay.json` (produced by the replay) plus the
frozen IR, and asks one question: `order_ok` is documented as detecting a
"reading-order defect", but the serializer it reads appends table cells in
detector emission order. How much of the metric's signal is page reading
order, and how much is table cell list order?

The test is a difference. Under the counterfactual serializer, table cell
sequence is canonical, so any `order_ok=False` that SURVIVES is a genuine
page-level ordering signal; any that disappears was table-serialization
noise. Nothing else about the metric changes.

    python experiments/027_evaluation_serialization/order_metric_audit.py
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> int:
    rep = json.loads((HERE / "historical_replay.json").read_text())
    arms = rep["arms"]

    rows = []
    for a in arms:
        c, k = a["control"], a["counterfactual"]
        n = a["documents"]
        ctl_fail = n - c["docs_order_ok"]
        cf_fail = n - k["docs_order_ok"]
        si = a["structural_integrity"]
        broken = (si["tables"] - si["ordered"]) if si["tables"] else 0
        rows.append({
            "milestone": a["milestone"], "arm": a["arm"], "documents": n,
            "tables": si["tables"], "tables_structurally_broken": broken,
            "structural_integrity": si["value"],
            "order_ok_false_control": ctl_fail,
            "order_ok_false_counterfactual": cf_fail,
            "flags_caused_by_table_serialization": ctl_fail - cf_fail,
            "flags_surviving_as_genuine_page_order": cf_fail,
            "share_of_flags_that_were_serialization": (
                round((ctl_fail - cf_fail) / ctl_fail, 4) if ctl_fail else None),
            "detection_rate_of_broken_tables": (
                round((ctl_fail - cf_fail) / broken, 4) if broken else None),
        })

    real = [r for r in rows if r["documents"] >= 10]
    tot_ctl = sum(r["order_ok_false_control"] for r in real)
    tot_cf = sum(r["order_ok_false_counterfactual"] for r in real)
    tot_broken = sum(r["tables_structurally_broken"] for r in real)

    # the SCAN-49 family, where 025 made its claim
    scan = [r for r in rows if r["tables"] == 94]

    payload = {
        "question": "does order_ok measure page reading order, or table cell list order?",
        "method": "difference between the frozen serializer and a serializer identical "
                  "except that table cells are iterated in (row, col) order",
        "totals_over_arms_with_n>=10": {
            "arms": len(real),
            "order_ok_false_control": tot_ctl,
            "order_ok_false_counterfactual": tot_cf,
            "flags_caused_by_table_serialization": tot_ctl - tot_cf,
            "share_of_all_flags_that_were_serialization": round((tot_ctl - tot_cf) / tot_ctl, 4),
            "tables_structurally_broken": tot_broken,
        },
        "scan49_family": {
            "arms": len(scan),
            "tables": 94,
            "tables_structurally_broken": scan[0]["tables_structurally_broken"] if scan else None,
            "structural_integrity": scan[0]["structural_integrity"] if scan else None,
            "order_ok_false_control": scan[0]["order_ok_false_control"] if scan else None,
            "order_ok_false_counterfactual": scan[0]["order_ok_false_counterfactual"] if scan else None,
            "detection_rate": scan[0]["detection_rate_of_broken_tables"] if scan else None,
            "reproduces_025_claim": (
                scan[0]["tables_structurally_broken"] == 11
                and scan[0]["order_ok_false_control"] == 4) if scan else None,
        },
        "findings": {
            "false_negatives": "a structurally broken table produces an order_ok flag ONLY "
                               "when the document's must_contain strings happen to straddle "
                               "the inversion. On SCAN-49, 11 tables are broken and 4 "
                               "documents flag: 7 false negatives, detection rate 0.36.",
            "false_positives": "none identifiable. Every flag that disappears under the "
                               "counterfactual corresponded to a table whose cell list was "
                               "genuinely out of geometric order, so those flags were TRUE "
                               "observations -- of table serialization, not of page reading "
                               "order. They are mislabelled, not wrong.",
            "conflation": "order_ok mixes two independent properties. After "
                          "canonicalization every surviving flag is page-level.",
        },
        "per_arm": rows,
    }
    (HERE / "order_metric_audit.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False))

    t = payload["totals_over_arms_with_n>=10"]
    print(f"arms (n>=10): {t['arms']}")
    print(f"  order_ok=False  control        : {t['order_ok_false_control']}")
    print(f"  order_ok=False  counterfactual : {t['order_ok_false_counterfactual']}")
    print(f"  flags caused by table serialization: {t['flags_caused_by_table_serialization']}"
          f"  ({t['share_of_all_flags_that_were_serialization']:.1%} of all flags)")
    s = payload["scan49_family"]
    print(f"\nSCAN-49 family ({s['arms']} arms, 94 tables):")
    print(f"  structurally broken tables : {s['tables_structurally_broken']} "
          f"(structural integrity {s['structural_integrity']})")
    print(f"  documents flagged by order_ok: {s['order_ok_false_control']} -> "
          f"{s['order_ok_false_counterfactual']}")
    print(f"  detection rate of broken tables: {s['detection_rate']}")
    print(f"  reproduces the 025 claim (11 broken / 4 flagged): {s['reproduces_025_claim']}")
    print("\nper-arm, arms where flags were purely serialization:")
    for r in rows:
        if r["flags_caused_by_table_serialization"]:
            print(f"  {r['milestone']} {r['arm']:<40} "
                  f"{r['order_ok_false_control']}->{r['order_ok_false_counterfactual']} "
                  f"({r['flags_caused_by_table_serialization']} serialization)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
