# Observations — 001 PDF text-layer quality

Run on the 10 unique PDFs at the repo root (24 sampled pages), CPU-only,
2026-08-20.

## Result: the signals separate the corpus cleanly

| Signal | Clean pages (n=20) | Corrupt pages (n=2) | Threshold used |
|---|---|---|---|
| `mixed_script_word_ratio` | 0.000 – 0.000 | 0.400 – 0.538 | 0.10 |
| `unexpected_script_ratio` | 0.000 – 0.000 | 0.157 – 0.213 | 0.10 |
| `digit_in_word_ratio` | 0.000 – 0.011 | 0.356 – 0.380 | 0.30 |
| `alpha_ratio` | 0.698 – 0.840 | 0.393 – 0.515 | 0.30 (min) |

2 further pages carried too little text to assess (48 and 203 chars on cover
slides) and are correctly reported as `insufficient_text` rather than either
"clean" or "suspicious".

**`mixed_script_word_ratio` is the discriminating signal.** Every clean page
scored exactly 0.000 — including the Vietnamese-language pages, which is the
important negative control, since Vietnamese diacritics could plausibly have
been mistaken for encoding damage. The corrupt pages scored 0.400 and 0.538.
The threshold at 0.10 sits in a gap with no observed values in it at all.

`alpha_ratio` did **not** fire on the corrupt pages (0.393 and 0.515, both
above the 0.30 floor). It is retained as a secondary signal for symbol-soup
extraction, not as a CMap detector.

## What was flagged

Only `FROGSLEAP_BUSINESS LICENSE.pdf`, both sampled pages. This is the
document already known to be corrupt from the phase-1 smoke test — its text
layer decodes `Độc lập Tự do Hạnh phúc` as `ĈӝF OұS 7ӵ GR +ҥQK SK~F`.
Rerouting it through the visual/OCR path recovers correct Vietnamese.

No clean document was flagged (zero false positives on this corpus).

## What this does *not* show

* **n=1 corrupt document.** Perfect separation on a single positive example
  is weak evidence about the threshold's general position. It shows the
  signal responds to this failure mode with a large margin; it does not
  establish a false-positive rate on a wider corpus.
* **Only one corruption mode is covered.** A CMap that maps letters onto
  *other plausible Latin letters* would keep the text single-script and pass
  every signal here. That failure is undetectable without a language model
  or an OCR cross-check, and we have not looked for examples of it.
* **Latin-corpus assumption.** `expected_scripts: ["LATIN"]` is what makes
  `unexpected_script_ratio` meaningful. A genuinely mixed-script corpus
  needs that setting changed, not the thresholds loosened.
* Nothing here says the *rerouted* output is correct — only that the
  original was wrong. See 004 for reading-order problems in the recovered
  text.

## Follow-up worth doing

Cross-check a suspicious page's native text against an OCR sample of the
same page and measure the disagreement directly. That would turn a
heuristic into a measurement, and would also catch the Latin-to-Latin case
the current signals miss.
