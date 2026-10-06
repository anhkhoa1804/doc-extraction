# CDOI ExtractionPackage v1 integration status

## Status: specification available; producer and consumer implementation unconfirmed

The authoritative public Extraction ↔ KP/CDOI boundary is
`DocumentExtractionContract` version `1.0.0`, with `ExtractionPackage v1` as
its payload/implementation name. The internal canonical `Document` remains
schema `1.4.0`; it is neither the public contract nor KP's internal
`DocumentIR`.

The specification facts supplied by the CDOI owner are authoritative. The
normative source file/revision and implementation artifacts were not found in
this checkout or the accessible sibling workspace. In particular, no local
ExtractionPackage producer, public validator, `DocumentIR` adapter,
`EvidenceRef` model/resolver, or named
`cdoi_doc_extraction_adapter_v1` implementation was found. Do not infer that
the official contract is undefined; do not claim that this repository has
adopted it.

The package producer and KP consumer must both enforce exact public identity
and fail closed on unsupported versions and unknown fields. The producer must
preserve physical extraction evidence, nulls, explicit producer reading order
and issues. KP must validate, adapt to `DocumentIR`, preserve `EvidenceRef`,
and reject incompatible versions. Fatal producer issues must produce the
official `EXTRACTION_PACKAGE_FAILED` behavior with no successful empty
document. These are adoption requirements, not current API guarantees.

## Evidence and exact gaps

The existing public API is `doc_extraction.cli.process_file(path, config,
output_root=...)`; it returns/writes only canonical `Document`. Internal
`RunStatus.FAILED` is rejected by canonical `Document` validation, and
`process_file` raises on extraction failure while writing failure metadata
where safe. This is a useful producer-side fail-closed foundation, but it is
not the public FATAL/ErrorEnvelope mapping.

Current metadata has filename, full SHA-256, detected file type, route,
pipeline/backend, model versions, timestamp, config and device. It does not
have an explicit `extraction_run_id`, source byte size, guaranteed MIME type,
first-class language hints, or approved `source_document_id`. The local
`document_id` is a filesystem-safe filename stem plus eight hash characters;
it must not be treated as source identity without CDOI confirmation. Element
and table IDs exist, but cells lack IDs, textual source spans are absent, and
no EvidenceRef grammar/resolver exists locally. Warning/error values are
strings, not structured `ContractIssue`/`ErrorEnvelope` instances.

The user-specified `cdoi_doc_extraction_adapter_v1` is a separate
producer-side compatibility adapter for legacy internal Document schemas
1.0.0–1.2.0. It is not the public contract validator and not the KP
`DocumentIR` adapter. Its path/implementation could not be confirmed here;
`schemas/version.py` records internal version history, not that adapter.

Acquisition-owned `source_url`, `final_url`, `acquisition_job_id`,
`artifact_id`, and retrieval timestamps remain outside ExtractionPackage.
No `document_revision_id` is present in official v1. Entity/relation/canonical
entity ontology, KG writes, review decisions, and agent reasoning remain
outside Extraction.

## Adoption path

1. Obtain the authoritative CDOI repo path, immutable spec revision/hash,
   executable model, generated JSON Schema, and shared fixtures.
2. Confirm field/null/ID/locator/error/EvidenceRef semantics using
   [`cdoi-teammate-confirmation-checklist.md`](cdoi-teammate-confirmation-checklist.md).
3. Implement the narrow Extraction producer adapter from canonical Document
   1.4.0; do not relabel the internal schema or alter its semantics to fit the
   external package.
4. Add producer conformance/golden tests, including exact-version and
   unknown-field rejection, warnings, partial/error, FATAL fail-closed,
   null/order preservation, and EvidenceRef targets.
5. Obtain KP's validator/adapter path and run a shared package fixture through
   validation → `DocumentIR` → EvidenceRef source resolution.
6. Claim cross-team adoption only after both repositories provide passing
   test evidence and owners sign off.

See [`contract-adoption-audit.md`](contract-adoption-audit.md) for the full
field mapping and status inventory. Until the producer exists, this API must
not return a guessed package; callers requiring the cross-team contract must
fail integration setup explicitly.
