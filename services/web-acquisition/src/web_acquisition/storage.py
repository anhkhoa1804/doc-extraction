"""Content-addressed, immutable publication; no URL-derived filesystem paths."""

from __future__ import annotations

import hashlib
import os
import re
import stat
from pathlib import Path
from typing import BinaryIO, Protocol
from uuid import uuid4

from .models import AcquisitionError, Artifact


def private_directory(path: Path) -> int:
    """Retain a no-follow directory descriptor, including all ancestors."""
    path = path.absolute()
    if ".." in path.parts:
        raise AcquisitionError("unsafe_store_path")
    fd = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            try:
                os.mkdir(part, 0o700, dir_fd=fd)
            except FileExistsError:
                pass
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


class Download(Protocol):
    size: int

    @property
    def sha256(self) -> str: ...
    def write(self, data: bytes) -> None: ...
    def read_bounded(self, maximum: int) -> bytes: ...
    def seal(self) -> Artifact: ...
    def discard(self) -> None: ...


class ArtifactStore(Protocol):
    def begin(self, maximum: int) -> Download: ...


class PendingBlob:
    def __init__(self, store: FileArtifactStore, maximum: int):
        self.store = store
        self.maximum = maximum
        self.name = uuid4().hex
        self.fd = os.open(
            self.name,
            os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=store.pending_fd,
        )
        self.stream: BinaryIO = os.fdopen(self.fd, "w+b")
        self.hasher = hashlib.sha256()
        self.size = 0
        self.closed = False

    @property
    def sha256(self) -> str:
        return self.hasher.hexdigest()

    def write(self, data: bytes) -> None:
        if self.closed or self.size + len(data) > self.maximum:
            raise AcquisitionError("too_large")
        self.stream.write(data)
        self.hasher.update(data)
        self.size += len(data)

    def read_bounded(self, maximum: int) -> bytes:
        if self.size > maximum:
            raise AcquisitionError("html_parse_limit")
        self.stream.flush()
        self.stream.seek(0)
        value = self.stream.read(maximum + 1)
        self.stream.seek(0, os.SEEK_END)
        if len(value) > maximum:
            raise AcquisitionError("html_parse_limit")
        return value

    def seal(self) -> Artifact:
        if self.closed:
            raise AcquisitionError("closed_download")
        self.stream.flush()
        os.fsync(self.stream.fileno())
        digest = self.hasher.hexdigest()
        os.fchmod(self.stream.fileno(), 0o400)
        shard = self.store.shard(digest[:2])
        try:
            try:
                os.link(
                    self.name,
                    digest[2:],
                    src_dir_fd=self.store.pending_fd,
                    dst_dir_fd=shard,
                    follow_symlinks=False,
                )
                os.fsync(shard)
            except FileExistsError:
                try:
                    fd = os.open(digest[2:], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=shard)
                except OSError as exc:
                    raise AcquisitionError("artifact_integrity") from exc
                with os.fdopen(fd, "rb") as existing:
                    info = os.fstat(existing.fileno())
                    if not stat.S_ISREG(info.st_mode) or info.st_size != self.size:
                        raise AcquisitionError("artifact_integrity")
                    hasher = hashlib.sha256()
                    while chunk := existing.read(65536):
                        hasher.update(chunk)
                    if hasher.hexdigest() != digest:
                        raise AcquisitionError("artifact_integrity")
        finally:
            os.close(shard)
        artifact = Artifact(
            artifact_id="sha256:" + digest,
            sha256=digest,
            storage_uri=f"sha256/{digest[:2]}/{digest[2:]}",
            size_bytes=self.size,
        )
        self.discard()
        return artifact

    def discard(self) -> None:
        if not self.closed:
            self.closed = True
            self.stream.close()
            os.unlink(self.name, dir_fd=self.store.pending_fd)


class FileArtifactStore:
    def __init__(self, root: Path):
        self.root = root.absolute()
        self.root_fd = private_directory(self.root)
        self.pending_fd = self._child(self.root_fd, ".pending")
        self.cas_fd = self._child(self.root_fd, "sha256")

    @staticmethod
    def _child(parent: int, name: str) -> int:
        try:
            os.mkdir(name, 0o700, dir_fd=parent)
        except FileExistsError:
            pass
        return os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)

    def shard(self, prefix: str) -> int:
        return self._child(self.cas_fd, prefix)

    def begin(self, maximum: int) -> PendingBlob:
        return PendingBlob(self, maximum)

    def copy_verified(self, artifact: Artifact, destination: BinaryIO) -> None:
        if (
            not re.fullmatch("[0-9a-f]{64}", artifact.sha256)
            or artifact.artifact_id != "sha256:" + artifact.sha256
        ):
            raise AcquisitionError("artifact_identity")
        shard = self.shard(artifact.sha256[:2])
        try:
            descriptor = os.open(artifact.sha256[2:], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=shard)
        finally:
            os.close(shard)
        hasher = hashlib.sha256()
        count = 0
        with os.fdopen(descriptor, "rb") as source:
            if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
                raise AcquisitionError("artifact_integrity")
            while chunk := source.read(min(65536, artifact.size_bytes - count + 1)):
                count += len(chunk)
                if count > artifact.size_bytes:
                    raise AcquisitionError("artifact_integrity")
                hasher.update(chunk)
                destination.write(chunk)
        if count != artifact.size_bytes or hasher.hexdigest() != artifact.sha256:
            raise AcquisitionError("artifact_integrity")

    def close(self) -> None:
        os.close(self.pending_fd)
        os.close(self.cas_fd)
        os.close(self.root_fd)
