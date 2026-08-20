"""Document VLM backend — interface stub only, no implementation ships by
default.

Why: a usable local document VLM (PaddleOCR-VL, MinerU-VLM, or a general
Qwen2-VL-class model) realistically needs several GB of VRAM for tolerable
latency. The reference environment's GPU (4 GB VRAM, driver limited to CUDA
11.2) can't run one, and the globally installed torch build is CPU-only
besides. Rather than ship a VLM integration nobody can run here, this module
defines the shape a future implementation should have, so a GPU-equipped
follow-up machine has somewhere to drop it in. See docs/backends.md.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from doc_extraction.pipelines.base import BackendUnavailableError
from doc_extraction.schemas.document import Document


def is_available() -> bool:
    return False


class VLMBackend:
    name = "vlm"

    def is_available(self) -> bool:
        return False

    def convert(self, path: Path, config: Any) -> Document:
        raise BackendUnavailableError(
            "No document VLM is configured in this environment (needs a GPU with "
            "several GB of free VRAM). See docs/backends.md for candidate models "
            "and what implementing this would involve."
        )
