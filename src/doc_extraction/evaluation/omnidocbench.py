"""Adapter between doc_extraction's canonical IR and the official
OmniDocBench benchmark (`opendatalab/OmniDocBench`, Apache-2.0).

Scope and boundaries
---------------------
This module does the translation work only. It does **not** reimplement any
benchmark metric (Edit Distance, BLEU, METEOR, TEDS, CDM, COCODet) and does
**not** modify the official evaluator. The evaluator is an external
dependency: cloned upstream into `.external/OmniDocBench/` (gitignored, not
vendored into this repository) and run in its own Python 3.10/3.11
virtualenv (`.venv-omnidoc/`, also gitignored — the evaluator requires
`>=3.10,<3.12`, incompatible with this project's main 3.12 environment). See
`experiments/005_omnidocbench/README.md` for exact setup, the pinned
upstream commit, and the full IR<->OmniDocBench field mapping table.

What this module provides:
  - `bbox_to_omnidocbench_poly` / `omnidocbench_poly_to_bbox` — coordinate
    conversion between our axis-aligned `BBox` and OmniDocBench's 8-number
    `poly` (four corner points).
  - `load_dataset` — validate and enumerate an OmniDocBench dataset
    directory (the ground-truth JSON + `images/`), raising `DatasetError`
    with a specific reason rather than guessing or partially succeeding.
  - `page_to_prediction_markdown` — render one canonical `Page` (always
    single-page here: one OmniDocBench sample is one page image) into the
    Markdown format the official `end2end` evaluation method expects.
  - `write_predictions` — orchestrate running a doc_extraction backend over
    every sample and writing one `.md` file per page, matching the
    evaluator's required `<image_stem>.md` naming exactly.
  - `build_benchmark_metadata` — the provenance record every benchmark run
    writes (backend, versions, device, config, dataset hash, timestamp).
  - `write_evaluator_config` — render the evaluator's own YAML config from a
    template, pointed at our generated predictions.
  - `run_official_evaluator` — invoke `pdf_validation.py` in the isolated
    venv and collect its output; a thin subprocess wrapper, not a
    reimplementation of anything it does.
"""
from __future__ import annotations

from doc_extraction import config as _config

import json
import os
import platform
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from doc_extraction.schemas.element import BBox, Element, ElementType
from doc_extraction.schemas.page import Page

# The upstream commit this adapter was written and verified against. See
# experiments/005_omnidocbench/README.md for how this was determined and
# what changes if it drifts. Recorded here (not just in the README) so
# `build_benchmark_metadata` can stamp every run with it automatically.
PINNED_UPSTREAM_COMMIT = "193627ae9e97d89188468ed1ee3b7a856ff76044"
PINNED_UPSTREAM_REPO = "https://github.com/opendatalab/OmniDocBench"

# ---------------------------------------------------------------------------
# Coordinate conversion (spec §10)
# ---------------------------------------------------------------------------
#
# Both systems use a top-left origin with +y downward. Verified directly
# against the OmniDocBench README's own worked example at the pinned commit
# (a poly with top corners at y=781 and bottom corners at y=806 — y grows
# downward, matching doc_extraction's BBox convention exactly; see
# schemas/element.py BBox docstring). The only real difference is shape:
# OmniDocBench stores four corner points (8 numbers) to allow rotated/skewed
# regions; our BBox is always axis-aligned. Conversion between the two is
# therefore exact in the direction we actually need (BBox -> poly, for
# writing predictions) and necessarily lossy in the other direction for a
# genuinely rotated poly (poly -> BBox degrades to that poly's axis-aligned
# bounding box, since BBox has no rotation field to preserve the skew).


def bbox_to_omnidocbench_poly(bbox: BBox) -> list[float]:
    """Axis-aligned BBox -> OmniDocBench's 8-number poly: top-left,
    top-right, bottom-right, bottom-left, in that order (matches the
    ordering documented in the OmniDocBench README's dataset format)."""
    return [
        bbox.x0, bbox.y0,  # top-left
        bbox.x1, bbox.y0,  # top-right
        bbox.x1, bbox.y1,  # bottom-right
        bbox.x0, bbox.y1,  # bottom-left
    ]


