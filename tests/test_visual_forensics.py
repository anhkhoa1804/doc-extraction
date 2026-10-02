"""Model-free tests at the real Classic stage/adapter/assembly boundaries."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from PIL import Image

from doc_extraction.backends.docling_backend import DoclingBackend
from doc_extraction.cli import process_file
from doc_extraction.config import PipelineConfig
from doc_extraction.evaluation.omnidocbench import page_to_prediction_markdown
from doc_extraction.pipelines import base
from doc_extraction.pipelines.base import (
    BackendUnavailableError,
    LayoutResult,
    OCRResult,
    OCRToken,
    PageInput,
    Region,
    TableResult,
    run_scanned_page_pipeline,
)
from doc_extraction.schemas.element import BBox
from doc_extraction.schemas.table import Cell, Table
from doc_extraction.utils.visual_forensics import (
    MAX_BYTES,
    MAX_LABELS,
    MAX_PAGES,
    MAX_REGIONS,
    MAX_TOKENS,
    VisualForensics,
    VisualPageTrace,
    summarize_traces,
)
from tests.backend_conformance import assert_document_conforms

BOX = BBox(x0=1, y0=1, x1=40, y1=40)


class Components:
    name = "fixture"

    def __init__(self, regions=None, tokens=None, tables=None, available=True):
        self.regions = regions or []
        self.tokens = tokens or []
        self.tables = tables or []
        self.available = available

    def is_available(self):
        return self.available

    def analyze(self, page):
        return LayoutResult(deepcopy(self.regions), self.name)

    def recognize(self, page):
        return OCRResult(deepcopy(self.tokens), self.name)

    def extract(self, page, regions):
        return TableResult(tables=deepcopy(self.tables), backend=self.name)


def run_page(tmp_path, components, ocr=None, tables=None):
    image = tmp_path / "image.png"
    Image.new("RGB", (50, 70), "white").save(image)
    recorder = VisualForensics(tmp_path / "out")
    page = run_scanned_page_pipeline(
        image, 0, 200, components, ocr or components, tables or components,
        tmp_path / "out", forensics=recorder,
    )
    recorder.persist()
    return page, recorder, recorder.pages[0].data


def test_zero_layout_regions_are_observed_not_inferred(tmp_path):
    _, _, trace = run_page(tmp_path, Components())
    assert trace["layout"]["regions"] == 0
    assert trace["ocr"]["component_calls"] == 1
    assert trace["ocr"]["projected_tokens"] == 0
    assert trace["ocr"]["model_invocations"] is None


def test_formula_layout_ocr_not_invoked_is_distinct_from_zero_result(tmp_path):
    image = tmp_path / "image.png"
    Image.new("RGB", (50, 70)).save(image)
    recorder = VisualForensics(tmp_path)
    with pytest.raises(BackendUnavailableError):
        run_scanned_page_pipeline(
            image, 0, 200, Components([Region(BOX, "formula")]),
            Components(available=False), Components(), tmp_path, forensics=recorder,
        )
    recorder.persist()
    trace = recorder.pages[0].data
    assert trace["formula"]["regions"] == 1
    assert trace["ocr"]["component_calls"] == 0
    assert trace["ocr"]["state"] == "backend_unavailable"
    assert trace["ocr"]["projected_tokens"] is None


def test_formula_layout_invoked_ocr_zero_and_null_canonical_text(tmp_path):
    page, recorder, trace = run_page(tmp_path, Components([Region(BOX, "formula")]))
    assert trace["ocr"]["component_calls"] == 1
    assert trace["ocr"]["state"] == "returned"
    assert trace["ocr"]["projected_tokens"] == 0
    assert trace["ocr"]["raw_tokens"] is None
    assert trace["ocr"]["target_regions"] is None
    assert trace["canonical"]["null_text"] == 1
    assert trace["canonical"]["warnings_count"] == 1
    assert page.elements[0].text is None
    assert summarize_traces([json.loads(recorder.path.read_text())])["formula_only_zero_projected_ocr"] == 1


def test_projected_tokens_reach_canonical_without_source_text_in_trace(tmp_path):
    secret_text = "private source text should not appear in operational diagnostics"
    page, recorder, trace = run_page(tmp_path, Components(
        [Region(BOX, "text")], [OCRToken(secret_text, BOX)],
    ))
    assert page.elements[0].text == secret_text
    assert trace["ocr"]["tokens_by_region"][0]["tokens"] == 1
    assert trace["canonical"]["text_bearing"] == 1
    assert secret_text not in recorder.path.read_text()


def test_simulated_downstream_text_loss_is_visible(tmp_path, monkeypatch):
    original = base.merge_regions_into_page

    def discard(*args, **kwargs):
        page = original(*args, **kwargs)
        for element in page.elements:
            element.text = None
        return page

    monkeypatch.setattr(base, "merge_regions_into_page", discard)
    _, recorder, trace = run_page(tmp_path, Components([Region(BOX, "text")], [OCRToken("known", BOX)]))
    assert trace["ocr"]["projected_tokens"] == 1
    assert trace["canonical"]["text_bearing"] == 0
    summary = summarize_traces([json.loads(recorder.path.read_text())])
    assert summary["projected_ocr_without_canonical_text"] == 1


def test_zero_layout_without_ocr_dispatch_does_not_claim_zero_tokens(tmp_path):
    from doc_extraction.stages.layout import run_layout

    trace = VisualPageTrace(0, 50, 70, "visual")
    page = PageInput(0, 50, 70, visual_trace=trace)
    run_layout(page, Components(), tmp_path)
    assert trace.data["layout"]["regions"] == 0
    assert trace.data["ocr"]["state"] == "not_reached"
    assert trace.data["ocr"]["projected_tokens"] is None


def test_zero_layout_does_not_invent_actual_ocr_target_count(tmp_path):
    # Current Docling does NOT expose target regions. Do not infer them from
    # projected layout. A fake reader can report the actual invocation input
    # in its own test harness; the production trace deliberately stays unknown.
    _, _, trace = run_page(tmp_path, Components())
    assert trace["layout"]["regions"] == 0
    assert trace["ocr"]["component_calls"] == 1
    assert trace["ocr"]["target_regions"] is None


def test_scanned_pdf_visual_route_is_traced(tmp_path, monkeypatch):
    from doc_extraction.pipelines.pdf import parse_scanned_pdf

    images = []
    for index in range(2):
        image = tmp_path / f"image-{index}.png"
        Image.new("RGB", (50, 70)).save(image)
        images.append(image)
    monkeypatch.setattr("doc_extraction.pipelines.pdf.render_pdf_pages", lambda *args: images)
    recorder = VisualForensics(tmp_path)
    components = Components([Region(BOX, "text")], [OCRToken("known", BOX)])
    pages = parse_scanned_pdf(tmp_path / "scanned.pdf", 200, components, components,
                              components, tmp_path, forensics=recorder)
    assert [page.index for page in pages] == [0, 1]
    assert [trace.data["route"] for trace in recorder.pages.values()] == ["scanned_pdf"] * 2


def test_visual_pdf_fallback_is_traced(tmp_path, monkeypatch):
    from doc_extraction.pipelines.pdf import _apply_page_fallback
    from doc_extraction.schemas.page import Page

    image = tmp_path / "image.png"
    Image.new("RGB", (50, 70)).save(image)
    monkeypatch.setattr("doc_extraction.pipelines.pdf.render_single_pdf_page", lambda *args: image)
    recorder = VisualForensics(tmp_path)
    components = Components([Region(BOX, "text")], [OCRToken("known", BOX)])
    pages = _apply_page_fallback(
        tmp_path / "digital.pdf", [Page(index=0, width=50, height=70)], [0], PipelineConfig(),
        tmp_path, components, components, components, None, forensics=recorder,
    )
    assert pages[0].source_route == "digital_pdf+page_fallback"
    assert recorder.pages[0].data["route"] == "digital_pdf+page_fallback"


def test_trace_summary_cli_is_bounded_and_diagnostic_only(tmp_path, capsys):
    from scripts.summarize_visual_traces import main

    _, recorder, _ = run_page(tmp_path, Components([Region(BOX, "formula")]))
    assert main([str(recorder.path)]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["patterns"]["formula_only_zero_projected_ocr"] == 1
    assert output["omitted_pages"] == 0
    recorder.path.write_bytes(b"x" * (MAX_BYTES + 1))
    with pytest.raises(SystemExit) as exc:
        main([str(recorder.path)])
    assert exc.value.code == 2


def test_trace_summary_cli_rejects_old_stage_artifacts(tmp_path):
    from scripts.summarize_visual_traces import main

    path = tmp_path / "layout.json"
    path.write_text('{"regions": []}')
    with pytest.raises(SystemExit) as exc:
        main([str(path)])
    assert exc.value.code == 2


def test_explicit_order_omission_is_visible_without_changing_serializer(tmp_path):
    from doc_extraction.schemas.document import Document, RunMetadata
    from doc_extraction.schemas.element import Element, ElementType
    from doc_extraction.schemas.page import Page

    page = Page(index=0, width=50, height=70, reading_order=["selected"], elements=[
        Element(id="selected", type=ElementType.TEXT, text="emitted", source_backend="fixture"),
        Element(id="omitted", type=ElementType.TEXT, text="missing from export", source_backend="fixture"),
    ])
    metadata = RunMetadata(input_filename="fixture.png", input_path="fixture.png", file_hash_sha256="a" * 64,
                           file_type="image", route="image", pipeline="baseline", backend="fixture", timestamp="fixed")
    document = Document(document_id="fixture", metadata=metadata, pages=[page])
    before = document.to_markdown()
    recorder = VisualForensics(tmp_path)
    trace = recorder.page(0, 50, 70, "image")
    recorder.assembled(document, before)
    assert trace.data["canonical"]["text_bearing"] == 2
    assert trace.data["serialization"]["ordered_text_bearing"] == 1
    assert trace.data["serialization"]["omitted_text_bearing"] == 1
    assert document.to_markdown() == before
    assert "missing from export" not in before


def test_observer_failure_cannot_alter_extraction(tmp_path):
    components = Components([Region(BOX, "text")], [OCRToken("known", BOX)])

    def fail_observation(page):
        raise ValueError("private dependency state")

    components.visual_forensic_snapshot = fail_observation
    page, recorder, trace = run_page(tmp_path, components)
    assert page.elements[0].text == "known"
    assert trace["dependency_observation_failed"] is True
    assert "private dependency state" not in recorder.path.read_text()


def test_malformed_optional_observation_cannot_replace_pipeline_error(tmp_path):
    trace = VisualPageTrace(0, 10, 20, "visual")
    trace.layout_result(NS(regions=None, warnings=[]))
    assert trace.data["observation_failed"] is True
    assert trace.data["layout"]["regions"] is None
    recorder = VisualForensics(tmp_path)
    recorder.assembled(None, "")
    recorder.persist()
    assert json.loads(recorder.path.read_text())["observation_failed"] is True


def cached_docling(tmp_path, monkeypatch, text="", geometry=True, enrichment=False, retained=None):
    image = tmp_path / "docling.png"
    Image.new("RGB", (50, 70)).save(image)
    box = NS(l=1, t=1, r=40, b=40, coord_origin="TOPLEFT")
    item = NS(label="formula", text=text, prov=[NS(bbox=box)] if geometry else [])
    document = NS(pages={}, iterate_items=lambda **kwargs: iter([(item, 0)]))
    backend = DoclingBackend(ocr_languages=["en", "vi"])
    backend._page_cache[str(image)] = NS(document=document, pages=[NS(parsed_page=retained)])
    backend._converter = NS(format_to_options={"image": NS(pipeline_options=NS(
        do_ocr=True, do_formula_enrichment=enrichment, ocr_options=NS(lang=["en", "vi"]),
    ))})
    monkeypatch.setattr(backend, "is_available", lambda: True)
    return image, backend


def test_actual_docling_adapter_formula_configuration_and_unavailable_raw_ocr(tmp_path, monkeypatch):
    image, backend = cached_docling(tmp_path, monkeypatch)
    recorder = VisualForensics(tmp_path)
    page = run_scanned_page_pipeline(image, 0, 200, backend, backend, Components(), tmp_path, forensics=recorder)
    trace = recorder.pages[0].data
    dep = trace["dependency"]
    assert dep["configured_ocr_languages"] == ["en", "vi"]
    assert dep["formula_enrichment_enabled"] is False
    assert dep["public_items_examined"] == 1
    assert dep["public_items_with_text"] == 0
    assert dep["retained_ocr_cells"] is None
    assert trace["formula"]["text_results"] == 0
    assert trace["formula"]["model_invocations"] is None
    assert page.elements[0].text is None


def test_actual_docling_adapter_preserves_available_formula_text(tmp_path, monkeypatch):
    image, backend = cached_docling(tmp_path, monkeypatch, text="x + y", enrichment=True)
    recorder = VisualForensics(tmp_path)
    page = run_scanned_page_pipeline(image, 0, 200, backend, backend, Components(), tmp_path, forensics=recorder)
    assert page.elements[0].text == "x + y"
    assert recorder.pages[0].data["formula"]["text_results"] == 1
    assert recorder.pages[0].data["dependency"]["formula_enrichment_enabled"] is True


def test_docling_public_text_without_geometry_exposes_projection_loss(tmp_path, monkeypatch):
    image, backend = cached_docling(tmp_path, monkeypatch, text="available", geometry=False)
    recorder = VisualForensics(tmp_path)
    page = run_scanned_page_pipeline(image, 0, 200, backend, backend, Components(), tmp_path, forensics=recorder)
    trace = recorder.pages[0].data
    assert trace["dependency"]["public_items_with_text"] == 1
    assert trace["dependency"]["public_text_items_without_geometry"] == 1
    assert trace["ocr"]["projected_tokens"] == 0
    assert not page.elements  # absence is not replaced by fabricated geometry


@pytest.mark.parametrize("cells,expected", [([], 0), ([NS(from_ocr=True)], 1)])
def test_retained_docling_cells_zero_vs_unknown(tmp_path, monkeypatch, cells, expected):
    image, backend = cached_docling(tmp_path, monkeypatch, retained=NS(textline_cells=cells))
    snapshot = backend.visual_forensic_snapshot(PageInput(0, 50, 70, image_path=image))
    assert snapshot["retained_ocr_cells"] == expected


def test_trace_observer_never_converts_an_uncached_image(tmp_path, monkeypatch):
    backend = DoclingBackend()
    monkeypatch.setattr(backend, "_get_converter", lambda: pytest.fail("observer must not load a model"))
    assert backend.visual_forensic_snapshot(PageInput(0, 1, 1, image_path=tmp_path / "uncached.png")) is None


def test_config_snapshot_reads_instantiated_image_options_not_mutated_requested_languages(tmp_path, monkeypatch):
    image, backend = cached_docling(tmp_path, monkeypatch)
    backend.ocr_languages = ["ch_sim"]
    backend._converter.format_to_options["pdf"] = NS(pipeline_options=NS(
        do_formula_enrichment=True, ocr_options=NS(lang=["wrong-format"]),
    ))
    snapshot = backend.visual_forensic_snapshot(PageInput(0, 50, 70, image_path=image))
    assert snapshot["requested_ocr_languages"] == ["ch_sim"]
    assert snapshot["configured_ocr_languages"] == ["en", "vi"]
    assert snapshot["formula_enrichment_enabled"] is False


def test_table_tokens_keep_table_ownership_with_trace(tmp_path):
    table = Table(id="p0-t0", n_rows=1, n_cols=1, bbox=BOX, source_backend="fixture",
                  cells=[Cell(row=0, col=0, bbox=BOX, text="")])
    page, _, trace = run_page(tmp_path, Components(
        [Region(BOX, "table"), Region(BBox(x0=0, y0=0, x1=50, y1=70), "text")],
        [OCRToken("cell", BOX), OCRToken("outside", BBox(x0=42, y0=45, x1=48, y1=50))], [table],
    ))
    assert page.tables[0].cells[0].text == "cell"
    assert "cell" not in [e.text for e in page.elements]
    assert [e.text for e in page.elements if e.text] == ["outside"]
    assert trace["table"]["text_cells"] == 1
    assert trace["ocr"]["projected_tokens"] == 2


def test_public_api_trace_on_off_and_repeat_have_identical_content(tmp_path, monkeypatch):
    image = tmp_path / "input.png"
    Image.new("RGB", (50, 70)).save(image)
    components = Components([Region(BOX, "text")], [OCRToken("known", BOX)])
    monkeypatch.setattr("doc_extraction.cli._get_component_backends", lambda config: (components,) * 3)
    outputs, traces = [], []
    for index, enabled in enumerate([False, True, True]):
        out = tmp_path / str(index)
        doc = process_file(image, PipelineConfig(visual_forensics=enabled), output_dir=out)
        assert_document_conforms(doc)
        data = doc.model_dump(mode="json")
        # Intentionally ephemeral identity and rendering location, unrelated
        # to observations, vary between the three isolated output directories.
        data.pop("document_id")
        for key in ["timestamp", "runtime_seconds"]:
            data["metadata"].pop(key)
        for page in data["pages"]:
            page.pop("rendered_image_path")
        outputs.append(data)
        trace_path = out / "diagnostics" / "classic_visual_trace.json"
        if enabled:
            trace = json.loads(trace_path.read_text())
            assert trace["input_sha256"] == doc.metadata.file_hash_sha256
            assert trace["run"].pop("metadata_timestamp") == doc.metadata.timestamp
            traces.append(trace)
        else:
            assert not trace_path.exists()
    assert outputs[0] == outputs[1] == outputs[2]
    assert traces[0] == traces[1]
    assert traces[0]["pages"][0]["serialization"]["ordered_text_bearing"] == 1
    assert traces[0]["export"]["markdown_bytes"] > 0


def test_failed_ocr_trace_is_persisted_without_changing_failure(tmp_path, monkeypatch):
    image = tmp_path / "input.png"
    Image.new("RGB", (50, 70)).save(image)
    components = Components([Region(BOX, "text")])

    def crash(page):
        raise RuntimeError("private error content")

    monkeypatch.setattr(components, "recognize", crash)
    monkeypatch.setattr("doc_extraction.cli._get_component_backends", lambda config: (components,) * 3)
    out = tmp_path / "out"
    with pytest.raises(RuntimeError, match="private error content"):
        process_file(image, PipelineConfig(visual_forensics=True), output_dir=out)
    path = out / "diagnostics" / "classic_visual_trace.json"
    trace = json.loads(path.read_text())["pages"][0]
    assert trace["ocr"]["state"] == "failed"
    assert trace["ocr"]["exception_type"] == "RuntimeError"
    assert trace["ocr"]["projected_tokens"] is None
    assert trace["canonical"] is None
    assert "private error content" not in path.read_text()
    assert json.loads((out / "metadata.json").read_text())["status"] == "failed"
    assert json.loads(path.read_text())["run"]["status"] == "failed"
    assert not (out / "final" / "document.json").exists()


def test_bounds_labels_regions_tokens_pages_bytes_and_privacy(tmp_path):
    recorder = VisualForensics(tmp_path)
    regions = [Region(BOX, f"label-{i}") for i in range(MAX_REGIONS + 1)]
    ocr = OCRResult([OCRToken("NEVER LOG", BOX)] * (MAX_TOKENS + 1))
    template = VisualPageTrace(0, 50, 70, "visual")
    template.layout_result(LayoutResult(regions))
    template.ocr_result(ocr, regions)
    for index in range(MAX_PAGES + 1):
        trace = recorder.page(index, 50, 70, "visual")
        if trace is not None:
            trace.data = deepcopy(template.data)
            trace.data["page_index"] = index
    recorder.persist()
    payload = json.loads(recorder.path.read_text())
    assert recorder.path.stat().st_size <= MAX_BYTES
    assert len(payload["pages"]) <= MAX_PAGES
    assert payload["omitted_pages"] >= 1
    assert len(payload["pages"][0]["layout"]["labels"]["counts"]) == MAX_LABELS
    assert len(payload["pages"][0]["ocr"]["tokens_by_region"]) == MAX_REGIONS
    assert payload["pages"][0]["ocr"]["token_counts_truncated"] is True
    assert "NEVER LOG" not in recorder.path.read_text()


def test_retained_layout_cells_can_distinguish_loss_before_public_projection(tmp_path, monkeypatch):
    image, backend = cached_docling(tmp_path, monkeypatch)
    backend._page_cache[str(image)].pages[0].predictions = NS(layout=NS(clusters=[
        NS(label="formula", cells=[NS(text="already recognized")]),
    ]))
    snapshot = backend.visual_forensic_snapshot(PageInput(0, 50, 70, image_path=image))
    assert snapshot["retained_layout_cells_with_text"] == 1
    assert snapshot["retained_formula_cells_with_text"] == 1
    assert snapshot["public_items_with_text"] == 0
    assert snapshot["retained_ocr_cells"] is None


def test_diagnostic_symlink_not_followed_and_failure_does_not_raise(tmp_path):
    recorder = VisualForensics(tmp_path / "out")
    recorder.page(0, 10, 20, "visual")
    recorder.path.parent.mkdir(parents=True)
    target = tmp_path / "untouched"
    target.write_text("original")
    recorder.path.symlink_to(target)
    recorder.persist()
    assert recorder.persistence_failed
    assert target.read_text() == "original"


def test_unexpected_observer_fields_are_not_persisted(tmp_path):
    trace = VisualPageTrace(0, 10, 20, "visual")
    trace.observe_dependency(NS(visual_forensic_snapshot=lambda page: {
        "arbitrary_secret": "DO NOT LOG", "ocr_backend": "easyocr\n\x1b[31m",
        "configured_ocr_languages": ["en", "vi"], "formula_enrichment_enabled": False,
        "public_items_with_text": "untrusted text",
    }), None)
    assert "DO NOT LOG" not in json.dumps(trace.data)
    assert "public_items_with_text" not in trace.data["dependency"]
    assert "\x1b" not in trace.data["dependency"]["ocr_backend"]


def test_existing_empty_page_artifacts_model_free_replay(tmp_path):
    """Optional local evidence replay, NOT a new EasyOCR inference result."""
    root = Path(__file__).resolve().parents[1]
    run = root / ".benchmarks/runs/omnidocbench/representative-v2-full-20261002T080500Z/_doc_extraction_runs"
    stored = run / "page-062fc21c-6b9c-40be-8d0e-7a617509a9bc-2b0527c5"
    if not (stored / "rendered/page-001.png").exists():
        pytest.skip("local ignored historical benchmark artifacts unavailable")
    layout = json.loads((stored / "layout/page-001.json").read_text())
    ocr = json.loads((stored / "ocr/page-001.json").read_text())
    assert ocr["tokens"] == []
    components = Components([Region(BBox(**r["bbox"]), r["label"]) for r in layout["regions"]])
    pages = []
    recorder = VisualForensics(tmp_path)
    for enabled in [False, True]:
        page = run_scanned_page_pipeline(
            stored / "rendered/page-001.png", 0, 200, components, components, Components(available=False),
            tmp_path, forensics=recorder if enabled else None,
        )
        page.reading_order = [e.id for e in page.elements]
        pages.append(page)
    assert pages[0].model_dump() == pages[1].model_dump()
    assert page_to_prediction_markdown(pages[1]) == "\n"
    trace = recorder.pages[0].data
    assert trace["input_dimensions"] == [1654, 2339]
    assert trace["layout"]["labels"]["counts"] == {"formula": 5}
    assert trace["ocr"]["projected_tokens"] == 0
    assert trace["ocr"]["raw_tokens"] is None
    assert trace["canonical"]["null_text"] == 5
    assert trace["canonical"]["text_bearing"] == 0
    recorder.persist()
    persisted = json.loads(recorder.path.read_text())
    assert summarize_traces([persisted])["formula_only_zero_projected_ocr"] == 1
