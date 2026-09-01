# Requires GNU make. Every target is a one-liner, so the equivalent command is
# obvious if you'd rather not use make at all.
#
# Everything here is CPU-only. No target requires a GPU.
#
# PYTHON is auto-detected for the platform's venv layout (POSIX puts the
# interpreter in .venv/bin, Windows in .venv/Scripts) and can be overridden:
#
#     make test PYTHON=~/.venvs/doc-extraction-linux312/bin/python
#
ifeq ($(OS),Windows_NT)
    PYTHON ?= .venv/Scripts/python.exe
    VENV_CREATE ?= py -3.12 -m venv --system-site-packages .venv
    # Windows-only packaging snag: antlr4-python3-runtime (a docling
    # dependency) has no wheel and its sdist fails under PEP 517 here.
    # Not needed on POSIX — see docs/setup.md.
    EXTRA_SETUP ?= $(PYTHON) -m pip install "antlr4-python3-runtime==4.9.3" --no-use-pep517
else
    PYTHON ?= .venv/bin/python
    VENV_CREATE ?= python3.12 -m venv .venv
    EXTRA_SETUP ?= true
endif

CONFIG := configs/cpu.yaml

.PHONY: setup models check test lint profile baseline compare inspect report validate manifest docker-build docker-test clean-outputs

setup:
	$(VENV_CREATE)
	PIP_CACHE_DIR=$(CURDIR)/.cache/pip $(PYTHON) -m pip install --upgrade setuptools wheel
	PIP_CACHE_DIR=$(CURDIR)/.cache/pip $(EXTRA_SETUP)
	PIP_CACHE_DIR=$(CURDIR)/.cache/pip $(PYTHON) -m pip install -e ".[docling,tables,dev]"

# Docling refuses to auto-download once DOCLING_ARTIFACTS_PATH is set (which
# config.configure_caches() does), so the models must be fetched explicitly
# before the visual/OCR route can run. ~1.5 GB, once.
models:
	HF_HOME=$(CURDIR)/.cache/huggingface $(PYTHON) -m docling.cli.tools models download -o .cache/docling
	HF_HOME=$(CURDIR)/.cache/huggingface $(PYTHON) -m docling.cli.tools models download easyocr \
		--easyocr-lang en --easyocr-lang vi -o .cache/docling

# One command to answer "can this machine run the project, and what can't it
# do?" — cheap: loads no model, creates no CUDA context, processes no document.
check:
	$(PYTHON) scripts/validate_environment.py

test:
	$(PYTHON) -m pytest -q

# Aggregate per-stage cold/warm timings from runs that already happened.
profile:
	$(PYTHON) scripts/profile_pipeline.py --input outputs/

baseline:
	$(PYTHON) -m doc_extraction run --input data --config $(CONFIG)

# Docling costs ~35 s/page on CPU (~4 s/page on an L4) — target one file
# rather than the corpus.
compare:
	$(PYTHON) -m doc_extraction compare --input "data/FROGSLEAP_Impact_Module_TriAn_B2B_Sample.pdf" \
		--config $(CONFIG) --backends baseline docling

inspect:
	$(PYTHON) -m doc_extraction inspect

report:
	$(PYTHON) scripts/build_failure_report.py --input outputs/

# The full local validation sequence (see README "Local validation").
validate: check test baseline inspect report

manifest:
	$(PYTHON) scripts/build_sample_manifest.py

docker-build:
	docker build -t doc-extraction:cpu .

docker-test:
	docker run --rm doc-extraction:cpu

clean-outputs:
	rm -rf outputs/* && touch outputs/.gitkeep
