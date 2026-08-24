# GPU host runbook (A30-class)

Everything needed to bring this project up on a company GPU host and run
the benchmarks that the development laptop cannot. **Nothing in this
document has been executed on a GPU** — the laptop is a CPU-only,
4 GiB-VRAM, CUDA-11.2-era machine and is explicitly not the compute
target. Values marked *TO MEASURE* are placeholders to fill in on the
host; none of them are estimated or fabricated here.

**PAM is out of scope.** No credentials, hostnames, or connection details
belong in this repository. Get to a shell on the host through the
organisation's normal PAM flow, then start at step 1.

---

## 0. Target assumptions

| | |
|---|---|
| Hardware | NVIDIA A30 (24 GiB HBM2) or better |
| OS | Linux |
| Driver | Recent enough for the CUDA runtime of the installed torch wheel (cu121/cu124 wheels need a ≥ 530 driver) |
| Python | 3.12 (3.10–3.12 is the range every candidate supports; MinerU caps at 3.12 on Windows, Linux allows 3.13) |
| Isolation | venv or Docker |
| Network | Access to HuggingFace (or an internal mirror) for weights |

24 GiB comfortably fits every candidate below; none of them is close to
the limit. The binding constraint on an A30 will be **throughput and
batch size, not capacity.**

---

## 1. Verify the host before installing anything

```bash
nvidia-smi
```

Then, once the project is installed (step 2), the project's own diagnostic:

```bash
python -m doc_extraction.cli env
```

It reports Python/platform, torch version **and whether torch is a CUDA or
CPU-only build**, driver CUDA version, every visible GPU with VRAM,
which optional backends import, and where the model caches point. It also
interprets the result rather than only listing facts — the failure it
exists to catch is a config saying `device: cuda` on a CPU-only torch
build, which does not error, it just runs ~30× slower on CPU.

For scripted bring-up gating:

```bash
python -m doc_extraction.cli env --require-gpu
```

Exits non-zero unless torch can actually use a GPU. Use this in CI or as
the first line of a benchmark script so a mis-provisioned host fails loudly
instead of silently producing CPU timings.

`--json` emits the same report machine-readably; `--min-vram-gib` sets the
bar used to flag an inadequate card (default 20; an A30 is 24).

**Expected on the laptop (for contrast — this is what a bad host looks
like):** `GPU usable: NO`, `torch CUDA build: CPU-only`, driver CUDA 11.2,
RTX 3050 4096 MiB flagged as below the VLM-tier bar.

---

## 2. Install

```bash
git clone <this repo> && cd doc-extraction
python3.12 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip
```

Install a **CUDA** torch build explicitly — do not let a transitive
dependency pull the CPU wheel:

```bash
pip install torch --index-url https://download.pytorch.org/whl/cu121
python -c "import torch; print(torch.__version__, torch.version.cuda, torch.cuda.is_available())"
```

That must print a non-`None` CUDA version and `True` before continuing.

Then the project and its backends:

```bash
pip install -e ".[docling,tables]"
python -m doc_extraction.cli env          # re-check: GPU usable should now be YES
```

### Model caches — set these before downloading weights

On a shared host, unset caches mean every user re-downloads multi-GB
weights into their home directory.

```bash
export HF_HOME=/srv/models/hf                # or your shared volume
export HUGGINGFACE_HUB_CACHE=$HF_HOME/hub
export TORCH_HOME=/srv/models/torch
```

`doc_extraction.cli env` reports these, and warns when none is set.

### Candidate parsers (install per experiment, not all at once)

```bash
# PaddleOCR-VL (Apache-2.0) — try FIRST, see docs/model_licenses.md
pip install paddleocr

# dots.ocr (MIT)
pip install transformers  # + vllm for throughput

# MinerU2.5 (AGPL-3.0 weights — legal review required before use)
pip install "mineru-vl-utils[transformers]"
```

The **licence-led ordering is deliberate**: PaddleOCR-VL (Apache-2.0) and
dots.ocr (MIT) are permissively licensed; MinerU2.5's weights are AGPL-3.0.
If a permissive model matches MinerU2.5 on our residual failures, the AGPL
question never has to be answered. See `docs/model_licenses.md`.

---

## 3. Smoke tests (minutes, not hours)

Run in order; stop at the first failure.

```bash
# 3a. Unit suite — must be green before anything else
pytest -q

# 3b. Environment gate
python -m doc_extraction.cli env --require-gpu

# 3c. Existing pipeline, GPU profile, one page
python -m doc_extraction.cli run --input <one-pdf-or-image> --config configs/gpu.yaml
```

