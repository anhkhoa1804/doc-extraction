"""Private observation ledger and evidence-integrity evaluator.

This module deliberately does not extend the public ``Document`` schema. It
records what a backend supplied and how the existing canonical projection used
it, so an experiment can compare canonical output (A) with the same output
plus a ledger (B) without changing extraction behaviour.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from enum import Enum
from hashlib import sha256
import json
import re
from typing import Any
from html.parser import HTMLParser

from doc_extraction.schemas.document import Document


class Disposition(str, Enum):
    ACCEPTED = "accepted"
    UNRESOLVED = "unresolved"
    EXCLUDED = "excluded"


class LossBoundary(str, Enum):
    ACQUISITION = "acquisition"
    NORMALIZATION = "normalization"
    OWNERSHIP = "ownership"
    RECONCILIATION = "reconciliation"
    CANONICAL_PROJECTION = "canonical_projection"
    SERIALIZATION = "serialization"
    UNKNOWN = "unknown"
    PRESERVED = "preserved"


@dataclass(frozen=True)
class OwnershipClaim:
    owner_ref: str
    basis: str


@dataclass(frozen=True)
class ObservationRecord:
    """An immutable acquired or explicitly derived physical observation."""

    observation_id: str
    backend: str
    payload_kind: str
    page_index: int | None
    text: str | None = None
    raw_role: str | None = None
    geometry: tuple[float, float, float, float] | None = None
    source_locator: str | None = None
    confidence: float | None = None
    confidence_origin: str | None = None
    derivation_refs: tuple[str, ...] = ()
    candidate_claims: tuple[OwnershipClaim, ...] = ()
    disposition: Disposition = Disposition.EXCLUDED
    public_object_refs: tuple[str, ...] = ()
    warning_context: tuple[str, ...] = ()
    # ``acquisition`` means captured immediately when the backend result was
    # returned, before this pipeline normalizes, fills cells, or merges it.
    # ``projection`` is the compatibility/reconciliation view used by 043/044.
    capture_stage: str = "projection"


def _box(value: Any) -> tuple[float, float, float, float] | None:
    return None if value is None else (float(value.x0), float(value.y0), float(value.x1), float(value.y1))


def _fingerprint(*, backend: str, kind: str, page: int | None, text: str | None,
                 role: str | None, geometry: tuple[float, float, float, float] | None,
                 locator: str | None, duplicate_rank: int) -> str:
    # Content/locator based, not a source-list index. Rank distinguishes
    # genuinely indistinguishable duplicate captures.
    payload = json.dumps([backend, kind, page, text, role, geometry, locator, duplicate_rank],
                         ensure_ascii=False, separators=(",", ":"))
    return "obs-" + sha256(payload.encode("utf-8")).hexdigest()[:20]


@dataclass
class ObservationLedger:
    """Append-only private ledger; captured material is not source truth."""

    records: list[ObservationRecord] = field(default_factory=list)
    acquisition_records: list[ObservationRecord] = field(default_factory=list)

    def add(self, record: ObservationRecord) -> None:
        if any(old.observation_id == record.observation_id for old in self.records):
            raise ValueError(f"duplicate observation identity: {record.observation_id}")
        self.records.append(record)

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": 2,
            "records": [asdict(r) for r in sorted(self.records, key=lambda r: r.observation_id)],
            "acquisition_records": [asdict(r) for r in sorted(self.acquisition_records, key=lambda r: r.observation_id)],
        }

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    def capture_acquisition_scanned_page(self, *, page_index: int, layout_result: Any,
                                         ocr_result: Any, table_result: Any | None) -> None:
        """Capture backend-returned observations before any page projection.

        This is the earliest common, backend-neutral boundary in the modular
        scanned-page route. It deliberately receives raw ``LayoutResult``,
        ``OCRResult``, and ``TableResult`` objects, not a ``Page`` or
        ``Document``. ``table_result`` is captured before `_fill_table_cell_text`
        mutates table-cell text from OCR tokens.
        """
        if any(record.page_index == page_index for record in self.acquisition_records):
            raise ValueError(f"acquisition observations already captured for page {page_index}")
        duplicates: Counter[tuple[Any, ...]] = Counter()

        def ident(backend: str, kind: str, text: str | None, role: str | None,
                  geometry: tuple[float, float, float, float] | None, locator: str | None) -> str:
            key = (backend, kind, page_index, text, role, geometry, locator)
            rank = duplicates[key]
            duplicates[key] += 1
            return _fingerprint(backend=backend, kind=kind, page=page_index, text=text, role=role,
                                geometry=geometry, locator=locator, duplicate_rank=rank)

        raw_table_ids: dict[str, str] = {}
        for region in layout_result.regions:
            self.acquisition_records.append(ObservationRecord(
                ident(layout_result.backend, "layout_region", None, region.label, _box(region.bbox), region.source_id),
                layout_result.backend, "layout_region", page_index, raw_role=region.label, geometry=_box(region.bbox),
                source_locator=region.source_id, confidence=region.confidence, confidence_origin="layout_backend",
                warning_context=tuple(layout_result.warnings), capture_stage="acquisition"))
        for token in ocr_result.tokens:
            self.acquisition_records.append(ObservationRecord(
                ident(ocr_result.backend, "ocr_token", token.text, None, _box(token.bbox), None), ocr_result.backend,
                "ocr_token", page_index, text=token.text, geometry=_box(token.bbox), confidence=token.confidence,
                confidence_origin="ocr_backend", warning_context=tuple(ocr_result.warnings), capture_stage="acquisition"))
        if table_result is None:
            return
        for table in table_result.tables:
            oid = ident(table.source_backend, "table", None, None, _box(table.bbox), table.id)
            raw_table_ids[table.id] = oid
            self.acquisition_records.append(ObservationRecord(
                oid, table.source_backend, "table", page_index, geometry=_box(table.bbox), source_locator=table.id,
                confidence=table.confidence, confidence_origin="table_backend", warning_context=tuple(table_result.warnings),
                capture_stage="acquisition"))
            for cell in table.cells:
                ref = f"page:{page_index}:table:{table.id}:cell:{cell.row}:{cell.col}"
                self.acquisition_records.append(ObservationRecord(
                    ident(table.source_backend, "table_cell_candidate", cell.text, None, _box(cell.bbox), ref),
                    table.source_backend, "table_cell_candidate", page_index, text=cell.text, geometry=_box(cell.bbox),
                    confidence=cell.confidence, confidence_origin="table_backend", derivation_refs=(raw_table_ids[table.id],),
                    warning_context=tuple(table_result.warnings), capture_stage="acquisition"))

    def capture_scanned_page(self, *, page: Any, layout_result: Any, ocr_result: Any,
                             table_result: Any | None) -> None:
        """Record existing scanned-page stage outputs after canonical merge.

        The method makes no extraction decision. Geometric ownership claims
        remain unresolved when more than one compatible owner exists.
        """
        page_index, regions = page.index, list(layout_result.regions)
        tables = list(table_result.tables) if table_result else []
        duplicates: Counter[tuple[Any, ...]] = Counter()

        def ident(backend: str, kind: str, text: str | None, role: str | None,
                  geometry: tuple[float, float, float, float] | None, locator: str | None) -> str:
            key = (backend, kind, page_index, text, role, geometry, locator)
            rank = duplicates[key]
            duplicates[key] += 1
            return _fingerprint(backend=backend, kind=kind, page=page_index, text=text, role=role,
                                geometry=geometry, locator=locator, duplicate_rank=rank)

        for number, region in enumerate(regions):
            ref = f"page:{page_index}:element:p{page_index}-e{number}"
            self.add(ObservationRecord(
                ident(layout_result.backend, "layout_region", None, region.label, _box(region.bbox), region.source_id),
                layout_result.backend, "layout_region", page_index, raw_role=region.label,
                geometry=_box(region.bbox), source_locator=region.source_id, confidence=region.confidence,
                confidence_origin="layout_backend", candidate_claims=(OwnershipClaim(ref, "canonical layout-region projection"),),
                disposition=Disposition.ACCEPTED, public_object_refs=(ref,)))

        token_ids: list[tuple[Any, str]] = []
        for token in ocr_result.tokens:
            claims: list[OwnershipClaim] = []
            for number, region in enumerate(regions):
                if _contains(region.bbox, token.bbox):
                    claims.append(OwnershipClaim(f"page:{page_index}:element:p{page_index}-e{number}", "token centre in layout region"))
            for table in tables:
                for cell in table.cells:
                    if cell.bbox is not None and _contains(cell.bbox, token.bbox):
                        claims.append(OwnershipClaim(f"page:{page_index}:table:{table.id}:cell:{cell.row}:{cell.col}", "token centre in table cell"))
            recovered = tuple(sorted(f"page:{page_index}:element:{e.id}" for e in page.elements
                                     if e.extra.get("recovered") and e.bbox is not None and _contains(e.bbox, token.bbox)))
            disposition = (Disposition.ACCEPTED if len(claims) == 1 or recovered else
                           Disposition.UNRESOLVED if len(claims) > 1 else Disposition.EXCLUDED)
            oid = ident(ocr_result.backend, "ocr_token", token.text, None, _box(token.bbox), None)
            token_ids.append((token, oid))
            self.add(ObservationRecord(
                oid, ocr_result.backend, "ocr_token", page_index, text=token.text, geometry=_box(token.bbox),
                confidence=token.confidence, confidence_origin="ocr_backend", candidate_claims=tuple(claims),
                disposition=disposition, public_object_refs=recovered if recovered else
                (() if len(claims) != 1 else (claims[0].owner_ref,))))

        for table in tables:
            table_ref = f"page:{page_index}:table:{table.id}"
            table_id = ident(table.source_backend, "table", None, None, _box(table.bbox), table.id)
            self.add(ObservationRecord(table_id, table.source_backend, "table", page_index, geometry=_box(table.bbox),
                source_locator=table.id, confidence=table.confidence, confidence_origin="table_backend",
                disposition=Disposition.ACCEPTED, public_object_refs=(table_ref,)))
            for cell in table.cells:
                ref = f"{table_ref}:cell:{cell.row}:{cell.col}"
                parents = tuple(oid for token, oid in token_ids if cell.bbox is not None and _contains(cell.bbox, token.bbox))
                self.add(ObservationRecord(
                    ident(table.source_backend, "table_cell", cell.text, None, _box(cell.bbox), ref),
                    table.source_backend, "table_cell", page_index, text=cell.text, geometry=_box(cell.bbox),
                    confidence=cell.confidence, confidence_origin="table_backend", derivation_refs=parents + (table_id,),
                    candidate_claims=(OwnershipClaim(ref, "table-cell projection"),), disposition=Disposition.ACCEPTED,
                    public_object_refs=(ref,)))


def _contains(outer: Any, inner: Any) -> bool:
    return outer.x0 <= (inner.x0 + inner.x1) / 2 <= outer.x1 and outer.y0 <= (inner.y0 + inner.y1) / 2 <= outer.y1


def normalize_text(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").strip()).casefold()


class _CellTextParser(HTMLParser):
    """Minimal deterministic extractor for OmniDocBench ``td``/``th`` text."""
    def __init__(self) -> None:
        super().__init__()
        self._depth = 0
        self._parts: list[str] = []
        self.cells: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"td", "th"}:
            self._depth += 1
            if self._depth == 1:
                self._parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._depth:
            self._depth -= 1
            if self._depth == 0:
                self.cells.append(normalize_text("".join(self._parts)))

    def handle_data(self, data: str) -> None:
        if self._depth:
            self._parts.append(data)


def html_cell_texts(html: str) -> tuple[str, ...]:
    """Return normalized cell strings; HTML is a truth source, not a model."""
    parser = _CellTextParser()
    parser.feed(html)
    parser.close()
    return tuple(cell for cell in parser.cells if cell)


def truth_exact_match(text: str | None, truth_cells: tuple[str, ...]) -> bool:
    """Strict cell-level truth predicate used by the frozen development protocol."""
    value = normalize_text(text)
    return bool(value) and value in truth_cells


def baseline_phrase_match(text: str | None, baseline_texts: tuple[str, ...]) -> bool:
    """Locator-scoped exact phrase check used when canonical spans are absent."""
    value = normalize_text(text)
    return bool(value) and any(f" {value} " in f" {baseline} " for baseline in baseline_texts)


def truth_aware_candidate(*, text: str | None, truth_cells: tuple[str, ...],
                          baseline_texts: tuple[str, ...], ownership_valid: bool,
                          provenance_complete: bool, structurally_valid: bool) -> dict[str, bool]:
    """Classify one candidate under the frozen normalized-exact protocol."""
    text_bearing = bool(normalize_text(text))
    correct = truth_exact_match(text, truth_cells)
    duplicate = baseline_phrase_match(text, baseline_texts)
    novel = text_bearing and correct and ownership_valid and provenance_complete and not duplicate
    return {"text_bearing": text_bearing, "correct": correct, "duplicate_baseline": duplicate,
            "ownership_valid": ownership_valid, "provenance_complete": provenance_complete,
            "structurally_valid": structurally_valid, "novel_correct_textual_evidence": novel,
            "structural_only_recovery": structurally_valid and not novel}


def classify_loss_boundary(*, acquisition_present: bool, canonical_exact_present: bool,
                           canonical_normalized_present: bool, serialized_present: bool,
                           ownership_conflict: bool, reconciliation_missing: bool = False) -> LossBoundary:
    """Classify the first evidenced disappearance; unknowns stay unknown."""
    if not acquisition_present:
        return LossBoundary.ACQUISITION
    if reconciliation_missing:
        return LossBoundary.RECONCILIATION
    if not canonical_normalized_present:
        return LossBoundary.OWNERSHIP if ownership_conflict else LossBoundary.CANONICAL_PROJECTION
    if not canonical_exact_present:
        return LossBoundary.NORMALIZATION
    if not serialized_present:
        return LossBoundary.SERIALIZATION
    return LossBoundary.PRESERVED


def _object_refs(document: Document) -> set[str]:
    refs: set[str] = set()
    for page in document.pages:
        refs.update(f"page:{page.index}:element:{e.id}" for e in page.elements)
        for table in page.tables:
            refs.add(f"page:{page.index}:table:{table.id}")
            refs.update(f"page:{page.index}:table:{table.id}:cell:{c.row}:{c.col}" for c in table.cells)
    return refs


def _texts(document: Document) -> set[str]:
    values = {normalize_text(e.text) for p in document.pages for e in p.elements}
    values |= {normalize_text(c.text) for p in document.pages for t in p.tables for c in t.cells}
    return values - {""}


def _serialized_texts(document: Document) -> set[str]:
    # Markdown is the current human-facing serialization boundary. This is a
    # diagnostic, not a substitute for a lossless public contract.
    return {normalize_text(line) for line in document.to_markdown().splitlines() if normalize_text(line)}


def evaluate_evidence_integrity(*, baseline: Document, candidate: Document, ledger: ObservationLedger) -> dict[str, Any]:
    """Paired A/B evaluator using normalized exact text, never semantic similarity.

    Novelty is representational only; correct-vs-incorrect text requires an
    external truth annotation and is therefore intentionally not inferred.
    """
    records = ledger.records
    accepted = [r for r in records if r.disposition is Disposition.ACCEPTED]
    unresolved = [r for r in records if r.disposition is Disposition.UNRESOLVED]
    excluded = [r for r in records if r.disposition is Disposition.EXCLUDED]
    output_refs = _object_refs(candidate)
    traced = {ref for r in accepted for ref in r.public_object_refs}
    candidate_texts, baseline_texts = _texts(candidate), _texts(baseline)
    serialized_texts = _serialized_texts(candidate)
    accepted_texts = {normalize_text(r.text) for r in accepted if normalize_text(r.text)}
    derived = [r for r in accepted if r.derivation_refs]
    identifiers = {r.observation_id for r in records}
    return {
        "captured": len(records), "accepted": len(accepted), "unresolved": len(unresolved), "excluded": len(excluded),
        "accounting_invariant": len(records) == len(accepted) + len(unresolved) + len(excluded),
        "evidence_presence": len(accepted), "evidence_loss": len(excluded),
        "duplication": sum(len(r.public_object_refs) > 1 for r in accepted),
        "misownership": sum(len(r.candidate_claims) > 1 for r in unresolved),
        "uncertainty_preserved": len(unresolved),
        "structural_only_recovery": sum(r.payload_kind == "table_cell" and not normalize_text(r.text) for r in accepted),
        "novel_textual_evidence": sorted(candidate_texts - baseline_texts),
        "novel_textual_evidence_count": len(candidate_texts - baseline_texts),
        "duplicate_textual_evidence": sorted(candidate_texts & baseline_texts),
        "duplicate_textual_evidence_count": len(candidate_texts & baseline_texts),
        "serialized_evidence_loss": sorted((accepted_texts & candidate_texts) - serialized_texts),
        "serialized_evidence_loss_count": len((accepted_texts & candidate_texts) - serialized_texts),
        # Both directions matter: dangling claims are invalid, and an
        # accepted canonical object without a source is incomplete provenance.
        "provenance_complete": not (traced - output_refs) and not (output_refs - traced),
        "untraced_accepted_public_refs": sorted(traced - output_refs),
        "canonical_objects_without_provenance": sorted(output_refs - traced),
        "derivation_complete": sum(all(parent in identifiers for parent in r.derivation_refs) for r in derived),
        "derived_objects": len(derived),
        "canonical_output_equivalent": candidate.model_dump(mode="json") == baseline.model_dump(mode="json"),
    }
