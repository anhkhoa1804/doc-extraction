# CDOI / KP teammate confirmation checklist

Please answer each item with **YES / NO / PATH / VERSION / TEST EVIDENCE** as applicable. “Integration works” is not sufficient; each answer should identify the owning repository and exact implementation/test location. This checklist records confirmations; it does not define contract semantics.

## Official contract source and version

- [ ] What is the authoritative CDOI repository and immutable commit/tag for `DocumentExtractionContract 1.0.0` / `ExtractionPackage v1`? Provide repository URL/path, revision, and SHA-256 (or equivalent integrity identity) of the normative specification.
- [ ] Is `src/cdoi/cross_team_contracts.py` the authoritative executable definition? Provide exact path/revision or identify the replacement.
- [ ] Is `src/cdoi/contracts.py` the authoritative package/issue implementation? Provide exact path/revision or identify the replacement.
- [ ] Is `docs/cdoi_document_extraction_contract_v1.schema.json` the generated normative JSON Schema? Provide exact path/revision and the command/source used to generate it.
- [ ] Is `tools/export_cross_team_schemas.py` the canonical generator? Provide exact path/revision or the replacement.
- [ ] Confirm the public identity is exactly `contract_name=DocumentExtractionContract`, `contract_version=1.0.0`, with `ExtractionPackage v1` as the payload/implementation name. Is 1.0.0 the only currently accepted public Extraction contract? Provide validator/version tests.
- [ ] Confirm unknown fields are rejected and unsupported `(contract_name, contract_version)` pairs fail closed without version guessing. Provide test paths and test names.

## Producer-side Extraction implementation

- [ ] What is the ExtractionPackage v1 producer entry point and owning repository/path? Provide the function/API, version, and a valid serialized package fixture.
- [ ] Is `cdoi_doc_extraction_adapter_v1` implemented? Provide exact path/revision and tests. Confirm it only adapts legacy **internal** Document schemas 1.0.0, 1.1.0, and 1.2.0, and is not the public KP adapter or a change to the public contract version.
- [ ] What exact mapping produces `extraction_run_id` and `source_document_id`? State owner, uniqueness/scope, stability, and test evidence. Confirm `document_revision_id` is not part of v1.
- [ ] Which source field supplies `source_name`, `source_mime_type`, optional `source_hash`, and `source_size_bytes`? State hash algorithm/encoding and how source size/MIME cross from Acquisition without moving Acquisition ownership.
- [ ] Which exact backend provenance, `extracted_at`, language-hint, and provenance fields are emitted? Identify the allowed primitive metadata types and tests proving no paths/secrets/arbitrary objects leak.
- [ ] How are internal pages/elements/tables/cells/sections mapped? Provide official handling for optional geometry, null text/geometry, source spans, coordinate units/origin, table spans, stable ID scope, and explicit producer `reading_order`.
- [ ] How are stable cell IDs produced or resolved? If IDs derive from composite locators, cite the normative contract rule and EvidenceRef tests; do not assume `table + row + column` is sufficient.
- [ ] How are warnings and non-fatal errors represented as `ContractIssue`? Provide exact `severity`, `error_code`, `retryable`, `detail`, `run_id`, context/location mapping and tests. Distinguish internal `RunStatus` from public issue semantics.
- [ ] What exact producer behavior maps a fatal extraction issue to `EXTRACTION_PACKAGE_FAILED`? Confirm no package/document is emitted as success and no empty document is fabricated. Provide failure-path tests.
- [ ] Provide producer conformance tests for valid success, warning, partial/error, FATAL, empty document, multiple pages, null geometry/text, tables/cells, reading order, provenance, malformed fields, unknown fields, unsupported versions, and missing/invalid evidence references.

## KP consumer and `DocumentIR` adapter

- [ ] What KP repository/path/version contains the ExtractionPackage validator and adapter into internal `DocumentIR`? Identify each separately if they are in different modules.
- [ ] Does KP validate the exact contract name/version before adaptation and reject unknown fields/versions? Provide test paths and test names.
- [ ] Does the adapter preserve physical text, nulls, page/element/table/cell locations, spans, explicit producer reading order, provenance, warnings and non-fatal errors without rewriting physical extraction evidence? Provide round-trip/adapter tests.
- [ ] What is KP's normative `EvidenceRef` model and resolver? Provide exact reference grammar, allowed target IDs/locators, source-identity checks, and tests resolving elements, tables and cells back to the source evidence.
- [ ] Does KP reject `EXTRACTION_PACKAGE_FAILED` and any FATAL issue without creating a successful/empty `DocumentIR` or semantic preview? Provide tests.
- [ ] Confirm semantic ontology, entity/relation candidates, canonical entities, governance/review decisions and KG writes remain KP-owned, not part of ExtractionPackage production.

## Acquisition ownership boundary

- [ ] Confirm `source_url`, `final_url`, `acquisition_job_id`, `artifact_id`, and retrieval timestamps remain Acquisition-owned and are not added to the public Extraction contract.
- [ ] Which Acquisition-provided source facts (if any) are passed to Extraction for the official source provenance fields? Identify the seam path and tests for identity/hash/MIME/size consistency.
- [ ] Confirm HTML/text acquisition does not imply Extraction support for that media type; identify the explicit unsupported-format failure test at the seam.

## Joint adoption gate

- [ ] Provide a shared valid package fixture consumed by both Extraction producer tests and KP validator tests, pinned to contract 1.0.0.
- [ ] Provide shared invalid fixtures proving unknown-field rejection, unsupported-version rejection, malformed issues, FATAL fail-closed behavior, null preservation, and unresolved EvidenceRef rejection.
- [ ] Identify a minimal integration test that runs Extraction producer → KP validator → `DocumentIR` adapter → EvidenceRef resolution against one source artifact, with exact repository paths and expected result.
- [ ] State the responsible owner and acceptance sign-off for each unresolved item above. Until these are evidenced, cross-team contract adoption remains unconfirmed.
