# Observations — 007

## 1. The hypothesis was right, and the obvious remedy is wrong

The aggregate text edit distance improved from **0.7476 to 0.5543** (−25.9%)
by changing one config line. That is decisive on the original question: the
first OmniDocBench score was measuring an **OCR language mismatch**, not a
broadly broken extraction pipeline. Chinese page-level edit distance nearly
halved (0.9744 → 0.5278).

But the naive reading of that result — "so configure Chinese" — is refuted by
the same run:

| Subset | Baseline (`en`,`vi`) | Candidate (`ch_sim`,`en`) | |
|---|---|---|---|
| All text (page avg) | 0.7476 | **0.5543** | −25.9% better |
| Simplified Chinese (n=149) | 0.9611 | **0.7354** | −23.5% better |
| **English (n=80)** | **0.3857** | 0.5540 | **+43.6% worse** |
| English + Chinese mixed (n=10) | 0.9314 | 0.9792 | +5.1% worse |
| Reading order | 0.6664 | **0.5775** | −13.3% better |

Swapping the Latin recognition model for the Chinese one does not *add* a
capability — it **trades** one for another. EasyOCR serves `vi` from
`latin_g2` and `ch_sim` from `zh_sim_g2`, and a single reader cannot hold
both. The language sets are mutually exclusive, so every configuration is a
choice about which subset of the corpus to read well.

## 2. The sharpest single number: English tables collapse

| Table metric | Baseline | Candidate |
|---|---|---|
| `table_en` TEDS-structure (n=3) | **0.7150** | **0.0000** |
| `table_simplified_chinese` TEDS-structure (n=7) | 0.0952 | 0.1753 |
| All tables, TEDS-structure | 0.2812 | 0.1227 |

English table structure went from the single best result in the entire
baseline evaluation to zero. n=3 makes this indicative rather than
conclusive, but a fall from 0.715 to exactly 0.000 is not noise in the
ordinary sense — it means no English table was recovered structurally at all.

Aggregate table TEDS got *worse* overall (0.0908 → 0.0041) even though the
Chinese structure subset improved. A single aggregate number would have
hidden both halves of this.

## 3. Why reading order improved without touching the reading-order code

Reading order improved by 13.3% while `stages/reading_order.py` was
untouched. This is not a reading-order improvement — it is a measurement
artifact worth understanding.

The geometric orderer ranks *detected regions*. When OCR returns nothing for
a Chinese page, there are almost no regions to order, and the metric compares
an essentially empty sequence against a full ground-truth one. Once the text
is actually recognized, there are real regions to sequence and the ordering
heuristic gets a chance to be right.

The lesson generalizes: **downstream metrics are not independent of upstream
recognition.** A reading-order or table score computed over a page whose text
was never read is measuring the failure of OCR, not the quality of the stage
being named.

## 4. Chinese is better but still poor — do not overclaim

0.7354 is a large improvement over 0.9611 and still a bad score in absolute
terms. Having the right language model is evidently necessary and clearly not
sufficient. What remains unexplained is whether the residual error is
recognition quality, region segmentation, or the reading-order/aggregation
path — this experiment does not separate them, and no claim is made about
which.

## 5. An operational finding: config and model cache must move together

The first attempt failed on all 18 pages with
`FileNotFoundError: Missing .../EasyOcr/zh_sim_g2.pth and downloads disabled`.

Changing `ocr_languages` requires a matching prefetch, because the project
sets `DOCLING_ARTIFACTS_PATH`, which disables Docling's auto-download. Two
things are worth recording:

* This is the **correct** failure. Eighteen pages of confidently empty output
  would have been far worse than a hard crash, and would have looked exactly
  like "the pipeline is bad at Chinese" — which is the very conclusion this
  experiment exists to test. The loud failure protected the science.
* It is nonetheless a sharp edge: the config accepts any language string, and
  the mismatch only surfaces at first inference. `scripts/validate_environment.py`
  now lists the cached EasyOCR models for exactly this reason, and
  `docs/reproducibility-matrix.md` records which language sets are validated.

## 6. What this means for the project

**The repository default should not change.** `["en", "vi"]` is correct for
the private corpus this project actually serves, and this experiment gives no
reason to alter it — it would trade a matched configuration for a mismatched
one.

The transferable findings are:

1. **A benchmark must not inherit a corpus-tuned configuration.** Any future
   OmniDocBench result should state its `ocr_languages`, and comparing runs
   with different language sets is not a comparison of pipelines. The
   config snapshot in `run_metadata.json` already records this — it now needs
   to be *read* when interpreting a score.
2. **A single global OCR language set is inadequate for a multilingual
   corpus**, and the ceiling is structural rather than a tuning problem: no
   single EasyOCR reader configuration can score well on both subsets here.
3. Per-document (or per-page) language detection is the real fix, and it fits
   the repository's existing architecture unusually well — routing already
   computes cheap per-page text signals before committing to an expensive
   path, and `ingest/text_quality.py` already counts Unicode scripts per page.
   The information needed to choose a language pack is largely already being
   computed and then discarded.

## 7. Negative result worth keeping

The aggregate improved, so a less careful writeup could have reported this as
a clean 26% win. It is not one. Recording the English regression is the more
useful half of the result: it is what turns "configure Chinese" into "route by
language", and it is the reason the project default stays where it is.