def omnidocbench_poly_to_bbox(poly: list[float]) -> BBox:
    """OmniDocBench poly (8 numbers, 4 corner points) -> axis-aligned BBox.

    Takes the min/max across all four points rather than assuming the first
    pair is top-left — a genuinely axis-aligned poly round-trips exactly;
    a rotated one yields its bounding box, not a wrong answer dressed up as
    a right one.
    """
    if len(poly) != 8:
        raise ValueError(f"expected an 8-number OmniDocBench poly, got {len(poly)} value(s): {poly!r}")
    xs = poly[0::2]
    ys = poly[1::2]
    return BBox(x0=min(xs), y0=min(ys), x1=max(xs), y1=max(ys))


# ---------------------------------------------------------------------------
# Dataset discovery & validation (spec §6, §23)
# ---------------------------------------------------------------------------


class DatasetError(RuntimeError):
    """The dataset directory doesn't match the documented OmniDocBench
    schema. Always raised with the specific reason — never a silent partial
    read, per the spec's "never silently assume" principle."""


@dataclass
class OmniDocSample:
    """One page/sample: OmniDocBench's unit of evaluation is a single page
    image, not a multi-page document."""

    index: int
    image_path: Path
    image_name: str
    page_no: int | None
    width: float | None
    height: float | None
    page_attribute: dict[str, Any] = field(default_factory=dict)

    @property
    def prediction_filename(self) -> str:
        """Deterministic, matches the evaluator's own convention exactly:
        the image filename with its extension swapped for `.md` (the
        upstream README shows `.jpg`; the HuggingFace copy of the dataset
        actually ships `.png` — swapping whatever extension is present,
        rather than hardcoding one, is what actually matches either)."""
        return Path(self.image_name).with_suffix(".md").name


def _find_ground_truth_json(dataset_root: Path) -> Path:
    for name in ("OmniDocBench.json", "OmniDocBench_demo.json"):
        candidate = dataset_root / name
        if candidate.exists():
            return candidate
    matches = sorted(dataset_root.glob("*.json"))
    if matches:
        return matches[0]
    raise DatasetError(
        f"no OmniDocBench ground-truth JSON found under {dataset_root} "
        f"(expected OmniDocBench.json or OmniDocBench_demo.json — see "
        f"experiments/005_omnidocbench/README.md for how to obtain the dataset)"
    )


