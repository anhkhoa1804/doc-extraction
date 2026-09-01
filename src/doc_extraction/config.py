"""Pipeline configuration.

Config is a plain, serializable object (so it can be dropped verbatim into
RunMetadata.config_snapshot for reproducibility) loaded from a YAML file and
optionally overridden by CLI flags. See configs/default.yaml, configs/cpu.yaml,
configs/gpu.yaml.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CACHE_DIR = REPO_ROOT / ".cache"


class BackendToggles(BaseModel):
    """Which whole-document backends are enabled for `compare`, and which
    stage-level backend the baseline pipeline should prefer. A backend can be
    "enabled" here and still be reported unavailable at run time if it isn't
    installed — see backends/*_backend.py `is_available()`."""

    docling: bool = True
    mineru: bool = False
    paddleocr: bool = False
    vlm: bool = False


class PipelineConfig(BaseModel):
    # Local/private sample documents live under data/ (gitignored — see
    # data/README.md), not the repo root.
    input_dir: str = "data"
    output_dir: str = "outputs"
    # "cpu" | "cuda" | "auto". "auto" inspects the GPU's *current* state
    # (free VRAM, utilization, other compute processes) and picks a device —
    # see utils/resources.py. It is not "cuda if a GPU exists": on a shared
    # machine that would compete with another project's job. An explicit
    # "cpu"/"cuda" is always honoured verbatim so a recorded benchmark device
    # is never silently overridden.
    device: str = "cpu"
    # VRAM this workload should assume it needs, for `device: auto` only.
    # The visual route on real benchmark pages was measured peaking near
    # 16.6 GiB; the default here is deliberately modest so light work is not
    # vetoed off the GPU by a pessimistic default.
    gpu_required_mib: int = 2048
    # VRAM left unclaimed for co-tenants when `auto` decides. A courtesy
    # margin, not an enforced cap.
    gpu_safety_margin_mib: int = 1024
    # Whether `auto` may use a GPU that already has an idle co-tenant.
    # False makes `auto` require an entirely clear GPU.
    gpu_allow_shared: bool = True

    # Rendering (stages/render.py)
    render_dpi: int = 200

    # --- PDF routing: quantity gate (ingest/dispatcher.py) ---
    # A PDF page counts as "has text" if it yields at least this many
    # extractable characters; a document clears the quantity gate if at least
    # `digital_pdf_page_ratio` of sampled pages do.
    digital_pdf_min_chars_per_page: int = 40
    digital_pdf_page_ratio: float = 0.6
    digital_pdf_sample_pages: int = 5

    # --- PDF routing: quality gate (ingest/text_quality.py) ---
    # Defaults calibrated against this repo's sample corpus (22 clean pages,
    # 2 known-corrupt pages) — see experiments/001_pdf_text_quality/.
    # Re-calibrate with scripts/calibrate_text_quality.py for a new corpus.
    text_quality_min_chars: int = 200
    text_quality_max_mixed_script_word_ratio: float = 0.10
    text_quality_max_unexpected_script_ratio: float = 0.10
    text_quality_max_replacement_ratio: float = 0.02
    text_quality_max_control_ratio: float = 0.02
    text_quality_min_alpha_ratio: float = 0.30
    text_quality_max_digit_in_word_ratio: float = 0.30
    text_quality_expected_scripts: list[str] = Field(default_factory=lambda: ["LATIN"])
    # Fraction of sampled pages that may fail quality checks before the whole
    # document is rerouted to the visual/OCR path.
    text_quality_max_suspicious_page_ratio: float = 0.34
    # Within the digital-PDF route, re-extract individual suspicious pages
    # via the visual/OCR path instead of trusting their text layer. This is
    # the "cheap signal, expensive fix only where needed" mechanism; it
    # requires an OCR backend to be available.
    digital_pdf_page_fallback: bool = True

    # --- Tables ---
    # Extract table structure from digital PDFs using PyMuPDF's native
    # (vector/text-layer) table finder — no rendering, no OCR, no model.
    digital_pdf_tables: bool = True

    # OCR (stages/ocr.py)
    ocr_languages: list[str] = Field(default_factory=lambda: ["en", "vi"])

    # Backend selection
    layout_backend: str = "docling"
    ocr_backend: str = "docling"
    table_backend: str = "table_transformer"
    backends: BackendToggles = Field(default_factory=BackendToggles)

    # Caching. Relative by default so a clone on another machine resolves it
    # against its own working directory — `config_snapshot` in metadata.json
    # then stays machine-independent. `configure_caches()` resolves it.
    cache_dir: str = ".cache"

    log_level: str = "INFO"

    def to_snapshot(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def configure_caches(cache_dir: str | Path | None = None) -> None:
    """Point HuggingFace Hub / Docling model downloads and pip's own cache at
    a project-local directory instead of their per-user defaults under the
    OS drive. On the reference machine the OS drive has <8 GB free while the
    repo lives on a roomier drive, so this is not cosmetic — it's
    load-bearing. Only sets vars that aren't already set, so an operator's
    explicit environment always wins.

    A relative `cache_dir` is resolved against the repository root, not the
    process working directory, so `doc_extraction` run from anywhere still
    finds the same cache.
    """
    base = Path(cache_dir) if cache_dir else DEFAULT_CACHE_DIR
    if not base.is_absolute():
        base = REPO_ROOT / base

    # Create a directory only for a variable we are actually going to set.
    # Creating all of them unconditionally contradicts the "operator's
    # environment wins" rule above: in a container where HF_HOME and friends
    # are already pointed at a mounted volume, it would still try to mkdir
    # under the repo root — which fails outright when that path is not
    # writable by the running user, for directories nothing would ever use.
    for variable, path in (
        ("HF_HOME", base / "huggingface"),
        ("HUGGINGFACE_HUB_CACHE", base / "huggingface" / "hub"),
        ("DOCLING_ARTIFACTS_PATH", base / "docling"),
        ("PIP_CACHE_DIR", base / "pip"),
    ):
        if os.environ.get(variable):
            continue
        path.mkdir(parents=True, exist_ok=True)
        os.environ[variable] = str(path)


def load_config(path: str | Path | None = None, overrides: dict[str, Any] | None = None) -> PipelineConfig:
    data: dict[str, Any] = {}
    if path is not None:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    if overrides:
        data = _deep_merge(data, overrides)
    config = PipelineConfig.model_validate(data)
    configure_caches(config.cache_dir)
    return config


def _deep_merge(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged
