"""Filesystem-level CAS invariants, using real private temporary directories."""

from __future__ import annotations

import hashlib
import os

import pytest
from conftest import Reply

from web_acquisition.models import AcquisitionError, CrawlPolicy
from web_acquisition.storage import FileArtifactStore


def test_same_content_seals_once_and_reuses_identity(tmp_path):
    store = FileArtifactStore(tmp_path / "artifacts")
    try:
        first = store.begin(128)
        first.write(b"shared")
        first_artifact = first.seal()
        second = store.begin(128)
        second.write(b"shared")
        second_artifact = second.seal()
        digest = hashlib.sha256(b"shared").hexdigest()
        assert first_artifact.artifact_id == "sha256:" + digest
        assert second_artifact.artifact_id == first_artifact.artifact_id
        assert second_artifact.storage_uri == first_artifact.storage_uri
        assert second_artifact.size_bytes == first_artifact.size_bytes
        assert (tmp_path / "artifacts" / "sha256" / digest[:2] / digest[2:]).read_bytes() == b"shared"
        assert not list((tmp_path / "artifacts" / ".pending").iterdir())
    finally:
        store.close()


def test_discarded_or_too_large_download_never_creates_artifact(tmp_path):
    store = FileArtifactStore(tmp_path / "artifacts")
    try:
        pending = store.begin(4)
        pending.write(b"part")
        pending.discard()
        rejected = store.begin(4)
        with pytest.raises(AcquisitionError, match="too_large"):
            rejected.write(b"large")
        rejected.discard()
        assert not list((tmp_path / "artifacts" / ".pending").iterdir())
        assert not list((tmp_path / "artifacts" / "sha256").iterdir())
    finally:
        store.close()


def test_symlink_at_existing_digest_is_rejected(tmp_path):
    store = FileArtifactStore(tmp_path / "artifacts")
    try:
        body = b"attacker-controlled"
        digest = hashlib.sha256(body).hexdigest()
        shard = tmp_path / "artifacts" / "sha256" / digest[:2]
        shard.mkdir(exist_ok=True)
        target = tmp_path / "outside"
        target.write_bytes(body)
        os.symlink(target, shard / digest[2:])
        pending = store.begin(128)
        pending.write(body)
        with pytest.raises(AcquisitionError, match="artifact_integrity"):
            pending.seal()
        pending.discard()
        assert not list((tmp_path / "artifacts" / ".pending").iterdir())
    finally:
        store.close()


async def test_publish_exception_never_exposes_artifact_metadata(harness, monkeypatch):
    manager, _server, _transport, _root = await harness({"/": Reply()})

    def fail_publish(*_args):
        raise RuntimeError("injected publish failure")

    monkeypatch.setattr(manager.repository, "publish", fail_publish)
    job = manager.submit(["http://web.example/"], CrawlPolicy(robots_mode="ignore", host_interval=0))
    result = await manager.wait(job.job_id)
    assert result.status == "failed"
    assert result.error_summary == "internal_error"
    assert not manager.repository.artifacts(job.job_id)
