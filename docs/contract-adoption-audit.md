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

## Role-separation evidence

| Role/fact | Evidence classification | Finding |
| --- | --- | --- |
| Public contract identity `DocumentExtractionContract` 1.0.0; payload name `ExtractionPackage v1` | `CONFIRMED_FROM_OFFICIAL_SPEC` | Treat as authoritative; exact source revision/path still needs teammate handoff |
| Official contract distinguishes internal Extraction `Document` from the public package | `CONFIRMED_FROM_OFFICIAL_SPEC` | The official boundary keeps the internal representation distinct |
| This checkout defines canonical `Document` schema 1.4.0 and exposes it through the current public API | `CONFIRMED_LOCAL` | Local schema/version and public API are present; this does not prove package equivalence |
| `cdoi_doc_extraction_adapter_v1` is producer-side compatibility for legacy internal schemas 1.0.0–1.2.0, distinct from public package producer and KP adapter | `CONFIRMED_FROM_OFFICIAL_SPEC` | Role distinction is authoritative for this audit; executable path is not found locally |
| Public ExtractionPackage v1 producer | `NOT_FOUND_LOCALLY` | Current public API emits internal Document only |
| KP validator and `DocumentIR` adapter | `NOT_FOUND_LOCALLY` | Exact owner paths and test evidence required |
| EvidenceRef model/resolver and physical provenance preservation across KP adaptation | `NOT_FOUND_LOCALLY` | No local type, resolver, or cross-repository conformance test |
| Internal Extraction fields are semantically equivalent to official package fields | `REQUIRES_TEAMMATE_CONFIRMATION` | Similar names/data do not establish wire-level contract equivalence |

## Contract inventory

| Contract area | Official requirement | Current doc-extraction state | Gap | Owner | Evidence | Evidence classification |
| --- | --- | --- | --- | --- | --- | --- |
| Public identity/version | Exact contract name/version; package name ExtractionPackage v1 | Internal `schema_version=1.4.0`; no public package producer | Public envelope and exact-version validator absent | Extraction producer; CDOI owns schema | `schemas/document.py`, `schemas/version.py`; no package code found | NOT_FOUND_LOCALLY |
| Unknown fields/version | Reject unknown fields and unsupported versions; no guessing | Internal Pydantic models generally use `extra="forbid"`; not a public-package validator | Contract-specific validator and tests absent | Extraction; KP independently validates | Internal models only | NOT_FOUND_LOCALLY |
| Source identity | `source_name`, MIME, optional hash, size; `source_document_id` | `input_filename`, full SHA-256 and local document key exist; no canonical MIME, byte-size, or explicit source-document identity field | Mapping and size propagation need confirmation/implementation | Extraction + Acquisition metadata; CDOI defines meaning | `RunMetadata`, `utils/ids.py`, Acquisition models | REQUIRES_TEAMMATE_CONFIRMATION |
| Run identity/provenance | `extraction_run_id`, backend, `extracted_at`, language hints, provenance | Timestamp, route/backend, model versions, config/device exist; no explicit run ID or first-class language hint | Run-ID ownership and safe projection undefined | Extraction producer | `RunMetadata`, `process_file()` | REQUIRES_TEAMMATE_CONFIRMATION |
| Physical sections | Sections are part of public physical structure | No canonical section model; pages contain elements/tables | Official optionality/derivation and lossless mapping must be confirmed | CDOI + Extraction | `schemas/page.py`; no section schema | REQUIRES_TEAMMATE_CONFIRMATION |
| Elements/locations | Stable IDs, text/nulls, locations, coordinates/spans, optional geometry, source spans | Element IDs/type/text/bbox/page/source/order/parent/level; no explicit source offsets | Stable-ID scope and source-span mapping absent | Extraction; CDOI defines locator rules | `schemas/element.py` | REQUIRES_TEAMMATE_CONFIRMATION |
| Tables/cells | Stable IDs, locations and spans | Table IDs, dimensions, bbox; cells have row/column/spans/bbox/text/header, but no ID; cell text is non-null `str` default `""` | Cell ID and empty-versus-unknown/null semantics need mapping | Extraction; CDOI defines identity/null rules | `schemas/table.py` | REQUIRES_TEAMMATE_CONFIRMATION |
| Reading order | Explicit producer order is authoritative | `Page.reading_order` is an explicit element-ID sequence; model permits incomplete order | Preserve exact sequence; clarify official handling of incomplete order | Extraction; KP must preserve | `schemas/page.py`, conformance helper | REQUIRES_TEAMMATE_CONFIRMATION |
| Issues/errors | Official `ContractIssue`; warnings/nonfatal errors remain visible | Internal status plus warning/error string lists; no `ContractIssue` or `ErrorEnvelope` | Severity/code/retryability/detail/context mapping absent | Extraction + CDOI; KP preserves | `RunMetadata`, `RunStatus` | REQUIRES_TEAMMATE_CONFIRMATION |
| FATAL | Fail closed as `EXTRACTION_PACKAGE_FAILED`; no successful empty package | Internal FAILED cannot instantiate canonical `Document`; `process_file` raises and writes failure metadata where safe | Package failure envelope and KP rejection tests absent | Extraction producer + KP consumer | `Document` validator, `cli.process_file` | REQUIRES_TEAMMATE_CONFIRMATION |
| EvidenceRef | Stable IDs + source identity/provenance resolve physical evidence; KP preserves refs | Element/table local IDs and page/bbox; no cell IDs, EvidenceRef model or resolver | Official reference syntax and end-to-end source resolution absent | Joint Extraction/KP; CDOI specifies | No local implementation found | NOT_FOUND_LOCALLY |
| Producer compatibility adapter | `cdoi_doc_extraction_adapter_v1` for legacy internal schemas 1.0.0–1.2.0; distinct from public/KP adapters | Named implementation not found locally; current runtime schema is 1.4.0 | Confirm path/owner and how legacy data is adapted before package emission | Extraction/CDOI teammate | `git grep`; `schemas/version.py` | NOT_FOUND_LOCALLY |
| Acquisition boundary | URLs/job/artifact/retrieval timestamps remain Acquisition-owned | Separate Artifact/Resource/CrawlJob; seam calls public `process_file` | Confirm which Acquisition-supplied MIME/hash/size enter producer; keep URL/job fields out of contract | Acquisition + Extraction | `services/web-acquisition/.../integration.py` | REQUIRES_TEAMMATE_CONFIRMATION |
| KP adapter / DocumentIR | KP validates, adapts to `DocumentIR`, preserves EvidenceRef and rejects incompatible versions | No KP implementation or `DocumentIR` found in accessible workspace | Teammate must provide implementation path and test evidence | KP | Bounded workspace search | NOT_FOUND_LOCALLY |

