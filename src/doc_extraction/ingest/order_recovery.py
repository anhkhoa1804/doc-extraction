"""Order Recovery v1 -- word-order scrambling, the one real defect
`scan_recovery` (experiment 015) was structurally unable to reach.

    Docling element (suspect: multi-line item?)
            v
    line-cluster EasyOCR tokens in its bbox
            v
    order-consistency signal (NOT word-Jaccard)
            v
    reconstruct only if same words, different order, high confidence
            v
    replace only if better

Why this exists, and why it is a different mechanism from scan_recovery
------------------------------------------------------------------------
Experiment 015 measured `scan_recovery`'s agreement-based trigger (word-
Jaccard) against 6 real scans and found it never fires on 5 of them,
because Docling and EasyOCR either fail identically (correlated error) or
-- the case this module targets -- agree almost perfectly on WHICH words
are present while disagreeing on their ORDER. Word-Jaccard is a set
operation; it cannot see order by construction, and experiment 015's own
test (`test_pure_word_reordering_does_not_trigger`) already locks that in
as an intentional non-goal of that signal.

Experiment 018 traced the real mechanism directly on `hc_scan_vi`: Docling
merges several physical lines (a two-line letterhead, a salutation line
sitting just above a body paragraph) into ONE recognized item, and that
item's internal word order comes out scrambled -- confirmed on real
pixels, not assumed:

    docling: "Kính Phòng Tài chính Kế toán Căn cứ biên bản ... gửi: phải"
    truth:   "Kính gửi: Phòng Tài chính Kế toán Căn cứ biên bản ..."

Docling's `recognize()` exposes only ITEM-level bbox+text, never per-word
geometry (see `docling_backend.py`), so the scrambled item cannot be
re-sorted by its OWN internal word boxes -- there aren't any. What can be
compared against it is EasyOCR's raw tokens covering the same region:
EasyOCR detects per physical line, not per merged paragraph, so it did
not scramble in the first place. Reconstructing physical line order from
those tokens (cluster by mutual y-overlap, sort each line left-to-right,
sort lines top-to-bottom) and comparing that reconstruction's word ORDER
against Docling's -- via `order_consistency`, a Longest-Increasing-
Subsequence-based signal distinct from word-Jaccard -- both detects the
defect and supplies the fix in one pass.

Measured directly (`experiments/018_bottleneck_discovery/`), this is not
universally safe: on `cmb_scan_multicol_en`, EasyOCR's own coverage of one
merged item was incomplete, and blindly trusting a reconstruction from an
incomplete token set would have made a CORRECTLY-ordered Docling reading
worse. The word-Jaccard precondition below (`RECON_JACCARD_MIN`) is the
guard against exactly that case -- reordering is only attempted when the
two readings already agree on WHICH words are present; a low-Jaccard
disagreement is content loss, a different problem this module does not
try to solve.
"""
from __future__ import annotations

import bisect
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from doc_extraction.ingest.text_quality import assess_text
from doc_extraction.pipelines.base import OCRToken, PageInput
from doc_extraction.schemas.element import BBox, Element

# A reconstruction is only even considered when the two readings already
# agree this well on WHICH words are present -- below this, the two
# backends disagree on content, not just order, and reordering is not the
# right recovery action (see cmb_scan_multicol_en in the module docstring).
RECON_JACCARD_MIN = 0.7

# Below this LIS ratio, order is considered genuinely inconsistent rather
# than incidental (a single word transposed among ~10-15 still scores
# 0.90-0.95; untuned beyond separating this milestone's 2 real defects
# from its 4 correctly-ordered controls -- see experiments/018 for the
# raw numbers this was read off, not fit to).
ORDER_CONSISTENCY_MAX = 0.95

# Two EasyOCR tokens belong to the same physical line if their y-ranges
# overlap by at least this fraction of the shorter one -- same constant
# and same reasoning as targeted_recovery.py's line segmentation and
# pipelines/base.py's row-band clustering: a plain (y0, x0) tuple sort
# gets same-line tokens with slightly different y0 out of order (measured
# on hc_scan_vi's own third line: y0 values 449.0/450.9/452.0 for tokens
# that must read left-to-right, not by y0).
LINE_Y_OVERLAP_MIN = 0.3


def _words(s: str) -> list[str]:
    s = unicodedata.normalize("NFC", s).lower()
    return [w for w in re.split(r"[^0-9a-zà-ỹăâđêôơư]+", s, flags=re.I) if w]


def word_jaccard(a: str, b: str) -> float:
    wa, wb = set(_words(a)), set(_words(b))
    return len(wa & wb) / len(wa | wb) if (wa or wb) else 1.0


def _lis_length(seq: list[int]) -> int:
    tails: list[int] = []
    for x in seq:
        i = bisect.bisect_left(tails, x)
        if i == len(tails):
            tails.append(x)
        else:
            tails[i] = x
    return len(tails)


