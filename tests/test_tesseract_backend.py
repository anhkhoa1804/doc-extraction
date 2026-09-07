"""TesseractBackend — the genuinely-independent `OCRBackend` (experiment 022).

Most tests drive `_tokens_from_tsv` directly with literal TSV, so they need
no tesseract binary and no model data. Two exceptions talk to the real
executable: the availability probe and
`test_coordinate_placement_matches_a_known_layout`, which validates the
coordinate-space claim in the module docstring against ground truth — a
thing no stub can establish. Both skip cleanly when tesseract is absent.
"""
from __future__ import annotations

import shutil

import pytest

from doc_extraction.backends.tesseract_backend import (
    DEFAULT_LANGUAGES,
    TesseractBackend,
    to_tesseract_langs,
)
from doc_extraction.pipelines.base import PageInput

HEADER = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext"

has_tesseract = shutil.which("tesseract") is not None
requires_tesseract = pytest.mark.skipif(
    not has_tesseract, reason="tesseract executable not installed")


def tsv(*rows: str) -> str:
    return "\n".join([HEADER, *rows]) + "\n"


def word_row(text, left=10, top=20, width=30, height=8, conf=95.0,
             block=1, par=1, line=1, word=1) -> str:
    return (f"5\t1\t{block}\t{par}\t{line}\t{word}\t{left}\t{top}\t{width}\t"
            f"{height}\t{conf}\t{text}")


def test_defaults_to_en_and_vi():
    """Production language config stays en+vi unless explicitly overridden —
    never silently widened for benchmark convenience."""
    assert TesseractBackend().languages == DEFAULT_LANGUAGES == ["en", "vi"]


def test_language_codes_map_to_traineddata_names():
    """config speaks ISO 639-1; tesseract traineddata is ISO 639-2/T. A
    backend that passed "en+vi" through would fail to load any model."""
    assert to_tesseract_langs(["vi"]) == "vie"
    assert to_tesseract_langs(["en"]) == "eng"


def test_english_is_ordered_last_regardless_of_config_order():
    """Tesseract's language order is significant: the first entry is the
    primary model. Measured over the 49-PDF corpus, `eng+vie` scores 0.7488
    on Vietnamese vs 0.9050 for `vie+eng`, at identical English quality --
    English-primary drops tone marks on uppercase Vietnamese
    (`HỢP ĐỒNG` -> `HOP DONG`). `config.ocr_languages` is naturally written
    ["en", "vi"], so honouring its order literally would pick the worse
    configuration by default.
    """
    assert to_tesseract_langs(["en", "vi"]) == "vie+eng"
    assert to_tesseract_langs(["vi", "en"]) == "vie+eng"


def test_non_english_language_order_is_otherwise_preserved():
    """Only `eng` is demoted -- it is the fallback script, not the subject.
    Any other ordering the caller chose is left alone."""
    assert to_tesseract_langs(["vi", "deu", "en"]) == "vie+deu+eng"


def test_unknown_language_code_passes_through():
    """So a user who installs another traineddata can name it directly
    rather than being blocked by this project's mapping table."""
    assert to_tesseract_langs(["deu"]) == "deu"


def test_word_rows_become_tokens_with_pixel_bboxes():
    """TSV left/top/width/height are top-left-origin +y-down pixels of the
    image handed to tesseract — the repo's `BBox` convention, so x1/y1 are
    left+width and top+height with no flip and no rescale."""
    tokens = TesseractBackend._tokens_from_tsv(
        tsv(word_row("Điều", left=10, top=20, width=30, height=8)))

    assert len(tokens) == 1
    assert tokens[0].text == "Điều"
    assert (tokens[0].bbox.x0, tokens[0].bbox.y0) == (10.0, 20.0)
    assert (tokens[0].bbox.x1, tokens[0].bbox.y1) == (40.0, 28.0)


def test_confidence_is_rescaled_to_easyocr_range():
    """Tesseract reports 0-100, EasyOCR 0.0-1.0, and both land in the same
    `OCRToken.confidence` field that shared thresholds read (e.g.
    `evidence_fusion.LOW_CONFIDENCE_MAX = 0.4`). Emitting raw 0-100 here
    would silently disable every confidence gate downstream."""
    tokens = TesseractBackend._tokens_from_tsv(tsv(word_row("x", conf=95.0)))
    assert tokens[0].confidence == pytest.approx(0.95)
    assert 0.0 <= tokens[0].confidence <= 1.0


