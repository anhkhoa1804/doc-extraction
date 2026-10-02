"""Optional public-API seam, never ExtractionPackage v1 or internal parsers."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from .models import AcquisitionError, Artifact, Resource
from .storage import FileArtifactStore

_SUFFIXES = {
    "application/pdf": ".pdf",
    "text/plain": ".txt",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/tiff": ".tiff",
    "image/bmp": ".bmp",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
}


@dataclass(frozen=True)
class ExtractionInput:
    artifact_id: str
    path: Path
    filename: str
    media_type: str | None
    source_url: str
    final_url: str | None
    job_id: str
    resource_id: str


@contextmanager
def extraction_input(
    store: FileArtifactStore, artifact: Artifact, resource: Resource
) -> Iterator[ExtractionInput]:
    if resource.artifact_id != artifact.artifact_id or resource.status != "acquired":
        raise AcquisitionError("unacquired_artifact")
    suffix = _SUFFIXES.get(resource.content_type or "")
    if suffix is None:
        raise AcquisitionError("unsupported_extraction_media_type")
    with TemporaryDirectory(prefix="web-acquisition-extraction-") as directory:
        path = Path(directory) / ("artifact" + suffix)
        with path.open("xb") as destination:
            os.chmod(path, 0o600)
            store.copy_verified(artifact, destination)
        yield ExtractionInput(
            artifact.artifact_id,
            path,
            path.name,
            resource.content_type,
            resource.source_url,
            resource.final_url,
            resource.job_id,
            resource.resource_id,
        )


def extract_with_public_api(value: ExtractionInput, config: Any, output_root: Path) -> Any:
    """Caller must schedule in an extraction worker, not the crawl event loop.

    HTML/text acquisition does not imply doc-extraction supports that format.
    Its own preflight/status/error semantics remain authoritative.
    """
    from doc_extraction.cli import process_file

    return process_file(value.path, config, output_root=output_root)
