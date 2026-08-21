# Running on Kaggle (T4 GPU)

This project is CPU-only and validated on a small local corpus (see
[experimentation.md](experimentation.md)). Kaggle is used for one specific
thing: running the **public** [OmniDocBench](https://github.com/opendatalab/OmniDocBench)
benchmark ([experiments/005_omnidocbench](../experiments/005_omnidocbench/))
at full scale, on a machine with more CPU time (and optionally a GPU) than
the dev machine has.

This repo's own `data/` (local/private sample documents — see
[data/README.md](../data/README.md)) is gitignored and **never** goes to
Kaggle. Only `experiments/005_omnidocbench/` and the public OmniDocBench
dataset are involved in the Kaggle workflow below.

## Architecture

```
GitHub (this repo)  -->  Kaggle Notebook  -->  git clone  -->  attach/download
                                                                OmniDocBench
                                                                     |
                                                                     v
                                                     T4 GPU accelerator (optional)
                                                                     |
                                                                     v
                                              experiments/005_omnidocbench/run.py
                                                                     |
                                                                     v
                                                     metrics saved to /kaggle/working
```

## Step 1 — GitHub

Push this repo to a GitHub remote you control. No private data leaves your
machine: `data/*` is gitignored (only `data/README.md` and
`data/manifest.json` are tracked — see the root [README](../README.md)
"Data" section), and `.external/OmniDocBench/` / `.venv-omnidoc/` are also
gitignored.

```bash
git push -u origin master
```

## Step 2 — Create the Kaggle notebook

