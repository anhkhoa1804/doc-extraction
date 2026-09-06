# 022 — The recognizer was the bottleneck

## Current Baseline

`git rev-parse HEAD` at start: `205baf3`. `pytest -q`: 304 passed, 10
skipped (interpreter `~/.venvs/doc-extraction-gpu312/bin/python`). GPU
preflight **CLEAR** before each of the 3 GPU workloads (0 MiB / 23034 MiB,
0% utilization, no compute processes); postflight clean, nothing leaked.

Experiment 021 left one falsifiable question. It has a decisive answer.

## The Question

021 established that `cmb_scan_tiny_vi`'s 0.00 recall is Vietnamese
character-level corruption, and that this project's two OCR backends share
one recognizer (`docling_backend.py:221` wires Docling's OCR to EasyOCR, so
both resolve `vi` through the same `latin_g2` weights). That made one
question decisive either way:

> Is the diacritic information present in these pixels and missed by
> `latin_g2`, or absent from the render entirely?

Tesseract 4.1.1's LSTM engine with `vie` traineddata is the cheapest honest
test — different model family, different training data, no shared lineage,
Apache-2.0, CPU-only, `apt install tesseract-ocr-vie`.

## OBSERVED

Same corpus PDFs, same renderer, same 200 DPI, same `must_contain` strings,
same scoring. EasyOCR on the **L4**; Tesseract on **CPU**. 49 of 58
documents (9 excluded: not PDFs, or no `must_contain`). All pages rendered,
not page 0 only.

| engine | mean raw exact | mean raw word | perfect docs | zero-recall docs | total time |
|---|---|---|---|---|---|
| EasyOCR (GPU) | 0.6245 | 0.9051 | 14 | 7 | 111.3 s |
| **Tesseract `vie` (CPU)** | **0.9270** | **0.9336** | **38** | **1** | **77.0 s** |

Split by language — the whole effect lives in one of them:

| language | n | EasyOCR | Tesseract | relative |
|---|---|---|---|---|
| **Vietnamese** | 29 | **0.4197** | **0.8865** | **+111%** |
| English | 20 | 0.9214 | 0.9857 | +7% |

The three documents 021 named, at 200 DPI:

