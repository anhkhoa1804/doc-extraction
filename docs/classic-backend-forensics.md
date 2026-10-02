# Classic backend forensic findings

This note records evidence from the stored `representative-v2-full-20261002T080500Z`
run and local source inspection. The outcome-ranked 26-page failure-analysis
set is diagnostic only; its counts are not estimates of full-dataset failure
rates. Benchmark source pages and raw predictions are not reproduced here.

## Empty-output case

Finding: **STRONGLY INDICATED**. The exact page is
`page-062fc21c-6b9c-40be-8d0e-7a617509a9bc.png#0`.

The persisted trace shows successful image rendering at 1654×2339, then five
layout regions all labelled `formula`, zero OCR tokens, five canonical
formula elements with null text, and a one-byte Markdown prediction. No
table was detected. The visual-image route is:

```text
ingest.dispatcher → pipelines.image → run_scanned_page_pipeline
  → layout.run_layout → ocr.run_ocr → table.run_table
  → merge_regions_into_page → Document.to_markdown
```

For the recorded Docling component configuration, `DoclingBackend.analyze`
and `.recognize` share one cached `DocumentConverter.convert()` result.
`analyze()` projects Docling item labels and geometry to layout regions;
`recognize()` projects nonempty item `.text` values to tokens and skips items
without text. `merge_regions_into_page()` consequently leaves text null when
no OCR token falls inside a region, and the Markdown view omits null-text
elements. That confirms the content is absent before the final Markdown
serializer, but not the first internal stage that lost it.

The installed source versions are Docling 2.124.0, docling-core 2.93.0,
docling-ibm-models 3.13.2, and EasyOCR 1.7.2. The run's resolved config sets
OCR languages to `en` and `vi`; the page annotation says simplified Chinese.
Docling's `BaseOcrModel` selects OCR boxes from layout clusters without
excluding formula-labelled clusters. Its `EasyOcrOptions` applies a
confidence threshold, and the local Classic configuration does not enable
Docling's optional formula enrichment (`do_formula_enrichment` defaults to
false). These facts make language coverage and disabled formula recognition
plausible contributors. They do not establish whether EasyOCR emitted no
cells, whether its confidence filtering removed them, or whether later
Docling assembly omitted internal results. The raw Docling page predictions,
OCR cells, and formula-enrichment outputs were not retained in the run.

No production workaround was added: enabling another language/model path
would change supported configuration and runtime requirements, and there is
not enough retained evidence to select a safe narrow fix. Current Classic
code does surface a warning when a text/formula region has no OCR tokens;
the stored run predates that warning behavior.

## Confirmed visual table ownership defect

The same frozen run contains a canonical page for
`jiaocaineedrop_jiaocai_needrop_en_397.jpg#1830` where text present in table
cells was also emitted in sibling text elements. The table bbox spans
approximately y=677–1116 in the page coordinate frame; duplicate text
elements (including the row labels and values) lie within it. This is direct
output evidence of duplicate physical ownership, not merely an evaluator
metric inference.

`merge_regions_into_page()` now treats recognized table bounds as an
exclusive owner when gathering non-table region text. It filters per token
center rather than discarding an entire overlapping region, so content
outside the table remains available. This aligns with `_orphan_tokens()`,
which already does not recover tokens from inside a table. The regression in
`tests/test_orphan_ocr_recovery.py` exercises table-cell filling plus visual
page assembly and verifies both non-duplication and preservation of text
outside the table.

The native PDF table path separately has existing regression coverage in
`tests/test_pipelines.py::test_table_text_is_not_duplicated_as_loose_paragraphs`
and the run-ownership tests in `tests/test_table_ownership.py`.

## Existing benchmark failure clusters

The frozen outcome-ranked set contains 26 pages. Threshold counts below are
descriptive of that selected set only (threshold `Edit_dist >= 0.9`):

| Observable symptom in selected set | Count | Evidence / interpretation |
| --- | ---: | --- |
| Text-block Edit distance ≥ 0.9 | 15/26 | Severe text mismatch; recognition, layout coverage, language, and alignment remain possible causes. |
| Reading-order Edit distance ≥ 0.9 | 12/26 | Ordering mismatch; metrics alone do not distinguish layout order from missing/extra text. |
| Table Edit distance ≥ 0.9 | 6/15 table-bearing selected pages | Table text/structure mismatch; no causal assignment from this metric alone. |
| Formula Edit distance ≥ 0.9 | 6 selected pages with that metric | Severe formula mismatch; the full-run aggregate is also very high, but this selected set is not a denominator for prevalence. |
| Empty one-byte Markdown predictions | 2/26 | One is the confirmed empty-output page above; the other was not source-adjudicated here. |
| Extraction failures or recorded warnings | 0/26 | These are successful-run accuracy failures, not reported extraction failures. |

On the table-heavy page `page-50ffe5d2-cd27-449a-a813-d4a8c44b12ea.png#0`,
per-page diagnostic structure-only TEDS is 0.84375 while full TEDS is
-0.036909. That is **observed** divergence consistent with content mismatch
or evaluator edge behavior, not a confirmed cause. Another selected table
page has both structure and full TEDS near zero, which is consistent with a
structural failure but still requires inspecting the table output and image
before assigning cause. The full run reported 180 pages with no extraction
failure; this does not imply complete visible-content recovery.

The OmniDocBench Markdown evaluator does not measure geometry. Geometry
failures therefore cannot be counted from these metrics. No serialization
failure or missing benchmark page was observed in the frozen run; the empty
prediction is produced from an already-empty canonical text projection.

## Determinism and conformance

`tests/test_determinism.py` repeats native digital PDF, native-table, reading
order, Office, and stable-document-ID paths on CPU, comparing canonical
structures while excluding documented run-extrinsic fields (timestamps,
durations, and output/input paths). It deliberately makes no determinism
claim for the model-based visual route. The shared test helper
`tests/backend_conformance.py` is applied to actual Classic public-API output
and a fake E2E worker output; it validates structure and physical honesty,
not content accuracy or equality between backends.

## Contract boundary

The only established extraction object in this repository is the internal
canonical `Document` (schema version 1.4.0), exposed through the documented
public extraction API. Repository and available sibling-workspace searches
found no authoritative cross-team `DocumentExtractionContract 1.0.0`,
`ExtractionPackage v1`, or KP `DocumentIR` adapter. The downstream ownership
and mapping rules remain unknown; this note does not define them.
