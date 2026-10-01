# 045 — acquisition-time capture protocol v1

## Question

Does direct capture before canonical page projection expose truth-supported,
correctly owned textual evidence absent from A's canonical output?

## Population

Use 044 protocol-v2's ten frozen development cases unchanged: `d2-00` …
`d2-07`, `ctl-00`, `ctl-01`. No held-out data is accessed.

## Conditions

A calls the current `run_scanned_page_pipeline` without a ledger. B makes the
same call with `ObservationLedger`. B capture occurs after component backend
return and before `_fill_table_cell_text` and `merge_regions_into_page`. B is
observational: it neither changes a result object nor invokes recovery.

## Truth and endpoints

The frozen 044 normalized-exact OmniDocBench HTML-cell truth and
locator-scoped baseline phrase rule are reused unchanged. Novel-correct means
text-bearing + cell-exact correct + ownership-valid + provenance reaching an
acquisition observation + absent from A at the same GT table locator.

## Loss taxonomy

For an acquisition token: `normalization` means a normalized canonical phrase
exists but the raw phrase does not; `ownership` means no canonical phrase and
the reconciliation view has competing claims; `canonical_projection` means
no canonical phrase without a competing claim; `serialization` means a
canonical exact phrase exists but Markdown omits it. `acquisition` can only
be assigned where a requested raw observation was not captured; this run
records such absence explicitly rather than inventing it. `reconciliation`
and `unknown` remain zero unless direct evidence establishes them.

## Decision

At least one direct-acquisition, truth-correct, baseline-missing,
ownership-valid, provenance-complete observation plus zero control novelty is
required for `ACQUISITION-TIME PRESERVATION SUPPORTED FOR NEXT STAGE`.
Otherwise, added distinctions without this endpoint yield
`OBSERVABILITY ONLY; ACQUISITION-TIME QUALITY BENEFIT UNPROVEN`.