| document | EasyOCR exact/word | Tesseract exact/word |
|---|---|---|
| `cmb_scan_tiny_vi` (corpus's only 0.00) | 0.000 / 0.625 | **0.667 / 0.944** |
| `ord_contract_vi` (013 correlated error) | 0.000 / 0.782 | **1.000 / 1.000** |
| `hc_low_contrast_vi` (013 correlated error) | 0.000 / 0.735 | **1.000 / 1.000** |

Twelve documents went from partial or total failure to perfect, including
`hc_checkbox_vi` (0.200→1.000), `ord_form_vi` (0.250→1.000), `hc_scan_vi`
(0.250→1.000), `hc_tiny_text_vi` (0.333→1.000), and `long_policy_vi_60p`
(0.333→1.000, and 39.2 s vs 58.9 s across 60 pages).

**Tesseract is not uniformly better — 4 documents regress:**

| document | EasyOCR | Tesseract |
|---|---|---|
| `hc_rotation_vi` | 0.333 | **0.000** |
| `hc_tiny_cells_vi` | 0.429 | 0.286 |
| `cmb_tiny_table_en` | 0.857 | 0.714 |
| `cmb_lowcontrast_stamp_vi` | 0.800 | 0.600 |

## INTERPRETATION

**The information was on the page the whole time.** Four milestones treated
`cmb_scan_tiny_vi` as a resolution problem and spent up to 34.8 megapixels
on it; a different recognizer reads it at 3.87 megapixels, on CPU, in
0.60 s. The dominant lever for Vietnamese on this corpus is the **choice of
recognizer**, not DPI, not recovery logic, not fusion, and not a VLM.

**This is the more uncomfortable reading.** This project has built
increasingly sophisticated machinery on top of the recognizer —
cross-backend agreement (`7aab649`), evidence fusion (013), targeted
recovery (014), scan recovery (015), order recovery (018) — while the
recognizer underneath was resolving Vietnamese at 0.42 exact recall. Some
of that machinery was measuring, and working around, a defect one apt
package removes. `order_recovery` in particular was validated on
`hc_scan_vi`, a document Tesseract simply reads correctly (0.250→1.000).
That does not make the machinery wrong — it makes its *evaluation baseline*
wrong, and every "n=2 real positive cases" promotion decision in milestones
014-018 was taken against a baseline that understated the achievable floor.

**The 4 regressions are the most valuable part of the result.** They are
not linguistic — they are geometric: rotation, tiny cells inside tables,
low contrast under a stamp. EasyOCR's detector handles degraded and rotated
geometry better; Tesseract's recognizer handles Vietnamese characters far
better. The two engines **fail differently**, which is exactly the property
021 showed the current pair lacks. This is the precondition for
`assess_ocr_agreement` to become a real signal rather than a recognizer
agreeing with itself: disagreement between EasyOCR and Tesseract carries
information that disagreement between Docling and EasyOCR cannot.
`hc_rotation_vi`'s 0.333→0.000 is a specific, probably-cheap defect —
Tesseract ran at `--psm 3` with no orientation detection; `--psm 0`/OSD is
untested and is the obvious first thing to try.

## LIMITATION

These are the caveats that keep this from being a promotion decision:

1. **This measures raw OCR text recall on rendered pages, not the shipped
   pipeline.** Most of this corpus's digital PDFs route through the native
   text layer and never reach OCR at all, so the corpus's headline recall
   (0.9537) will **not** move by 0.30. This result bounds the OCR route's
   ceiling; it does not predict the production delta. That A/B has not been
   run.
2. **Hallucination was not measured.** The corpus scores `must_not_contain`
   and this comparison did not. An engine that emits more text can score
   better on recall while producing more confident garbage — precisely the
   failure this project's central design decision exists to prevent. Until
   `must_not_contain` and precision are measured, "better" means "better on
   recall," nothing more.
3. **No geometry evaluation.** The pipeline consumes `OCRToken` bboxes and
   confidences for layout, table cell assignment, and `order_recovery`.
   Tesseract's word-level boxes (TSV output) are untested here; a recognizer
   that reads better but localizes worse could regress tables while
   improving text.
4. Tesseract 4.1.1 (Ubuntu's package), not 5.x. n=49 documents, synthetic,
   one corpus. English n=20 is too small to call the +7% meaningful.

## Architecture Consequence

The native-first adaptive architecture is **not** challenged by this — the
routing decision, the text-quality gate, and the per-page fallback are all
orthogonal to which recognizer runs on the pixels. What is challenged is the
assumption that the OCR stage was a solved, swappable commodity whose
identity did not matter. It was the bottleneck, and it was invisible
because both "independent" backends shared it.

## What We Should NOT Build

* **A diacritic post-processor** — still rejected, and now clearly
  unnecessary: the accents can be *read*, so guessing them from a language
  prior would be strictly worse and unfalsifiable.
* **Any VLM work for this failure class.** 021 argued the VLM decision test
  was satisfied because no existing evidence source could recover the
  diacritics. That premise is now false: a 4 MB CPU traineddata file
  recovers them. A VLM for Vietnamese character recognition would be orders
  of magnitude more compute for a problem `apt install` solves.
* **More DPI escalation.** Closed in 021, and reconfirmed: the winning
  configuration is the *lowest* DPI tested.
* **Replacing EasyOCR outright.** The 4 regressions say it would trade one
  set of failures for another. The evidence supports adding an engine, not
  swapping one.

## Next 3 Actions

1. **Wire Tesseract as a real backend** (`backends/tesseract_backend.py`)
   emitting `OCRToken` with word-level bboxes and confidences from TSV
   output, then run the full production A/B through the actual pipeline —
   `must_contain` *and* `must_not_contain`, tables, and reading order. This
   is the number that decides promotion, and it is the number that does not
   exist yet.
2. **Re-run `assess_ocr_agreement` with EasyOCR vs Tesseract** as the two
   sources. 021 showed the current pair cannot disagree at the character
   level; this pair demonstrably can (49 documents, 4 of them in opposite
   directions). Test whether agreement now predicts correctness — the
   signal's original premise, testable for the first time.
3. **Fix the rotation regression** (`--psm 0` orientation detection) and
   re-measure `hc_rotation_vi`; if OSD closes it, the complementarity
   argument strengthens and the per-document routing question ("which
   engine for which page?") becomes the natural follow-on.

## Promotion Decision

| | decision |
|---|---|
| Tesseract `vie` as an **evidence source** | **STRONG CANDIDATE** — not promoted |
| Tesseract as a **replacement** for EasyOCR | **REJECTED** — 4 regressions, geometric |
| "The recognizer is the dominant lever for VI" | **ACCEPTED** as this corpus's finding |

No production code changed. Promotion requires the full-pipeline A/B with
hallucination and geometry measured (action 1) — recall-only evidence is
not sufficient to ship a recognizer, and this project has rejected weaker
promotions for less.

## Reproduce

```bash
sudo apt-get install -y tesseract-ocr tesseract-ocr-vie   # 4.1.1, Apache-2.0

cd research/experiments/_scan_forensics
python independent_recognizer.py --device cuda --dpi 200 \
    --docs $(python -c "import json;print(' '.join(d['document_id'] for d in json.load(open('../../production_corpus/corpus/manifest.json'))['documents_list']))")
```

Raw output: `research/experiments/_scan_forensics/independent_recognizer.json`
(per-document, per-engine, full normalization ladder, timings).
