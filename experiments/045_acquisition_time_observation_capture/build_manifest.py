"""Freeze 045's unchanged 044-v2 development population and input hashes."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SOURCE = ROOT / "experiments/044_truth_aware_development_replay/population_manifest_v2.json"
OUT = HERE / "population_manifest.json"


def main() -> int:
    if OUT.exists():
        raise SystemExit(f"refusing to overwrite frozen manifest: {OUT}")
    source = json.loads(SOURCE.read_text())
    cases = []
    for item in source["cases"]:
        image = ROOT / "experiments/035_mechanism_d_gating/dataset/gt_tables/images" / item["source_image"]
        cases.append({**item, "input_path": str(image.relative_to(ROOT)),
                      "input_sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
                      "eligibility": "included" if image.is_file() else "excluded",
                      "exclusion_reason": None if image.is_file() else "source image unavailable"})
    payload = {"experiment": "045_acquisition_time_observation_capture", "protocol": "PROTOCOL.md",
               "development_only": True, "source_population_sha256": source["population_sha256"], "cases": cases}
    payload["population_sha256"] = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                                               separators=(",", ":")).encode()).hexdigest()
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(f"frozen {sum(x['eligibility'] == 'included' for x in cases)}/{len(cases)}: {payload['population_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
