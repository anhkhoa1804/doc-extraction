"""Freeze the 044 development population before evaluating candidate outcomes."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "population_manifest.json"
SOURCE = ROOT / "experiments/036_mechanism_d_counterfactual/population_manifest.json"
GT = ROOT / "experiments/034a_omnidocbench_snapshot/dataset/full/OmniDocBench.json"


def main() -> int:
    if OUT.exists():
        raise SystemExit(f"refusing to overwrite frozen manifest: {OUT}")
    source = json.loads(SOURCE.read_text())
    truth = json.loads(GT.read_text())
    truth_index = {}
    for page in truth:
        image = Path(page["page_info"]["image_path"]).name
        for det in page["layout_dets"]:
            if det.get("category_type") == "table":
                truth_index[(image, str(det["anno_id"]))] = det
    cases = []
    for item in source["treatment_cases"][:8]:
        key = (item["image"], str(item["gt_table_anno_id"]))
        det = truth_index.get(key)
        run = ROOT / item["source_run"]
        artifacts = {name: (run / name).is_file() for name in (
            "final/document.json", "layout/page-001.json", "ocr/page-001.json", "tables/page-001.json")}
        eligible = bool(det and det.get("html") and all(artifacts.values()))
        cases.append({
            "case_id": item["case_id"], "source_image": item["image"], "source_locator": item["gt_table_anno_id"],
            "page_locator": item["gt_bbox_px"], "historical_failure": "strict_D2",
            "raw_role": item["targets"][0]["label"], "source_run": item["source_run"],
            "artifacts": artifacts, "truth_source": "OmniDocBench table HTML + GT rectangle",
            "truth_available": bool(det and det.get("html")), "eligibility": "included" if eligible else "excluded",
            "exclusion_reason": None if eligible else "missing persisted artifact or GT table HTML",
        })
    payload = {"experiment": "044_truth_aware_development_replay", "protocol": "PROTOCOL.md", "source_manifest": str(SOURCE.relative_to(ROOT)),
               "selection": "first eight frozen strict-D2 entries, in source-manifest order", "development_only": True, "cases": cases}
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    payload["population_sha256"] = hashlib.sha256(canonical.encode()).hexdigest()
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(f"frozen {sum(c['eligibility'] == 'included' for c in cases)}/{len(cases)} cases: {payload['population_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
