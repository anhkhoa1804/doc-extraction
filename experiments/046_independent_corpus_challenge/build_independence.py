"""Audit 046's frozen population against 035, 044, and 045."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
from build_manifest import DATASET, IMAGE_ROOT, source_group  # noqa: E402


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    manifest = json.loads((HERE / "population_manifest.json").read_text())
    pages = json.loads(DATASET.read_text())
    historic_images = {Path(page["page_info"]["image_path"]).name for page in pages
                       if any(det.get("category_type") == "table" for det in page["layout_dets"])}
    historic_groups = {source_group(image) for image in historic_images}
    historic_hashes = {_digest(IMAGE_ROOT / image) for image in historic_images if (IMAGE_ROOT / image).is_file()}
    prior_records: set[str] = set()
    prior_images: set[str] = set()
    prior_hashes: set[str] = set()
    for name in ("044_truth_aware_development_replay/population_manifest_v2.json",
                 "045_acquisition_time_observation_capture/population_manifest.json"):
        for record in json.loads((ROOT / "experiments" / name).read_text())["cases"]:
            prior_images.add(record["source_image"])
            prior_records.add(f"{record['source_image']}:{record['source_locator']}")
            if record.get("input_sha256"):
                prior_hashes.add(record["input_sha256"])

    rows = []
    for record in manifest["cases"]:
        image = record["source_image"]
        row = {
            "case_id": record["case_id"], "source_identity": record["source_group_id"],
            "source_hash": record["input_sha256"], "image_hash": record["input_sha256"],
            "benchmark_id": record["benchmark_record_id"], "source_group_id": record["source_group_id"],
            "relation_to_035": "disjoint" if record["source_group_id"] not in historic_groups and image not in historic_images and record["input_sha256"] not in historic_hashes else "overlap",
            "relation_to_044": "disjoint" if image not in prior_images and record["benchmark_record_id"] not in prior_records and record["input_sha256"] not in prior_hashes else "overlap",
            "relation_to_045": "disjoint" if image not in prior_images and record["benchmark_record_id"] not in prior_records and record["input_sha256"] not in prior_hashes else "overlap",
        }
        rows.append(row)
    audit = {"population_sha256": manifest["population_sha256"], "table_population_source": str(DATASET.relative_to(ROOT)),
             "historical_035_table_images": len(historic_images), "historical_035_table_groups": len(historic_groups - {None}),
             "cases": rows,
             "all_disjoint": all(all(row[key] == "disjoint" for key in ("relation_to_035", "relation_to_044", "relation_to_045")) for row in rows)}
    (HERE / "independence_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n")
    lines = ["# 046 — independence audit", "", f"Population hash: `{manifest['population_sha256']}`.", "",
             "The source identity is a conservative filename-derived document stem. Records with no defensible stem (UUID-only `page-...`) were excluded. The 035 comparison is conservative: every OmniDocBench page with a table annotation is treated as historical 035-family material.", "",
             f"Result: **{'PASS' if audit['all_disjoint'] else 'FAIL'}** — {len(rows)} case records are source-group, image-hash, and benchmark-record disjoint from 035 and the 044/045 descendants.", "",
             "| case | source group | 035 | 044 | 045 |", "| --- | --- | --- | --- | --- |"]
    lines.extend(f"| {r['case_id']} | `{r['source_group_id']}` | {r['relation_to_035']} | {r['relation_to_044']} | {r['relation_to_045']} |" for r in rows)
    (HERE / "INDEPENDENCE.md").write_text("\n".join(lines) + "\n")
    print(json.dumps({"all_disjoint": audit["all_disjoint"], "cases": len(rows)}, indent=2))
    return 0 if audit["all_disjoint"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
