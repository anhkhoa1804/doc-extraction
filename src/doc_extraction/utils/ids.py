"""Deterministic, filesystem-safe identifiers."""
from __future__ import annotations

import re
from pathlib import Path

_UNSAFE = re.compile(r"[^a-zA-Z0-9._-]+")


def slugify(name: str) -> str:
    slug = _UNSAFE.sub("-", name).strip("-")
    return slug or "file"


def document_id(path: Path, file_hash: str) -> str:
    """<slugified-stem>-<first 8 hex chars of sha256>.

    The hash suffix keeps two differently-named-but-identical files, or two
    same-named files from different folders, from colliding in outputs/.
    """
    return f"{slugify(path.stem)}-{file_hash[:8]}"
