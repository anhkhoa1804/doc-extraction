# CDOI / KP contract readiness handoff

## Current conclusion

**SPECIFICATION AVAILABLE; IMPLEMENTATION UNCONFIRMED.** The authoritative public boundary is `DocumentExtractionContract` 1.0.0, with `ExtractionPackage v1` as its payload/implementation name. This checkout currently emits internal `Document` 1.4.0 and has no evidenced ExtractionPackage producer or KP consumer implementation. Do not report full adoption.

Evidence classifications in this handoff use exactly:

```text
CONFIRMED_LOCAL
CONFIRMED_FROM_OFFICIAL_SPEC
NOT_FOUND_LOCALLY
REQUIRES_TEAMMATE_CONFIRMATION
NOT_APPLICABLE
```

The normative specification facts below are those supplied by the CDOI owner. The specification's immutable repository path/revision and implementation source files were not found in this checkout or searched sibling repositories. “Not found locally” is scoped to that search; it does not deny external ownership or implementation.

## A. Proven locally

| Fact | Classification | Evidence / limit |
| --- | --- | --- |
| Current public entry point returns/writes internal canonical `Document` 1.4.0, not a demonstrated package | `CONFIRMED_LOCAL` | `src/doc_extraction/cli.py`, `schemas/document.py`, `schemas/version.py`, `docs/public-api.md` |
| Internal metadata has `input_filename`, full `file_hash_sha256`, detected `file_type`, route/backend, timestamp, config/model/device, warning/error string arrays and status | `CONFIRMED_LOCAL` | `RunMetadata` in `src/doc_extraction/schemas/document.py`; `process_file()` |
| `document_id` is a local output key formed from slugified filename stem plus first eight SHA-256 characters | `CONFIRMED_LOCAL` | `src/doc_extraction/utils/ids.py`; not an approved source ID |
| Pages carry element/table lists and explicit `reading_order`; element/table bboxes may be null and coordinate origin/unit are declared | `CONFIRMED_LOCAL` | `schemas/page.py`, `element.py`, `table.py`; not proof of public mapping |
| Element IDs and table IDs exist; cell row/column/span data exists, but `Cell` has no ID and `Cell.text` is non-nullable | `CONFIRMED_LOCAL` | `schemas/element.py`, `schemas/table.py` |
| Internal `Document` rejects `RunStatus.FAILED`; `process_file` raises on failure and records failure metadata where safe | `CONFIRMED_LOCAL` | `schemas/document.py`, `cli.py`; not official FATAL conformance |
| Acquisition has separate `Artifact`, `Resource`, `CrawlJob`; the integration seam calls the public extraction API | `CONFIRMED_LOCAL` | `services/web-acquisition/src/web_acquisition/models.py`, `integration.py` |
| Frozen Classic and E2E evidence remains unchanged | `CONFIRMED_LOCAL` | Phase 1 report and companion summary; no benchmark was run for this handoff |

## B. Proven by the official specification facts

| Contract fact | Classification |
| --- | --- |
| Public identity is exactly `DocumentExtractionContract` version `1.0.0`; payload/implementation name is `ExtractionPackage v1` | `CONFIRMED_FROM_OFFICIAL_SPEC` |
| Internal Extraction `Document 1.4.0`, public contract package, and KP internal `DocumentIR` are distinct layers | `CONFIRMED_FROM_OFFICIAL_SPEC` |
| Unsupported public versions fail closed; unknown fields are rejected; consumer version guessing is disallowed | `CONFIRMED_FROM_OFFICIAL_SPEC` |
| Extraction owns physical OCR/layout/locations/tables/cells/reading order/provenance/issues; KP preserves physical evidence | `CONFIRMED_FROM_OFFICIAL_SPEC` |
| Null remains null; explicit producer `reading_order` is authoritative; warnings and non-fatal errors remain visible | `CONFIRMED_FROM_OFFICIAL_SPEC` |
| FATAL fails closed as `EXTRACTION_PACKAGE_FAILED`; it cannot become a successful empty document or fabricated semantic preview | `CONFIRMED_FROM_OFFICIAL_SPEC` |
| KP validates the package, adapts to `DocumentIR`, preserves `EvidenceRef`, and rejects incompatible versions | `CONFIRMED_FROM_OFFICIAL_SPEC` |
| v1 excludes `document_revision_id`; source URL/final URL, acquisition job/artifact IDs and retrieval timestamps remain Acquisition-owned | `CONFIRMED_FROM_OFFICIAL_SPEC` |

These are requirements, not evidence that either repository implements them.

## C. Identity and physical-evidence gaps

