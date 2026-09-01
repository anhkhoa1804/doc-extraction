# doc-extraction

A modular, research-oriented pipeline for extracting structured content from
heterogeneous enterprise documents (PDF, DOCX, XLSX, PPTX, scanned images).

**CPU-first: no GPU is required, and every result in this repository is
reproducible without one.** A GPU path now exists and has been measured (see
[experiments/006](experiments/006_linux_gpu_validation/)); it is an
optimization, not a requirement, and produces identical output.

## What this is — and isn't

This repository is **extraction infrastructure**, not a finished extraction
product. The premise: average-case document extraction is already handled
reasonably well by current open-source SOTA (Docling, MinerU,
PaddleOCR/PP-Structure, table-structure models, document VLMs). What is
actually interesting is where those systems *fail* — hard cases, long-tail
layouts, noisy scans, complex tables, reading-order mistakes — and how a
pipeline should route around them.

So this repo is built to make every stage **observable and swappable**, and
to make failures **visible**, rather than to squeeze out the last point of
accuracy today. See [docs/research-roadmap.md](docs/research-roadmap.md).

Out of scope: model training/fine-tuning, knowledge graphs, ontologies, RAG,
business/workflow reasoning. The output is a structured document
representation; what consumes it is someone else's problem.

## The central design decision

"Does this PDF have a text layer?" is **not** the same question as "is this
PDF's text layer usable?". Conflating them produces the worst available
failure: confident, plentiful, wrong output that nothing downstream detects.

One document in this repo's own corpus decodes `Độc lập Tự do Hạnh phúc` as
`ĈӝF OұS 7ӵ GR +ҥQK SK~F` — a broken embedded-font `ToUnicode` CMap. It has
*more* than enough characters to pass a naive quantity check.

So PDF routing asks both questions, both cheaply:

```
PDF ─┬─ too little text ──────────────────────► scanned_pdf  (render + OCR)
     ├─ text present but fails quality checks ─► scanned_pdf  (render + OCR)
     └─ passes both ─────────────────────────► digital_pdf  (native, ~free)
                                                  └─ per-page quality check
                                                     └─ bad page? render + OCR
                                                        that page only
```

The quality check ([`ingest/text_quality.py`](src/doc_extraction/ingest/text_quality.py))
uses only already-extracted text — no rendering, no OCR, no model — so it is
cheap enough to run on every page, which is what makes per-page fallback
affordable. Thresholds are **calibrated against this corpus**, not guessed:
see [experiments/001_pdf_text_quality](experiments/001_pdf_text_quality/).

## Architecture

```
input documents
    -> file/type detection            ingest/classifier.py
    -> route selection                ingest/dispatcher.py   (quantity + quality)
    -> format-specific parsing        pipelines/office.py, pipelines/pdf.py
    -> table structure                stages/table.py        (native or visual)
    -> rendering (only where needed)  stages/render.py
    -> OCR / layout                   stages/ocr.py, stages/layout.py
    -> reading order                  stages/reading_order.py
    -> assembly / export              stages/assemble.py
    -> canonical structured document  schemas/document.py
```

Every stage persists its own intermediate output under
`outputs/<document_id>/<stage>/` — there is no black-box `extract()`. See
[docs/architecture.md](docs/architecture.md) and
[docs/output-format.md](docs/output-format.md).

## Data

Local, internal enterprise sample documents (`*.pdf`, `*.docx`, `*.xlsx`)
live under `data/` and are used as pipeline input. They are **never
renamed or modified** — every run reads them and writes exclusively under
`outputs/`. They are **intentionally excluded from Git**; see
[data/README.md](data/README.md) for why and for the committed manifest
that documents them without distributing their content.

## Kaggle

