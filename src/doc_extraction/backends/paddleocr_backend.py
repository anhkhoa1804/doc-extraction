"""PaddleOCR / PP-Structure backend — documented, NOT installed/verified in
the reference environment.

Why it isn't installed here: PaddlePaddle is a separate deep learning
framework from the torch stack the rest of this project already carries, its
Windows wheel + PP-Structure model downloads are a non-trivial addition on a
system with under 8 GB free on the OS drive, and it has a history of
Windows-specific install friction (a VC++ redistributable requirement,
occasional numpy version pinning conflicts). See docs/backends.md for exact
install steps.

Defines a real `LayoutBackend` / `OCRBackend` / `TableBackend`-shaped class
(PP-Structure covers all three) and a `WholeDocumentBackend`, all of which
raise a clear, structured error rather than failing on import.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

from doc_extraction.pipelines.base import BackendUnavailableError, LayoutResult, OCRResult, PageInput, Region, TableResult
from doc_extraction.schemas.document import Document

_INSTALL_HINT = (
    "paddleocr/paddlepaddle are not installed in this environment. "
    "Install with `pip install -e '.[paddle]'` — see docs/backends.md for "
    "Windows-specific notes before doing so."
)


def is_available() -> bool:
    return (
        importlib.util.find_spec("paddleocr") is not None
        and importlib.util.find_spec("paddle") is not None
    )


class PaddleOCRBackend:
    name = "paddleocr"

    def is_available(self) -> bool:
        return is_available()

    def convert(self, path: Path, config: Any) -> Document:
        raise BackendUnavailableError(_INSTALL_HINT)

    def analyze(self, page: PageInput) -> LayoutResult:
        raise BackendUnavailableError(_INSTALL_HINT)

    def recognize(self, page: PageInput) -> OCRResult:
        raise BackendUnavailableError(_INSTALL_HINT)

    def extract(self, page: PageInput, regions: list[Region]) -> TableResult:
        raise BackendUnavailableError(_INSTALL_HINT)
