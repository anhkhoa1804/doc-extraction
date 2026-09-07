"""COMPOSITE -- lines 5 and 7 applied together, after their individual effects were known.

Line 4 (`--psm 1`) is deliberately NOT folded in here. It changes the
recogniser itself, so it cannot be simulated from artifacts produced at
psm=3; it is measured end to end by `line4_end_to_end.py`. The two are
additive without approximation because they act on disjoint documents:
line 4's screen showed psm=1 changes acquisition on `hc_rotation_vi` and on
no other document in the corpus, and `hc_rotation_vi` is untouched by lines
5 and 7.

The two composed here:

    line 5  stop discarding OCR tokens that no detected layout region claims
    line 7  re-OCR the first column of any detected table whose own mean
            token confidence is below 0.70, at 600 DPI with --psm 6

Both are proxies at the text level: recovered text is appended to the
assembled document rather than routed into elements and cells. That is
sound for measuring *whether the evidence returns* and unsound for
measuring where it lands, so a promotion decision needs the real
implementation and an end-to-end run. The control is measured alongside the
failure corpus precisely so that a proxy which wins by dumping text cannot
pass unnoticed.

CPU only. Re-uses crops already rendered by the line 7 sweep when present.
"""
from __future__ import annotations

import csv
import io
import json
import statistics
import subprocess
import sys
from pathlib import Path

import pymupdf

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "research/production_corpus"))

from doc_extraction.backends.tesseract_backend import to_tesseract_langs  # noqa: E402
from run_benchmark import _norm  # noqa: E402

CORPUS = REPO / "research/production_corpus/corpus"
RUNS = REPO / "experiments/023_evidence_centric/_runs/visual/tesseract"
CROPS = Path("/tmp/claude-1002/-home-leanhkhoa150204/"
             "c332e03d-3ca4-4cd3-a188-684628b67cdf/scratchpad/024_l7b")
LANGS = to_tesseract_langs(["en", "vi"])
CONF_TRIGGER = 0.70
REOCR_DPI, REOCR_PSM = 600, 6
FAILURE_CORPUS = {
    "hc_rotation_vi", "hc_tiny_cells_vi", "cmb_scan_multicol_en",
    "cmb_scan_tiny_vi", "cmb_tiny_table_en", "cmb_scan_stamp_table_vi",
    "cmb_stamp_table_vi",
}


def ocr(image: Path) -> str:
    proc = subprocess.run(["tesseract", str(image), "stdout", "-l", LANGS,
                           "--psm", str(REOCR_PSM), "tsv"],
                          capture_output=True, text=True)
    words = []
    for row in csv.DictReader(io.StringIO(proc.stdout), delimiter="\t",
                              quoting=csv.QUOTE_NONE):
        if (row.get("level") or "").strip() != "5":
            continue
        text = (row.get("text") or "").strip()
        try:
            if text and float(row["conf"]) >= 0:
                words.append(text)
        except (KeyError, TypeError, ValueError):
            continue
    return _norm(" ".join(words))


def final_text(doc_dir: Path) -> str:
    parts: list[str] = []

    def walk(node) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                if k == "text" and isinstance(v, str):
                    parts.append(v)
                else:
                    walk(v)
        elif isinstance(node, list):
            for x in node:
                walk(x)

    walk(json.loads((doc_dir / "final" / "document.json").read_text()))
    return _norm(" ".join(parts))


def centre_in(token: dict, region: dict) -> bool:
    b, r = token["bbox"], region["bbox"]
    cx, cy = (b["x0"] + b["x1"]) / 2, (b["y0"] + b["y1"]) / 2
    return r["x0"] <= cx <= r["x1"] and r["y0"] <= cy <= r["y1"]


