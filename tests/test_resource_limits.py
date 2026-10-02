from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from pydantic import ValidationError

from doc_extraction.config import PipelineConfig
from doc_extraction.schemas.document import RunMetadata, RunStatus
from doc_extraction.utils.limits import (
    ExtractionLimits,
    ResourceGuard,
    ResourceLimitExceeded,
    active_resource_guard,
    current_runtime_elapsed_seconds,
    preflight_input,
)
from doc_extraction.utils.serde import read_json

from .fixtures import make_image, make_pdf_with_text


def _guard(**overrides: float) -> ResourceGuard:
    return ResourceGuard(ExtractionLimits(**overrides))


def test_input_size_limit_is_checked_before_route_or_hash(tmp_path, monkeypatch):
    from doc_extraction import cli

    source = tmp_path / "oversized.pdf"
    source.write_bytes(b"%PDF-1.7\n" + b"x" * 64)
    config = PipelineConfig(limits=ExtractionLimits(max_input_bytes=16))

    def unexpected_route(*_args, **_kwargs):
        raise AssertionError("route must not run after an input-size rejection")

    monkeypatch.setattr(cli.dispatcher, "route", unexpected_route)
    with pytest.raises(ResourceLimitExceeded, match="max_input_bytes"):
        cli.process_file(source, config, output_root=tmp_path / "output")

    metadata_path = next((tmp_path / "output").glob("rejected-*/metadata.json"))
    metadata = RunMetadata.model_validate(read_json(metadata_path))
    assert metadata.status is RunStatus.FAILED
    assert metadata.resource_violation is not None
    assert metadata.resource_violation["limit_name"] == "max_input_bytes"
    assert metadata.file_hash_sha256 == ""


def test_input_size_boundary_is_inclusive(tmp_path):
    source = make_pdf_with_text(tmp_path / "one.pdf", ["within boundary"])
    size = source.stat().st_size

    preflight_input(source, ExtractionLimits(max_input_bytes=size), _guard(max_input_bytes=size))
    with pytest.raises(ResourceLimitExceeded, match="max_input_bytes"):
        preflight_input(source, ExtractionLimits(max_input_bytes=size - 1), _guard(max_input_bytes=size - 1))


def test_active_guard_exposes_true_elapsed_runtime_for_timeout_diagnostics():
    now = [10.0]
    guard = ResourceGuard(ExtractionLimits(max_runtime_seconds=5), clock=lambda: now[0])
    assert current_runtime_elapsed_seconds() is None
    with active_resource_guard(guard):
        now[0] = 15.25
        assert current_runtime_elapsed_seconds() == 5.25
    assert current_runtime_elapsed_seconds() is None


def test_pdf_page_limit_is_checked_before_page_extraction(tmp_path):
    source = make_pdf_with_text(tmp_path / "two-pages.pdf", ["one", "two"])
    preflight_input(source, ExtractionLimits(max_document_units=2), _guard(max_document_units=2))
    with pytest.raises(ResourceLimitExceeded, match="max_document_units"):
        preflight_input(source, ExtractionLimits(max_document_units=1), _guard(max_document_units=1))


def test_page_limit_is_a_failed_run_with_a_structured_diagnostic(tmp_path):
    from doc_extraction.cli import process_file

    source = make_pdf_with_text(tmp_path / "two-pages.pdf", ["one", "two"])
    with pytest.raises(ResourceLimitExceeded, match="max_document_units"):
        process_file(
            source,
            PipelineConfig(limits=ExtractionLimits(max_document_units=1)),
            output_root=tmp_path / "output",
        )

    metadata_path = next((tmp_path / "output").glob("rejected-*/metadata.json"))
    metadata = RunMetadata.model_validate(read_json(metadata_path))
    assert metadata.status is RunStatus.FAILED
    assert metadata.resource_violation is not None
    assert metadata.resource_violation["limit_name"] == "max_document_units"


def test_image_pixel_limit_is_checked_before_decoding(tmp_path):
    source = make_image(tmp_path / "large.png", (20, 20))
    with pytest.raises(ResourceLimitExceeded, match="max_image_pixels"):
        preflight_input(source, ExtractionLimits(max_image_pixels=399), _guard(max_image_pixels=399))


def test_pdf_raster_reserves_temp_budget_before_writing(tmp_path):
    from doc_extraction.stages.render import render_pdf_pages

    source = make_pdf_with_text(tmp_path / "page.pdf", ["raster budget"])
    rendered = tmp_path / "rendered"
    guard = _guard(max_temp_bytes=1)
    with pytest.raises(ResourceLimitExceeded, match="max_temp_bytes"):
        render_pdf_pages(source, rendered, 72, resource_guard=guard)
    assert not list(rendered.glob("page-*.png"))


def test_runtime_deadline_is_deterministic_at_a_guard_boundary():
    ticks = iter([10.0, 10.5])
    guard = ResourceGuard(ExtractionLimits(max_runtime_seconds=0.25), clock=lambda: next(ticks))
    with pytest.raises(ResourceLimitExceeded, match="max_runtime_seconds") as excinfo:
        guard.check_runtime("test boundary")
    assert excinfo.value.as_dict()["detail"] == "cooperative deadline reached at test boundary"


@pytest.mark.parametrize(
    ("writer", "limits", "expected"),
    [
        (
            lambda path: _write_zip(path, [("word/document.xml", b"x"), ("extra.xml", b"y")]),
            {"max_archive_members": 1},
            "max_archive_members",
        ),
        (
            lambda path: _write_zip(path, [("word/document.xml", b"x" * 100)]),
            {"max_archive_uncompressed_bytes": 50},
            "max_archive_uncompressed_bytes",
        ),
        (
            lambda path: _write_zip(path, [("word/document.xml", b"x" * 10_000)]),
            {"max_archive_compression_ratio": 2},
            "max_archive_compression_ratio",
        ),
        (
            lambda path: _write_zip(path, [("../escape.xml", b"x"), ("word/document.xml", b"x")]),
            {},
            "archive_member_path",
        ),
    ],
)
def test_ooxml_archive_limits_are_enforced_during_preflight(tmp_path, writer, limits, expected):
    source = tmp_path / "unsafe.docx"
    writer(source)
    policy = ExtractionLimits(**limits)
    with pytest.raises(ResourceLimitExceeded, match=expected):
        preflight_input(source, policy, ResourceGuard(policy))


def test_ooxml_sheet_count_is_a_document_unit(tmp_path):
    source = tmp_path / "book.xlsx"
    _write_zip(
        source,
        [
            ("xl/workbook.xml", b"<workbook />"),
            ("xl/worksheets/sheet1.xml", b"<worksheet />"),
            ("xl/worksheets/sheet2.xml", b"<worksheet />"),
        ],
    )
    policy = ExtractionLimits(max_document_units=1)
    with pytest.raises(ResourceLimitExceeded, match="max_document_units"):
        preflight_input(source, policy, ResourceGuard(policy))


@pytest.mark.parametrize("invalid", [{"max_input_bytes": 0}, {"max_runtime_seconds": -1}, {"max_image_pixels": 0}])
def test_limit_configuration_rejects_nonpositive_values(invalid):
    with pytest.raises(ValidationError):
        ExtractionLimits(**invalid)


def _write_zip(path: Path, members: list[tuple[str, bytes]]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members:
            archive.writestr(name, payload)
