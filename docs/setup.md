# Setup

CPU-only. Nothing here needs a GPU or CUDA.

## Environment this was built and validated against

Windows, no WSL, CPU-only. These specifics matter because they change what
"just install it" means:

- **Python**: use the `py` launcher explicitly — `py -3.12`. On the reference
  machine, plain `python`/`python3` on PATH resolved to an incomplete MSYS2
  build with no working `pip`. Verify yours:
  ```bash
  py -3.12 -c "import sys; print(sys.executable)"
  ```
- **Disk**: pip's cache, HuggingFace Hub downloads, and Docling's model
  artifacts total ~1.9 GB and default to per-user directories on the OS
  drive. On the reference machine that drive has <8 GB free while the repo
  lives on a roomier data drive, so redirecting them is load-bearing rather
  than cosmetic. See "Cache redirection" below.
- **GPU**: `torch.cuda.is_available()` is **False** here (CPU-only torch
  2.8.0+cpu; the GPU driver caps at CUDA 11.2). No GPU path in this repo has
  been validated — see [backends.md](backends.md).
- **No `make`** on plain Windows. Every `make` target is a one-liner with a
  direct `python -m doc_extraction ...` equivalent; see the Makefile.

## Install

```bash
# 1. Venv. --system-site-packages reuses an existing global torch/transformers
#    rather than re-downloading ~2 GB. pip still shadows anything you install
#    explicitly inside the venv.
py -3.12 -m venv --system-site-packages .venv

# 2. Core package only — parsing, schemas, CLI, native PDF tables.
#    No OCR/layout model, no torch requirement.
.venv/Scripts/python.exe -m pip install -e .

# 3. Backends (Docling + Table Transformer) and dev tools.
.venv/Scripts/python.exe -m pip install -e ".[docling,tables,dev]"
```

The core install is deliberately light: `import doc_extraction` must never
require a heavy optional dependency, and a test enforces that.

### Windows snag: `antlr4-python3-runtime`

Docling depends on `omegaconf`, which pins `antlr4-python3-runtime==4.9.3`.
That version has no prebuilt Windows wheel and its sdist fails under PEP 517
build isolation with:

```
error: [Errno 2] No such file or directory: 'bin\pygrun'
```

Install it once via the legacy build path first — it builds fine once
`setuptools`/`wheel` are present in the venv:

```bash
.venv/Scripts/python.exe -m pip install --upgrade setuptools wheel
.venv/Scripts/python.exe -m pip install "antlr4-python3-runtime==4.9.3" --no-use-pep517
.venv/Scripts/python.exe -m pip install -e ".[docling,tables,dev]"
```

## Cache redirection

`configs/*.yaml` set `cache_dir: ".cache"` (relative, resolved against the
repo root), and `config.configure_caches()` exports `HF_HOME`,
`HUGGINGFACE_HUB_CACHE`, `DOCLING_ARTIFACTS_PATH`, and `PIP_CACHE_DIR` to
point inside it — but only for variables not already set, so your
environment always wins.

That happens **after** `doc_extraction.config` is imported, which does not
help `pip`'s own download cache. Export it yourself before installing:

```bash
export PIP_CACHE_DIR="$(pwd)/.cache/pip"                 # bash
$env:PIP_CACHE_DIR = "$(Get-Location)\.cache\pip"        # PowerShell
```

`.cache/` is gitignored.

## Prefetching models (optional)

First use downloads ~1.5 GB (Docling + EasyOCR) and ~110 MB (Table
Transformer). To fetch them up front rather than mid-run:

```bash
export HF_HOME="$(pwd)/.cache/huggingface"
.venv/Scripts/python.exe -m docling.cli.tools models download -o .cache/docling
.venv/Scripts/python.exe -m docling.cli.tools models download easyocr \
    --easyocr-lang en --easyocr-lang vi -o .cache/docling
```

Vietnamese matters here: Docling's default OCR engine (RapidOCR) has no
dedicated Vietnamese model, so this project configures EasyOCR instead. See
[backends.md](backends.md).

Once cached, the whole validation sequence runs offline.

## Verify

```bash
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m doc_extraction run --input . --config configs/cpu.yaml
```

The full validation sequence is in the [README](../README.md) under "Local
validation".

## A second environment: benchmarking

Benchmarking against OmniDocBench (`experiments/005_omnidocbench/`) needs
its own Python 3.10/3.11 environment, separate from everything above — the
official evaluator requires `<3.12`, and this project's main `.venv` is
3.12. That setup (including two Windows-specific bugs found and worked
around) is documented on its own in
[experiments/005_omnidocbench/README.md](../experiments/005_omnidocbench/README.md)
rather than duplicated here, since it's optional and unrelated to running
the extraction pipeline itself.
