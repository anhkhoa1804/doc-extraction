from pathlib import Path

from doc_extraction.backends.routed_ocr_backend import RoutedOCRBackend
from doc_extraction.pipelines.base import OCRResult, OCRToken, PageInput
from doc_extraction.schemas.element import BBox
from doc_extraction.stages.ocr import run_ocr
from doc_extraction.utils.serde import read_json


def _result(text: str, backend: str = "stub") -> OCRResult:
    if not text:
        return OCRResult(backend=backend)
    return OCRResult(
        tokens=[OCRToken(text=text, bbox=BBox(x0=1, y0=1, x1=50, y1=20), confidence=0.9)],
        backend=backend,
    )


class _Backend:
    def __init__(self, result=None, error: Exception | None = None, name="stub"):
        self.result = result
        self.error = error
        self.name = name
        self.calls = 0

    def is_available(self):
        return True

    def recognize(self, _page):
        self.calls += 1
        if self.error:
            raise self.error
        return self.result


def _page() -> PageInput:
    return PageInput(page_index=0, width=100, height=100, image_path=Path("page.png"))


def test_non_han_uses_only_baseline_and_records_route_diagnostics():
    baseline = _Backend(_result("Vietnamese baseline", "docling"), name="docling")
    specialized = _Backend(_result("中文", "easyocr"), name="easyocr")
    routed = RoutedOCRBackend(baseline, specialized, osd=lambda _p: ("Latin", 4.2))

    result = routed.recognize(_page())

    assert result.backend == "docling"
    assert baseline.calls == 1
    assert specialized.calls == 0
    assert result.diagnostics["state"] == "BASELINE_ONLY"
    assert result.diagnostics["osd_script"] == "Latin"


def test_han_uses_specialized_output_and_records_content_free_telemetry():
    baseline = _Backend(_result("base", "docling"), name="docling")
    specialized = _Backend(_result("中文识别内容", "easyocr"), name="easyocr")
    routed = RoutedOCRBackend(baseline, specialized, osd=lambda _p: ("Han", 7.0))

    result = routed.recognize(_page())

    assert result.backend == "easyocr"
    assert result.diagnostics["state"] == "SPECIALIZED_OK"
    assert result.diagnostics["fallback"] is False
    assert "中文识别内容" not in str(result.diagnostics)


def test_empty_specialized_output_falls_back_and_records_reason():
    baseline = _Backend(_result("valid baseline text", "docling"), name="docling")
    specialized = _Backend(_result("", "easyocr"), name="easyocr")
    routed = RoutedOCRBackend(baseline, specialized, osd=lambda _p: ("Han", 1.43))

    result = routed.recognize(_page())

    assert result.backend == "docling"
    assert result.tokens[0].text == "valid baseline text"
    assert result.diagnostics["state"] == "SPECIALIZED_EMPTY"
    assert result.diagnostics["fallback_reason"] == "specialized_no_text_tokens"
    assert result.diagnostics["fallback"] is True
    assert result.diagnostics["selected_backend"] == "docling"
    assert any("experimental OCR route fallback" in warning for warning in result.warnings)


def test_specialized_exception_falls_back_to_baseline():
    baseline = _Backend(_result("baseline", "docling"), name="docling")
    specialized = _Backend(error=RuntimeError("failure"), name="easyocr")
    routed = RoutedOCRBackend(baseline, specialized, osd=lambda _p: ("Han", 3.0))

    result = routed.recognize(_page())

    assert result.backend == "docling"
    assert result.diagnostics["state"] == "SPECIALIZED_EXCEPTION"
    assert result.diagnostics["candidate_error_type"] == "RuntimeError"
    assert result.diagnostics["fallback"] is True


def test_malformed_specialized_output_falls_back():
    baseline = _Backend(_result("baseline", "docling"), name="docling")
    specialized = _Backend(["not", "an", "OCRResult"], name="easyocr")
    routed = RoutedOCRBackend(baseline, specialized, osd=lambda _p: ("Han", 3.0))

    result = routed.recognize(_page())

    assert result.backend == "docling"
    assert result.diagnostics["state"] == "SPECIALIZED_MALFORMED"
    assert result.diagnostics["fallback"] is True


def test_severe_nonempty_length_collapse_falls_back_without_ground_truth():
    baseline = _Backend(_result("baseline text " * 10, "docling"), name="docling")
    specialized = _Backend(_result("短", "easyocr"), name="easyocr")
    routed = RoutedOCRBackend(baseline, specialized, osd=lambda _p: ("Han", 5.0))

    result = routed.recognize(_page())

    assert result.backend == "docling"
    assert result.diagnostics["state"] == "SPECIALIZED_SUSPICIOUS"
    assert result.diagnostics["fallback_reason"] == "text_length_collapse_vs_cached_baseline"


def test_live_ocr_stage_persists_route_telemetry_without_copying_text(tmp_path):
    baseline = _Backend(_result("base " * 10, "docling"), name="docling")
    specialized_text = "中文路由结果" * 10
    specialized = _Backend(_result(specialized_text, "easyocr"), name="easyocr")
    routed = RoutedOCRBackend(baseline, specialized, osd=lambda _p: ("Han", 5.0))

    run_ocr(_page(), routed, tmp_path / "ocr")
    artifact = read_json(tmp_path / "ocr" / "page-001.json")

    assert artifact["diagnostics"]["state"] == "SPECIALIZED_OK"
    assert artifact["diagnostics"]["selected_backend"] == "easyocr"
    assert specialized_text not in str(artifact["diagnostics"])
    assert artifact["tokens"][0]["text"] == specialized_text


def test_osd_failure_safely_selects_baseline():
    baseline = _Backend(_result("baseline", "docling"), name="docling")
    specialized = _Backend(_result("中文", "easyocr"), name="easyocr")

    def failed_osd(_path):
        raise OSError("not installed")

    result = RoutedOCRBackend(baseline, specialized, osd=failed_osd).recognize(_page())

    assert result.backend == "docling"
    assert result.diagnostics["state"] == "BASELINE_ONLY"
    assert result.diagnostics["osd_available"] is False
    assert result.diagnostics["osd_error_type"] == "OSError"