| Identity/evidence concept | Current fact | Classification / gap |
| --- | --- | --- |
| Source identity (`source_document_id`) | Local `document_id` is a short-hash output directory key; full source SHA-256 exists separately | `REQUIRES_TEAMMATE_CONFIRMATION`: source-ID namespace, scope, derivation and relationship to Acquisition identity must be specified; do not equate the local key with it |
| Extraction-run identity (`extraction_run_id`) | No explicit run ID in canonical `Document`/`RunMetadata`; timestamp is present | `NOT_FOUND_LOCALLY`: owner must provide run-ID generation/uniqueness semantics |
| Source identity fields | Filename and full SHA-256 exist; guaranteed MIME and source byte size are absent from canonical metadata | `REQUIRES_TEAMMATE_CONFIRMATION`: exact MIME/hash/size sources and wire meanings; implement after ownership agreement |
| Physical element/table identity | Local IDs and table references exist; scope/stability across runs is not established | `REQUIRES_TEAMMATE_CONFIRMATION`: contract ID scope and stability tests |
| Physical cell identity | Cells have no explicit ID; row/column locators exist | `REQUIRES_TEAMMATE_CONFIRMATION`: normative stable cell-ID rule; do not invent a composite EvidenceRef |
| Future EvidenceRef identity/resolution | No EvidenceRef type, resolver or KP test locally | `NOT_FOUND_LOCALLY`: KP path, grammar, source check, target resolution and tests required |
| Physical provenance | Backend/source identifiers, page positions, optional geometry and source SHA exist internally | `REQUIRES_TEAMMATE_CONFIRMATION`: package projection and KP preservation are unproven |
| `document_revision_id` | Excluded by official v1 facts | `NOT_APPLICABLE` |
| Acquisition identity/operations | `source_url`, `final_url`, `acquisition_job_id`, `artifact_id`, retrieval timestamps are separately owned | `CONFIRMED_FROM_OFFICIAL_SPEC`: keep outside ExtractionPackage; confirm seam behavior, do not relocate them |

## D. Failure semantics evidence

| Layer/event | Current evidence | Classification |
| --- | --- | --- |
| Internal extraction failure | Internal status `failed` cannot be published as canonical Document; public call raises | `CONFIRMED_LOCAL` |
| Item warning/non-fatal error | Internal warning/error strings and `success_with_warnings` status exist | `CONFIRMED_LOCAL`; public `ContractIssue` mapping is not proven |
| This checkout has no public FATAL → `EXTRACTION_PACKAGE_FAILED` producer mapping or conformance test | Local search found no package producer/envelope mapping or executable contract test | `NOT_FOUND_LOCALLY` |
| The official producer/KP implementation must prove FATAL → `EXTRACTION_PACKAGE_FAILED` end-to-end | This is required by the official specification; owning paths and test evidence are outstanding | `REQUIRES_TEAMMATE_CONFIRMATION` |
| Package rejection | No local public package validator/producer boundary | `NOT_FOUND_LOCALLY` |
| KP-side rejection | No KP validator/adapter available in the searched workspace | `NOT_FOUND_LOCALLY`; teammate must supply path and tests |

Internal fail-closed behavior does **not** prove the public FATAL contract.

## E. Exact teammate questions

Answer each with **YES / NO / PATH / REVISION / VERSION / TEST EVIDENCE**. Identify the owning repository and immutable revision; do not answer only “integration works.”

1. What is the normative contract repository, file path, immutable revision, and integrity hash?
2. What is the authoritative JSON Schema path, version, and generator path/command?
3. What exact path/revision implements the ExtractionPackage v1 producer?
4. Where is `cdoi_doc_extraction_adapter_v1`, who owns it, and does it adapt only internal schemas 1.0.0–1.2.0 before public package production?
5. What exact path/revision implements the KP package validator?
6. What exact path/revision implements the KP `DocumentIR` adapter?
7. Where is EvidenceRef defined and resolved; what tests prove element/table/cell references resolve to their source evidence?
8. What are the normative source-document and extraction-run identity scopes, generation rules, and stability guarantees? Is the current local short-hash key explicitly rejected as a source ID?
9. What are the exact `source_name`, MIME, hash algorithm/encoding, and byte-size semantics, and which system supplies each value?
10. What normative rule defines stable element, table, and cell IDs and their scope?
11. What does null versus empty mean for element text, cell text, geometry, locations, and spans?
12. What are the exact structured warning/error fields and mappings for `ContractIssue` / `ErrorEnvelope`, including severity, code, retryability, detail, run ID and context/location?
13. What test proves exact supported-version acceptance and unsupported-version fail-closed behavior, with no version guessing?
14. What test proves unknown-field rejection, including strict primitive-only metadata maps?
15. What producer and KP tests prove FATAL becomes `EXTRACTION_PACKAGE_FAILED` and never a successful/empty package or `DocumentIR`?
16. What tests prove KP preserves physical evidence, nulls, explicit reading order, issues and EvidenceRef through adaptation?
17. Does Acquisition retain ownership of URLs, job/artifact IDs and retrieval timestamps, and what seam test proves only agreed source provenance crosses into Extraction?
18. Which public Extraction contract versions are currently accepted? Confirm whether v1.0.0 is the only accepted version today.

The longer conformance checklist is in [`cdoi-teammate-confirmation-checklist.md`](cdoi-teammate-confirmation-checklist.md). The field-by-field local mapping is in [`contract-adoption-audit.md`](contract-adoption-audit.md).

## F. Strict adoption gate

Phase 1 may claim **“CDOI/KP contract adoption confirmed”** only after the normative specification/schema paths and revisions are pinned; the producer, legacy compatibility adapter, KP validator, `DocumentIR` adapter and EvidenceRef resolver are identified; mappings and ownership are agreed; and shared conformance evidence proves exact-version and unknown-field rejection, null/order/evidence preservation, structured issue handling, and FATAL fail-closed behavior across both repositories.

Until every required item is evidenced and internally consistent, the status remains:

**CROSS-TEAM CONTRACT CONFIRMATION REQUIRED**
