# CPU-only reproducible environment for doc-extraction.
#
# Scope: this image reproduces the *validated CPU* environment — the one the
# repository's local validation sequence uses. It deliberately does NOT
# contain a GPU/CUDA stack: torch is installed from PyTorch's CPU index, which
# keeps the image ~4 GB instead of ~9 GB. See docs/reproducible-environment.md
# for the GPU story.
#
# What is NOT baked in, by policy (see .dockerignore):
#   * data/            private enterprise documents
#   * model weights    ~1.5 GB of Docling/EasyOCR/Table-Transformer artifacts
#   * benchmark data   OmniDocBench dataset and .external/ evaluator clone
#   * outputs/         run artifacts
#   * credentials
# All of those are mounted at run time instead. A container image is copied
# and shared; private documents and multi-GB weights must not travel with it.

FROM python:3.12-slim-bookworm

# libgl1/libglib2.0-0 are needed by opencv, pulled in transitively by easyocr.
# --no-install-recommends keeps the layer minimal; the apt lists are removed
# in the same layer so they never reach the image.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    # Model caches live on a mounted volume, never in the image. Matches the
    # variables config.configure_caches() sets, so an operator-provided mount
    # wins over the project-local default.
    HF_HOME=/cache/huggingface \
    HUGGINGFACE_HUB_CACHE=/cache/huggingface/hub \
    DOCLING_ARTIFACTS_PATH=/cache/docling \
    # All four must be set. configure_caches() creates a project-local
    # directory for any it finds unset, which fails under a non-root user
    # because /app is not writable by them.
    PIP_CACHE_DIR=/cache/pip

# Install torch from the CPU index FIRST, as its own layer: it is by far the
# largest dependency and the least likely to change, so it stays cached across
# rebuilds when only project source changes.
RUN pip install --index-url https://download.pytorch.org/whl/cpu \
        "torch==2.13.0" "torchvision==0.28.0"

# Dependency metadata only, so this layer is not invalidated by source edits.
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN pip install -e ".[docling,tables,dev]"

COPY tests/ ./tests/
COPY configs/ ./configs/
COPY scripts/ ./scripts/
COPY Makefile ./
# The OmniDocBench adapter lives under experiments/ rather than in the
# installed package, and tests/test_omnidocbench.py loads run.py and
# evaluate.py by path — so the image needs the experiment *code*. The
# dataset, predictions, logs and the evaluator clone stay excluded by
# .dockerignore; only source and small committed result metadata are copied.
COPY experiments/ ./experiments/

# Import check at build time: fail the build, not the first run, if the
# package cannot be imported in this environment.
RUN python -c "import doc_extraction; print('doc_extraction', doc_extraction.__version__)"

# Non-root by default: nothing here needs root, and a container that writes
# to a mounted output directory as root leaves root-owned files on the host.
RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /cache /outputs \
    && chown -R appuser:appuser /app /cache /outputs
USER appuser

CMD ["python", "-m", "pytest", "-q"]
