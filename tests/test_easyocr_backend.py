"""EasyOCRBackend — the direct-OCR `OCRBackend` adapter (experiment 012).

All tests stub the `easyocr.Reader` instance directly (`backend._reader =
...`), bypassing `_get_reader()`'s lazy construction, so none of this needs
the real model weights or a GPU. `test_coordinate_placement_matches_a_known_layout`
is the one exception that talks to the real EasyOCR model — it exists
specifically to validate the coordinate-space claim in the module docstring
against ground truth, which a stub cannot do.
"""
from __future__ import annotations

import numpy as np
import pytest

from doc_extraction.backends.easyocr_backend import DEFAULT_LANGUAGES, EasyOCRBackend
from doc_extraction.pipelines.base import PageInput

VI_TEXT = "Độc lập Tự do Hạnh phúc"


class _StubReader:
    def __init__(self, detections):
        self.detections = detections
        self.calls = []

    def readtext(self, path, detail=1):
        self.calls.append(path)
        return self.detections


def _backend_with(detections, device="cpu") -> EasyOCRBackend:
    backend = EasyOCRBackend(device=device)
    backend._reader = _StubReader(detections)
    return backend


def _page(tmp_path, name="page.png") -> PageInput:
    path = tmp_path / name
    path.write_bytes(b"not a real png, never opened by the stub reader")
    return PageInput(page_index=0, width=400, height=200, image_path=path)


def test_defaults_to_en_and_vi():
    """Production language config stays en+vi unless explicitly overridden —
    never silently widened to another language for benchmark convenience."""
    backend = EasyOCRBackend()
    assert backend.languages == DEFAULT_LANGUAGES == ["en", "vi"]


def test_english_token_recovered(tmp_path):
    backend = _backend_with([([[10, 10], [60, 10], [60, 30], [10, 30]], "Hello", 0.95)])
    result = backend.recognize(_page(tmp_path))
    assert [t.text for t in result.tokens] == ["Hello"]
    assert result.backend == "easyocr"


def test_vietnamese_diacritics_survive(tmp_path):
    backend = _backend_with([([[10, 10], [200, 10], [200, 30], [10, 30]], VI_TEXT, 0.9)])
    result = backend.recognize(_page(tmp_path))
    assert result.tokens[0].text == VI_TEXT


def test_empty_result_when_nothing_detected(tmp_path):
    backend = _backend_with([])
    result = backend.recognize(_page(tmp_path))
    assert result.tokens == []
    assert result.backend == "easyocr"


def test_blank_detection_is_dropped_not_emitted_as_empty_token(tmp_path):
    backend = _backend_with([([[0, 0], [10, 0], [10, 10], [0, 10]], "   ", 0.4)])
    result = backend.recognize(_page(tmp_path))
    assert result.tokens == []


def test_multiple_tokens_preserve_order_and_each_confidence(tmp_path):
    backend = _backend_with([
        ([[0, 0], [40, 0], [40, 20], [0, 20]], "one", 0.99),
        ([[0, 30], [40, 30], [40, 50], [0, 50]], "two", 0.42),
    ])
    result = backend.recognize(_page(tmp_path))
    assert [t.text for t in result.tokens] == ["one", "two"]
    assert result.tokens[0].confidence == pytest.approx(0.99)
    assert result.tokens[1].confidence == pytest.approx(0.42)


def test_confidence_is_never_none_unlike_the_docling_path(tmp_path):
    """The entire reason this backend exists: DoclingBackend.recognize()
    hard-codes confidence=None because docling's TextItem has no such field.
    EasyOCR's real per-detection confidence must reach OCRToken unchanged."""
    backend = _backend_with([([[0, 0], [10, 0], [10, 10], [0, 10]], "x", 0.5)])
    result = backend.recognize(_page(tmp_path))
    assert result.tokens[0].confidence is not None
    assert result.tokens[0].confidence == pytest.approx(0.5)


def test_polygon_bbox_conversion_is_axis_aligned_min_max(tmp_path):
    """EasyOCR's 4-point polygon collapses to an axis-aligned BBox by
    min/max over the four corners, with no flip and no rescale (see the
    module docstring on why that differs from the Docling path)."""
    backend = _backend_with([([[15, 25], [95, 20], [98, 55], [12, 60]], "skewed", 0.8)])
    result = backend.recognize(_page(tmp_path))
    bbox = result.tokens[0].bbox
    assert (bbox.x0, bbox.y0, bbox.x1, bbox.y1) == (12.0, 20.0, 98.0, 60.0)


def test_numpy_int_polygon_coordinates_are_handled(tmp_path):
    """EasyOCR returns polygon coordinates as numpy.int32, not plain
    Python ints/floats — verified against the real library output."""
    poly = [[np.int32(10), np.int32(10)], [np.int32(50), np.int32(10)],
             [np.int32(50), np.int32(30)], [np.int32(10), np.int32(30)]]
    backend = _backend_with([(poly, "np", 0.7)])
    result = backend.recognize(_page(tmp_path))
    assert (result.tokens[0].bbox.x0, result.tokens[0].bbox.y0) == (10.0, 10.0)


def test_no_image_path_returns_empty_with_warning():
    backend = EasyOCRBackend()
    page = PageInput(page_index=0, width=100, height=100, image_path=None)
    result = backend.recognize(page)
    assert result.tokens == []
    assert result.warnings


def test_reader_is_not_constructed_until_recognize_is_called():
    """`device: auto`'s GPU probe must never trigger a CUDA context merely
    by constructing this backend to inspect whether a GPU is free — the
    Reader (and its `gpu=True` CUDA init) must be built lazily."""
    backend = EasyOCRBackend(device="cuda")
    assert backend._reader is None


def test_cuda_device_is_requested_from_a_mocked_reader(monkeypatch, tmp_path):
    """The device string reaches easyocr.Reader's `gpu` flag correctly,
    without actually touching CUDA — the constructor call itself is mocked."""
    calls = {}

    class _FakeEasyOCRModule:
        class Reader:
            def __init__(self, lang_list, gpu, verbose):
                calls["lang_list"] = lang_list
                calls["gpu"] = gpu

            def readtext(self, path, detail=1):
                return []

    import sys
    monkeypatch.setitem(sys.modules, "easyocr", _FakeEasyOCRModule())

    backend = EasyOCRBackend(device="cuda", languages=["en", "vi"])
    backend.recognize(_page(tmp_path))

    assert calls["gpu"] is True
    assert calls["lang_list"] == ["en", "vi"]


def test_coordinate_placement_matches_a_known_layout(tmp_path):
    """Ground-truth check against the real model: text drawn at a known
    pixel position must be detected at (approximately) that position, in
    top-left-origin, +y-down pixel space with no flip and no rescale.
    Guards the coordinate claim this backend's whole value proposition
    (a token a caller can trust the geometry of) rests on.
    """
    pytest.importorskip("easyocr")
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (400, 200), "white")
    ImageDraw.Draw(img).text((50, 60), "HELLO", fill="black")
    path = tmp_path / "known.png"
    img.save(path)

    backend = EasyOCRBackend(device="cpu")
    result = backend.recognize(PageInput(page_index=0, width=400, height=200, image_path=path))

    assert len(result.tokens) == 1
    token = result.tokens[0]
    assert token.text.upper() == "HELLO"
    # Detected box must be close to where the text was actually drawn, not
    # merely present somewhere on the page.
    assert 30 <= token.bbox.x0 <= 60
    assert 45 <= token.bbox.y0 <= 75
    assert token.bbox.x1 < 400 and token.bbox.y1 < 200
