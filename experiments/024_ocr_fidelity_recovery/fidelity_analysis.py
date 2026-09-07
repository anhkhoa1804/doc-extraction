"""LINE 1 -- what are the last 4-5% of characters?

Experiment 023 closed with 58.0% of missed strings in a "fidelity" bucket:
the recognizer produced >=0.90 character recall, assembly preserved it
intact, and the string still did not match exactly. This asks what those
missing characters actually are.

Method. For every `must_contain` string a condition failed to find, the
string is aligned against the best-matching window of the extraction
(`difflib`, the same matcher the A/B's `char_recall` uses), and every
character-level edit in that alignment is classified by mechanism. Both the
raw OCR tokens and the assembled document are analysed, so an edit can be
attributed to recognition or to assembly.

Classification is deliberately conservative and ordered: the first rule
that fits wins, and `substitution` is the catch-all, so a mechanism is only
named when the evidence is unambiguous.

    diacritic       same base letters under NFD, combining marks differ
    case            differs only by case
    unicode_norm    equal under NFC but not codepoint-identical
    digit_letter    a digit against a letter, either direction
    punctuation     both sides punctuation or symbol
    whitespace      whitespace only
    deletion        expected characters absent from the extraction
    insertion       extra characters inside the matched span
    substitution    letter against letter, mechanism not otherwise named

`scorer_artifact` is reported separately and is NOT a classification of an
edit: it is the count of strings that would match if the scorer normalised
more aggressively than `_norm` already does. `_norm` already NFC-normalises
and collapses whitespace runs (experiment 016), so this number is expected
to be near zero -- it exists to prove that, not to license widening the
scorer. Nothing here changes the scorer.

Reads only artifacts already on disk. No OCR, no model, no GPU.
"""
from __future__ import annotations

import difflib
import json
import sys
import unicodedata
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "research/production_corpus"))

from run_benchmark import _norm  # noqa: E402

CORPUS = REPO / "research/production_corpus/corpus"
RUNS = REPO / "experiments/023_evidence_centric/_runs/visual"
AB = REPO / "experiments/023_evidence_centric/ab_visual.json"
ARMS = ("tesseract", "easyocr")

FAILURE_CORPUS = [
    "hc_rotation_vi", "hc_tiny_cells_vi", "cmb_scan_multicol_en",
    "cmb_scan_tiny_vi", "cmb_tiny_table_en", "cmb_scan_stamp_table_vi",
    "cmb_stamp_table_vi",
]


def strip_marks(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if not unicodedata.combining(c))


def classify(exp: str, got: str) -> str:
    if exp == got:
        return "identical"
    if not exp.strip() and not got.strip():
        return "whitespace"
    if not got:
        return "deletion"
    if not exp:
        return "insertion"
    if unicodedata.normalize("NFC", exp) == unicodedata.normalize("NFC", got):
        return "unicode_norm"
    if exp.casefold() == got.casefold():
        return "case"
    if strip_marks(exp).casefold() == strip_marks(got).casefold():
        return "diacritic"
    ed, gd = any(c.isdigit() for c in exp), any(c.isdigit() for c in got)
    ea, ga = any(c.isalpha() for c in exp), any(c.isalpha() for c in got)
    if (ed and ga and not ea) or (gd and ea and not ga):
        return "digit_letter"
    punct = lambda s: all(not c.isalnum() and not c.isspace() for c in s)  # noqa: E731
    if punct(exp) and punct(got):
        return "punctuation"
    return "substitution"


def raw_text(arm: str, doc_dir: str) -> str:
    parts: list[str] = []
    for page in sorted((RUNS / arm / doc_dir / "ocr").glob("page-*.json")):
        parts.extend(t.get("text", "") for t in json.loads(page.read_text()).get("tokens", []))
    return _norm(" ".join(parts))


def final_text(arm: str, doc_dir: str) -> str:
    doc = RUNS / arm / doc_dir / "final" / "document.json"
    if not doc.is_file():
        return ""
    parts: list[str] = []

    def walk(node) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "text" and isinstance(value, str):
                    parts.append(value)
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(json.loads(doc.read_text()))
    return _norm(" ".join(parts))