Inventory classifications refer to local implementation evidence, not the authority or existence of the official specification.

## Field-level mapping: internal Document 1.4.0 → public package

This is a mapping inventory, not a schema proposal. A candidate source does not establish semantic equivalence until confirmed by the contract owner.

| Official field/area | Official presence/nullability | Current source | Transform / lossless? | Owner | Evidence classification |
| --- | --- | --- | --- | --- | --- |
| `contract_name` | Exact identity required; non-null | None | Emit literal official value; lossless once producer exists | Extraction producer | NOT_FOUND_LOCALLY |
| `contract_version` | Exact `1.0.0`; non-null | Internal `schema_version=1.4.0` is a different version space | Emit literal `1.0.0`; never copy internal version | Extraction producer | NOT_FOUND_LOCALLY |
| `extraction_run_id` | Identity field; exact nullability/format to confirm against schema | None | Must create with owner-approved scope; timestamp is not interchangeable | Extraction producer | NOT_FOUND_LOCALLY |
| `source_document_id` | Identity field; exact nullability/format to confirm | Local `document_id` = slugified stem + first 8 SHA-256 hex chars | Not lossless as an asserted source ID; short digest/local output key can collide | Acquisition provides identity if defined; Extraction passes through | REQUIRES_TEAMMATE_CONFIRMATION |
| `source_name` | Source provenance; exact nullability/normalization to confirm | `RunMetadata.input_filename` | Candidate direct mapping after normalization rules confirmed | Acquisition/Extraction | REQUIRES_TEAMMATE_CONFIRMATION |
| `source_mime_type` | Source provenance; exact nullability to confirm | `file_type`, transient `FileInfo.mime_guess` | Not lossless: `file_type` can be `pdf`; MIME is not retained authoritatively | Acquisition supplies media type; Extraction carries it | NOT_FOUND_LOCALLY |
| `source_hash` | Optional per official facts | `RunMetadata.file_hash_sha256` | Candidate direct SHA-256; confirm official algorithm/encoding | Extraction computes; Acquisition hash may be compared | REQUIRES_TEAMMATE_CONFIRMATION |
| `source_size_bytes` | Source provenance; exact nullability to confirm | None in canonical metadata | Must carry exact byte count; keep source ownership at Acquisition where applicable | Acquisition/Extraction | NOT_FOUND_LOCALLY |
| Backend provenance | Backend fields required; exact shape/nullability from official schema | `route`, `pipeline`, `backend`, page source fields, versions/config/device | Allowlisted transform needed; arbitrary `config_snapshot` is not safe/lossless strict metadata | Extraction producer | REQUIRES_TEAMMATE_CONFIRMATION |
| `extracted_at` | Extraction provenance; exact nullability/temporal meaning to confirm | `RunMetadata.timestamp` ISO UTC, set before assembly | Candidate mapping but start/completion semantics may differ | Extraction producer | REQUIRES_TEAMMATE_CONFIRMATION |
| Language hints | Extraction provenance; exact nullability to confirm | May be nested in `config_snapshot`; not a guaranteed field | Extract only validated language codes; may be absent | Extraction producer | REQUIRES_TEAMMATE_CONFIRMATION |
| `provenance` | Structured provenance; exact schema/nullability to confirm | Run/page/backend/source IDs | Must transform; direct arbitrary map pass-through is not lossless or strict | Extraction producer | REQUIRES_TEAMMATE_CONFIRMATION |
| `sections` | Required/optional and nullable shape not independently checked from schema file | No internal section collection | No lossless mapping established; do not synthesize sections | CDOI defines shape; Extraction maps | NOT_FOUND_LOCALLY |
| `elements` | Physical structure; exact nested requiredness from schema file | `Page.elements` | Map/whitelist by official element schema; `extra: Any` cannot pass through | Extraction producer | REQUIRES_TEAMMATE_CONFIRMATION |
| Stable element IDs | Stable physical IDs required | `Element.id` exists, commonly generated from page/position | Local ID presence confirmed; public scope and cross-run stability not proven | Extraction producer; CDOI defines scope | REQUIRES_TEAMMATE_CONFIRMATION |
| Text/null | Null must remain null where unknown; nested exact optionality to confirm | `Element.text: str\|None`; `Cell.text: str = ""` | Element null can survive; cell model cannot distinguish unknown from empty | Extraction producer | REQUIRES_TEAMMATE_CONFIRMATION |
| Nullable physical values | Null preservation required by official facts | Element bbox, rendered page numbers and some provenance fields can be null | Local null capability exists for several fields; complete package null/omission mapping is untested | Extraction producer; KP preserves | REQUIRES_TEAMMATE_CONFIRMATION |
| Locations/coordinates | Geometry optional per official facts; exact locator nullability/units to confirm | Page index, optional bbox, coordinate origin/unit | Can retain null bbox; coordinate/index conversion needs official locator rules | Extraction producer | REQUIRES_TEAMMATE_CONFIRMATION |
| Coordinates/spans/source spans | Physical coordinates/spans required as defined; source-span nullability to confirm | BBox, table row/column spans; no textual offsets | Physical geometry/table spans exist; textual source spans unavailable | Extraction producer | REQUIRES_TEAMMATE_CONFIRMATION |
| `tables` | Physical table structure | `Page.tables` | Mapping not implemented; table/cell schema conformance untested | Extraction producer | REQUIRES_TEAMMATE_CONFIRMATION |
| Stable table IDs | Stable physical IDs required | `Table.id` exists, locally page-scoped by producer conventions | Public scope and cross-run stability not proven | Extraction producer; CDOI defines scope | REQUIRES_TEAMMATE_CONFIRMATION |
| `cells` | Physical cell content/geometry/spans | `Table.cells` with row/column, spans, bbox and text | Shape exists internally; public mapping and stable references untested | Extraction producer | REQUIRES_TEAMMATE_CONFIRMATION |
| Stable cell IDs | Stable physical IDs required | No `Cell.id`; row/column position exists | No approved ID rule; do not synthesize a public identifier | Extraction producer; CDOI defines scope | NOT_FOUND_LOCALLY |
| Nullable cell text | Null must remain null when unknown | `Cell.text` is non-null `str`, default `""` | Cannot represent unknown separately from empty cell text internally | Extraction producer; semantics from CDOI | NOT_FOUND_LOCALLY |
| `reading_order` | Explicit producer order authoritative; exact completeness/nullability rules to confirm | `Page.reading_order` explicit list | Preserve exact sequence, not storage order; incomplete sequence remains an open conformance rule | Extraction producer; KP preserves | REQUIRES_TEAMMATE_CONFIRMATION |
| Warnings | Warnings remain visible downstream | `RunMetadata.warnings: list[str]` | Local strings exist; transformation/preservation through package/KP untested | Extraction producer; KP preserves | REQUIRES_TEAMMATE_CONFIRMATION |
| Errors | Non-fatal errors remain visible where applicable | `RunMetadata.errors: list[str]` plus internal status | No structured severity/code/retryability/detail/context; package mapping untested | Extraction producer; KP preserves | REQUIRES_TEAMMATE_CONFIRMATION |
| `ContractIssue` | Structured issue with severity/code/retryable/detail/run/context per official facts | No local model | No mapping implementation/test | Extraction producer; CDOI defines schema | NOT_FOUND_LOCALLY |
| Unknown-field rejection | Unknown fields rejected | Internal models use `extra="forbid"` in places; no package validator | Internal strictness is not public-package conformance | Extraction and KP validators | NOT_FOUND_LOCALLY |
| Unsupported-version rejection | Exact supported contract version; fail closed, no guessing | Internal `Document` rejects schema versions other than 1.4.0 | Does not validate public contract name/version or KP inputs | Extraction and KP validators | NOT_FOUND_LOCALLY |
| FATAL handling | FATAL cannot yield successful empty package | Internal FAILED Document rejected and API raises | This does not prove mapping to public error envelope | Extraction producer + KP | REQUIRES_TEAMMATE_CONFIRMATION |
| `EXTRACTION_PACKAGE_FAILED` | Required public failure classification for FATAL | No local constant/envelope/producer mapping found | No executable public behavior | Extraction producer + KP | NOT_FOUND_LOCALLY |
| Physical provenance preservation | KP preserves physical evidence and provenance | Internal backend/source IDs, page/bbox, order and source hash exist | Cross-package/KP preservation has no local integration test | Extraction + KP | REQUIRES_TEAMMATE_CONFIRMATION |
| EvidenceRef identity/resolution | References resolve to stable source-backed physical evidence | No EvidenceRef type or resolver; no cell IDs | End-to-end source identity/reference resolution unproven | Joint Extraction/KP | NOT_FOUND_LOCALLY |
| Strict metadata maps | Primitive-only and strict; exact optionality per field | `config_snapshot`, `text_profile`, `resource_violation`, `Element.extra` | Direct pass-through unsafe: several use `Any`; build explicit allowlist | Extraction producer | NOT_FOUND_LOCALLY |

