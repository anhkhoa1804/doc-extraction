"""Compose paired OCR-language route outputs with fail-closed empty fallback.

This is an offline research tool, not a production router. It uses only
runtime artifacts (the selected-language provenance, candidate validity,
and candidate text/warnings); no ground truth or benchmark page identity is
used in the fallback decision.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from doc_extraction.ingest.language_routing import select_routed_markdown


def _prediction_name(page_id: str) -> str:
    image_name = page_id.split("#", 1)[0]
    return f"{Path(image_name).stem}.md"


def compose(
    *,
    baseline_dir: Path,
    routed_dir: Path,
    route_provenance: Path,
    output_dir: Path,
) -> dict:
    baseline_files = {path.name for path in baseline_dir.glob("*.md")}
    routed_files = {path.name for path in routed_dir.glob("*.md")}
    if not baseline_files or baseline_files != routed_files:
        raise ValueError("baseline and routed Markdown page populations must match exactly")

    provenance = json.loads(route_provenance.read_text(encoding="utf-8"))
    entries = provenance.get("predictions")
    if not isinstance(entries, list):
        raise TypeError("route provenance must contain a predictions list")
    selected = {_prediction_name(item["page_id"]): item for item in entries}
    if set(selected) != routed_files:
        raise ValueError("route provenance page identity does not match prediction files")

    output_dir.mkdir(parents=True, exist_ok=False)
    fallbacks: list[dict[str, str | int | bool | None]] = []
    routed_count = 0
    for name in sorted(routed_files):
        candidate_path = routed_dir / name
        candidate = candidate_path.read_text(encoding="utf-8")
        baseline = (baseline_dir / name).read_text(encoding="utf-8")
        identity = selected[name]
        expected_sha = identity.get("sha256")
        actual_sha = hashlib.sha256(candidate_path.read_bytes()).hexdigest()
        if expected_sha != actual_sha:
            raise ValueError(f"routed prediction hash does not match provenance: {name}")

        if identity.get("selected_languages") == "ch_sim,en":
            routed_count += 1
            result = select_routed_markdown(
                candidate_markdown=candidate,
                baseline_markdown=baseline,
            )
            selected_text = result.selected_markdown
            if result.used_baseline_fallback:
                fallbacks.append(
                    {
                        "page_id": identity["page_id"],
                        "reason": result.reason,
                        "baseline_nonempty": bool(baseline.strip()),
                        "candidate_bytes": len(candidate_path.read_bytes()),
                        "baseline_bytes": len((baseline_dir / name).read_bytes()),
                    }
                )
        else:
            selected_text = candidate
        (output_dir / name).write_text(selected_text, encoding="utf-8")

    summary = {
        "kind": "offline saved-output replay; no OCR inference",
        "prediction_count": len(routed_files),
        "han_route_count": routed_count,
        "fallback_count": len(fallbacks),
        "fallbacks": fallbacks,
        "baseline_dir": str(baseline_dir),
        "routed_dir": str(routed_dir),
        "route_provenance": str(route_provenance),
        "output_dir": str(output_dir),
    }
    (output_dir.parent / "fallback_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-dir", type=Path, required=True)
    parser.add_argument("--routed-dir", type=Path, required=True)
    parser.add_argument("--route-provenance", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(compose(**vars(args)), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
