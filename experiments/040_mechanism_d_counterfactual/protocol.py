"""Frozen, outcome-independent helpers for Experiment 040.

This module is intentionally small and mostly pure.  The treatment runner
imports it for identity and integrity checks, while the analysis runner uses
the same definitions after specialist output exists.  No function here takes
GT information as treatment input.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

EXPERIMENT_ID = "040_mechanism_d_counterfactual"
BASELINE_CHECKPOINT = "cdb8fd80f5c2d9dc1711b50828ec9301c5bb1adf"
DEVELOPMENT_SPLIT = "development"
HELDOUT_SPLITS = frozenset({"heldout", "held_out", "held_out_test", "test"})
INVOCATION_MODES = frozenset({"PAGE_WIDE", "LABELLED_CROP", "NOT_INVOKED"})
TARGET_KIND = "d2_region"
CONTROL_KIND = "non_table_control_region"
PRIMARY_ROLES = ("document_index", "picture", "text", "list_item", "code")

# These are the frozen 036 boundaries.  They are study definitions, not
# production thresholds and must not be changed after treatment starts.
GT_IOU_MIN = 0.3
OWNER_IOU_MIN = 0.1
MATERIAL_CONFLICT_IOU = 0.1
CELL_ESCAPE_MARGIN_PX = 1.0
CELL_ESCAPE_FRACTION_MAX = 0.2


class HeldoutAccessError(RuntimeError):
    """Raised before any specialist call for a non-development unit."""


class ProtocolViolation(RuntimeError):
    """Raised when an immutable treatment contract is not satisfied."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return sha256_bytes(encoded)


def atomic_write_json(path: Path, payload: Any) -> None:
    """Write a complete JSON file by replace-on-success."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def require_development(record: dict[str, Any]) -> None:
    """Fail closed before treatment if a record is not development data."""
    split = record.get("split")
    if split != DEVELOPMENT_SPLIT:
        raise HeldoutAccessError(
            f"refusing Experiment 040 treatment for split={split!r}; only development is permitted"
        )


def bbox_dict(value: Any) -> dict[str, float]:
    if isinstance(value, dict):
        return {key: float(value[key]) for key in ("x0", "y0", "x1", "y1")}
    return {key: float(getattr(value, key)) for key in ("x0", "y0", "x1", "y1")}


def bbox_equal(first: Any, second: Any) -> bool:
    return bbox_dict(first) == bbox_dict(second)


def iou(first: Any, second: Any) -> float:
    a, b = bbox_dict(first), bbox_dict(second)
    ix0, iy0 = max(a["x0"], b["x0"]), max(a["y0"], b["y0"])
    ix1, iy1 = min(a["x1"], b["x1"]), min(a["y1"], b["y1"])
    intersection = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
    area_a = max(0.0, a["x1"] - a["x0"]) * max(0.0, a["y1"] - a["y0"])
    area_b = max(0.0, b["x1"] - b["x0"]) * max(0.0, b["y1"] - b["y0"])
    union = area_a + area_b - intersection
    return intersection / union if union else 0.0


def structure_validity(table: dict[str, Any] | None) -> dict[str, Any]:
    """The frozen 036 structural-validity rule."""
    if table is None:
        return {"valid": False, "reason": "no_structure", "n_rows": 0, "n_cols": 0, "n_cells": 0}
    rows = int(table.get("n_rows", 0))
    cols = int(table.get("n_cols", 0))
    cells = list(table.get("cells") or [])
    table_bbox = table.get("bbox")
    if rows < 1 or cols < 1 or not cells or table_bbox is None:
        return {
            "valid": False,
            "reason": "empty_or_missing_geometry",
            "n_rows": rows,
            "n_cols": cols,
            "n_cells": len(cells),
        }
    box = bbox_dict(table_bbox)
    escaping = sum(
        1
        for cell in cells
        if cell.get("bbox") is not None
        and (
            float(cell["bbox"]["x0"]) < box["x0"] - CELL_ESCAPE_MARGIN_PX
            or float(cell["bbox"]["x1"]) > box["x1"] + CELL_ESCAPE_MARGIN_PX
            or float(cell["bbox"]["y0"]) < box["y0"] - CELL_ESCAPE_MARGIN_PX
            or float(cell["bbox"]["y1"]) > box["y1"] + CELL_ESCAPE_MARGIN_PX
        )
    )
    fraction = escaping / len(cells)
    return {
        "valid": fraction < CELL_ESCAPE_FRACTION_MAX,
        "reason": None if fraction < CELL_ESCAPE_FRACTION_MAX else "cells_escape_table_bbox",
        "n_rows": rows,
        "n_cols": cols,
        "n_cells": len(cells),
        "escaping_cells": escaping,
        "escaping_cell_fraction": round(fraction, 6),
    }


def crop_png_bytes(image_path: Path, bbox: dict[str, float]) -> tuple[bytes, int, int]:
    """Encode exactly the PIL crop used by the treatment backend."""
    from io import BytesIO

    from PIL import Image

    with Image.open(image_path) as source:
        crop = source.convert("RGB").crop(tuple(bbox_dict(bbox).values()))
        stream = BytesIO()
        crop.save(stream, format="PNG")
        return stream.getvalue(), crop.width, crop.height


def pre_treatment_features(
    *,
    region: dict[str, Any],
    page_width: float,
    page_height: float,
    region_index: int,
    page_region_count: int,
    ocr_tokens: list[dict[str, Any]],
) -> dict[str, Any]:
    """Create only frozen baseline features; no GT or treatment output."""
    box = bbox_dict(region["bbox"])
    width = max(0.0, box["x1"] - box["x0"])
    height = max(0.0, box["y1"] - box["y0"])
    child_tokens = []
    for token in ocr_tokens:
        token_box = token["bbox"]
        cx = (float(token_box["x0"]) + float(token_box["x1"])) / 2
        cy = (float(token_box["y0"]) + float(token_box["y1"])) / 2
        if box["x0"] <= cx <= box["x1"] and box["y0"] <= cy <= box["y1"]:
            child_tokens.append(token)
    return {
        "raw_role": str(region.get("label", "")),
        "normalized_role": str(region.get("label", "")).strip().lower(),
        "layout_confidence": region.get("confidence"),
        "layout_confidence_source": "baseline_layout" if region.get("confidence") is not None else None,
        "region_source_id": region.get("source_id"),
        "region_index": region_index,
        "page_region_count": page_region_count,
        "region_bbox": box,
        "region_area_fraction": (width * height) / (page_width * page_height)
        if page_width > 0 and page_height > 0
        else None,
        "region_width_fraction": width / page_width if page_width else None,
        "region_height_fraction": height / page_height if page_height else None,
        "aspect_ratio": width / height if height else None,
        "ocr_child_count": len(child_tokens),
        "ocr_child_chars": sum(len(str(token.get("text") or "")) for token in child_tokens),
        "route": "image",
        "backend": "table_transformer",
        "device": "cpu",
    }


def policy_fires(features: dict[str, Any]) -> dict[str, bool]:
    """Frozen policy-family indicators, computed before treatment outcomes."""
    role = features["normalized_role"]
    return {
        "POLICY_0_ABSTAIN_ALL": False,
        "POLICY_1_ROLE_ONLY_DOCUMENT_INDEX": role == "document_index",
        "POLICY_2_DOCUMENT_INDEX_AND_ZERO_OCR": role == "document_index"
        and features["ocr_child_count"] == 0,
        "POLICY_3_BROAD_NON_TABLE_ROLE_NEGATIVE_CONTROL": role in PRIMARY_ROLES,
    }