def test_non_word_hierarchy_rows_are_ignored():
    """Levels 1-4 describe the page/block/para/line hierarchy and carry
    conf=-1. Emitting them would double-count the text and put a sentinel
    into a field consumers read as a probability."""
    rows = tsv(
        "1\t1\t0\t0\t0\t0\t0\t0\t600\t800\t-1\t",
        "2\t1\t1\t0\t0\t0\t10\t20\t100\t50\t-1\t",
        "4\t1\t1\t1\t1\t0\t10\t20\t100\t10\t-1\t",
        word_row("real"),
    )
    tokens = TesseractBackend._tokens_from_tsv(rows)
    assert [t.text for t in tokens] == ["real"]


def test_negative_confidence_rows_are_dropped():
    tokens = TesseractBackend._tokens_from_tsv(
        tsv(word_row("kept", conf=80.0), word_row("dropped", conf=-1.0)))
    assert [t.text for t in tokens] == ["kept"]


def test_blank_and_whitespace_text_dropped():
    """Tesseract emits empty word rows for inter-word gaps; they are not
    evidence and would inflate token counts used as a density signal."""
    tokens = TesseractBackend._tokens_from_tsv(
        tsv(word_row(""), word_row("   "), word_row("real")))
    assert [t.text for t in tokens] == ["real"]


def test_token_order_is_tesseracts_reading_order_not_geometry():
    """Ordering must be deterministic and meaningful. Tokens come back in
    tesseract's own (block, par, line, word) sequence — preserved as-is, so
    two runs over identical pixels produce an identical token sequence."""
    rows = tsv(
        word_row("first", block=1, line=1, word=1, top=20),
        word_row("second", block=1, line=1, word=2, top=20),
        word_row("third", block=2, line=1, word=1, top=100),
    )
    tokens = TesseractBackend._tokens_from_tsv(rows)
    assert [t.text for t in tokens] == ["first", "second", "third"]


def test_tab_in_text_is_not_treated_as_a_quote_character():
    """QUOTE_NONE matters: a word containing a quote character must not
    swallow the rest of the row. Regression guard for csv defaults."""
    tokens = TesseractBackend._tokens_from_tsv(tsv(word_row('"quoted"')))
    assert tokens[0].text == '"quoted"'


def test_missing_image_returns_warning_not_exception():
    """Matches EasyOCRBackend: a page with no rendered raster is a
    reportable condition, not a crash."""
    result = TesseractBackend().recognize(
        PageInput(page_index=0, width=100, height=100, image_path=None))
    assert result.tokens == []
    assert result.backend == "tesseract"
    assert result.warnings and "no rendered image" in result.warnings[0]


def test_device_is_recorded_even_though_execution_is_cpu(tmp_path):
    """Tesseract is CPU-only. `device` is accepted for constructor parity
    and kept visible, so a caller that asked for cuda can see it did not
    get it rather than being silently misled about where work ran."""
    assert TesseractBackend(device="cuda").device == "cuda"


@requires_tesseract
def test_vietnamese_traineddata_is_installed():
    """The whole point of this backend is Vietnamese. If `vie` is missing,
    every result it produces is an English-only misreading."""
    from doc_extraction.backends.tesseract_backend import available_languages

    assert "vie" in available_languages()


@requires_tesseract
def test_coordinate_placement_matches_a_known_layout(tmp_path):
    """Ground truth against the real binary: text drawn at a known pixel
    position must be detected at approximately that position, in
    top-left-origin +y-down space. Guards the coordinate claim that makes
    these tokens usable for table cell assignment and order recovery."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (400, 200), "white")
    ImageDraw.Draw(img).text((50, 60), "HELLO", fill="black")
    path = tmp_path / "known.png"
    img.save(path)

    backend = TesseractBackend(device="cpu", languages=["en"])
    result = backend.recognize(
        PageInput(page_index=0, width=400, height=200, image_path=path))

    assert result.backend == "tesseract"
    texts = [t.text.upper() for t in result.tokens]
    assert "HELLO" in texts
    token = result.tokens[texts.index("HELLO")]
    assert 30 <= token.bbox.x0 <= 70
    assert 45 <= token.bbox.y0 <= 80
    assert token.bbox.x1 < 400 and token.bbox.y1 < 200
    assert backend.last_duration_s is not None and backend.last_duration_s > 0
