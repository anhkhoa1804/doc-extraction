"""Is the orphan-token phenomenon an artefact of synthetic scans?

`scan_cohort_ab.py` measures line 5 on documents this repository rasterized
itself. A rasterized born-digital page is a *clean* scan: correct skew, even
illumination, no camera, no fold, no bleed-through. If orphan tokens only
appear on such pages, the scan-heavy result would say nothing about real
scanning.

OmniDocBench's bundled demo set is 18 genuine document page images -- books,
newspapers, magazines, exam papers, handwritten notes, academic PDFs.
Its English subset is used here as an independent check that the mechanism
line 5 addresses exists on real scans too.

This is a MECHANISM PROBE ONLY. It reports orphan prevalence and nothing
else. It makes no quality claim, because:

  * OmniDocBench has no `must_contain` ground truth -- it is scored by an
    external evaluator on edit distance and TEDS, which is not this
    repository's scorer and is not installed here;
  * 10 of the 18 pages are Simplified Chinese against a `vie+eng`
    configuration, so recognition quality on them would measure the language
    configuration, not line 5.

Only pages the demo's own `page_attribute.language` marks `english` are
probed, and no recall number is produced for any of them.

    python experiments/024_ocr_fidelity_recovery/scan_cohort_realscan_probe.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "research/production_corpus"))
sys.path.insert(0, str(REPO / "experiments/023_evidence_centric"))

import run_ab  # noqa: E402
from doc_extraction import cli  # noqa: E402
from doc_extraction.backends.docling_backend import DoclingBackend  # noqa: E402
from doc_extraction.backends.table_backend import TableTransformerBackend  # noqa: E402
from doc_extraction.backends.tesseract_backend import TesseractBackend  # noqa: E402
from doc_extraction.config import PipelineConfig  # noqa: E402
from doc_extraction.pipelines import base as pbase  # noqa: E402

DATASET = REPO / "experiments/005_omnidocbench/dataset/demo"
REAL = pbase._orphan_tokens
RECORD: list[dict] = []
CURRENT = {"name": None}


def hook(regions, ocr_result, tables):
    orphans = REAL(regions, ocr_result, tables)
    unclaimed = [t for t in ocr_result.tokens
                 if not any(pbase._center_in(t.bbox, r.bbox) for r in regions)]
    RECORD.append({
        "image": CURRENT["name"],
        "tokens_recognised": len(ocr_result.tokens),
        "regions": len(regions),
        "tables": len(tables),
        "unclaimed_by_region": len(unclaimed),
        "table_excluded": len(unclaimed) - len(orphans),
        "orphans": len(orphans),
        "orphan_blocks": len(pbase._cluster_orphans(orphans)),
    })
    return orphans


def main() -> int:
    gt = json.loads((DATASET / "OmniDocBench_demo.json").read_text())
    english = [s for s in gt
               if s["page_info"].get("page_attribute", {}).get("language") == "english"]
    print(f"OmniDocBench demo: {len(gt)} pages, {len(english)} tagged english")

    config = run_ab.configure("adaptive", "cpu")
    config.ocr_backend = "__ab_tesseract"
    cli._COMPONENT_BACKEND_CACHE[
        (config.device, tuple(config.ocr_languages), config.ocr_backend)] = (
        DoclingBackend(device="cpu", ocr_languages=PipelineConfig().ocr_languages),
        TesseractBackend(device="cpu", languages=config.ocr_languages),
        TableTransformerBackend(device="cpu"))

    pbase._orphan_tokens = hook
    out_root = HERE / "_runs" / "realscan_probe"
    rows = []
    t0 = time.perf_counter()
    for sample in english:
        name = sample["page_info"]["image_path"]
        path = DATASET / "images" / name
        if not path.exists():
            print(f"  MISSING {name}")
            continue
        CURRENT["name"] = name
        before = len(RECORD)
        started = time.perf_counter()
        try:
            doc = cli.process_file(path, config, output_root=out_root)
            recovered = [e for p in doc.pages for e in (p.elements or [])
                         if (e.extra or {}).get("recovered") == "orphan_ocr_tokens"]
            err = None
        except Exception as exc:  # noqa: BLE001 - a crash is a result
            recovered, err = [], f"{type(exc).__name__}: {exc}"
        rec = RECORD[before:]
        rows.append({
            "image": name,
            "data_source": sample["page_info"]["page_attribute"].get("data_source"),
            "layout": sample["page_info"]["page_attribute"].get("layout"),
            "special_issue": sample["page_info"]["page_attribute"].get("special_issue"),
            "runtime_s": round(time.perf_counter() - started, 2),
            "error": err,
            "tokens": sum(r["tokens_recognised"] for r in rec),
            "orphans": sum(r["orphans"] for r in rec),
            "table_excluded": sum(r["table_excluded"] for r in rec),
            "recovered_elements": len(recovered),
            "recovered_tokens": sum((e.extra or {}).get("token_count", 0) for e in recovered),
        })
        r = rows[-1]
        rate = r["orphans"] / r["tokens"] if r["tokens"] else 0.0
        print(f"  {name[:52]:<54} tokens {r['tokens']:>5} orphans {r['orphans']:>5} "
              f"({rate:6.1%})  blocks {r['recovered_elements']:>3}  {r['runtime_s']:6.2f}s",
              flush=True)
    pbase._orphan_tokens = REAL

    tok = sum(r["tokens"] for r in rows)
    orp = sum(r["orphans"] for r in rows)
    recd = sum(r["recovered_tokens"] for r in rows)
    result = {
        "commit": run_ab.subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                                        text=True, cwd=REPO).stdout.strip(),
        "probe": "mechanism only -- no quality claim, no scorer, no ground truth",
        "dataset": "experiments/005_omnidocbench/dataset/demo (real document page images)",
        "selection": "page_attribute.language == 'english'; the 10 Simplified Chinese "
                     "and 1 mixed pages are excluded because the pipeline is configured "
                     "vie+eng and would measure the language configuration, not line 5",
        "n_pages_dataset": len(gt), "n_pages_probed": len(rows),
        "tokens_recognised": tok, "orphan_tokens": orp,
        "orphan_rate": round(orp / tok, 4) if tok else None,
        "recovered_tokens": recd,
        "recovery_rate": round(recd / orp, 4) if orp else None,
        "table_excluded": sum(r["table_excluded"] for r in rows),
        "recovered_elements": sum(r["recovered_elements"] for r in rows),
        "wall_s": round(time.perf_counter() - t0, 1),
        "cpu_state": run_ab.cpu_state(),
        "rows": rows, "pages": RECORD,
    }
    path = HERE / "scan_cohort_realscan_probe.json"
    path.write_text(json.dumps(result, indent=1, ensure_ascii=False))
    print(f"\nreal scans: {orp}/{tok} tokens orphaned = {orp/tok:.1%}; "
          f"{recd}/{orp} recovered = {recd/orp:.1%}" if tok and orp else "\nno tokens")
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
