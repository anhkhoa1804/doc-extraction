"""Configuration handling and backend availability contracts."""
from __future__ import annotations

import os

import pytest
import yaml

from doc_extraction.config import PipelineConfig, load_config
from doc_extraction.pipelines.base import BackendUnavailableError

ALL_CONFIGS = ["default.yaml", "cpu.yaml", "gpu.yaml"]


@pytest.mark.parametrize("name", ALL_CONFIGS)
def test_shipped_configs_load_and_validate(repo_root, name):
    config = load_config(repo_root / "configs" / name)
    assert isinstance(config, PipelineConfig)


@pytest.mark.parametrize("name", ["default.yaml", "cpu.yaml"])
def test_default_and_cpu_configs_are_cpu_only(repo_root, name):
    """This phase's explicit goal: the default path must never need a GPU."""
    assert load_config(repo_root / "configs" / name).device == "cpu"


@pytest.mark.parametrize("name", ALL_CONFIGS)
def test_configs_contain_no_absolute_paths(repo_root, name):
    """A committed config must be machine-independent, or a clone on another
    box silently writes to a directory that does not exist there."""
    raw = yaml.safe_load((repo_root / "configs" / name).read_text(encoding="utf-8"))
    for key, value in raw.items():
        if isinstance(value, str):
            assert not value.startswith("/"), f"{name}:{key} is an absolute POSIX path"
            assert ":" not in value[:3], f"{name}:{key} looks like an absolute Windows path"


def test_config_snapshot_is_machine_independent():
    """`config_snapshot` lands in every metadata.json; an absolute cache path
    there would make results non-portable."""
    snapshot = PipelineConfig().to_snapshot()
    assert snapshot["cache_dir"] == ".cache"
    assert snapshot["device"] == "cpu"


def test_overrides_merge_over_file(repo_root):
    config = load_config(repo_root / "configs" / "cpu.yaml", overrides={"render_dpi": 72})
    assert config.render_dpi == 72
    assert config.device == "cpu"


def test_invalid_config_value_is_rejected(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("render_dpi: not-a-number\n", encoding="utf-8")
    with pytest.raises(Exception):
        load_config(bad)


def test_unknown_config_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "missing.yaml")


def test_empty_config_falls_back_to_defaults(tmp_path):
    empty = tmp_path / "empty.yaml"
    empty.write_text("", encoding="utf-8")
    assert load_config(empty).device == "cpu"


# --- Backend availability contracts ---------------------------------------


def test_core_package_imports_without_optional_backends():
    """The core package must never require a heavy optional dependency."""
    import importlib

    for module in [
        "doc_extraction.cli",
        "doc_extraction.pipelines.pdf",
        "doc_extraction.pipelines.office",
        "doc_extraction.backends.mineru_backend",
        "doc_extraction.backends.paddleocr_backend",
        "doc_extraction.backends.vlm_backend",
        "doc_extraction.backends.pymupdf_table_backend",
    ]:
        assert importlib.import_module(module) is not None


@pytest.mark.parametrize(
    "module_path,class_name",
    [
        ("doc_extraction.backends.mineru_backend", "MinerUBackend"),
        ("doc_extraction.backends.paddleocr_backend", "PaddleOCRBackend"),
        ("doc_extraction.backends.vlm_backend", "VLMBackend"),
    ],
)
def test_unavailable_backends_fail_loudly_with_guidance(module_path, class_name, tmp_path):
    import importlib

    backend = getattr(importlib.import_module(module_path), class_name)()
    assert backend.is_available() is False
    with pytest.raises(BackendUnavailableError) as excinfo:
        backend.convert(tmp_path / "x.pdf", config=None)
    # The error must tell an operator what to do, not just that it failed.
    assert "docs/backends.md" in str(excinfo.value)


def test_installed_backends_report_available():
    from doc_extraction.backends.pymupdf_table_backend import PyMuPDFTableBackend
    from doc_extraction.backends.table_backend import TableTransformerBackend

    assert PyMuPDFTableBackend().is_available() is True
    assert PyMuPDFTableBackend().version()
    # transformers/torch are installed in the reference environment.
    assert TableTransformerBackend().is_available() is True


def test_docling_backend_reports_availability_consistently():
    from doc_extraction.backends.docling_backend import DoclingBackend, is_available

    assert DoclingBackend().is_available() == is_available()


def test_model_versions_are_recorded():
    from doc_extraction.cli import collect_model_versions

    versions = collect_model_versions("baseline")
    assert "doc_extraction" in versions
    assert "pymupdf" in versions


