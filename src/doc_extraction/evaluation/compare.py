"""Backend comparison (spec §9): run several whole-document backends over
the same file and produce a diffable summary. Purely descriptive counts —
not a scored benchmark, see evaluation/metrics.py.
"""
from __future__ import annotations

import html
from pathlib import Path
from typing import Any

from doc_extraction.evaluation.disagreement import all_pairwise
from doc_extraction.evaluation.metrics import document_stats
from doc_extraction.schemas.document import Document

_METRIC_ROWS = [
    ("status", "Status"),
    ("num_pages", "Pages"),
    ("num_elements", "Elements"),
    ("num_tables", "Tables"),
    ("num_table_cells", "Table cells"),
    ("total_text_chars", "Text chars"),
    ("mean_confidence", "Mean confidence"),
    ("runtime_seconds", "Runtime (s)"),
    ("device", "Device"),
    ("error", "Error"),
]


def build_comparison(
    path: Path,
    documents: dict[str, Document | None],
    errors: dict[str, str],
) -> dict[str, Any]:
    """Per-backend stats plus pairwise structural disagreement.

    Deliberately produces no aggregate "quality score": there is no ground
    truth for this corpus, and a single number would hide exactly the
    per-page detail that makes this useful for failure analysis.
    """
    per_backend: dict[str, Any] = {}
    for backend_name, document in documents.items():
        if document is None:
            per_backend[backend_name] = {"status": "failed", "error": errors.get(backend_name, "unknown error")}
            continue
        per_backend[backend_name] = {"status": "ok", **document_stats(document)}

    return {
        "input_file": path.name,
        "backends": per_backend,
        "disagreements": all_pairwise(documents),
    }


def render_comparison_html(path: Path, comparison: dict[str, Any]) -> str:
    backend_names = list(comparison["backends"].keys())
    header_cells = "".join(f"<th>{html.escape(b)}</th>" for b in backend_names)
    rows = []
    for key, label in _METRIC_ROWS:
        cells = []
        for backend_name in backend_names:
            value = comparison["backends"][backend_name].get(key, "")
            if isinstance(value, float):
                value = f"{value:.3f}"
            cells.append(f"<td>{html.escape(str(value))}</td>")
        rows.append(f"<tr><th>{label}</th>{''.join(cells)}</tr>")

    element_type_row_backends = [
        comparison["backends"][b].get("element_type_counts", {}) for b in backend_names
    ]
    all_types = sorted({t for counts in element_type_row_backends for t in counts})
    type_rows = []
    for etype in all_types:
        cells = "".join(f"<td>{counts.get(etype, 0)}</td>" for counts in element_type_row_backends)
        type_rows.append(f"<tr><th>{html.escape(etype)}</th>{cells}</tr>")

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Comparison: {html.escape(path.name)}</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 2rem; color: #222; }}
  table {{ border-collapse: collapse; margin-bottom: 2rem; }}
  th, td {{ border: 1px solid #ccc; padding: 6px 14px; text-align: left; }}
  th {{ background: #f0f0f0; }}
  h2 {{ margin-top: 2rem; }}
  .note {{ color: #666; font-size: .9rem; max-width: 60rem; }}
  td.flag {{ background: #ffe9e0; font-weight: 600; }}
</style></head>
<body>
  <h1>{html.escape(path.name)}</h1>
  <p class="note">Descriptive comparison only — there is no ground truth for this corpus,
  so nothing here is a quality score. Large deltas mark pages worth inspecting.</p>
  <table><tr><th>Metric</th>{header_cells}</tr>{''.join(rows)}</table>
  <h2>Element type counts</h2>
  <table><tr><th>Type</th>{header_cells}</tr>{''.join(type_rows) or '<tr><td colspan="99">no elements</td></tr>'}</table>
  {_render_disagreements(comparison.get("disagreements", []))}
</body></html>"""


def _render_disagreements(disagreements: list[dict[str, Any]]) -> str:
    if not disagreements:
        return (
            "<h2>Disagreement</h2><p class='note'>Only one backend produced output, "
            "so there is nothing to compare against.</p>"
        )

    sections = []
    for pair in disagreements:
        page_rows = []
        for page in pair["pages"]:
            similarity = page["text_similarity"]
            correlation = page["reading_order_correlation"]
            sim_class = " class='flag'" if similarity is not None and similarity < 0.6 else ""
            corr_class = " class='flag'" if correlation is not None and correlation < 0.9 else ""
            tbl_class = " class='flag'" if page["table_count_delta"] != 0 else ""
            page_rows.append(
                f"<tr><td>{page['page_index'] + 1}</td>"
                f"<td>{page['left_elements']} / {page['right_elements']}</td>"
                f"<td{tbl_class}>{page['left_tables']} / {page['right_tables']}</td>"
                f"<td>{page['left_text_chars']} / {page['right_text_chars']}</td>"
                f"<td{sim_class}>{similarity}</td>"
                f"<td>{page['bbox_match_rate']}</td>"
                f"<td>{page['mean_matched_iou']}</td>"
                f"<td{corr_class}>{correlation}</td></tr>"
            )
        sections.append(
            f"<h3>{html.escape(pair['left'])} vs {html.escape(pair['right'])}</h3>"
            f"<p class='note'>pages {pair['left_pages']} / {pair['right_pages']} &middot; "
            f"mean text similarity {pair['mean_text_similarity']}</p>"
            "<table><tr><th>page</th><th>elements L/R</th><th>tables L/R</th>"
            "<th>text chars L/R</th><th>text similarity</th><th>bbox match rate</th>"
            "<th>mean IoU</th><th>reading-order corr.</th></tr>"
            f"{''.join(page_rows) or '<tr><td colspan=8>no comparable pages</td></tr>'}</table>"
        )
    return "<h2>Disagreement (pairwise)</h2>" + "".join(sections)
