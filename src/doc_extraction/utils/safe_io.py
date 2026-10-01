"""No-follow output operations for the Linux/POSIX production deployment.

Directory descriptors are retained through each write: replacing a path with
a symlink between validation and opening cannot redirect the write. The
deployment must still keep output directories private to the service account.
An attacker running as that account is outside this filesystem boundary.
"""
from __future__ import annotations

import os
import stat
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import IO


class UnsafeOutputPath(ValueError):
    """An output path contains traversal, a symlink, or a non-regular file."""


@contextmanager
def directory_fd(path: Path) -> Iterator[int]:
    if not hasattr(os, "O_NOFOLLOW") or os.open not in os.supports_dir_fd:
        raise UnsafeOutputPath("secure output requires POSIX directory-descriptor support")
    path = path.absolute()
    if ".." in path.parts:
        raise UnsafeOutputPath("output path contains parent traversal")
    descriptor = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            try:
                os.mkdir(part, mode=0o700, dir_fd=descriptor)
            except FileExistsError:
                pass
            try:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            except OSError as exc:
                raise UnsafeOutputPath("output directory contains a symlink or invalid component") from exc
            os.close(descriptor)
            descriptor = child
        yield descriptor
    finally:
        os.close(descriptor)


def secure_mkdir(path: Path) -> None:
    with directory_fd(path):
        pass


@contextmanager
def output_file(path: Path, *, append: bool = False, binary: bool = False) -> Iterator[IO]:
    """Write atomically, or append to a no-follow regular single-link file."""
    with directory_fd(path.parent) as parent:
        try:
            existing = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            existing = None
        if existing is not None and (not stat.S_ISREG(existing.st_mode) or existing.st_nlink != 1):
            raise UnsafeOutputPath("output target must be a regular file with one link")
        name = path.name if append else f".write-{uuid.uuid4().hex}"
        flags = os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW
        flags |= os.O_APPEND if append else os.O_EXCL
        descriptor = os.open(name, flags, 0o600, dir_fd=parent)
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise UnsafeOutputPath("output target changed to a non-regular or linked file")
            os.fchmod(descriptor, 0o600)
            mode = ("a" if append else "w") + ("b" if binary else "")
            with os.fdopen(descriptor, mode, encoding=None if binary else "utf-8", newline=None if binary else "") as stream:
                descriptor = -1
                yield stream
            if not append:
                os.replace(name, path.name, src_dir_fd=parent, dst_dir_fd=parent)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            if not append:
                try:
                    os.unlink(name, dir_fd=parent)
                except FileNotFoundError:
                    pass


def write_text(path: Path, text: str) -> None:
    with output_file(path) as stream:
        stream.write(text)


def remove_output(path: Path) -> None:
    """Unpublish a generated artifact without following its final component."""
    with directory_fd(path.parent) as parent:
        try:
            os.unlink(path.name, dir_fd=parent)
        except FileNotFoundError:
            pass


@contextmanager
def run_lock(output_dir: Path) -> Iterator[None]:
    """Fail immediately if a second process targets the same run directory."""
    try:
        import fcntl
    except ImportError as exc:
        raise UnsafeOutputPath("secure run locking requires POSIX flock support") from exc

    with output_file(output_dir / ".run.lock", append=True) as stream:
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise UnsafeOutputPath("another extraction is writing this output directory") from exc
        try:
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
