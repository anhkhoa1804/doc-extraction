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
    """The real, immutable sample documents at the repo root. Tests may
    *read* these, never write/rename/move them."""
    return sorted(
        p for p in repo_root.iterdir() if p.is_file() and p.suffix.lower().lstrip(".") in _SAMPLE_EXTENSIONS
    )
