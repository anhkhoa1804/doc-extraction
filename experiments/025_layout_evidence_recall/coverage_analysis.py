"""025 line 2 -- region coverage recall and required-string coverage.

Offline. Reads `coverage_dataset.json`; runs no pipeline, no OCR, no model,
no GPU.

Two diagnostic metrics, neither of which replaces an extraction metric:

  Region Coverage Recall -- the fraction of recognised OCR tokens whose
  centre falls inside at least one emitted layout region. This is the
  detector's recall measured against evidence the recogniser already
  produced, which needs no new labels and no new corpus.

  Required-string coverage -- for every `must_contain` string, whether the
  OCR tokens that spell it are covered, partially covered, or wholly
  uncovered by layout. This is what bridges geometry to benchmark behaviour,
  and it is the metric 024 said a layout milestone would need in order not
  to be wrongly abandoned.

    python experiments/025_layout_evidence_recall/coverage_analysis.py
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "coverage_dataset.json"


def norm(s: str) -> str:
    s = unicodedata.normalize("NFC", s or "")
    return re.sub(r"\s+", " ", s).strip().lower()


def main() -> int:
    if not DATA.exists():
        print("coverage_dataset.json missing -- run coverage_instrument.py first")
        return 1
    d = json.loads(DATA.read_text())
    pages, docs = d["pages"], {r["document_id"]: r for r in d["documents"]}

    # --- region coverage recall ---------------------------------------------
    tot = Counter()
    per_doc = defaultdict(Counter)
    per_label_claimed = Counter()
    for p in pages:
        c = Counter(t["claim"] for t in p["tokens"])
        tot.update(c)
        tot["tokens"] += len(p["tokens"])
        tot["regions"] += len(p["regions"])
        tot["tables"] += len(p["tables"])
        per_doc[p["document_id"]].update(c)
        per_doc[p["document_id"]]["tokens"] += len(p["tokens"])
        per_doc[p["document_id"]]["regions"] += len(p["regions"])
        for r in p["regions"]:
            per_label_claimed[r["label"]] += r["claimed_tokens"]

    covered = tot["region"]
    rcr = covered / tot["tokens"] if tot["tokens"] else 0.0
    # Coverage counting table/cell ownership as covered too -- the number a
    # reader will otherwise compute themselves and mistake for the headline.
    rcr_incl_tables = (tot["region"] + tot["cell"] + tot["table"]) / tot["tokens"]

    label_hist = Counter()
    conf_present = 0
    for p in pages:
        for r in p["regions"]:
            label_hist[r["label"]] += 1
            if r["confidence"] is not None:
                conf_present += 1

    # --- per-document, and by stratum ---------------------------------------
    doc_rows = []
    for did, c in per_doc.items():
        row = docs[did]
        doc_rows.append({
            "document_id": did,
            "language": row["language"],
            "document_type": row["document_type"],
            "labels": row["labels"],
            "pages": row["pages"],
            "tokens": c["tokens"],
            "regions": c["regions"],
            "region_covered": c["region"],
            "cell": c["cell"],
            "table": c["table"],
            "orphan": c["orphan"],
            "coverage_recall": round(c["region"] / c["tokens"], 4) if c["tokens"] else None,
            "orphan_rate": round(c["orphan"] / c["tokens"], 4) if c["tokens"] else None,
            "regions_per_page": round(c["regions"] / row["pages"], 2),
            "exact": row["text_recall"], "char": row["char_recall"],
            "order_ok": row["order_ok"], "tables_ok": row["tables_ok"],
        })
    doc_rows.sort(key=lambda r: r["orphan_rate"] or 0, reverse=True)

    # --- required-string coverage -------------------------------------------
    # A must_contain string is "covered" when every word of it is carried by
    # tokens that layout claimed. Words are matched against the page's token
    # texts; a string whose words are not in the OCR output at all is an
    # ACQUISITION failure and is reported separately -- layout cannot cover
    # evidence that was never recognised. That separation is the whole point:
    # it keeps class A out of class B.
    string_rows = []
    for did, row in docs.items():
        dpages = [p for p in pages if p["document_id"] == did]
        toks = [t for p in dpages for t in p["tokens"]]
        by_word = defaultdict(list)
        for t in toks:
            for w in norm(t["text"]).split():
                by_word[w].append(t)
        for s in row["must_contain"]:
            words = norm(s).split()
            if not words:
                continue
            found = {w: by_word.get(w, []) for w in words}
            recognised = [w for w in words if found[w]]
            if not recognised:
                verdict = "not_recognised"          # class A
            else:
                claimed = [w for w in recognised
                           if any(t["claim"] in ("region", "cell", "table") for t in found[w])]
                if len(recognised) < len(words):
                    verdict = "partially_recognised"  # class A, partial
                elif len(claimed) == len(words):
                    verdict = "covered"
                elif claimed:
                    verdict = "partially_covered"     # class B, partial
                else:
                    verdict = "uncovered"             # class B
            string_rows.append({
                "document_id": did, "string": s, "verdict": verdict,
                "words": len(words), "words_recognised": len(recognised),
                "in_missing_list": s in (row.get("missing") or []),
            })
    verdicts = Counter(r["verdict"] for r in string_rows)

    payload = {
        "commit": d["commit"],
        "source": "coverage_dataset.json",
        "note": "diagnostic metrics; they do not replace the extraction metrics",
        "totals": {
            "documents": len(docs), "pages": len(pages),
            "tokens_recognised": tot["tokens"],
            "claimed_by_region": tot["region"],
            "claimed_by_cell": tot["cell"],
            "inside_table_not_cell": tot["table"],
            "orphan": tot["orphan"],
            "regions": tot["regions"], "tables": tot["tables"],
            "regions_per_page": round(tot["regions"] / len(pages), 3),
        },
        "region_coverage_recall": round(rcr, 4),
        "region_coverage_recall_incl_table_ownership": round(rcr_incl_tables, 4),
        "orphan_rate": round(tot["orphan"] / tot["tokens"], 4),
        "region_label_histogram": dict(label_hist.most_common()),
        "tokens_claimed_by_region_label": dict(per_label_claimed.most_common()),
        "region_confidence_available": {
            "regions_total": tot["regions"], "with_confidence": conf_present,
            "note": "Docling's layout backend emits no per-region confidence; "
                    "a confidence-gated fallback (proposal intervention 4) has "
                    "no signal to gate on and is not testable as specified.",
        },
        "required_string_coverage": {
            "strings_total": len(string_rows),
            "verdicts": dict(verdicts),
            "rows": string_rows,
        },
        "per_document": doc_rows,
    }
    (HERE / "coverage_analysis.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False))

    print(f"tokens {tot['tokens']}  region {tot['region']}  cell {tot['cell']}  "
          f"table {tot['table']}  orphan {tot['orphan']}")
    print(f"REGION COVERAGE RECALL  {rcr:.4f}   (incl. table ownership {rcr_incl_tables:.4f})")
    print(f"regions/page {tot['regions']/len(pages):.2f}   labels: {dict(label_hist)}")
    print(f"region confidence available on {conf_present}/{tot['regions']} regions")
    print(f"required strings: {dict(verdicts)}")
    print("\nworst 10 documents by orphan rate:")
    for r in doc_rows[:10]:
        print(f"  {r['document_id']:<30} orphan {r['orphan']:>4}/{r['tokens']:<5} "
              f"rate {r['orphan_rate']:.3f}  cov {r['coverage_recall']:.3f}  "
              f"reg/pg {r['regions_per_page']:.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
