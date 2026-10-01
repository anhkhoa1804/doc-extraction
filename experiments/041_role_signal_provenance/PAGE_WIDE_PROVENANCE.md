# Module B — page-wide provenance contract

This module is a no-treatment observational replay. It is not a D2
counterfactual and does not infer invocation mode from final output.

## Frozen population rule

Select only 039 records with `split == "development"`, deterministically from
the frozen 039 manifest and baseline layout metadata. Include, where present:

* all known development D2 pages or a deterministic complete D2-page stratum;
* non-D2 table pages;
* non-table control pages;
* ambiguous/high-density layout pages;
* at least one page with a baseline table-labelled region and one page without
  one, so the actual telemetry can test both routing modes.

The D2 page identity is frozen from the 039 forensic artifact before replay;
it is not recomputed from replay output. No held-out page may enter the sample.

## Required per-page result

Record:

* image and source hashes, group, category, split, and role distribution;
* `PAGE_WIDE`, `LABELLED_CROP`, `NOT_INVOKED` counts;
* whether page-wide, labelled-crop, both, or neither occurred;
* all specialist call records, detector boxes/scores, structure output,
  ownership events, warnings/errors, and timings;
* baseline final table count, ownership state, reading order, and serialized
  evidence hash.

The replay must use the validated additive `TableTelemetryRecorder`, the
unchanged production pipeline, CPU device, and `configs/cpu.yaml`. It must
write to an isolated 041 output root and never overwrite 039 or 040 results.

## Current status

The Module A hard stop was encountered before this replay. Consequently there
are no 041 provenance results and no empirical page-wide distribution in this
checkpoint. The unresolved interpretation from 039 remains unresolved:
`D2` does not prove page-wide specialist absence.
