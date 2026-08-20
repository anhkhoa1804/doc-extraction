"""Text-layer quality assessment for born-digital PDFs.

Why this exists
---------------
A PDF can carry a text layer that is *present and plentiful* but *decoded
wrongly*. The usual cause is a broken or non-standard ``ToUnicode`` CMap in
an embedded font subset: the glyph codes are read correctly, but each code
maps to the wrong character. The first smoke test on this repo's own corpus
hit exactly this (``FROGSLEAP_BUSINESS LICENSE.pdf`` decodes
``Độc lập Tự do`` as ``ĈӝF OұS 7ӵ GR``).

A character-count heuristic cannot see this: the garbage is exactly as long
as the real text. So routing on "does this page have enough characters"
silently produces confident nonsense — the worst possible failure mode for
downstream research, because nothing looks broken.

Design constraints
------------------
* **Cheap.** Signals are computed from already-extracted text. No rendering,
  no OCR, no model, no GPU. Classifying a document must not cost more than
  parsing it.
* **Conservative.** Flagging a good page as suspicious costs an unnecessary
  OCR pass; missing a bad page corrupts the dataset silently. We still bias
  toward *not* flagging unless a signal is strongly out of range, because a
  false positive that reroutes a clean page to OCR also degrades output.
* **Explainable.** Every verdict carries the individual signal values and a
  human-readable reason list. There is no opaque score to tune blindly.
* **Deterministic.** Pure function of the input string. No randomness, no
  ordering dependence, no I/O.

Signals
-------
``mixed_script_word_ratio``
    Fraction of word-like tokens containing characters from two or more
    different Unicode scripts (e.g. Latin + Cyrillic in one word). This is
    the strongest CMap-corruption signal: a mis-mapped font subset scatters
    codepoints across unrelated blocks, so ``ĈӝF`` (Latin + Cyrillic) is
    common in garbage and essentially absent from real prose.

``unexpected_script_ratio``
    Fraction of alphabetic characters outside the scripts the corpus is
    expected to use (default: Latin, which covers English and Vietnamese —
    Vietnamese precomposed diacritics live in Latin Extended blocks).

``replacement_ratio``
    Fraction of U+FFFD REPLACEMENT CHARACTER — an explicit "could not
    decode" marker.

``control_ratio``
    Fraction of non-whitespace control/unassigned characters.

``alpha_ratio``
    Fraction of characters that are alphabetic. Very low values on a page
    with substantial text suggest symbol soup rather than prose.

``digit_in_word_ratio``
    Fraction of word-like tokens that mix letters and digits. Broken CMaps
    frequently map letters onto digit glyphs (``&+Ë1+``), whereas genuine
    alphanumeric tokens (part numbers, ``COVID19``) are a small minority of
    normal text. URL-like tokens are excluded — a URL legitimately mixes
    letters and digits, and a slide carrying two links and little else would
    otherwise be flagged purely for containing links (observed on the real
    corpus; see experiments/001_pdf_text_quality/observations.md).

Normalization
-------------
Text is NFKC-normalized before analysis. Documents routinely use Unicode
compatibility variants for *styling* — mathematical bold capitals
(``𝐅𝐑𝐎𝐆𝐒𝐋𝐄𝐀𝐏``), fullwidth forms — which are Latin letters wearing a
costume. Without normalization their Unicode names begin ``MATHEMATICAL``
or ``FULLWIDTH`` and they read as an unexpected script. NFKC folds them back
to plain Latin while leaving genuinely different scripts (Cyrillic, Greek)
untouched, so it removes this false positive without weakening detection.

Limitations (documented, not hidden)
------------------------------------
* Tuned for Latin-script corpora (English/Vietnamese here). A genuinely
  multilingual document mixing Latin and Cyrillic/Greek/CJK *will* score
  higher on ``unexpected_script_ratio``; set ``expected_scripts``
  accordingly rather than lowering thresholds.
* Cannot detect a CMap that maps letters onto *other plausible Latin
  letters* — the output stays single-script and passes every signal here.
  Detecting that needs a language model or an OCR cross-check.
* Says nothing about reading order, layout, or whether the right text was
  extracted — only whether the characters themselves look decodable.
* Short strings are statistically unreliable; below
  ``min_chars_for_assessment`` the verdict is always "not suspicious" with
  an explicit ``insufficient_text`` reason, so callers can distinguish
  "looks fine" from "could not tell".
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache

# Tokens shorter than this are ignored for word-level signals: 1-2 character
# fragments are too noisy to say anything about script mixing.
_MIN_WORD_LEN = 3

# Substrings that mark a token as a URL/path/identifier rather than a word.
# Such tokens legitimately mix letters and digits, so they are excluded from
# `digit_in_word_ratio` (but still counted everywhere else).
_URL_MARKERS = ("http://", "https://", "www.", ".com", ".vn", ".org", ".net", ".html", ".htm", "@")


def _is_url_like(token: str) -> bool:
    lowered = token.lower()
    if any(marker in lowered for marker in _URL_MARKERS):
        return True
    # A long slug with many hyphens and no spaces is a path fragment.
    return lowered.count("-") >= 3 and "/" not in lowered and len(lowered) > 20


@lru_cache(maxsize=4096)
def script_of(char: str) -> str | None:
    """Coarse Unicode script name for one character, or None for
    non-alphabetic characters.

    Uses the character's Unicode name prefix (``LATIN SMALL LETTER A`` ->
    ``LATIN``), which is stdlib-only and deterministic. This is coarser than
    a real script property table but is exactly the granularity the
    mixed-script signal needs, without adding a dependency.
    """
    if not char.isalpha():
        return None
    try:
        name = unicodedata.name(char)
    except ValueError:  # unnamed / unassigned codepoint
        return "UNKNOWN"
    return name.split(" ", 1)[0]


@dataclass
class TextQualityReport:
    """Explainable verdict for one page or document of extracted text."""

    n_chars: int
    n_words: int
    alpha_ratio: float
    mixed_script_word_ratio: float
    unexpected_script_ratio: float
    replacement_ratio: float
    control_ratio: float
    digit_in_word_ratio: float
    suspicious: bool
    reasons: list[str] = field(default_factory=list)
    scripts_seen: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "n_chars": self.n_chars,
            "n_words": self.n_words,
            "alpha_ratio": round(self.alpha_ratio, 4),
            "mixed_script_word_ratio": round(self.mixed_script_word_ratio, 4),
            "unexpected_script_ratio": round(self.unexpected_script_ratio, 4),
            "replacement_ratio": round(self.replacement_ratio, 4),
            "control_ratio": round(self.control_ratio, 4),
            "digit_in_word_ratio": round(self.digit_in_word_ratio, 4),
            "suspicious": self.suspicious,
            "reasons": list(self.reasons),
            "scripts_seen": dict(self.scripts_seen),
        }


@dataclass(frozen=True)
class TextQualityThresholds:
    """Decision thresholds. Defaults are calibrated against this repo's own
    sample corpus (see experiments/001_pdf_text_quality/) — 9 clean PDFs and
    1 known-corrupt PDF — not guessed. Re-calibrate for a different corpus
    rather than assuming these transfer."""

    min_chars_for_assessment: int = 200
    max_mixed_script_word_ratio: float = 0.10
    max_unexpected_script_ratio: float = 0.10
    max_replacement_ratio: float = 0.02
    max_control_ratio: float = 0.02
    min_alpha_ratio: float = 0.30
    max_digit_in_word_ratio: float = 0.30
    expected_scripts: tuple[str, ...] = ("LATIN",)


def assess_text(text: str, thresholds: TextQualityThresholds | None = None) -> TextQualityReport:
    """Assess whether `text` looks like correctly-decoded natural text.

    Pure and deterministic. See the module docstring for what each signal
    means and what this cannot detect.
    """
    th = thresholds or TextQualityThresholds()
    # Fold compatibility variants (mathematical bold, fullwidth, ...) back to
    # their base letters before any script analysis. See module docstring.
    text = unicodedata.normalize("NFKC", text)
    n_chars = len(text)

    if n_chars == 0:
        return TextQualityReport(
            n_chars=0, n_words=0, alpha_ratio=0.0, mixed_script_word_ratio=0.0,
            unexpected_script_ratio=0.0, replacement_ratio=0.0, control_ratio=0.0,
            digit_in_word_ratio=0.0, suspicious=False, reasons=["insufficient_text"],
        )

    n_alpha = 0
    n_replacement = 0
    n_control = 0
    scripts_seen: dict[str, int] = {}
    n_unexpected_alpha = 0

    for ch in text:
        if ch == "�":
            n_replacement += 1
            continue
        category = unicodedata.category(ch)
        if category in ("Cc", "Cn", "Co", "Cs") and not ch.isspace():
            n_control += 1
            continue
        if ch.isalpha():
            n_alpha += 1
            script = script_of(ch) or "UNKNOWN"
            scripts_seen[script] = scripts_seen.get(script, 0) + 1
            if script not in th.expected_scripts:
                n_unexpected_alpha += 1

    words = [w for w in text.split() if len(w) >= _MIN_WORD_LEN]
    n_words = len(words)
    n_mixed_script = 0
    n_digit_in_word = 0
    n_digit_candidates = 0
    for word in words:
        word_scripts = {s for s in (script_of(c) for c in word) if s is not None}
        if len(word_scripts) > 1:
            n_mixed_script += 1
        if _is_url_like(word):
            continue  # URLs legitimately mix letters and digits
        n_digit_candidates += 1
        has_alpha = any(c.isalpha() for c in word)
        has_digit = any(c.isdigit() for c in word)
        if has_alpha and has_digit:
            n_digit_in_word += 1

    alpha_ratio = n_alpha / n_chars
    replacement_ratio = n_replacement / n_chars
    control_ratio = n_control / n_chars
    unexpected_script_ratio = (n_unexpected_alpha / n_alpha) if n_alpha else 0.0
    mixed_script_word_ratio = (n_mixed_script / n_words) if n_words else 0.0
    digit_in_word_ratio = (n_digit_in_word / n_digit_candidates) if n_digit_candidates else 0.0

    reasons: list[str] = []
    suspicious = False

    if n_chars < th.min_chars_for_assessment:
        # Too little text to judge. Explicitly NOT suspicious — the caller
        # decides what to do with a page that simply has little text.
        reasons.append("insufficient_text")
    else:
        if mixed_script_word_ratio > th.max_mixed_script_word_ratio:
            suspicious = True
            reasons.append(
                f"mixed_script_words={mixed_script_word_ratio:.2%} "
                f"(> {th.max_mixed_script_word_ratio:.0%}) — likely broken font CMap"
            )
        if unexpected_script_ratio > th.max_unexpected_script_ratio:
            suspicious = True
            reasons.append(
                f"unexpected_script_chars={unexpected_script_ratio:.2%} "
                f"(> {th.max_unexpected_script_ratio:.0%}), expected {list(th.expected_scripts)}"
            )
        if replacement_ratio > th.max_replacement_ratio:
            suspicious = True
            reasons.append(f"replacement_chars={replacement_ratio:.2%} (> {th.max_replacement_ratio:.0%})")
        if control_ratio > th.max_control_ratio:
            suspicious = True
            reasons.append(f"control_chars={control_ratio:.2%} (> {th.max_control_ratio:.0%})")
        if alpha_ratio < th.min_alpha_ratio:
            suspicious = True
            reasons.append(f"alpha_ratio={alpha_ratio:.2%} (< {th.min_alpha_ratio:.0%}) — symbol soup")
        if digit_in_word_ratio > th.max_digit_in_word_ratio:
            suspicious = True
            reasons.append(
                f"digit_letter_words={digit_in_word_ratio:.2%} (> {th.max_digit_in_word_ratio:.0%})"
            )
        if not suspicious:
            reasons.append("ok")

    return TextQualityReport(
        n_chars=n_chars,
        n_words=n_words,
        alpha_ratio=alpha_ratio,
        mixed_script_word_ratio=mixed_script_word_ratio,
        unexpected_script_ratio=unexpected_script_ratio,
        replacement_ratio=replacement_ratio,
        control_ratio=control_ratio,
        digit_in_word_ratio=digit_in_word_ratio,
        suspicious=suspicious,
        reasons=reasons,
        scripts_seen=scripts_seen,
    )
