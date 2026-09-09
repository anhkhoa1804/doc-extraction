"""035 shared geometry/matching primitives, used by Phase 3 (region
matching), Phase 4 (failure funnel), Phase 9 (geometry stratification) and
Phase 13 (false positives). One implementation, imported everywhere, so
every phase's IoU/containment numbers are computed identically -- per
Phase 23's reproducibility requirement (a deterministic matcher rerun must
be byte-identical).

Coordinate space: identity, pixel space of the original page image --
proven in Phase 2 (coordinate_alignment.json). No transform applied here.
"""
from __future__ import annotations

import json
from pathlib import Path


def poly_to_bbox(poly: list[float]) -> dict:
    xs = poly[0::2]
    ys = poly[1::2]
    return {"x0": min(xs), "y0": min(ys), "x1": max(xs), "y1": max(ys)}


def bbox_area(b: dict) -> float:
    return max(0.0, b["x1"] - b["x0"]) * max(0.0, b["y1"] - b["y0"])


def bbox_intersection_area(a: dict, b: dict) -> float:
    x0 = max(a["x0"], b["x0"]); y0 = max(a["y0"], b["y0"])
    x1 = min(a["x1"], b["x1"]); y1 = min(a["y1"], b["y1"])
    if x1 <= x0 or y1 <= y0:
        return 0.0
    return (x1 - x0) * (y1 - y0)


def bbox_iou(a: dict, b: dict) -> float:
    inter = bbox_intersection_area(a, b)
    union = bbox_area(a) + bbox_area(b) - inter
    return inter / union if union > 0 else 0.0


def bbox_center(b: dict) -> tuple[float, float]:
    return ((b["x0"] + b["x1"]) / 2, (b["y0"] + b["y1"]) / 2)


def bbox_center_distance(a: dict, b: dict) -> float:
    ax, ay = bbox_center(a); bx, by = bbox_center(b)
    return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5


def centroid_in_bbox(point_bbox: dict, container: dict) -> bool:
    cx, cy = bbox_center(point_bbox)
    return container["x0"] <= cx <= container["x1"] and container["y0"] <= cy <= container["y1"]


def containment_fraction(inner: dict, outer: dict) -> float:
    """Fraction of `inner`'s area covered by `outer` -- i.e. intersection / inner_area."""
    area_inner = bbox_area(inner)
    if area_inner <= 0:
        return 0.0
    return bbox_intersection_area(inner, outer) / area_inner


def union_coverage_of_gt(gt_bbox: dict, region_bboxes: list[dict], grid: int = 200) -> float:
    """Fraction of `gt_bbox`'s area covered by the UNION of `region_bboxes`
    (regions may overlap each other -- simple sum would double-count).
    Computed by rasterizing gt_bbox onto a grid x grid boolean grid; exact
    for axis-aligned rectangles up to grid resolution, which is more than
    enough given gt_bbox dimensions are in the hundreds-to-thousands of px
    and we only need coverage FRACTION, not sub-pixel precision.
    """
    x0, y0, x1, y1 = gt_bbox["x0"], gt_bbox["y0"], gt_bbox["x1"], gt_bbox["y1"]
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0 or not region_bboxes:
        return 0.0
    n_covered = 0
    for gx in range(grid):
        cx = x0 + (gx + 0.5) / grid * w
        for gy in range(grid):
            cy = y0 + (gy + 0.5) / grid * h
            for r in region_bboxes:
                if r["x0"] <= cx <= r["x1"] and r["y0"] <= cy <= r["y1"]:
                    n_covered += 1
                    break
    return n_covered / (grid * grid)


