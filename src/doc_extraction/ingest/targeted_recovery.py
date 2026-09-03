"""Targeted OCR recovery v0 — the smallest loop from a CONFLICT/low-trust
`EvidenceGroup` (see `evidence_fusion.py`) to a verified replacement.

    verification / disagreement
            v
        region bbox
            v
      targeted re-OCR
            v
    re-segment if necessary
            v
          verify
            v
    replace only if better

Why this exists
----------------
Experiment 013 measured that a naive "crop the conflict bbox and re-OCR it"
resolves some conflicts (a single, genuinely legible misread) but not
others (a Docling anchor that turned out to span two separate paragraphs —
re-OCR of the same jumbled crop, even upscaled, just produces a third
jumbled reading). This module adds the missing step for that second case:
a cheap, classical (non-learned) line resegmentation via horizontal
projection profile, tried only when it finds more than one row band in the
crop, and a decision rule that only accepts the result if it is measurably
better than what was already there.

What this deliberately does not do
------------------------------------
It never touches a TRUSTED group — the caller only invokes `recover_region`
for groups already judged CONFLICT (or otherwise suspicious), so "old
evidence suspicious" is a precondition, not something this module checks.
It does not decide *which* groups need recovery — that is
`evidence_fusion`'s job. It is not wired into the production pipeline; see
`experiments/013_evidence_fusion/README.md` for the promotion decision.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

from doc_extraction.ingest.evidence_fusion import EvidenceGroup, LOW_CONFIDENCE_MAX, _words
from doc_extraction.ingest.text_quality import assess_text
from doc_extraction.pipelines.base import PageInput

# How much extra similarity to an original reading (over the original
# inter-source agreement, floored at 0.5) a recovered reading must show to
# count as "moved the needle" rather than "a third opinion, no better than
# the two we already had." A rough starting point, calibrated by
# inspection against the 2 real conflicts this corpus produced — same
# discipline, same caveat, as every other threshold in this project
# (`evidence_fusion.AGREE_SIMILARITY_MIN`, `verification.AGREEMENT_SUSPICIOUS_BELOW`).
RESOLVE_MARGIN = 0.5


def _word_overlap(a: str, b: str) -> float:
    wa, wb = _words(a), _words(b)
    return len(wa & wb) / len(wa | wb) if (wa or wb) else 1.0


def _otsu_threshold(gray: np.ndarray) -> int:
    """Classical Otsu binarization threshold. Not a model -- a closed-form
    histogram statistic -- chosen over a fixed threshold because scan
    brightness varies across this corpus (low-contrast documents are one of
    its named hard-case categories) and a fixed cutoff would silently fail
    on those."""
    hist, _ = np.histogram(gray, bins=256, range=(0, 256))
    total = gray.size
    sum_all = float(np.dot(hist, np.arange(256)))
    sum_b, weight_b, best_var, threshold = 0.0, 0.0, 0.0, 128
    for i in range(256):
        weight_b += hist[i]
        if weight_b == 0:
            continue
        weight_f = total - weight_b
        if weight_f == 0:
            break
        sum_b += i * hist[i]
        mean_b = sum_b / weight_b
        mean_f = (sum_all - sum_b) / weight_f
        variance = weight_b * weight_f * (mean_b - mean_f) ** 2
        # `>=`, not `>`: a cleanly bimodal image (this project's stamped/
        # scanned corpus produces near-bimodal ink-vs-background histograms
        # often enough to matter) has a plateau of tied maximum variance
        # across every intensity level between the two classes. Taking the
        # *first* tied i (plain `>`) picks a threshold right at the ink
        # class's own value, which the `ink = gray < threshold` check
        # downstream then classifies as background. Taking the *last* tied
        # i puts the cutoff at the far edge of the plateau, correctly on
        # the background side of every ink pixel.
        if variance >= best_var:
            best_var, threshold = variance, i
    return threshold


def segment_lines(crop: Image.Image, min_gap_rows: int = 3, min_ink_frac: float = 0.02) -> list[tuple[int, int]]:
    """Horizontal projection-profile line segmentation: find row bands with
    ink above `min_ink_frac`, separated by gaps of at least `min_gap_rows`
    near-blank rows. Simplest robust method available -- no connected
    components, no learned layout model -- deliberately, per the mission's
    "do not add a heavy model for this." Returns [] if the crop has no
    discernible ink at all, [(0, height)] if it is one contiguous band."""
    gray = np.array(crop.convert("L"))
    if gray.size == 0:
        return []
    threshold = _otsu_threshold(gray)
    ink = gray < threshold
    row_frac = ink.mean(axis=1)
    is_text_row = row_frac > min_ink_frac

    bands: list[tuple[int, int]] = []
    start: int | None = None
    gap = 0
    height = len(is_text_row)
    for y in range(height):
        if is_text_row[y]:
            if start is None:
                start = y
            gap = 0
        elif start is not None:
            gap += 1
            if gap >= min_gap_rows:
                bands.append((start, y - gap + 1))
                start = None
                gap = 0
    if start is not None:
        bands.append((start, height))
    return bands


@dataclass
class RecoveryAttempt:
    method: str  # "plain" | "upscale" | "resegment"
    text: str
    mean_confidence: float | None
    sim_to_docling: float
    sim_to_easyocr: float


@dataclass
class RecoveryResult:
    bbox: tuple[float, float, float, float]
    attempts: list[RecoveryAttempt] = field(default_factory=list)
    chosen: RecoveryAttempt | None = None
    replaced: bool = False
    reasons: list[str] = field(default_factory=list)


def _ocr_image(easyocr_backend, image_path: Path) -> tuple[str, float | None]:
    with Image.open(image_path) as im:
        w, h = float(im.size[0]), float(im.size[1])
    result = easyocr_backend.recognize(PageInput(page_index=0, width=w, height=h, image_path=image_path))
    text = " ".join(t.text for t in result.tokens)
    confs = [t.confidence for t in result.tokens if t.confidence is not None]
    return text, (sum(confs) / len(confs) if confs else None)


def recover_region(
    group: EvidenceGroup,
    page_image: Image.Image,
    easyocr_backend,
    scratch_dir: Path,
    pad: int = 10,
    upscale: int = 3,
) -> RecoveryResult:
    """Run all three re-OCR methods (plain crop, upscaled crop, resegmented
    crop) against one already-flagged group's bbox, then apply the
    replace-only-if-better decision rule. Caller is responsible for only
    invoking this on groups already judged CONFLICT/SUSPICIOUS -- this
    function does not re-check that."""
    scratch_dir.mkdir(parents=True, exist_ok=True)
    x0 = max(0, int(group.bbox.x0) - pad)
    y0 = max(0, int(group.bbox.y0) - pad)
    x1 = min(page_image.width, int(group.bbox.x1) + pad)
    y1 = min(page_image.height, int(group.bbox.y1) + pad)
    crop = page_image.crop((x0, y0, x1, y1))

    result = RecoveryResult(bbox=(group.bbox.x0, group.bbox.y0, group.bbox.x1, group.bbox.y1))
    original_agreement = group.text_similarity or 0.0

    def make_attempt(method: str, text: str, conf: float | None) -> RecoveryAttempt:
        return RecoveryAttempt(
            method=method, text=text, mean_confidence=conf,
            sim_to_docling=_word_overlap(group.docling_text, text),
            sim_to_easyocr=_word_overlap(group.easyocr_text, text),
        )

    plain_path = scratch_dir / "plain.png"
    crop.save(plain_path)
    text, conf = _ocr_image(easyocr_backend, plain_path)
    result.attempts.append(make_attempt("plain", text, conf))

    up_path = scratch_dir / "upscale.png"
    crop.resize((crop.width * upscale, crop.height * upscale), Image.LANCZOS).save(up_path)
    text, conf = _ocr_image(easyocr_backend, up_path)
    result.attempts.append(make_attempt("upscale", text, conf))

    bands = segment_lines(crop)
    if len(bands) > 1:
        band_texts, band_confs = [], []
        for i, (by0, by1) in enumerate(bands):
            band_crop = crop.crop((0, max(0, by0 - 2), crop.width, min(crop.height, by1 + 2)))
            band_path = scratch_dir / f"band_{i}.png"
            band_crop.save(band_path)
            btext, bconf = _ocr_image(easyocr_backend, band_path)
            band_texts.append(btext)
            if bconf is not None:
                band_confs.append(bconf)
        text = " ".join(t for t in band_texts if t)
        conf = sum(band_confs) / len(band_confs) if band_confs else None
        result.attempts.append(make_attempt("resegment", text, conf))
    else:
        result.reasons.append(f"resegment skipped: projection profile found {len(bands)} band(s), not >1")

    # Pick the attempt with the best combination of plausibility, moving
    # similarity, and confidence -- never the one that merely "looks
    # different." Candidates that fail assess_text are excluded outright.
    candidates = [a for a in result.attempts if not assess_text(a.text).suspicious and a.text.strip()]
    if candidates:
        result.chosen = max(candidates, key=lambda a: (max(a.sim_to_docling, a.sim_to_easyocr), a.mean_confidence or 0.0))

    if result.chosen is None:
        result.reasons.append("no candidate passed the plausibility gate")
        return result

    best_sim = max(result.chosen.sim_to_docling, result.chosen.sim_to_easyocr)
    conf_ok = result.chosen.mean_confidence is None or result.chosen.mean_confidence >= LOW_CONFIDENCE_MAX
    moved_the_needle = best_sim > max(original_agreement, RESOLVE_MARGIN)

    if conf_ok and moved_the_needle:
        result.replaced = True
        result.reasons.append(
            f"{result.chosen.method}: similarity {best_sim:.2f} > "
            f"max(original_agreement={original_agreement:.2f}, {RESOLVE_MARGIN}), confidence ok"
        )
    else:
        result.reasons.append(
            f"kept old evidence: best candidate ({result.chosen.method}) similarity {best_sim:.2f} "
            f"did not clear max(original_agreement={original_agreement:.2f}, {RESOLVE_MARGIN})"
            + ("" if conf_ok else f", confidence {result.chosen.mean_confidence:.2f} below {LOW_CONFIDENCE_MAX}")
        )

    return result
