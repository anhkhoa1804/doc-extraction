# 005 — OmniDocBench integration

## Question

The previous experiments (000-004) measured this pipeline against its own
12-document corpus, with no external reference point. **How does the
current baseline actually compare against a standard, third-party
benchmark, and where does it fail on document types and languages our own
corpus doesn't cover?**

This experiment integrates the official [OmniDocBench](https://github.com/opendatalab/OmniDocBench)
benchmark, generates predictions with this repo's own backends, and scores
them with the *unmodified* official evaluator. It does not train or tune
anything — the goal stated by the task this phase implements is **"measure
first, don't optimize before we know where the pipeline actually fails."**

## Upstream, pinned exactly

| | |
|---|---|
| Repository | https://github.com/opendatalab/OmniDocBench |
| Pinned commit | `193627ae9e97d89188468ed1ee3b7a856ff76044` (2026-07-27) |
| Package version | `omnidocbench-eval` 1.6.0 (per its own `pyproject.toml`) |
| Dataset version | v1.6 (per the README's own changelog at this commit) |
| License | Apache-2.0 |
| Python required | `>=3.10,<3.12` |

Verified directly from the pinned commit's source (not from a summarized
web page — an earlier fetch of the README via a summarizing tool invented
a materially wrong prediction format; everything below was cross-checked
against the actual files in the clone). Re-verify before trusting this
document if the pin is ever bumped:

```bash
cd .external/OmniDocBench && git log -1 --oneline && git rev-parse HEAD
```

## Why the evaluator is not vendored, and why it needs its own Python

The evaluator is cloned **outside version control**, at
`.external/OmniDocBench/` (gitignored), and run in its own virtualenv,
`.venv-omnidoc/` (also gitignored) — not this project's main `.venv`.

Two independent reasons, both hard constraints, not preferences:

1. **It's a separate project we don't own.** Modifying or redistributing
   its source inside this repo would blur where its Apache-2.0-licensed
   code ends and ours begins, and would drift from upstream silently.
2. **It requires Python `<3.12`.** This project's main environment is
   Python 3.12 (`.venv`). The evaluator's own `pyproject.toml` pins
   `requires-python = ">=3.10,<3.12"` — genuinely incompatible, not just
   untested.

## Setup

```bash
# 1. Clone the evaluator, pinned to the commit above.
git clone https://github.com/opendatalab/OmniDocBench.git .external/OmniDocBench
cd .external/OmniDocBench && git checkout 193627ae9e97d89188468ed1ee3b7a856ff76044 && cd ../..

# 2. A Python 3.10 or 3.11 interpreter. This machine had only 3.12 installed;
#    the `py` launcher can fetch 3.11 on demand:
py install 3.11

# 3. Isolated venv + dependencies.
py -3.11 -m venv .venv-omnidoc
export PIP_CACHE_DIR="$(pwd)/.cache/pip"   # keep the download off the OS drive
.venv-omnidoc/Scripts/python.exe -m pip install --upgrade pip
```

### Windows snag: `lxml==4.9.1` has no Windows wheel

The evaluator pins `lxml==4.9.1` exactly. That version has no prebuilt
Windows wheel and its sdist build needs libxml2/libxslt headers that
aren't present on a stock Windows box — the build fails with `fatal error
C1083: Cannot open include file: 'libxml/xmlversion.h'`. This is the same
class of issue as the `antlr4-python3-runtime` pin in the main project's
own `docs/setup.md` (a Windows-incompatible exact pin in an otherwise-fine
dependency), fixed the same way: install a modern `lxml` (which *does*
ship Windows wheels) instead of fighting the pin, then install everything
else exactly as pinned, then the package itself with `--no-deps` so pip
doesn't re-demand the broken pin:

```bash
.venv-omnidoc/Scripts/python.exe -m pip install lxml   # unpinned — grabs a prebuilt wheel
.venv-omnidoc/Scripts/python.exe -m pip install \
  "apted==1.0.3" "beautifulsoup4==4.11.1" "evaluate==0.4.3" "func-timeout==4.3.5" \
  "Levenshtein==0.25.1" "loguru==0.7.2" "matplotlib==3.7.5" "nltk==3.9.1" \
  "numpy==1.24.4" "pandas==2.0.3" "Pillow==10.4.0" "pylatexenc==2.10" \
  "PyYAML==6.0.2" "scipy==1.10.1" "tabulate==0.9.0" "tqdm==4.67.1"
.venv-omnidoc/Scripts/python.exe -m pip install --no-deps -e .external/OmniDocBench
```

Verify:

```bash
.venv-omnidoc/Scripts/python.exe -c "from src.core.pipeline import run_config_file; print('OK')"
```

### Windows snag: the evaluator crashes on the Chinese dataset content

`UnicodeDecodeError: 'charmap' codec can't decode byte ...` on the very
first run. The evaluator (developed on Linux) opens the ground-truth JSON
with `open(path)` — no explicit encoding — which on Windows defaults to
the system codepage (cp1252 here), and the dataset is genuinely
multilingual (Chinese is one of its five languages). This is a real bug in
unmodified upstream code, confirmed at the pinned commit; not something to
route around by touching their source.

**Fix, without modifying the evaluator:** Python's standard UTF-8 mode
(`PYTHONUTF8=1`, PEP 540) makes `open()`'s default encoding UTF-8
regardless of the platform codepage. `evaluate.py`
(`run_official_evaluator` in `src/doc_extraction/evaluation/omnidocbench.py`)
sets this for the evaluator subprocess automatically — nothing to do
manually when using this repo's own scripts.

## Dataset

Two options, both usable with the same `--dataset <dir>` flag:

**Small, official, bundled with the clone** (used for the runs in this
directory — see below): `.external/OmniDocBench/demo_data/omnidocbench_demo/`
(18 pages, ~9 MB, provided by upstream specifically for validating an
integration like this one). Copied into
`experiments/005_omnidocbench/dataset/demo/` (gitignored) for a stable
local path.

**Full dataset** (1651 pages, not run locally — see "What was and wasn't
run" below): https://huggingface.co/datasets/opendatalab/OmniDocBench
— `OmniDocBench.json` + `images/*.png`. Any directory with that shape
works with `--dataset`; `load_dataset()` doesn't care where it came from.

## IR → OmniDocBench mapping

The adapter (`src/doc_extraction/evaluation/omnidocbench.py`) targets the
**`end2end`** evaluation method (upstream's own recommendation over
`md2md` — it preserves attribute/category information the `md2md` method
discards). Ground truth is OmniDocBench's JSON directly; predictions are
one Markdown file per page, named `<image_stem>.md`.

| Our representation | OmniDocBench representation | Notes |
|---|---|---|
| `Element.type=HEADING` | `#`..`######` Markdown heading | level clamped 1-6 |
| `Element.type=PARAGRAPH`/`TEXT` | plain text block, blank-line separated | matches the evaluator's own paragraph splitter (`content.split('\n\n')`) |
| `Element.type=LIST_ITEM` | `- ` prefixed line | no distinct OmniDocBench category for lists; scored as ordinary text |
| `Element.type=TABLE` + `Table` | `Table.to_markdown()`'s GitHub-style pipe table | the evaluator auto-detects pipe tables and converts them to HTML before TEDS scoring (`md_table_reg` / `convert_markdown_to_html` in the pinned commit) — verified by reading that code, not assumed |
| `Element.type=FORMULA` | `$$...$$` (wrapped only if not already LaTeX-delimited) | see "What's lost", below |
| `Element.type=IMAGE` | `![alt](name)` | not scored by end2end text/table/formula/reading-order metrics |
| `Element.type=CHECKBOX`/`SIGNATURE`/`OTHER` | plain text, if any | no OmniDocBench category maps to these — documented loss, not silently dropped (the element's text still appears, just unlabeled) |
| `Page.reading_order` | Markdown block order | whichever ordering produced the `Document` — our own heuristic, or a whole-document backend's |

Confirmed against a real GT/prediction pair from the pinned commit
(`demo_data/omnidocbench_demo/mds/eastmoney_...pdf_0.md`): headings use a
single `#` regardless of apparent visual hierarchy, tables are raw
`<table>` HTML, images use standard Markdown image syntax. Our
`Table.to_markdown()` pipe-table output is a *different* valid input the
evaluator's own preprocessing already handles — not a guess.

### What's unavoidably lost

- **Span-level annotations** (inline formulas, footnote marks) — our IR
  has no span-level element type; only OmniDocBench's *block*-level
  categories are populated.
- **Per-block attribute tags** — `with_span`, `text_rotate`,
  `table_layout`, etc. exist only on the ground-truth side; we have no
  equivalent to assign on the prediction side, nor does the end2end
  Markdown format carry them.
- **Confidence scores** — `Element.confidence` has no home in Markdown
  text; dropped.
- **Genuine formula recognition** — none of this project's backends run a
  formula-recognition model. `ElementType.FORMULA` is only ever populated
  when a layout model (Docling) *labels* a region as a formula; the text
  inside still comes from general OCR, not LaTeX recognition. Formula
  scores in the reports below should be read as "how did general OCR do on
  formula-labeled regions", not as a real formula-recognition result.

### Coordinate systems (spec requirement — verified, not assumed)

Both systems use a **top-left origin with +y increasing downward**.
Confirmed directly from the OmniDocBench README's own worked example at
the pinned commit: a `poly` with top corners at `y=781` and bottom corners
at `y=806` — y grows downward, exactly matching this project's `BBox`
convention (`schemas/element.py`). The only structural difference is
shape: OmniDocBench stores four corner points (8 numbers, to allow
rotated/skewed regions); our `BBox` is always axis-aligned.

`bbox_to_omnidocbench_poly` / `omnidocbench_poly_to_bbox` convert between
them; round-trip is exact for axis-aligned regions (all of ours) and
degrades a genuinely rotated poly to its axis-aligned bounding box in the
other direction (documented, not silently wrong — our IR has no rotation
field to preserve the skew). Tested with a top-left region, a bottom-right
region, a full-page region, and non-square page dimensions — see
`tests/test_omnidocbench.py`.

These conversions are **not exercised by the end2end text/table/formula/
reading-order metrics used below** — end2end scoring is Markdown-content
based, not geometric. They exist for `inspect_sample.py`'s ground-truth
box overlay and for a possible future layout-detection (COCODet) arm,
which this phase does not run — see "Not done in this phase".

## Matching method

`quick_match` (upstream's own recommendation): segments both sides into
paragraphs, then uses "Adjacency Search Match" truncation/merging so
paragraph-splitting differences between our output and the ground truth
don't get double-penalized. `simple_match` is faster but stricter (no
truncation/merging); `no_split` treats a whole page as one block and
cannot produce attribute-level or reading-order results. All three are
selectable via `--match-method`.

## Architecture: prepare / evaluate / run

```
OmniDocBench dataset
        |
        v
prepare.py   --backend {baseline|docling}    (doc_extraction, .venv, Py 3.12)
        |
        v
predictions/*.md
        |
        v
evaluate.py  --dataset ... --output ...      (subprocess -> .venv-omnidoc, Py 3.11)
        |
        v
metrics.json, run_summary.json, runtime_environment.json
        |
        v
run.py writes report.md
```

`prepare.py` and `evaluate.py` are independently rerunnable: re-scoring
with a different `--match-method` doesn't regenerate predictions;
regenerating predictions with a different backend doesn't require the
evaluator to be set up at all. `run.py` is the thin orchestrator shown in
the top-level examples; `--skip-prepare` / `--skip-evaluate` expose the
same split from the single entrypoint.

`inspect_sample.py` is separate and optional: a static HTML page per
sample (ground-truth boxes overlaid on the page image, next to our
predicted Markdown) for spot-checking. It does not reimplement any part of
the evaluator's matching.

## What was and wasn't run

**Run**: the full 18-page official demo set
(`demo_data/omnidocbench_demo/`), both `baseline` and `docling` backends,
`quick_match`, CDM and BLEU/METEOR **excluded**. Results:
`results/baseline/`, `results/docling/` (each with `report.md`,
`metrics.json`, `runtime.json`, `run_metadata.json` committed;
`predictions/` and the evaluator's raw per-sample debug dumps are not —
see `.gitignore`).

**Not run: the full 1651-page dataset.** This pipeline's visual route
(Docling layout+OCR, ~20-50s/page on this CPU — see
`experiments/000_smoke/observations.md`) is what every OmniDocBench sample
takes, since every sample is a standalone image with no native text layer
to route around. At an observed ~50s/page, 1651 pages is **on the order of
23 hours per backend** on this machine — not a "run it and wait" amount of
local CPU time, and the task this phase implements is explicit: *"If not
[reasonably processable locally], do not fake completion... document
exactly what remains to run on Kaggle."* Prediction generation and
evaluator integration are validated end-to-end on real data; scaling to
the full dataset is a matter of time and (optionally) a GPU-accelerated
Docling backend, not unresolved integration risk. See
`kaggle/run_full_benchmark.ipynb`.

**Not done in this phase, deliberately**: layout-detection (COCODet) and
single-module (isolated formula/table-recognition) evaluation — both are
separate evaluator task types with their own prediction formats distinct
from `end2end`. The coordinate-conversion functions this phase built are
ready for a future layout-detection arm; wiring the rest is future work,
not started here per the "measure first" scope of this phase.

## Files

```
config.yaml              default flags for run.py (edit, or override via CLI/Kaggle)
prepare.py, evaluate.py, run.py, inspect_sample.py
dataset/demo/             the official 18-page demo set (gitignored)
results/
  baseline/               report.md, metrics.json, runtime.json, run_metadata.json (committed)
                          predictions/, evaluator_config.yaml, *_result.json debug dumps (gitignored)
  docling/                 same shape
logs/                     evaluate.py's captured evaluator stdout/stderr (gitignored)
kaggle/run_full_benchmark.ipynb
```
