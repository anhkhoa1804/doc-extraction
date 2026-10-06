# CDOI DocumentExtractionContract adoption audit

## Finding

The authoritative public boundary is **CDOI `DocumentExtractionContract` 1.0.0**, whose implementation/payload name is **ExtractionPackage v1**. It is distinct from internal Extraction `Document` schema 1.4.0 and KP's internal `DocumentIR`.

**Adoption status: SPECIFICATION AVAILABLE; IMPLEMENTATION UNCONFIRMED.** The official specification and facts are authoritative for this audit, as supplied by the CDOI owner. The actual specification file/repository revision was not reachable in this checkout or accessible sibling workspace, so this audit does not claim to have independently validated the complete schema, generated schema, or executable validator. The named paths below were searched for and not found locally:

```text
src/cdoi/cross_team_contracts.py
src/cdoi/contracts.py
docs/cdoi_document_extraction_contract_v1.schema.json
tools/export_cross_team_schemas.py
```

No ExtractionPackage producer, KP adapter, `DocumentIR`, `EvidenceRef`, `ContractIssue`, or `cdoi_doc_extraction_adapter_v1` implementation was found in the inspected checkout/accessibly searched sibling workspace. This is evidence of **not found here**, not evidence that the official contract is undefined.

The producer must emit exactly `contract_name=DocumentExtractionContract` and `contract_version=1.0.0`. Unsupported versions and unknown fields fail closed. No consumer-side version guessing is allowed. Internal `Document.schema_version=1.4.0` must not be exposed as the public interchange version. Official v1 does not contain `document_revision_id`; this audit proposes no such field.

## Contract inventory

| Contract area | Official requirement | Current doc-extraction state | Gap | Owner | Evidence | Status |
| --- | --- | --- | --- | --- | --- | --- |
| Public identity/version | Exact contract name/version; package name ExtractionPackage v1 | Internal `schema_version=1.4.0`; no public package producer | Public envelope and exact-version validator absent | Extraction producer; CDOI owns schema | `schemas/document.py`, `schemas/version.py`; no package code found | MISSING |
| Unknown fields/version | Reject unknown fields and unsupported versions; no guessing | Internal Pydantic models generally use `extra="forbid"`; not a public-package validator | Contract-specific validator and tests absent | Extraction; KP independently validates | Internal models only | PARTIAL |
| Source identity | `source_name`, MIME, optional hash, size; `source_document_id` | `input_filename`, full SHA-256 and local document key exist; no canonical MIME, byte-size, or explicit source-document identity field | Mapping and size propagation need confirmation/implementation | Extraction + Acquisition metadata; CDOI defines meaning | `RunMetadata`, `utils/ids.py`, Acquisition models | PARTIAL |
| Run identity/provenance | `extraction_run_id`, backend, `extracted_at`, language hints, provenance | Timestamp, route/backend, model versions, config/device exist; no explicit run ID or first-class language hint | Run-ID ownership and safe projection undefined | Extraction producer | `RunMetadata`, `process_file()` | PARTIAL |
| Physical sections | Sections are part of public physical structure | No canonical section model; pages contain elements/tables | Official optionality/derivation and lossless mapping must be confirmed | CDOI + Extraction | `schemas/page.py`; no section schema | UNKNOWN |
| Elements/locations | Stable IDs, text/nulls, locations, coordinates/spans, optional geometry, source spans | Element IDs/type/text/bbox/page/source/order/parent/level; no explicit source offsets | Stable-ID scope and source-span mapping absent | Extraction; CDOI defines locator rules | `schemas/element.py` | PARTIAL |
| Tables/cells | Stable IDs, locations and spans | Table IDs, dimensions, bbox; cells have row/column/spans/bbox/text/header, but no ID; cell text is non-null `str` default `""` | Cell ID and empty-versus-unknown/null semantics need mapping | Extraction; CDOI defines identity/null rules | `schemas/table.py` | PARTIAL |
| Reading order | Explicit producer order is authoritative | `Page.reading_order` is an explicit element-ID sequence; model permits incomplete order | Preserve exact sequence; clarify official handling of incomplete order | Extraction; KP must preserve | `schemas/page.py`, conformance helper | PARTIAL |
| Issues/errors | Official `ContractIssue`; warnings/nonfatal errors remain visible | Internal status plus warning/error string lists; no `ContractIssue` or `ErrorEnvelope` | Severity/code/retryability/detail/context mapping absent | Extraction + CDOI; KP preserves | `RunMetadata`, `RunStatus` | PARTIAL |
| FATAL | Fail closed as `EXTRACTION_PACKAGE_FAILED`; no successful empty package | Internal FAILED cannot instantiate canonical `Document`; `process_file` raises and writes failure metadata where safe | Package failure envelope and KP rejection tests absent | Extraction producer + KP consumer | `Document` validator, `cli.process_file` | PARTIAL |
| EvidenceRef | Stable IDs + source identity/provenance resolve physical evidence; KP preserves refs | Element/table local IDs and page/bbox; no cell IDs, EvidenceRef model or resolver | Official reference syntax and end-to-end source resolution absent | Joint Extraction/KP; CDOI specifies | No local implementation found | EXTERNAL DEPENDENCY |
| Producer compatibility adapter | `cdoi_doc_extraction_adapter_v1` for legacy internal schemas 1.0.0–1.2.0; distinct from public/KP adapters | Named implementation not found locally; current runtime schema is 1.4.0 | Confirm path/owner and how legacy data is adapted before package emission | Extraction/CDOI teammate | `git grep`; `schemas/version.py` | UNKNOWN |
| Acquisition boundary | URLs/job/artifact/retrieval timestamps remain Acquisition-owned | Separate Artifact/Resource/CrawlJob; seam calls public `process_file` | Confirm which Acquisition-supplied MIME/hash/size enter producer; keep URL/job fields out of contract | Acquisition + Extraction | `services/web-acquisition/.../integration.py` | PARTIAL |
| KP adapter / DocumentIR | KP validates, adapts to `DocumentIR`, preserves EvidenceRef and rejects incompatible versions | No KP implementation or `DocumentIR` found in accessible workspace | Teammate must provide implementation path and test evidence | KP | Bounded workspace search | EXTERNAL DEPENDENCY |