def edits(needle: str, haystack: str) -> tuple[list[dict], float]:
    """Align `needle` to its best-matching window and return the edits."""
    if not haystack:
        return [{"kind": "deletion", "expected": needle, "got": ""}], 0.0
    sm = difflib.SequenceMatcher(None, needle, haystack, autojunk=False)
    blocks = [b for b in sm.get_matching_blocks() if b.size]
    if not blocks:
        return [{"kind": "deletion", "expected": needle, "got": ""}], 0.0
    lo = max(0, blocks[0].b - blocks[0].a)
    hi = min(len(haystack), blocks[-1].b + blocks[-1].size + (len(needle) - blocks[-1].a))
    window = haystack[lo:hi]
    matched = sum(b.size for b in blocks) / len(needle)
    out = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(
            None, needle, window, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        exp, got = needle[i1:i2], window[j1:j2]
        out.append({"kind": classify(exp, got), "expected": exp, "got": got})
    return out, matched


def main() -> int:
    manifest = json.loads((CORPUS / "manifest.json").read_text())
    by_id = {d["document_id"]: d for d in manifest["documents_list"]}
    ab = json.loads(AB.read_text())
    dirs = {p.name.rsplit("-", 1)[0]: p.name
            for p in (RUNS / "tesseract").iterdir() if p.is_dir()}

    rows, scorer_artifacts = [], []
    for arm in ARMS:
        for r in ab["conditions"][arm]["rows"]:
            doc_id = r["document_id"]
            if not r["missing"] or doc_id not in dirs:
                continue
            raw, fin = raw_text(arm, dirs[doc_id]), final_text(arm, dirs[doc_id])
            for s in r["missing"]:
                n = _norm(s)
                raw_edits, raw_m = edits(n, raw)
                fin_edits, fin_m = edits(n, fin)
                # Would a more aggressive normaliser have matched? Reported,
                # never applied -- see module docstring.
                folded = strip_marks(n).casefold().replace(" ", "")
                if folded and folded in strip_marks(fin).casefold().replace(" ", ""):
                    scorer_artifacts.append({"arm": arm, "document_id": doc_id, "string": s})
                rows.append({
                    "arm": arm, "document_id": doc_id,
                    "in_failure_corpus": doc_id in FAILURE_CORPUS,
                    "labels": by_id[doc_id].get("hard_case_labels", []),
                    "language": by_id[doc_id].get("language"),
                    "string": s,
                    "char_recall_raw": round(raw_m, 4),
                    "char_recall_final": round(fin_m, 4),
                    "raw_edits": raw_edits, "final_edits": fin_edits,
                })

    def tally(key: str, subset) -> dict:
        c = Counter(e["kind"] for r in subset for e in r[key])
        return dict(c.most_common())

    fc = [r for r in rows if r["in_failure_corpus"]]
    tess = [r for r in rows if r["arm"] == "tesseract"]
    tess_fc = [r for r in tess if r["in_failure_corpus"]]

    out = {
        "line": 1, "question": "what are the last 4-5% of characters?",
        "baseline_commit": ab.get("commit"), "strategy": "visual", "arms": list(ARMS),
        "n_missing_strings": len(rows),
        "edit_mechanisms_raw_all": tally("raw_edits", rows),
        "edit_mechanisms_final_all": tally("final_edits", rows),
        "edit_mechanisms_raw_tesseract": tally("raw_edits", tess),
        "edit_mechanisms_raw_tesseract_failure_corpus": tally("raw_edits", tess_fc),
        "scorer_artifacts": {"n": len(scorer_artifacts), "cases": scorer_artifacts},
        "rows": rows,
    }
    (HERE / "fidelity_analysis.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))

    def show(title, d):
        tot = sum(d.values()) or 1
        print(f"\n{title}  (n={tot})")
        for k, v in d.items():
            print(f"  {k:14s} {v:5d}  {100*v/tot:5.1f}%")

    print(f"missing strings analysed: {len(rows)}  (tesseract {len(tess)}, failure-corpus {len(fc)})")
    show("EDIT MECHANISMS -- raw OCR tokens, all arms", out["edit_mechanisms_raw_all"])
    show("EDIT MECHANISMS -- raw OCR tokens, tesseract only", out["edit_mechanisms_raw_tesseract"])
    show("EDIT MECHANISMS -- tesseract, FAILURE CORPUS only", out["edit_mechanisms_raw_tesseract_failure_corpus"])
    print(f"\nscorer artifacts (would match under looser normalisation): {len(scorer_artifacts)}")
    for c in scorer_artifacts[:10]:
        print(f"   {c['arm']:10s} {c['document_id']:26s} {c['string'][:44]!r}")
    print("\nwrote fidelity_analysis.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
