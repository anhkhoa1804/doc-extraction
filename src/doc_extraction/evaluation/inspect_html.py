"""Human-readable per-document HTML inspector (spec §10): page image + bbox
overlays + element text + table structure, all in one static page with no
JS-framework dependency. Reads a document's already-written
outputs/<document_id>/final/document.json — this never re-runs the pipeline.
"""
from __future__ import annotations

import html
import os
from pathlib import Path

from doc_extraction.schemas.document import Document
from doc_extraction.schemas.element import ElementType
from doc_extraction.schemas.page import Page

_TYPE_COLORS: dict[str, str] = {
    "text": "#4c78a8",
    "heading": "#e45756",
    "paragraph": "#4c78a8",
    "list_item": "#72b7b2",
    "table": "#f58518",
    "image": "#b279a2",
    "formula": "#54a24b",
    "checkbox": "#eeca3b",
    "signature": "#d62728",
    "other": "#999999",
}


def _bbox_overlay_style(bbox, page_width: float, page_height: float) -> str:
    if not page_width or not page_height:
        return "display:none;"
    left = 100 * bbox.x0 / page_width
    top = 100 * bbox.y0 / page_height
    width = 100 * (bbox.x1 - bbox.x0) / page_width
    height = 100 * (bbox.y1 - bbox.y0) / page_height
    return f"left:{left:.3f}%; top:{top:.3f}%; width:{width:.3f}%; height:{height:.3f}%;"


def _render_page(page: Page, inspection_dir: Path) -> str:
    color_legend = "".join(
        f'<span class="legend-item"><span class="swatch" style="background:{color}"></span>{etype}</span>'
        for etype, color in _TYPE_COLORS.items()
    )

    image_block = ""
    if page.rendered_image_path:
        image_abs = Path(page.rendered_image_path).resolve()
        image_rel = Path(os.path.relpath(image_abs, inspection_dir.resolve()))
        overlays = []
        for element in page.elements:
            if element.bbox is None:
                continue
            color = _TYPE_COLORS.get(element.type.value, "#999999")
            title = html.escape((element.text or element.type.value)[:120])
            style = _bbox_overlay_style(element.bbox, page.width, page.height)
            overlays.append(
                f'<div class="bbox" style="{style} border-color:{color};" title="{title}">'
                f'<span class="bbox-label" style="background:{color};">{element.type.value}</span></div>'
            )
        image_block = f"""
        <div class="page-viewer">
          <img src="{image_rel.as_posix()}" alt="page {page.index + 1}">
          {''.join(overlays)}
        </div>"""

    element_rows = []
    order = page.reading_order or [e.id for e in page.elements]
    for position, element_id in enumerate(order):
        element = page.element_by_id(element_id)
        if element is None:
            continue
        text_preview = html.escape((element.text or "")[:200])
        bbox_str = (
            f"({element.bbox.x0:.0f},{element.bbox.y0:.0f})-({element.bbox.x1:.0f},{element.bbox.y1:.0f})"
            if element.bbox
            else "-"
        )
        table_html = ""
        if element.type == ElementType.TABLE and element.table_id:
            table = page.table_by_id(element.table_id)
            if table is not None:
                grid = table.to_grid()
                body_rows = "".join(
                    "<tr>" + "".join(f"<td>{html.escape(cell)}</td>" for cell in row) + "</tr>"
                    for row in grid
                )
                table_html = f'<table class="mini-table">{body_rows}</table>'
        element_rows.append(
            f"<tr><td>{position}</td><td>{element.type.value}</td><td>{element.confidence if element.confidence is not None else '-'}</td>"
            f"<td>{bbox_str}</td><td>{text_preview}{table_html}</td></tr>"
        )

    note_flags = [n for n in page.notes if n.startswith("SUSPECT") or "fallback" in n]
    notes_block = ""
    if page.notes:
        css_class = "notes flagged" if note_flags else "notes"
        notes_block = (
            f'<ul class="{css_class}">'
            + "".join(f"<li>{html.escape(n)}</li>" for n in page.notes)
            + "</ul>"
        )
    provenance = " &middot; ".join(
        filter(
            None,
            [
                f"route={html.escape(page.source_route)}" if page.source_route else None,
                f"backend={html.escape(page.source_backend)}" if page.source_backend else None,
                "logical page (not a rendered page)" if not page.is_rendered_page else None,
            ],
        )
    )

    return f"""
    <section class="page-section">
      <h2>Page {page.index + 1} <small>{page.width:.0f} x {page.height:.0f} ({page.coordinate_unit}, origin {page.coordinate_origin}{f', {page.dpi} dpi' if page.dpi else ''})</small></h2>
      <div class="provenance">{provenance}</div>
      {notes_block}
      <div class="legend">{color_legend}</div>
      {image_block}
      <table class="elements-table">
        <tr><th>#</th><th>type</th><th>conf</th><th>bbox</th><th>content</th></tr>
        {''.join(element_rows) or '<tr><td colspan="5">no elements</td></tr>'}
      </table>
    </section>"""


