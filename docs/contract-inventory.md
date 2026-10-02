# Extraction boundary inventory

This inventory records artifacts found in this checkout and available sibling
workspace. It distinguishes repository facts from ownership inferences; it is
not a proposed cross-team schema.

| Artifact | Path / identity | Owner, producer, consumer | Status | Evidence classification / confidence |
| --- | --- | --- | --- | --- |
| Canonical internal document model | `src/doc_extraction/schemas/document.py`, `page.py`, `element.py`, `table.py`; `schema_version = 1.4.0` | Owner inferred as this repository; produced by `process_file()` / document assembly; consumed by this package's serializers and callers | Implemented | FACT: model, validators, and schema-version constant are present; HIGH confidence |
| Canonical JSON serialization | `final/document.json`; documented in `docs/output-format.md` | Produced by extraction assembly; consumed by local callers | Implemented, internal only | FACT: it serializes canonical `Document`; HIGH confidence |
| Markdown view | `Document.to_markdown()` and OmniDocBench adapter in `src/doc_extraction/evaluation/omnidocbench.py` | Human inspection / pinned benchmark evaluator | Implemented, explicitly lossy and benchmark-specific | FACT: separate serializer code and documentation; HIGH confidence |
| Public extraction API | `doc_extraction.cli.process_file(path, config, output_root=...)`; `docs/public-api.md` | Package producer; service callers | Implemented | FACT: documented function exists and Web Acquisition seam calls it; HIGH confidence |
| `DocumentExtractionContract 1.0.0` | No schema/model/example/validator found in tracked repo or available sibling source tree | Owner, producer, and consumer cannot be inferred | NOT FOUND / UNDEFINED in inspected workspace | FACT: searches and contract-blocker documentation show no artifact; MEDIUM confidence limited to inspected workspace |
| `ExtractionPackage v1` | No authoritative external contract or converter found; see `docs/extractionpackage-v1-integration.md` | KP/CDOI ownership was requested but no owner artifact or consumer entry point is present | NOT FOUND / UNDEFINED in inspected workspace | FACT: only references describe the missing contract; MEDIUM confidence limited to inspected workspace |
| KP `DocumentIR` adapter | No adapter implementation or downstream `DocumentIR` model found | Downstream owner unknown | NOT FOUND | FACT: no implementation/reference beyond blocker documentation; MEDIUM confidence |
| Extraction run provenance | `RunMetadata` in `schemas/document.py` | Produced by extractor; extraction consumers | Implemented internally | FACT: contains input name/path/hash, detected file type, route, backend, config, versions, runtime/device, status/warnings/errors. It has no source byte-size or authoritative MIME field; HIGH confidence |
| Physical evidence traceability | Element/table/cell source backend and optional source IDs, plus internal diagnostics in `evaluation/evidence_integrity.py` | Extractor diagnostics; no external evidence-reference consumer found | Partial/internal | FACT: canonical fields and research/diagnostic ledger exist; no formal `EvidenceRef` cross-team schema found. HIGH confidence for repo model, MEDIUM for absence outside workspace |
| Acquisition artifact | `services/web-acquisition/src/web_acquisition/models.py` (`Artifact`, `Resource`, `CrawlJob`) and `integration.py` | Owner inferred as Web Acquisition; acquisition service produces artifact; optional extraction seam consumes it | Implemented separately from `Document` | FACT: acquisition models and API seam are present. Resource/source URL/job provenance remain acquisition-owned; no extraction-contract mapping is defined. HIGH confidence |
| E2E worker protocol | Private framed JSON process protocol in `utils/process_worker.py` and `backends/paddleocr_vl_backend.py` | Extractor backend worker ↔ supervising process | Implemented, private | FACT: bounded framed messages and parent validation; not a downstream document contract. HIGH confidence |
| Benchmark result/ground-truth pairing | `doc_extraction.evaluation.omnidocbench`, `experiments/005_omnidocbench/evaluate.py`, benchmark recorder | Benchmark tooling ↔ pinned OmniDocBench evaluator | Implemented for run-scoped evaluation | FACT: exact prediction alignment is checked and frozen subset GT is selected from run metadata; regression tests exist. HIGH confidence |

## Internal-to-external boundary analysis

The only established flow is:

```text
Acquisition Artifact → public extraction API → internal Document 1.4.0
                                      → [external contract unknown] → KP unknown
```

`Document` fields that are clearly physical extraction concerns include page
identity/order, elements, explicit reading order, geometry and its coordinate
convention, physical table/cell grids, extracted text, backend/source IDs, and
run warnings/errors. `RunMetadata` also carries extractor operational facts
such as route, backend, runtime, device, model versions, and config snapshot.

The Web Acquisition `Artifact`, `Resource`, and `CrawlJob` own URL, redirect,
HTTP, crawl-job, acquisition hash/size, and discovery lineage. No rule was
found that says which of these acquisition facts must cross into a future
extraction contract; adding them to `Document` would be an unsupported
ownership change.

No entity, relation, canonical-entity, semantic-normalization, or governance
model appears in the canonical schema. These remain outside extraction.
Whether a future KP contract carries semantic projections alongside physical
evidence is UNKNOWN and must be decided by its owner.

Potentially unsafe-to-project-without-contract-definitions include:

* storage order versus explicit `reading_order`;
* null geometry, text, confidence, and logical page locators;
* `file_type` (detected kind) versus MIME type;
* source hash versus acquisition artifact identity and size;
* free-form warning/error strings versus external severity/status enums;
* `Element.extra` and internal backend/source identifiers;
* physical page/table/cell identifiers and their scope/stability.

These are open mapping questions, not candidate fields or semantics for a
guessed adapter. See [`extractionpackage-v1-integration.md`](extractionpackage-v1-integration.md)
for the concrete owner-supplied artifacts needed to unblock integration.

## Backend conformance scope

`tests/backend_conformance.py` is a test helper, not a public runtime API. It
revalidates canonical model structure, explicit order and resolvable physical
references, checks geometry/table-span invariants, and verifies serialized
nulls and diagnostics survive round trips. It proves structural and
representational conformance only; it does not prove that all visible source
content was recognized or that one backend is more accurate.

The known Classic empty-output case remains **STRONGLY INDICATED**, not
confirmed. Local Docling 2.124.0 / docling-core 2.93.0 source inspection shows
that formula labels are included in OCR-region selection, so label-based OCR
suppression is not supported by the evidence. The recorded configuration
uses EasyOCR languages `en` and `vi` for a simplified-Chinese page, while
Docling formula enrichment is left at its default-disabled setting. The run
artifacts do not retain Docling's internal OCR cells or formula-stage outputs,
so they cannot distinguish zero recognition from a later Docling assembly
loss. No speculative recovery was added. The full trace and evidence limit
are recorded in [`classic-backend-forensics.md`](classic-backend-forensics.md).

Stored representative-v2 canonical output also confirms one visual-route
table-ownership defect: a recognized table's cell strings were repeated in
overlapping sibling text elements. The visual merge now excludes OCR tokens
whose centers are inside recognized table bounds from non-table region text;
the same ownership boundary already applied to orphan recovery. A synthetic
visual-pipeline regression preserves non-table text outside those bounds.
