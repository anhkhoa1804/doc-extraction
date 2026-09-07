"""Build the scan-dominant cohort -- frozen BEFORE any comparison is run.

The adaptive validation (`line5_adaptive_ab.py`) established that the shipped
router sends 6.25% of corpus pages to OCR, and that line 5 can only act on
those. The open question is distributional: how much does line 5 help when
OCR exposure is high rather than marginal?

The repository has no scan-dominant scored corpus. Its entire scan
population is 5 image-only PDFs and 2 PNGs -- and 2 of those 5 are precisely
the documents line 5 was already shown to help, so scoring that set would be
circular. OmniDocBench's demo set is real scans but is 10/18 Chinese against
a `vie+eng` configuration and carries no `must_contain` ground truth, so it
can support a mechanism measurement and not a quality one.

So the cohort is CONSTRUCTED, per option 4, by the smallest rule that admits
no selection freedom at all:

    SCAN-49: take all 49 scored PDFs of research/production_corpus -- the
    entire existing scored population, in full. A document whose every page
    is already image-only is copied verbatim. Every other document is
    flattened to images by the corpus generator's OWN `_rasterize`
    (150 DPI, greyscale, JPEG q 58-66, seed 20260902) -- the same function
    and the same parameters that produced `hc_scan_*`.

    IMAGE-2: the corpus's 2 PNGs, which the frozen 49-PDF contract excludes
    and which are the only documents exercising the image route. Reported
    separately, never mixed into the headline number.

Properties of this rule:

* **No leakage.** The selection predicate is "is a scored PDF in the
  production corpus" -- membership is total, so no outcome, orphan count or
  `must_contain` result can influence it. Nothing is chosen; everything is
  taken.
* **No new ground truth.** `must_contain`, `must_not_contain` and
  `expected_tables` carry over unchanged from the source manifest. The
  document content is identical; only its delivery changes.
* **The router is not touched.** A rasterized document has no text layer, so
  the *unmodified* adaptive router sends it down `scanned_pdf` on its own.
  This is the production path, not a `--strategy visual` override of it.
* **Paired.** Every cohort document has a same-document counterpart in the
  49-document adaptive result, so deltas can be read per document rather
  than only in aggregate.

What the rule cannot do: a rasterized born-digital page is a *clean* scan.
It reproduces the routing and the layout-detection conditions of a scan, not
the degradation of a real one. That limit is stated in the README and is why
the OmniDocBench probe exists alongside it.

    python experiments/024_ocr_fidelity_recovery/scan_cohort_build.py
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "research/production_corpus"))

import pymupdf  # noqa: E402

import generate  # noqa: E402  -- the corpus's own generator, imported not copied

SRC = REPO / "research/production_corpus/corpus"
OUT = HERE / "_runs" / "scan_cohort_corpus"
SCAN_DPI = 150  # generate.DocSpec.scan_dpi default, unchanged


def image_only_pages(path: Path) -> tuple[int, int]:
    """(pages, pages with no usable text layer). The threshold is the
    router's own `digital_pdf_min_chars_per_page`, so 'image-only' here
    means what the shipped dispatcher means by it."""
    doc = pymupdf.open(path)
    per = [len((p.get_text() or "").strip()) for p in doc]
    doc.close()
    return len(per), sum(1 for c in per if c < 40)


def main() -> int:
    manifest = json.loads((SRC / "manifest.json").read_text())
    src_docs = manifest["documents_list"]

    OUT.mkdir(parents=True, exist_ok=True)
    for stale in OUT.glob("*"):
        stale.unlink()

    entries = []
    for entry in src_docs:
        name = entry["filename"]
        is_pdf = name.lower().endswith(".pdf")
        is_png = name.lower().endswith(".png")
        if not (is_pdf or is_png) or not entry["must_contain"]:
            continue
        src = SRC / name
        if not src.exists():
            continue

        if is_png:
            stratum, action = "IMAGE-2", "copied (already an image)"
            shutil.copyfile(src, OUT / name)
            pages, imgonly = 1, 1
        else:
            pages, imgonly = image_only_pages(src)
            if imgonly == pages:
                stratum, action = "SCAN-49", "copied (already image-only)"
                shutil.copyfile(src, OUT / name)
            else:
                stratum, action = "SCAN-49", f"rasterized at {SCAN_DPI} DPI"
                doc = pymupdf.open(src)
                flat = generate._rasterize(doc, dpi=SCAN_DPI, noisy=True)
                generate._save_pdf(flat, OUT / name)  # closes `flat` itself
                _, imgonly = image_only_pages(OUT / name)

        dst = OUT / name
        out_pages, out_imgonly = (
            (1, 1) if is_png else image_only_pages(dst)
        )
        entries.append({
            **{k: entry[k] for k in (
                "document_id", "filename", "format", "language", "document_type",
                "page_count", "hard_case_labels", "difficulty", "must_contain",
                "must_not_contain", "expected_tables")},
            "stratum": stratum,
            "action": action,
            "source_sha256": entry["sha256"],
            "source_pages": pages,
            "source_image_only_pages": (1 if is_png else imgonly if action.startswith("copied") else None),
            "cohort_pages": out_pages,
            "cohort_image_only_pages": out_imgonly,
            "sha256": hashlib.sha256(dst.read_bytes()).hexdigest(),
            "bytes": dst.stat().st_size,
        })

    scan49 = [e for e in entries if e["stratum"] == "SCAN-49"]
    image2 = [e for e in entries if e["stratum"] == "IMAGE-2"]
    out = {
        "cohort": "scan-dominant-024-L5-generalization",
        "built_by": "experiments/024_ocr_fidelity_recovery/scan_cohort_build.py",
        "source_corpus": "research/production_corpus/corpus (manifest version "
                         f"{manifest['version']}, seed {manifest['seed']})",
        "selection_rule": (
            "Total membership, no selection freedom: SCAN-49 is every scored PDF "
            "of the production corpus (49/49); IMAGE-2 is both of its scored PNGs. "
            "A document already image-only on every page is copied verbatim; every "
            "other is flattened by the corpus generator's own _rasterize at "
            f"{SCAN_DPI} DPI, greyscale, JPEG q58-66, seed {generate.SEED}. "
            "must_contain / must_not_contain / expected_tables carry over unchanged. "
            "No document is selected on any observed outcome."
        ),
        "rasterizer": "research/production_corpus/generate.py::_rasterize (imported, not copied)",
        "scan_dpi": SCAN_DPI,
        "seed": generate.SEED,
        "strata": {
            "SCAN-49": {"documents": len(scan49),
                        "pages": sum(e["cohort_pages"] for e in scan49),
                        "image_only_pages": sum(e["cohort_image_only_pages"] for e in scan49),
                        "rasterized": sum(1 for e in scan49 if e["action"].startswith("rasterized")),
                        "already_image_only": sum(1 for e in scan49 if e["action"].startswith("copied"))},
            "IMAGE-2": {"documents": len(image2),
                        "pages": sum(e["cohort_pages"] for e in image2)},
        },
        "must_not_contain_coverage": {
            "documents_with_any": sum(1 for e in entries if e["must_not_contain"]),
            "total_strings": sum(len(e["must_not_contain"]) for e in entries),
            "documents": len(entries),
        },
        "documents_list": entries,
    }
    path = HERE / "scan_cohort_manifest.json"
    path.write_text(json.dumps(out, indent=1, ensure_ascii=False))

    print(json.dumps(out["strata"], indent=1))
    print("must_not_contain coverage:", json.dumps(out["must_not_contain_coverage"]))
    print(f"corpus -> {OUT}")
    print(f"manifest -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
