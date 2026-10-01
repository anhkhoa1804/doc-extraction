"""Bound operational strings without changing extracted document content."""
from __future__ import annotations

import unicodedata


def diagnostic_text(value: object, max_chars: int = 2000) -> str:
    text = str(value)
    visible = "".join(
        ch if ch.isprintable() and unicodedata.category(ch) != "Cf" else ascii(ch)[1:-1]
        for ch in text[:max_chars]
    )
    return visible + (" [truncated]" if len(text) > max_chars else "")