### Identity, EvidenceRef and failure boundary

The local document key is `slugified stem + first eight SHA-256 characters`, not a run ID or approved CDOI source identity. The full source SHA-256 is present; source size and `source_document_id` are not. Element IDs and table IDs exist and table elements reference tables. Cells are addressed internally by their containing table plus row/column, but they have no IDs; that composite is **not** declared an EvidenceRef. Page index, optional bbox, and coordinate unit/origin offer physical locators, but original-source spans and any EvidenceRef resolver are absent. Therefore the chain from source identity through package ID/reference to KP `DocumentIR` and back to the original evidence is not yet proven.

Internal status is `success`, `success_with_warnings`, or `failed`. The canonical `Document` validator rejects `failed`; public `process_file` raises on failure and writes failure metadata where safe. This provides a fail-closed internal foundation, but it does not implement official `FATAL`, `EXTRACTION_PACKAGE_FAILED`, `ContractIssue`, or `ErrorEnvelope`. Error/warning strings lack structured severity, error code, retryability, detail/context and official run ID. No producer package is emitted today, so FATAL-at-contract-boundary behavior remains unimplemented here and KP rejection remains external.

The named `cdoi_doc_extraction_adapter_v1` is distinct from both the public v1 package producer and the KP `DocumentIR` adapter. It was not found in this checkout; `schemas/version.py` records internal version history, not an adapter for legacy `1.0.0`–`1.2.0` documents. Confirm its owning repository/path and how its normalized output reaches the v1 producer. Do not guess compatibility semantics.

No `document_revision_id` belongs in the public v1 payload. `source_url`, `final_url`, `acquisition_job_id`, `artifact_id`, and retrieval timestamps remain Acquisition-owned and must not be moved into Extraction. Entity/relation/canonical-entity ontology and governance remain outside the extraction layer.

## Adoption gate

Do not claim adoption until Extraction emits and validates only exact v1 packages, including golden/conformance cases for success, warnings, partial/error and FATAL; preserves nulls, explicit order, physical evidence and issues; and rejects unknown fields/versions. KP must independently validate, adapt to `DocumentIR`, preserve EvidenceRef and reject incompatible versions. See [`cdoi-teammate-confirmation-checklist.md`](cdoi-teammate-confirmation-checklist.md) for specific path/version/test-evidence questions.
