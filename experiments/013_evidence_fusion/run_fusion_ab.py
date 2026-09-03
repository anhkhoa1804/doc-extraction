"""013 — Evidence Fusion v0: three policies over the same OCR evidence.

Reuses experiment 012's exact corpus, rendering, and recall scoring (same
13 documents already span the mission's requested categories: clean EN/VI,
scan, tiny text, low contrast, stamp, table, mixed EN/VI -- no new corpus
needed). Only the OCR stage runs (same "controlled A/B" discipline as 012);
layout/table are not run.

Policy A -- best single backend: EasyOCR alone (the measured stronger
single backend per experiment 012).
Policy B -- naive union: exactly experiment 012's "union" (raw
concatenation of both backends' full text, unconditionally).
Policy C -- evidence-aware fusion: `doc_extraction.ingest.evidence_fusion`,
spatial grouping + per-region agree/conflict/single-source decision.

    python experiments/013_evidence_fusion/run_fusion_ab.py --device cuda --resource-state CLEAR
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
import unicodedata
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
CORPUS = REPO / "research/production_corpus/corpus"

# Identical to experiment 012's DOCS list -- same corpus, same documents,
# so results are directly comparable to the 012 baseline without a second
# ground-truth audit.
DOCS = [
    "hc_scan_vi", "hc_scan_en", "cmb_scan_multicol_en",
    "cmb_scan_stamp_table_vi", "cmb_scan_tiny_vi", "ord_invoice_png_vi",
    "ord_contract_en", "ord_contract_vi", "hc_tiny_text_en", "hc_tiny_text_vi",
    "hc_low_contrast_vi", "hc_stamp_text_vi", "cmb_multicol_table_en",
]


def words(s: str) -> list[str]:
    s = unicodedata.normalize("NFC", s).lower()
    return [w for w in re.split(r"[^0-9a-zà-ỹăâđêôơư]+", s, flags=re.I) if w]


def norm(s: str) -> str:
    return " ".join(unicodedata.normalize("NFC", s or "").split()).lower()


def recall(text: str, must: list[str]) -> tuple[float, float]:
    tw = set(words(text))
    ex = sum(1 for s in must if norm(s) in norm(text)) / len(must) if must else 1.0
    per = []
    for s in must:
        sw = words(s)
        per.append(sum(1 for w in sw if w in tw) / len(sw) if sw else 0.0)
    wr = sum(per) / len(per) if per else 1.0
    return ex, wr


def duplicate_rate(text: str) -> float:
    """Fraction of word *tokens* (not distinct words) that are exact repeats
    of an earlier occurrence at the same normalized form. A crude proxy for
    "how much of this string is the same content said twice" -- naive union
    should score high here for documents where the backends agree; fusion
    should score low, since agreeing regions are deduplicated by
    construction (see evidence_fusion.EvidenceGroup.fused_text)."""
    toks = words(text)
    if not toks:
        return 0.0
    seen: dict[str, int] = {}
    dup = 0
    for w in toks:
        seen[w] = seen.get(w, 0) + 1
        if seen[w] > 1:
            dup += 1
    return dup / len(toks)


def pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 2 or len(set(xs)) < 2 or len(set(ys)) < 2:
        return None
    return statistics.correlation(xs, ys)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--dpi", type=int, default=200)
    ap.add_argument("--resource-state", default="unspecified")
    ap.add_argument("--json", type=Path, default=Path(__file__).parent / "results.json")
    args = ap.parse_args()

    from doc_extraction.backends.docling_backend import DoclingBackend
    from doc_extraction.backends.easyocr_backend import EasyOCRBackend
    from doc_extraction.ingest.evidence_fusion import assemble_fused_text, fuse_page, summarize
    from doc_extraction.pipelines.base import PageInput
    from doc_extraction.stages.render import render_image_passthrough, render_single_pdf_page
    from PIL import Image

    scratch = Path("/tmp/claude-1002/-home-leanhkhoa150204/015e597f-af8b-4e89-800b-931d0f18d3f8/scratchpad/fusion_ab")
    scratch.mkdir(parents=True, exist_ok=True)

    manifest = json.loads((CORPUS / "manifest.json").read_text())
    by_id = {d["document_id"]: d for d in manifest["documents_list"]}

    docling = DoclingBackend(device=args.device, ocr_languages=["en", "vi"])
    easyocr_backend = EasyOCRBackend(device=args.device, languages=["en", "vi"])

    results = []
    for i, name in enumerate(DOCS):
        meta = by_id[name]
        src = CORPUS / meta["filename"]
        must = meta["must_contain"]
        is_pdf = src.suffix.lower() == ".pdf"

        page_dir = scratch / name
        img = (render_single_pdf_page(src, 0, page_dir, dpi=args.dpi) if is_pdf
               else render_image_passthrough(src, page_dir))
        with Image.open(img) as im:
            pw, ph = float(im.size[0]), float(im.size[1])

        page_input = PageInput(page_index=0, width=pw, height=ph, image_path=img, dpi=args.dpi)

        t0 = time.perf_counter()
        docling_result = docling.recognize(page_input)
        t_docling = time.perf_counter() - t0
        t0 = time.perf_counter()
        easyocr_result = easyocr_backend.recognize(page_input)
        t_easyocr = time.perf_counter() - t0

        text_d = " ".join(t.text for t in docling_result.tokens)
        text_e = " ".join(t.text for t in easyocr_result.tokens)
        text_union = text_d + " " + text_e

        t0 = time.perf_counter()
        groups = fuse_page(docling_result.tokens, easyocr_result.tokens)
        text_fused = assemble_fused_text(groups)
        t_fuse = time.perf_counter() - t0
        fsummary = summarize(groups)

        ex_a, wr_a = recall(text_e, must)  # policy A: best single backend
        ex_b, wr_b = recall(text_union, must)  # policy B: naive union
        ex_c, wr_c = recall(text_fused, must)  # policy C: evidence fusion
        ex_d_only, wr_d_only = recall(text_d, must)  # raw docling alone, for correlated-error analysis

        wd, we = set(words(text_d)), set(words(text_e))
        whole_doc_agreement = len(wd & we) / len(wd | we) if (wd or we) else 1.0
        conf_e = [t.confidence for t in easyocr_result.tokens if t.confidence is not None]
        mean_conf = statistics.mean(conf_e) if conf_e else None

        row = {
            "document": name,
            "n_must_contain": len(must),
            "policy_a_easyocr": {"exact_recall": round(ex_a, 4), "word_recall": round(wr_a, 4),
                                  "duplicate_rate": round(duplicate_rate(text_e), 4)},
            "policy_b_naive_union": {"exact_recall": round(ex_b, 4), "word_recall": round(wr_b, 4),
                                      "duplicate_rate": round(duplicate_rate(text_union), 4)},
            "policy_c_evidence_fusion": {"exact_recall": round(ex_c, 4), "word_recall": round(wr_c, 4),
                                          "duplicate_rate": round(duplicate_rate(text_fused), 4),
                                          **fsummary.as_dict(), "seconds_fusion_only": round(t_fuse, 4)},
            "docling_alone": {"exact_recall": round(ex_d_only, 4), "word_recall": round(wr_d_only, 4)},
            "min_single_backend_word_recall": round(min(wr_a, wr_d_only), 4),
            "whole_doc_word_agreement": round(whole_doc_agreement, 4),
            "easyocr_mean_confidence": round(mean_conf, 4) if mean_conf is not None else None,
            "docling_seconds": round(t_docling, 3),
            "easyocr_seconds": round(t_easyocr, 3),
        }
        results.append(row)
        print(f"  {name:<26} A(wr)={wr_a:.3f} B(wr)={wr_b:.3f} C(wr)={wr_c:.3f}  "
              f"dupB={row['policy_b_naive_union']['duplicate_rate']:.2f} "
              f"dupC={row['policy_c_evidence_fusion']['duplicate_rate']:.2f} "
              f"conflict_rate={fsummary.conflict_rate:.2f} agree={whole_doc_agreement:.2f}")

    n = len(results)

    def col(policy: str, field: str) -> list[float]:
        return [r[policy][field] for r in results]

    summary = {
        "n_documents": n, "device": args.device, "resource_state": args.resource_state,
        "policy_a_easyocr": {
            "mean_exact_recall": round(statistics.mean(col("policy_a_easyocr", "exact_recall")), 4),
            "mean_word_recall": round(statistics.mean(col("policy_a_easyocr", "word_recall")), 4),
            "mean_duplicate_rate": round(statistics.mean(col("policy_a_easyocr", "duplicate_rate")), 4),
        },
        "policy_b_naive_union": {
            "mean_exact_recall": round(statistics.mean(col("policy_b_naive_union", "exact_recall")), 4),
            "mean_word_recall": round(statistics.mean(col("policy_b_naive_union", "word_recall")), 4),
            "mean_duplicate_rate": round(statistics.mean(col("policy_b_naive_union", "duplicate_rate")), 4),
        },
        "policy_c_evidence_fusion": {
            "mean_exact_recall": round(statistics.mean(col("policy_c_evidence_fusion", "exact_recall")), 4),
            "mean_word_recall": round(statistics.mean(col("policy_c_evidence_fusion", "word_recall")), 4),
            "mean_duplicate_rate": round(statistics.mean(col("policy_c_evidence_fusion", "duplicate_rate")), 4),
            "mean_conflict_rate": round(statistics.mean(col("policy_c_evidence_fusion", "conflict_rate")), 4),
        },
        "correlations": {
            "confidence_vs_c_word_recall": pearson(
                [r["easyocr_mean_confidence"] for r in results if r["easyocr_mean_confidence"] is not None],
                [r["policy_c_evidence_fusion"]["word_recall"] for r in results if r["easyocr_mean_confidence"] is not None],
            ),
            "agreement_vs_c_word_recall": pearson(
                [r["whole_doc_word_agreement"] for r in results],
                [r["policy_c_evidence_fusion"]["word_recall"] for r in results],
            ),
            "combined_vs_c_word_recall": pearson(
                [
                    0.5 * r["whole_doc_word_agreement"] + 0.5 * (r["easyocr_mean_confidence"] or 0.0)
                    for r in results
                ],
                [r["policy_c_evidence_fusion"]["word_recall"] for r in results],
            ),
            # matches experiment 012's exact methodology (agreement vs the
            # weaker of the two raw single-backend recalls) for direct
            # comparability with that milestone's r=0.856 finding.
            "agreement_vs_min_single_backend_recall_exp012_replication": pearson(
                [r["whole_doc_word_agreement"] for r in results],
                [r["min_single_backend_word_recall"] for r in results],
            ),
        },
    }
    correlated_error_docs = [
        r["document"] for r in results
        if r["whole_doc_word_agreement"] >= 0.9 and r["min_single_backend_word_recall"] < 0.85
    ]
    summary["correlated_error_documents"] = correlated_error_docs

    print(f"\n=== summary (n={n}, device={args.device}, resource_state={args.resource_state}) ===")
    print(json.dumps(summary, indent=2))

    args.json.write_text(json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=2))
    print(f"\nwrote {args.json}")


if __name__ == "__main__":
    main()
