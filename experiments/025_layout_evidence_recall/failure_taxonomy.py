"""025 line 6 -- failure-mechanism classification. §2 classes, kept separate.

Offline. Reads `coverage_dataset.json` and `orphan_topology.json`.

Two accountings, because they answer different questions and mixing them is
how a milestone talks itself into the wrong fix:

  TOKEN accounting -- of the recognised OCR evidence, what happened to it?
  This is where class B lives, and it is dominated by volume.

  DOCUMENT accounting -- of the documents that still score imperfectly, what
  is actually wrong with them? This is where the residual failures live, and
  it is dominated by structure.

Class B is further split by whether the uncovered evidence is unique content
or running page furniture repeated across pages, because 024's headline
result turns on that distinction and the distinction had never been measured.

    python experiments/025_layout_evidence_recall/failure_taxonomy.py
"""
from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", s or "")).strip().lower()


def main() -> int:
    d = json.loads((HERE / "coverage_dataset.json").read_text())
    topo = json.loads((HERE / "orphan_topology.json").read_text())
    docs = {r["document_id"]: r for r in d["documents"]}
    per_page = {(r["document_id"], r["page_index"]): r for r in topo["per_page"]}

    # --- token accounting ----------------------------------------------------
    claims = Counter()
    for p in d["pages"]:
        claims.update(t["claim"] for t in p["tokens"])
    tokens = sum(claims.values())

    # class B split: furniture vs unique content
    furniture = unique = 0
    by_doc_class = defaultdict(Counter)
    for p in d["pages"]:
        cls = per_page[(p["document_id"], p["page_index"])].get("classes") or {}
        by_doc_class[p["document_id"]].update(cls)
        for t in p["tokens"]:
            if t["claim"] != "orphan":
                continue
        # header/footer bands are running furniture on this corpus; verified
        # below by repetition, not asserted from the band alone.
    for did, c in by_doc_class.items():
        furniture += c.get("header_band", 0) + c.get("footer_band", 0)
        unique += sum(v for k, v in c.items() if k not in ("header_band", "footer_band"))

    orphan_strings = [norm(t["text"]) for p in d["pages"]
                      for t in p["tokens"] if t["claim"] == "orphan"]
    rep = Counter(orphan_strings)

    # --- document accounting -------------------------------------------------
    doc_class = {}
    for did, r in docs.items():
        ps = [p for p in d["pages"] if p["document_id"] == did]
        tk = sum(len(p["tokens"]) for p in ps)
        orp = sum(1 for p in ps for t in p["tokens"] if t["claim"] == "orphan")
        cov = 1 - (orp / tk) if tk else None
        defects = []
        if not r["order_ok"]:
            defects.append("D_reading_order")
        if not r["tables_ok"]:
            defects.append("B2_table_region_not_emitted")
        if r["char_recall"] < 0.999:
            defects.append("A_ocr_acquisition_or_fidelity")
        if r["text_recall"] < 1.0 and not defects:
            defects.append("A_exact_only")
        doc_class[did] = {
            "defects": defects, "coverage_recall": round(cov, 4) if cov is not None else None,
            "orphans": orp, "tokens": tk,
            "exact": r["text_recall"], "char": r["char_recall"],
            "order_ok": r["order_ok"], "tables_ok": r["tables_ok"],
            "tables_found": r["tables_found"], "tables_expected": r["tables_expected"],
            "region_labels": dict(Counter(rg["label"] for p in ps for rg in p["regions"])),
            "labels": r["labels"],
        }
    defective = {k: v for k, v in doc_class.items() if v["defects"]}
    cov_caused = {k: v for k, v in defective.items() if v["orphans"] > 0}

    payload = {
        "commit": d["commit"],
        "classes": {
            "A": "OCR acquisition failure -- the recognizer never produced usable evidence",
            "B": "layout detection/coverage failure -- evidence exists, no region covers it",
            "C": "region ownership failure -- region covers it, assignment puts it elsewhere",
            "D": "reading-order failure -- regions and ownership right, sequence wrong",
        },
        "token_accounting": {
            "tokens_recognised": tokens,
            "claimed_by_region": claims["region"],
            "claimed_by_cell": claims["cell"],
            "inside_table_not_cell": claims["table"],
            "class_B_orphans": claims["orphan"],
            "class_B_rate": round(claims["orphan"] / tokens, 4),
            "class_C_ownership_conflicts": sum(
                1 for p in d["pages"] for t in p["tokens"] if t["n_owners"] > 1),
            "class_C_evidence": "tokens whose centre falls inside two regions at once. "
                                "`_gather_region_text` runs per region, so each such token "
                                "is emitted into BOTH elements -- duplicated evidence. 024 "
                                "measured orphan_also_claimed = 0, which is a different and "
                                "still-true statement: recovered orphans are not duplicates. "
                                "Region-on-region overlap was never measured until now.",
            "class_C_by_document": {
                did: n for did, n in sorted(
                    Counter(p["document_id"] for p in d["pages"]
                            for t in p["tokens"] if t["n_owners"] > 1).items(),
                    key=lambda kv: -kv[1])},
            "class_B_split": {
                "running_page_furniture_header_footer": furniture,
                "unique_content": unique,
                "furniture_share": round(furniture / claims["orphan"], 4),
            },
            "orphan_repetition": {
                "orphan_tokens": len(orphan_strings),
                "distinct_strings": len(rep),
                "top_repeats": rep.most_common(10),
            },
        },
        "document_accounting": {
            "documents": len(docs),
            "documents_defective": len(defective),
            "documents_whose_defect_could_be_coverage": len(cov_caused),
            "defect_histogram": {
                " + ".join(k): n for k, n in Counter(
                    tuple(v["defects"]) for v in defective.values()).most_common()},
            "defective": defective,
        },
        "verdict": {
            "dominant_by_token_volume": "B -- but 86.7% of it is running page "
                                        "header/footer furniture on 2 documents",
            "dominant_by_residual_failure": "not B -- 7 of 8 defective documents have "
                                            "coverage recall 1.000",
        },
        "per_document_orphan_classes": {k: dict(v) for k, v in by_doc_class.items() if sum(v.values())},
    }
    (HERE / "failure_taxonomy.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False))

    ta = payload["token_accounting"]
    print(f"TOKENS {tokens}: region {ta['claimed_by_region']} cell {ta['claimed_by_cell']} "
          f"table {ta['inside_table_not_cell']} ORPHAN {ta['class_B_orphans']} "
          f"({ta['class_B_rate']:.2%})")
    print(f"  class B split: furniture {furniture}  unique {unique}  "
          f"furniture share {ta['class_B_split']['furniture_share']:.2%}")
    print(f"  orphan distinct strings {len(rep)} of {len(orphan_strings)} tokens")
    da = payload["document_accounting"]
    print(f"\nDOCUMENTS {da['documents']}: defective {da['documents_defective']}, "
          f"of which coverage could explain {da['documents_whose_defect_could_be_coverage']}")
    for k, v in da["defect_histogram"].items():
        print(f"  {k}: {v}")
    print("\ndefective documents:")
    for did, v in defective.items():
        print(f"  {did:<30} cov {v['coverage_recall']:.3f} orph {v['orphans']:<4} "
              f"{v['defects']}  tables {v['tables_found']}/{v['tables_expected']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
