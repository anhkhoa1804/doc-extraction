"""Tesseract — an `OCRBackend` that is genuinely independent of EasyOCR.

Why this exists
----------------
Experiment 021 established that this project's two OCR paths are not two
recognizers. `docling_backend.py` configures Docling's OCR to *be* EasyOCR
(`EasyOcrOptions`), so `DoclingBackend` and `EasyOCRBackend` resolve
Vietnamese through the same `latin_g2` weights and fail identically at the
character level. Experiment 013's "correlated errors" — two documents where
both sources scored a byte-identical 0.782 word recall — were that shared
recognizer agreeing with itself, not independent corroboration.

Experiment 022 measured Tesseract 4.1.1's LSTM engine with `vie`
traineddata against EasyOCR over 49 corpus PDFs at a fixed 200 DPI:
Vietnamese mean exact recall 0.4197 -> 0.8865, English 0.9214 -> 0.9857,
on CPU, faster than EasyOCR on an L4. It also regressed 4 documents, all
*geometric* (rotation, tiny table cells, low contrast under a stamp) and
none linguistic. Two engines that fail differently are the precondition for
`verification.assess_ocr_agreement` to carry information at all, which is
what this backend is here to make testable.

Evidence contract
------------------
`OCRToken(text, bbox, confidence)`, identical to `EasyOCRBackend` — no
parallel OCR architecture, no new result type. Three details matter for the
evidence to be comparable across backends rather than merely present:

* **Confidence is rescaled.** Tesseract reports 0-100; EasyOCR reports
  0.0-1.0. This backend divides by 100 so a threshold like
  `evidence_fusion.LOW_CONFIDENCE_MAX = 0.4` means the same thing whichever
  backend produced the token. A backend that emitted raw 0-100 into a
  shared field would silently disable every confidence gate downstream.
* **Coordinates are already this repo's convention.** Tesseract's TSV
  `left/top/width/height` are top-left-origin, +y-down pixels of the exact
  image handed to it — the same space as `BBox` and as EasyOCR's polygons,
  so no flip and no rescale (unlike Docling, which rasterizes internally at
  150 DPI and must be rescaled). Verified in `tests/test_tesseract_backend.py`
  against a synthetic image with known text placement.
* **Ordering is deterministic.** Tokens are emitted in Tesseract's own
  `(block, paragraph, line, word)` order, which is its reading order, not
  in raster or hash order. Two runs over the same pixels produce the same
  token sequence.

TSV, not plain text: `--psm 3` stdout would give the words and throw away
the boxes and confidences the pipeline consumes for layout, table cell
assignment, and `order_recovery`.

Timing is deliberately *not* added to `OCRResult`. `stages/ocr.py` already
times every backend through `StageLogger`, and widening a shared, serialized
dataclass to carry a field one backend wanted would change every existing
backend's on-disk output. It is exposed as `last_duration_s` on the instance
for callers that want it without paying that cost.
"""
from __future__ import annotations

import csv
import io
import shutil
import subprocess
import time

from doc_extraction.pipelines.base import OCRResult, OCRToken, PageInput
from doc_extraction.schemas.element import BBox

DEFAULT_LANGUAGES = ["en", "vi"]

# config.ocr_languages speaks ISO 639-1 ("en", "vi"); tesseract traineddata
# is named in ISO 639-2/T ("eng", "vie"). Only languages this project
# actually targets are mapped -- an unknown code is passed through unchanged
# so a user who installs another traineddata can name it directly.
_LANG_MAP = {"en": "eng", "vi": "vie", "zh": "chi_sim", "ch_sim": "chi_sim"}

# Tesseract's page segmentation mode. 3 = fully automatic, no orientation
# detection -- its default, and what experiment 022 measured. Exposed
# because 022's one total regression (`hc_rotation_vi`, 0.333 -> 0.000) is
# plausibly an orientation failure that `--psm 0`/OSD would address, and
# that is a measurement this backend should make possible rather than
# foreclose.
DEFAULT_PSM = 3


