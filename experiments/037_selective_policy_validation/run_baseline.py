#!/usr/bin/env python
"""Render frozen 037 source PDFs and run the unchanged production baseline.

This is pre-treatment feature generation only.  It never invokes the
experimental forced-crop helper and writes only beneath the ignored results
root.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import pymupdf

# Cached production checkpoints are a prerequisite for this repository's
# reproducible offline runs.  Do not let a transient DNS lookup alter a run.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))

from doc_extraction.cli import process_file  # noqa: E402
from doc_extraction.config import load_config  # noqa: E402


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--document", action="append", dest="documents")
    args = parser.parse_args()
    manifest_path = HERE / "population_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    result_root = HERE / "results"
    inputs = result_root / "prepared_inputs"
    runs = result_root / "baseline_runs"
    inputs.mkdir(parents=True, exist_ok=True)
    runs.mkdir(parents=True, exist_ok=True)
    config = load_config(ROOT / "configs/cpu.yaml")
    render_metadata = []
    for record in manifest["records"]:
        if args.documents and record["document_id"] not in args.documents:
            continue
        source = ROOT / "research/production_corpus/corpus" / record["source_file"]
        image = inputs / f"{record['document_id']}.png"
        if not image.exists():
            pdf = pymupdf.open(source)
            pix = pdf[0].get_pixmap(dpi=record["render_dpi"], alpha=False)
            pix.save(image)
        # Rendering via the same pinned PyMuPDF source is deterministic enough
        # for a run identity; record the actual emitted image hash regardless.
        record["rendered_image"] = str(image.relative_to(ROOT))
        record["rendered_image_sha256"] = sha256(image)
        scale = record["render_dpi"] / 72.0
        box = record["source_table_bbox_points"]
        record["gt_table_bbox_px"] = {k: round(v * scale, 6) for k, v in box.items()}
        out = runs / record["document_id"]
        if not (out / "final/document.json").exists():
            process_file(image, config=config, output_dir=out)
        render_metadata.append({"document_id": record["document_id"], "image_sha256": record["rendered_image_sha256"], "run": str(out.relative_to(ROOT))})
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    (result_root / "baseline_run_index.json").write_text(json.dumps(render_metadata, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
