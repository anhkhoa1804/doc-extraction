# Reproducible environments

This project has, as of this document, **three** environments that are kept
deliberately separate. Mixing them is the single easiest way to produce a
benchmark number that cannot be reproduced.

| Environment | Python | torch | Purpose |
|---|---|---|---|
| Extraction — CPU | 3.12 | CPU build | The validated reference. All CPU results. |
| Extraction — GPU | 3.12 | CUDA build | GPU execution only. Same source, same models. |
| OmniDocBench evaluator | 3.11 | n/a | The official evaluator, unmodified. Never mixed with the above. |

The evaluator is kept apart because it is an *external, unmodified* judge:
if it shared an environment with the system under test, a dependency bump
made for extraction could silently change the score.

## Why CPU and GPU are separate environments here

`torch` ships as either a CPU build or a CUDA build, not both. Installing the
CUDA build over the CPU one replaces it, which invalidates any CPU timing
previously measured in that environment. Keeping two environments means a
CPU-vs-GPU comparison is a comparison of two *pinned, still-present* stacks
rather than a before/after on one mutated stack.

Verified on this machine: both environments produce **byte-identical
extraction output** for the same input — same text, same tables, 0.000 px
bbox delta. Only runtime differs. That is the property that makes the
comparison meaningful.

## Building them

```bash
# CPU (the validated reference)
uv venv --python 3.12 ~/.venvs/doc-extraction-linux312
uv pip install --python ~/.venvs/doc-extraction-linux312/bin/python -e ".[docling,tables,dev]"

# GPU — note the explicit CUDA index; without it pip resolves the CPU wheel
# and torch.cuda.is_available() is False on a perfectly good GPU.
uv venv --python 3.12 ~/.venvs/doc-extraction-gpu312
uv pip install --python ~/.venvs/doc-extraction-gpu312/bin/python \
    --index-url https://download.pytorch.org/whl/cu128 torch torchvision
uv pip install --python ~/.venvs/doc-extraction-gpu312/bin/python -e ".[docling,tables,dev]"
```

Check which one you are in before trusting a number:

```bash
python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
# 2.13.0+cpu   False     <- CPU environment
# 2.11.0+cu128 True      <- GPU environment
```

`2.x.y+cpu` with `False` means the *build* has no CUDA support. It says
nothing about whether a GPU is present or free — a distinction worth making
explicitly, because the two are easy to confuse when debugging.

## Models are never part of the environment

Model weights (~1.5 GB) are downloaded once into `.cache/` and shared by both
environments. They are not in the venvs, not in git, and not in the Docker
image.

```bash
export HF_HOME="$(pwd)/.cache/huggingface"
python -m docling.cli.tools models download -o .cache/docling
python -m docling.cli.tools models download easyocr \
    --easyocr-lang en --easyocr-lang vi -o .cache/docling
```

**Setting `DOCLING_ARTIFACTS_PATH` disables Docling's auto-download.** Once
`config.configure_caches()` has pointed it at `.cache/docling`, Docling will
only use models already there — an empty directory produces
`FileNotFoundError: Missing .../craft_mlt_25k.pth and downloads disabled`
rather than fetching them. Prefetch first. This is documented upstream
behaviour, not a bug, but it is the most common first-run failure here.

## Docker (CPU)

`Dockerfile` builds the CPU environment reproducibly.

```bash
docker build -t doc-extraction:cpu .
docker run --rm doc-extraction:cpu                    # runs the test suite
```

To do real work, mount the things that are deliberately *not* in the image:

```bash
docker run --rm --user "$(id -u):$(id -g)" \
    -v "$(pwd)/.cache:/cache" \
    -v "$(pwd)/data:/data:ro" \
    -v "$(pwd)/outputs:/outputs" \
    doc-extraction:cpu \
    python -m doc_extraction run --input /data --output /outputs --config configs/cpu.yaml
```

`--user "$(id -u):$(id -g)"` is required whenever you bind-mount a writable
directory. The image's own `appuser` is uid 1000; if your host uid differs
(1002 here) the container cannot write to your mounted `outputs/`. Running as
your own uid fixes that *and* keeps the resulting files owned by you.

The image sets `HF_HOME`, `HUGGINGFACE_HUB_CACHE`, `DOCLING_ARTIFACTS_PATH`
**and** `PIP_CACHE_DIR` to paths under `/cache`. All four matter:
`configure_caches()` creates a project-local directory for any of them it
finds unset, and `/app` is not writable by a non-root user.

The image deliberately contains **no** private documents, **no** model
weights, **no** benchmark dataset, **no** outputs and **no** credentials —
see `.dockerignore`. An image gets copied and shared; those must not travel
with it. Input is mounted read-only.

The container runs as a non-root `appuser` (uid 1000) so files written to a
mounted `outputs/` are not root-owned on the host.

### GPU Docker — not built

Not built or validated here. It needs the NVIDIA Container Toolkit on the
host; on a shared machine that is a host-level change that should be a
deliberate, separately-approved decision rather than a side effect of running
this project. The native GPU environment above is validated and needs no such
change.

## Recording an environment with a result

Every run writes `metadata.json` with `model_versions`, `config_snapshot`,
`device` and a timestamp; OmniDocBench runs additionally record the upstream
commit, the dataset hashes, Python version and platform.

Two dataset hashes are recorded, deliberately:

* `ground_truth_sha256` — hash of the exact bytes. Identifies a *copy*.
* `ground_truth_semantic_sha256` — hash of the decoded content. Identifies
  the *dataset*, and is stable across platforms.

The byte hash is not portable: a Windows checkout (CRLF) of an unchanged
upstream file hashes differently from a POSIX one (LF). The committed Windows
runs in `experiments/005_omnidocbench/results/` record `146690ea…` for the
pinned demo ground truth; a Linux checkout of the *same pinned commit* yields
`a0686ff3…`. The files are byte-identical apart from line endings. Comparing
results across machines is the whole reason to record a dataset identifier,
so both hashes are stored.
