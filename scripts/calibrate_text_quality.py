#!/usr/bin/env python
"""Calibration harness for the PDF text-quality heuristic.

Prints, for every PDF in a directory, the per-page signal values from
`doc_extraction.ingest.text_quality`. Used to set the thresholds in
`TextQualityThresholds` against real observed data rather than guesses, and
to re-check them when the corpus changes.

Read-only: opens input PDFs for reading only, writes nothing except the
optional --json report.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pymupdf  # noqa: E402

from doc_extraction.ingest.text_quality import assess_text  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=".", help="Directory (or single PDF) to scan.")
    parser.add_argument("--json", help="Optional path to write the full report as JSON.")
    parser.add_argument("--max-pages", type=int, default=3, help="Pages per document to sample.")
    args = parser.parse_args()

    root = Path(args.input)
    paths = [root] if root.is_file() else sorted(p for p in root.iterdir() if p.suffix.lower() == ".pdf")

    report = []
    for path in paths:
        doc = pymupdf.open(path)
        try:
            for page_index in range(min(doc.page_count, args.max_pages)):
                text = doc[page_index].get_text()
                assessment = assess_text(text)
                row = {"file": path.name, "page": page_index + 1, **assessment.as_dict()}
                top_scripts = sorted(row["scripts_seen"].items(), key=lambda kv: -kv[1])[:3]
                row["scripts_seen"] = dict(top_scripts)
                report.append(row)
                print(
                    f"{'SUSPECT' if row['suspicious'] else 'ok     '} "
                    f"{path.name[:44]:<44} p{page_index + 1} "
                    f"chars={row['n_chars']:>6} "
                    f"mixed={row['mixed_script_word_ratio']:.3f} "
                    f"unexp={row['unexpected_script_ratio']:.3f} "
                    f"alpha={row['alpha_ratio']:.3f} "
                    f"dig={row['digit_in_word_ratio']:.3f} "
                    f"scripts={[s for s, _ in top_scripts]}"
                )
        finally:
            doc.close()

    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nWrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
