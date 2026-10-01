# 042 role-normalization routing design

This module is offline and routing-only. It must not invoke TableTransformer,
read GT, inspect treatment output, or create table evidence.

The source audit found that `DoclingBackend.analyze` emits a lower-cased
Docling label as `Region.label`, while the production table gate consumes
`region.label.lower() == "table"`. Telemetry's `normalized_role` is the same
lower-casing convention, not an independent semantic ontology.

Frozen transparent hypotheses:

```text
document_index -> table
text          -> unchanged
picture       -> unchanged
code          -> unchanged
list_item     -> unchanged
```

For every development baseline case, compare current raw-label routing with a
hypothetical gate consuming the proposed normalized role. Emit exactly one of
`INVOCATION_CHANGED`, `INVOCATION_UNCHANGED`, `ROUTE_ERROR`, or
`PROTOCOL_ERROR`. Routing change does not imply table recovery or evidence
improvement.

The phrase `wrong-role ownership -> table` is not an executable mapping: it
requires GT or post-treatment ownership information and is therefore not a
valid pre-treatment rule.
