"""OmniDocBench adapter: coordinate conversion, dataset validation, Markdown
rendering, and evaluator-invocation plumbing.

Deliberately does not run a full benchmark or require the actual evaluator
/ dataset to be present — those are external, multi-GB/Linux-toolchain
dependencies (see experiments/005_omnidocbench/README.md). Evaluator
subprocess invocation is tested via `check_evaluator_available`'s failure
path (no real interpreter needed) and via a fake interpreter script for the
success path.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from doc_extraction.evaluation import omnidocbench as odb
from doc_extraction.schemas.element import BBox, Element, ElementType
from doc_extraction.schemas.page import Page
from doc_extraction.schemas.table import Cell, Table

# ---------------------------------------------------------------------------
# Coordinate conversion (spec §10: top-left, bottom-right, full-page,
# non-square page dimensions)
# ---------------------------------------------------------------------------


def test_bbox_to_poly_top_left_region():
    poly = odb.bbox_to_omnidocbench_poly(BBox(x0=0, y0=0, x1=50, y1=30))
    assert poly == [0, 0, 50, 0, 50, 30, 0, 30]


def test_bbox_to_poly_bottom_right_region():
    # A region anchored at the bottom-right corner of a 1200x1684 page.
    poly = odb.bbox_to_omnidocbench_poly(BBox(x0=1100, y0=1600, x1=1200, y1=1684))
    assert poly == [1100, 1600, 1200, 1600, 1200, 1684, 1100, 1684]
    back = odb.omnidocbench_poly_to_bbox(poly)
    assert back == BBox(x0=1100, y0=1600, x1=1200, y1=1684)


def test_bbox_to_poly_full_page_region():
    page_bbox = BBox(x0=0, y0=0, x1=1200, y1=1684)
    poly = odb.bbox_to_omnidocbench_poly(page_bbox)
    assert odb.omnidocbench_poly_to_bbox(poly) == page_bbox


@pytest.mark.parametrize(
    "bbox",
    [
        BBox(x0=10, y0=20, x1=110, y1=70),  # wide
        BBox(x0=10, y0=20, x1=40, y1=520),  # tall (non-square page shape)
        BBox(x0=0, y0=0, x1=1, y1=1),  # tiny
    ],
)
def test_bbox_poly_round_trip(bbox):
    assert odb.omnidocbench_poly_to_bbox(odb.bbox_to_omnidocbench_poly(bbox)) == bbox


def test_poly_to_bbox_takes_bounding_box_of_rotated_poly():
    """A non-axis-aligned poly has no exact BBox equivalent — this must
    degrade to *a* usable bbox (the axis-aligned bounding box), not raise
    and not silently return nonsense."""
    # A poly rotated 45 degrees around (50, 50), roughly.
    poly = [50, 0, 100, 50, 50, 100, 0, 50]
    result = odb.omnidocbench_poly_to_bbox(poly)
    assert result.x0 == 0 and result.x1 == 100
    assert result.y0 == 0 and result.y1 == 100


def test_poly_to_bbox_rejects_wrong_length():
    with pytest.raises(ValueError):
        odb.omnidocbench_poly_to_bbox([1, 2, 3])


# ---------------------------------------------------------------------------
# Dataset discovery & validation
# ---------------------------------------------------------------------------


def _write_dataset(tmp_path: Path, records: list[dict], image_names: list[str]) -> Path:
    dataset_root = tmp_path / "dataset"
    images_dir = dataset_root / "images"
    images_dir.mkdir(parents=True)
    for name in image_names:
        (images_dir / name).write_bytes(b"\x89PNG\r\n\x1a\n")  # minimal PNG magic, content unused
    (dataset_root / "OmniDocBench.json").write_text(json.dumps(records), encoding="utf-8")
    return dataset_root


def _sample_record(image_name: str, page_no: int = 0) -> dict:
    return {
        "layout_dets": [],
        "page_info": {
            "page_no": page_no,
            "height": 1684,
            "width": 1200,
            "image_path": f"images/{image_name}",
            "page_attribute": {"language": "en"},
        },
    }


def test_load_dataset_happy_path(tmp_path):
    records = [_sample_record("a.jpg"), _sample_record("b.jpg", page_no=1)]
    dataset_root = _write_dataset(tmp_path, records, ["a.jpg", "b.jpg"])

    gt_path, samples = odb.load_dataset(dataset_root)
    assert gt_path == dataset_root / "OmniDocBench.json"
    assert [s.image_name for s in samples] == ["a.jpg", "b.jpg"]
    assert samples[0].prediction_filename == "a.md"
    assert samples[0].width == 1200 and samples[0].height == 1684


def test_load_dataset_swaps_arbitrary_extension_not_just_jpg(tmp_path):
    """The real HuggingFace copy of OmniDocBench ships .png, not the .jpg
    shown in the upstream README's prose example — the filename convention
    must generalize."""
    dataset_root = _write_dataset(tmp_path, [_sample_record("page.png")], ["page.png"])
    _, samples = odb.load_dataset(dataset_root)
    assert samples[0].prediction_filename == "page.md"


def test_load_dataset_missing_path():
    with pytest.raises(odb.DatasetError, match="does not exist"):
        odb.load_dataset(Path("Z:/definitely/not/here"))


def test_load_dataset_missing_ground_truth_json(tmp_path):
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    with pytest.raises(odb.DatasetError, match="no OmniDocBench ground-truth JSON"):
        odb.load_dataset(empty_dir)


def test_load_dataset_malformed_json(tmp_path):
    dataset_root = tmp_path / "dataset"
    dataset_root.mkdir()
    (dataset_root / "OmniDocBench.json").write_text("{not valid json", encoding="utf-8")
    with pytest.raises(odb.DatasetError, match="not valid JSON"):
        odb.load_dataset(dataset_root)


def test_load_dataset_wrong_top_level_shape(tmp_path):
    """The documented schema is a top-level array of page records — a
    single object (an easy mistake, e.g. pasting one record) must be
    rejected with a specific reason, not silently misread."""
    dataset_root = tmp_path / "dataset"
    dataset_root.mkdir()
    (dataset_root / "OmniDocBench.json").write_text(json.dumps({"not": "a list"}), encoding="utf-8")
    with pytest.raises(odb.DatasetError, match="expected a top-level JSON array"):
        odb.load_dataset(dataset_root)


def test_load_dataset_record_missing_page_info(tmp_path):
    dataset_root = tmp_path / "dataset"
    dataset_root.mkdir()
    (dataset_root / "OmniDocBench.json").write_text(json.dumps([{"layout_dets": []}]), encoding="utf-8")
    with pytest.raises(odb.DatasetError, match="page_info"):
        odb.load_dataset(dataset_root)


def test_load_dataset_missing_images_directory_raises(tmp_path):
    """This is the 'incompatible/incomplete dataset' case: the ground-truth
    JSON is well-formed but references images that were never downloaded
    (e.g. an interrupted transfer) — this must fail loudly, not silently
    evaluate on whatever partial set happens to exist."""
    dataset_root = tmp_path / "dataset"
    dataset_root.mkdir()
    (dataset_root / "OmniDocBench.json").write_text(
        json.dumps([_sample_record("missing.jpg")]), encoding="utf-8"
    )
    with pytest.raises(odb.DatasetError, match="reference an image file not present"):
        odb.load_dataset(dataset_root)


def test_load_dataset_is_deterministically_ordered(tmp_path):
    records = [_sample_record(f"{i}.jpg", page_no=i) for i in reversed(range(5))]
    names = [f"{i}.jpg" for i in range(5)]
    dataset_root = _write_dataset(tmp_path, records, names)
    _, samples_a = odb.load_dataset(dataset_root)
    _, samples_b = odb.load_dataset(dataset_root)
    assert [s.index for s in samples_a] == [s.index for s in samples_b] == list(range(5))


# ---------------------------------------------------------------------------
# Subset selection (deterministic naming / reproducibility)
# ---------------------------------------------------------------------------


def _make_samples(n: int) -> list[odb.OmniDocSample]:
    return [
        odb.OmniDocSample(index=i, image_path=Path(f"{i}.jpg"), image_name=f"{i}.jpg", page_no=i, width=100, height=100)
        for i in range(n)
    ]


def test_select_subset_is_deterministic():
    samples = _make_samples(20)
    first = odb.select_subset(samples, limit=5)
    second = odb.select_subset(samples, limit=5)
    assert [s.index for s in first] == [s.index for s in second]


def test_select_subset_spreads_across_dataset_not_just_the_prefix():
    samples = _make_samples(100)
    subset = odb.select_subset(samples, limit=10)
    indices = [s.index for s in subset]
    assert indices != list(range(10)), "subset must not just be the first N samples"
    assert max(indices) - min(indices) > 50


def test_select_subset_returns_everything_when_limit_exceeds_size():
    samples = _make_samples(5)
    assert odb.select_subset(samples, limit=100) == samples
    assert odb.select_subset(samples, limit=None) == samples


def test_select_subset_rejects_non_positive_limit():
    with pytest.raises(ValueError):
        odb.select_subset(_make_samples(5), limit=0)


# ---------------------------------------------------------------------------
# IR -> Markdown prediction rendering
# ---------------------------------------------------------------------------


def _text_el(eid: str, x0, y0, x1, y1, etype=ElementType.PARAGRAPH, **kwargs) -> Element:
    return Element(id=eid, type=etype, bbox=BBox(x0=x0, y0=y0, x1=x1, y1=y1), page_number=1, source_backend="test", **kwargs)


def test_page_to_markdown_orders_by_reading_order():
    page = Page(
        index=0, width=100, height=100,
        elements=[_text_el("b", 0, 20, 50, 30, text="second"), _text_el("a", 0, 0, 50, 10, text="first")],
        reading_order=["a", "b"],
    )
    markdown = odb.page_to_prediction_markdown(page)
    assert markdown.index("first") < markdown.index("second")


def test_page_to_markdown_heading_levels():
    page = Page(
        index=0, width=100, height=100,
        elements=[_text_el("h1", 0, 0, 50, 10, etype=ElementType.HEADING, text="Title", level=1),
                  _text_el("h3", 0, 20, 50, 30, etype=ElementType.HEADING, text="Sub", level=3)],
        reading_order=["h1", "h3"],
    )
    markdown = odb.page_to_prediction_markdown(page)
    assert "# Title" in markdown
    assert "### Sub" in markdown


def test_page_to_markdown_list_item():
    page = Page(index=0, width=10, height=10,
                elements=[_text_el("l1", 0, 0, 5, 5, etype=ElementType.LIST_ITEM, text="item one")],
                reading_order=["l1"])
    assert "- item one" in odb.page_to_prediction_markdown(page)


def test_page_to_markdown_table_uses_table_to_markdown():
    table = Table(id="t0", page_number=1, n_rows=1, n_cols=2, source_backend="test",
                  cells=[Cell(row=0, col=0, text="k"), Cell(row=0, col=1, text="v")])
    element = Element(id="e0", type=ElementType.TABLE, page_number=1, source_backend="test", table_id="t0")
    page = Page(index=0, width=10, height=10, elements=[element], tables=[table], reading_order=["e0"])
    markdown = odb.page_to_prediction_markdown(page)
    assert "| k | v |" in markdown


def test_page_to_markdown_formula_gets_latex_wrapped():
    page = Page(index=0, width=10, height=10,
                elements=[_text_el("f1", 0, 0, 5, 5, etype=ElementType.FORMULA, text="E=mc^2")],
                reading_order=["f1"])
    markdown = odb.page_to_prediction_markdown(page)
    assert "$$E=mc^2$$" in markdown


def test_page_to_markdown_formula_not_double_wrapped():
    page = Page(index=0, width=10, height=10,
                elements=[_text_el("f1", 0, 0, 5, 5, etype=ElementType.FORMULA, text="$$E=mc^2$$")],
                reading_order=["f1"])
    markdown = odb.page_to_prediction_markdown(page)
    assert markdown.count("$$") == 2  # not $$$$E=mc^2$$$$


def test_page_to_markdown_empty_page_does_not_crash():
    page = Page(index=0, width=10, height=10, elements=[], reading_order=[])
    assert odb.page_to_prediction_markdown(page) == "\n"


def test_page_to_markdown_blocks_separated_by_blank_line():
    page = Page(
        index=0, width=100, height=100,
        elements=[_text_el("a", 0, 0, 50, 10, text="para one"), _text_el("b", 0, 20, 50, 30, text="para two")],
        reading_order=["a", "b"],
    )
    markdown = odb.page_to_prediction_markdown(page)
    assert "para one\n\npara two" in markdown


# ---------------------------------------------------------------------------
# Prediction generation orchestration
# ---------------------------------------------------------------------------


def test_write_predictions_deterministic_output_naming(tmp_path):
    samples = [odb.OmniDocSample(index=0, image_path=Path("x.jpg"), image_name="x.jpg", page_no=0, width=10, height=10)]
    page = Page(index=0, width=10, height=10, elements=[_text_el("a", 0, 0, 5, 5, text="hi")], reading_order=["a"])

    def process(image_path: Path):
        return page, "image", 1.23

    results = odb.write_predictions(samples, tmp_path / "preds", process)
    assert results[0].output_path == tmp_path / "preds" / "x.md"
    assert results[0].output_path.exists()
    assert results[0].error is None


def test_write_predictions_continues_after_a_failure(tmp_path):
    samples = [
        odb.OmniDocSample(index=0, image_path=Path("bad.jpg"), image_name="bad.jpg", page_no=0, width=10, height=10),
        odb.OmniDocSample(index=1, image_path=Path("ok.jpg"), image_name="ok.jpg", page_no=1, width=10, height=10),
    ]
    page = Page(index=0, width=10, height=10, elements=[], reading_order=[])

    def process(image_path: Path):
        if image_path.name == "bad.jpg":
            raise RuntimeError("simulated backend failure")
        return page, "image", 0.5

    results = odb.write_predictions(samples, tmp_path / "preds", process)
    assert results[0].error is not None and "simulated backend failure" in results[0].error
    assert results[1].error is None
    assert (tmp_path / "preds" / "ok.md").exists()
    assert not (tmp_path / "preds" / "bad.md").exists()


def test_write_runtime_report(tmp_path):
    samples = [odb.OmniDocSample(index=i, image_path=Path(f"{i}.jpg"), image_name=f"{i}.jpg", page_no=i, width=1, height=1) for i in range(2)]
    results = [
        odb.PredictionRunResult(samples[0], tmp_path / "0.md", 2.0, "image"),
        odb.PredictionRunResult(samples[1], tmp_path / "1.md", 0.0, "error", error="boom"),
    ]
    report = odb.write_runtime_report(results, tmp_path / "runtime.json")
    assert report["succeeded"] == 1
    assert report["failed"] == 1
    assert report["total_runtime_seconds"] == 2.0
    assert report["pages_per_second"] == 0.5
    assert (tmp_path / "runtime.json").exists()
    assert json.loads((tmp_path / "runtime.json").read_text(encoding="utf-8"))["failed"] == 1


# ---------------------------------------------------------------------------
# Benchmark metadata
# ---------------------------------------------------------------------------


def test_build_benchmark_metadata(tmp_path):
    gt = tmp_path / "gt.json"
    gt.write_text("[]", encoding="utf-8")
    metadata = odb.build_benchmark_metadata(
        backend="baseline", device="cpu", ground_truth_path=gt, num_samples=3,
        config_snapshot={"device": "cpu"}, model_versions={"doc_extraction": "0.1.0"},
    )
    assert metadata["benchmark"] == "OmniDocBench"
    assert metadata["upstream_commit"] == odb.PINNED_UPSTREAM_COMMIT
    assert metadata["num_samples"] == 3
    assert metadata["ground_truth_sha256"] == odb.dataset_content_hash(gt)
    assert json.dumps(metadata)  # must be JSON-serializable as-is


def test_dataset_content_hash_is_stable(tmp_path):
    gt = tmp_path / "gt.json"
    gt.write_text('[{"a": 1}]', encoding="utf-8")
    assert odb.dataset_content_hash(gt) == odb.dataset_content_hash(gt)


# ---------------------------------------------------------------------------
# Evaluator config generation
# ---------------------------------------------------------------------------


def test_write_evaluator_config_shape(tmp_path):
    import yaml

    config_path = odb.write_evaluator_config(
        ground_truth_path=tmp_path / "gt.json",
        predictions_dir=tmp_path / "preds",
        output_path=tmp_path / "config.yaml",
    )
    loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert loaded["end2end_eval"]["dataset"]["match_method"] == "quick_match"
    assert loaded["end2end_eval"]["metrics"]["display_formula"]["metric"] == ["Edit_dist"]  # no CDM by default


def test_write_evaluator_config_can_include_cdm_and_bleu(tmp_path):
    import yaml

    config_path = odb.write_evaluator_config(
        ground_truth_path=tmp_path / "gt.json", predictions_dir=tmp_path / "preds",
        output_path=tmp_path / "config.yaml", include_cdm=True, include_bleu_meteor=True,
    )
    loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert "CDM" in loaded["end2end_eval"]["metrics"]["display_formula"]["metric"]
    assert "BLEU" in loaded["end2end_eval"]["metrics"]["text_block"]["metric"]


def test_write_evaluator_config_handles_windows_paths(tmp_path):
    """Backslashes and drive-letter colons must round-trip through the
    generated YAML without corrupting the path."""
    import yaml

    windows_path = Path("D:\\doc-extraction\\dataset\\OmniDocBench.json")
    config_path = odb.write_evaluator_config(
        ground_truth_path=windows_path, predictions_dir=tmp_path / "preds",
        output_path=tmp_path / "config.yaml",
    )
    loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert loaded["end2end_eval"]["dataset"]["ground_truth"]["data_path"] == str(windows_path)


# ---------------------------------------------------------------------------
# Evaluator availability / invocation
# ---------------------------------------------------------------------------


def test_check_evaluator_available_missing_python(tmp_path):
    with pytest.raises(odb.EvaluatorNotAvailableError, match="no Python interpreter"):
        odb.check_evaluator_available(tmp_path / "nope" / "python.exe", tmp_path / "repo")


def test_check_evaluator_available_missing_repo(tmp_path):
    fake_python = tmp_path / "python.exe"
    fake_python.write_bytes(b"")
    with pytest.raises(odb.EvaluatorNotAvailableError, match="does not look like an OmniDocBench checkout"):
        odb.check_evaluator_available(fake_python, tmp_path / "not_a_repo")


def test_check_evaluator_available_happy_path(tmp_path):
    fake_python = tmp_path / "python.exe"
    fake_python.write_bytes(b"")
    (tmp_path / "pdf_validation.py").write_text("", encoding="utf-8")
    odb.check_evaluator_available(fake_python, tmp_path)  # must not raise


def test_run_official_evaluator_raises_before_spawning_when_unavailable(tmp_path):
    with pytest.raises(odb.EvaluatorNotAvailableError):
        odb.run_official_evaluator(
            omnidoc_python=tmp_path / "missing.exe", omnidoc_repo=tmp_path, config_path=tmp_path / "c.yaml",
        )


def test_run_official_evaluator_invokes_subprocess_with_utf8_env(tmp_path, monkeypatch):
    """Uses a fake 'interpreter' (this test's own Python) running a tiny
    script instead of the real evaluator, so this stays fast and needs no
    external dependency — it only tests our own subprocess plumbing: the
    right command, the right cwd, PYTHONUTF8 set for the child."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pdf_validation.py").write_text(
        "import os, sys\n"
        "assert os.environ.get('PYTHONUTF8') == '1'\n"
        "assert '--config' in sys.argv\n"
        "print('ran ok')\n",
        encoding="utf-8",
    )
    config_path = tmp_path / "config.yaml"
    config_path.write_text("end2end_eval: {}\n", encoding="utf-8")

    process = odb.run_official_evaluator(
        omnidoc_python=Path(sys.executable), omnidoc_repo=repo, config_path=config_path,
        log_path=tmp_path / "log.txt",
    )
    assert process.returncode == 0
    assert "ran ok" in process.stdout
    assert (tmp_path / "log.txt").exists()