def dataset_content_hash(ground_truth_path: Path) -> str:
    """SHA-256 of the ground-truth JSON *as bytes on disk*. Provenance only —
    recorded in run metadata so a result can be traced to exactly which copy
    of the file produced it. Not used to validate the file (a legitimate
    dataset update changes this hash; that isn't an error).

    NOTE: this is deliberately a hash of the exact bytes, so it identifies a
    *copy*, not a dataset version. It differs between a Windows checkout
    (CRLF) and a POSIX one (LF) for the same upstream commit — see
    `dataset_semantic_hash` for a hash that does not.
    """
    import hashlib

    digest = hashlib.sha256()
    with open(ground_truth_path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


# Re-exported so callers (and tests) can express paths relative to the same
# root `portable_path` normalizes against.
REPO_ROOT = _config.REPO_ROOT


def portable_path(path: Path | str, repo_root: Path | None = None) -> str:
    """Render `path` for a file that will be committed or shared.

    A path inside the repository becomes repo-relative; anything else is
    reduced to its final component. Absolute paths must not be written into
    result metadata: on POSIX they embed the operator's username
    (`/home/<user>/...`), and even without that they describe one machine's
    layout, which is noise in a file whose purpose is cross-machine
    comparison.

    This is the promise `build_benchmark_metadata` already documents; it was
    not previously enforced for `dataset_root`, and the committed Windows
    results show the consequence (`D:\\doc-extraction\\...`).
    """
    root = Path(repo_root) if repo_root is not None else REPO_ROOT
    p = Path(path)
    try:
        return Path(p).resolve().relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        # Outside the repository (a mounted dataset, a Kaggle input): keep the
        # leaf so the result is still identifiable, drop the machine layout.
        return p.name


def dataset_semantic_hash(ground_truth_path: Path) -> str:
    """SHA-256 of the ground-truth JSON's *decoded content*, independent of
    file formatting, indentation, encoding form and line endings.

    Why both this and `dataset_content_hash`: the byte hash answers "is this
    the identical file?", which is what you want when auditing one machine.
    It cannot answer "is this the same dataset?" across machines, because a
    Windows checkout of an unchanged upstream file hashes differently from a
    POSIX one (git's `core.autocrlf` rewrites LF to CRLF on checkout). That
    was observed concretely in this repository: the committed Windows runs
    under experiments/005_omnidocbench/results/ record
    `146690ea...` for the pinned demo ground truth, while a Linux checkout of
    the *same* pinned upstream commit yields `a0686ff3...`. The two files are
    byte-identical apart from line endings, but the recorded hashes suggest —
    wrongly — that two different datasets were evaluated.

    Comparing benchmark results across machines is the entire point of
    recording a dataset identifier, so runs also record this normalized hash,
    which is stable across platforms for the same logical dataset.
    """
    import hashlib
    import json as _json

    with open(ground_truth_path, "r", encoding="utf-8") as f:
        data = _json.load(f)
    canonical = _json.dumps(data, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_dataset(dataset_root: Path | str) -> tuple[Path, list[OmniDocSample]]:
    """Validate and enumerate an OmniDocBench dataset directory.

    Returns (ground_truth_json_path, samples), sorted by `index` (the
    record's position in the ground-truth JSON — deterministic and stable
    across re-runs). Raises `DatasetError` for anything that doesn't match
    the documented schema.
    """
    dataset_root = Path(dataset_root)
    if not dataset_root.exists():
        raise DatasetError(f"dataset path does not exist: {dataset_root}")
    if not dataset_root.is_dir():
        raise DatasetError(f"dataset path is not a directory: {dataset_root}")

    gt_path = _find_ground_truth_json(dataset_root)
    try:
        raw = json.loads(gt_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DatasetError(f"{gt_path} is not valid JSON: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise DatasetError(f"{gt_path} is not valid UTF-8: {exc}") from exc

    if not isinstance(raw, list):
        raise DatasetError(
            f"{gt_path}: expected a top-level JSON array of page records "
            f"(per the OmniDocBench dataset format), got {type(raw).__name__}"
        )
    if not raw:
        raise DatasetError(f"{gt_path}: contains zero records")

    search_dirs = [dataset_root / "images", dataset_root]
    samples: list[OmniDocSample] = []
    missing_images: list[str] = []

    for i, record in enumerate(raw):
        if not isinstance(record, dict):
            raise DatasetError(f"{gt_path}: record {i} is not a JSON object")
        page_info = record.get("page_info")
        if not isinstance(page_info, dict):
            raise DatasetError(
                f"{gt_path}: record {i} has no 'page_info' object — does not match the "
                f"OmniDocBench schema documented in experiments/005_omnidocbench/README.md"
            )
        image_path_field = page_info.get("image_path")
        if not image_path_field:
            raise DatasetError(f"{gt_path}: record {i}'s page_info has no 'image_path'")
        image_name = Path(image_path_field).name

        resolved: Path | None = None
        for base in search_dirs:
            candidate = base / image_name
            if candidate.exists():
                resolved = candidate
                break
        if resolved is None:
            missing_images.append(image_name)
            continue

        samples.append(
            OmniDocSample(
                index=i,
                image_path=resolved,
                image_name=image_name,
                page_no=page_info.get("page_no"),
                width=page_info.get("width"),
                height=page_info.get("height"),
                page_attribute=page_info.get("page_attribute") or {},
            )
        )

    if missing_images:
        raise DatasetError(
            f"{gt_path}: {len(missing_images)} of {len(raw)} record(s) reference an image "
            f"file not present under {dataset_root} (checked {[str(d) for d in search_dirs]}); "
            f"first few missing: {missing_images[:5]}. The dataset directory looks incomplete "
            f"— re-download rather than proceeding with a partial set."
        )

    samples.sort(key=lambda s: s.index)
    return gt_path, samples


def select_subset(
    samples: list[OmniDocSample], limit: int | None, seed: int = 0
) -> list[OmniDocSample]:
    """Deterministically pick `limit` samples spread across the dataset
    (every Nth record, not the first N) so a small validation subset isn't
    biased toward whatever document type happens to sort first. `seed`
    only shifts the starting offset — the selection is otherwise a pure
    function of `limit` and the sample list, so the same arguments always
    pick the same pages."""
    if limit is None or limit >= len(samples):
        return samples
    if limit <= 0:
        raise ValueError(f"limit must be positive, got {limit}")
    step = len(samples) / limit
    offset = seed % max(1, int(step) or 1)
    indices = sorted({min(len(samples) - 1, offset + int(i * step)) for i in range(limit)})
    return [samples[i] for i in indices]


# ---------------------------------------------------------------------------
# IR -> OmniDocBench end2end Markdown (spec §9)
# ---------------------------------------------------------------------------
#
# | Our representation        | OmniDocBench representation         | Notes |
# |----------------------------|--------------------------------------|-------|
# | Element.type=HEADING        | `#`..`######` Markdown heading         | level clamped to 1-6 |
# | Element.type=PARAGRAPH/TEXT  | plain text block, blank-line separated | matches evaluator's paragraph splitter |
# | Element.type=LIST_ITEM        | `- ` prefixed line                    | evaluator has no distinct list category; scored as text |
# | Element.type=TABLE + Table      | `<table>` HTML (pymupdf_tables route) or pipe-table (visual route) | evaluator auto-converts pipe tables to HTML before TEDS |
# | Element.type=FORMULA           | `$$...$$` (wrapped if not already LaTeX-delimited) | our backends rarely populate this — see README |
# | Element.type=IMAGE              | `![alt](name)`                        | not scored by end2end text/table/formula/order metrics |
# | Element.type=CHECKBOX/SIGNATURE/OTHER | element.text as plain text, if any | no OmniDocBench category maps to these; documented loss |
# | Page.reading_order               | Markdown block order                  | our own ordering, or a backend's — whichever produced the Document |
#
# Full write-up, including what information is unavoidably lost (span-level
# annotations, per-block attribute tags, our confidence scores — end2end
# markdown carries none of these), is in
# experiments/005_omnidocbench/README.md.

_LATEX_WRAPPERS = (("$$", "$$"), ("$", "$"), ("\\[", "\\]"), ("\\(", "\\)"))


def _looks_latex_wrapped(text: str) -> bool:
    stripped = text.strip()
    return any(stripped.startswith(l) and stripped.endswith(r) and len(stripped) > len(l) + len(r) for l, r in _LATEX_WRAPPERS)


def _element_to_markdown_block(element: Element, page: Page) -> str | None:
    if element.type == ElementType.TABLE and element.table_id:
        table = page.table_by_id(element.table_id)
        return table.to_markdown() if table is not None else None
    if element.type == ElementType.FORMULA:
        text = (element.text or "").strip()
        if not text:
            return None
        return text if _looks_latex_wrapped(text) else f"$${text}$$"
    if element.type == ElementType.HEADING:
        depth = min(max(element.level or 1, 1), 6)
        heading_text = (element.text or "").strip()
        return f"{'#' * depth} {heading_text}".rstrip() or None
    if element.type == ElementType.LIST_ITEM:
        return f"- {(element.text or '').strip()}".rstrip()
    if element.type == ElementType.IMAGE:
        name = element.source_id or "image"
        return f"![{name}]({name})"
    if element.text and element.text.strip():
        return element.text.strip()
    return None


def page_to_prediction_markdown(page: Page) -> str:
    """Render one canonical `Page` as OmniDocBench `end2end` prediction
    Markdown: blocks in reading order, separated by a blank line.

    This is deliberately a different rendering from `Document.to_markdown()`
    (which keeps a document title and a "## Page N" wrapper for our own
    human-readable inspection output) — that method is untouched by this
    module. An OmniDocBench prediction is one page with no wrapper at all.
    """
    order = page.reading_order or [e.id for e in page.elements]
    blocks: list[str] = []
    for element_id in order:
        element = page.element_by_id(element_id)
        if element is None:
            continue
        block = _element_to_markdown_block(element, page)
        if block:
            blocks.append(block)
    return ("\n\n".join(blocks) + "\n") if blocks else "\n"


# ---------------------------------------------------------------------------
# Prediction generation (spec §6, §7)
# ---------------------------------------------------------------------------


@dataclass
class PredictionRunResult:
    sample: OmniDocSample
    output_path: Path
    runtime_seconds: float
    route: str
    error: str | None = None


def write_predictions(
    samples: list[OmniDocSample],
    predictions_dir: Path,
    process_sample: Callable[[Path], tuple[Page, str, float]],
    logger: Callable[[str], None] | None = None,
) -> list[PredictionRunResult]:
    """Run `process_sample` (supplied by the caller — see
    experiments/005_omnidocbench/prepare.py, which wires this to
    `doc_extraction.cli.process_file`) over every sample and write one
    Markdown prediction file per page.

    `process_sample(image_path) -> (page, route, runtime_seconds)` is
    injected rather than imported directly so this module stays free of a
    hard dependency on any particular backend, and so tests can supply a
    fake without needing Docling/torch installed.

    A per-sample failure is recorded (`PredictionRunResult.error`) and
    processing continues — one bad page must not abort a benchmark run of
    hundreds of pages — but nothing is swallowed silently: every failure is
    visible in the returned results and in `runtime.json`.
    """
    predictions_dir.mkdir(parents=True, exist_ok=True)
    results: list[PredictionRunResult] = []
    for sample in samples:
        out_path = predictions_dir / sample.prediction_filename
        try:
            page, route, runtime_seconds = process_sample(sample.image_path)
            markdown = page_to_prediction_markdown(page)
            out_path.write_text(markdown, encoding="utf-8")
            results.append(PredictionRunResult(sample, out_path, runtime_seconds, route))
            if logger:
                logger(f"ok    {sample.image_name} ({runtime_seconds:.2f}s, route={route})")
        except Exception as exc:  # noqa: BLE001 - recorded per-sample, run continues
            results.append(
                PredictionRunResult(sample, out_path, 0.0, "error", error=f"{type(exc).__name__}: {exc}")
            )
            if logger:
                logger(f"FAIL  {sample.image_name}: {type(exc).__name__}: {exc}")
    return results


def write_runtime_report(results: list[PredictionRunResult], path: Path) -> dict[str, Any]:
    ok = [r for r in results if r.error is None]
    failed = [r for r in results if r.error is not None]
    total_runtime = sum(r.runtime_seconds for r in ok)
    report = {
        "total_pages": len(results),
        "succeeded": len(ok),
        "failed": len(failed),
        "total_runtime_seconds": round(total_runtime, 3),
        "mean_seconds_per_page": round(total_runtime / len(ok), 4) if ok else None,
        "pages_per_second": round(len(ok) / total_runtime, 4) if total_runtime > 0 else None,
        "routes": _count_routes(ok),
        "failures": [{"image": r.sample.image_name, "error": r.error} for r in failed],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def _count_routes(results: list[PredictionRunResult]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in results:
        counts[r.route] = counts.get(r.route, 0) + 1
    return counts


# ---------------------------------------------------------------------------
# Benchmark run metadata (spec §8)
# ---------------------------------------------------------------------------


def build_benchmark_metadata(
    *,
    backend: str,
    device: str,
    ground_truth_path: Path,
    num_samples: int,
    config_snapshot: dict[str, Any],
    model_versions: dict[str, str] | None = None,
) -> dict[str, Any]:
    """The provenance record every benchmark run writes. Paths are relative
    to the repository root wherever practical — no local username or
    absolute machine path leaks into a file meant to be committed/shared."""
    return {
        "benchmark": "OmniDocBench",
        "upstream_repo": PINNED_UPSTREAM_REPO,
        "upstream_commit": PINNED_UPSTREAM_COMMIT,
        "backend": backend,
        "device": device,
        "python": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ground_truth_file": ground_truth_path.name,
        # Byte hash identifies the exact copy; semantic hash identifies the
        # dataset across platforms (CRLF/LF). See the two functions' docs.
        "ground_truth_sha256": dataset_content_hash(ground_truth_path),
        "ground_truth_semantic_sha256": dataset_semantic_hash(ground_truth_path),
        "num_samples": num_samples,
        "model_versions": model_versions or {},
        "config": config_snapshot,
    }


# ---------------------------------------------------------------------------
# Evaluator config generation & invocation (spec §6, §7)
# ---------------------------------------------------------------------------


def write_evaluator_config(
    *,
    ground_truth_path: Path,
    predictions_dir: Path,
    output_path: Path,
    match_method: str = "quick_match",
    match_workers: int = 4,
    include_bleu_meteor: bool = False,
    include_cdm: bool = False,
) -> Path:
    """Render an `end2end.yaml`-shaped config for the official evaluator.

    `include_cdm` defaults to False: CDM (formula rendering) needs a
    Linux-only toolchain (TeX Live + ImageMagick 7.x built from source +
    Ghostscript) — the upstream project's own `pyproject.toml` states this
    explicitly under `[tool.omnidocbench.system-dependencies]` at the pinned
    commit, it isn't a guess. Enable it only on a Linux/Docker runner that
    actually has that toolchain; see docs in
    experiments/005_omnidocbench/README.md.
    """
    import yaml

    text_metrics = ["Edit_dist"] + (["BLEU", "METEOR"] if include_bleu_meteor else [])
    formula_metrics = ["Edit_dist"] + (["CDM"] if include_cdm else [])

    config = {
        "end2end_eval": {
            "metrics": {
                "text_block": {"metric": text_metrics},
                "display_formula": {"metric": formula_metrics},
                "table": {"metric": ["TEDS", "Edit_dist"]},
                "reading_order": {"metric": ["Edit_dist"]},
            },
            "dataset": {
                "dataset_name": "end2end_dataset",
                "ground_truth": {"data_path": str(ground_truth_path)},
                "prediction": {"data_path": str(predictions_dir)},
                "match_method": match_method,
                "match_workers": match_workers,
            },
        }
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # Windows paths (backslashes, drive-letter colons) round-trip safely
    # through PyYAML's default emitter without needing manual escaping —
    # let it choose the scalar style rather than hand-quoting.
    with open(output_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
    return output_path


def default_omnidoc_python(repo_root: Path | str) -> Path:
    """Platform-appropriate path to the isolated evaluator venv's
    interpreter, assuming the standard `.venv-omnidoc` layout described in
    experiments/005_omnidocbench/README.md — `bin/python` on Linux/macOS
    (e.g. Kaggle), `Scripts/python.exe` on Windows. A venv only ever gets
    one of these two layouts, keyed off the OS it was created on."""
    subdir = ("Scripts", "python.exe") if os.name == "nt" else ("bin", "python")
    return Path(repo_root) / ".venv-omnidoc" / subdir[0] / subdir[1]


class EvaluatorNotAvailableError(RuntimeError):
    """The isolated evaluator environment isn't set up yet. Carries setup
    instructions rather than a bare failure — see
    experiments/005_omnidocbench/README.md for the full sequence."""


def check_evaluator_available(omnidoc_python: Path, omnidoc_repo: Path) -> None:
    if not Path(omnidoc_python).exists():
        venv_python = "bin/python" if os.name != "nt" else "Scripts\\python.exe"
        raise EvaluatorNotAvailableError(
            f"no Python interpreter at {omnidoc_python}. Set up the isolated evaluator "
            f"environment first: py -3.11 -m venv .venv-omnidoc && "
            f".venv-omnidoc/{venv_python} -m pip install -e {omnidoc_repo} "
            f"(see experiments/005_omnidocbench/README.md)"
        )
    if not (Path(omnidoc_repo) / "pdf_validation.py").exists():
        raise EvaluatorNotAvailableError(
            f"{omnidoc_repo} does not look like an OmniDocBench checkout "
            f"(pdf_validation.py not found). Clone it: git clone "
            f"{PINNED_UPSTREAM_REPO} {omnidoc_repo} && cd {omnidoc_repo} && "
            f"git checkout {PINNED_UPSTREAM_COMMIT}"
        )


def run_official_evaluator(
    *,
    omnidoc_python: Path,
    omnidoc_repo: Path,
    config_path: Path,
    log_path: Path | None = None,
    timeout_seconds: int | None = None,
) -> subprocess.CompletedProcess:
    """Invoke the official evaluator: `python pdf_validation.py --config
    <config_path>`, run from inside the cloned repo (it uses relative
    imports and writes results to a `./result/` directory relative to its
    own working directory — both are the evaluator's own design, not
    something this adapter controls).

    Raises `EvaluatorNotAvailableError` up front rather than letting a
    missing interpreter surface as a confusing subprocess error.

    Sets `PYTHONUTF8=1` for the subprocess. The evaluator (developed and
    tested on Linux) opens the ground-truth JSON with the platform-default
    encoding rather than an explicit `utf-8`; on Windows that default is a
    codepage such as cp1252, which cannot decode the dataset's Chinese-
    language content and crashes with `UnicodeDecodeError` on the very
    first run. Python's standard UTF-8 mode (PEP 540) fixes this without
    touching a single line of the evaluator's own source — confirmed
    against the pinned commit; see experiments/005_omnidocbench/README.md
    "Known Windows issue".
    """
    check_evaluator_available(omnidoc_python, omnidoc_repo)
    config_path = Path(config_path).resolve()
    cmd = [str(omnidoc_python), "pdf_validation.py", "--config", str(config_path)]
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    process = subprocess.run(
        cmd,
        cwd=str(omnidoc_repo),
        capture_output=True,
        # Decode the child's UTF-8 output explicitly rather than via
        # text=True's locale-default decoding — on Windows that default is
        # the same cp1252-family codepage that motivates PYTHONUTF8 above,
        # and would otherwise crash *our* capture of the evaluator's
        # Chinese-language dataset paths/messages even once the child
        # itself runs cleanly. errors="replace" so a capture glitch shows up
        # as a few replacement characters in the log, never a crash that
        # discards real evaluator output.
        encoding="utf-8",
        errors="replace",
        timeout=timeout_seconds,
        env=env,
    )
    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(
            f"$ {' '.join(cmd)}\n(cwd={omnidoc_repo})\n\n--- stdout ---\n{process.stdout}\n"
            f"\n--- stderr ---\n{process.stderr}\n\nexit code: {process.returncode}\n",
            encoding="utf-8",
        )
    return process


def collect_evaluator_results(omnidoc_repo: Path, save_name: str) -> dict[str, Path]:
    """Locate the result files the evaluator just wrote under
    `<omnidoc_repo>/result/` for the given `save_name` (see
    `build_save_name` in the pinned commit's `src/core/pipeline.py`:
    `basename(prediction_dir) + "_" + match_method`).

    Returns whichever of the expected files actually exist — the evaluator
    only writes some of them depending on which metrics were configured —
    keyed by a short logical name, not asserted to all be present.
    """
    result_dir = Path(omnidoc_repo) / "result"
    candidates = {
        "metric_result": result_dir / f"{save_name}_metric_result.json",
        "run_summary": result_dir / f"{save_name}_run_summary.json",
        "runtime_environment": result_dir / f"{save_name}_runtime_environment.json",
    }
    return {name: path for name, path in candidates.items() if path.exists()}
