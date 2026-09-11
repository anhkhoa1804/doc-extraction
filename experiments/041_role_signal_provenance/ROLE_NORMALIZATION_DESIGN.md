# Module C — role-normalization falsification

## Layer separation

The analysis keeps these layers distinct:

```text
raw role / proposed normalized role
        -> routing gate
        -> specialist invocation mode
        -> ownership and serialized evidence
```

Module C stops after the routing layer. It does not run a specialist and does
not claim a recovery.

## Current implementation

`DoclingBackend.analyze` emits the lower-cased Docling layout label as the
`Region.label`. Telemetry records the same lower-cased value as
`normalized_role`; this is not an independent semantic ontology. The
production gate in `run_scanned_page_pipeline` filters table regions with
`region.label.lower() == "table"`. The TableTransformer backend then uses
`LABELLED_CROP` when supplied table boxes and `PAGE_WIDE` when none are
supplied.

## Frozen hypotheses

* H1: `document_index -> table` is a transparent routing hypothesis.
* H2: `text`, `picture`, `code`, and `list_item` remain unchanged negative
  roles; no universal non-table mapping is allowed.
* H3: “wrong-role ownership -> table” is not an executable pre-treatment
  mapping because the phrase requires GT or post-treatment ownership to
  identify it.

## Frozen routing outcomes

For each development-only case, compare raw production routing with a pure
hypothetical gate consuming the proposed normalized role. Emit exactly one of:

* `INVOCATION_CHANGED`
* `INVOCATION_UNCHANGED`
* `ROUTE_ERROR`
* `PROTOCOL_ERROR`

The result must state whether the current implementation actually consumes
the proposed normalized role. A predicted `LABELLED_CROP` route is not table
evidence and is not a valid recovery.

## Current status

The contract is frozen, but Module C was not executed because the Module A
same-role-control hard stop prevents Experiment 041 execution from advancing.