`configs/gpu.yaml` already plumbs `device: cuda` through every stage
(Docling layout/TableFormer/EasyOCR via `AcceleratorOptions`, and Table
Transformer's models *and* their input tensors). Its header states plainly
that no timing from it has ever been recorded — step 5 is where that
changes.

### 3d. Per-model bring-up

For each candidate, confirm it loads, uses the GPU, and produces output on
a single page before benchmarking:

```bash
nvidia-smi --query-gpu=memory.used --format=csv -l 1 &   # watch VRAM
# ... run one page through the candidate ...
kill %1
```

Record: loads (y/n), peak VRAM, cold start, single-page latency.

---

## 4. Dataset

OmniDocBench is already integrated. On the host:

```bash
# dataset (public benchmark; ~1651 pages)
huggingface-cli download opendatalab/OmniDocBench --repo-type dataset \
  --local-dir .external/OmniDocBench-data

# evaluator (pinned commit — do not float this)
git clone https://github.com/opendatalab/OmniDocBench .external/OmniDocBench
git -C .external/OmniDocBench checkout 193627ae9e97d89188468ed1ee3b7a856ff76044
python3.11 -m venv .venv-omnidoc && .venv-omnidoc/bin/pip install -r .external/OmniDocBench/requirements.txt
```

The evaluator runs in its own venv by project convention; `evaluate.py`
finds it automatically.

**Evaluator hygiene is already hardened — do not undo it.** The TEDS
timeout is written directly into the generated evaluator config
(`DEFAULT_TEDS_TIMEOUT_SECONDS`, 900s) rather than left to an env var, and
`evaluate.py` scans evaluator stdout for `[TEDS-timeout]` lines, writing a
`TEDS_TIMEOUTS.txt` marker and a loud warning into the result directory if
any occur. This exists because wall-clock timeouts silently scored 0.0 —
indistinguishable from real extraction failures — and contaminated two
100-page runs before being traced (see `observations.md` §18).
**Any run whose result dir contains `TEDS_TIMEOUTS.txt` is invalid for
table metrics.**

---

## 5. Benchmark commands

Escalate in this order. Do not skip to the full set.

```bash
# 20-page diagnostic subset (fast iteration)
PYTHONUTF8=1 python experiments/005_omnidocbench/run.py \
  --dataset .external/OmniDocBench-data \
  --backend baseline --config configs/gpu.yaml \
  --output experiments/005_omnidocbench/results/a30_baseline_20 \
  --subset 20 --seed 0 --match-workers 4

# 100-page validation
... --subset 100 --seed 0 --output .../a30_baseline_100

# full 1651 pages — only after 100 is clean
... (omit --subset) --output .../a30_baseline_full
```

Subsets are deterministic for a given `--seed`, and nested: the 100-page
set contains the 20-page set. Results land in `<output>/` as
`metrics.json`, `report.md`, `runtime.json`, `run_metadata.json`, and
`predictions/`.

**Never compare across different subset sizes or timeout regimes**, and
never compare our subset scores against published full-benchmark numbers —
that comparison is invalid and this project does not make it.

---

## 6. What to measure (fill these in on the host)

### Feasibility

| Model | Loads | Peak VRAM | CUDA OK | 1 page OK |
|---|---|---|---|---|
| Current pipeline (`configs/gpu.yaml`) | *TO MEASURE* | *TO MEASURE* | | |
| PaddleOCR-VL | | | | |
| dots.ocr | | | | |
| MinerU2.5 | | | | |

### Performance

| Model | Cold start | Warm latency/page | Pages/min | Best batch size | GPU util % |
|---|---|---|---|---|---|
| … | *TO MEASURE* | | | | |

### Quality (same subset, same evaluator, same normalisation)

| Pipeline | text | table TEDS | TEDS-S | reading order | formula | runtime |
|---|---|---|---|---|---|---|
| A: current baseline (GPU) | *TO MEASURE* | | | | | |
| B: Docling + TT + composition | | | | | | |
| C: SOTA parser alone | | | | | | |
| D: SOTA parser + our composition | | | | | | |
| E: multi-backend | | | | | | |

Known reference points from CPU measurement, for sanity-checking only —
**not** targets: current pipeline `table TEDS.all` 0.4514 on the 100-page
subset (timeout-corrected), ~70 s/page CPU.

### Blocking verification item

**Does PaddleOCR-VL actually support Vietnamese?** Its card and abstract
claim 109 languages without naming Vietnamese, and no primary-source list
was found. This project's real target corpus is Vietnamese/English, so
this must be tested directly on the host with Vietnamese documents before
PaddleOCR-VL is adopted. If it does not, dots.ocr (MIT, 100 languages
demonstrated) is the permissive fallback.

---

## 7. Serving shape

The existing runner already loads models **once per process** and reuses
them (`_COMPONENT_BACKEND_CACHE` in `cli.py`), which is the property that
matters — the earlier per-page reload was a measured, fixed bug. For
higher throughput on the host:

- Prefer **vLLM** for the VLM candidates where supported (both PaddleOCR-VL
  and dots.ocr document a vLLM path; MinerU documents vLLM/SGLang). The
  transformers path used on the laptop is correctness-oriented, not
  throughput-oriented.
- Batch at the **page** level.
- One worker per GPU to start. Only add workers after measuring GPU
  utilisation — if util is already high, more workers add contention, not
  throughput.

`_COMPONENT_BACKEND_CACHE`'s docstring notes the backends are safe to
reuse only because the runner is sequential; **a parallel runner must
re-check that assumption before sharing them across threads.**

---

## 8. Environment diagnostics to capture with every result

Already recorded automatically into each result directory
(`run_metadata.json`, `runtime_environment.json`): evaluator commit,
ground-truth SHA-256, model versions, device, config snapshot, subset size
and seed. Add the `env` report alongside it:

```bash
python -m doc_extraction.cli env --json > <output>/environment.json
```

so a result can always be tied to the exact host that produced it.
