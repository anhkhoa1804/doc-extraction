"""Opt-in, fail-closed page-level CJK OCR route.

The baseline Docling layout pass runs before OCR and already materializes its
baseline OCR result in the shared page cache. On OSD-Han pages this wrapper
tries the existing direct EasyOCR backend with ``ch_sim,en`` and falls back
to that cached baseline result for empty, malformed, exceptional, or
catastrophically collapsed output. The route is never enabled by default.
"""
from __future__ import annotations

import math
import re
import shutil
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from doc_extraction.ingest.language_routing import (
    MIN_BASELINE_CHARS_FOR_COLLAPSE,
    SPECIALIZED_TEXT_COLLAPSE_RATIO,
    select_ocr_language_route,
)
from doc_extraction.pipelines.base import OCRBackend, OCRResult, OCRToken, PageInput
from doc_extraction.schemas.element import BBox
from doc_extraction.utils.limits import (
    current_ocr_output_limit,
    current_subprocess_timeout,
)
from doc_extraction.utils.subprocesses import run_bounded

_SCRIPT_RE = re.compile(r"^Script:\s*(.+?)\s*$", re.MULTILINE)
_CONFIDENCE_RE = re.compile(r"^Script confidence:\s*([0-9.]+)\s*$", re.MULTILINE)


def detect_osd_script(image_path: Path) -> tuple[str | None, float | None]:
    """Run bounded Tesseract OSD; failures are unavailable, never a route."""
    executable = shutil.which("tesseract")
    if executable is None:
        return None, None
    configured_timeout = current_subprocess_timeout()
    timeout = min(10.0, configured_timeout) if configured_timeout is not None else 10.0
    try:
        result = run_bounded(
            [executable, str(image_path.resolve()), "stdout", "--psm", "0", "-l", "osd"],
            timeout=timeout,
            max_output_bytes=min(current_ocr_output_limit(), 64 * 1024),
        )
    except Exception:  # noqa: BLE001 - OSD failure must fail closed to baseline OCR.
        return None, None
    if result.returncode != 0:
        return None, None
    output = f"{result.stdout}\n{result.stderr}"
    script_match = _SCRIPT_RE.search(output)
    confidence_match = _CONFIDENCE_RE.search(output)
    if not script_match:
        return None, None
    confidence = None
    if confidence_match:
        try:
            parsed = float(confidence_match.group(1))
            confidence = parsed if math.isfinite(parsed) else None
        except ValueError:
            pass
    return script_match.group(1), confidence


def _token_text_stats(result: Any) -> tuple[int, int, bool]:
    """Return token count, non-whitespace characters, and structural validity."""
    if not isinstance(result, OCRResult) or not isinstance(result.tokens, list):
        return 0, 0, False
    count = 0
    chars = 0
    for token in result.tokens:
        if (
            not isinstance(token, OCRToken)
            or not isinstance(token.text, str)
            or not isinstance(token.bbox, BBox)
            or (
                token.confidence is not None
                and (
                    not isinstance(token.confidence, int | float)
                    or not math.isfinite(token.confidence)
                )
            )
        ):
            return len(result.tokens), chars, False
        if not all(math.isfinite(v) for v in (token.bbox.x0, token.bbox.y0, token.bbox.x1, token.bbox.y1)):
            return len(result.tokens), chars, False
        if token.bbox.x1 < token.bbox.x0 or token.bbox.y1 < token.bbox.y0:
            return len(result.tokens), chars, False
        count += 1
        chars += sum(not char.isspace() for char in token.text)
    return count, chars, True


