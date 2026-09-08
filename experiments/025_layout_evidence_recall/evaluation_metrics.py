"""025 line 10 -- diagnostic evaluation metrics. Research framework, not production.

Offline. Reads `coverage_dataset.json`. No pipeline, no OCR, no GPU.

024 established that recall metrics are blind to evidence they did not ask
for. 025 found a second blindness of the opposite sign. Both are invisible
to `text_recall` and `char_recall` because both count ground-truth strings
FOUND, never output EMITTED:

    orphaned evidence     is dropped   -> recall cannot fall, nothing is wrong with the output
    duplicated evidence   is emitted   -> recall cannot fall, the output has it twice

These five metrics are defined so a future layout milestone can see what the
benchmark cannot. They are deliberately NOT wired into the scorer, the
production metrics, or any acceptance gate -- §8 asks for the framework, not
for adoption, and adopting a metric mid-milestone is how thresholds get
tuned to results.

    python experiments/025_layout_evidence_recall/evaluation_metrics.py
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent


def inside(tok, r):
    cx = (tok["bbox"][0] + tok["bbox"][2]) / 2
    cy = (tok["bbox"][1] + tok["bbox"][3]) / 2
    return r["bbox"][0] <= cx <= r["bbox"][2] and r["bbox"][1] <= cy <= r["bbox"][3]


def main() -> int:
    d = json.loads((HERE / "coverage_dataset.json").read_text())
    pages = d["pages"]

    tokens = own = Counter()
    own = Counter()
    emissions = 0
    total_tokens = 0
    per_doc = defaultdict(lambda: Counter())
    struct_pages_ok = struct_pages = 0

    for p in pages:
        regions = p["regions"]
        total_tokens += len(p["tokens"])
        for t in p["tokens"]:
            n = t["n_owners"]
            own[min(n, 3) if n < 3 else 3] += 1
            per_doc[p["document_id"]]["tokens"] += 1
            if n == 0:
                per_doc[p["document_id"]]["orphan"] += 1
            elif n == 1:
                per_doc[p["document_id"]]["exactly_one"] += 1
            else:
                per_doc[p["document_id"]]["multi"] += 1
        emissions += sum(sum(1 for t in p["tokens"] if inside(t, r)) for r in regions)

        # structural integrity: are this page's table cells in geometric order?
        for tb in p["tables"]:
            struct_pages += 1
            ys = [b[1] for b in tb["cell_bboxes"]]
            if ys == sorted(ys):
                struct_pages_ok += 1

    n0, n1, n2, n3 = own[0], own[1], own[2], own[3]
    multi = n2 + n3
    metrics = {
        "evidence_coverage": {
            "definition": "fraction of OCR tokens claimed by EXACTLY ONE region",
            "value": round(n1 / total_tokens, 4),
            "numerator": n1, "denominator": total_tokens,
            "why": "the only state in which a token is neither lost nor duplicated",
        },
        "orphan_rate": {
            "definition": "fraction of OCR tokens claimed by ZERO regions",
            "value": round(n0 / total_tokens, 4), "numerator": n0,
            "why": "class B. L5 rescues these; without L5 they are discarded",
        },
        "overlap_rate": {
            "definition": "fraction of OCR tokens claimed by TWO OR MORE regions",
            "value": round(multi / total_tokens, 4), "numerator": multi,
            "why": "class C. each such token is emitted once per owning region",
        },
        "evidence_duplication": {
            "definition": "token emissions across all regions, minus the distinct "
                          "tokens that any region owns",
            "token_emissions": emissions,
            "distinct_tokens_owned_by_at_least_one_region": total_tokens - n0,
            "duplicate_emissions": emissions - (total_tokens - n0),
            "rate": round((emissions - (total_tokens - n0)) / total_tokens, 4),
            "denominator_note": "orphans are in no region and contribute no emission, "
                                "so they are excluded from the distinct-token baseline; "
                                "including them made this negative.",
            "why": "what actually reaches document_text twice; strictly >= overlap_rate "
                   "because a token owned by k regions contributes k-1 duplicates",
        },
        "structural_integrity": {
            "definition": "fraction of detected tables whose cells are emitted in "
                          "non-decreasing bbox y0 order",
            "tables": struct_pages, "ordered": struct_pages_ok,
            "value": round(struct_pages_ok / struct_pages, 4) if struct_pages else None,
            "why": "class E. document_text serializes cells in list order, so a table "
                   "failing this emits its rows out of sequence",
        },
    }

    # how much of the structural damage does the benchmark actually surface?
    docs_meta = {r["document_id"]: r for r in d["documents"]}
    broken = {p["document_id"] for p in pages for tb in p["tables"]
              if [b[1] for b in tb["cell_bboxes"]]
              and [b[1] for b in tb["cell_bboxes"]] != sorted(b[1] for b in tb["cell_bboxes"])}
    seen_by_benchmark = {x for x in broken if not docs_meta[x]["order_ok"]}
    metrics["structural_integrity"]["documents_with_a_misordered_table"] = len(broken)
    metrics["structural_integrity"]["surfaced_as_order_ok_false"] = len(seen_by_benchmark)
    metrics["structural_integrity"]["invisible_to_benchmark"] = sorted(broken - seen_by_benchmark)
    metrics["structural_integrity"]["benchmark_detection_rate"] = round(
        len(seen_by_benchmark) / len(broken), 4) if broken else None

    payload = {
        "commit": d["commit"],
        "status": "RESEARCH FRAMEWORK -- not wired into the scorer or any gate",
        "motivation": {
            "recall_is_blind_to": ["orphaned evidence (024)", "duplicated evidence (025)",
                                   "repeated page furniture counted as recovered content",
                                   "content absent from sparse must_contain"],
            "reason": "text_recall and char_recall count ground-truth strings FOUND, "
                      "never output EMITTED",
        },
        "metrics": metrics,
        "per_document": {
            did: {"tokens": c["tokens"], "orphan": c["orphan"],
                  "exactly_one": c["exactly_one"], "multi": c["multi"],
                  "evidence_coverage": round(c["exactly_one"] / c["tokens"], 4)}
            for did, c in sorted(per_doc.items(),
                                 key=lambda kv: kv[1]["exactly_one"] / kv[1]["tokens"])},
    }
    (HERE / "evaluation_metrics.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False))

    print("| metric                | value | detail |")
    print("| --------------------- | ----: | ------ |")
    m = metrics
    print(f"| evidence_coverage     | {m['evidence_coverage']['value']} | {n1}/{total_tokens} claimed by exactly one region |")
    print(f"| orphan_rate           | {m['orphan_rate']['value']} | {n0} tokens in 0 regions |")
    print(f"| overlap_rate          | {m['overlap_rate']['value']} | {multi} tokens in >=2 regions |")
    print(f"| evidence_duplication  | {m['evidence_duplication']['rate']} | {m['evidence_duplication']['duplicate_emissions']} duplicate emissions of {emissions} total |")
    print(f"| structural_integrity  | {m['structural_integrity']['value']} | {struct_pages_ok}/{struct_pages} tables cell-ordered by y |")
    print("\nworst 8 documents by evidence_coverage:")
    for did, v in list(payload["per_document"].items())[:8]:
        print(f"  {did:<30} cov {v['evidence_coverage']:.3f}  orphan {v['orphan']:<4} multi {v['multi']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
