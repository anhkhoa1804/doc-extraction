# Observations — 000 CPU smoke test

Run 2026-08-20, CPU-only, `configs/cpu.yaml`, 12 files at the repo root.

## Result

All 12 documents processed, exit code 0, no parser failures.

| Metric | Value |
|---|---|
| Documents | 12 (10 unique — two pairs are byte-identical duplicates) |
| Pages / slides / sheets | 124 |
| Elements | 1868 |
| Tables | 76 |
| Table cells | 1382 |
| Total runtime | 94.9 s |

## Routing

| Route | Documents |
|---|---|
| `digital_pdf` | 8 |
| `native_office` | 3 |
| `scanned_pdf` | 1 |

The single `scanned_pdf` is `FROGSLEAP_BUSINESS LICENSE.pdf`, and it was
**not** routed there for lack of text — it has a full text layer on 100% of
sampled pages. It was rerouted because that text fails quality checks
(broken font CMap). See 001.

## Runtime is dominated entirely by the OCR path

| Document | Route | Runtime |
|---|---|---|
| FROGSLEAP_BUSINESS LICENSE.pdf (2 pages) | scanned_pdf | **84.6 s** |
| FROGSLEAP_COMPANY PROFILE.pdf (40 pages) | digital_pdf | 3.5 s |
| everything else | native / digital | 0.06 – 1.0 s |

One 2-page document on the OCR path costs **89% of the entire corpus
runtime**. The 40-page document on the native path costs 3.5 s — roughly
**480× less per page**.

This is the single clearest quantitative result in the repo, and it is what
justifies the routing design: getting the route decision right matters far
more than optimizing either path. It also means any future false positive in
the quality gate is expensive, not merely untidy — an earlier revision of the
heuristic wrongly flagged 2 pages of the company profile, which pushed that
document from 3.5 s to 122 s (a 35× penalty) before the false positives were
fixed. See 001.

## Reproducibility

Both duplicate pairs produced identical page/element/table counts under
different `document_id`s, which is a (weak but free) determinism check:
identical bytes in, identical structure out.

## What this does not show

* Nothing here checks *correctness*. Every number above is a count, not an
  accuracy. A document could extract 31 tables that are all wrong and this
  experiment would call it a success.
* Two 9-page documents produced 0 tables. Not verified by hand whether they
  genuinely contain none — see 002.