def main() -> int:
    CROPS.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((CORPUS / "manifest.json").read_text())
    by_id = {d["document_id"]: d for d in manifest["documents_list"]}
    dirs = {p.name.rsplit("-", 1)[0]: p.name for p in RUNS.iterdir() if p.is_dir()}

    base_fc, base_ct, new_fc, new_ct = [], [], [], []
    calls, gained, lost, per_doc = 0, [], [], {}

    for doc_id, dir_name in sorted(dirs.items()):
        d = RUNS / dir_name
        req = by_id[doc_id]["must_contain"]
        base = final_text(d)
        extra: list[str] = []

        for ocr_page in sorted((d / "ocr").glob("page-*.json")):
            lay = d / "layout" / f"{ocr_page.stem}.json"
            regions = json.loads(lay.read_text()).get("regions", []) if lay.is_file() else []
            extra += [t.get("text", "")
                      for t in json.loads(ocr_page.read_text()).get("tokens", [])
                      if not any(centre_in(t, r) for r in regions)]

        pdf = pymupdf.open(CORPUS / by_id[doc_id]["filename"])
        for tbl_page in sorted((d / "tables").glob("page-*.json")):
            page_no = int(tbl_page.stem.split("-")[1]) - 1
            if page_no >= len(pdf):
                continue
            page = pdf[page_no]
            sx, sy = page.rect.x1 / 1653.0, page.rect.y1 / 2339.0
            toks = json.loads((d / "ocr" / f"{tbl_page.stem}.json").read_text()).get("tokens", [])
            for ti, table in enumerate(json.loads(tbl_page.read_text()).get("tables", [])):
                bb, cells = table.get("bbox"), table.get("cells") or []
                if not bb or not cells:
                    continue
                inside = [k for k in toks
                          if bb["x0"] <= (k["bbox"]["x0"] + k["bbox"]["x1"]) / 2 <= bb["x1"]
                          and bb["y0"] <= (k["bbox"]["y0"] + k["bbox"]["y1"]) / 2 <= bb["y1"]]
                if not inside:
                    continue  # a detected table holding no tokens is a spurious detection
                if statistics.mean(k.get("confidence", 0) or 0 for k in inside) >= CONF_TRIGGER:
                    continue
                spans = sorted({(c["bbox"]["x0"], c["bbox"]["x1"]) for c in cells if c.get("bbox")})
                merged: list[list[float]] = []
                for x0, x1 in spans:
                    if merged and x0 <= merged[-1][1]:
                        merged[-1][1] = max(merged[-1][1], x1)
                    else:
                        merged.append([x0, x1])
                if not merged:
                    continue
                ys = [c["bbox"]["y0"] for c in cells if c.get("bbox")]
                ye = [c["bbox"]["y1"] for c in cells if c.get("bbox")]
                a, b = merged[0]
                clip = pymupdf.Rect(max(0, a * sx - 4), max(0, min(ys) * sy - 4),
                                    min(page.rect.x1, b * sx + 4),
                                    min(page.rect.y1, max(ye) * sy + 4))
                if clip.width <= 1 or clip.height <= 1:
                    continue
                img = CROPS / f"{doc_id}-{page_no}-{ti}-0.png"
                if not img.exists():
                    page.get_pixmap(dpi=REOCR_DPI, clip=clip).save(img)
                extra.append(ocr(img))
                calls += 1

        aug = _norm(base + " " + " ".join(extra)) if extra else base
        b_found = [s for s in req if _norm(s) in base]
        n_found = [s for s in req if _norm(s) in aug]
        (base_fc if doc_id in FAILURE_CORPUS else base_ct).append(len(b_found) / len(req))
        (new_fc if doc_id in FAILURE_CORPUS else new_ct).append(len(n_found) / len(req))
        if doc_id in FAILURE_CORPUS:
            per_doc[doc_id] = {"base": len(b_found), "after": len(n_found), "required": len(req)}
        gained += [{"document_id": doc_id, "string": s} for s in set(n_found) - set(b_found)]
        lost += [{"document_id": doc_id, "string": s} for s in set(b_found) - set(n_found)]

    n = len(dirs)
    out = {
        "experiment": "composite_line5_line7",
        "interventions": ["line5_recover_orphaned_tokens",
                          f"line7_reocr_first_column_when_table_conf<{CONF_TRIGGER}"],
        "excluded": "line4_psm1 -- acts on a disjoint document, measured end to end separately",
        "note": "text-level proxy; recovered text appended, not routed into elements/cells",
        "failure_corpus_recall": {"base": round(statistics.mean(base_fc), 4),
                                  "after": round(statistics.mean(new_fc), 4)},
        "control_recall": {"base": round(statistics.mean(base_ct), 4),
                           "after": round(statistics.mean(new_ct), 4)},
        "cost": {"documents": n, "extra_ocr_calls": calls,
                 "invocations_per_document": round((n + calls) / n, 4)},
        "thresholds": {"acceptance_failure": 0.75, "acceptance_control": 0.9807,
                       "rejection_failure": 0.68, "rejection_control": 0.9757,
                       "max_invocations": 1.10},
        "per_failure_document": per_doc, "gained": gained, "lost": lost,
    }
    (HERE / "composite.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(json.dumps({k: v for k, v in out.items()
                      if k in ("failure_corpus_recall", "control_recall", "cost")}, indent=1))
    print(f"gained {len(gained)}  lost {len(lost)}")
    print("wrote composite.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