def test_collect_evaluator_results_only_returns_existing_files(tmp_path):
    result_dir = tmp_path / "result"
    result_dir.mkdir()
    (result_dir / "predictions_quick_match_metric_result.json").write_text("{}", encoding="utf-8")
    found = odb.collect_evaluator_results(tmp_path, "predictions_quick_match")
    assert set(found.keys()) == {"metric_result"}


def test_collect_evaluator_results_empty_when_nothing_written(tmp_path):
    (tmp_path / "result").mkdir()
    assert odb.collect_evaluator_results(tmp_path, "nope") == {}


# ---------------------------------------------------------------------------
# run.py's config.yaml-seeded defaults (loaded as a module, since it lives
# in experiments/ rather than the installed package)
# ---------------------------------------------------------------------------


def _load_run_module():
    import importlib.util

    run_path = Path(__file__).resolve().parents[1] / "experiments" / "005_omnidocbench" / "run.py"
    spec = importlib.util.spec_from_file_location("_omnidocbench_run_under_test", run_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_run_defaults_config_missing_file_yields_hardcoded_fallbacks(tmp_path):
    run = _load_run_module()
    defaults = run._load_defaults(tmp_path / "does_not_exist.yaml")
    assert defaults == {}
    parser = run.build_parser(defaults)
    args = parser.parse_args(["--dataset", "d", "--backend", "baseline", "--output", "o"])
    assert args.match_workers == 4
    assert args.match_method == "quick_match"


def test_run_defaults_config_overrides_hardcoded_fallbacks(tmp_path):
    run = _load_run_module()
    config_path = tmp_path / "config.yaml"
    config_path.write_text("match_workers: 9\nmatch_method: simple_match\n", encoding="utf-8")
    defaults = run._load_defaults(config_path)
    parser = run.build_parser(defaults)
    args = parser.parse_args(["--dataset", "d", "--backend", "baseline", "--output", "o"])
    assert args.match_workers == 9
    assert args.match_method == "simple_match"


def test_run_cli_flag_wins_over_defaults_config(tmp_path):
    """A flag passed on the command line must always win — this is what
    makes the same script Kaggle-usable without editing the checked-in
    config.yaml."""
    run = _load_run_module()
    config_path = tmp_path / "config.yaml"
    config_path.write_text("match_workers: 9\n", encoding="utf-8")
    defaults = run._load_defaults(config_path)
    parser = run.build_parser(defaults)
    args = parser.parse_args(["--dataset", "d", "--backend", "baseline", "--output", "o", "--match-workers", "1"])
    assert args.match_workers == 1
