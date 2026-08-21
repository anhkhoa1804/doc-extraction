#!/usr/bin/env python
"""Regenerate data/manifest.json from the local sample files under data/.

Read-only over the sample files themselves — only ever opens them for
hashing/stat, never writes to them. The manifest is metadata only: name,
size, SHA-256, and detected type. It never contains extracted text or any
other document content.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from doc_extraction.ingest.classifier import detect  # noqa: E402
from doc_extraction.utils.hashing import sha256_file  # noqa: E402
from doc_extraction.utils.serde import write_json  # noqa: E402

_SAMPLE_EXTENSIONS = {"pdf", "docx", "xlsx", "pptx"}


def main() -> None:
    data_dir = REPO_ROOT / "data"
    data_dir.mkdir(exist_ok=True)

    files = []
    for path in sorted(data_dir.iterdir()):
        if not path.is_file() or path.suffix.lower().lstrip(".") not in _SAMPLE_EXTENSIONS:
            continue
        info = detect(path)
        files.append(
            {
                "name": path.name,
                "size": path.stat().st_size,
                "sha256": sha256_file(path),
                "extension": path.suffix.lower(),
                "detected_kind": info.detected_kind,
            }
        )

    out_path = data_dir / "manifest.json"
    write_json(
        out_path,
        {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "files": files,
        },
    )
    print(f"Wrote {out_path} ({len(files)} files)")


if __name__ == "__main__":
    main()
