# Claim ledger

Labels describe the evidence in this repository, not universal claims about
document extraction.

| Claim | Status | Basis and limit |
| --- | --- | --- |
| Structure-valid recovery is not necessarily useful textual evidence | **ESTABLISHED** | Frozen Experiment 040 includes empty structurally valid tables and baseline-duplicate text. |
| The ledger improves observability and evidence accounting | **ESTABLISHED** | Experiments 043--046 preserve identity, provenance, duplicate and ambiguity distinctions without changing canonical output. |
| Acquisition-time preservation improves extraction quality | **CONTRADICTED in tested populations** | 045 and independent 046 both found zero novel-correct acquisition evidence under their frozen rules. This is not a universal impossibility claim. |
| Canonical projection causes major truth loss | **CONTRADICTED in the 046 exact-match subset** | All 9/9 exact acquired truth units were represented canonically. The evidence is too small and restricted to call this a general result. |
| Serialization causes major truth loss | **CONTRADICTED in the 046 exact-match subset** | All 9/9 exact acquired truth units appeared in Markdown under the frozen matching rule. |
| Ownership ambiguity causes truth loss | **UNKNOWN** | The liberal feasibility oracle adds one ambiguous exact-text unit, but truth has no canonical-owner label and all exact text is baseline-duplicate. |
| Acquisition coverage is the dominant loss mechanism | **UNKNOWN** | 15/24 truth units lack exact acquired text, but no-centre events are confounded by coarse spans, annotation segmentation, and one out-of-bounds locator. |
| Stage-localized truth-side attribution is valid on real runs | **CONTRADICTED** | The current artifacts cannot distinguish non-acquisition from locator/segmentation mismatch, so real boundary attribution is not identifiable. |
| The oracle-reconciliation gap is meaningful | **UNKNOWN** | The observed upper bound is 1/24, but it is not a valid semantic ownership oracle. |
| The framework is novel | **NOT TESTED** | Gate 1 validates neither novelty nor a comparison to related provenance or error-decomposition work. |

## Consequence

The ledger and evaluator remain useful engineering infrastructure for
provenance, duplicate detection, ambiguity disclosure, and reproducible audit.
They have not passed the research validity requirement for a stage-localized,
truth-side causal measurement methodology.
