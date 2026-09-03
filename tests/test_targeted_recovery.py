"""Targeted OCR recovery v0 — segmentation and the replace-only-if-better
decision rule. Follows `test_easyocr_backend.py`'s convention: stub
`easyocr.Reader` so no GPU or model weights are needed; the crop images
themselves are real PIL images (segmentation genuinely needs pixels)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

from doc_extraction.backends.easyocr_backend import EasyOCRBackend
from doc_extraction.ingest.evidence_fusion import EvidenceGroup, EvidenceToken
from doc_extraction.ingest.targeted_recovery import (
    RESOLVE_MARGIN,
    _otsu_threshold,
    recover_region,
    segment_lines,
)
from doc_extraction.schemas.element import BBox


def _two_line_image(width=200, height=60) -> Image.Image:
    # Grayscale ("L") mode first: `Image.new("RGB", ..., color=255)` fills
    # only the first channel with a scalar color (a real PIL gotcha, not a
    # deliberate choice), which is not white -- converting from a
    # single-band image sidesteps it entirely.
    img = Image.new("L", (width, height), color=255)
    draw = ImageDraw.Draw(img)
    draw.rectangle([10, 5, 150, 15], fill=0)  # line 1 band
    draw.rectangle([10, 40, 160, 50], fill=0)  # line 2 band, separated by a blank gap
    return img.convert("RGB")


def _one_line_image(width=200, height=20) -> Image.Image:
    img = Image.new("L", (width, height), color=255)
    draw = ImageDraw.Draw(img)
    draw.rectangle([10, 5, 150, 15], fill=0)
    return img.convert("RGB")


def test_otsu_threshold_separates_light_and_dark():
    arr = np.array([0] * 50 + [255] * 50, dtype=np.uint8)
    t = _otsu_threshold(arr)
    assert 0 < t < 255


def test_segment_lines_finds_two_bands_with_a_real_gap():
    bands = segment_lines(_two_line_image())
    assert len(bands) == 2


def test_segment_lines_finds_one_band_for_single_line():
    bands = segment_lines(_one_line_image())
    assert len(bands) == 1


def test_segment_lines_empty_crop_returns_no_bands():
    blank = Image.new("L", (100, 20), color=255).convert("RGB")
    assert segment_lines(blank) == []


class _StubReader:
    def __init__(self, by_call: list[list[tuple]]):
        self.by_call = list(by_call)
        self.calls = 0

    def readtext(self, path, detail=1):
        idx = min(self.calls, len(self.by_call) - 1)
        self.calls += 1
        return self.by_call[idx]


def _detection(text: str, conf: float, x0=0, y0=0, x1=50, y1=15):
    polygon = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
    return (polygon, text, conf)


def _group(docling_text: str, easyocr_text: str, similarity: float) -> EvidenceGroup:
    box = BBox(x0=0, y0=0, x1=200, y1=20)
    g = EvidenceGroup(
        bbox=box,
        docling=[EvidenceToken(docling_text, box, None, "docling", 0)],
        easyocr=[EvidenceToken(easyocr_text, box, 0.5, "easyocr", 0)],
        text_similarity=similarity,
        decision="conflict",
    )
    return g


def test_recovery_replaces_when_a_candidate_clearly_resolves_the_conflict(tmp_path):
    """Mirrors the real `cmb_multicol_table_en` case: docling says "Ijob",
    easyocr says "job", and re-OCR of the crop confidently returns "job" --
    a clean win that should be accepted."""
    group = _group(docling_text="Ijob", easyocr_text="job", similarity=0.0)
    backend = EasyOCRBackend(device="cpu")
    backend._reader = _StubReader([
        [_detection("job", 0.99)],  # plain
        [_detection("job", 0.99)],  # upscale
    ])
    page_image = _one_line_image()

    result = recover_region(group, page_image, backend, tmp_path)

    assert result.replaced is True
    assert result.chosen is not None
    assert result.chosen.text.strip() == "job"


def test_recovery_keeps_old_evidence_when_nothing_resolves(tmp_path):
    """Mirrors the real `cmb_scan_tiny_vi` case: re-OCR just produces a
    third garbled reading that doesn't clearly agree with either original.
    Must never blindly replace in that situation."""
    group = _group(
        docling_text="Dieu 2 Tham Khoan chi",
        easyocr_text="Quy che nay ap dung cho toan bo",
        similarity=0.1,
    )
    backend = EasyOCRBackend(device="cpu")
    backend._reader = _StubReader([
        [_detection("xyzzy plugh qwerty", 0.4)],  # plain: agrees with neither
        [_detection("plugh xyzzy something", 0.4)],  # upscale: still agrees with neither
    ])
    page_image = _one_line_image()

    result = recover_region(group, page_image, backend, tmp_path)

    assert result.replaced is False
    assert any("kept old evidence" in r for r in result.reasons)


def test_recovery_rejects_low_confidence_even_if_similar(tmp_path):
    group = _group(docling_text="job title here", easyocr_text="job title", similarity=0.4)
    backend = EasyOCRBackend(device="cpu")
    backend._reader = _StubReader([
        [_detection("job title here", 0.1)],  # matches docling well, but low confidence
        [_detection("job title here", 0.1)],
    ])
    page_image = _one_line_image()

    result = recover_region(group, page_image, backend, tmp_path)

    assert result.replaced is False
