"""Is EasyOCR<->Tesseract agreement a valid verification signal?

The milestone's most important question. `verification.assess_ocr_agreement`
was built on a premise experiment 021 falsified: its two "independent"
sources both resolved OCR through EasyOCR, so it was a recognizer agreeing
with itself and structurally could not witness a character-level error.
Experiment 012 measured r=0.856 between that agreement and recall over 13
documents; that correlation was real but its causal reading was wrong.

Now the pair is genuinely independent. This recomputes agreement over
EasyOCR<->Tesseract and asks what it actually predicts.

Reads the per-page OCR artifacts the A/B run already wrote
(`_runs/<strategy>/<condition>/<doc>/ocr/page-*.json`) rather than
re-running OCR, so the tokens analysed are byte-identical to the ones the
scored pipeline consumed -- no risk of analysing a different run than the
one the conclusions are drawn from.

Outputs, per section 6 of the milestone:
  * the 2x2: who is right when the two disagree
  * calibration: does the agreement score predict correctness
  * does either source's confidence predict which one is right
  * does geometric overlap predict correctness
  * whether the signal behaves differently for table-bearing documents
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "research/production_corpus"))

from doc_extraction.ingest.verification import (  # noqa: E402
    AGREEMENT_SUSPICIOUS_BELOW,
    assess_ocr_agreement,
)
from doc_extraction.schemas.element import BBox  # noqa: E402

from run_benchmark import _norm  # noqa: E402

CORPUS = REPO / "research/production_corpus/corpus"


def load_tokens(run_dir: Path, doc_dir_name: str) -> list[dict]:
    ocr_dir = run_dir / doc_dir_name / "ocr"
    if not ocr_dir.is_dir():
        return []
    tokens: list[dict] = []
    for page_json in sorted(ocr_dir.glob("page-*.json")):
        data = json.loads(page_json.read_text())
        for t in data.get("tokens", []):
            t["_page"] = page_json.stem
            tokens.append(t)
    return tokens


def text_of(tokens: list[dict]) -> str:
    return _norm(" ".join(t["text"] for t in tokens))


# Codepoints present in Vietnamese and absent from English. Used as a cheap
# runtime language signal by the routing experiment; recorded here because
# this is where both engines' text is already loaded.
VI_ONLY = re.compile(r"[ăâđêôơưàáảãạằắẳẵặầấẩẫậèéẻẽẹềếểễệìíỉĩị"
                     r"òóỏõọồốổỗộờớởỡợùúủũụừứửữựỳýỷỹỵ]", re.IGNORECASE)


def vietnameseness(text: str) -> float:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    return round(len(VI_ONLY.findall("".join(letters))) / len(letters), 4)


def _iou(a: dict, b: dict) -> float:
    ba, bb = a["bbox"], b["bbox"]
    ix = max(0.0, min(ba["x1"], bb["x1"]) - max(ba["x0"], bb["x0"]))
    iy = max(0.0, min(ba["y1"], bb["y1"]) - max(ba["y0"], bb["y0"]))
    inter = ix * iy
    area_a = (ba["x1"] - ba["x0"]) * (ba["y1"] - ba["y0"])
    area_b = (bb["x1"] - bb["x0"]) * (bb["y1"] - bb["y0"])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def mean_geometric_overlap(a: list[dict], b: list[dict]) -> float | None:
    """Mean best-match IoU from the coarser stream into the finer one. A
    cheap proxy for 'did the two engines find text in the same places',
    which is a different question from 'did they read it the same way' --
    the milestone asks whether that geometric signal predicts correctness
    independently of the textual one."""
    if not a or not b:
        return None
    sample = a[:200]  # bounded: this is O(n*m) and only needs to be indicative
    best = []
    for ta in sample:
        best.append(max((_iou(ta, tb) for tb in b), default=0.0))
    return sum(best) / len(best) if best else None


def pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 3:
        return None
    try:
        return statistics.correlation(xs, ys)
    except (statistics.StatisticsError, ValueError):
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--strategy", default="visual")
    ap.add_argument("--runs", type=Path, default=Path(__file__).parent / "_runs")
    ap.add_argument("--out", type=Path,
                    default=Path(__file__).parent / "agreement_analysis.json")
    args = ap.parse_args()

    easy_root = args.runs / args.strategy / "easyocr"
    tess_root = args.runs / args.strategy / "tesseract"
    if not easy_root.is_dir() or not tess_root.is_dir():
        print(f"missing run dirs; expected {easy_root} and {tess_root}")
        return 1

    manifest = json.loads((CORPUS / "manifest.json").read_text())
    by_id = {d["document_id"]: d for d in manifest["documents_list"]}
    # output dirs are named "<document_id>-<hash>"
    dirs = {p.name.rsplit("-", 1)[0]: p.name for p in easy_root.iterdir() if p.is_dir()}

    rows = []
    cells = {"both_right": 0, "easyocr_only": 0, "tesseract_only": 0, "both_wrong": 0}
    conf_calls, conf_correct = 0, 0

    for doc_id, dir_name in sorted(dirs.items()):
        entry = by_id.get(doc_id)
        if not entry or not (tess_root / dir_name).is_dir():
            continue
        e_tok, t_tok = load_tokens(easy_root, dir_name), load_tokens(tess_root, dir_name)
        if not e_tok and not t_tok:
            continue
        e_text, t_text = text_of(e_tok), text_of(t_tok)

        verdict = assess_ocr_agreement(e_text, t_text, "easyocr", "tesseract")
        agreement = verdict.score or 0.0

        must = entry["must_contain"]
        per_string = []
        for s in must:
            n = _norm(s)
            e_has, t_has = n in e_text, n in t_text
            key = ("both_right" if e_has and t_has else
                   "easyocr_only" if e_has else
                   "tesseract_only" if t_has else "both_wrong")
            cells[key] += 1
            per_string.append({"string": s, "easyocr": e_has,
                               "tesseract": t_has, "outcome": key})

        e_conf = [t["confidence"] for t in e_tok if t.get("confidence") is not None]
        t_conf = [t["confidence"] for t in t_tok if t.get("confidence") is not None]
        e_mean = sum(e_conf) / len(e_conf) if e_conf else None
        t_mean = sum(t_conf) / len(t_conf) if t_conf else None

        e_recall = sum(1 for p in per_string if p["easyocr"]) / (len(must) or 1)
        t_recall = sum(1 for p in per_string if p["tesseract"]) / (len(must) or 1)

        # Does confidence pick the winner? Only meaningful where the two
        # actually differ in recall -- a tie teaches nothing about the
        # predictor and would inflate accuracy toward 50%.
        if e_mean is not None and t_mean is not None and e_recall != t_recall:
            conf_calls += 1
            picked_t = t_mean >= e_mean
            if (picked_t and t_recall > e_recall) or (not picked_t and e_recall > t_recall):
                conf_correct += 1

        rows.append({
            "document_id": doc_id, "language": entry["language"],
            "difficulty": entry["difficulty"],
            "labels": entry["hard_case_labels"],
            "expected_tables": entry.get("expected_tables", 0),
            "agreement": round(agreement, 4),
            "agreement_status": verdict.status.value,
            "easyocr_recall": round(e_recall, 4), "tesseract_recall": round(t_recall, 4),
            "best_recall": round(max(e_recall, t_recall), 4),
            "min_recall": round(min(e_recall, t_recall), 4),
            "easyocr_mean_conf": round(e_mean, 4) if e_mean is not None else None,
            "tesseract_mean_conf": round(t_mean, 4) if t_mean is not None else None,
            "easyocr_tokens": len(e_tok), "tesseract_tokens": len(t_tok),
            "geometric_overlap": mean_geometric_overlap(e_tok, t_tok),
            "vietnameseness": vietnameseness(e_text),
            "vietnameseness_tesseract": vietnameseness(t_text),
            "per_string": per_string,
        })

    report = build_report(rows, cells, conf_calls, conf_correct)
    args.out.write_text(json.dumps({"rows": rows, "report": report},
                                   indent=1, ensure_ascii=False))
    print_report(rows, report)
    print(f"\nwrote {args.out}")
    return 0


def build_report(rows, cells, conf_calls, conf_correct) -> dict:
    agr = [r["agreement"] for r in rows]
    return {
        "n_documents": len(rows),
        "string_outcomes": cells,
        "disagreements": cells["easyocr_only"] + cells["tesseract_only"],
        "confidence_predictor": {
            "decidable_documents": conf_calls,
            "correct_picks": conf_correct,
            "accuracy": round(conf_correct / conf_calls, 4) if conf_calls else None,
        },
        "correlations": {
            "agreement_vs_min_recall": pearson(agr, [r["min_recall"] for r in rows]),
            "agreement_vs_best_recall": pearson(agr, [r["best_recall"] for r in rows]),
            "geometric_overlap_vs_min_recall": pearson(
                [r["geometric_overlap"] for r in rows if r["geometric_overlap"] is not None],
                [r["min_recall"] for r in rows if r["geometric_overlap"] is not None]),
            "easyocr_conf_vs_easyocr_recall": pearson(
                [r["easyocr_mean_conf"] for r in rows if r["easyocr_mean_conf"] is not None],
                [r["easyocr_recall"] for r in rows if r["easyocr_mean_conf"] is not None]),
            "tesseract_conf_vs_tesseract_recall": pearson(
                [r["tesseract_mean_conf"] for r in rows if r["tesseract_mean_conf"] is not None],
                [r["tesseract_recall"] for r in rows if r["tesseract_mean_conf"] is not None]),
        },
        "calibration": calibration(rows),
        "by_table_presence": {
            "with_tables": subset_stats([r for r in rows if r["expected_tables"] > 0]),
            "without_tables": subset_stats([r for r in rows if r["expected_tables"] == 0]),
        },
        "threshold_behaviour": threshold_stats(rows),
    }


def calibration(rows) -> list[dict]:
    """Mean recall within agreement bands. A useful signal shows recall
    rising monotonically with agreement; a flat profile means the score
    carries no information about correctness."""
    bands = [(0.0, 0.3), (0.3, 0.5), (0.5, 0.7), (0.7, 0.9), (0.9, 1.01)]
    out = []
    for lo, hi in bands:
        sub = [r for r in rows if lo <= r["agreement"] < hi]
        if not sub:
            out.append({"band": f"[{lo},{hi})", "n": 0})
            continue
        out.append({
            "band": f"[{lo},{hi})", "n": len(sub),
            "mean_min_recall": round(sum(r["min_recall"] for r in sub) / len(sub), 4),
            "mean_best_recall": round(sum(r["best_recall"] for r in sub) / len(sub), 4),
            "documents": [r["document_id"] for r in sub],
        })
    return out


def subset_stats(sub) -> dict:
    if not sub:
        return {"n": 0}
    return {"n": len(sub),
            "mean_agreement": round(sum(r["agreement"] for r in sub) / len(sub), 4),
            "corr_agreement_vs_min_recall": pearson(
                [r["agreement"] for r in sub], [r["min_recall"] for r in sub])}


def threshold_stats(rows) -> dict:
    """How the shipped threshold behaves on the new pair: of the documents
    it flags SUSPICIOUS, how many actually have a degraded reading?"""
    flagged = [r for r in rows if r["agreement"] < AGREEMENT_SUSPICIOUS_BELOW]
    clean = [r for r in rows if r["agreement"] >= AGREEMENT_SUSPICIOUS_BELOW]
    return {
        "threshold": AGREEMENT_SUSPICIOUS_BELOW,
        "flagged": len(flagged),
        "flagged_mean_min_recall": (round(sum(r["min_recall"] for r in flagged) / len(flagged), 4)
                                    if flagged else None),
        "flagged_mean_best_recall": (round(sum(r["best_recall"] for r in flagged) / len(flagged), 4)
                                     if flagged else None),
        "unflagged_mean_min_recall": (round(sum(r["min_recall"] for r in clean) / len(clean), 4)
                                      if clean else None),
        "flagged_documents": [r["document_id"] for r in flagged],
    }


def print_report(rows, report) -> None:
    c = report["string_outcomes"]
    total = sum(c.values()) or 1
    print(f"=== EasyOCR <-> Tesseract agreement: {report['n_documents']} documents ===\n")
    print("Who is right, per required string:")
    for k, v in c.items():
        print(f"  {k:<16}{v:>5}  ({v / total:.1%})")
    print(f"  {'disagreements':<16}{report['disagreements']:>5}  "
          f"({report['disagreements'] / total:.1%})")

    cp = report["confidence_predictor"]
    print(f"\nDoes confidence pick the better source? {cp['correct_picks']}/"
          f"{cp['decidable_documents']} = {cp['accuracy']}")

    print("\nCorrelations (Pearson r):")
    for k, v in report["correlations"].items():
        print(f"  {k:<42}{'n/a' if v is None else f'{v:+.4f}'}")

    print("\nCalibration by agreement band:")
    for b in report["calibration"]:
        if b["n"]:
            print(f"  {b['band']:<12}n={b['n']:<4}min_recall={b['mean_min_recall']:.4f}  "
                  f"best_recall={b['mean_best_recall']:.4f}")
        else:
            print(f"  {b['band']:<12}n=0")

    t = report["threshold_behaviour"]
    print(f"\nShipped threshold {t['threshold']}: flags {t['flagged']} documents")
    print(f"  flagged   mean min-recall {t['flagged_mean_min_recall']}  "
          f"best {t['flagged_mean_best_recall']}")
    print(f"  unflagged mean min-recall {t['unflagged_mean_min_recall']}")


if __name__ == "__main__":
    raise SystemExit(main())