Statuses refer to evidence in this repository/workspace, not the authority or existence of the CDOI specification supplied for this audit.

## Field-level mapping: internal Document 1.4.0 → public package

This is a mapping inventory, not a schema proposal. A candidate source does not establish semantic equivalence until confirmed by the contract owner.

| Official field/area | Official presence/nullability | Current source | Transform / lossless? | Owner | Status |
| --- | --- | --- | --- | --- | --- |
| `contract_name` | Exact identity required; non-null | None | Emit literal official value; lossless once producer exists | Extraction producer | MISSING |
| `contract_version` | Exact `1.0.0`; non-null | Internal `schema_version=1.4.0` is a different version space | Emit literal `1.0.0`; never copy internal version | Extraction producer | MISSING |
| `extraction_run_id` | Identity field; exact nullability/format to confirm against schema | None | Must create with owner-approved scope; timestamp is not interchangeable | Extraction producer | MISSING |
| `source_document_id` | Identity field; exact nullability/format to confirm | Local `document_id` = slugified stem + first 8 SHA-256 hex chars | Not lossless as an asserted source ID; short digest/local output key can collide | Acquisition provides identity if defined; Extraction passes through | UNKNOWN |
| `source_name` | Source provenance; exact nullability/normalization to confirm | `RunMetadata.input_filename` | Candidate direct mapping after normalization rules confirmed | Acquisition/Extraction | PARTIAL |
| `source_mime_type` | Source provenance; exact nullability to confirm | `file_type`, transient `FileInfo.mime_guess` | Not lossless: `file_type` can be `pdf`; MIME is not retained authoritatively | Acquisition supplies media type; Extraction carries it | MISSING |
| `source_hash` | Optional per official facts | `RunMetadata.file_hash_sha256` | Candidate direct SHA-256; confirm official algorithm/encoding | Extraction computes; Acquisition hash may be compared | PARTIAL |
| `source_size_bytes` | Source provenance; exact nullability to confirm | None in canonical metadata | Must carry exact byte count; keep source ownership at Acquisition where applicable | Acquisition/Extraction | MISSING |
| Backend provenance | Backend fields required; exact shape/nullability from official schema | `route`, `pipeline`, `backend`, page source fields, versions/config/device | Allowlisted transform needed; arbitrary `config_snapshot` is not safe/lossless strict metadata | Extraction producer | PARTIAL |
| `extracted_at` | Extraction provenance; exact nullability/temporal meaning to confirm | `RunMetadata.timestamp` ISO UTC, set before assembly | Candidate mapping but start/completion semantics may differ | Extraction producer | PARTIAL |
| Language hints | Extraction provenance; exact nullability to confirm | May be nested in `config_snapshot`; not a guaranteed field | Extract only validated language codes; may be absent | Extraction producer | PARTIAL |
| `provenance` | Structured provenance; exact schema/nullability to confirm | Run/page/backend/source IDs | Must transform; direct arbitrary map pass-through is not lossless or strict | Extraction producer | PARTIAL |
| `sections` | Required/optional and nullable shape not independently checked from schema file | No internal section collection | No lossless mapping established; do not synthesize sections | CDOI defines shape; Extraction maps | UNKNOWN |
| `elements` | Physical structure; exact nested requiredness from schema file | `Page.elements` | Map/whitelist by official element schema; `extra: Any` cannot pass through | Extraction producer | PARTIAL |
| Text/null | Null must remain null where unknown; nested exact optionality to confirm | `Element.text: str\|None`; `Cell.text: str = ""` | Element null can survive; cell model cannot distinguish unknown from empty | Extraction producer | PARTIAL |
| Locations/coordinates | Geometry optional per official facts; exact locator nullability/units to confirm | Page index, optional bbox, coordinate origin/unit | Can retain null bbox; coordinate/index conversion needs official locator rules | Extraction producer | PARTIAL |
| Coordinates/spans/source spans | Physical coordinates/spans required as defined; source-span nullability to confirm | BBox, table row/column spans; no textual offsets | Physical geometry/table spans exist; textual source spans unavailable | Extraction producer | PARTIAL |
| `tables` / `cells` | Physical table structure; stable IDs; exact optional fields to confirm | `Page.tables`, IDs, cells/row/column/spans; Cell has no ID | Table mapping possible; cell ID and stable scope absent; no fabricated IDs absent official rule | Extraction producer | PARTIAL |
| `reading_order` | Explicit producer order authoritative; exact completeness/nullability rules to confirm | `Page.reading_order` explicit list | Preserve exact sequence, not storage order; incomplete sequence remains an open conformance rule | Extraction producer; KP preserves | PARTIAL |
| Warnings/errors / `ContractIssue` | Structured issues required; severity/code/retryable/detail/run/context per official facts | `RunMetadata.warnings/errors: list[str]`, `RunStatus` | Not lossless: strings lack structured fields; official mappings need confirmation | Extraction producer; KP preserves | PARTIAL |
| Strict metadata maps | Primitive-only and strict; exact optionality per field | `config_snapshot`, `text_profile`, `resource_violation`, `Element.extra` | Direct pass-through unsafe: several use `Any`; build explicit allowlist | Extraction producer | MISSING for direct projection |

