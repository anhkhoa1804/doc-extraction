"""Distributional comparison: line 5 at 6.25% OCR exposure vs at ~100%.

Reads the two frozen A/B results -- `line5_adaptive_ab.json` (the production
corpus on the shipped router) and `scan_cohort_ab.json` (the same 49
documents, same ground truth, same scorer, same router, delivered as scans)
-- and writes `scan_cohort_comparison.json`.

Every document appears in both, so deltas are paired per document. No
statistical test is applied: with 49 documents and a handful of them
affected, a p-value would be decoration rather than evidence (§11).
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load(name: str) -> dict:
    return json.loads((HERE / name).read_text())


def arm_rows(res: dict, arm: str) -> dict:
    return {r["document_id"]: r for r in res["arms"][arm]["rows"]}


def mechanism(res: dict) -> dict:
    ap = res.get("audit_pages", [])
    tok = sum(p["tokens_recognised"] for p in ap)
    orp = sum(p["orphans"] for p in ap)
    unc = sum(p["unclaimed_by_region"] for p in ap)
    tex = sum(p["table_excluded"] for p in ap)
    recovered = [r for cap in res["arms"]["l5"]["captures"].values() for r in cap["recovered"]]
    rec_tok = sum(r["token_count"] for r in recovered)
    l5 = res["arms"]["l5"]
    return {
        "ocr_pages": l5["ocr_pages"], "ocr_documents": l5["ocr_documents"],
        "ocr_invocations": l5["ocr_invocations"],
        "total_pages": res["n_pages"], "total_documents": res["n_documents"],
        "ocr_page_pct": round(l5["ocr_pages"] / res["n_pages"], 4),
        "ocr_invocations_per_document": round(l5["ocr_invocations"] / res["n_documents"], 4),
        "tokens_recognised": tok,
        "unclaimed_by_region": unc,
        "table_excluded": tex,
        "orphan_tokens": orp,
        "orphan_rate": round(orp / tok, 4) if tok else None,
        "recovered_tokens": rec_tok,
        "recovery_rate": round(rec_tok / orp, 4) if orp else None,
        "recovered_elements": len(recovered),
        "pages_with_recovery": len({(r["document_id"], r["page_index"]) for r in recovered}),
        "documents_with_recovery": len({r["document_id"] for r in recovered}),
        "l5_trigger_rate_pages": round(
            len({(r["document_id"], r["page_index"]) for r in recovered}) / l5["ocr_pages"], 4)
        if l5["ocr_pages"] else None,
        "orphan_also_claimed": sum(p.get("orphan_also_claimed", 0) for p in ap),
        "isolated_l5_s": round(sum(p["l5_isolated_s"] for p in ap), 6),
    }


def quality(res: dict) -> dict:
    out = {}
    for arm in ("baseline", "l5"):
        a = res["arms"][arm]["aggregate"]
        out[arm] = {k: a[k] for k in (
            "n", "mean_text_recall", "mean_char_recall", "docs_perfect", "docs_zero",
            "docs_order_ok", "docs_tables_ok", "docs_hallucinated", "errors")}
        out[arm]["wall_s"] = res["arms"][arm]["wall_s"]
        out[arm]["ocr_seconds"] = res["arms"][arm]["ocr_seconds"]
        out[arm]["by_language"] = a["by_language"]
    d = {}
    for k in ("mean_text_recall", "mean_char_recall", "docs_perfect", "docs_zero",
              "docs_order_ok", "docs_tables_ok", "docs_hallucinated", "errors", "wall_s"):
        d[k] = round(out["l5"][k] - out["baseline"][k], 6)
    out["delta"] = d
    return out


def changed(res: dict) -> list[dict]:
    B, L = arm_rows(res, "baseline"), arm_rows(res, "l5")
    caps = res["arms"]["l5"]["captures"]
    rows = []
    for k in B:
        if B[k]["text_sha"] == L[k]["text_sha"]:
            continue
        rec = caps[k]["recovered"]
        bp = {p["index"]: p for p in res["arms"]["baseline"]["captures"][k]["pages"]}
        lp = {p["index"]: p for p in caps[k]["pages"]}
        rows.append({
            "document_id": k, "language": B[k]["language"],
            "difficulty": B[k]["difficulty"], "labels": B[k]["labels"],
            "pages": B[k]["pages"],
            "exact_before": B[k]["text_recall"], "exact_after": L[k]["text_recall"],
            "char_before": B[k]["char_recall"], "char_after": L[k]["char_recall"],
            "chars_before": B[k]["chars"], "chars_after": L[k]["chars"],
            "missing_before": B[k]["missing"], "missing_after": L[k]["missing"],
            "recovered_elements": len(rec),
            "recovered_tokens": sum(r["token_count"] for r in rec),
            "pages_with_recovery": len({r["page_index"] for r in rec}),
            "order_ok_before": B[k]["order_ok"], "order_ok_after": L[k]["order_ok"],
            "tables_before": B[k]["tables_found"], "tables_after": L[k]["tables_found"],
            "tables_ok_before": B[k]["tables_ok"], "tables_ok_after": L[k]["tables_ok"],
            "hallucinated_before": B[k]["hallucinated"], "hallucinated_after": L[k]["hallucinated"],
            "native_text_identical": all(
                bp[i]["native_text_sha"] == lp[i]["native_text_sha"] for i in bp),
            "table_text_identical": all(
                bp[i]["table_text_sha"] == lp[i]["table_text_sha"] for i in bp),
            "exact_moved": L[k]["text_recall"] != B[k]["text_recall"],
            "char_moved": L[k]["char_recall"] != B[k]["char_recall"],
        })
    return sorted(rows, key=lambda r: -r["recovered_tokens"])


def regression_audit(res: dict) -> dict:
    B, L = res["arms"]["baseline"]["captures"], res["arms"]["l5"]["captures"]
    keys = ("route", "n_native_elements", "n_tables", "n_cells",
            "native_text_sha", "table_text_sha")
    identical = differing = 0
    order_lost = tables_lost = dup = 0
    Br, Lr = arm_rows(res, "baseline"), arm_rows(res, "l5")
    for doc in B:
        bp = {p["index"]: p for p in B[doc]["pages"]}
        lp = {p["index"]: p for p in L[doc]["pages"]}
        for i in bp:
            b, l = bp[i], lp[i]
            same_native = all(b[k] == l[k] for k in keys)
            if same_native and b["reading_order"] == l["reading_order"] and b["notes"] == l["notes"]:
                identical += 1
            else:
                differing += 1
            if not same_native and l["n_recovered_elements"] == 0:
                dup += 1  # a page changed without recovery -- would be a real defect
        if Br[doc]["order_ok"] and not Lr[doc]["order_ok"]:
            order_lost += 1
        if Br[doc]["tables_ok"] and not Lr[doc]["tables_ok"]:
            tables_lost += 1
    return {
        "pages_identical": identical, "pages_differing": differing,
        "pages_changed_without_recovery": dup,
        "documents_losing_order_ok": order_lost,
        "documents_losing_tables_ok": tables_lost,
        "documents_recall_regressed": sum(
            1 for k in Br if Lr[k]["text_recall"] < Br[k]["text_recall"]),
        "documents_char_regressed": sum(
            1 for k in Br if Lr[k]["char_recall"] < Br[k]["char_recall"]),
        "documents_newly_hallucinating": sum(
            1 for k in Br if Lr[k]["hallucinated"] and not Br[k]["hallucinated"]),
        "documents_newly_erroring": sum(
            1 for k in Br if Lr[k]["error"] and not Br[k]["error"]),
        "native_text_changed_anywhere": sum(
            1 for doc in B for b, l in zip(B[doc]["pages"], L[doc]["pages"])
            if b["native_text_sha"] != l["native_text_sha"]),
        "table_text_changed_anywhere": sum(
            1 for doc in B for b, l in zip(B[doc]["pages"], L[doc]["pages"])
            if b["table_text_sha"] != l["table_text_sha"]),
    }


def strata(res: dict) -> dict:
    """Paired per-document deltas by pre-known document property. Groups with
    fewer than 3 documents are reported with their N and no derived rate --
    §7 forbids manufacturing subgroup statistics."""
    B, L = arm_rows(res, "baseline"), arm_rows(res, "l5")
    caps = res["arms"]["l5"]["captures"]
    defs = {
        "vietnamese": lambda r: r["language"] == "vi",
        "english": lambda r: r["language"] == "en",
        "multi_column": lambda r: "multi_column" in r["labels"],
        "reading_order": lambda r: "reading_order" in r["labels"],
        "has_expected_tables": lambda r: r["tables_expected"] > 0,
        "tiny_text": lambda r: "tiny_text" in r["labels"],
        "low_quality_or_occluded": lambda r: bool(
            {"low_contrast", "stamp", "occlusion", "watermark", "scan_quality"} & set(r["labels"])),
        "no_hard_labels": lambda r: not r["labels"],
        "multi_page": lambda r: r["pages"] > 1,
    }
    out = {}
    for name, pred in defs.items():
        ids = [k for k in B if pred(B[k])]
        if not ids:
            continue
        de = [L[k]["text_recall"] - B[k]["text_recall"] for k in ids]
        dc = [L[k]["char_recall"] - B[k]["char_recall"] for k in ids]
        rec = {k: sum(r["token_count"] for r in caps[k]["recovered"]) for k in ids}
        entry = {
            "n": len(ids),
            "documents_affected": sum(1 for k in ids if rec[k] > 0),
            "recovered_tokens": sum(rec.values()),
            "supported": len(ids) >= 3,
        }
        if entry["supported"]:
            entry.update({
                "exact_before": round(statistics.mean(B[k]["text_recall"] for k in ids), 4),
                "exact_after": round(statistics.mean(L[k]["text_recall"] for k in ids), 4),
                "exact_delta": round(statistics.mean(de), 4),
                "char_before": round(statistics.mean(B[k]["char_recall"] for k in ids), 4),
                "char_after": round(statistics.mean(L[k]["char_recall"] for k in ids), 4),
                "char_delta": round(statistics.mean(dc), 4),
                "documents_improved": sum(1 for x in de if x > 0),
                "documents_regressed": sum(1 for x in de if x < 0),
            })
        else:
            entry["note"] = "N < 3 -- reported for completeness, no rate derived"
        out[name] = entry
    return out


def main() -> int:
    adaptive = load("line5_adaptive_ab.json")
    scan = load("scan_cohort_ab.json")
    pp = HERE / "scan_cohort_realscan_probe.json"
    probe = json.loads(pp.read_text()) if pp.exists() else None

    ma, ms = mechanism(adaptive), mechanism(scan)
    qa, qs = quality(adaptive), quality(scan)
    ch = changed(scan)
    rec_tok = ms["recovered_tokens"]
    aff = [c for c in ch if c["recovered_tokens"] > 0]

    out = {
        "commit": scan["commit"],
        "question": "Does line 5's value scale with OCR exposure and orphan prevalence?",
        "conditions": {
            "production_corpus_adaptive": {
                "source": "line5_adaptive_ab.json", "commit": adaptive["commit"],
                "documents": adaptive["n_documents"], "pages": adaptive["n_pages"],
                "mechanism": ma, "quality": qa},
            "scan_cohort_adaptive": {
                "source": "scan_cohort_ab.json", "commit": scan["commit"],
                "cohort_rule": scan["cohort_rule"],
                "documents": scan["n_documents"], "pages": scan["n_pages"],
                "mechanism": ms, "quality": qs},
        },
        "distribution": {
            "ocr_page_pct": [ma["ocr_page_pct"], ms["ocr_page_pct"]],
            "ocr_exposure_ratio": round(ms["ocr_page_pct"] / ma["ocr_page_pct"], 2)
            if ma["ocr_page_pct"] else None,
            "orphan_rate": [ma["orphan_rate"], ms["orphan_rate"]],
            "recovery_rate": [ma["recovery_rate"], ms["recovery_rate"]],
            "l5_trigger_rate_pages": [ma["l5_trigger_rate_pages"], ms["l5_trigger_rate_pages"]],
            "recovered_tokens": [ma["recovered_tokens"], ms["recovered_tokens"]],
            "exact_delta": [qa["delta"]["mean_text_recall"], qs["delta"]["mean_text_recall"]],
            "char_delta": [qa["delta"]["mean_char_recall"], qs["delta"]["mean_char_recall"]],
            "exact_delta_per_1000_recovered_tokens": [
                round(qa["delta"]["mean_text_recall"] / ma["recovered_tokens"] * 1000, 6)
                if ma["recovered_tokens"] else None,
                round(qs["delta"]["mean_text_recall"] / rec_tok * 1000, 6) if rec_tok else None],
            "exact_delta_per_affected_document": [
                round(qa["delta"]["mean_text_recall"] / ma["documents_with_recovery"], 6)
                if ma["documents_with_recovery"] else None,
                round(qs["delta"]["mean_text_recall"] / ms["documents_with_recovery"], 6)
                if ms["documents_with_recovery"] else None],
            "ocr_invocations_per_document": [ma["ocr_invocations_per_document"],
                                             ms["ocr_invocations_per_document"]],
        },
        "changed_documents": ch,
        "benchmark_insensitive": [
            {k: c[k] for k in ("document_id", "recovered_tokens", "recovered_elements",
                               "exact_before", "exact_after", "char_before", "char_after",
                               "chars_before", "chars_after")}
            for c in aff if not c["exact_moved"]],
        "real_scan_probe": (
            {k: probe[k] for k in (
                "dataset", "selection", "n_pages_dataset", "n_pages_probed",
                "tokens_recognised", "orphan_tokens", "orphan_rate",
                "recovered_tokens", "recovery_rate", "recovered_elements",
                "table_excluded")}
            | {"note": "mechanism only -- no quality claim, no scorer, no ground truth"}
            if probe else {"note": "not run"}),
        "orphan_rate_by_condition": {
            "production corpus, adaptive router (6.25% of pages OCR'd)": ma["orphan_rate"],
            "rasterized scan cohort, adaptive router (100% OCR'd)": ms["orphan_rate"],
            "real document scans, OmniDocBench english (100% OCR'd)":
                probe["orphan_rate"] if probe else None,
        },
        "regression_audit": regression_audit(scan),
        "strata": strata(scan),
        "must_not_contain_coverage": json.loads(
            (HERE / "scan_cohort_manifest.json").read_text())["must_not_contain_coverage"],
    }
    p = HERE / "scan_cohort_comparison.json"
    p.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(f"wrote {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