def to_tesseract_langs(languages: list[str]) -> str:
    """Map to traineddata names, and put `eng` last.

    Tesseract's language ORDER is significant -- the first entry acts as the
    primary model -- and this is not a cosmetic detail. Measured over the
    49-PDF production corpus at 200 DPI, changing only the order:

        eng+vie   Vietnamese 0.7488   English 0.9857
        vie+eng   Vietnamese 0.9050   English 0.9857

    +0.156 absolute on Vietnamese (+21% relative) for zero English cost.
    English-primary reads uppercase Vietnamese as English and silently
    drops the tone marks (`HỢP ĐỒNG` -> `HOP DONG`), which is the exact
    failure class experiment 021 traced. `config.ocr_languages` is
    naturally written `["en", "vi"]`, so honouring its order literally
    would select the worse configuration by default.

    English is demoted rather than Vietnamese promoted so this stays
    correct for a future third language: `eng` is the fallback script here,
    not the subject.
    """
    mapped = [_LANG_MAP.get(code, code) for code in languages]
    ordered = [m for m in mapped if m != "eng"] + [m for m in mapped if m == "eng"]
    return "+".join(ordered)


def is_available() -> bool:
    return shutil.which("tesseract") is not None


def available_languages() -> list[str]:
    if not is_available():
        return []
    try:
        proc = subprocess.run(["tesseract", "--list-langs"],
                              capture_output=True, text=True, timeout=30,
                              check=False)
    except (OSError, subprocess.SubprocessError):
        return []
    lines = proc.stdout.splitlines()
    return [ln.strip() for ln in lines[1:] if ln.strip()]


class TesseractBackend:
    """`OCRBackend` Protocol implementation: Tesseract via TSV output.

    CPU-only by construction. `device` is accepted and ignored so this is a
    drop-in for the other OCR backends' constructor signature; it is
    recorded on the instance rather than silently dropped, so a caller that
    asked for `cuda` and got CPU execution can see that it did.
    """

    name = "tesseract"

    def __init__(self, device: str = "cpu", languages: list[str] | None = None,
                 psm: int = DEFAULT_PSM) -> None:
        self.device = device  # accepted for interface parity; tesseract is CPU-only
        self.languages = list(languages) if languages else list(DEFAULT_LANGUAGES)
        self.psm = psm
        self.last_duration_s: float | None = None

    def is_available(self) -> bool:
        return is_available()

    def recognize(self, page: PageInput) -> OCRResult:
        if page.image_path is None:
            return OCRResult(tokens=[], backend=self.name,
                             warnings=["no rendered image for this page"])
        if not self.is_available():
            return OCRResult(tokens=[], backend=self.name,
                             warnings=["tesseract executable not found on PATH"])

        langs = to_tesseract_langs(self.languages)
        started = time.perf_counter()
        try:
            proc = subprocess.run(
                ["tesseract", str(page.image_path), "stdout",
                 "-l", langs, "--psm", str(self.psm), "tsv"],
                capture_output=True, text=True, check=True)
        except subprocess.CalledProcessError as exc:
            self.last_duration_s = time.perf_counter() - started
            detail = (exc.stderr or "").strip().splitlines()
            return OCRResult(tokens=[], backend=self.name, warnings=[
                f"tesseract failed (exit {exc.returncode}) for langs {langs!r}"
                + (f": {detail[-1]}" if detail else "")])
        self.last_duration_s = time.perf_counter() - started

        return OCRResult(tokens=self._tokens_from_tsv(proc.stdout),
                         backend=self.name)

    @staticmethod
    def _tokens_from_tsv(tsv: str) -> list[OCRToken]:
        """Word-level rows only (`level == 5`), in Tesseract's own reading
        order. Non-word rows describe the block/paragraph/line hierarchy and
        carry `conf == -1`; emitting them would double-count text and inject
        a sentinel confidence into a field consumers read as a probability.
        """
        tokens: list[OCRToken] = []
        reader = csv.DictReader(io.StringIO(tsv), delimiter="\t",
                                quoting=csv.QUOTE_NONE)
        for row in reader:
            if (row.get("level") or "").strip() != "5":
                continue
            text = (row.get("text") or "").strip()
            if not text:
                continue
            try:
                conf = float(row["conf"])
                left, top = float(row["left"]), float(row["top"])
                width, height = float(row["width"]), float(row["height"])
            except (KeyError, TypeError, ValueError):
                continue
            if conf < 0:
                continue
            tokens.append(OCRToken(
                text=text,
                bbox=BBox(x0=left, y0=top, x1=left + width, y1=top + height),
                # 0-100 -> 0.0-1.0, matching EasyOCR's scale so a shared
                # confidence threshold means the same thing either way.
                confidence=conf / 100.0,
            ))
        return tokens
