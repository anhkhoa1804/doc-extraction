"""Scan Recovery v1 — the reusable page-level recovery API, built entirely
from already-validated primitives.

    verification / disagreement
            v
        region bbox
            v
      targeted re-OCR
            v
        verify
            v
    replace only if better

Why this exists, and why it is not a second extraction pipeline
------------------------------------------------------------------
Forensically tracing 6 real scan failures (`experiments/015_scan_recovery/`)
found that Docling's own OCR occasionally merges several lines into one
recognized block whose internal word order comes out scrambled (e.g. "Kính
gửi: Phòng Tài chính - Kế toán" reassembled as "Kính ... Kế toán ... gửi:
phải" -- every word present, order destroyed). This is invisible to
`text_quality.assess_text` (the scrambled text is still valid, correctly-
scripted Vietnamese -- plausibility checks decoding sanity, not word
order) but visible to `verification.assess_ocr_agreement`: a direct
EasyOCR pass over the same pixels reads the line as one coherent unit
(EasyOCR's finer per-line tokens don't merge across lines the way
Docling's did), so word-Jaccard agreement between the two readings is low
even though both readings are individually plausible-looking text.

This module is deliberately a thin orchestration of three already-shipped,
already-tested pieces -- `assess_ocr_agreement` (the trigger),
`evidence_fusion.fuse_page` (the action, already fixed and PROMOTEd in the
prior milestone), and `text_quality.assess_text` (part of the verify-again
gate) -- not a new recognition path. Per the architecture target:

    EXTRACT -> VERIFY -> RECOVER IF NECESSARY -> VERIFY AGAIN -> IR

this module *is* the RECOVER step. It never re-runs layout or table
detection, never invents a new OCR call type, and never touches an
element whose old evidence was not already suspicious.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from doc_extraction.ingest.evidence_fusion import FusionStatus, assemble_fused_text, fuse_page
from doc_extraction.ingest.text_quality import assess_text
from doc_extraction.ingest.verification import VerificationStatus, assess_ocr_agreement
from doc_extraction.pipelines.base import OCRToken, PageInput, _center_in
from doc_extraction.schemas.element import Element


@dataclass
class RecoveryRecord:
    """One element's recovery attempt, kept for provenance -- "why was this
    text selected?" per the mission's own standing requirement."""

    element_id: str
    trigger: str  # "agreement_low" | "no_easyocr_evidence" (skipped) | "not_suspicious" (skipped)
    action: str  # "fuse_with_easyocr" | "none"
    source: str  # "docling+easyocr" | "docling_only"
    old_text: str
    old_quality: float | None  # the agreement score that triggered recovery, if any
    new_text: str | None
    new_quality: str | None  # the fused group's FusionStatus, if a fusion was attempted
    decision: str  # "replaced" | "kept_old"
    reasons: list[str] = field(default_factory=list)


@dataclass
class RecoverySummary:
    records: list[RecoveryRecord] = field(default_factory=list)
    replaced: int = 0
    kept: int = 0
    skipped_not_suspicious: int = 0

    def as_dict(self) -> dict:
        return {
            "replaced": self.replaced, "kept": self.kept,
            "skipped_not_suspicious": self.skipped_not_suspicious,
            "records": [r.__dict__ for r in self.records],
        }


def recover_page_elements(
    page,
    page_image_path: Path,
    easyocr_backend,
    page_width: float,
    page_height: float,
    dpi: int | None = None,
) -> RecoverySummary:
    """Cross-check every text-bearing `Element` already on `page` against a
    fresh direct-EasyOCR pass over the same rendered image, and replace an
    element's text only when (a) cross-backend agreement flags the old
    reading as suspicious -- a trigger `assess_text` alone cannot raise for
    word-order-only defects -- and (b) `evidence_fusion`'s own verdict on
    the merged evidence is TRUSTED, not merely different. Never touches an
    element `assess_ocr_agreement` did not flag."""
    summary = RecoverySummary()
    easyocr_result = easyocr_backend.recognize(
        PageInput(page_index=0, width=page_width, height=page_height, image_path=page_image_path, dpi=dpi)
    )

    for element in page.elements:
        if not element.text or element.bbox is None:
            continue

        matched = [t for t in easyocr_result.tokens if _center_in(t.bbox, element.bbox)]
        if not matched:
            summary.skipped_not_suspicious += 1
            continue

        easyocr_text = " ".join(t.text for t in sorted(matched, key=lambda t: (t.bbox.y0, t.bbox.x0)))
        agreement = assess_ocr_agreement(element.text, easyocr_text, source_a="docling", source_b="easyocr")

        if agreement.status is not VerificationStatus.SUSPICIOUS:
            summary.skipped_not_suspicious += 1
            continue

        docling_anchor = [OCRToken(text=element.text, bbox=element.bbox, confidence=None)]
        groups = fuse_page(docling_anchor, matched)
        fused_text = assemble_fused_text(groups)
        fusion_status = groups[0].status if groups else FusionStatus.CONFLICT
        fusion_decision = groups[0].decision if groups else "conflict"

        record = RecoveryRecord(
            element_id=element.id, trigger="agreement_low", action="fuse_with_easyocr",
            source="docling+easyocr", old_text=element.text, old_quality=agreement.score,
            new_text=fused_text, new_quality=fusion_status.value,
            decision="kept_old", reasons=list(agreement.reasons),
        )

        # "Verified better" accepts two of evidence_fusion's own decisions,
        # never its "conflict" one: `keep_both_agree` (TRUSTED -- the two
        # sources concur) and `keep_both_partial` (SUSPICIOUS, similarity in
        # [0.3, 0.7) -- real overlap, likely the same content with extra or
        # missing words, still a genuine union rather than two competing
        # claims). `conflict` (similarity < 0.3) is excluded deliberately:
        # its `fused_text()` also concatenates old+new, so a word-subset
        # check cannot distinguish "safe union" from "unsafe conflict" here
        # -- both trivially contain the old text as a substring -- the
        # similarity band evidence_fusion already computed is what actually
        # carries that distinction, so this reuses it rather than
        # re-deriving a weaker proxy.
        verified_better = (
            fused_text.strip()
            and fused_text != element.text
            and not assess_text(fused_text).suspicious
            and fusion_decision in ("keep_both_agree", "keep_both_partial")
        )
        if verified_better:
            element.extra["recovery"] = {"old_text": element.text, "trigger": "agreement_low",
                                          "agreement": agreement.score}
            element.text = fused_text
            record.decision = "replaced"
            summary.replaced += 1
        else:
            record.reasons.append(f"fusion status={fusion_status.value}, not accepted as verified-better")
            summary.kept += 1

        summary.records.append(record)

    return summary
