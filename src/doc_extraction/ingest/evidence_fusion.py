"""Evidence Fusion v0 — combine two OCR backends' structured readings of the
same page instead of picking one, or blindly concatenating both.

Why this exists
----------------
Experiment 012 measured that naive text-level union of Docling's and direct
EasyOCR's output beats either backend alone (mean word recall 0.9286 vs
0.9111 best single backend), and that cross-backend word-Jaccard agreement
predicts recall far better than either backend's own confidence (r=0.856
vs r=0.491). But naive union duplicates every line the two backends agree
on, and confidence/agreement were only measured at whole-document
granularity — neither tells a consumer *which part* of a page is trustworthy.

This module operates at region granularity instead: it aligns each
backend's tokens spatially, decides per-region whether the two sources
agree, disagree, or only one has evidence at all, and only then produces a
final text — one that keeps agreeing text once (not twice), keeps
single-source text with its own evidence quality noted, and marks
disagreement as CONFLICT rather than silently concatenating both readings
into a string that reads as if it were one coherent finding.

What this deliberately does not do
------------------------------------
It is not a learned model — every decision is a threshold over measured,
interpretable quantities (bbox overlap, word-Jaccard text similarity,
confidence, `text_quality.assess_text`'s plausibility gate). It does not
touch table structure: Docling's `recognize()` already flattens table
cells to plain OCR tokens (see `docling_backend.py`), and this module
fuses OCR tokens exactly the way experiment 012 did — table geometry
fusion is a separate, harder problem, deferred per that experiment's own
scope note. It is not wired into the production pipeline or CLI: this is
an experimental research primitive (`experiments/013_evidence_fusion/`)
until a benchmark demonstrates a net win with no unacceptable regression.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from enum import Enum

from doc_extraction.ingest.text_quality import assess_text
from doc_extraction.pipelines.base import OCRToken
from doc_extraction.schemas.element import BBox

# Mirrors `ingest.verification._words` exactly (same regex, same NFC
# normalization) so fusion's notion of "these two readings agree" is
# identical to the whole-document signal already measured in experiment
# 012/verification.py, not a second, subtly-different tokenizer.
_WORD_RE = re.compile(r"[^0-9a-zà-ỹăâđêôơư]+", re.IGNORECASE)


def _words(text: str) -> set[str]:
    normalized = unicodedata.normalize("NFC", text or "").lower()
    return {w for w in _WORD_RE.split(normalized) if w}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def _area(b: BBox) -> float:
    return max(0.0, b.x1 - b.x0) * max(0.0, b.y1 - b.y0)


def _intersection_area(a: BBox, b: BBox) -> float:
    ix0, iy0 = max(a.x0, b.x0), max(a.y0, b.y0)
    ix1, iy1 = min(a.x1, b.x1), min(a.y1, b.y1)
    return max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)


def _union_bbox(boxes: list[BBox]) -> BBox:
    return BBox(
        x0=min(b.x0 for b in boxes), y0=min(b.y0 for b in boxes),
        x1=max(b.x1 for b in boxes), y1=max(b.y1 for b in boxes),
    )


def _iou(a: BBox, b: BBox) -> float:
    inter = _intersection_area(a, b)
    union = _area(a) + _area(b) - inter
    return inter / union if union > 0 else 0.0


class FusionStatus(str, Enum):
    TRUSTED = "trusted"
    SUSPICIOUS = "suspicious"
    CONFLICT = "conflict"


# Thresholds are rough starting points calibrated by inspection against
# experiment 012's 13-document corpus, exactly like verification.py's
# AGREEMENT_SUSPICIOUS_BELOW = 0.5 — not tuned, and stated as such so a
# future session does not mistake either for a calibrated value.
MATCH_OVERLAP_MIN = 0.4  # fraction of an EasyOCR token's area that must fall inside a Docling anchor to count as "the same region"
AGREE_SIMILARITY_MIN = 0.7  # word-Jaccard at/above this -> the two sides are saying the same thing
CONFLICT_SIMILARITY_MAX = 0.3  # word-Jaccard below this, with both sides present -> CONFLICT, not a blend
LOW_CONFIDENCE_MAX = 0.4  # single-source EasyOCR evidence below this confidence is downgraded to SUSPICIOUS


@dataclass
class EvidenceToken:
    """One backend's reading of one detection, with the provenance fields
    the mission asked for kept explicit rather than folded into a string."""

    text: str
    bbox: BBox
    confidence: float | None
    source: str  # "docling" | "easyocr"
    order: int  # index in that source's own OCRResult.tokens, i.e. that backend's reading order


@dataclass
class EvidenceGroup:
    """One spatial region of the page, with every source's evidence for it
    and the fusion decision reached over that evidence — never a flattened
    "AB" string standing in for two sources that disagree."""

    bbox: BBox
    docling: list[EvidenceToken] = field(default_factory=list)
    easyocr: list[EvidenceToken] = field(default_factory=list)
    text_similarity: float | None = None  # None when only one source has evidence
    bbox_overlap: float | None = None  # IoU between the two sides' union bboxes; None when single-source
    status: FusionStatus = FusionStatus.TRUSTED
    decision: str = ""  # "single_docling" | "single_easyocr" | "keep_both_agree" | "keep_both_partial" | "conflict"
    reasons: list[str] = field(default_factory=list)

    @property
    def docling_text(self) -> str:
        return " ".join(t.text for t in sorted(self.docling, key=lambda t: (t.bbox.y0, t.bbox.x0)))

    @property
    def easyocr_text(self) -> str:
        return " ".join(t.text for t in sorted(self.easyocr, key=lambda t: (t.bbox.y0, t.bbox.x0)))

    @property
    def easyocr_mean_confidence(self) -> float | None:
        confs = [t.confidence for t in self.easyocr if t.confidence is not None]
        return sum(confs) / len(confs) if confs else None

    def fused_text(self) -> str:
        """The text this group contributes to the assembled page. Present
        for every status including CONFLICT — CONFLICT changes what a
        *consumer* should do with the text (flag for review / targeted
        recovery), not whether text is emitted at all; dropping it would
        trade a labeled uncertainty for a silent recall loss, which is a
        worse failure mode for a v0 that has not yet built a recovery path."""
        if self.docling and self.easyocr:
            if self.decision == "keep_both_agree":
                return self._merge_agreeing_tokens()
            # partial agreement or conflict: neither side is emitted alone;
            # both raw readings are kept verbatim (recall over an uncertain
            # union beats a confident guess at which one is right) and the
            # uncertainty itself is carried at group.status, not silently
            # resolved into a single blended string.
            return f"{self.docling_text} {self.easyocr_text}"
        return self.docling_text or self.easyocr_text

    def _merge_agreeing_tokens(self) -> str:
        """Fix for the diagnosed v0 bug (experiment 013): picking one
        side's full string on "agree" can silently drop a word that only
        survives on the *other* side, even at high aggregate similarity --
        e.g. a Docling anchor reading "Section 1. Scope ..." merged with an
        EasyOCR reading "Scope Section ..." that is missing the "1"
        (word-Jaccard 0.80, correctly judged as "agree", but not identical).

        Fix operates on tokens, not strings: EasyOCR's tokens are always
        kept (finer granularity, carries confidence, the marginally
        stronger single backend per experiment 012). A Docling token is
        added to the output *only if* it contains at least one normalized
        word absent from the combined EasyOCR reading of this region --
        i.e. only if it actually carries information EasyOCR's tokens do
        not. A Docling token whose words are a subset of EasyOCR's is
        redundant and excluded, so a region where the two sides read
        identically still emits exactly one copy -- this is what keeps
        duplicate rate down relative to naive union, while the subset
        check is what stops information loss."""
        e_words = _words(self.easyocr_text)
        combined = list(self.easyocr)
        for d_tok in self.docling:
            if _words(d_tok.text) - e_words:
                combined.append(d_tok)
        return " ".join(t.text for t in sorted(combined, key=lambda t: (t.bbox.y0, t.bbox.x0)))


def _group_tokens(docling_tokens: list[OCRToken], easyocr_tokens: list[OCRToken]) -> list[EvidenceGroup]:
    """Align two token streams spatially. Docling's tokens are used as
    anchors (they are already line/block granularity — see
    `docling_backend.py`'s module docstring), each EasyOCR token is matched
    to the anchor it overlaps most, and any EasyOCR token that overlaps no
    anchor above `MATCH_OVERLAP_MIN` becomes its own singleton region --
    this is exactly the case that matters most operationally: Docling
    dropped a whole region (as the traverse_pictures bug did, see
    experiment 011) and only EasyOCR has evidence for it at all."""
    anchors = [
        EvidenceGroup(bbox=tok.bbox, docling=[EvidenceToken(tok.text, tok.bbox, tok.confidence, "docling", i)])
        for i, tok in enumerate(docling_tokens)
    ]
    orphans: list[EvidenceGroup] = []

    for j, tok in enumerate(easyocr_tokens):
        ev = EvidenceToken(tok.text, tok.bbox, tok.confidence, "easyocr", j)
        tok_area = _area(tok.bbox)
        best_idx, best_frac = -1, 0.0
        for idx, anchor in enumerate(anchors):
            if tok_area <= 0:
                continue
            frac = _intersection_area(tok.bbox, anchor.bbox) / tok_area
            if frac > best_frac:
                best_idx, best_frac = idx, frac
        if best_idx >= 0 and best_frac >= MATCH_OVERLAP_MIN:
            anchors[best_idx].easyocr.append(ev)
        else:
            orphans.append(EvidenceGroup(bbox=tok.bbox, easyocr=[ev]))

    return anchors + orphans


def _decide(group: EvidenceGroup) -> None:
    """Fill in `status`, `decision`, `reasons`, `text_similarity`,
    `bbox_overlap` for one already-grouped region. Every branch is a
    threshold over a measured quantity — no learned weighting."""
    has_d, has_e = bool(group.docling), bool(group.easyocr)

    if has_d and not has_e:
        report = assess_text(group.docling_text)
        group.status = FusionStatus.SUSPICIOUS if report.suspicious else FusionStatus.TRUSTED
        group.decision = "single_docling"
        group.reasons = ["only docling has evidence for this region"] + report.reasons
        return

    if has_e and not has_d:
        report = assess_text(group.easyocr_text)
        conf = group.easyocr_mean_confidence
        low_conf = conf is not None and conf < LOW_CONFIDENCE_MAX
        group.status = FusionStatus.SUSPICIOUS if (report.suspicious or low_conf) else FusionStatus.TRUSTED
        group.decision = "single_easyocr"
        reasons = ["only easyocr has evidence for this region (docling likely dropped or missed it)"]
        if conf is not None:
            reasons.append(f"mean confidence={conf:.2f}")
        group.reasons = reasons + report.reasons
        return

    # Both sides present.
    d_words, e_words = _words(group.docling_text), _words(group.easyocr_text)
    similarity = _jaccard(d_words, e_words)
    group.text_similarity = similarity
    union_bbox_d = _union_bbox([t.bbox for t in group.docling])
    union_bbox_e = _union_bbox([t.bbox for t in group.easyocr])
    group.bbox_overlap = _iou(union_bbox_d, union_bbox_e)

    if similarity >= AGREE_SIMILARITY_MIN:
        group.status = FusionStatus.TRUSTED
        group.decision = "keep_both_agree"
        group.reasons = [f"docling/easyocr word-agreement={similarity:.2f}"]
    elif similarity < CONFLICT_SIMILARITY_MAX:
        group.status = FusionStatus.CONFLICT
        group.decision = "conflict"
        group.reasons = [
            f"docling/easyocr word-agreement={similarity:.2f} (below {CONFLICT_SIMILARITY_MAX})",
            f"docling reads: {group.docling_text!r}",
            f"easyocr reads: {group.easyocr_text!r}",
        ]
    else:
        group.status = FusionStatus.SUSPICIOUS
        group.decision = "keep_both_partial"
        group.reasons = [f"docling/easyocr word-agreement={similarity:.2f} (partial)"]


def fuse_page(docling_tokens: list[OCRToken], easyocr_tokens: list[OCRToken]) -> list[EvidenceGroup]:
    """Full v0 fusion pipeline for one page: group tokens spatially, decide
    each group's status, return groups in reading-order (top-to-bottom,
    banded, then left-to-right within a band -- a coarse but reasonable
    approximation given neither source's own ordering can be assumed to
    survive spatial regrouping)."""
    groups = _group_tokens(docling_tokens, easyocr_tokens)
    for g in groups:
        _decide(g)

    def sort_key(g: EvidenceGroup) -> tuple[float, float]:
        band = round(g.bbox.y0 / 20.0)
        return (band, g.bbox.x0)

    return sorted(groups, key=sort_key)


def assemble_fused_text(groups: list[EvidenceGroup]) -> str:
    return " ".join(g.fused_text() for g in groups if g.fused_text())


@dataclass
class FusionSummary:
    n_groups: int = 0
    n_single_docling: int = 0
    n_single_easyocr: int = 0
    n_agree: int = 0
    n_partial: int = 0
    n_conflict: int = 0

    @property
    def conflict_rate(self) -> float:
        dual = self.n_agree + self.n_partial + self.n_conflict
        return self.n_conflict / dual if dual else 0.0

    def as_dict(self) -> dict:
        return {
            "n_groups": self.n_groups,
            "n_single_docling": self.n_single_docling,
            "n_single_easyocr": self.n_single_easyocr,
            "n_agree": self.n_agree,
            "n_partial": self.n_partial,
            "n_conflict": self.n_conflict,
            "conflict_rate": round(self.conflict_rate, 4),
        }


def summarize(groups: list[EvidenceGroup]) -> FusionSummary:
    s = FusionSummary(n_groups=len(groups))
    for g in groups:
        if g.decision == "single_docling":
            s.n_single_docling += 1
        elif g.decision == "single_easyocr":
            s.n_single_easyocr += 1
        elif g.decision == "keep_both_agree":
            s.n_agree += 1
        elif g.decision == "keep_both_partial":
            s.n_partial += 1
        elif g.decision == "conflict":
            s.n_conflict += 1
    return s
