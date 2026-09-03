# 011 — Recover text Docling drops when a layout region is mislabeled `picture`

## Question

Experiment `1015ab2` root-caused the top production failure class
(`scan_quality`): when a stamp/seal sits over a table, Docling's layout
model labels the whole region `picture`, and `DoclingBackend.recognize()`
only ever handles `table` and text-bearing top-level items — a `picture`
item has no `.text`, so the region is silently dropped in full, even though
Docling had already OCR'd every cell inside it.

That commit stopped at diagnosis ("this resolves it, and deliberately does
not fix it"). This experiment asks: **is the fix actually the smallest thing
it looks like, and does it measurably recover the corpus?**

## Root cause, confirmed at the object level

`DoclingDocument.iterate_items()` takes a `traverse_pictures: bool = False`
parameter. With the default, a `PictureItem`'s `children` are invisible to
the traversal entirely — not filtered, not summarized, simply never visited.
Probing `cmb_scan_stamp_table_vi` directly: the `picture` item has 16
children, every one a `TextItem` with real recognized text (`STT`,
`San pham A-100`, `CONG TY TNHH`, `DA DUYET`, ...) and a page-absolute bbox
correctly nested inside the picture's own bbox. Docling recognized the
table perfectly. Nothing needed to be re-inferred — the traversal just never
looked.

## Fix

Pass `traverse_pictures=True` at all three `iterate_items()` call sites in
`docling_backend.py` (`convert()`, `analyze()`, `recognize()`). Nested
children then surface as ordinary `text` (or `table`) items one level
deeper — handled by the exact same code paths already in place for
top-level items, so no new branch was needed. The `picture` item itself is
still emitted (image semantics preserved), just no longer as the only thing
representing that region.

## Measured

Production corpus (`research/production_corpus/`, 58 docs/125 pages),
strategy `adaptive`, device `cuda` (GPU **CLEAR**: 0 MiB used, 22,564 free,
0% util both runs — resource state held constant so the delta is
attributable to the code change alone, not contention):

| | before (`results_before.json`) | after (`results_after.json`) |
|---|---|---|
| mean recall | 0.9405 | **0.9491** |
| fully recovered | 52/58 | 52/58 |
| `cmb_scan_stamp_table_vi` recall | **0.25** | **0.75** |
| every other document | unchanged | unchanged |
| test suite | 226 passed | **227 passed** (+1 regression test) |

`cmb_scan_stamp_table_vi` is the only document affected — expected, since
it is the only one in the corpus whose failure mode is this exact
mislabel-then-drop mechanism. All 57 other documents score identically
before and after, which is the control: this change touches picture-region
traversal only.

Table *structure* for this document is still not recovered (`tables 0/1`,
unchanged) — Table Transformer's own visual table detector independently
fails to find a grid under the stamp. That is a separate, harder defect
(table *detection*, not text *retrieval*) and is out of scope here; recorded
as a known remaining gap, not silently left unstated.

## Regression test

`tests/test_config_and_backends.py::test_docling_recognize_and_analyze_traverse_picture_children`
— a pure unit test over a stubbed `iterate_items(traverse_pictures=...)`
that fails on the pre-fix code (verified: reverting the three call sites
locally reproduces the failure) and passes after. No model or corpus
needed to run it.

## What this does NOT establish

* Table *detection* under occlusion is still broken; this experiment did
  not touch it.
* The other 5/6 `scan_quality` failures are unrelated mechanisms
  (resolution, genuine OCR misreads, tiny text) and are untouched by this
  fix, exactly as `1015ab2` predicted.
* Synthetic corpus only — see the standing caveat in `experiments/010`.

## Reproduce

```bash
python research/production_corpus/generate.py
python research/production_corpus/run_benchmark.py --strategy adaptive --device cuda
```
