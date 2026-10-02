# OmniDocBench Failure Analysis v1

Analysis records: **26 pages** from the frozen classic representative-v2 run.
Selection is outcome-ranked for diagnosis only; it is not a new benchmark population. No benchmark text or images are reproduced because dataset redistribution terms are unverified.

## Observed findings

### page-062fc21c-6b9c-40be-8d0e-7a617509a9bc.png#0

**OBSERVED:** Classic final Document contains five formula-labelled regions with null text; OCR returned zero tokens; benchmark Markdown is header-only/empty.

**Inference, not confirmed:** The loss precedes the benchmark serializer. The available trace places it in the classic layout/OCR path, but does not identify a lower-level model root cause.

### page-50ffe5d2-cd27-449a-a813-d4a8c44b12ea.png#0

**OBSERVED:** The wide/rotated table page has a negative per-page TEDS diagnostic (-0.036909) while structure-only TEDS is 0.84375.

**Inference, not confirmed:** The discrepancy is consistent with severe cell-content mismatch or a diagnostic/evaluation edge case; no cause is confirmed.

### page-14cd673f-d86d-45a7-a13e-2b4e1d91c08f.png#0

**OBSERVED:** A handwriting/equation-hard page has near-1 text and formula Edit distance in the frozen baseline.

**Inference, not confirmed:** Recognition, formula serialization, annotation semantics, and matching remain competing explanations without a complete artifact-by-artifact adjudication.

## Dominant measured symptoms

The classic frozen metrics show high normalized edit distances for text (0.573988), reading order (0.584992), tables (0.712518), and formulas (0.985389). These are benchmark-protocol mismatches, not causal diagnoses. The available artifacts provide a confirmed empty-output path trace for one page; most ranked pages remain cause-unknown.

Table aggregate TEDS (0.398111) and structure-only TEDS (0.632317) are the evaluator's `all` aggregations. Per-page means (0.413877 and 0.673171) are diagnostics and not interchangeable with these aggregates.

## Limitations

- This is a ranked inspection set, not a blinded or representative sample.
- Most selected cases have metric evidence only; root-cause labels remain UNKNOWN.
- Table TEDS per-page values are diagnostic outputs; official aggregate metrics remain the evaluator's all-table aggregation.