def order_consistency(a_text: str, b_text: str) -> float:
    """1.0 = `a`'s words appear in `b` in the same relative order; low =
    same words, different order. Maps each word of `a` (in emitted order)
    to the position of its first unused match in `b`, then scores what
    fraction of that index sequence is already increasing (Longest
    Increasing Subsequence, O(n log n)). Deliberately NOT word-Jaccard:
    that signal is order-insensitive by construction (experiment 015) and
    this module exists specifically for the defect class that leaves
    invisible to it."""
    a_words, b_words = _words(a_text), _words(b_text)
    if not a_words:
        return 1.0
    used = [False] * len(b_words)
    positions: list[int] = []
    for w in a_words:
        for j, bw in enumerate(b_words):
            if bw == w and not used[j]:
                used[j] = True
                positions.append(j)
                break
    if not positions:
        return 0.0
    return _lis_length(positions) / len(a_words)


def _center_in(inner: BBox, outer: BBox) -> bool:
    cx, cy = (inner.x0 + inner.x1) / 2, (inner.y0 + inner.y1) / 2
    return outer.x0 <= cx <= outer.x1 and outer.y0 <= cy <= outer.y1


def _y_overlap_fraction(a: BBox, b: BBox) -> float:
    inter = max(0.0, min(a.y1, b.y1) - max(a.y0, b.y0))
    shorter = min(max(1e-6, a.y1 - a.y0), max(1e-6, b.y1 - b.y0))
    return inter / shorter


def line_cluster_reconstruction(tokens: list[OCRToken], region_bbox: BBox) -> str:
    """Physical-line reading order from whichever `tokens` land inside
    `region_bbox`: cluster by mutual y-overlap (single-linkage, not a
    naive same-line-implies-equal-y0 assumption), sort each line
    left-to-right, sort lines top-to-bottom, join. Returns "" if nothing
    lands in the region."""
    matched = [t for t in tokens if _center_in(t.bbox, region_bbox)]
    remaining = list(matched)
    lines: list[list[OCRToken]] = []
    while remaining:
        cluster = [remaining.pop(0)]
        changed = True
        while changed:
            changed = False
            still = []
            for t in remaining:
                if any(_y_overlap_fraction(t.bbox, m.bbox) >= LINE_Y_OVERLAP_MIN for m in cluster):
                    cluster.append(t)
                    changed = True
                else:
                    still.append(t)
            remaining = still
        lines.append(cluster)
    lines.sort(key=lambda ln: sum(t.bbox.y0 for t in ln) / len(ln))
    parts = []
    for ln in lines:
        ln.sort(key=lambda t: t.bbox.x0)
        parts.append(" ".join(t.text for t in ln if t.text))
    return " ".join(p for p in parts if p).strip()


@dataclass
class OrderRecoveryRecord:
    element_id: str
    old_text: str
    reconstruction: str | None
    jaccard: float | None
    order_consistency: float | None
    decision: str  # "replaced" | "kept_old"
    reasons: list[str] = field(default_factory=list)


@dataclass
class OrderRecoverySummary:
    records: list[OrderRecoveryRecord] = field(default_factory=list)
    replaced: int = 0
    kept: int = 0

    def as_dict(self) -> dict:
        return {"replaced": self.replaced, "kept": self.kept,
                "records": [r.__dict__ for r in self.records]}


def recover_page_order(
    page,
    page_image_path: Path,
    easyocr_backend,
    page_width: float,
    page_height: float,
    dpi: int | None = None,
) -> OrderRecoverySummary:
    """Cross-check every text-bearing `Element` on `page` against a
    line-clustered reconstruction of a fresh direct-EasyOCR pass, and
    replace an element's text only when (a) the reconstruction agrees
    closely enough on WHICH words are present (`RECON_JACCARD_MIN`) --
    ruling out the content-loss case a reconstruction cannot safely fix
    -- (b) the two disagree on order specifically
    (`order_consistency < ORDER_CONSISTENCY_MAX`), and (c) the
    reconstruction itself passes `assess_text`'s plausibility gate.
    Never touches an element whose reconstruction was ambiguous, empty,
    or already order-consistent."""
    summary = OrderRecoverySummary()
    easyocr_result = easyocr_backend.recognize(
        PageInput(page_index=0, width=page_width, height=page_height, image_path=page_image_path, dpi=dpi)
    )
    if not easyocr_result.tokens:
        return summary

    for element in page.elements:
        if not element.text or element.bbox is None:
            continue

        recon = line_cluster_reconstruction(easyocr_result.tokens, element.bbox)
        if not recon:
            continue

        jac = word_jaccard(element.text, recon)
        order = order_consistency(element.text, recon)
        record = OrderRecoveryRecord(
            element_id=element.id, old_text=element.text, reconstruction=recon,
            jaccard=round(jac, 4), order_consistency=round(order, 4), decision="kept_old",
        )

        if jac < RECON_JACCARD_MIN:
            record.reasons.append(f"jaccard={jac:.3f} below {RECON_JACCARD_MIN} -- content disagreement, not order")
        elif order >= ORDER_CONSISTENCY_MAX:
            record.reasons.append(f"order_consistency={order:.3f} -- already order-consistent")
        elif assess_text(recon).suspicious:
            record.reasons.append("reconstruction failed text_quality.assess_text")
        elif recon.strip() == element.text.strip():
            record.reasons.append("reconstruction identical to existing text")
        else:
            element.extra["order_recovery"] = {
                "old_text": element.text, "jaccard": jac, "order_consistency": order,
            }
            element.text = recon
            record.decision = "replaced"
            summary.replaced += 1
            summary.records.append(record)
            continue

        summary.kept += 1
        summary.records.append(record)

    return summary
