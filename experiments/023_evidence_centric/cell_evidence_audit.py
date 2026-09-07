"""Was the missing text ever recognized? Acquisition vs ownership, offline.

Experiment 023 left seven documents where no arm reaches full recall. The
milestone's closing claim is that the largest cluster -- tiny text inside
table cells -- fails during *assembly* rather than during *recognition*:
the characters are read and then lost on the way into a cell.

That claim is falsifiable without running anything. For every string a
condition failed to find, this asks two questions of artifacts already on
disk:

    is it in the raw OCR tokens?      -> the recognizer saw it
    is it in the assembled document?  -> the pipeline kept it

    in raw, not in final  ->  ASSEMBLY loss  (evidence ownership)
    not in raw            ->  ACQUISITION loss (evidence acquisition)

Exact containment is brittle across token spacing, so each string is also
scored with the same `char_recall` the A/B uses. A string with high char
recall in raw and low char recall in final was recognized and dropped.

Reads only `_runs/visual/<arm>/<doc>/ocr/page-*.json` and
`.../final/document.json`. No OCR, no model, no GPU.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "research/production_corpus"))

from run_benchmark import _norm  # noqa: E402

from run_ab import char_recall  # noqa: E402

CORPUS = REPO / "research/production_corpus/corpus"
RUNS = HERE / "_runs" / "visual"
ARMS = ("easyocr", "tesseract")


def raw_text(arm: str, doc_dir: str) -> str:
    ocr = RUNS / arm / doc_dir / "ocr"
    parts: list[str] = []
    for page in sorted(ocr.glob("page-*.json")):
        data = json.loads(page.read_text())
        parts.extend(t.get("text", "") for t in data.get("tokens", []))
    return _norm(" ".join(parts))


def final_text(arm: str, doc_dir: str) -> str:
    doc = RUNS / arm / doc_dir / "final" / "document.json"
    if not doc.is_file():
        return ""
    data = json.loads(doc.read_text())
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

    walk(data)
    return _norm(" ".join(parts))


def main() -> int:
    manifest = json.loads((CORPUS / "manifest.json").read_text())
    by_id = {d["document_id"]: d for d in manifest["documents_list"]}
    ab = json.loads((HERE / "ab_visual.json").read_text())
    dirs = {p.name.rsplit("-", 1)[0]: p.name
            for p in (RUNS / "easyocr").iterdir() if p.is_dir()}

    findings, totals = [], {"assembly": 0, "acquisition": 0, "ambiguous": 0}
    for arm in ARMS:
        rows = {r["document_id"]: r for r in ab["conditions"][arm]["rows"]}
        for doc_id, row in sorted(rows.items()):
            if not row["missing"]:
                continue
            doc_dir = dirs.get(doc_id)
            if not doc_dir:
                continue
            raw, fin = raw_text(arm, doc_dir), final_text(arm, doc_dir)
            for s in row["missing"]:
                n = _norm(s)
                r_char, f_char = char_recall(n, raw), char_recall(n, fin)
                # Recognized-but-lost: near-complete in the tokens, materially
                # worse once assembled. The 0.90/0.15 gap is deliberately wide
                # so that only unambiguous cases are counted as assembly loss.
                if r_char >= 0.90 and (r_char - f_char) >= 0.15:
                    verdict = "assembly"
                elif r_char < 0.90:
                    verdict = "acquisition"
                else:
                    verdict = "ambiguous"
                totals[verdict] += 1
                findings.append({
                    "arm": arm, "document_id": doc_id,
                    "labels": by_id[doc_id].get("hard_case_labels", []),
                    "missing_string": s,
                    "char_recall_raw_tokens": round(r_char, 4),
                    "char_recall_final_document": round(f_char, 4),
                    "exact_in_raw": n in raw, "exact_in_final": n in fin,
                    "verdict": verdict,
                })

    out = {"commit": ab.get("commit"), "strategy": "visual", "arms": list(ARMS),
           "totals": totals, "findings": findings}
    (HERE / "cell_evidence_audit.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))

    print(f"{'arm':10s} {'document':30s} {'raw':>6} {'final':>6}  {'verdict':12s} string")
    for f in findings:
        print(f"{f['arm']:10s} {f['document_id']:30s} {f['char_recall_raw_tokens']:>6.3f} "
              f"{f['char_recall_final_document']:>6.3f}  {f['verdict']:12s} {f['missing_string'][:44]!r}")
    print("\ntotals:", totals)
    print("wrote cell_evidence_audit.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
