"""025 -- deterministic layout-coverage interventions. Research only.

Each entry is a pure function applied to a page's DETECTED regions before
`merge_regions_into_page` consumes them. Production code is untouched; the
A/B harness installs these on the objects it constructs itself.

Which interventions exist here is decided by `orphan_topology.json`, not by
the proposal's guesses, and the measurement redirected them:

  proposal intervention 1 (region gap recovery)  -> `gap_region`, below
  proposal intervention 2 (column-gap recovery)  -> subsumed by `gap_region`;
      lateral-band orphans are 28 tokens on 2 pages, and the same cluster
      rule catches them, so a separate column-only arm would differ from
      `gap_region` on nothing and is not worth a run.
  proposal intervention 3 (table extent recovery) -> NOT IMPLEMENTED. It
      presupposes a detected table whose extent is short. The three failing
      table documents have NO detected table at all: layout returns 13-17
      `text` regions plus a `picture` and never labels a table, at coverage
      recall 1.000. There is no extent to extend.
  proposal intervention 4 (confidence-aware fallback) -> NOT IMPLEMENTABLE.
      Docling emits `confidence=None` on all 258 regions.

`gap_region` is therefore the single arm the evidence supports, and it is
deliberately the MAXIMAL version of the hypothesis: every coherent orphan
cluster becomes a region. If upstream coverage repair can change anything,
this arm changes it.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from doc_extraction.pipelines.base import Region, _cluster_orphans, _orphan_tokens  # noqa: E402
from doc_extraction.schemas.element import BBox  # noqa: E402


def gap_region(regions, ocr_result, tables, width, height):
    """Synthesize one `text` region per coherent cluster of orphan tokens.

    Orphans and clustering both come from production (`_orphan_tokens`,
    `_cluster_orphans`), so this covers exactly the tokens L5 would have
    rescued -- the arm isolates WHERE the repair happens (layout vs
    post-merge fallback), not WHICH tokens it touches. The same alphanumeric
    guard L5 uses applies, so rule and border glyph runs do not become
    regions.
    """
    orphans = _orphan_tokens(regions, ocr_result, tables)
    out: list[Region] = []
    for block in _cluster_orphans(orphans):
        text = " ".join(t.text for t in block if t.text)
        if not any(ch.isalnum() for ch in text):
            continue
        out.append(Region(
            bbox=BBox(
                x0=min(t.bbox.x0 for t in block), y0=min(t.bbox.y0 for t in block),
                x1=max(t.bbox.x1 for t in block), y1=max(t.bbox.y1 for t in block),
            ),
            label="text",
            confidence=None,
            source_id="025_gap_region",
        ))
    return out


REGISTRY = {
    "none": None,
    "gap_region": gap_region,
}
