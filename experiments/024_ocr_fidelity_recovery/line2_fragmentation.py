"""LINE 2 -- is correct OCR evidence fragmented across tokens?

If a required string is present in the recognizer's output but split across
tokens that the assembler joins with a space it should not have inserted
(`"A" "-" "100"` -> `"A - 100"`), then a deterministic join rule recovers it
for free. This measures whether that is happening, before any code changes.

Three joins are compared against the baseline, on the same token streams the
scored pipeline consumed:

    J0  " ".join                      -- what `_gather_region_text` does today
    J1  gap-aware                     -- no space when the horizontal gap to
                                         the next token is below `gap_ratio`
                                         of the left token's mean glyph width
                                         and both sit in one line band
    J2  punctuation-aware             -- no space either side of - / : . when
                                         the neighbouring tokens are adjacent
    J3  J1 + J2

Scored on the frozen contract's split: the 7-document failure corpus and the
42-document control. A rule that gains on the failure corpus and loses on the
control is rejected -- that is the whole point of measuring both.

This is a raw-token proxy for an assembly-side change, not an end-to-end run.
A rule that shows no gain here cannot show one end to end, so a zero result
is decisive; a non-zero result would have to be implemented and re-measured
through the full pipeline before any promotion.

Reads artifacts already on disk. No OCR, no model, no GPU.
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "research/production_corpus"))

from run_benchmark import _norm  # noqa: E402

CORPUS = REPO / "research/production_corpus/corpus"
RUNS = REPO / "experiments/023_evidence_centric/_runs/visual/tesseract"
AB = REPO / "experiments/023_evidence_centric/ab_visual.json"

FAILURE_CORPUS = [
    "hc_rotation_vi", "hc_tiny_cells_vi", "cmb_scan_multicol_en",
    "cmb_scan_tiny_vi", "cmb_tiny_table_en", "cmb_scan_stamp_table_vi",
    "cmb_stamp_table_vi",
]
GAP_RATIO = 0.30
BAND_OVERLAP = 0.5
GLUE = set("-/:.")


def bands(tokens: list[dict]) -> list[list[dict]]:
    """Same line-band construction the production assembler uses."""
    out: list[dict] = []
    for t in sorted(tokens, key=lambda t: (t["bbox"]["y0"], t["bbox"]["x0"])):
        b = t["bbox"]
        for band in out:
            ov = min(band["y1"], b["y1"]) - max(band["y0"], b["y0"])
            short = min(band["y1"] - band["y0"], b["y1"] - b["y0"])
            if ov > 0 and short > 0 and ov >= BAND_OVERLAP * short:
                band["toks"].append(t)
                band["y0"], band["y1"] = min(band["y0"], b["y0"]), max(band["y1"], b["y1"])
                break
        else:
            out.append({"y0": b["y0"], "y1": b["y1"], "toks": [t]})
    return [sorted(b["toks"], key=lambda t: t["bbox"]["x0"])
            for b in sorted(out, key=lambda b: b["y0"])]


def join(tokens: list[dict], gap_aware: bool, punct_aware: bool) -> str:
    parts: list[str] = []
    for band in bands(tokens):
        for i, t in enumerate(band):
            txt = t.get("text", "")
            if not txt:
                continue
            if parts:
                glue = False
                if i > 0:
                    prev = band[i - 1]
                    gap = t["bbox"]["x0"] - prev["bbox"]["x1"]
                    if gap_aware:
                        w = (prev["bbox"]["x1"] - prev["bbox"]["x0"]) / max(len(prev.get("text", "") or "x"), 1)
                        if gap <= GAP_RATIO * w:
                            glue = True
                    if punct_aware and gap <= 2.0 * (
                            (prev["bbox"]["x1"] - prev["bbox"]["x0"]) / max(len(prev.get("text", "") or "x"), 1)):
                        if (prev.get("text", "")[-1:] in GLUE) or (txt[:1] in GLUE):
                            glue = True
                parts.append(("" if glue else " ") + txt)
            else:
                parts.append(txt)
    return _norm("".join(parts))


def doc_text(doc_dir: Path, gap_aware: bool, punct_aware: bool) -> str:
    out = []
    for page in sorted((doc_dir / "ocr").glob("page-*.json")):
        out.append(join(json.loads(page.read_text()).get("tokens", []), gap_aware, punct_aware))
    return _norm(" ".join(out))


def main() -> int:
    manifest = json.loads((CORPUS / "manifest.json").read_text())
    by_id = {d["document_id"]: d for d in manifest["documents_list"]}
    ab = json.loads(AB.read_text())
    dirs = {p.name.rsplit("-", 1)[0]: p.name for p in RUNS.iterdir() if p.is_dir()}

    rules = {"J0_space": (False, False), "J1_gap": (True, False),
             "J2_punct": (False, True), "J3_gap_punct": (True, True)}
    results, changed = {}, []
    for name, (ga, pa) in rules.items():
        fc, ctl = [], []
        for doc_id, dir_name in dirs.items():
            req = by_id[doc_id]["must_contain"]
            if not req:
                continue
            text = doc_text(RUNS / dir_name, ga, pa)
            found = [s for s in req if _norm(s) in text]
            (fc if doc_id in FAILURE_CORPUS else ctl).append(len(found) / len(req))
            if name == "J0_space":
                results.setdefault("_baseline_found", {})[doc_id] = set(found)
            else:
                base = results["_baseline_found"][doc_id]
                gained, lost = set(found) - base, base - set(found)
                if gained or lost:
                    changed.append({"rule": name, "document_id": doc_id,
                                    "in_failure_corpus": doc_id in FAILURE_CORPUS,
                                    "gained": sorted(gained), "lost": sorted(lost)})
        results[name] = {"failure_corpus_recall": round(statistics.mean(fc), 4),
                         "control_recall": round(statistics.mean(ctl), 4),
                         "n_failure": len(fc), "n_control": len(ctl)}
    results.pop("_baseline_found")
    out = {"line": 2, "question": "is correct OCR evidence fragmented across tokens?",
           "note": "raw-token proxy for an assembly-side join change, not an end-to-end run",
           "gap_ratio": GAP_RATIO, "glue_chars": sorted(GLUE),
           "rules": results, "changed_strings": changed}
    (HERE / "line2_fragmentation.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))

    print(f"{'rule':16s} {'failure':>9s} {'control':>9s}   (raw-token proxy)")
    for name in rules:
        r = results[name]
        print(f"{name:16s} {r['failure_corpus_recall']:>9.4f} {r['control_recall']:>9.4f}")
    print(f"\nstrings gained/lost vs J0: {len(changed)}")
    for c in changed[:20]:
        print(f"  {c['rule']:14s} {'FC' if c['in_failure_corpus'] else '  '} {c['document_id']:26s} "
              f"gained={c['gained']} lost={c['lost']}")
    print("\nwrote line2_fragmentation.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
