"""File hashing helpers.

Used to (a) build a stable document_id and (b) record file_hash_sha256 in
run metadata so re-runs and comparisons are keyed on content, not just name.
Sample/input files are only ever opened here for reading — never written to.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

_CHUNK_SIZE = 1024 * 1024


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()
