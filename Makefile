# Requires GNU make (not preinstalled on plain Windows — use WSL, git-bash
# with make installed, or run the .venv/Scripts/python.exe command in each
# target directly; every target is a one-liner so the equivalent is obvious).
#
# Everything here is CPU-only. No target requires a GPU.

PYTHON := .venv/Scripts/python.exe
CONFIG := configs/cpu.yaml

.PHONY: setup test baseline compare inspect report validate manifest clean-outputs

setup:
	py -3.12 -m venv --system-site-packages .venv
	PIP_CACHE_DIR=$(CURDIR)/.cache/pip $(PYTHON) -m pip install --upgrade setuptools wheel
	PIP_CACHE_DIR=$(CURDIR)/.cache/pip $(PYTHON) -m pip install "antlr4-python3-runtime==4.9.3" --no-use-pep517
	PIP_CACHE_DIR=$(CURDIR)/.cache/pip $(PYTHON) -m pip install -e ".[docling,tables,dev]"

test:
	$(PYTHON) -m pytest -q

baseline:
	$(PYTHON) -m doc_extraction run --input data --config $(CONFIG)

# Docling costs ~35 s/page on CPU — target one file rather than the corpus.
compare:
	$(PYTHON) -m doc_extraction compare --input "data/FROGSLEAP_Impact_Module_TriAn_B2B_Sample.pdf" \
		--config $(CONFIG) --backends baseline docling

inspect:
	$(PYTHON) -m doc_extraction inspect

report:
	$(PYTHON) scripts/build_failure_report.py --input outputs/

# The full local validation sequence (see README "Local validation").
validate: test baseline inspect report

manifest:
	$(PYTHON) scripts/build_sample_manifest.py

clean-outputs:
	rm -rf outputs/* && touch outputs/.gitkeep
