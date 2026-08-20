#!/usr/bin/env python
"""Build a side-by-side HTML view of one OmniDocBench sample: the page
image with ground-truth layout boxes overlaid, next to our generated
prediction Markdown. A static page, in the same spirit as
doc_extraction's own outputs/<id>/inspection/index.html — no bbox-matching
logic is reimplemented here (that's the official evaluator's job); this is
purely for a human to look at a page and its prediction together.

    python experiments/005_omnidocbench/inspect.py \\
        --dataset experiments/005_omnidocbench/dataset/demo \\
        --prediction experiments/005_omnidocbench/results/baseline/predictions \\
        --sample notes_1ba14cb325bc448f7201b20502ecf2b5_15.jpg \\
        --output experiments/005_omnidocbench/results/baseline/inspection

Omit --sample to build a page for every sample with a matching prediction.
"""
from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from doc_extraction.evaluation import omnidocbench as odb  # noqa: E402

_CATEGORY_COLORS = {
    "title": "#e45756", "text_block": "#4c78a8", "table": "#f58518",
    "figure": "#b279a2", "equation_isolated": "#54a24b", "header": "#999999",
    "footer": "#999999", "page_number": "#999999", "reference": "#72b7b2",
}
_DEFAULT_COLOR = "#666666"


def _record_for_sample(dataset_root: Path, sample_name: str) -> tuple[dict, Path]:
    gt_path, samples = odb.load_dataset(dataset_root)
    raw = json.loads(gt_path.read_text(encoding="utf-8"))
    for record in raw:
        if Path(record.get("page_info", {}).get("image_path", "")).name == sample_name:
            match = next((s for s in samples if s.image_name == sample_name), None)
            if match is None:
                raise odb.DatasetError(f"{sample_name} has a GT record but its image file is missing")
            return record, match.image_path
    raise odb.DatasetError(f"no record for {sample_name!r} in {gt_path}")


def _render_sample(record: dict, image_path: Path, prediction_text: str, output_dir: Path) -> Path:
    import os

    output_dir.mkdir(parents=True, exist_ok=True)
    image_rel = Path(os.path.relpath(image_path.resolve(), output_dir.resolve())).as_posix()

    page_info = record.get("page_info", {})
    width = float(page_info.get("width") or 1)
    height = float(page_info.get("height") or 1)
    image_name = image_path.name

    overlays = []
    legend_seen: dict[str, str] = {}
    for det in record.get("layout_dets", []):
        poly = det.get("poly")
        if not poly or len(poly) != 8:
            continue
        bbox = odb.omnidocbench_poly_to_bbox(poly)
        category = det.get("category_type", "unknown")
        color = _CATEGORY_COLORS.get(category, _DEFAULT_COLOR)
        legend_seen[category] = color
        title = html.escape((det.get("text") or det.get("html") or det.get("latex") or category)[:150])
        left, top = 100 * bbox.x0 / width, 100 * bbox.y0 / height
        w, h = 100 * bbox.width / width, 100 * bbox.height / height
        overlays.append(
            f'<div class="bbox" style="left:{left:.3f}%;top:{top:.3f}%;width:{w:.3f}%;height:{h:.3f}%;'
            f'border-color:{color};" title="{title}"></div>'
        )

    legend_html = "".join(
        f'<span class="legend-item"><span class="swatch" style="background:{c}"></span>{html.escape(cat)}</span>'
        for cat, c in sorted(legend_seen.items())
    )

    doc = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>OmniDocBench: {html.escape(image_name)}</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 2rem; color: #222; }}
  .columns {{ display: flex; gap: 2rem; align-items: flex-start; flex-wrap: wrap; }}
  .page-viewer {{ position: relative; display: inline-block; max-width: 600px; }}
  .page-viewer img {{ width: 100%; display: block; border: 1px solid #ccc; }}
  .bbox {{ position: absolute; border: 2px solid; background: rgba(255,255,255,0.02); }}
  .legend {{ margin-bottom: .5rem; font-size: .85rem; }}
  .legend-item {{ margin-right: 1rem; }}
  .swatch {{ display:inline-block; width:10px; height:10px; margin-right:4px; border-radius:2px; }}
  pre.prediction {{ background: #f7f7f7; padding: 1rem; max-width: 600px; white-space: pre-wrap;
                     word-wrap: break-word; border-radius: 4px; font-size: .85rem; }}
  h2 {{ font-size: 1rem; }}
</style></head>
<body>
  <h1>{html.escape(image_name)}</h1>
  <p>page_no={page_info.get('page_no')} &middot; {width:.0f}x{height:.0f} &middot;
     attributes: {html.escape(json.dumps(page_info.get('page_attribute', {}), ensure_ascii=False))}</p>
  <div class="columns">
    <div>
      <h2>Ground truth layout ({len(record.get('layout_dets', []))} regions)</h2>
      <div class="legend">{legend_html}</div>
      <div class="page-viewer">
        <img src="{html.escape(image_rel)}" alt="{html.escape(image_name)}">
        {''.join(overlays)}
      </div>
    </div>
    <div>
      <h2>Our prediction (Markdown)</h2>
      <pre class="prediction">{html.escape(prediction_text)}</pre>
    </div>
  </div>
</body></html>"""
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{Path(image_name).stem}.html"
    out_path.write_text(doc, encoding="utf-8")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--prediction", required=True, help="Predictions directory (from prepare.py).")
    parser.add_argument("--sample", default=None, help="One image filename; omit to build every matched sample.")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)

    dataset_root = Path(args.dataset).resolve()
    predictions_dir = Path(args.prediction).resolve()
    output_dir = Path(args.output).resolve()

    try:
        gt_path, samples = odb.load_dataset(dataset_root)
    except odb.DatasetError as exc:
        print(f"dataset error: {exc}", file=sys.stderr)
        return 1
    raw = json.loads(gt_path.read_text(encoding="utf-8"))
    records_by_image = {Path(r.get("page_info", {}).get("image_path", "")).name: r for r in raw}

    targets = [args.sample] if args.sample else [s.image_name for s in samples]
    built = []
    for image_name in targets:
        record = records_by_image.get(image_name)
        sample = next((s for s in samples if s.image_name == image_name), None)
        if record is None or sample is None:
            print(f"  skip {image_name}: not in dataset", file=sys.stderr)
            continue
        pred_path = predictions_dir / sample.prediction_filename
        if not pred_path.exists():
            print(f"  skip {image_name}: no prediction at {pred_path}", file=sys.stderr)
            continue
        out = _render_sample(record, sample.image_path, pred_path.read_text(encoding="utf-8"), output_dir)
        built.append(out)
        print(f"  -> {out}")

    if not built:
        print("nothing built", file=sys.stderr)
        return 1

    index = output_dir / "index.html"
    index.write_text(
        "<!doctype html><html><head><meta charset='utf-8'><title>OmniDocBench inspection</title></head><body>"
        "<h1>OmniDocBench inspection</h1><ul>"
        + "".join(f'<li><a href="{p.name}">{html.escape(p.stem)}</a></li>' for p in built)
        + "</ul></body></html>",
        encoding="utf-8",
    )
    print(f"index -> {index}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
