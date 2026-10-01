"""Freeze the independent, text-truth population for Experiment 046.

Selection is deliberately metadata-only: no pipeline output is read here.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
DATASET = ROOT / "experiments/034a_omnidocbench_snapshot/dataset/full/OmniDocBench.json"
IMAGE_ROOT = DATASET.parent / "images"
OUT = HERE / "population_manifest.json"
SOURCE_TYPES = (
    "academic_literature", "book", "colorful_textbook", "exam_paper",
    "magazine", "newspaper", "PPT2PDF",
)


def source_group(image_name: str) -> str | None:
    """Return a document stem only when the filename makes it defensible."""
    stem = Path(image_name).stem
    if re.fullmatch(r"page-[0-9a-f-]{36}", stem):
        return None
    grouped = re.sub(r"(?:\.pdf|_page)?[_-]\d+$", "", stem, flags=re.IGNORECASE)
    return grouped if grouped != stem or ".pdf" in image_name else None


def stable_rank(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def box(poly: list[float]) -> dict[str, float]:
    xs, ys = poly[::2], poly[1::2]
    return {"x0": min(xs), "y0": min(ys), "x1": max(xs), "y1": max(ys)}


def main() -> int:
    if OUT.exists():
        raise SystemExit(f"refusing to overwrite frozen manifest: {OUT}")
    pages = json.loads(DATASET.read_text())
    historical_groups = {
        source_group(page["page_info"]["image_path"])
        for page in pages
        if any(det.get("category_type") == "table" for det in page["layout_dets"])
    }
    historical_groups.discard(None)
    eligible: list[dict] = []
    for page in pages:
        info = page["page_info"]
        image_name = Path(info["image_path"]).name
        group = source_group(image_name)
        attrs = info.get("page_attribute", {})
        if group is None or group in historical_groups or attrs.get("data_source") not in SOURCE_TYPES:
            continue
        if any(det.get("category_type") == "table" for det in page["layout_dets"]):
            continue
        image = IMAGE_ROOT / image_name
        if not image.is_file():
            continue
        for det in page["layout_dets"]:
            text = det.get("text") or ""
            if det.get("category_type") not in {"text_block", "title"}:
                continue
            if not (8 <= len(text) <= 180) or "\n" in text or "\\" in text or "$" in text or not det.get("poly"):
                continue
            eligible.append({
                "source_image": image_name, "source_group_id": group,
                "benchmark_record_id": f"{image_name}:{det['anno_id']}",
                "truth": {"annotation_id": str(det["anno_id"]), "category_type": det["category_type"],
                          "text": text, "locator": box(det["poly"])},
                "page_attributes": attrs, "input_path": str(image.relative_to(ROOT)),
            })
    selected: list[dict] = []
    used_groups: set[str] = set()
    control_specs = (
        ("ctl-00", lambda r: r["truth"]["category_type"] == "text_block" and r["page_attributes"].get("layout") == "single_column"),
        ("ctl-01", lambda r: r["truth"]["category_type"] == "title"),
        ("ctl-02", lambda r: r["truth"]["category_type"] == "text_block" and r["page_attributes"].get("layout") in {"double_column", "1andmore_column", "three_column"}),
    )
    for case_id, predicate in control_specs:
        options = [r for r in eligible if predicate(r) and r["source_group_id"] not in used_groups]
        if not options:
            raise SystemExit(f"cannot select required control {case_id}")
        record = min(options, key=lambda r: stable_rank(r["benchmark_record_id"]))
        selected.append({**record, "case_id": case_id, "case_role": "control", "eligibility": "included"})
        used_groups.add(record["source_group_id"])
    for source_type in SOURCE_TYPES:
        options = [r for r in eligible if r["page_attributes"].get("data_source") == source_type and r["source_group_id"] not in used_groups]
        options.sort(key=lambda r: stable_rank(r["benchmark_record_id"]))
        distinct_options: list[dict] = []
        local_groups: set[str] = set()
        for record in options:
            if record["source_group_id"] in local_groups:
                continue
            distinct_options.append(record)
            local_groups.add(record["source_group_id"])
        if len(distinct_options) < 3:
            raise SystemExit(f"insufficient candidates for {source_type}")
        for record in distinct_options[:3]:
            case_id = f"ind-{len([x for x in selected if x['case_role'] == 'challenge']):02d}"
            selected.append({**record, "case_id": case_id, "case_role": "challenge", "eligibility": "included"})
            used_groups.add(record["source_group_id"])
    payload = {
        "experiment": "046_independent_corpus_challenge", "protocol": "PROTOCOL.md",
        "selection_version": "v1-metadata-only",
        "selection_rule": "three fixed controls plus three SHA-256-ranked text annotations per source type; no pipeline outcome read",
        "independence_rule": "source group, image SHA-256, and benchmark record must be absent from 035 table population and 044/045 descendants",
        "cases": selected,
    }
    # Hash only frozen records. Hashing every eligible image makes metadata
    # selection expensive without adding evidence for the final population.
    for record in payload["cases"]:
        record["input_sha256"] = hashlib.sha256((ROOT / record["input_path"]).read_bytes()).hexdigest()
    payload["population_sha256"] = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(f"frozen {len(selected)} cases / {len(used_groups)} groups: {payload['population_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
