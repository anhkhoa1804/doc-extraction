"""Freeze protocol-v2 population, adding two known table-gated controls."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "population_manifest_v2.json"
SOURCE = ROOT / "experiments/036_mechanism_d_counterfactual/population_manifest.json"
MATCHES = ROOT / "experiments/035_mechanism_d_gating/table_region_matching.json"


def artifact_status(run: str) -> dict[str, bool]:
    base = ROOT / run
    return {name: (base / name).is_file() for name in (
        "final/document.json", "layout/page-001.json", "ocr/page-001.json", "tables/page-001.json")}


def entry(*, case_id: str, image: str, anno: str | int, bbox: dict, role: str, run: str,
          category: str) -> dict:
    artifacts = artifact_status(run)
    eligible = all(artifacts.values())
    return {"case_id": case_id, "source_image": image, "source_locator": anno, "page_locator": bbox,
            "historical_failure": category, "raw_role": role, "source_run": run, "artifacts": artifacts,
            "truth_source": "OmniDocBench table HTML + GT rectangle", "truth_available": True,
            "eligibility": "included" if eligible else "excluded",
            "exclusion_reason": None if eligible else "missing persisted artifact"}


def main() -> int:
    if OUT.exists():
        raise SystemExit(f"refusing to overwrite frozen manifest: {OUT}")
    d2 = json.loads(SOURCE.read_text())["treatment_cases"][:8]
    cases = [entry(case_id=x["case_id"], image=x["image"], anno=x["gt_table_anno_id"], bbox=x["gt_bbox_px"],
                   role=x["targets"][0]["label"], run=x["source_run"], category="strict_D2") for x in d2]
    records = json.loads(MATCHES.read_text())["records"]
    image = "page-0b20ed47-7c6c-4578-bbdf-057a89a083ec.png"
    run = "experiments/035_mechanism_d_gating/results/gt_tables_chunk0/_doc_extraction_runs/page-0b20ed47-7c6c-4578-bbdf-057a89a083ec-c9830bd6"
    for number, anno in enumerate(("box_id_2", "box_id_4")):
        record = next(r for r in records if r["image"] == image and str(r["gt_table_anno_id"]) == anno)
        cases.append(entry(case_id=f"ctl-{number:02d}", image=image, anno=anno, bbox=record["gt_bbox_px"],
                           role="table", run=run, category="exact_match_control"))
    payload = {"experiment": "044_truth_aware_development_replay", "protocol": "PROTOCOL-v2.md",
               "source_manifest": str(SOURCE.relative_to(ROOT)), "development_only": True,
               "selection": "first eight frozen D2 entries plus two fixed table-gated controls", "cases": cases}
    payload["population_sha256"] = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                                               separators=(",", ":")).encode()).hexdigest()
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(f"frozen {sum(x['eligibility'] == 'included' for x in cases)}/{len(cases)}: {payload['population_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
