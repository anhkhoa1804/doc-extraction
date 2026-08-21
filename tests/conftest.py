from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
_SAMPLE_EXTENSIONS = {"pdf", "docx", "xlsx"}


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def sample_files(repo_root: Path) -> list[Path]:
    """The real, local sample documents under data/. Tests may *read*
    these, never write/rename/move them. Session-local: on a clone without
    any local documents present, this is an empty list rather than an
    error — tests consuming it should handle that (most already do, by
    filtering an empty list down to an empty list)."""
    data_dir = repo_root / "data"
    if not data_dir.is_dir():
        return []
    return sorted(
        p for p in data_dir.iterdir() if p.is_file() and p.suffix.lower().lstrip(".") in _SAMPLE_EXTENSIONS
    )
