# Release readiness — pre-push / GPU-host pre-flight audit

Last audit: 2026-08-26 (hardening pass). Scope: is this repository safe to
push and ready to clone onto a Linux A30-class GPU host?

## Verdict

```
RELEASE STATUS:  PASS  — for a PRIVATE GitHub repository
                 BLOCKED — for a PUBLIC repository (history rewrite required)
```

The intended state is a **private** repository for internal R&D. Under that
decision there are **no blocking items**. The public-repo blocker is
recorded below and is a deliberate, documented decision — not an oversight.

---

## Status table

| Area | Status | Evidence / Action |
|---|---|---|
| Git safety | **PASS** | Only intended source/docs/tests tracked; notebook excluded; no weights, venvs, caches, datasets or predictions |
| Current-tree privacy | **PASS** | 18 files pseudonymised this pass; scan for private identifiers returns **zero hits** across all tracked files |
| Historical privacy | **WARNING** (private repo) / **BLOCKED** (public repo) | All **18/18** commits contain the private company name. Decision: keep repo private, do **not** rewrite history. See below |
| Linux portability | **PASS** | No Windows absolute paths in `src/`; no `shell=True`/`os.system`/`.bat`/`.ps1`; venv interpreter path branches on `os.name`; `pathlib` throughout; subprocess uses argument arrays |
| GPU diagnostics | **PASS** | `cli env` / `--require-gpu` / `--json` / `--min-vram-gib`; reports GPU name, VRAM, driver CUDA, torch CUDA build, availability; verified on laptop |
| CUDA/PyTorch | **PASS** (fixed this pass) | Hardcoded `cu121` removed. Runbook now reads the driver first and instructs choosing a matching wheel; adds a CUDA-sensitive-dependency section on how GPU torch gets silently replaced by the CPU wheel |
| Configs | **PASS** | 5 configs; device/OCR matrix verified; two tests enforce the CPU/GPU benchmark pair differ **only** by `device` |
| Model cache | **PASS** | `configure_caches()` sets `HF_HOME`, `HUGGINGFACE_HUB_CACHE`, `DOCLING_ARTIFACTS_PATH`, `PIP_CACHE_DIR` via `setdefault` (operator env wins); no `C:\`, `D:\` or `/kaggle/` in `src/` |
| Backend matrix | **PASS** | Stubs labelled as stubs; GPU-wired vs GPU-validated distinguished — see below |
| License | **WARNING** | Two AGPL items need company legal review (`pymupdf` core dependency; MinerU2.5 weights). `docs/model_licenses.md` |
| Security | **PASS** | No egress in `src/`; no external LLM/SaaS APIs; only egress is model/package download at setup |
| Logging | **PASS** | `log_event` records metadata only (document id, page, stage, backend, status, runtime, device, output path, warnings, error, metrics). **No document text, OCR output or table content** |
| Failure semantics | **WARNING** | Loud and non-silent; but several states are not first-class — see below |
| OmniDocBench | **PASS** | Evaluator commit pinned; dataset external; subset GT wired; TEDS timeout durable in config + post-run detection; reproducibility checklist added (`gpu_host.md` §9) |
| A30 runbook | **PASS** | Golden path, driver-aware install, dataset setup, benchmark commands, measurement tables, 4-experiment plan |
| Tests | **PASS** | **213 passed**; `compileall` clean; `git diff --check` clean |

---

## Historical privacy — the decision

**Decision: keep the GitHub repository PRIVATE. No history rewrite.**

Measured: **all 18 commits** in the repository's history contain the
private company name (`git rev-list --all` + per-commit `git grep`). The
names first appear in `29c1d26` and `4221e4a`. Rewriting would therefore
touch every commit — effectively equivalent to starting a fresh repository.

No document *content* is in history — the exposure is filenames and the
metadata they imply (counterparty names, document types). Experiment
`results.json` files were checked directly and contain statistics only
(`total_text_chars`, `text_similarity`), never extracted text.

For an internal R&D repository, a private remote is sufficient and
proportionate. **No destructive history rewriting was performed**, per the
standing instruction not to do so without an explicit request.

**If this repository is ever to be made public**, that is a separate,
deliberate action requiring one of:

1. `git-filter-repo` history rewrite, then force-push (invalidates clones);
2. a fresh repository with squashed, redacted history (loses the commit
   narrative, which has real evidentiary value here);
3. re-creating the repo from the current clean tree only.

Do not make the repository public without doing one of these first.

### Current tree — cleaned this pass

18 tracked files were pseudonymised (`Makefile`, `docs/output-format.md`,
`src/doc_extraction/ingest/text_quality.py`, three test files, and the
`experiments/00{0..4}` research logs and `results.json`). Real filenames
map to stable pseudonyms (`sample-business-licence.pdf`,
`sample-pricing.xlsx`, …) so cross-document references still line up and
the evidence trail stays readable.

Two tests previously selected corpus fixtures **by private filename**;
they now select **by property** (which document fails the text-quality
gate). This removes the private-name coupling and is more robust — it keeps
working on a machine whose corpus differs, which the filename version did
not. Verified still meaningful on the real corpus: 9 PDFs, exactly 1
rerouted to OCR, `suspicious_page_ratio = 1.00`.

The 12 private documents remain **on disk and untracked** (`data/*` ignored,
only `data/README.md` tracked; `data/README.md` itself was redacted in the
previous pass — it had named files *and* identified which one contains
national ID numbers, dates of birth and home addresses).

---

## Backend matrix — GPU-wired vs GPU-validated

Terminology used strictly:

- **GPU-wired** — `device` reaches the backend in code; never executed on a GPU
- **GPU-smoke-tested** — ran on a GPU at least once
- **GPU-validated** — benchmarked on a GPU with recorded quality + performance
- **production-ready** — GPU-validated, licence-cleared, failure-tested

| Backend | Implemented | CPU | GPU status | Tested | Production-ready |
|---|---|---|---|---|---|
| Docling (layout/OCR/tables) | Yes | Yes (measured) | **GPU-wired** | Yes (CPU) | No |
| Table Transformer | Yes | Yes (measured) | **GPU-wired** | Yes (CPU) | No |
| PyMuPDF native tables | Yes | Yes | n/a | Yes | No (AGPL review) |
| MinerU `MinerUVLTableBackend` | Yes (table candidates only) | Yes (measured, 5 tables) | **not wired** — see below | Adapter unit-tested | No |
| MinerU `MinerUBackend` (whole-doc) | **Stub** | — | — | Raises clearly | No |
| PaddleOCR / PaddleOCR-VL | **Stub** / not installed | — | — | — | No — **GPU-host candidate** |
| dots.ocr | Not integrated | — | — | — | No — GPU-host candidate |
| VLM | **Stub** | — | — | Raises clearly | No |
| Formula | **Not present** | — | — | — | No — largest untouched gap (`display_formula` ≈ 0.995) |

**Nothing in this repository is GPU-validated.** `configs/gpu.yaml` and
`configs/omnidocbench-gpu.yaml` are GPU-wired only.

### MinerU adapter — Linux transfer check

- No laptop-specific paths, no hardcoded model cache (uses `HF_HOME` via
  the standard HF resolution), no `.exe`, no `shell=True`, no subprocess.
- `device` is a constructor parameter; `float32` on CPU and `bfloat16`
  otherwise — so a GPU host gets bf16 automatically.
- **Honest gap:** `MinerUVLTableBackend` is *not* wired into the pipeline
  or the CLI backend factory. It is a standalone candidate source with an
  adapter and 12 unit tests. Using it on the A30 means constructing it
  explicitly. Deliberate — composition wiring was gated on GPU measurement.
- Unavailable-backend error is explicit and distinguishes "package absent"
  from "whole-document convert() not implemented".

---

## Failure semantics — current behaviour

Verified non-silent, but **not** a first-class taxonomy. Documented rather
than redesigned, per scope.

| State | Current behaviour |
|---|---|
| SUCCESS | exit 0 |
| PARTIAL_SUCCESS | Per-file: failures print to stderr, exit 1. Benchmark: failed page writes **no** prediction file, recorded in `runtime.json` `failures[]`. PDF page-fallback records the exception in page `notes` + logs a failure event |
| INVALID_INPUT | Path/config errors return 1 with a message |
| BACKEND_UNAVAILABLE | `BackendUnavailableError` with install instructions |
| MODEL_UNAVAILABLE | Same path as above |
| GPU_UNAVAILABLE | **`cli env --require-gpu` exits non-zero** — the intended gate |
| GPU_OOM | **Not first-class.** Surfaces as a caught exception, printed with type and message, exit 1. Loud, but not programmatically distinguishable. **UNKNOWN — VERIFY ON GPU HOST** |
| TIMEOUT | TEDS timeouts detected post-run (`TEDS_TIMEOUTS.txt` + stderr warning). No pipeline-level timeout |
| EXTRACTION_ERROR | Caught per file/page, reported, exit 1 |

Not a release blocker: no state is silently converted into an empty
success. The gap is granularity, not correctness.

---

## Fixed in this pass

1. **Current-tree privacy** — 18 files pseudonymised; 2 tests decoupled
   from private filenames; tracked tree now scans clean.
2. **Hardcoded `cu121` removed** — the runbook reads `nvidia-smi` first and
   instructs choosing a wheel matching the host's actual driver. The
   example is explicitly labelled `cuXXX` / "EXAMPLE ONLY". Driver row in
   §0 changed to "Unknown until measured on the host."
3. **CUDA-sensitive dependency warning** — how a later `pip install`
   silently replaces GPU torch with the CPU wheel from PyPI, with
   `--dry-run` check and the rule that `cli env --require-gpu` is the gate
   after *every* install.
4. **Golden path** added at the top of the runbook (6 ordered steps).
5. **Benchmark reproducibility checklist** (`gpu_host.md` §9) — 10 items.
6. **A30 experiment plan** (`gpu_host.md` §10) — Experiments 0–3.

---

## Known warnings (non-blocking)

- **AGPL, legal review required.** `pymupdf` is AGPL-3.0 and is a **core,
  non-optional** dependency — the most binding licence in the project.
  MinerU2.5 *weights* are AGPL-3.0 (its code is Apache-2.0-based).
  Mitigation already planned: benchmark Apache-2.0 (PaddleOCR-VL) and MIT
  (dots.ocr) alternatives first, so the AGPL review may never be needed.
  **No legal determination is made in this repository.**
- **Nothing is GPU-validated.** Every CUDA path is wired and unexecuted.
- **GPU OOM is not first-class.** UNKNOWN — VERIFY ON GPU HOST.
- **PaddleOCR-VL Vietnamese support** is cited from official documentation
  but **not verified in practice by this project**. The target corpus is
  Vietnamese/English — smoke-test before adopting.
- **History contains private filenames** — private repo only, see above.
