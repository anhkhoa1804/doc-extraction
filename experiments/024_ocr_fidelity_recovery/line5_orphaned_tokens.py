"""LINE 5 -- how much recognised evidence is discarded for want of a region?

`_gather_region_text` collects only the tokens whose centre falls inside a
detected layout region (`_center_in`). Tokens that no region claims are not
mis-ordered and not mis-assigned: they are dropped, silently, and never
reach the assembled document.

`cmb_scan_multicol_en` is the clean case. Docling detects two regions; of 34
OCR tokens, 19 are claimed and 15 are orphaned -- and the orphans are the
whole second column, including the string the A/B scored as missing. The
recogniser read it correctly. Nothing downstream ever saw it.

This measures the class corpus-wide: per document, how many tokens are
orphaned, and how many required strings exist *only* in orphaned tokens --
that last number is the recall this mechanism is costing, and it is
recoverable without a single additional OCR call.

Note what this is not. Experiment 023 ruled out token-to-cell *ownership*
(0 of 18 table-document failures) and that finding stands: this is not the
assignment rule choosing the wrong cell. It is layout/structure detection
failing to emit a region at all, upstream of any assignment. The two are
different mechanisms with different fixes.

Reads artifacts already on disk. No OCR, no model, no GPU.
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "research/production_corpus"))

from run_benchmark import _norm  # noqa: E402

CORPUS = REPO / "research/production_corpus/corpus"
RUNS = REPO / "experiments/023_evidence_centric/_runs/visual/tesseract"
AB = REPO / "experiments/023_evidence_centric/ab_visual.json"
FAILURE_CORPUS = {
    "hc_rotation_vi", "hc_tiny_cells_vi", "cmb_scan_multicol_en",
    "cmb_scan_tiny_vi", "cmb_tiny_table_en", "cmb_scan_stamp_table_vi",
    "cmb_stamp_table_vi",
}


def centre_in(token: dict, region: dict) -> bool:
    b, r = token["bbox"], region["bbox"]
    cx, cy = (b["x0"] + b["x1"]) / 2, (b["y0"] + b["y1"]) / 2
    return r["x0"] <= cx <= r["x1"] and r["y0"] <= cy <= r["y1"]


def main() -> int:
    manifest = json.loads((CORPUS / "manifest.json").read_text())
    by_id = {d["document_id"]: d for d in manifest["documents_list"]}
    ab = json.loads(AB.read_text())
    missing_by_doc = {r["document_id"]: r["missing"]
                      for r in ab["conditions"]["tesseract"]["rows"]}
    dirs = {p.name.rsplit("-", 1)[0]: p.name for p in RUNS.iterdir() if p.is_dir()}

    rows = []
    for doc_id, dir_name in sorted(dirs.items()):
        d = RUNS / dir_name
        claimed_txt, orphan_txt = [], []
        n_tok = n_orphan = n_regions = 0
        for ocr_page in sorted((d / "ocr").glob("page-*.json")):
            stem = ocr_page.stem
            lay = d / "layout" / f"{stem}.json"
            regions = json.loads(lay.read_text()).get("regions", []) if lay.is_file() else []
            n_regions += len(regions)
            for t in json.loads(ocr_page.read_text()).get("tokens", []):
                n_tok += 1
                if any(centre_in(t, r) for r in regions):
                    claimed_txt.append(t.get("text", ""))
                else:
                    n_orphan += 1
                    orphan_txt.append(t.get("text", ""))
        claimed, orphan = _norm(" ".join(claimed_txt)), _norm(" ".join(orphan_txt))
        # A required string recoverable purely by not discarding orphans.
        only_in_orphans = [s for s in missing_by_doc.get(doc_id, [])
                           if _norm(s) not in claimed
                           and _norm(s) in _norm(claimed + " " + orphan)]
        rows.append({
            "document_id": doc_id, "in_failure_corpus": doc_id in FAILURE_CORPUS,
            "labels": by_id[doc_id].get("hard_case_labels", []),
            "regions": n_regions, "tokens": n_tok, "orphaned": n_orphan,
            "orphan_rate": round(n_orphan / n_tok, 4) if n_tok else 0.0,
            "missing_strings": len(missing_by_doc.get(doc_id, [])),
            "recoverable_from_orphans": only_in_orphans,
        })

    recoverable = [r for r in rows if r["recoverable_from_orphans"]]
    worst = sorted(rows, key=lambda r: -r["orphan_rate"])[:12]
    out = {
        "line": 5,
        "question": "how much recognised evidence is discarded for want of a region?",
        "mechanism": "layout/structure detection emits no region; _center_in drops the tokens",
        "not_this": "token-to-cell ownership, which experiment 023 ruled out and which stands",
        "totals": {
            "documents": len(rows),
            "tokens": sum(r["tokens"] for r in rows),
            "orphaned": sum(r["orphaned"] for r in rows),
            "orphan_rate": round(sum(r["orphaned"] for r in rows)
                                 / max(sum(r["tokens"] for r in rows), 1), 4),
            "mean_orphan_rate_per_document": round(
                statistics.mean(r["orphan_rate"] for r in rows), 4),
            "documents_with_recoverable_strings": len(recoverable),
            "recoverable_strings": sum(len(r["recoverable_from_orphans"]) for r in recoverable),
        },
        "rows": rows,
    }
    (HERE / "line5_orphaned_tokens.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))

    t = out["totals"]
    print(f"documents {t['documents']}  tokens {t['tokens']}  orphaned {t['orphaned']} "
          f"({100*t['orphan_rate']:.1f}%)  mean per-doc orphan rate {100*t['mean_orphan_rate_per_document']:.1f}%")
    print(f"\nrequired strings recoverable by NOT discarding orphans: {t['recoverable_strings']} "
          f"in {t['documents_with_recoverable_strings']} document(s)")
    for r in recoverable:
        flag = "FC" if r["in_failure_corpus"] else "  "
        print(f"  {flag} {r['document_id']:28s} orphan {r['orphaned']}/{r['tokens']} "
              f"({100*r['orphan_rate']:.0f}%)  {r['recoverable_from_orphans']}")
    print("\nhighest orphan rates:")
    for r in worst:
        flag = "FC" if r["in_failure_corpus"] else "  "
        print(f"  {flag} {r['document_id']:28s} regions={r['regions']:<3d} "
              f"orphan {r['orphaned']:>3d}/{r['tokens']:<4d} ({100*r['orphan_rate']:5.1f}%)  {r['labels']}")
    print("\nwrote line5_orphaned_tokens.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
