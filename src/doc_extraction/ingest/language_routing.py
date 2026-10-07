"""Deterministic route-selection helpers for the opt-in CJK OCR experiment.

OSD and OCR execution live in the experimental backend adapter; the helpers
here remain pure so route choice and baseline selection can be tested without
models. The pipeline default is unchanged and routing is disabled unless the
explicit experimental config toggle is enabled.
"""
from __future__ import annotations

from dataclasses import dataclass

from doc_extraction.schemas.page import Page

BASELINE_OCR_LANGUAGES = ("en", "vi")
HAN_OCR_LANGUAGES = ("ch_sim", "en")
MIN_BASELINE_CHARS_FOR_COLLAPSE = 40
SPECIALIZED_TEXT_COLLAPSE_RATIO = 0.5
_EMPTY_OCR_WARNING = "OCR returned no text tokens for "


@dataclass(frozen=True)
class LanguageRoute:
    languages: tuple[str, ...]
    reason: str

    @property
    def is_han_route(self) -> bool:
        return self.languages == HAN_OCR_LANGUAGES


@dataclass(frozen=True)
class RouteSelection:
    selected_markdown: str
    used_baseline_fallback: bool
    reason: str | None = None
    selected_page: Page | None = None


def select_ocr_language_route(osd_script: str | None) -> LanguageRoute:
    """Route only a positive OSD Han result; missing/error/non-Han stays baseline."""
    if isinstance(osd_script, str) and osd_script.strip().casefold() == "han":
        return LanguageRoute(HAN_OCR_LANGUAGES, "tesseract_osd_han")
    reason = "tesseract_osd_unavailable" if not osd_script else "tesseract_osd_non_han"
    return LanguageRoute(BASELINE_OCR_LANGUAGES, reason)


def select_routed_markdown(
    *,
    candidate_markdown: object | None,
    baseline_markdown: str,
    candidate_page: Page | None = None,
    baseline_page: Page | None = None,
    candidate_error: str | None = None,
    candidate_valid: bool = True,
) -> RouteSelection:
    """Accept a healthy specialized result or retain the baseline result.

    Triggers are runtime-observable only: inference exception/missing or
    invalid candidate, whitespace-only serialization, or Docling's explicit
    warning that text-bearing regions received no OCR tokens. No filenames,
    labels, annotations, or evaluator values are accepted by this function.
    """
    reason: str | None = None
    if candidate_error is not None:
        reason = "candidate_ocr_or_pipeline_error"
    elif candidate_markdown is None:
        reason = "candidate_result_missing"
    elif not isinstance(candidate_markdown, str):
        reason = "candidate_result_malformed"
    elif not candidate_valid:
        reason = "candidate_result_invalid"
    elif not candidate_markdown.strip():
        reason = "candidate_markdown_empty"
    elif candidate_page is not None and any(
        _EMPTY_OCR_WARNING in note for note in candidate_page.notes
    ):
        reason = "candidate_ocr_empty_for_detected_regions"
    elif _text_length_collapsed(candidate_markdown, baseline_markdown):
        reason = "candidate_text_length_collapse"

    if reason is not None:
        return RouteSelection(
            selected_markdown=baseline_markdown,
            used_baseline_fallback=True,
            reason=reason,
            selected_page=baseline_page,
        )
    return RouteSelection(
        selected_markdown=candidate_markdown,
        used_baseline_fallback=False,
        selected_page=candidate_page,
    )


def _text_length_collapsed(candidate: str, baseline: str) -> bool:
    """Catch severe candidate shrink only when baseline carries enough text.

    This is a conservative, content-free safety signal, not a quality score.
    Thresholds were checked against the saved 50-page paired CJK output
    cohort; they remain experimental until live multilingual validation.
    """
    baseline_chars = sum(not char.isspace() for char in baseline)
    candidate_chars = sum(not char.isspace() for char in candidate)
    return (
        baseline_chars >= MIN_BASELINE_CHARS_FOR_COLLAPSE
        and candidate_chars < SPECIALIZED_TEXT_COLLAPSE_RATIO * baseline_chars
    )