def test_unknown_backend_name_is_rejected():
    from doc_extraction.cli import build_whole_document_backend

    with pytest.raises(ValueError):
        build_whole_document_backend("nonexistent", PipelineConfig())


# --- device plumbing ------------------------------------------------------
# Both regressions below were live bugs, and neither surfaced as a failure:
# the pipeline kept producing correct output while quietly ignoring
# `config.device`. Only wall-clock time (and, on CUDA, a crash) revealed
# them, so they need assertions rather than observation.


@pytest.mark.parametrize("device", ["cpu", "cuda"])
def test_docling_pipeline_options_follow_configured_device(device):
    """docling must be told the device explicitly. Left unset it falls back
    to its own `device="auto"`, which resolves to CUDA whenever a GPU is
    visible — silently disagreeing with a config that says "cpu"."""
    from docling.datamodel.base_models import InputFormat

    from doc_extraction.backends.docling_backend import DoclingBackend

    converter = DoclingBackend(device=device, ocr_languages=["en", "vi"])._get_converter()

    for fmt in (InputFormat.PDF, InputFormat.IMAGE):
        options = converter.format_to_options[fmt].pipeline_options
        assert options.accelerator_options.device == device
        # `use_gpu` must stay None: it is deprecated upstream and *overrides*
        # the accelerator device instead of following it, which is exactly
        # what pinned EasyOCR to CPU on a CUDA box.
        assert options.ocr_options.use_gpu is None
        assert options.ocr_options.lang == ["en", "vi"]


def test_table_transformer_moves_inputs_to_its_device():
    """The models are moved to `self.device`; their inputs must be too, or
    torch raises "Expected all tensors to be on the same device" as soon as
    device is not cpu. Asserted on CPU by checking the call actually routes
    every input tensor through `.to(device)`."""
    from doc_extraction.backends.table_backend import TableTransformerBackend

    backend = TableTransformerBackend(device="cpu")
    moved: list[str] = []

    class _FakeProcessor:
        def __call__(self, images, return_tensors):
            return {"pixel_values": _TrackedTensor(moved, "pixel_values")}

        def post_process_object_detection(self, outputs, threshold, target_sizes):
            return [{"boxes": [], "labels": [], "scores": []}]

    class _TrackedTensor:
        def __init__(self, log, name):
            self._log = log
            self._name = name

        def to(self, device):
            self._log.append(f"{self._name}->{device}")
            return self

    class _FakeModel:
        def __call__(self, **inputs):
            return object()

    backend._detection_processor = _FakeProcessor()
    backend._detection_model = _FakeModel()
    backend._structure_model = _FakeModel()
    backend._lazy_load = lambda: None

    class _FakeImage:
        size = (100, 200)

    backend._detect_tables(_FakeImage())
    assert moved == ["pixel_values->cpu"], f"inputs were not moved to the device: {moved}"


def test_component_backends_are_cached_per_device_and_languages():
    """Backends are constructed per processed file, but each instance loads
    its own models on first use. Rebuilding them per file made every page pay
    the full model-load cost again — on a benchmark whose pages all take the
    visual route, that dominated the run (visible as a fresh "Loading
    weights"/"LOAD REPORT" per page in the logs). They must be reused."""
    from doc_extraction.cli import _get_component_backends, clear_component_backend_cache

    clear_component_backend_cache()
    try:
        cfg = PipelineConfig(device="cpu", ocr_languages=["en", "vi"])
        layout_a, ocr_a, table_a = _get_component_backends(cfg)

        # A separate but equivalent config must hit the same cached instances.
        layout_b, _, table_b = _get_component_backends(
            PipelineConfig(device="cpu", ocr_languages=["en", "vi"])
        )
        assert layout_a is layout_b
        assert table_a is table_b

        # One Docling instance serves layout+OCR so a page converts once.
        assert layout_a is ocr_a

        # Device and language changes must not silently reuse a wrong backend.
        layout_cuda, _, _ = _get_component_backends(
            PipelineConfig(device="cuda", ocr_languages=["en", "vi"])
        )
        assert layout_cuda is not layout_a
        assert layout_cuda.device == "cuda"

        layout_en, _, _ = _get_component_backends(
            PipelineConfig(device="cpu", ocr_languages=["en"])
        )
        assert layout_en is not layout_a

        clear_component_backend_cache()
        layout_fresh, _, _ = _get_component_backends(cfg)
        assert layout_fresh is not layout_a
    finally:
        clear_component_backend_cache()