def render_inspection_html(document: Document, inspection_dir: Path) -> str:
    pages_html = "".join(_render_page(page, inspection_dir) for page in document.pages)
    return f"""<!doctype html>
<html><head><meta charset="utf-8">
<title>Inspect: {html.escape(document.metadata.input_filename)}</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 2rem; color: #222; }}
  h1 {{ margin-bottom: 0; }}
  .meta {{ color: #666; margin-bottom: 2rem; }}
  .page-section {{ margin-bottom: 3rem; border-top: 1px solid #ddd; padding-top: 1rem; }}
  .legend {{ margin-bottom: .5rem; font-size: .85rem; }}
  .legend-item {{ margin-right: 1rem; }}
  .swatch {{ display:inline-block; width:10px; height:10px; margin-right:4px; border-radius:2px; }}
  .page-viewer {{ position: relative; display: inline-block; max-width: 900px; margin-bottom: 1rem; }}
  .page-viewer img {{ width: 100%; display: block; border: 1px solid #ccc; }}
  .bbox {{ position: absolute; border: 2px solid; background: rgba(255,255,255,0.02); }}
  .bbox-label {{ position: absolute; top: -1.1em; left: 0; font-size: 10px; color: white; padding: 0 3px; white-space: nowrap; }}
  table.elements-table {{ border-collapse: collapse; width: 100%; font-size: .85rem; }}
  table.elements-table th, table.elements-table td {{ border: 1px solid #ddd; padding: 4px 8px; vertical-align: top; }}
  table.elements-table th {{ background: #f5f5f5; text-align: left; }}
  table.mini-table {{ border-collapse: collapse; margin-top: 4px; }}
  table.mini-table td {{ border: 1px solid #ddd; padding: 2px 6px; font-size: .8rem; }}
  .provenance {{ color: #666; font-size: .85rem; margin-bottom: .4rem; }}
  ul.notes {{ font-size: .85rem; color: #555; background: #f7f7f7; padding: .5rem 1.5rem; border-radius: 4px; }}
  ul.notes.flagged {{ background: #ffe9e0; color: #7a2c10; }}
</style></head>
<body>
  <h1>{html.escape(document.metadata.input_filename)}</h1>
  <div class="meta">
    document_id={html.escape(document.document_id)} &middot;
    schema={html.escape(document.schema_version)} &middot;
    route={html.escape(document.metadata.route)} &middot;
    pipeline={html.escape(document.metadata.pipeline)} &middot;
    backend={html.escape(document.metadata.backend)} &middot;
    runtime={document.metadata.runtime_seconds if document.metadata.runtime_seconds is not None else '-'}s &middot;
    device={html.escape(document.metadata.device)}
    {f'<div>route reason: {html.escape(document.metadata.route_reason)}</div>' if document.metadata.route_reason else ''}
    {f'<div class="doc-warnings">warnings: {html.escape("; ".join(document.metadata.warnings))}</div>' if document.metadata.warnings else ''}
  </div>
  {pages_html}
</body></html>"""
