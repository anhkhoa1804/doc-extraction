"""Step A — What file is this?

Extension + stdlib MIME guess + content-based magic-byte / zip-content
sniffing. Deliberately avoids `python-magic` (needs libmagic, painful on
Windows) — the handful of signatures we actually need (PDF, OOXML zip,
legacy OLE, common raster images) are cheap to check by hand and cover every
format this project routes on.
"""
from __future__ import annotations

import mimetypes
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

# OOXML (zip-based) containers are told apart by a marker entry that only
# that format writes.
_OOXML_MARKERS: dict[str, str] = {
    "word/document.xml": "docx",
    "xl/workbook.xml": "xlsx",
    "ppt/presentation.xml": "pptx",
}

_IMAGE_SIGNATURES: list[tuple[bytes, str]] = [
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff", "jpeg"),
    (b"GIF87a", "gif"),
    (b"GIF89a", "gif"),
    (b"II*\x00", "tiff"),
    (b"MM\x00*", "tiff"),
    (b"BM", "bmp"),
]

_OLE_SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_OLE_LEGACY_BY_EXT = {"doc": "doc_legacy", "xls": "xls_legacy", "ppt": "ppt_legacy"}

_EXTENSION_FALLBACK = {
    "pdf": "pdf",
    "docx": "docx",
    "xlsx": "xlsx",
    "pptx": "pptx",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "tif": "image/tiff",
    "tiff": "image/tiff",
    "bmp": "image/bmp",
}


@dataclass
class FileInfo:
    path: Path
    extension: str
    mime_guess: str | None
    detected_kind: str
    confidence: float
    notes: list[str] = field(default_factory=list)


def _read_header(path: Path, n: int = 8) -> bytes:
    with open(path, "rb") as f:
        return f.read(n)


def detect(path: Path) -> FileInfo:
    """Content-first file type detection. Never opens the file for writing."""
    ext = path.suffix.lower().lstrip(".")
    mime_guess, _ = mimetypes.guess_type(str(path))
    notes: list[str] = []
    header = _read_header(path, 8)

    if header.startswith(b"%PDF"):
        return FileInfo(path, ext, mime_guess or "application/pdf", "pdf", 1.0, notes)

    for signature, kind in _IMAGE_SIGNATURES:
        if header.startswith(signature):
            return FileInfo(path, ext, mime_guess, f"image/{kind}", 1.0, notes)

    if header[:2] == b"PK":
        try:
            with zipfile.ZipFile(path) as zf:
                names = set(zf.namelist())
            for marker, kind in _OOXML_MARKERS.items():
                if marker in names:
                    return FileInfo(path, ext, mime_guess, kind, 1.0, notes)
            notes.append("zip container without a recognized OOXML marker entry")
            return FileInfo(path, ext, mime_guess, "zip_unknown", 0.3, notes)
        except zipfile.BadZipFile:
            notes.append("PK header present but zip could not be opened")
            return FileInfo(path, ext, mime_guess, "unknown", 0.0, notes)

    if header == _OLE_SIGNATURE:
        kind = _OLE_LEGACY_BY_EXT.get(ext, "ole_legacy")
        notes.append(
            "legacy OLE compound file container; exact kind inferred from "
            "extension (unsupported by native parsers in this project)"
        )
        return FileInfo(path, ext, mime_guess, kind, 0.5, notes)

    notes.append("no recognized magic bytes; falling back to file extension")
    kind = _EXTENSION_FALLBACK.get(ext, "unknown")
    confidence = 0.4 if kind != "unknown" else 0.0
    return FileInfo(path, ext, mime_guess, kind, confidence, notes)
