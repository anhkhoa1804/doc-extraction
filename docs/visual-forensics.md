# Classic visual forensic trace

This opt-in debug artifact observes the **baseline component pipeline**, not a
new public extraction contract. Canonical Document remains 1.4.0. The
authoritative CDOI `DocumentExtractionContract` 1.0.0 / ExtractionPackage v1
is distinct from this internal diagnostic; no public package producer or KP
adapter is implemented in this repository. See
[`contract-adoption-audit.md`](contract-adoption-audit.md).

Enable `visual_forensics: true` in a normal CPU/production configuration, or
construct `PipelineConfig(visual_forensics=True)` for the existing public
`doc_extraction.cli.process_file(...)` entry point. The default is false.
The public function signature and extraction settings are unchanged. This
debug switch is excluded from `config_snapshot`: it controls observations,
not extraction semantics. Presence and format of the separate artifact
identify instrumentation. No OCR languages, models or resource limits change.

After a baseline run, look for:

```text
<run>/diagnostics/classic_visual_trace.json
```

It covers standalone images, scanned PDF pages and digital PDF visual page
fallbacks. Native-only extraction and whole-document/E2E backends do not
produce visual page traces. The recorder publishes on public API exit,
including extraction failures after the recorder was created. A failure
before image opening has no page trace. Diagnostic persistence is best-effort;
permission errors/unsafe diagnostic targets cannot mask a backend exception
or change a successful extraction. An absent trace is **not** proof that a
stage was skipped. Existing metadata/logs remain authoritative for run outcome.
An `observation_failed` or `dependency_observation_failed` flag means affected
observations are incomplete; do not interpret remaining counts as a complete
trace. Optional observation exceptions never replace pipeline exceptions.
The public API binds the artifact to the input SHA-256 and the actual
`metadata.json` timestamp. Check both before attributing a trace to a run:
old artifacts may remain if the same output directory is later reused with
tracing disabled. A direct internal stage replay has no public run binding.

## What the stages mean

| Field | Observation | Does not establish |
| --- | --- | --- |
| `input_dimensions`, `rendered_image_opened` | The rendered image opened and its pixel dimensions were read | Correctness of rasterization or visible-content recovery |
| `layout.component_calls`, `state` | Actual `analyze()` dispatch/return/failure or unavailable backend | Internal detector/model invocation count |
| `layout.regions`, `labels` | Projected adapter regions and label frequencies | Raw detector labels before Docling assembly |
| `ocr.component_calls`, `state` | Actual `recognize()` dispatch/return/failure | Calls to EasyOCR `readtext()`; Docling can reuse its cached conversion |
| `ocr.projected_tokens` | Returned `OCRResult.tokens` count | Raw OCR detections; Docling emits block/cell-level tokens |
| `ocr.tokens_by_region` | Bounded, **nonexclusive** token-center containment in projected layout boxes | OCR crop selection or exclusive ownership |
| `ocr.target_regions`, `raw_tokens`, `model_invocations` | Currently unavailable (`null`) | Zero crops, zero raw OCR detections or zero model calls |
| `dependency.public_items_*` | Cached public Docling item text/geometry counts before token projection | Original OCR cells or recognition accuracy |
| `dependency.retained_ocr_cells` | Retained parsed-page cells marked `from_ocr`, if exposed | All raw detections before filtering; absent parsed pages yield `null` |
| `dependency.retained_layout_*` | Retained cluster/cell-reference aggregates if exposed | Unique raw tokens; cells may occur in multiple clusters |
| `formula.regions`, `text_results` | Projected formula regions and public formula items with text | Specialist formula recognizer calls/successes; OCR may supply this text |
| `dependency.formula_enrichment_enabled` | Actual instantiated Docling pipeline option, if accessible | That any formula inference succeeded |
| `table.state`, `backend_tables` | Actual table component dispatch and returned candidates | Canonical table success if later filling/assembly fails |
| `table.tables`, `text_cells` | Canonical tables and nonempty cells after filling/assembly | Table structure/content accuracy |
| `canonical` | Element/text/null/formula counts and page-note count after merge, refreshed after final assembly | Complete recovery of visible content |
| `serialization` | Elements selected by explicit reading order and text-bearing omissions | Fidelity of benchmark Markdown or complete emitted text |
| `export` | Bytes in actual canonical Document Markdown, document-scoped | Page content surviving; this export includes headings even for empty pages |
| `run` | Internal status and warning/error counts | External FATAL/PARTIAL semantics |

All unknown stages/counts are `null`, not zero. `not_reached`,
`backend_unavailable`, `invoked`, `returned` and `failed` describe observed
component boundaries. A failing component records only the exception type,
never its potentially sensitive message. Configuration is bounded to backend
identities, language codes and OCR/formula enablement booleans. Source text
is not copied into the trace. Warnings are counted, not duplicated as strings.
For cached Docling conversions, requested language codes are separate from
the language codes in the instantiated **image** pipeline options. If those
options are inaccessible, configured languages are `null`, not a guessed
copy of the requested list.

Useful distinctions:

* Zero layout regions are separate from an unobserved OCR stage.
* An unavailable recognizer has zero component calls and `null` tokens; a
  recognizer returning an empty `OCRResult` has one call and zero tokens.