Public [OmniDocBench](https://github.com/opendatalab/OmniDocBench)
experiments (`experiments/005_omnidocbench/`) can be run on a Kaggle T4
GPU. Nothing under `data/` is ever attached to Kaggle. See
[docs/kaggle.md](docs/kaggle.md).

## Quick start

```bash
# POSIX
python3.12 -m venv .venv && .venv/bin/python -m pip install -e ".[docling,tables,dev]"

# Windows
py -3.12 -m venv --system-site-packages .venv
.venv/Scripts/python.exe -m pip install -e ".[docling,tables,dev]"
```

Or `make setup`, which picks the right interpreter path for the platform.

Then fetch the models once (~1.5 GB) with `make models`. This is **required**
before the visual/OCR route will run, not optional: the project points
`DOCLING_ARTIFACTS_PATH` at `.cache/docling`, and Docling disables
auto-download whenever that variable is set.

Windows users will hit an `antlr4-python3-runtime` packaging snag — the
two-command fix is in [docs/setup.md](docs/setup.md), along with the
cache-redirection environment variables that keep multi-GB model downloads
off a full system drive.

## Local validation (CPU-only)

The whole sequence, reproducible from a clean checkout, no GPU:

```bash
# $PY is .venv/bin/python on POSIX, .venv/Scripts/python.exe on Windows.
$PY -m pytest -q
$PY -m doc_extraction run     --input data --config configs/cpu.yaml
$PY -m doc_extraction compare --input data --config configs/cpu.yaml --backends baseline docling
$PY -m doc_extraction inspect
$PY scripts/build_failure_report.py --input outputs/
```

Or with GNU make: `make setup && make models && make test && make baseline && make compare && make report`.

On a clean checkout `data/` is empty (the corpus is private — see
[data/README.md](data/README.md)), so `pytest` reports the corpus-dependent
tests as **skipped**, not failed, and `run`/`compare` have no input. The
suite itself passes with no local documents present.

`compare` runs Docling over every input and takes ~35 s per page on CPU —
point it at a single file rather than the whole corpus unless you mean it.

## Commands

| Command | Purpose |
|---|---|
| `scripts/validate_environment.py` | Check what this machine can run — Python, deps, GPU, model cache, Docker — and what to do about each gap. Loads no model. |
| `doc_extraction run --input <path>` | Baseline modular pipeline (or one named backend) over a file or directory |
| `doc_extraction run --device auto` | Pick cpu/cuda from the GPU's *current* free VRAM, utilization and co-tenants |
| `scripts/profile_pipeline.py --input outputs/` | Per-stage cold/warm timings from runs that already happened |
| `doc_extraction compare --input <path> --backends baseline docling` | Run several systems over the same input and report structural **disagreement** |
| `doc_extraction inspect [<document_id>]` | HTML viewer: page image + bbox overlays + OCR + tables + final IR. Omit the id to build all |
| `scripts/build_failure_report.py --input outputs/` | Failure-analysis report across everything already extracted |

Thin wrappers in `scripts/` provide the same for environments without `make`.

## Output

Every run writes `outputs/<document_id>/` — `metadata.json` (including the
route decision *and its evidence*), per-stage intermediates, `final/`, and
`logs/pipeline.jsonl`. Nothing is written next to the inputs. See
[docs/output-format.md](docs/output-format.md).

## Shared-machine execution

`device: auto` inspects the GPU's current state and picks a device, rather
than assuming a GPU that exists is a GPU that is free:

```bash
doc_extraction run --input data --device auto
# device: auto -> cpu: 1 other compute process(es) holding 4746 MiB at 100% utilization — actively computing
```

`cpu` and `cuda` keep their literal meanings — an explicit choice is never
overridden, because a recorded benchmark device that the pipeline silently
changed would be worthless. Only `auto` probes. The decision and the GPU
state behind it are written to `metadata.json` as `device_decision`, so a
result explains which device it used *and why*. See
[docs/reproducibility-matrix.md](docs/reproducibility-matrix.md) for what has
actually been validated, and with what contention.

## Status

| Component | Status |
|---|---|
| Native PDF text + tables (PyMuPDF) | Validated locally, CPU |
| Native DOCX / XLSX / PPTX | Validated locally, CPU |
| Docling (whole-document, and layout+OCR components) | Validated locally, CPU |
| Table Transformer (visual route) | Validated locally, CPU |
| MinerU, PaddleOCR | Optional, **not installed** — adapters report unavailable |
| Document VLM | **Planned** — interface only, no implementation |
| Linux (Ubuntu 22.04, Python 3.12) | Validated — full suite + visual route, see [experiments/006](experiments/006_linux_gpu_validation/) |
| GPU (NVIDIA L4, CUDA 12.8) | **Validated.** Models and input tensors confirmed on `cuda:0`; output byte-identical to CPU; 8.9× warm layout speedup — see [experiments/006](experiments/006_linux_gpu_validation/) |
| Docker (CPU) | Builds and runs the test suite; see [docs/reproducible-environment.md](docs/reproducible-environment.md) |
| Docker (GPU) | **Not built.** Needs a host-level NVIDIA Container Toolkit change |

Details and per-backend install notes: [docs/backends.md](docs/backends.md).

## Benchmarking against OmniDocBench

[OmniDocBench](https://github.com/opendatalab/OmniDocBench) (CVPR 2025) is
integrated as an external, unmodified evaluator — see
[experiments/005_omnidocbench](experiments/005_omnidocbench/) for the
adapter, the exact upstream commit pinned, the IR→benchmark field mapping,
and results from a validated small-subset run (`baseline` and `docling`
backends; the full 1651-page benchmark needs more CPU time or a GPU than
this dev machine has — the same run is prepared and documented for Kaggle
in that directory's `kaggle/` notebook).

## Documentation

- [docs/architecture.md](docs/architecture.md) — pipeline and component boundaries
- [docs/setup.md](docs/setup.md) — environment, dependencies, caches, CPU/GPU
- [docs/backends.md](docs/backends.md) — per-backend status, install, limits, licences
- [docs/output-format.md](docs/output-format.md) — canonical IR, schema version, coordinates
- [docs/experimentation.md](docs/experimentation.md) — reproducibility, comparison, logging
- [docs/research-roadmap.md](docs/research-roadmap.md) — hypotheses, with evidence and its limits
- [docs/kaggle.md](docs/kaggle.md) — running public OmniDocBench experiments on a Kaggle T4 GPU
- [experiments/](experiments/) — investigations actually run, with observations