class RoutedOCRBackend:
    """Experimental OCRBackend decorator with runtime-only route telemetry."""

    name = "experimental_osd_cjk_router"

    def __init__(
        self,
        baseline: OCRBackend,
        specialized: OCRBackend,
        *,
        osd: Callable[[Path], tuple[str | None, float | None]] = detect_osd_script,
    ) -> None:
        self.baseline = baseline
        self.specialized = specialized
        self.osd = osd

    def is_available(self) -> bool:
        return self.baseline.is_available() and self.specialized.is_available()

    @staticmethod
    def _with_diagnostics(result: OCRResult, diagnostics: dict[str, Any]) -> OCRResult:
        return OCRResult(
            tokens=list(result.tokens),
            backend=result.backend,
            warnings=list(result.warnings),
            diagnostics=diagnostics,
        )

    def recognize(self, page: PageInput) -> OCRResult:
        if page.image_path is None:
            baseline = self.baseline.recognize(page)
            return self._with_diagnostics(
                baseline,
                {"state": "BASELINE_ONLY", "reason": "page_image_unavailable"},
            )

        started = time.perf_counter()
        osd_started = time.perf_counter()
        try:
            script, confidence = self.osd(page.image_path)
            osd_error = None
        except Exception as exc:  # noqa: BLE001 - unavailable OSD is a baseline route.
            script, confidence = None, None
            osd_error = type(exc).__name__
        osd_seconds = time.perf_counter() - osd_started
        route = select_ocr_language_route(script)
        common: dict[str, Any] = {
            "osd_available": script is not None,
            "osd_script": script,
            "osd_confidence": confidence,
            "route_reason": route.reason,
            "baseline_languages": ["en", "vi"],
            "specialized_languages": ["ch_sim", "en"],
            "osd_seconds": round(osd_seconds, 6),
            "specialized_backend": self.specialized.name,
            "fallback": False,
        }
        if osd_error:
            common["osd_error_type"] = osd_error

        if not route.is_han_route:
            baseline_started = time.perf_counter()
            result = self.baseline.recognize(page)
            baseline_seconds = time.perf_counter() - baseline_started
            count, chars, valid = _token_text_stats(result)
            return self._with_diagnostics(
                result,
                {
                    **common,
                    "state": "BASELINE_ONLY",
                    "selected_backend": result.backend,
                    "fallback_reason": None,
                    "specialized_token_count": None,
                    "baseline_token_count": count,
                    "baseline_nonspace_chars": chars,
                    "baseline_result_valid": valid,
                    "baseline_seconds": round(baseline_seconds, 6),
                    "baseline_fallback_seconds": 0.0,
                    "specialized_seconds": 0.0,
                    "total_router_seconds": round(time.perf_counter() - started, 6),
                },
            )

        specialized_started = time.perf_counter()
        try:
            candidate = self.specialized.recognize(page)
            candidate_error = None
        except Exception as exc:  # noqa: BLE001 - specialized failures trigger fallback.
            candidate = None
            candidate_error = type(exc).__name__
        specialized_seconds = time.perf_counter() - specialized_started
        candidate_count, candidate_chars, candidate_valid = _token_text_stats(candidate)

        fallback_reason: str | None = None
        state = "SPECIALIZED_OK"
        if candidate_error:
            state, fallback_reason = "SPECIALIZED_EXCEPTION", "specialized_exception"
        elif candidate is None:
            state, fallback_reason = "SPECIALIZED_MALFORMED", "specialized_missing_result"
        elif not candidate_valid:
            state, fallback_reason = "SPECIALIZED_MALFORMED", "specialized_invalid_tokens"
        elif candidate_count == 0 or candidate_chars == 0:
            state, fallback_reason = "SPECIALIZED_EMPTY", "specialized_no_text_tokens"

        baseline_result: OCRResult | None = None
        baseline_seconds = 0.0
        baseline_count: int | None = None
        baseline_chars: int | None = None
        baseline_valid: bool | None = None
        if fallback_reason is None:
            # With the supported default (Docling), the layout pass populated
            # this result in its page cache. Other baseline backends may incur
            # a second OCR pass only on Han-routed pages.
            baseline_started = time.perf_counter()
            try:
                baseline_result = self.baseline.recognize(page)
                baseline_count, baseline_chars, baseline_valid = _token_text_stats(baseline_result)
            except Exception as exc:  # noqa: BLE001 - baseline failure is telemetry, not route success.
                common["baseline_error_type"] = type(exc).__name__
            baseline_seconds = time.perf_counter() - baseline_started
            if (
                baseline_result is not None
                and baseline_valid
                and baseline_chars is not None
                and baseline_chars >= MIN_BASELINE_CHARS_FOR_COLLAPSE
                and candidate_chars < SPECIALIZED_TEXT_COLLAPSE_RATIO * baseline_chars
            ):
                state, fallback_reason = "SPECIALIZED_SUSPICIOUS", "text_length_collapse_vs_cached_baseline"
            replacement_count = sum(token.text.count("\ufffd") for token in candidate.tokens)
            if candidate_chars and replacement_count / candidate_chars > 0.02:
                state, fallback_reason = "SPECIALIZED_SUSPICIOUS", "replacement_character_rate"
            if not any(char.isalnum() for token in candidate.tokens for char in token.text):
                state, fallback_reason = "SPECIALIZED_SUSPICIOUS", "no_alphanumeric_or_han_characters"

        if fallback_reason is not None:
            common_diag = {
                **common,
                "state": state,
                "fallback": True,
                "selected_backend": (
                    baseline_result.backend if baseline_result is not None else None
                ),
                "fallback_reason": fallback_reason,
                "candidate_error_type": candidate_error,
                "specialized_token_count": candidate_count,
                "specialized_nonspace_chars": candidate_chars,
                "specialized_seconds": round(specialized_seconds, 6),
                "baseline_token_count": baseline_count,
                "baseline_nonspace_chars": baseline_chars,
                "baseline_result_valid": baseline_valid,
                "baseline_seconds": round(baseline_seconds, 6),
                "baseline_fallback_seconds": round(baseline_seconds, 6),
                "total_router_seconds": round(time.perf_counter() - started, 6),
            }
            if baseline_result is None:
                # For an empty/exceptional candidate, retry the baseline here
                # if it was not already fetched for quality comparison.
                fallback_started = time.perf_counter()
                baseline_result = self.baseline.recognize(page)
                common_diag["baseline_seconds"] = round(
                    common_diag["baseline_seconds"] + time.perf_counter() - fallback_started, 6
                )
                common_diag["baseline_fallback_seconds"] = round(
                    time.perf_counter() - fallback_started, 6
                )
                baseline_count, baseline_chars, baseline_valid = _token_text_stats(baseline_result)
                common_diag.update(
                    baseline_token_count=baseline_count,
                    baseline_nonspace_chars=baseline_chars,
                    baseline_result_valid=baseline_valid,
                    selected_backend=baseline_result.backend,
                    total_router_seconds=round(time.perf_counter() - started, 6),
                )
            selected = self._with_diagnostics(baseline_result, common_diag)
            selected.warnings.append(f"experimental OCR route fallback: {fallback_reason}")
            return selected

        assert candidate is not None
        candidate.diagnostics = {
            **common,
            "state": "SPECIALIZED_OK",
            "selected_backend": candidate.backend,
            "fallback_reason": None,
            "specialized_token_count": candidate_count,
            "specialized_nonspace_chars": candidate_chars,
            "specialized_seconds": round(specialized_seconds, 6),
            "baseline_token_count": baseline_count,
            "baseline_nonspace_chars": baseline_chars,
            "baseline_result_valid": baseline_valid,
            "baseline_seconds": round(baseline_seconds, 6),
            "baseline_fallback_seconds": 0.0,
            "total_router_seconds": round(time.perf_counter() - started, 6),
        }
        return candidate
