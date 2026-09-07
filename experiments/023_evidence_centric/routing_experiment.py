"""Can a deterministic router get most of the quality without paying for both engines?

Milestone question Q4. Conditions C/D/E all invoke both recognizers on every
page; if a router can pick the right single engine most of the time, the
system gets heterogeneous-evidence quality at close to single-engine cost.

Method: the router chooses, per document, among arms the A/B already
measured end-to-end. Quality is then that arm's real full-pipeline score --
not a re-derived text-level estimate -- and cost is that arm's real OCR
invocation count. This keeps routing honest: a policy cannot invent a
quality it did not actually produce.

The hard constraint is that every routing signal must be computable at
runtime, with no ground truth. Signals used:

    easyocr mean confidence     from OCRToken.confidence
    tesseract mean confidence   same field, same 0-1 scale
    token counts                cheap density proxy
    cross-engine agreement      verification.assess_ocr_agreement
    vietnameseness              share of Vietnamese-only codepoints in the
                                cheap engine's own output

`vietnameseness` deserves a warning and gets one in the results: it is read
off EasyOCR's text, and EasyOCR is the engine that *drops* Vietnamese tone
marks (experiment 021). A language signal derived from the failing engine
is partly self-defeating, which is itself worth measuring rather than
assuming either way.

Policies compared (section 10):
    P0  easyocr always                      (single-engine baseline)
    P1  tesseract always                    (single-engine baseline)
    P2  tesseract when easyocr confidence is low
    P3  tesseract when the page looks Vietnamese
    P4  fusion when the two disagree, else easyocr   (needs both to decide)
    P5  composite failure-risk trigger
    P6  oracle: best arm per document       (upper bound, not a policy)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

# Codepoints that exist in Vietnamese and not in English -- precomposed
# vowels with tone marks, plus đ. Presence of these in a reading is
# evidence the page is Vietnamese AND that the engine resolved tone marks.
VI_ONLY = re.compile(r"[ăâđêôơưàáảãạằắẳẵặầấẩẫậèéẻẽẹềếểễệìíỉĩị"
                     r"òóỏõọồốổỗộờớởỡợùúủũụừứửữựỳýỷỹỵ]", re.IGNORECASE)


def vietnameseness(text: str) -> float:
    letters = [c for c in unicodedata.normalize("NFC", text) if c.isalpha()]
    if not letters:
        return 0.0
    return len(VI_ONLY.findall("".join(letters))) / len(letters)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ab", type=Path, default=Path(__file__).parent / "ab_visual.json")
    ap.add_argument("--agreement", type=Path,
                    default=Path(__file__).parent / "agreement_analysis.json")
    ap.add_argument("--conf-threshold", type=float, default=0.75)
    ap.add_argument("--vi-threshold", type=float, default=0.02)
    ap.add_argument("--agree-threshold", type=float, default=0.5)
    ap.add_argument("--tess-conf-threshold", type=float, default=0.90,
                    help="P6/P7 escalation trigger on tesseract's own mean confidence")
    ap.add_argument("--out", type=Path,
                    default=Path(__file__).parent / "routing_experiment.json")
    args = ap.parse_args()

    ab = json.loads(args.ab.read_text())
    agr = {r["document_id"]: r for r in json.loads(args.agreement.read_text())["rows"]}

    arms = {name: {r["document_id"]: r for r in data["rows"]}
            for name, data in ab["conditions"].items()}
    if "easyocr" not in arms or "tesseract" not in arms:
        print("need at least easyocr and tesseract arms in the A/B results")
        return 1

    doc_ids = sorted(arms["easyocr"])
    # Per-arm OCR cost in engine invocations: single engines cost 1, every
    # composite runs both.
    cost = {"easyocr": 1, "tesseract": 1, "selection": 2, "union": 2,
            "fusion": 2, "fusion_recovery": 2}

    def signals(doc_id: str) -> dict:
        a = agr.get(doc_id, {})
        return {
            "easyocr_conf": a.get("easyocr_mean_conf"),
            "tesseract_conf": a.get("tesseract_mean_conf"),
            "agreement": a.get("agreement"),
            "vietnameseness": a.get("vietnameseness"),
            "easyocr_tokens": a.get("easyocr_tokens"),
        }

    policies = {
        "P0_easyocr_always": lambda s: "easyocr",
        "P1_tesseract_always": lambda s: "tesseract",
        "P2_tesseract_if_low_easyocr_conf": lambda s: (
            "tesseract" if (s["easyocr_conf"] is not None
                            and s["easyocr_conf"] < args.conf_threshold) else "easyocr"),
        "P3_tesseract_if_vietnamese": lambda s: (
            "tesseract" if (s["vietnameseness"] or 0.0) >= args.vi_threshold else "easyocr"),
        "P4_fusion_if_disagree": lambda s: (
            "fusion" if (s["agreement"] is not None
                         and s["agreement"] < args.agree_threshold) else "easyocr"),
        "P5_composite_risk": lambda s: composite(s, args),
        # P6/P7 invert the default. Every policy above assumes EasyOCR is
        # the cheap engine to start from, which was true when this file was
        # written and is false: measured on this corpus's own pages,
        # Tesseract costs 0.73 s/page on CPU against EasyOCR's 17.63 s/page,
        # and scores higher. So the cheap engine escalates to the expensive
        # one, not the other way round. The trigger is Tesseract's own mean
        # page confidence -- a signal available after one engine has run,
        # unlike cross-engine agreement, which costs both engines to compute
        # and therefore cannot save anything.
        "P6_tesseract_first_escalate_to_fusion": lambda s: (
            "fusion" if (s["tesseract_conf"] is not None
                         and s["tesseract_conf"] < args.tess_conf_threshold)
            else "tesseract"),
        "P7_tesseract_first_escalate_to_easyocr": lambda s: (
            "easyocr" if (s["tesseract_conf"] is not None
                          and s["tesseract_conf"] < args.tess_conf_threshold)
            else "tesseract"),
    }

    results = {"commit": ab.get("commit"), "strategy": ab.get("strategy"),
               "thresholds": {"confidence": args.conf_threshold,
                              "vietnameseness": args.vi_threshold,
                              "agreement": args.agree_threshold},
               "available_arms": sorted(arms), "policies": {}}

    for name, fn in policies.items():
        chosen, recalls, chars, costs, halluc = {}, [], [], [], 0
        for doc_id in doc_ids:
            arm = fn(signals(doc_id))
            if arm not in arms:          # arm not run; fall back to easyocr
                arm = "easyocr"
            row = arms[arm][doc_id]
            chosen[doc_id] = arm
            recalls.append(row["text_recall"])
            chars.append(row["char_recall"])
            costs.append(cost[arm])
            halluc += 1 if row["hallucinated"] else 0
        results["policies"][name] = summarize(name, chosen, recalls, chars, costs, halluc)

    # Threshold sweep for the escalation policies. A single threshold read
    # off these same 49 documents is an in-sample choice; reporting the
    # curve shows whether the operating point is a plateau or a spike.
    sweep = []
    for th in (0.80, 0.85, 0.88, 0.90, 0.92, 0.94, 0.95, 0.96, 1.01):
        for target in ("fusion", "easyocr"):
            if target not in arms:
                continue
            chosen, recalls, chars, costs, halluc = {}, [], [], [], 0
            for doc_id in doc_ids:
                c = signals(doc_id)["tesseract_conf"]
                arm = target if (c is not None and c < th) else "tesseract"
                row = arms[arm][doc_id]
                chosen[doc_id] = arm
                recalls.append(row["text_recall"]); chars.append(row["char_recall"])
                costs.append(cost[arm]); halluc += 1 if row["hallucinated"] else 0
            entry = summarize(f"th={th}->{target}", chosen, recalls, chars, costs, halluc)
            entry.pop("choices")
            entry["threshold"] = th
            entry["escalate_to"] = target
            sweep.append(entry)
    results["escalation_sweep"] = sweep

    # Oracle: the best arm per document. Not a policy -- it needs the answer
    # -- but it bounds what any router could achieve on these arms.
    chosen, recalls, chars, costs, halluc = {}, [], [], [], 0
    for doc_id in doc_ids:
        best_arm = max(arms, key=lambda a: (arms[a][doc_id]["text_recall"],
                                            arms[a][doc_id]["char_recall"]))
        row = arms[best_arm][doc_id]
        chosen[doc_id] = best_arm
        recalls.append(row["text_recall"]); chars.append(row["char_recall"])
        costs.append(cost[best_arm]); halluc += 1 if row["hallucinated"] else 0
    results["policies"]["ORACLE_best_arm"] = summarize(
        "ORACLE_best_arm", chosen, recalls, chars, costs, halluc)
    results["policies"]["ORACLE_best_arm"]["note"] = (
        "upper bound only -- selects using the ground truth a router cannot see")

    args.out.write_text(json.dumps(results, indent=1, ensure_ascii=False))

    print(f"{'policy':<34}{'recall':>8}{'char':>8}{'halluc':>8}{'cost':>7}{'quality/cost':>14}")
    for name, p in results["policies"].items():
        print(f"{name:<34}{p['mean_text_recall']:>8.4f}{p['mean_char_recall']:>8.4f}"
              f"{p['documents_hallucinated']:>8}{p['mean_ocr_invocations']:>7.2f}"
              f"{p['recall_per_invocation']:>14.4f}")
    print(f"\n{'escalation sweep (tesseract-first)':<34}{'recall':>8}{'char':>8}"
          f"{'cost':>7}{'escalated':>11}")
    for e in results["escalation_sweep"]:
        n_esc = e["arm_counts"].get(e["escalate_to"], 0)
        print(f"  tessConf<{e['threshold']:<6} -> {e['escalate_to']:<14}"
              f"{e['mean_text_recall']:>8.4f}{e['mean_char_recall']:>8.4f}"
              f"{e['mean_ocr_invocations']:>7.2f}{n_esc:>11}")
    print(f"\nwrote {args.out}")
    return 0


def composite(s: dict, args) -> str:
    """P5 -- escalate only when several cheap signals agree the page is at
    risk, rather than on any single one. Deliberately conservative: the
    milestone's objective is quality per unit compute, so a trigger that
    fires everywhere is a failure even if its quality is high."""
    risk = 0
    if s["easyocr_conf"] is not None and s["easyocr_conf"] < args.conf_threshold:
        risk += 1
    if (s["vietnameseness"] or 0.0) >= args.vi_threshold:
        risk += 1
    if s["agreement"] is not None and s["agreement"] < args.agree_threshold:
        risk += 1
    if risk >= 2:
        return "fusion"
    if risk == 1:
        return "tesseract"
    return "easyocr"


def summarize(name, chosen, recalls, chars, costs, halluc) -> dict:
    n = len(recalls) or 1
    mean_recall = sum(recalls) / n
    mean_cost = sum(costs) / n
    counts: dict[str, int] = {}
    for arm in chosen.values():
        counts[arm] = counts.get(arm, 0) + 1
    return {"mean_text_recall": round(mean_recall, 4),
            "mean_char_recall": round(sum(chars) / n, 4),
            "documents_hallucinated": halluc,
            "mean_ocr_invocations": round(mean_cost, 4),
            "recall_per_invocation": round(mean_recall / mean_cost, 4),
            "arm_counts": counts,
            "documents_perfect": sum(1 for r in recalls if r == 1.0),
            "documents_zero": sum(1 for r in recalls if r == 0.0),
            "choices": chosen}


if __name__ == "__main__":
    raise SystemExit(main())
