"""A shared contract for "should a consumer trust this result", plus a
post-hoc pass that applies it over an already-assembled `Document`.

Why this exists
----------------
Two gates already exist in this repo, built independently, for two
different silent-corruption incidents:

* `text_quality.assess_text` — is this text plausibly decoded, or garbage
  wearing the shape of prose (broken font CMap)? Built after the smoke test
  found `Độc lập Tự do` decoding to `ĈӝF OұS 7ӵ GR`.
* `table_quality.assess_table` — does a table's cell text match the runs
  that produced it, or has an overlay been woven in? Built after experiment
  010 found a stamped invoice cell reading `NBHộH`.

Both are cheap, deterministic, evidence-calibrated, and answer the same
underlying question in the same shape (trustworthy? how sure? why?) with
two different vocabularies (`suspicious: bool` vs `trusted: bool` +
`severity`). This module is *not* a rewrite of either — both keep computing
their own signals, because those signals are specific to what they inspect.
This only unifies the verdict they report, and adds the one thing neither
currently does: running over the **final assembled output**, not just at a
routing decision made before extraction.

Why post-hoc, in addition to pre-extraction routing
-----------------------------------------------------
`assess_text` today only gates the native-PDF route's decision (native vs.
render+OCR), decided *before* any text exists. It says nothing about
whether the text that OCR (or a VLM, or anything else) subsequently
produced is any good — and OCR misreads are a real, measured failure mode
in this project's own corpus (`clean_vi` at 50% recall in experiment 009).
A gate that only runs pre-extraction cannot see a post-extraction failure.
Running the same signals again over the assembled `Element.text` closes
that gap without duplicating the routing logic.

What this deliberately does not do
-----------------------------------
It does not invent a third verdict tier where the underlying gate does not
support one. `assess_text` is binary (`suspicious`) by design — conservative,
biased against false positives — so text verification here is TRUSTED or
SUSPICIOUS only, never INVALID; inventing an INVALID tier from a signal that
was calibrated as binary would be a tier this evidence does not support.
`assess_table`'s three-way severity (`none`/`medium`/`high`) already
distinguishes "geometry doubtful" from "content actively wrong" — mission
language for `high` is "a consumer reading that cell is reading a wrong
string", i.e. confidently wrong, which is exactly what INVALID means here.

It does not re-run table assessment: `assess_table` needs the source text
*runs* (PyMuPDF spans annotated with cell assignment), which exist only
transiently during table extraction and are not part of the serialized
`Table` schema. `Table.confidence` already carries that gate's verdict
(set in `pymupdf_table_backend.py`); this module reads it rather than
re-deriving it from information that is no longer available post-hoc.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from doc_extraction.ingest.text_quality import TextQualityReport, TextQualityThresholds, assess_text
from doc_extraction.schemas.document import Document
from doc_extraction.schemas.element import Element
from doc_extraction.schemas.table import Table


class VerificationStatus(str, Enum):
    TRUSTED = "trusted"
    SUSPICIOUS = "suspicious"
    INVALID = "invalid"


@dataclass
class VerificationResult:
    """One gate's verdict on one piece of already-produced output.

    `score` is a confidence in [0, 1] when the source gate provides one
    (tables do; text quality is binary and reports None rather than a
    fabricated number)."""

    status: VerificationStatus
    source: str  # which gate produced this: "text_quality" | "table_quality"
    reasons: list[str] = field(default_factory=list)
    score: float | None = None

    def as_dict(self) -> dict:
        return {
            "status": self.status.value,
            "source": self.source,
            "reasons": list(self.reasons),
            "score": self.score,
        }


def from_text_quality(report: TextQualityReport) -> VerificationResult:
    status = VerificationStatus.SUSPICIOUS if report.suspicious else VerificationStatus.TRUSTED
    return VerificationResult(status=status, source="text_quality", reasons=list(report.reasons))


def from_table_confidence(confidence: float | None, warning: str | None = None) -> VerificationResult:
    """Table.confidence already encodes `assess_table`'s verdict: unset (or
    the extraction default) means trusted, 0.5 means `medium` severity, 0.25
    means `high` — see `table_quality.py`'s call site. This is a read of an
    existing verdict, not a new judgment."""
    reasons = [warning] if warning else []
    if confidence is None or confidence >= 0.75:
        return VerificationResult(status=VerificationStatus.TRUSTED, source="table_quality",
                                   reasons=reasons, score=confidence)
    if confidence <= 0.3:
        return VerificationResult(status=VerificationStatus.INVALID, source="table_quality",
                                   reasons=reasons, score=confidence)
    return VerificationResult(status=VerificationStatus.SUSPICIOUS, source="table_quality",
                               reasons=reasons, score=confidence)


@dataclass
class VerificationSummary:
    trusted: int = 0
    suspicious: int = 0
    invalid: int = 0

    def record(self, status: VerificationStatus) -> None:
        if status is VerificationStatus.TRUSTED:
            self.trusted += 1
        elif status is VerificationStatus.SUSPICIOUS:
            self.suspicious += 1
        else:
            self.invalid += 1

    @property
    def total(self) -> int:
        return self.trusted + self.suspicious + self.invalid

    def as_dict(self) -> dict:
        return {"trusted": self.trusted, "suspicious": self.suspicious,
                "invalid": self.invalid, "total": self.total}


def verify_element_text(element: Element, thresholds: TextQualityThresholds | None = None) -> VerificationResult | None:
    """Verify one element's text. Returns None for elements with no text to
    judge (images, empty cells) rather than a fabricated TRUSTED verdict —
    "not applicable" and "checked and fine" are different claims."""
    if not element.text:
        return None
    report = assess_text(element.text, thresholds)
    if "insufficient_text" in report.reasons and len(report.reasons) == 1:
        return None
    return from_text_quality(report)


def verify_document(
    document: Document, thresholds: TextQualityThresholds | None = None
) -> VerificationSummary:
    """Run verification over every already-assembled element and table in
    `document`, in place: each `Element.extra["verification"]` and
    `Table.confidence`-derived verdict is recorded, and anything not TRUSTED
    is appended to its page's `notes` so the finding reaches the same place
    every other stage already reports through — no separate file to
    cross-reference to see what a document's output actually contains.

    Returns an aggregate count, meant for the run log, not for making a
    decision by itself: a summary that hides *which* element is suspicious
    is no more useful here than a blended table score was in experiment 010.
    """
    summary = VerificationSummary()
    for page in document.pages:
        for element in page.elements:
            result = verify_element_text(element, thresholds)
            if result is None:
                continue
            element.extra["verification"] = result.as_dict()
            summary.record(result.status)
            if result.status is not VerificationStatus.TRUSTED:
                page.notes.append(
                    f"verification: {element.id} {result.status.value} — {'; '.join(result.reasons)}"
                )

        for table in page.tables:
            result = from_table_confidence(table.confidence)
            summary.record(result.status)
            # Table.confidence already reached page.notes via the table
            # backend's own warning at extraction time (`as_warning`) when
            # not trusted — recorded here in the summary only, to avoid a
            # duplicate note for the same finding.

    return summary
