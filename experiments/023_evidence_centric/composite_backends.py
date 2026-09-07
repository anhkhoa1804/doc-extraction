"""Composite `OCRBackend`s that combine two independent recognizers.

These exist so conditions C/D/E of the milestone A/B run through the
*identical* production pipeline as A and B. Because they satisfy the same
`OCRBackend` protocol, `process_file` cannot tell them apart from a single
backend, so every downstream metric -- tables, reading order, assembled IR,
hallucination -- is produced by the real pipeline rather than by a
text-only side channel.

Research-only: nothing here is importable from `src/`, and none of it is
reachable from the shipped CLI. Per the milestone's production-safety rule,
they are injected into `cli._COMPONENT_BACKEND_CACHE` by the runner rather
than added as production `ocr_backend` names.

Fusion source order matters
----------------------------
`evidence_fusion._group_tokens(a, b)` is asymmetric by design: `a` supplies
the spatial *anchors* (it assumes block/line granularity) and each `b`
token is matched into the anchor it most overlaps. `_merge_agreeing_tokens`
then always keeps `b`'s tokens and adds an `a` token only when it carries a
word `b` lacks -- so `b` is the finer-grained, preferred source.

EasyOCR returns line-level detections; Tesseract TSV returns word-level
tokens. So EasyOCR is passed as `a` (anchors) and Tesseract as `b`
(preferred, finer). That is the orientation the module was built for; the
parameter names still say docling/easyocr because that was the pair that
existed when it was written.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from doc_extraction.ingest import evidence_fusion
from doc_extraction.ingest.evidence_fusion import FusionStatus
from doc_extraction.pipelines.base import OCRResult, OCRToken, PageInput


@dataclass
class PageStat:
    """Per-page instrumentation. The milestone asks for OCR invocation
    counts and per-source cost, which a single aggregate runtime hides."""

    page_index: int
    easyocr_tokens: int = 0
    tesseract_tokens: int = 0
    emitted_tokens: int = 0
    easyocr_s: float = 0.0
    tesseract_s: float = 0.0
    invocations: int = 0
    decision: str = ""
    groups: dict[str, int] = field(default_factory=dict)
    easyocr_mean_conf: float | None = None
    tesseract_mean_conf: float | None = None
    agreement: float | None = None


def _mean_conf(tokens: list[OCRToken]) -> float | None:
    vals = [t.confidence for t in tokens if t.confidence is not None]
    return sum(vals) / len(vals) if vals else None


class _DualSource:
    """Runs both recognizers over the same page and records what each cost.

    Subclasses decide what to emit. The two calls are always both made in
    C/D/E -- that is the compute these conditions actually pay, and the
    routing experiment (condition F) is the one that tries to avoid it.
    """

    def __init__(self, easyocr_backend, tesseract_backend) -> None:
        self.easy = easyocr_backend
        self.tess = tesseract_backend
        self.stats: list[PageStat] = []

    def is_available(self) -> bool:
        return self.easy.is_available() and self.tess.is_available()

    def _both(self, page: PageInput) -> tuple[list[OCRToken], list[OCRToken], PageStat]:
        stat = PageStat(page_index=page.page_index)

        t0 = time.perf_counter()
        easy_result = self.easy.recognize(page)
        stat.easyocr_s = time.perf_counter() - t0

        t0 = time.perf_counter()
        tess_result = self.tess.recognize(page)
        stat.tesseract_s = time.perf_counter() - t0

        e, t = easy_result.tokens, tess_result.tokens
        stat.easyocr_tokens, stat.tesseract_tokens = len(e), len(t)
        stat.easyocr_mean_conf, stat.tesseract_mean_conf = _mean_conf(e), _mean_conf(t)
        stat.invocations = 2
        self.stats.append(stat)
        return e, t, stat


class SelectionBackend(_DualSource):
    """Condition C -- source selection, not fusion.

    Picks one source's tokens for the whole page by mean confidence. This
    is the cheapest possible way to use two recognizers, and the control
    that says whether fusion's extra machinery earns anything over simply
    choosing the more confident reading.

    Confidence is comparable across the two only because
    `TesseractBackend` rescales 0-100 to 0.0-1.0 to match EasyOCR.
    """

    name = "selection"

    def recognize(self, page: PageInput) -> OCRResult:
        e, t, stat = self._both(page)
        ec, tc = stat.easyocr_mean_conf, stat.tesseract_mean_conf

        if ec is None and tc is None:
            chosen, why = (t or e), "neither source reported confidence"
        elif tc is None:
            chosen, why = e, "only easyocr reported confidence"
        elif ec is None:
            chosen, why = t, "only tesseract reported confidence"
        elif tc >= ec:
            chosen, why = t, f"tesseract mean confidence {tc:.3f} >= easyocr {ec:.3f}"
        else:
            chosen, why = e, f"easyocr mean confidence {ec:.3f} > tesseract {tc:.3f}"

        stat.decision = why
        stat.emitted_tokens = len(chosen)
        return OCRResult(tokens=list(chosen), backend=self.name, warnings=[why])


class UnionBackend(_DualSource):
    """Control -- naive token union, both sources concatenated.

    Experiment 012 measured that naive union beats either backend alone on
    recall; experiment 013 built evidence fusion because union duplicates
    every agreed line. This condition exists so fusion is measured against
    the crude thing it claims to improve on, not only against single
    sources. Expect high recall and high duplication.
    """

    name = "union"

    def recognize(self, page: PageInput) -> OCRResult:
        e, t, stat = self._both(page)
        stat.decision = "naive union of both sources"
        stat.emitted_tokens = len(e) + len(t)
        return OCRResult(tokens=list(e) + list(t), backend=self.name)


def fused_tokens(group) -> list[OCRToken]:
    """Token-level mirror of `EvidenceGroup.fused_text()`.

    The pipeline consumes geometry, so fusion must return tokens rather
    than a joined string -- table cell assignment and reading order both
    read `OCRToken.bbox`. This reproduces `fused_text`'s decisions exactly,
    including its central safety property: a CONFLICT still emits text.
    Dropping a conflicted region would trade a labeled uncertainty for a
    silent recall loss, which is the worse failure.
    """
    a, b = group.docling, group.easyocr  # slot a = anchors (easyocr), slot b = tesseract
    if a and b:
        if group.decision == "keep_both_agree":
            # Keep every preferred-source token; add an anchor token only
            # when it carries a word the preferred source does not have.
            b_words = evidence_fusion._words(group.easyocr_text)
            combined = list(b)
            for tok in a:
                if evidence_fusion._words(tok.text) - b_words:
                    combined.append(tok)
        else:
            combined = list(a) + list(b)
    else:
        combined = list(a) + list(b)
    return [OCRToken(text=t.text, bbox=t.bbox, confidence=t.confidence)
            for t in sorted(combined, key=lambda t: (t.bbox.y0, t.bbox.x0))]


class FusionBackend(_DualSource):
    """Condition D -- geometry-aware, conflict-aware evidence fusion.

    Uses the shipped `evidence_fusion` module rather than a new
    implementation, per the milestone's instruction to reuse it. EasyOCR
    supplies anchors, Tesseract is the preferred finer source (see module
    docstring).
    """

    name = "fusion"

    def recognize(self, page: PageInput) -> OCRResult:
        e, t, stat = self._both(page)
        groups = evidence_fusion.fuse_page(e, t)

        counts: dict[str, int] = {}
        for g in groups:
            counts[g.status.value] = counts.get(g.status.value, 0) + 1
        stat.groups = counts
        stat.decision = "evidence_fusion.fuse_page(easyocr_anchors, tesseract)"

        tokens: list[OCRToken] = []
        for g in groups:
            tokens.extend(fused_tokens(g))
        stat.emitted_tokens = len(tokens)

        sims = [g.text_similarity for g in groups if g.text_similarity is not None]
        stat.agreement = sum(sims) / len(sims) if sims else None

        warnings = [f"fusion groups: {counts}"]
        conflicts = [g for g in groups if g.status is FusionStatus.CONFLICT]
        if conflicts:
            warnings.append(f"{len(conflicts)} CONFLICT region(s) emitted with both readings")
        return OCRResult(tokens=tokens, backend=self.name, warnings=warnings)


class FusionRecoveryBackend(FusionBackend):
    """Condition E -- fusion plus the project's existing recovery logic.

    `order_recovery` is the mechanism milestone 018 validated and left
    EXPERIMENTAL. It reconstructs a scrambled reading by clustering a
    finer source's tokens into lines and sorting them; its trigger is a
    low `order_consistency` against a reference reading with high word
    overlap.

    Here it gets, for the first time, a genuinely independent second
    source to reconstruct from -- which is exactly the condition milestone
    021 showed it never had. Whether that makes it more useful is the
    question, so it is applied and measured, not assumed.
    """

    name = "fusion_recovery"

    def __init__(self, easyocr_backend, tesseract_backend) -> None:
        super().__init__(easyocr_backend, tesseract_backend)
        self.recovery_applied = 0
        self.recovery_declined = 0

    def recognize(self, page: PageInput) -> OCRResult:
        from doc_extraction.ingest import order_recovery

        e, t, stat = self._both(page)
        groups = evidence_fusion.fuse_page(e, t)

        counts: dict[str, int] = {}
        for g in groups:
            counts[g.status.value] = counts.get(g.status.value, 0) + 1
        stat.groups = counts

        tokens: list[OCRToken] = []
        for g in groups:
            group_tokens = fused_tokens(g)
            # Only regions where both sources spoke and disagreed in a way
            # consistent with scrambling are candidates: identical readings
            # need no recovery, single-source regions have nothing to
            # reconstruct against.
            if g.docling and g.easyocr and g.decision != "keep_both_agree":
                record = _try_order_recovery(order_recovery, g)
                if record is not None:
                    self.recovery_applied += 1
                    group_tokens = record
                else:
                    self.recovery_declined += 1
            tokens.extend(group_tokens)

        stat.emitted_tokens = len(tokens)
        stat.decision = (f"fusion + order_recovery "
                         f"(applied={self.recovery_applied}, declined={self.recovery_declined})")
        return OCRResult(tokens=tokens, backend=self.name,
                         warnings=[f"fusion groups: {counts}",
                                   f"order_recovery applied={self.recovery_applied}"])


def _line_clustered_tokens(tokens: list[OCRToken], region_bbox) -> list[OCRToken]:
    """Token-level mirror of `order_recovery.line_cluster_reconstruction`.

    That function returns a joined string; the pipeline needs tokens, so
    this reproduces its clustering exactly -- single-linkage on mutual
    y-overlap, each line sorted left-to-right, lines sorted top-to-bottom
    -- and returns the tokens in that order. Milestone 018 established
    directly that a naive `(y0, x0)` tuple sort is *wrong* here (three
    same-line tokens differing by 3px of y0 noise sort into the wrong
    order), so this must cluster rather than sort.
    """
    from doc_extraction.ingest.order_recovery import (
        LINE_Y_OVERLAP_MIN,
        _center_in,
        _y_overlap_fraction,
    )

    remaining = [t for t in tokens if _center_in(t.bbox, region_bbox)]
    lines: list[list[OCRToken]] = []
    while remaining:
        cluster = [remaining.pop(0)]
        changed = True
        while changed:
            changed = False
            still = []
            for t in remaining:
                if any(_y_overlap_fraction(t.bbox, m.bbox) >= LINE_Y_OVERLAP_MIN
                       for m in cluster):
                    cluster.append(t)
                    changed = True
                else:
                    still.append(t)
            remaining = still
        lines.append(cluster)

    lines.sort(key=lambda ln: sum(t.bbox.y0 for t in ln) / len(ln))
    ordered: list[OCRToken] = []
    for ln in lines:
        ln.sort(key=lambda t: t.bbox.x0)
        ordered.extend(ln)
    return ordered


def _try_order_recovery(order_recovery, group) -> list[OCRToken] | None:
    """Apply `order_recovery`'s *documented decision rule* to one fusion
    group, returning line-clustered tokens or None if it declines.

    `recover_page_order` is a post-assembly pass over `Element`s and cannot
    be called here, so this reuses the module's public primitives and its
    three stated conditions rather than reimplementing a private path:

      (a) the reconstruction agrees on WHICH words are present
          (`word_jaccard >= RECON_JACCARD_MIN`) -- this is the guard that
          refuses to "fix" a region where content is genuinely missing,
          the case milestone 018 showed a reconstruction makes worse;
      (b) the two readings disagree on ORDER specifically
          (`order_consistency < ORDER_CONSISTENCY_MAX`);
      (c) the reconstruction passes `assess_text`'s plausibility gate.

    Failure-tolerant: an exception in a research probe must not abort a
    58-document benchmark run.
    """
    from doc_extraction.ingest.text_quality import assess_text

    reference = group.docling_text  # slot a = easyocr anchors
    source_tokens = [OCRToken(text=t.text, bbox=t.bbox, confidence=t.confidence)
                     for t in group.easyocr]  # slot b = tesseract, finer
    if not reference or not source_tokens:
        return None
    try:
        recon = order_recovery.line_cluster_reconstruction(source_tokens, group.bbox)
        if not recon:
            return None
        if order_recovery.word_jaccard(recon, reference) < order_recovery.RECON_JACCARD_MIN:
            return None
        if order_recovery.order_consistency(reference, recon) >= order_recovery.ORDER_CONSISTENCY_MAX:
            return None
        if assess_text(recon).suspicious:
            return None
        return _line_clustered_tokens(source_tokens, group.bbox)
    except Exception:  # noqa: BLE001 - a probe failure is a declined recovery
        return None