def classify_match(gt_bbox: dict, candidates: list[dict]) -> tuple[str, dict]:
    """candidates: list of dicts, each with at least {"region_index", "bbox",
    "iou", "intersection_over_gt", "intersection_over_region"}, already
    computed and sorted by intersection_over_gt descending.

    Thresholds are round numbers, stated explicitly, NOT tuned/optimized
    (per this milestone's rule 8) -- chosen for interpretability:
      EXACT_MATCH: best IoU >= 0.75
      GOOD_MATCH:  best IoU in [0.5, 0.75)
      MULTIPLE_MATCH: >=2 regions each with intersection_over_gt >= 0.2,
                       AND their bbox UNION covers >= 0.6 of the GT table,
                       AND no single region alone already reaches EXACT/GOOD
      AMBIGUOUS: top-2 intersection_over_gt within 15% of each other,
                 top < 0.5, not already MULTIPLE_MATCH
      PARTIAL_MATCH: best intersection_over_gt >= 0.3, none of the above
      NO_REGION: best intersection_over_gt < 0.1 (essentially no candidate)
      (a residual band [0.1, 0.3) that fits none of the above still counts
      as PARTIAL_MATCH -- the weakest form of "some part represented")

    Returns (verdict, extra) where extra carries verdict-specific detail.
    """
    if not candidates:
        return "NO_REGION", {}

    top = candidates[0]
    second = candidates[1] if len(candidates) > 1 else None

    covering = [c for c in candidates if c["intersection_over_gt"] >= 0.2]
    if len(covering) >= 2 and top["iou"] < 0.5:
        union_cov = union_coverage_of_gt(gt_bbox, [c["bbox"] for c in covering])
        if union_cov >= 0.6:
            return "MULTIPLE_MATCH", {
                "n_contributing_regions": len(covering),
                "union_coverage_of_gt": round(union_cov, 4),
                "contributing_region_indices": [c["region_index"] for c in covering],
            }

    if top["iou"] >= 0.75:
        return "EXACT_MATCH", {"matched_region_index": top["region_index"]}
    if top["iou"] >= 0.5:
        return "GOOD_MATCH", {"matched_region_index": top["region_index"]}

    if (second is not None and top["intersection_over_gt"] > 0
            and second["intersection_over_gt"] >= 0.15
            and top["intersection_over_gt"] < 0.5
            and abs(top["intersection_over_gt"] - second["intersection_over_gt"]) <= 0.15 * top["intersection_over_gt"]):
        return "AMBIGUOUS", {
            "top_region_index": top["region_index"], "second_region_index": second["region_index"],
            "top_intersection_over_gt": round(top["intersection_over_gt"], 4),
            "second_intersection_over_gt": round(second["intersection_over_gt"], 4),
        }

    if top["intersection_over_gt"] >= 0.1:
        return "PARTIAL_MATCH", {"matched_region_index": top["region_index"]}

    return "NO_REGION", {"best_intersection_over_gt": round(top["intersection_over_gt"], 4)}


def detect_region_reuse(records: list[dict]) -> int:
    """Flag when the SAME internal region (image, region_index) is the
    matched_region for MORE THAN ONE GT table. Each GT table on a page is
    matched independently against all regions, so nothing otherwise rules
    out two adjacent/overlapping GT tables both landing on one region (e.g.
    Table Transformer merging two visually-adjacent tables, or a large
    wrongly-labelled region containing two small GT tables). Left
    unflagged, this would let one extracted table silently count as
    "recovered" (D0) for two GT tables at once.

    Mutates `records` IN PLACE, adding "shared_region_with_other_gt_tables"
    (list of the other gt_table_anno_id values sharing that region; empty
    list if none) to every record. ADDITIVE ONLY -- never changes verdict,
    threshold, or classification. Returns the number of distinct
    (image, region_index) collisions found.

    Regression coverage: test_matching_lib_regressions.py
    test_region_reuse_across_two_gt_tables_is_flagged.
    """
    from collections import defaultdict as _defaultdict
    region_users: dict[tuple, list[int]] = _defaultdict(list)
    for idx, rec in enumerate(records):
        if rec.get("matched_region"):
            key = (rec["image"], rec["matched_region"]["region_index"])
            region_users[key].append(idx)
    n_collisions = 0
    for key, idxs in region_users.items():
        if len(idxs) > 1:
            n_collisions += 1
            anno_ids = [records[i]["gt_table_anno_id"] for i in idxs]
            for i in idxs:
                records[i]["shared_region_with_other_gt_tables"] = [
                    a for a in anno_ids if a != records[i]["gt_table_anno_id"]
                ]
    for rec in records:
        rec.setdefault("shared_region_with_other_gt_tables", [])
    return n_collisions


