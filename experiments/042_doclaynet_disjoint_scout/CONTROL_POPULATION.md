# 042 natural control population

This artifact is intentionally pending baseline scouting. The control
population cannot be declared from source annotations or treatment output.

## Frozen admission rule

After an unchanged development-only baseline run, retain every naturally
emitted region whose raw role is exactly `document_index` as a candidate,
along with its source identity, page, bbox, layout/OCR features, and baseline
telemetry. No candidate is selected using GT geometry or treatment outcome.
Do not relabel another raw role as `document_index`.

The D2-like classification is attached after baseline output as an analytical
field. It is not a runtime selector feature. Regions matching a frozen 039 D2
identity are never admitted to the new control population.

## Required adequacy

The final control population should have at least 30 natural regions,
preferably 50, from at least five independent source-document groups and at
least three categories where naturally available. All pages in a source group
remain in the same 042 development partition. Group concentration and page
concentration are reported explicitly.

If the scout produces zero controls, the frozen terminal status is
`BLOCKED_NO_ADEQUATE_DOCUMENT_INDEX_CONTROL_POPULATION`. If controls exist but
independence is inadequate, use `BLOCKED_INSUFFICIENT_INDEPENDENCE`.

## Current status

No baseline scout has run. No control count is imputed and no treatment is
authorized.