1. On [kaggle.com](https://www.kaggle.com), create a new Notebook.
2. Keep it **private** unless you intend to share it.
3. In the notebook settings panel (Settings on the right-hand side; labeled
   "Accelerator" in the current Kaggle UI — the exact wording has changed
   before, so look for the accelerator/GPU selector if this differs):
   set **Accelerator** to **GPU T4 x2** (or **GPU T4 x1**, whichever is
   offered — either gives you a T4).
4. Turn on internet access for the notebook (needed to `git clone` and
   `pip install`) — this is usually a separate toggle in the same settings
   panel.

## Step 3 — Clone the repo

```bash
git clone https://github.com/<YOUR_USERNAME>/doc-extraction.git
cd doc-extraction
```

Replace `<YOUR_USERNAME>` with your actual GitHub username/org — there is
no fixed URL for this step.

## Step 4 — Install the project

```bash
pip install -e ".[docling,tables]" -q
```

This is the project's own install mechanism (see
[setup.md](setup.md) — the legacy-build workaround documented there for
`antlr4-python3-runtime` is a Windows-specific snag and does not apply on
Kaggle's Linux image).

The OmniDocBench evaluator is a **separate** project with its own
environment needs (Python `>=3.10,<3.12`) — see
[experiments/005_omnidocbench/README.md](../experiments/005_omnidocbench/README.md#setup)
for the full rationale. On Kaggle's default Python (currently 3.10/3.11),
install it directly, pinned to the same commit this repo's adapter targets:

```bash
git clone https://github.com/opendatalab/OmniDocBench.git .external/OmniDocBench
cd .external/OmniDocBench && git checkout 193627ae9e97d89188468ed1ee3b7a856ff76044 && cd ../..
pip install -e .external/OmniDocBench -q
```

If the attached Kaggle image's default Python is 3.12+, create an isolated
venv for the evaluator instead (same reasoning as the dev machine, which
needed this on Windows) and pass `--omnidoc-python .venv-omnidoc/bin/python`
to `run.py` in Step 6.

## Step 5 — Dataset

**Option A (recommended): attach as a Kaggle Dataset.** Upload
`OmniDocBench.json` + `images/` (from
https://huggingface.co/datasets/opendatalab/OmniDocBench) as a Kaggle
Dataset, then attach it to the notebook via "Add Input". It appears at:

```
/kaggle/input/<dataset-name>/
```

**Option B: use the small official demo set**, bundled with the evaluator
clone from Step 4 — no separate download, but only 18 pages (useful for the
smoke test, not the full benchmark):

```
.external/OmniDocBench/demo_data/omnidocbench_demo/
```

Either option is public OmniDocBench data. Never attach this repo's own
`data/` as a Kaggle input.

## Step 6 — Run the experiment

Using the actual current CLI (`experiments/005_omnidocbench/run.py`):

```bash
# Smoke test first — a small, deterministic subset.
python experiments/005_omnidocbench/run.py \
    --dataset /kaggle/input/<dataset-name> \
    --backend baseline \
    --output /kaggle/working/results/baseline_smoke \
    --subset 20 \
    --match-workers 2

# Full run (omit --subset).
python experiments/005_omnidocbench/run.py \
    --dataset /kaggle/input/<dataset-name> \
    --backend baseline \
    --output /kaggle/working/results/baseline \
    --match-workers 4
```

See [experiments/005_omnidocbench/kaggle/run_full_benchmark.ipynb](../experiments/005_omnidocbench/kaggle/run_full_benchmark.ipynb)
for the same commands wired into a runnable 10-step notebook (check Python,
check GPU, clone, install, locate dataset, print dataset path, smoke test,
full run, print metrics, save results).

## T4-specific expectations

- **The T4 is good for GPU inference, not for training a large model from
  scratch.** Nothing in this project trains a model — this workflow is
  evaluation-only.
- **The baseline extraction pipeline is CPU-oriented today.**
  `configs/cpu.yaml` (`device: cpu`) is what `run.py` uses by default, and
  neither the `baseline` nor `docling` backend currently requests CUDA —
  see `configs/gpu.yaml`'s own header, which documents that GPU support is
  unvalidated, not assumed working. Attaching a T4 does not, by itself,
  make an existing run faster.
- **Docling may not benefit from GPU in every stage.** Its layout/OCR
  models can use CUDA if configured to, but table structure recognition
  and other stages may stay CPU-bound regardless — do not assume a uniform
  speedup without measuring.
- **A future VLM backend should explicitly request and use CUDA** — the
  `vlm` backend is currently an unimplemented stub (see
  [backends.md](backends.md)); when implemented, it should set
  `device: cuda` and verify `torch.cuda.is_available()` rather than relying
  on the accelerator being attached.
- **Large model downloads dominate startup time**, not GPU compute — the
  first Docling run pulls ~1.5 GB of models (see
  [setup.md](setup.md#prefetching-models-optional)). Cache them under
  `/kaggle/working` (not `/kaggle/input`, which is read-only) so a session
  restart doesn't re-download:

  ```python
  import os
  os.environ.setdefault("HF_HOME", "/kaggle/working/.cache/huggingface")
  os.environ.setdefault("DOCLING_ARTIFACTS_PATH", "/kaggle/working/.cache/docling")
  ```
- **Outputs go to `/kaggle/working`**, never `/kaggle/input` (read-only,
  reserved for attached datasets).
- Do not claim a specific model "fits" or "runs well" on a T4 unless it has
  actually been tested and documented — the caveats above are known
  constraints, not a benchmark result.

## Command reference

```bash
# 1. GitHub
git push -u origin master

# 2-3. Kaggle notebook: Settings > Accelerator > GPU T4, then:
git clone https://github.com/<YOUR_USERNAME>/doc-extraction.git
cd doc-extraction

# 4. Install
pip install -e ".[docling,tables]" -q
git clone https://github.com/opendatalab/OmniDocBench.git .external/OmniDocBench
cd .external/OmniDocBench && git checkout 193627ae9e97d89188468ed1ee3b7a856ff76044 && cd ../..
pip install -e .external/OmniDocBench -q

# 5. Dataset — attach via Kaggle "Add Input", then:
DATASET_PATH=/kaggle/input/<dataset-name>

# 6. Run
python experiments/005_omnidocbench/run.py --dataset $DATASET_PATH --backend baseline \
    --output /kaggle/working/results/baseline_smoke --subset 20 --match-workers 2
python experiments/005_omnidocbench/run.py --dataset $DATASET_PATH --backend baseline \
    --output /kaggle/working/results/baseline --match-workers 4
python experiments/005_omnidocbench/run.py --dataset $DATASET_PATH --backend docling \
    --output /kaggle/working/results/docling --match-workers 4
```