def load_page_run(run_dir: Path) -> dict | None:
    """Load one --keep-runs page directory's relevant artifacts. Returns
    None if the run is incomplete (missing any required file -- e.g. a
    page that failed mid-pipeline)."""
    meta_p = run_dir / "metadata.json"
    layout_p = run_dir / "layout" / "page-001.json"
    doc_p = run_dir / "final" / "document.json"
    if not (meta_p.exists() and layout_p.exists() and doc_p.exists()):
        return None
    meta = json.loads(meta_p.read_text())
    layout = json.loads(layout_p.read_text())
    doc = json.loads(doc_p.read_text())
    tables_p = run_dir / "tables" / "page-001.json"
    tables_raw = json.loads(tables_p.read_text()) if tables_p.exists() else None
    return {
        "run_dir": str(run_dir), "metadata": meta, "layout": layout,
        "document": doc, "tables_raw": tables_raw,
    }


def gt_table_run_roots(
    experiment_dir: Path,
    source_names: tuple[str, ...] = ("chunk0", "chunk1"),
) -> list[Path]:
    """Return the deterministic roots containing 035 GT-table page runs.

    A source chunk can be split across its original extraction tree and one
    or more process-recycled recovery batches.  Keeping this discovery rule
    here prevents later phases from silently analyzing only the original
    partial trees after recovery completes.

    Recovery roots are included only after their corresponding validation
    record passes.  This is intentionally stricter than globbing every
    ``batch*`` directory: an interrupted first attempt can be retained as
    immutable incident evidence while a retry writes to a different root.
    The PASS validation records that retry's ``runs_dir`` explicitly, so an
    analysis cannot accidentally include both attempts or treat an
    incomplete run as corpus evidence.  Legacy validation files created
    before ``runs_dir`` was recorded fall back to the canonical batch path.
    """
    roots: list[Path] = []
    for source_name in source_names:
        original = experiment_dir / "results" / f"gt_tables_{source_name}" / "_doc_extraction_runs"
        if original.is_dir():
            roots.append(original)

        manifest_name = (
            "recovery_batches_manifest.json"
            if source_name == "chunk0"
            else f"{source_name}_recovery_batches_manifest.json"
        )
        manifest_path = experiment_dir / manifest_name
        validation_prefix = "" if source_name == "chunk0" else f"{source_name}_"

        if manifest_path.is_file():
            manifest = json.loads(manifest_path.read_text())
            for batch in sorted(manifest.get("batches", []), key=lambda b: b["batch_index"]):
                batch_index = batch["batch_index"]
                validation_path = experiment_dir / f"{validation_prefix}batch{batch_index}_validation.json"
                if not validation_path.is_file():
                    continue
                validation = json.loads(validation_path.read_text())
                if not validation.get("PASS"):
                    continue
                relative_runs_dir = validation.get(
                    "runs_dir",
                    f"results/gt_tables_{source_name}_recovery/batch{batch_index}/_doc_extraction_runs",
                )
                recovery_root = experiment_dir / relative_runs_dir
                if recovery_root.is_dir():
                    roots.append(recovery_root)
        else:
            # Backward-compatible fallback for an old result tree without a
            # manifest. New 035 recovery work always has a manifest and uses
            # the validation-gated path above.
            recovery_parent = experiment_dir / "results" / f"gt_tables_{source_name}_recovery"
            for batch_dir in sorted(recovery_parent.glob("batch*")):
                recovery_root = batch_dir / "_doc_extraction_runs"
                if recovery_root.is_dir():
                    roots.append(recovery_root)
    return roots


def gt_table_run_dirs(
    experiment_dir: Path,
    source_names: tuple[str, ...] = ("chunk0", "chunk1"),
) -> list[Path]:
    """Return sorted page-run directories from original and recovery roots."""
    run_dirs: list[Path] = []
    for root in gt_table_run_roots(experiment_dir, source_names):
        run_dirs.extend(sorted(p for p in root.iterdir() if p.is_dir()))
    return run_dirs
