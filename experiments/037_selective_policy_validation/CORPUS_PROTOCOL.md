# 037 corpus protocol

## Purpose and independence

037 tests whether a selector can safely admit blocked table regions before a
same-crop Table Transformer counterfactual.  It does not reuse the 34 D2
treatments or 145 controls from 036 for development or headline evaluation.
The source is the repository's independently generated enterprise corpus
(`research/production_corpus/corpus/manifest.json`, generator seed
`20260902`).  Each `document_id` is a source-document group; a group is never
split across development and held-out test.

This is a *synthetic* EN/VI corpus.  It provides controlled coverage and true
source geometry, not a prevalence estimate for external documents.  Any
positive result therefore requires a later real-corpus replication.

## Inclusion

The population is all one-page PDF source documents in the production-corpus
manifest with `expected_tables == 1` and a searchable source PDF text layer.
The searchable-text requirement permits a source-derived geometric table
annotation without consulting any extraction-model output.  Documents whose
source PDF has been rasterized are excluded, because this committed corpus has
no separate geometric annotation for them.  Non-table controls are selected
from the same frozen pages after baseline layout: one largest non-table layout
region whose IoU with every source table box is zero, or an explicit
``no_eligible_control`` exclusion.

## Ground truth and coordinate contract

Each PDF is rendered once at 200 DPI to an isolated experimental PNG input.
The source table rectangle is recovered from the generator's fixed table
content in the *source PDF*: the union of exact table-token word boxes is
expanded only to the enclosing generator primitive boundary (the fixed
`_draw_table` x=60 and documented style widths/row heights), then transformed
by the recorded render scale.  This source-only procedure is implemented in
`build_population.py`; it never reads layout, OCR, detector, structure, or
ownership output.  The manifest records source and rendered image hashes.

## Split

`SHA256("037-split-v1:" + document_id)` ranks the included document IDs.
The first half is development and the remainder held-out test.  This is fixed
before baseline candidate matching and before every counterfactual invocation.
No substitution, balancing, or post-outcome reassignment is permitted.

## Exclusions and activation

The corpus has 15 eligible source documents.  This is deliberately described
as a small-sample validation, not a power claim.  If baseline discovery yields
zero strict-D2 candidates in either split, 037 cannot estimate selector recall
for that split; it must report `NO_TRIGGERED_D2_CASES`, not treat ordinary
table success as a substitute.
