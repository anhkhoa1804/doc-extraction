"""Direct EasyOCR — an `OCRBackend` that calls EasyOCR itself rather than
going through Docling's wrapper.

Why this exists
----------------
`DoclingBackend.recognize()` already runs EasyOCR internally (it is
Docling's own configured OCR engine — see `docling_backend.py`), but two
things are lost crossing Docling's public `DoclingDocument` API on the way
back out:

* **Confidence.** Docling's `TextItem` has no confidence field at all
  (verified against `docling_core.types.doc.document.TextItem.model_fields`
  — there is no field to read, not a field this project forgot to read).
  EasyOCR computes a per-detection confidence internally; it simply never
  crosses the API boundary.
* **Granularity.** Docling's items are block/line-level ("text regions", per
  `docling_backend.py`'s own module docstring), not EasyOCR's native
  per-detection tokens.

Measured (`research/experiments/_scan_forensics/ocr_unbundle.py`, prior
milestone): on the corpus's six scanned failures, direct EasyOCR scored
higher word recall than the Docling path (0.924 vs 0.803 mean), ran 2.5x
faster, and returned a confidence on every detection versus zero from
Docling. This backend makes that path available as a first-class,
swappable component (`ocr_backend: easyocr` in config) rather than a
one-off research script — see `docs/backends.md` and
`experiments/012_direct_easyocr/README.md` for the full comparison.

Coordinate space
-----------------
Unlike Docling — which rasterizes internally at its own fixed resolution
(measured: 150 DPI) regardless of what image it is handed, so its
coordinates must be rescaled into the caller's pixel space
(`docling_backend._bbox_from_docling`) — EasyOCR runs directly on the exact
pixels it is given. Its returned polygon is already in that image's own
top-left-origin, +y-down pixel space, which is this repo's canonical `BBox`
convention. No flip, no rescale. Verified against a synthetic image with
known text placement (`tests/test_easyocr_backend.py`).

What this deliberately does not do
------------------------------------
It does not replace `DoclingBackend` as the layout backend — layout
(region detection/labeling) is not part of EasyOCR's job, and Docling's
layout output is unaffected by this module. This is an `OCRBackend` only.
"""
from __future__ import annotations

import importlib.util
from typing import Any

from doc_extraction.pipelines.base import OCRResult, OCRToken, PageInput
from doc_extraction.schemas.element import BBox

DEFAULT_LANGUAGES = ["en", "vi"]

# EasyOCR's own default confidence-related knobs, threaded through
# unconditionally rather than exposed as new config: this backend's job is
# to make the *existing* recognizer's evidence reachable, not to retune it.
# Re-tuning belongs to a future experiment with its own measurement, per
# the same discipline applied to the table quality gate's thresholds.


def is_available() -> bool:
    return importlib.util.find_spec("easyocr") is not None


class EasyOCRBackend:
    """`OCRBackend` Protocol implementation: EasyOCR called directly.

    The `Reader` (which loads the detector + recognizer weights) is built
    lazily on first `recognize()` call, not in `__init__` — constructing it
    eagerly would create a CUDA context merely to be instantiated, which is
    exactly what `device: auto`'s GPU probe must not trigger as a side
    effect of building this object to *inspect* whether a GPU is free.
    """

    name = "easyocr"

    def __init__(self, device: str = "cpu", languages: list[str] | None = None) -> None:
        self.device = device
        self.languages = list(languages) if languages else list(DEFAULT_LANGUAGES)
        self._reader: Any = None

    def is_available(self) -> bool:
        return is_available()

    def _get_reader(self):
        if self._reader is None:
            import easyocr

            self._reader = easyocr.Reader(
                self.languages, gpu=(self.device == "cuda"), verbose=False
            )
        return self._reader

    def recognize(self, page: PageInput) -> OCRResult:
        if page.image_path is None:
            return OCRResult(tokens=[], backend=self.name, warnings=["no rendered image for this page"])

        reader = self._get_reader()
        detections = reader.readtext(str(page.image_path), detail=1)

        tokens: list[OCRToken] = []
        for polygon, text, confidence in detections:
            text = (text or "").strip()
            if not text:
                continue
            xs = [float(p[0]) for p in polygon]
            ys = [float(p[1]) for p in polygon]
            bbox = BBox(x0=min(xs), y0=min(ys), x1=max(xs), y1=max(ys))
            tokens.append(OCRToken(text=text, bbox=bbox, confidence=float(confidence)))

        return OCRResult(tokens=tokens, backend=self.name)
