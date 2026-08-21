# Experimentation

## Local validation (CPU-only, no GPU)

The full sequence, reproducible from a clean checkout:

```bash
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m doc_extraction run     --input data --config configs/cpu.yaml
.venv/Scripts/python.exe -m doc_extraction compare --input data --config configs/cpu.yaml --backends baseline docling
.venv/Scripts/python.exe -m doc_extraction inspect
.venv/Scripts/python.exe scripts/build_failure_report.py --input outputs/
```

Nothing in that sequence needs a GPU, CUDA, or network access once models
are cached. `make test` / `make baseline` / `make compare` / `make report`
wrap the same commands.

## Reproducibility

`outputs/<document_id>/metadata.json` records the full resolved config
(`config_snapshot`), input file hash, route **and the reason for it**
(`route_reason`, `text_profile`), backend, library versions
(`model_versions`), timestamp, runtime, and device.

Two properties make this actually reproducible rather than nominally so:

* `config_snapshot` is **machine-independent** — `cache_dir` is relative, so
  a snapshot from one machine is valid on another.
* `document_id` is **content-addressed** (`<slug>-<sha256 prefix>`), so
  re-running a file overwrites its own directory instead of accumulating
  stale duplicates, and two files sharing a name cannot collide.

If two runs of the same input under the same config differ, that is itself a
finding worth investigating (an unpinned model, non-determinism in an OCR
engine), not something to shrug off.

## Backend comparison

```bash
doc_extraction compare --input data --config configs/cpu.yaml --backends baseline docling
```

Writes `outputs/comparison/<document_id>/`:

```
outputs/comparison/<document_id>/
  baseline/       full outputs/<document_id>/-shaped tree for that arm
  docling/
  diff.json       per-backend stats + pairwise disagreement
  summary.html    side-by-side tables, disagreements highlighted
```

`baseline` is an arm like any other — this repo's pipeline is a system under
comparison, not a reference answer.

### What is measured

Per backend: pages, elements, element types, tables, table cells, text
length, mean confidence, runtime, device, errors.

Pairwise per page (`evaluation/disagreement.py`):

| Metric | Question it answers |
|---|---|
| `element_count_delta`, `table_count_delta` | Did both systems find the same amount of structure? |
| `text_similarity` | Did they read the same characters? |
| `bbox_match_rate`, `mean_matched_iou` | Did they find the same *regions*? |
| `reading_order_correlation` | Did they order the shared regions the same way? |

Splitting "found the same regions" from "read them the same way" from
"ordered them the same way" is deliberate: a page can score perfectly on
region detection and still be badly wrong in reading order, and that is one
of this project's named research interests.

### What is deliberately *not* measured

**There is no aggregate quality score.** There is no ground truth for this
corpus, so any single number would manufacture confidence we have not
earned, and would hide the per-page detail that makes the comparison useful.
Large deltas are pointers to go look at a page, not verdicts on a backend.

## Failure report

```bash
python scripts/build_failure_report.py --input outputs/
```

Reads only artifacts already on disk — never re-runs extraction — and writes
`outputs/failure_report/`:

```
summary.md         most-suspicious-first overview
documents.csv      one row per document
pages.csv          one row per page
regions.csv        one row per element (bbox-level)
suspicious_text/   full text of pages that failed quality checks
tables/            every extracted table as CSV
inspection/        index linking to each document's HTML inspector
```

Surfaces: parser failures, suspicious native text, pages that needed the
visual fallback, text-density outliers (possible segmentation problems),
runtime outliers (relative to the batch median, not an absolute threshold),
and backend disagreements.

## Logging

Every stage call appends one line to
`outputs/<document_id>/logs/pipeline.jsonl`:

```json
{"timestamp":"...","document":"...","page":2,"stage":"table",
 "backend":"pymupdf_tables","status":"success","runtime_seconds":0.045,
 "device":"cpu","output_path":"outputs/.../tables/page-003.json",
 "warnings":[],"error":null,"metrics":{"num_tables":1,"num_cells":24}}
```

Failures are always logged (`status: "failure"`, `error` populated) **and
the exception is still raised** — `StageLogger.stage(...)` records before it
propagates, it never swallows. If the console says `FAILED`, the same
message plus stage/timing context is in `pipeline.jsonl`.

## Experiments

`experiments/NNN_name/` holds the *question*, the *config*, the *results*,
and the *conclusion* — small files worth committing. Raw run artifacts stay
in `outputs/` (gitignored, regenerable). See
[experiments/README.md](../experiments/README.md). Only experiments that
were actually run are recorded; a missing `results.json` truthfully means
"not run yet".

## External benchmarking (OmniDocBench)

Experiments 000-004 measure this pipeline against its own 12-document
corpus only — there is no external reference point. `experiments/005_omnidocbench/`
integrates the official [OmniDocBench](https://github.com/opendatalab/OmniDocBench)
benchmark as an **external, unmodified evaluator** (a separate Python
3.10/3.11 environment, `.venv-omnidoc/`, cloned outside version control at
`.external/OmniDocBench/`) rather than reimplementing any of its metrics
(Edit Distance, TEDS, CDM, BLEU/METEOR).

```bash
python experiments/005_omnidocbench/run.py \
    --dataset experiments/005_omnidocbench/dataset/demo \
    --backend baseline \
    --output experiments/005_omnidocbench/results/baseline
```

`prepare.py` (generate predictions, this project's own `.venv`) and
`evaluate.py` (invoke the official evaluator, subprocess into
`.venv-omnidoc`) are independently rerunnable — see
[experiments/005_omnidocbench/README.md](../experiments/005_omnidocbench/README.md)
for the full setup (including two genuine Windows-specific bugs found and
worked around without touching the evaluator's own code), the IR→benchmark
field mapping, and what was and wasn't run locally.

## Configuration

`configs/cpu.yaml` (validated), `configs/default.yaml` (identical to cpu),
`configs/gpu.yaml` (**unvalidated**, see its header). Override with
`--config path.yaml`, or point `--input`/`--output` for a one-off.

Precedence is intentionally just *file, then CLI flags* — no environment
overlay — so `config_snapshot` in `metadata.json` is a complete record of
what actually ran. The exception is the cache-directory variables described
in [setup.md](setup.md), which are set only if not already present so an
operator's environment always wins.