* Retained cluster text followed by empty public item text localizes loss
  upstream of adapter token projection, but does not identify its cause.
* Public text without geometry explains why the adapter cannot project it
  without fabricating coordinates.
* Nonzero projected tokens with no canonical element/cell text expose an
  assembly/projection discrepancy, not automatically a bug (for example,
  whitespace-only tokens can legitimately disappear).
* Canonical text outside explicit reading order is visible as an omission.
  Benchmark Markdown is a separate serializer; inspect its prediction bytes
  alongside this trace, never treat canonical export bytes as benchmark bytes.

## Bounds and privacy

At most 100 pages, 32 distinct labels, 128 region count rows per page and
4,096 examined projected tokens per region. Full layout/token totals remain
counts; per-region sampling has explicit truncation flags. Cached public
Docling traversal examines at most 4,096 items and 4,096 table cells in total.
Retained layout inspection examines at most 4,096 clusters and 4,096 cell
references in total. Retained parsed-page inspection examines up to 4,096 cells
per page (at most 100 dependency pages); it reports its bounded scope.
Counts from bounded dependency traversals are not full-population counts
when truncated. Names are limited to 64 safe characters; language lists to
32 entries. The entire JSON is limited to 256 KiB, with omitted-page accounting
when the byte budget is reached. Secure atomic no-follow output utilities are
used, with private file permissions.

No raw pixels, source text, arbitrary filesystem paths, credentials,
environment dumps or object reprs are retained. These are deterministic
aggregate observations apart from the explicit metadata timestamp used for
run binding. They naturally inherit any nondeterminism of an
upstream model. They do not change model execution or enable retention of
Docling's discarded raw pages. Optional tracing adds bounded CPU/I/O work;
normal production runtime/resource guards still apply.

## Known Chinese/formula page

Status: **STRONGLY INDICATED**, not a confirmed root cause.

`page-062fc21c-6b9c-40be-8d0e-7a617509a9bc.png#0` has stored evidence of a
1654×2339 rendered page, five projected formula regions, zero projected OCR
tokens, five null-text canonical formula elements and one-byte benchmark
Markdown. The historical config recorded `ocr_languages: [en, vi]`.
Raw OCR detections and Docling intermediate cells were not stored.

Source audit of installed Docling 2.124.0 / EasyOCR 1.7.2:

* `PipelineConfig` and `configs/{default,cpu,gpu}.yaml` set `en, vi`.
  `_get_component_backends` passes this to `DoclingBackend`, whose converter
  passes `EasyOcrOptions(lang=...)` to `EasyOcrModel`; that calls
  `easyocr.Reader(lang_list=...)`. This affects the recognition model, not
  merely metadata. It is configurable per `PipelineConfig`/document call,
  not automatically selected from document language.
* EasyOCR validates configured codes. Simplified Chinese is available as
  `ch_sim`, with a different recognition model and supported language
  combination; the current `en, vi` configuration does not select it.
  Neither this repository nor EasyOCR identifies the source-page language
  mismatch and emits a specific warning for it. No language/default changes
  were made. This is not proof that every Chinese character yields no OCR.
* `BaseOcrModel.get_ocr_rects` selects boxes from layout without excluding
  formula labels. EasyOCR filters cells by its configured confidence threshold.
  We cannot distinguish detection, confidence filtering or later assembly
  loss from the historical projected-token file.
* `PdfPipelineOptions.do_formula_enrichment` defaults to false and the local
  converter does not enable it. `StandardPdfPipeline` optionally creates
  `CodeFormulaVlmModel` for specialist code/formula enrichment. When disabled,
  page assembly can still concatenate OCR text from formula cluster cells.
  `DoclingBackend.recognize` projects available formula item text normally.
  Empty formula text remains null after merge, never synthetic LaTeX.
* Current generic empty-OCR diagnostics warn when detected text/formula
  regions receive no projected tokens. There is no new warning or recognition
  fallback introduced by instrumentation. Formula enrichment being disabled
  alone is not an extraction failure and does not prove why text was absent.
* Default Docling cleanup clears `parsed_page` unless `generate_parsed_pages`
  was enabled; we do not change this to produce stronger-looking evidence.

Run the small, model-free **stored-stage replay**:

```bash
uv run pytest tests/test_visual_forensics.py::test_existing_empty_page_artifacts_model_free_replay -q
```

This uses the existing ignored rendered/layout/OCR artifacts, runs the actual
Classic stages/merge and benchmark serializer with replay components, and
compares tracing on/off. It skips explicitly if local artifacts are absent.
It does **not** rerun EasyOCR or establish historical raw OCR behavior. Separate
cached-Docling adapter tests exercise available/missing item text and geometry
without downloading models. A live model run with retained upstream evidence
is still needed to distinguish the earlier internal information-loss stages.

## Summarizing future runs

```bash
uv run python scripts/summarize_visual_traces.py outputs/RUN/diagnostics/classic_visual_trace.json
```

The command accepts explicit trace files, checks the format/byte limit and
reports counts for formula-only/zero projected OCR, formula enrichment disabled,
projected OCR without canonical text, and zero OCR without a page warning.
Omitted pages are reported. It cannot recover internal states from old stage
files and refuses those files rather than presenting them as forensic traces.
These are symptom counts, **not** benchmark scores or causal classifications.
