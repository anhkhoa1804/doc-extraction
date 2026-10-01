# Gate 1 results

## Decision

**GATE 1 FAILED.**

The analysis has an independent truth-side denominator and a deterministic
functional classifier, but it cannot identify real loss boundaries from the
available artifacts. In particular, the current no-token-centre predicate
conflates at least OCR-span/annotation segmentation and truth-locator clipping
with non-acquisition. The truth annotations also lack canonical-owner labels,
which prevents a criterion-valid ownership oracle.

## Inputs and reproducibility

* Source run: `experiments/046_independent_corpus_challenge/runs/2026-10-01_protocol-v2_independent-corpus.json`.
* Population: the frozen 046 population, 24 pre-selected annotations from 24
  distinct source groups (21 challenge, 3 controls).
* Analysis: `run_gate.py`; primary immutable output:
  `gate1_results_v2.json`.
* `gate1_results.json` is retained as a superseded pre-correction analysis:
  it classified `ind-15` before the truth locator's out-of-image right edge
  was checked. It is not used for results.
* Unit of analysis: one frozen OmniDocBench text annotation per case, clustered
  by source group. Raw OCR tokens are not treated as independent samples.

## Tests

* Focused evaluator and fault-injection tests: **12 passed**.
* Full regression suite: **369 passed, 10 skipped, 5 warnings**. An initial
  full-suite run had one intermittent Office determinism failure; the isolated
  test and the final full-suite rerun passed. No production code was changed
  in this gate.

## Truth-side result

| State | Count / 24 |
| --- | ---: |
| truth exists | 24 |
| OCR token centre in truth locator | 17 |
| normalized-exact truth text acquired | 9 |
| exact acquired text with unique accepted ownership | 8 |
| exact text represented canonically | 9 |
| exact text serialized | 9 |
| exact text with provenance complete | 9 |

There were no canonical-projection or serialization losses among the nine
exact-text units. As a descriptive zero-event bound only, 0/9 has an
approximately 28.3% one-sided 95% binomial upper bound under an IID assumption;
the heterogeneous, one-unit-per-source design does not justify interpreting it
as a population estimate.

## Real-case attribution limitation

The v2 artifact has five challenge no-centre cases, not the `8/21` stated in
the task prompt. The artifact is authoritative for this gate. Two are directly
confounded by intersecting coarse OCR/layout spans (`ind-07`, `ind-10`), one has
an out-of-image truth locator (`ind-15`), and two have no intersecting current
OCR/layout span (`ind-12`, `ind-16`). Thus none establishes acquisition loss.

## Fault injection

Direct stage-state mutations exercised acquisition, ownership, reconciliation,
canonical projection, serialization, and normalization. The deterministic
classifier returned the intended label in 6/6 cases. This is a unit-level
functional check only: it does not establish that a label is causally
identifiable in a real pipeline execution.

## Oracle reconciliation

Baseline exact-text plus unique ownership is 8/24. A liberal truth-informed
claim-selection feasibility bound is 9/24, a gap of one unit. Because truth
does not say which canonical owner is correct, this is not a valid semantic
oracle; all nine exact-text units are already baseline duplicates. It cannot
show that reconciliation explains missing truth.

## Human adjudication

Not performed. Existing artifacts do not provide two independent judgments or
truth-side canonical owner labels, and a new annotation exercise is outside
this bounded gate. Matching and ownership reliability therefore remain
unknown rather than assumed.

## Validity assessment

| Dimension | Assessment | Reason |
| --- | --- | --- |
| Construct validity | Partial | The stages and denominator are explicit, but token-centre presence is not acquisition. |
| Criterion validity | Fails | There are no independent gold labels for actual acquisition stage or canonical ownership. |
| Discriminant validity | Partial | Synthetic state injections separate labels; real no-centre cases demonstrate category confounding. |
| Causal identifiability | Fails | Several physical/evaluator mechanisms produce the same observed state. |
| Denominator validity | Partial | The 24 truth annotations are pre-frozen and independent of candidates, but not token-level or owner-labelled. |
| Matching validity | Fails for loss attribution | Coarse spans and locator clipping produce false non-acquisition appearances. |

## Research versus engineering

The production/evaluation infrastructure remains useful for stable observation
IDs, provenance chains, ambiguity and duplicate reporting, and non-mutating
audit. The proposed research framework--truth-side, stage-localized causal
attribution across modular systems--does not have adequate validity from these
artifacts and should not proceed to a multi-system study.

## Required next action

Close this research branch and retain the evidence-integrity implementation as
engineering and evaluation infrastructure. No follow-on corpus, recovery, or
preservation experiment is recommended under this hypothesis.
