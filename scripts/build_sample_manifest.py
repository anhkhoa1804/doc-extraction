#!/usr/bin/env python
"""Regenerate samples/MANIFEST.json from the immutable sample files at the
repo root. Read-only over the sample files themselves — only ever opens them
for hashing/stat, never writes to them.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from doc_extraction.ingest.classifier import detect  # noqa: E402
from doc_extraction.utils.hashing import sha256_file  # noqa: E402
from doc_extraction.utils.serde import write_json  # noqa: E402

_SAMPLE_EXTENSIONS = {"pdf", "docx", "xlsx", "pptx"}


def main() -> None:
    entries = []
    for path in sorted(REPO_ROOT.iterdir()):
        if not path.is_file() or path.suffix.lower().lstrip(".") not in _SAMPLE_EXTENSIONS:
            continue
        info = detect(path)
        entries.append(
            {
                "filename": path.name,
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
                "detected_kind": info.detected_kind,
                "extension": info.extension,
            }
        )
    out_path = REPO_ROOT / "samples" / "MANIFEST.json"
    write_json(out_path, {"samples": entries})
    print(f"Wrote {out_path} ({len(entries)} files)")


if __name__ == "__main__":
    main()
