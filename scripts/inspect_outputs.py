#!/usr/bin/env python
"""Thin wrapper for environments without `make`:

    python scripts/inspect_outputs.py <document_id>

is equivalent to:

    python -m doc_extraction inspect <document_id>
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from doc_extraction.cli import build_parser  # noqa: E402

if __name__ == "__main__":
    parsed = build_parser().parse_args(["inspect", *sys.argv[1:]])
    sys.exit(parsed.func(parsed))
