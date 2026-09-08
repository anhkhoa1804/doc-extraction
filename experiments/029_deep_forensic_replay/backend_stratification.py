"""029 Phase 8 -- backend/configuration stratification with paired analysis.

Offline, read-only. Reuses `results/all_tables.json`. Where the SAME document
appears under multiple backends/arms (paired), prefers paired comparison over
unpaired averages, per the milestone's explicit instruction.

    python experiments/029_deep_forensic_replay/backend_stratification.py
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> int:
    tabs = json.loads((HERE / "results/all_tables.json").read_text())

    # --- signature 1: backend vs invalidity (already found, reconfirmed here) ---
    by_backend = defaultdict(lambda: Counter())
    for t in tabs:
        by_backend[t["source_backend"]]["total"] += 1
        by_backend[t["source_backend"]]["invalid"] += int(not t["structurally_valid"])
        by_backend[t["source_backend"]]["noncanon"] += int(not t["list_order_canonical"])

    # --- signature 2: stamp/occlusion label correlation, WITHIN table_transformer only ---
    tt = [t for t in tabs if t["source_backend"] == "table_transformer"]
    by_label = defaultdict(lambda: Counter())
    label_set = set()
    for t in tt:
        labels = t.get("labels") or []
        label_set.update(labels)
        key = "stamp_or_occlusion" if any(l in ("stamp", "occlusion") for l in labels) else "no_stamp_occlusion"
        by_label[key]["total"] += 1
        by_label[key]["invalid"] += int(not t["structurally_valid"])

    # --- signature 3: paired comparison -- same document, adaptive vs visual arm, table_transformer only ---
    # "adaptive" here means the arm name contains "adaptive"; "visual" means "visual" (excluding scan_cohort).
    paired = defaultdict(dict)
    for t in tabs:
        if t["source_backend"] != "table_transformer":
            continue
        if "adaptive" in t["arm"] and "scan_cohort" not in t["arm"]:
            mode = "adaptive"
        elif "visual" in t["arm"]:
            mode = "visual"
        else:
            continue
        key = (t["milestone"], t["document_id"], t["table_id"])
        paired[key][mode] = t["structurally_valid"]

    pair_rows = [(k, v) for k, v in paired.items() if "adaptive" in v and "visual" in v]
    concordant = sum(1 for _, v in pair_rows if v["adaptive"] == v["visual"])
    disagree_adaptive_valid_visual_invalid = sum(
        1 for _, v in pair_rows if v["adaptive"] and not v["visual"])
    disagree_visual_valid_adaptive_invalid = sum(
        1 for _, v in pair_rows if v["visual"] and not v["adaptive"])

    # --- signature 4: language ---
    by_lang = defaultdict(lambda: Counter())
    for t in tt:
        by_lang[t.get("language") or "UNKNOWN"]["total"] += 1
        by_lang[t.get("language") or "UNKNOWN"]["invalid"] += int(not t["structurally_valid"])

    payload = {
        "signature_1_backend": {
            b: {"total": c["total"], "invalid": c["invalid"],
               "invalid_rate": round(c["invalid"] / c["total"], 4),
               "noncanonical": c["noncanon"],
               "noncanonical_rate": round(c["noncanon"] / c["total"], 4)}
            for b, c in by_backend.items()
        },
        "signature_2_stamp_occlusion_within_table_transformer": {
            k: {"total": c["total"], "invalid": c["invalid"],
               "invalid_rate": round(c["invalid"] / c["total"], 4) if c["total"] else None}
            for k, c in by_label.items()
        },
        "signature_3_paired_adaptive_vs_visual_same_document": {
            "pairs": len(pair_rows),
            "concordant": concordant,
            "concordant_rate": round(concordant / len(pair_rows), 4) if pair_rows else None,
            "adaptive_valid_visual_invalid": disagree_adaptive_valid_visual_invalid,
            "visual_valid_adaptive_invalid": disagree_visual_valid_adaptive_invalid,
            "interpretation": (
                "If routing mode alone caused invalidity we would expect strong "
                "asymmetric disagreement. Concordance close to 1.0 would mean the "
                "SOURCE DOCUMENT drives the outcome, not adaptive/visual routing; "
                "routing determines WHETHER table_transformer runs at all (adaptive "
                "often uses pymupdf_tables on digital PDFs) but conditional on it "
                "running, the same document tends to produce the same verdict."),
        },
        "signature_4_language": {
            k: {"total": c["total"], "invalid": c["invalid"],
               "invalid_rate": round(c["invalid"] / c["total"], 4) if c["total"] else None}
            for k, c in by_lang.items()
        },
        "labels_observed_on_table_transformer_tables": sorted(label_set),
    }
    (HERE / "backend_stratification.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False))

    print("=== signature 1: backend ===")
    for b, v in payload["signature_1_backend"].items():
        print(f"  {b:<20} total={v['total']:<5} invalid_rate={v['invalid_rate']:.2%}  "
              f"noncanon_rate={v['noncanonical_rate']:.2%}")
    print("\n=== signature 2: stamp/occlusion (within table_transformer) ===")
    for k, v in payload["signature_2_stamp_occlusion_within_table_transformer"].items():
        print(f"  {k:<22} total={v['total']:<5} invalid_rate={v['invalid_rate']:.2%}")
    print("\n=== signature 3: paired adaptive vs visual, same document ===")
    s3 = payload["signature_3_paired_adaptive_vs_visual_same_document"]
    print(f"  pairs={s3['pairs']} concordant={s3['concordant']} ({s3['concordant_rate']:.2%})")
    print(f"  adaptive_valid,visual_invalid={s3['adaptive_valid_visual_invalid']}  "
          f"visual_valid,adaptive_invalid={s3['visual_valid_adaptive_invalid']}")
    print("\n=== signature 4: language (table_transformer only) ===")
    for k, v in payload["signature_4_language"].items():
        print(f"  {k:<10} total={v['total']:<5} invalid_rate={v['invalid_rate']:.2%}" if v['invalid_rate'] is not None else f"  {k}: n=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
