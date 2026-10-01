# 046 — independent corpus challenge results

## Primary result

Protocol v2 is the sole primary result. All 24 frozen, source-document
disjoint cases completed; A and B were canonically identical in all 24. Of 17
acquisition OCR observations inside a truth locator, 9 were strict
truth-correct, but **0** were baseline-missing and **0** met
`novel_correct_acquisition_evidence`. Every candidate was duplicate baseline
evidence under the frozen normalized-exact locator rule.

The predefined decision is therefore:

> **OBSERVABILITY SUPPORTED; ACQUISITION-TIME QUALITY THESIS NOT SUPPORTED**

This closes the current quality-improvement branch. It does not invalidate the
ledger's observability, provenance, ambiguity, or accounting uses.

## Protocol correction

The v1 artifact is retained but is invalid for loss-boundary reporting. It
compared raw acquisition strings with normalized baseline strings when
computing only `canonical_exact_present`, inflating normalization-loss counts.
The normalized duplicate predicate and primary novelty predicate were already
correct. Protocol v2 corrected raw exact matching and reran the entire
unchanged population. Do not combine v1 and v2 aggregates.

## Reproducibility

* Git: `d279c2392d3282c282a9694b0f1d884b5ef40c24`
* Population: 24 cases / 24 source groups;
  `4d8bf0edec40db04660da578609fe2323849888ed440605e46222208240b8707`
* Protocol v2:
  `684b47fc025c65daa263e1f639f0532e48c62f22d877ba0714ab0b616b9a4d46`
* Evaluator: `evidence_integrity.py: normalized-exact v045`
* Environment: Python 3.10.12; Docling 2.124.0; EasyOCR 1.7.2; Torch 2.14.0
* Immutable result: `runs/2026-10-01_protocol-v2_independent-corpus.json`

## Aggregate (v2)

| metric | value |
| --- | ---: |
| acquisition observations | 942 |
| projection observations | 945 |
| truth-locator candidates | 17 |
| truth-correct | 9 |
| baseline-missing | 0 |
| novel-correct acquisition evidence | 0 |
| duplicate baseline evidence | 17 |
| ownership conflicts / unresolved | 3 / 3 |
| provenance complete | 17 / 17 candidates; 24 / 24 cases |
| derivation complete | 17 / 17 candidates |
| acquisition / normalization / ownership loss | 0 / 0 / 0 |
| reconciliation / canonical-projection / serialization loss | 0 / 0 / 0 |
| canonical-equivalent cases | 24 / 24 |

## Per-case results

`acq` is all acquisition observations; `cand` is an OCR observation centred
inside the frozen truth locator; `correct`, `dup`, `conflict`, and `prov` are
over candidates. `miss` and `novel` are zero for every case. Loss taxonomy is
`preserved` for every candidate in v2; cases without candidates have no
candidate-level loss assignment.

| case | role | acq | cand | correct | dup | conflict | prov | novel |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| ctl-00 | control | 50 | 0 | 0 | 0 | 0 | 0 | 0 |
| ctl-01 | control | 36 | 1 | 1 | 1 | 0 | 1 | 0 |
| ctl-02 | control | 19 | 0 | 0 | 0 | 0 | 0 | 0 |
| ind-00 | challenge | 43 | 1 | 1 | 1 | 0 | 1 | 0 |
| ind-01 | challenge | 22 | 1 | 1 | 1 | 0 | 1 | 0 |
| ind-02 | challenge | 44 | 1 | 0 | 1 | 0 | 1 | 0 |
| ind-03 | challenge | 29 | 1 | 1 | 1 | 0 | 1 | 0 |
| ind-04 | challenge | 27 | 1 | 0 | 1 | 0 | 1 | 0 |
| ind-05 | challenge | 121 | 1 | 0 | 1 | 1 | 1 | 0 |
| ind-06 | challenge | 33 | 1 | 0 | 1 | 1 | 1 | 0 |
| ind-07 | challenge | 46 | 0 | 0 | 0 | 0 | 0 | 0 |
| ind-08 | challenge | 49 | 1 | 1 | 1 | 0 | 1 | 0 |
| ind-09 | challenge | 51 | 1 | 0 | 1 | 0 | 1 | 0 |
| ind-10 | challenge | 65 | 0 | 0 | 0 | 0 | 0 | 0 |
| ind-11 | challenge | 84 | 1 | 0 | 1 | 0 | 1 | 0 |
| ind-12 | challenge | 13 | 0 | 0 | 0 | 0 | 0 | 0 |
| ind-13 | challenge | 29 | 1 | 1 | 1 | 1 | 1 | 0 |
| ind-14 | challenge | 23 | 1 | 1 | 1 | 0 | 1 | 0 |
| ind-15 | challenge | 4 | 0 | 0 | 0 | 0 | 0 | 0 |
| ind-16 | challenge | 22 | 0 | 0 | 0 | 0 | 0 | 0 |
| ind-17 | challenge | 97 | 1 | 1 | 1 | 0 | 1 | 0 |
| ind-18 | challenge | 18 | 1 | 0 | 1 | 0 | 1 | 0 |
| ind-19 | challenge | 11 | 1 | 0 | 1 | 0 | 1 | 0 |
| ind-20 | challenge | 6 | 1 | 1 | 1 | 0 | 1 | 0 |

## Controls and failure analysis

All three controls have zero novel-correct false positives. `ctl-01` has one
truth-correct token, but it is already represented by canonical baseline text;
it is correctly classified as duplicate, not novel.

The strongest negative pattern is not loss: nine truth-correct acquisition
observations were already represented by the canonical baseline. Nine cases
had no acquisition OCR observation inside their selected truth locator, so
they cannot support a claim of textual recovery. Three candidates had multiple
ownership claims and remained unresolved; none was elevated to novelty.

The run found no acquisition, normalization, ownership, reconciliation,
canonical-projection, or serialization loss among its truth-locator candidates.
Thus this corpus supports explanation/accounting of captured material, but it
does not show that useful, truth-supported text was absent from canonical
output.
