"""Text-quality heuristic: the core defence against confidently-wrong text.

The garbled sample is real output observed from this repo's own corpus, not
an invented string — see tests/fixtures.py.
"""
from __future__ import annotations

import pytest

from doc_extraction.ingest.text_quality import (
    TextQualityThresholds,
    assess_text,
    script_of,
)
from tests.fixtures import CLEAN_ENGLISH_TEXT, CLEAN_VIETNAMESE_TEXT, GARBLED_CMAP_TEXT


def test_clean_english_is_not_suspicious():
    report = assess_text(CLEAN_ENGLISH_TEXT)
    assert report.suspicious is False
    assert report.reasons == ["ok"]


def test_clean_vietnamese_is_not_suspicious():
    """Vietnamese uses Latin-script precomposed diacritics; it must not be
    mistaken for corruption just because it is not English."""
    report = assess_text(CLEAN_VIETNAMESE_TEXT)
    assert report.suspicious is False
    assert report.mixed_script_word_ratio == 0.0
    assert report.unexpected_script_ratio == 0.0


def test_garbled_cmap_text_is_flagged():
    report = assess_text(GARBLED_CMAP_TEXT)
    assert report.suspicious is True
    assert any("mixed_script" in r for r in report.reasons)


def test_garbled_text_signals_exceed_clean_text_by_a_wide_margin():
    """Guards the calibration: the decision must rest on a real gap, not on
    a threshold that happens to sit between two near-identical values."""
    clean = assess_text(CLEAN_VIETNAMESE_TEXT)
    garbled = assess_text(GARBLED_CMAP_TEXT)
    assert garbled.mixed_script_word_ratio > clean.mixed_script_word_ratio + 0.25
    assert garbled.unexpected_script_ratio > clean.unexpected_script_ratio + 0.10


def test_short_text_is_reported_as_insufficient_not_suspicious():
    report = assess_text("Hello.")
    assert report.suspicious is False
    assert "insufficient_text" in report.reasons


def test_empty_text():
    report = assess_text("")
    assert report.suspicious is False
    assert report.n_chars == 0
    assert "insufficient_text" in report.reasons


def test_replacement_characters_are_flagged():
    text = "valid words here " * 20 + "�" * 40
    report = assess_text(text)
    assert report.suspicious is True
    assert any("replacement_chars" in r for r in report.reasons)


def test_expected_scripts_are_configurable():
    """A genuinely Cyrillic corpus should not be flagged when configured as
    such — the heuristic is corpus-relative, not Latin-chauvinist."""
    cyrillic = (
        "Это обычный абзац русского текста, который используется для проверки "
        "того, что оценка качества текста не помечает правильно декодированный "
        "кириллический текст как подозрительный при правильной настройке."
    )
    latin_only = assess_text(cyrillic)
    assert latin_only.suspicious is True

    configured = assess_text(cyrillic, TextQualityThresholds(expected_scripts=("CYRILLIC",)))
    assert configured.suspicious is False


def test_assessment_is_deterministic():
    first = assess_text(GARBLED_CMAP_TEXT).as_dict()
    second = assess_text(GARBLED_CMAP_TEXT).as_dict()
    assert first == second


def test_report_is_json_serializable():
    import json

    payload = json.dumps(assess_text(CLEAN_ENGLISH_TEXT).as_dict())
    assert "suspicious" in payload


@pytest.mark.parametrize(
    "char,expected",
    [("a", "LATIN"), ("Đ", "LATIN"), ("ộ", "LATIN"), ("Ӝ", "CYRILLIC"), ("Ω", "GREEK"), ("1", None), (" ", None)],
)
def test_script_of(char, expected):
    assert script_of(char) == expected


# --- False positives found on the real corpus (regression locks) ----------
# Both of these were flagged by an earlier revision of this heuristic on
# real pages of FROGSLEAP_COMPANY PROFILE.pdf. Neither page was corrupt.


def test_styled_unicode_letters_are_not_mistaken_for_another_script():
    """Mathematical-bold capitals are Latin letters used for styling. NFKC
    normalization must fold them back before script analysis."""
    text = (
        "PROJECT \U0001D401\U0001D411\U0001D40E\U0001D40C\U0001D40E\U0001D40E "
        "\U0001D40F\U0001D411\U0001D40E\U0001D409\U0001D404\U0001D402\U0001D413 "
        + CLEAN_ENGLISH_TEXT
    )
    report = assess_text(text)
    assert report.suspicious is False
    assert report.unexpected_script_ratio == 0.0


def test_urls_do_not_inflate_the_digit_in_word_signal():
    """A slide carrying links and little else must not be flagged just for
    containing links."""
    # Structurally identical to the real page that triggered this (a title,
    # two long slug URLs and a page number), with the URLs genericized so no
    # sample-document content is embedded in the test suite.
    text = (
        "Company in the media\n"
        "https://news.example.com/section/mot-bai-viet-rat-dai-ve-du-an-1134715.html\n"
        "https://other.example.vn/muc/mot-tieu-de-khac-cung-rat-dai-nhieu-tu"
        "-va-mot-so-chu-so-20180202162759713.htm\n13\n"
    )
    report = assess_text(text)
    assert report.suspicious is False


def test_url_exclusion_does_not_mask_genuine_digit_letter_corruption():
    """The URL carve-out must not become a hole the real failure fits through."""
    corrupt = " ".join(["&+Ë1+7", "9Lӊ71", "3+Ó1*2", "ĈĂ1*.é3", "0mVӕ4"] * 20)
    assert assess_text(corrupt).suspicious is True
