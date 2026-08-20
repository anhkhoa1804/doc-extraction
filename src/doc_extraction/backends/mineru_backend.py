"""MinerU (OpenDataLab) backend — documented, NOT installed/verified in the
reference environment.

Why it isn't installed here: MinerU's pip package name has moved between
`magic-pdf` (pre-1.0) and `mineru` (1.0+) across releases, its model weights
are downloaded from ModelScope or HuggingFace and run into multiple GB, and
this dev environment measured ~150 KB/s to PyPI with under 8 GB free on the
system drive — a multi-GB download is not a reasonable thing to attempt
opportunistically. See docs/backends.md for exact install steps to follow
when running this on a better-connected / more disk-rich machine.

This module still defines a real `WholeDocumentBackend`-shaped class so
`doc_extraction compare --backends mineru ...` degrades to a clear,
structured "unavailable" result instead of an import error or a silent
no-op.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

from doc_extraction.pipelines.base import BackendUnavailableError
from doc_extraction.schemas.document import Document


def is_available() -> bool:
    return importlib.util.find_spec("mineru") is not None


class MinerUBackend:
    name = "mineru"

    def is_available(self) -> bool:
        return is_available()

    def convert(self, path: Path, config: Any) -> Document:
        raise BackendUnavailableError(
            "mineru is not installed in this environment. "
            "Install with `pip install -e '.[mineru]'` after verifying the current "
            "package name/version and model download size upstream — see docs/backends.md."
        )
