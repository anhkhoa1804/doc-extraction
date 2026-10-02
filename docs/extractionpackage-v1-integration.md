# Cross-team extraction contract status

## Status: blocked on contract authority

`Document` is the internal canonical representation produced by this
repository. The checkout does not contain a separate cross-team
`DocumentExtractionContract 1.0.0` artifact, nor the previously requested
external `ExtractionPackage v1` KP/CDOI interchange contract. The internal
canonical schema is currently `Document.schema_version == "1.4.0"`; it must
not be relabeled as either external contract.

At the production hardening audit for this checkout, no authoritative
`DocumentExtractionContract 1.0.0` or ExtractionPackage v1 artifact is
available. Consequently, there is no adapter
implementation, public compatibility claim, or field-level mapping in this
repository.

## Evidence checked

The integration audit checked:

* the tracked working tree and `origin/fix/table-text-ownership` for schema,
  OpenAPI, protobuf, TypeScript, Python-model, canonical-example, adapter,
  and `ExtractionPackage`/`CDOI`/`DocumentIR` references;
* every reachable Git revision with a `DocumentExtractionContract`, `ExtractionPackage`,
  `cdoi_doc_extraction_adapter`, or `DocumentIR` string change; and
* the available sibling workspaces and the active project environment for an
  installed or editable KP/CDOI package.

Only the internal `Document` schema and historical research artifacts were
found. No versioned external schema, owner-supplied canonical JSON, validator,
or KP/CDOI consumer entry point was found. This audit therefore cannot freeze
or claim compatibility with `DocumentExtractionContract 1.0.0`; the internal
schema validation hardening described in `output-format.md` is not a
replacement for that authority.

## Required owner-supplied artifacts

Cross-team adapter implementation can begin only after the contract owner
supplies all of the following for one named, versioned contract:

1. The authoritative schema or executable model, including the normative
   version and compatibility policy.
2. Required and optional fields, enum constraints, and omission-versus-null
   semantics.
3. Identifier, locator, ordering, provenance, table/cell, section/block,
   warning/error, and run-status semantics.
4. At least one canonical valid example and a validator or test fixture that
   represents the downstream consumer's expectations.
5. The real KP/CDOI adapter or consumer entry point for a minimal integration
   test.

## Safe boundary already available

The future adapter belongs at the narrow boundary below. It must map from the
internal canonical `Document` only after external semantics are known.

```text
source file -> doc-extraction -> Document -> authoritative external contract -> KP/CDOI
```

`Document` and its canonical serialization are documented in
[`output-format.md`](output-format.md). That documentation is not an
ExtractionPackage specification and must not be treated as one. No adapter
module or placeholder schema is created while this blocker remains unresolved:
doing so would encode unsupported external semantics.

## Failure behavior

There is currently no ExtractionPackage conversion API. Callers needing the
external package must fail integration configuration explicitly rather than
receive a guessed projection. The normal `doc-extraction` CLI and Python API
continue to produce only the documented internal canonical `Document`.