### Identity, EvidenceRef and failure boundary

The local document key is `slugified stem + first eight SHA-256 characters`, not a run ID or approved CDOI source identity. The full source SHA-256 is present; source size and `source_document_id` are not. Element IDs and table IDs exist and table elements reference tables. Cells are addressed internally by their containing table plus row/column, but they have no IDs; that composite is **not** declared an EvidenceRef. Page index, optional bbox, and coordinate unit/origin offer physical locators, but original-source spans and any EvidenceRef resolver are absent. Therefore the chain from source identity through package ID/reference to KP `DocumentIR` and back to the original evidence is not yet proven.

Internal status is `success`, `success_with_warnings`, or `failed`. The canonical `Document` validator rejects `failed`; public `process_file` raises on failure and writes failure metadata where safe. This provides a fail-closed internal foundation, but it does not implement official `FATAL`, `EXTRACTION_PACKAGE_FAILED`, `ContractIssue`, or `ErrorEnvelope`. Error/warning strings lack structured severity, error code, retryability, detail/context and official run ID. No producer package is emitted today, so FATAL-at-contract-boundary behavior remains unimplemented here and KP rejection remains external.

The named `cdoi_doc_extraction_adapter_v1` is distinct from both the public v1 package producer and the KP `DocumentIR` adapter. It was not found in this checkout; `schemas/version.py` records internal version history, not an adapter for legacy `1.0.0`–`1.2.0` documents. Confirm its owning repository/path and how its normalized output reaches the v1 producer. Do not guess compatibility semantics.

No `document_revision_id` belongs in the public v1 payload. `source_url`, `final_url`, `acquisition_job_id`, `artifact_id`, and retrieval timestamps remain Acquisition-owned and must not be moved into Extraction. Entity/relation/canonical-entity ontology and governance remain outside the extraction layer.

## Adoption gate

Do not claim adoption until Extraction emits and validates only exact v1 packages, including golden/conformance cases for success, warnings, partial/error and FATAL; preserves nulls, explicit order, physical evidence and issues; and rejects unknown fields/versions. KP must independently validate, adapt to `DocumentIR`, preserve EvidenceRef and reject incompatible versions. See [`cdoi-teammate-confirmation-checklist.md`](cdoi-teammate-confirmation-checklist.md) for specific path/version/test-evidence questions.
