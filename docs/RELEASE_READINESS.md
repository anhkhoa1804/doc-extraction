# Release readiness — pre-push / GPU-host pre-flight audit

Audit date: 2026-08-24. Scope: is this repository safe to push to GitHub
and ready to clone onto a Linux A30-class GPU host?

## Verdict

```
RELEASE STATUS:  BLOCKED for a PUBLIC push
                 READY for a PRIVATE push / internal host
```

One blocking item, and it is not a code defect: **real private document
filenames are present in tracked files and in existing git history.** No
document *content* is exposed anywhere — the leak is filenames and the
metadata they imply (counterparty names, document types). Everything else
passed.

---

## Checklist

| # | Item | Status | Notes |
|---|---|---|---|
| 1 | Tests pass | **PASS** | 213 passed (was 209; +4 this audit) |
| 2 | Source tree clean | **PASS** | `compileall` OK; `git diff --check` clean |
| 3 | No private data tracked | **BLOCKED** | See below. 2 fixed here, 18 files remain + git history |
| 4 | No secrets | **PASS** | No keys/tokens/passwords/credential files. Apparent "internal IPs" are Windows build numbers (`10.0.26200`) and float coordinates |
| 5 | No model weights | **PASS** | No `.safetensors/.pth/.onnx/.bin` tracked; `.cache/`, `.venv-*` ignored |
| 6 | Linux-compatible | **PASS** | No Windows abs paths in `src/`, no `shell=True`, no `os.system`, no `.bat/.ps1`; venv interpreter path branches on `os.name` |
| 7 | GPU diagnostics | **PASS** | `cli env` / `--require-gpu` / `--json`; verified on laptop |
| 8 | CUDA/PyTorch instructions | **PASS** | Explicit CUDA-wheel install + post-install verification in `gpu_host.md` |
| 9 | Cache paths | **PASS** | `configure_caches()` sets `HF_HOME`, `HUGGINGFACE_HUB_CACHE`, `DOCLING_ARTIFACTS_PATH`, `PIP_CACHE_DIR` via `setdefault` — operator env always wins; no `D:\` or `/kaggle/` in `src/` |
| 10 | Backend matrix | **PASS** | See below — stubs are labelled as stubs |
| 11 | License audit | **WARNING** | `docs/model_licenses.md`; two AGPL items need legal review |
| 12 | Security audit | **PASS** | No egress in `src/`; no external LLM APIs; logs carry no document text |
| 13 | Failure semantics | **WARNING** | Loud and non-silent, but GPU OOM is untyped and untested on GPU |
| 14 | Golden commands | **PASS** | `gpu_host.md` §5, env-var parameterised |
| 15 | OmniDocBench integrity | **PASS** | Evaluator commit pinned; subset GT wired; TEDS timeout durable + post-run detection |
| 16 | PAM-safe | **PASS** | No credentials/hosts/IPs; runbook defers to the org's PAM flow |
| 17 | A30 next steps documented | **PASS** | `gpu_host.md`, `production_architecture.md`, `research-roadmap.md` |

---

## BLOCKED — private filenames in tracked files and history

**No document content is exposed.** Experiment `results.json` files were
checked directly and contain statistics only (`total_text_chars`,
`text_similarity`), never extracted text. The exposure is **filenames**,
which on this corpus still name a real third-party company, a business
licence, pricing and partnership documents.

### Fixed during this audit

| File | Action |
|---|---|
| `data/manifest.json` | **Untracked** (`git rm --cached`) and `.gitignore` whitelist removed. It listed all 12 private filenames with hashes in machine-readable form. File preserved on disk. |
| `data/README.md` | **Redacted.** It named files *and* identified which one contains national ID numbers, dates of birth and home addresses. All policy and corpus statistics kept; filenames and the PII pointer removed. |

### Still present — requires your decision

**18 tracked files, 64 occurrences**, all filenames only:

- `Makefile` — a real private filename inside a runnable `compare` command
- `docs/output-format.md` — real filename in an example JSON payload
- `src/doc_extraction/ingest/text_quality.py` — code comment
- `tests/fixtures.py`, `tests/test_pdf_routing.py`, `tests/test_text_quality.py` — comments
- `experiments/00{0,1,2,3,4}/` — observation logs, READMEs and `results.json`
  (`input_file` fields)

I did not mass-redact these, for two reasons. First, several are historical
research records where the filename is part of the evidence trail, and
choosing a redaction scheme is a judgement call that is yours. Second, and
decisive:

> **Redaction alone does not fix this.** These names are already in commit
> history (at least since `4221e4a`). Rewriting the working tree does not
> remove them from earlier commits, so a public push still exposes them.

### The three real options

1. **Push to a private GitHub repo** — pragmatic, no history surgery, and
   sufficient if the repo is internal anyway. **Recommended.**
2. **Rewrite history** with `git-filter-repo` before pushing publicly, then
   redact the working tree. Destructive; invalidates existing clones.
3. **Fresh repo with squashed history**, redacted first. Loses the commit
   narrative, which has real value in this project.

I have not performed any history rewrite — that is destructive and yours to
authorise.

---

## WARNING — licences (`docs/model_licenses.md`)

Two items marked **LEGAL REVIEW REQUIRED**:

- **`pymupdf` is AGPL-3.0 and is a *core, non-optional* dependency.** More
  binding than any model licence here, because it cannot be disabled by
  config. This is the single most restrictive licence in the project.
- **MinerU2.5 weights are AGPL-3.0** (its code is Apache-2.0-based — the
  split matters). Avoidable: PaddleOCR-VL is Apache-2.0 and dots.ocr is
  MIT, both comparably strong. The A30 plan benchmarks those first
  precisely so this review may never be needed.

No legal conclusions are drawn in this repository.

---

## WARNING — failure semantics

Verified non-silent: per-file failures print `FAILED: <type>: <msg>` to
stderr and set exit code 1; failed benchmark pages write **no** prediction
file and are recorded in `runtime.json` `failures[]`; the PDF page-fallback
path records the exception in page `notes` and logs a failure event rather
than emitting an empty page.

Gaps, honestly stated:

- **GPU OOM is not a distinct exception type or exit code.** It would
  surface as a caught `OutOfMemoryError` with exit 1 — loud, but not
  distinguishable from other failures programmatically.
  **UNKNOWN — VERIFY ON GPU HOST** (never run on a GPU).
- A crashed benchmark page produces no prediction file, which the evaluator
  then scores as an empty prediction. Reported in `failures[]`, but it does
  depress metrics rather than being excluded. Every run to date has 0
  failures, so this has not yet mattered.

---

## Backend status matrix

| Backend | Implemented | CPU | GPU | Tested | Production-ready |
|---|---|---|---|---|---|
| Docling (layout/OCR/tables) | Yes | Yes | Wired, **never measured** | Yes (CPU) | Candidate |
| Table Transformer | Yes | Yes | Wired, **never measured** | Yes (CPU) | Candidate |
| PyMuPDF native tables | Yes | Yes | n/a | Yes | Candidate (AGPL) |
| MinerU `MinerUVLTableBackend` | Yes (table candidates only) | Yes (measured) | **UNKNOWN — VERIFY ON GPU HOST** | Adapter unit-tested; model measured on 5 tables | No — AGPL + unmeasured on GPU |
| MinerU `MinerUBackend` (whole-doc) | **Stub** | — | — | Raises clearly | No |
| PaddleOCR | **Stub** | — | — | Raises clearly | No |
| VLM | **Stub** | — | — | Raises clearly | No |
| Formula | **Not present** | — | — | — | No — largest untouched gap (`display_formula` ≈ 0.995) |

---

## Fixed during this audit (beyond the data items)

**A real defect in the GPU benchmark path.** There was no config that could
correctly run OmniDocBench on a GPU:

- `configs/omnidocbench.yaml` — correct OCR (`en`+`ch_sim`), but `device: cpu`
  → would have **silently run on CPU** on the A30
- `configs/gpu.yaml` — `device: cuda`, but `ocr_languages: [en, vi]`
  → a **measurement error**, not just a slowdown: every CPU baseline in this
  repo used `en`+`ch_sim`, so results would not be comparable, and Chinese
  OCR degrades badly without `ch_sim` (0.9601 vs 0.3893 measured)

Added **`configs/omnidocbench-gpu.yaml`** (= `omnidocbench.yaml` with
`device: cuda`, nothing else changed), corrected `docs/gpu_host.md` §5 to
use it, and added two tests: one asserting the cuda+`ch_sim` pairing, one
asserting the CPU/GPU pair differ **only** by `device` so they cannot
silently drift apart.

---

## What will definitely work on the company host

- `pytest -q` (213), `compileall`, CLI, config loading, `cli env`
- Cache redirection to a shared volume
- OmniDocBench evaluator setup (pinned commit, isolated venv, Linux paths
  handled)
- The existing pipeline on **CPU**

## GPU-host-only — must be verified there

Everything below is **UNKNOWN — VERIFY ON GPU HOST**:

- Any CUDA execution at all. `configs/gpu.yaml` and
  `configs/omnidocbench-gpu.yaml` are wired but have **never been run on a
  GPU**.
- All throughput, latency, VRAM and batch-size figures.
- MinerU2.5 / PaddleOCR-VL / dots.ocr GPU behaviour.
- GPU OOM handling.
- **PaddleOCR-VL Vietnamese support.** Its card claims 109 languages;
  official PaddleOCR documentation is reported to list Vietnamese among
  them, but this project has **not** verified it from the primary language
  list, and the target corpus is Vietnamese/English. Smoke-test it directly.
