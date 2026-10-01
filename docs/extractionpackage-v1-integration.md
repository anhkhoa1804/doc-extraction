# ExtractionPackage v1 integration status

## Status: blocked on contract authority

`Document` is the internal canonical representation produced by this
repository. `ExtractionPackage v1` is an external KP/CDOI interchange
contract. This repository intentionally does not define, emulate, or infer
that contract.

As of production baseline `ad15d78e4af2409fc63ca108be7104dee75db2eb`, no
authoritative ExtractionPackage v1 artifact is available to this checkout.
Consequently, there is no adapter implementation, public compatibility claim,
or field-level mapping in this repository.

## Evidence checked

The integration audit checked:

* the tracked working tree and `origin/fix/table-text-ownership` for schema,
  OpenAPI, protobuf, TypeScript, Python-model, canonical-example, adapter,
  and `ExtractionPackage`/`CDOI`/`DocumentIR` references;
* every reachable Git revision with an `ExtractionPackage`,
  `cdoi_doc_extraction_adapter`, or `DocumentIR` string change; and
* the available sibling workspaces and the active project environment for an
  installed or editable KP/CDOI package.

Only the internal `Document` schema and historical research artifacts were
found. The two production-boundary documents that mention ExtractionPackage
explicitly state that an authoritative contract is absent. No versioned
external schema, owner-supplied canonical JSON, validator, or consumer entry
point was found.

## Required owner-supplied artifacts

Implementation can begin only after KP/CDOI supplies all of the following for
one named, versioned contract:

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
source file -> doc-extraction -> Document -> ExtractionPackage v1 -> KP/CDOI
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