def test_configure_caches_does_not_create_dirs_for_preset_variables(tmp_path, monkeypatch):
    """An operator who has already pointed the cache variables somewhere (a
    container with a mounted volume, say) must not have directories created
    under the repo root as a side effect.

    This is not cosmetic: if the repo root is not writable by the running
    user — the normal case for a non-root container user — the unconditional
    mkdir raised PermissionError and the run failed before it started, for
    directories nothing would ever have used.
    """
    from doc_extraction.config import configure_caches

    preset = tmp_path / "mounted-cache"
    preset.mkdir()
    for variable in ("HF_HOME", "HUGGINGFACE_HUB_CACHE", "DOCLING_ARTIFACTS_PATH", "PIP_CACHE_DIR"):
        monkeypatch.setenv(variable, str(preset))

    unwritable_base = tmp_path / "should-not-be-created"
    configure_caches(unwritable_base)

    assert not unwritable_base.exists(), "created cache dirs for variables that were already set"
    # ...and the operator's values are untouched.
    assert os.environ["HF_HOME"] == str(preset)
    assert os.environ["DOCLING_ARTIFACTS_PATH"] == str(preset)


def test_configure_caches_still_creates_and_sets_unset_variables(tmp_path, monkeypatch):
    """The default path must keep working: nothing preset -> dirs created and
    variables pointed at them."""
    from doc_extraction.config import configure_caches

    for variable in ("HF_HOME", "HUGGINGFACE_HUB_CACHE", "DOCLING_ARTIFACTS_PATH", "PIP_CACHE_DIR"):
        monkeypatch.delenv(variable, raising=False)

    base = tmp_path / "cache"
    configure_caches(base)

    assert (base / "huggingface").is_dir()
    assert (base / "docling").is_dir()
    assert (base / "pip").is_dir()
    assert os.environ["HF_HOME"] == str(base / "huggingface")
    assert os.environ["DOCLING_ARTIFACTS_PATH"] == str(base / "docling")


def test_stage_log_records_the_runs_actual_device(tmp_path):
    """The per-stage log is the pipeline's primary observability artifact, so
    its `device` field must reflect the run.

    It previously defaulted to "cpu" on every call with no call site ever
    passing it, so a full CUDA run produced logs claiming it ran on CPU —
    silently wrong provenance that any log-based profiler would repeat.
    """
    import json

    from doc_extraction.utils.logging import StageLogger

    logger = StageLogger("doc-1", tmp_path / "logs", device="cuda")
    with logger.stage("layout", "docling", page=0):
        pass
    logger.log_event(stage="table", backend="table_transformer", status="success")

    records = [json.loads(line) for line in (tmp_path / "logs" / "pipeline.jsonl").read_text().splitlines()]
    assert [r["device"] for r in records] == ["cuda", "cuda"]


def test_stage_log_device_can_still_be_overridden_per_call(tmp_path):
    """A stage that genuinely runs elsewhere than the rest of the run keeps
    the ability to say so."""
    import json

    from doc_extraction.utils.logging import StageLogger

    logger = StageLogger("doc-1", tmp_path / "logs", device="cuda")
    logger.log_event(stage="render", backend="pymupdf", status="success", device="cpu")
    record = json.loads((tmp_path / "logs" / "pipeline.jsonl").read_text().splitlines()[0])
    assert record["device"] == "cpu"


def test_stage_logger_defaults_to_cpu_when_unspecified(tmp_path):
    import json

    from doc_extraction.utils.logging import StageLogger

    logger = StageLogger("doc-1", tmp_path / "logs")
    logger.log_event(stage="parse", backend="pymupdf-native", status="success")
    record = json.loads((tmp_path / "logs" / "pipeline.jsonl").read_text().splitlines()[0])
    assert record["device"] == "cpu"


