"""Step B — What extraction route should be used?

Routes to native_office | digital_pdf | scanned_pdf | image | unknown.

Deliberately does *not* send everything through OCR/VLM. But "has a text
layer" is not sufficient evidence that the text layer is *usable*: a PDF can
carry plentiful text that decodes to garbage because of a broken embedded
font CMap (see ingest/text_quality.py, and the real example in this repo's
own corpus). So PDF routing asks two questions, both cheap:

    1. Is there enough extractable text at all?          (quantity)
    2. Does that text look like correctly-decoded prose?  (quality)

Only if both hold does a PDF take the native path. A PDF with plentiful but
corrupt text is routed to the visual/OCR path exactly like a scan, because
that is what it effectively is.

Per-page detail is preserved in the decision (`PdfTextProfile.per_page`) so
the digital-PDF pipeline can fall back for individual bad pages rather than
condemning a whole document — see pipelines/pdf.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pymupdf

from doc_extraction.config import PipelineConfig
from doc_extraction.ingest.classifier import FileInfo, detect
from doc_extraction.ingest.text_quality import TextQualityThresholds, assess_text

ROUTE_NATIVE_OFFICE = "native_office"
ROUTE_DIGITAL_PDF = "digital_pdf"
ROUTE_SCANNED_PDF = "scanned_pdf"
ROUTE_IMAGE = "image"
ROUTE_UNKNOWN = "unknown"


@dataclass
class PdfTextProfile:
    """Cheap per-page evidence about a PDF's text layer.

    `per_page` maps a 0-based page index to that page's
    `TextQualityReport.as_dict()`, for the sampled pages only.
    """

    page_count: int
    sampled_pages: list[int] = field(default_factory=list)
    text_page_ratio: float = 0.0
    suspicious_page_ratio: float = 0.0
    per_page: dict[int, dict[str, Any]] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "page_count": self.page_count,
            "sampled_pages": list(self.sampled_pages),
            "text_page_ratio": round(self.text_page_ratio, 4),
            "suspicious_page_ratio": round(self.suspicious_page_ratio, 4),
            "per_page": {str(k): v for k, v in self.per_page.items()},
        }


@dataclass
class RouteDecision:
    route: str
    file_info: FileInfo
    reason: str
    pdf_text_ratio: float | None = None
    text_profile: PdfTextProfile | None = None


def _sample_page_indices(total_pages: int, sample_size: int) -> list[int]:
    if total_pages <= sample_size:
        return list(range(total_pages))
    step = total_pages / sample_size
    return sorted({int(i * step) for i in range(sample_size)})


def thresholds_from_config(config: PipelineConfig) -> TextQualityThresholds:
    return TextQualityThresholds(
        min_chars_for_assessment=config.text_quality_min_chars,
        max_mixed_script_word_ratio=config.text_quality_max_mixed_script_word_ratio,
        max_unexpected_script_ratio=config.text_quality_max_unexpected_script_ratio,
        max_replacement_ratio=config.text_quality_max_replacement_ratio,
        max_control_ratio=config.text_quality_max_control_ratio,
        min_alpha_ratio=config.text_quality_min_alpha_ratio,
        max_digit_in_word_ratio=config.text_quality_max_digit_in_word_ratio,
        expected_scripts=tuple(config.text_quality_expected_scripts),
    )


def profile_pdf_text(path: Path, config: PipelineConfig) -> PdfTextProfile:
    """Sample pages and assess both the quantity and the quality of the
    extractable text layer. No rendering, no OCR — this must stay cheap
    enough to run on every PDF before deciding anything."""
    thresholds = thresholds_from_config(config)
    doc = pymupdf.open(path)
    try:
        if doc.page_count == 0:
            return PdfTextProfile(page_count=0)

        indices = _sample_page_indices(doc.page_count, config.digital_pdf_sample_pages)
        per_page: dict[int, dict[str, Any]] = {}
        n_with_text = 0
        n_suspicious = 0

        for i in indices:
            text = doc[i].get_text()
            report = assess_text(text, thresholds)
            per_page[i] = report.as_dict()
            if len(text.strip()) >= config.digital_pdf_min_chars_per_page:
                n_with_text += 1
            if report.suspicious:
                n_suspicious += 1

        n_sampled = len(indices)
        return PdfTextProfile(
            page_count=doc.page_count,
            sampled_pages=indices,
            text_page_ratio=n_with_text / n_sampled,
            suspicious_page_ratio=n_suspicious / n_sampled,
            per_page=per_page,
        )
    finally:
        doc.close()


def route(path: Path, config: PipelineConfig) -> RouteDecision:
    info = detect(path)

    if info.detected_kind in ("docx", "xlsx", "pptx"):
        return RouteDecision(
            ROUTE_NATIVE_OFFICE, info, f"native OOXML container ({info.detected_kind})"
        )

    if info.detected_kind.startswith("image/"):
        return RouteDecision(ROUTE_IMAGE, info, f"raster image ({info.detected_kind})")

    if info.detected_kind == "pdf":
        profile = profile_pdf_text(path, config)

        # 1. Quantity gate — not enough text to work with at all.
        if profile.text_page_ratio < config.digital_pdf_page_ratio:
            reason = (
                f"only {profile.text_page_ratio:.0%} of sampled pages have extractable text "
                f"(< {config.digital_pdf_page_ratio:.0%} threshold)"
            )
            return RouteDecision(ROUTE_SCANNED_PDF, info, reason, profile.text_page_ratio, profile)

        # 2. Quality gate — plenty of text, but is it decodable? A document
        #    whose sampled pages are mostly corrupt is treated as a scan,
        #    because trusting its text layer would produce confident garbage.
        if profile.suspicious_page_ratio > config.text_quality_max_suspicious_page_ratio:
            reason = (
                f"text layer present ({profile.text_page_ratio:.0%} of sampled pages) but "
                f"{profile.suspicious_page_ratio:.0%} of sampled pages fail text-quality checks "
                f"(> {config.text_quality_max_suspicious_page_ratio:.0%}) — likely broken font CMap; "
                f"routing to the visual/OCR path"
            )
            return RouteDecision(ROUTE_SCANNED_PDF, info, reason, profile.text_page_ratio, profile)

        reason = (
            f"{profile.text_page_ratio:.0%} of sampled pages have extractable text and "
            f"pass text-quality checks"
        )
        return RouteDecision(ROUTE_DIGITAL_PDF, info, reason, profile.text_page_ratio, profile)

    return RouteDecision(
        ROUTE_UNKNOWN, info, f"unsupported or unrecognized file kind: {info.detected_kind}"
    )
