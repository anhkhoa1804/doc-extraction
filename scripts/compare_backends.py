#!/usr/bin/env python
"""Thin wrapper for environments without `make`:

    python scripts/compare_backends.py --input . --backends docling

is equivalent to:

    python -m doc_extraction compare --input . --backends docling
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from doc_extraction.cli import build_parser  # noqa: E402

if __name__ == "__main__":
    parsed = build_parser().parse_args(["compare", *sys.argv[1:]])
    sys.exit(parsed.func(parsed))