def test_docling_recognize_emits_table_cell_text(tmp_path):
    """Table cells recognized by docling must reach the OCR token stream.

    `recognize()` previously skipped table items entirely, on the reasoning
    that the table stage would handle them. It does not: the baseline
    pipeline's table stage is Table Transformer, which contributes grid
    geometry and fills cell text from OCR tokens that fall inside each cell.
    With no tokens emitted for tables, every table cell on the visual route
    stayed empty while docling had already recognized all of them.

    This is a pure unit test over a stubbed docling document, so it locks the
    adapter contract without needing a model or a rendered page.
    """
    from doc_extraction.backends.docling_backend import DoclingBackend

    class _BBox:
        def __init__(self, l, t, r, b):
            self.l, self.t, self.r, self.b = l, t, r, b
            self.coord_origin = "TOPLEFT"

    class _Cell:
        def __init__(self, text, bbox):
            self.text, self.bbox = text, bbox

    class _Data:
        table_cells = [
            _Cell("SKU-1001", _BBox(10, 20, 60, 32)),
            _Cell("Sản phẩm 1", _BBox(70, 20, 140, 32)),
            _Cell("   ", _BBox(150, 20, 200, 32)),   # blank cell: skipped
            _Cell("no-geometry", None),              # no bbox: skipped, not faked
        ]

    class _TableItem:
        label = "table"
        data = _Data()

    tokens = DoclingBackend()._table_cell_tokens(_TableItem(), page_height=800)
    texts = [t.text for t in tokens]

    assert "SKU-1001" in texts
    assert "Sản phẩm 1" in texts, "Vietnamese cell text must survive unchanged"
    assert "   " not in texts and "" not in texts, "blank cells must not become tokens"
    assert "no-geometry" not in texts, (
        "a cell without geometry must be skipped, not given a fabricated box — "
        "a token in the wrong place is worse than a missing one"
    )
    assert all(t.bbox is not None for t in tokens)


class _DoclingBBox:
    """Minimal stand-in for docling's BoundingBox."""

    def __init__(self, l, t, r, b, origin="TOPLEFT"):
        self.l, self.t, self.r, self.b = l, t, r, b
        self.coord_origin = origin


def test_docling_bbox_is_rescaled_into_the_callers_pixel_space():
    """Docling rasterizes internally at its own resolution (measured: 150 DPI
    for an image input) regardless of the image it is handed. Its coordinates
    must be rescaled before they can be compared with anything else.

    Skipping this was invisible for a long time because region-vs-token
    containment compared docling geometry against docling geometry — both
    wrong identically. It surfaced only when docling tokens met Table
    Transformer cells, filling 0 of 50 cells on a table docling had read
    perfectly.
    """
    from doc_extraction.backends.docling_backend import _bbox_from_docling

    docling_page = (1239.6, 1754.0)   # docling's A4 at 150 DPI
    caller_height = 2339.0            # our render of the same page at 200 DPI
    scale = caller_height / docling_page[1]   # 1.3333...

    box = _bbox_from_docling(_DoclingBBox(117, 207, 148, 219), caller_height, docling_page)
    assert box.x0 == pytest.approx(117 * scale, rel=1e-6)
    assert box.y0 == pytest.approx(207 * scale, rel=1e-6)
    assert box.x1 == pytest.approx(148 * scale, rel=1e-6)


def test_docling_bottomleft_flip_uses_doclings_page_height_not_the_callers():
    """Mixing the two page heights in one subtraction silently offsets every
    box. Docling reports item `prov` boxes BOTTOMLEFT and table cells
    TOPLEFT, so both conventions occur in one document."""
    from doc_extraction.backends.docling_backend import _bbox_from_docling

    docling_page = (1239.6, 1754.0)
    caller_height = 2339.0
    # A box near the TOP of the page in bottom-left coords has a LARGE t.
    box = _bbox_from_docling(
        _DoclingBBox(125, 1631, 393, 1605, origin="BOTTOMLEFT"), caller_height, docling_page)
    expected_y0 = (1754.0 - 1631) * (caller_height / 1754.0)
    assert box.y0 == pytest.approx(expected_y0, rel=1e-6)
    assert box.y0 < caller_height * 0.25, "a box near the page top must stay near the top"


def test_docling_bbox_without_source_size_keeps_previous_behaviour():
    """When the caller's space already matches docling's — the whole-document
    `convert()` path on a PDF, where Page dimensions come from docling itself —
    no rescale must be applied."""
    from doc_extraction.backends.docling_backend import _bbox_from_docling

    box = _bbox_from_docling(_DoclingBBox(60, 79, 314, 93), 842.0, None)
    assert (box.x0, box.y0, box.x1, box.y1) == (60, 79, 314, 93)


def test_docling_bbox_normalizes_inverted_corners():
    from doc_extraction.backends.docling_backend import _bbox_from_docling

    box = _bbox_from_docling(_DoclingBBox(300, 400, 100, 200), 842.0, None)
    assert box.x0 <= box.x1 and box.y0 <= box.y1
