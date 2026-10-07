"""Prepare offline-pinned formula configs or replay a table export ablation.

No inference is performed here. Extraction uses the existing prepare.py;
evaluation uses the existing strict, pinned evaluate.py. Official runs are
read-only and experiment output directories must be new.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from doc_extraction.evaluation import omnidocbench as odb
from doc_extraction.schemas.document import Document
from doc_extraction.schemas.page import Page
from doc_extraction.utils.hashing import sha256_file
from doc_extraction.utils.safe_io import secure_mkdir, write_text

FORMULA_PAGES = [
    "PPT_MMAT5390Lecture1_page_023.png#23",
    "book_zh_CNASGL0072018_extracted_page_48.png#48",
    "docstructbench_llm-raw-scihub-o.O-j.physletb.2004.06.101.pdf_3.jpg#3",
    "exam_paper_en-file-putnam-archive_2013_Problems_2013_page_002.png#2",
    "jiaocaineedrop_jiaocai_needrop_en_1253.jpg#1996",
]


def write_record(path: Path, payload: dict) -> None:
    write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def formula_configs(base: dict, artifacts: str) -> tuple[dict, dict]:
    baseline = {**base, "docling_artifacts_path": artifacts, "docling_formula_enrichment": False}
    candidate = {**baseline, "docling_formula_enrichment": True}
    return baseline, candidate


def legacy_page_markdown(page: Page) -> str:
    """The preserved pre-fix export, solely for controlled offline replay."""
    blocks = []
    for element in page.elements_in_reading_order():
        if element.type.value == "table":
            table = page.table_by_id(element.table_id)
            if table is None:
                raise ValueError("table reference is unresolved")
            grid = table.to_grid()
            lines = ["| " + " | ".join(row) + " |" for row in grid]
            lines.insert(1, "| " + " | ".join(["---"] * table.n_cols) + " |")
            block = "\n".join(lines)
        else:
            block = odb._element_to_markdown_block(element, page)
        if block:
            blocks.append(block)
    return "\n\n".join(blocks) + "\n" if blocks else "\n"


def verified_replacement(page: Page, baseline: str) -> str:
    if legacy_page_markdown(page) != baseline:
        raise ValueError("retained canonical content does not reproduce the baseline prediction")
    return odb.page_to_prediction_markdown(page)


def prepare_formula(output: Path) -> None:
    manifest = ROOT / "benchmarks/manifests/omnidocbench-representative-v2.json"
    content = json.loads(manifest.read_text())
    by_id = {sample["page_id"]: sample for sample in content["subset"]["samples"]}
    if len(by_id) != len(content["subset"]["samples"]) or not set(FORMULA_PAGES) <= by_id.keys():
        raise ValueError("formula cohort is not uniquely present in the frozen manifest")
    model = ROOT / ".cache/docling/docling-project--CodeFormulaV2"
    if not (model / "model.safetensors").is_file():
        raise FileNotFoundError("local CodeFormulaV2 weights are unavailable")
    model_files = {
        path.name: {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
        for path in sorted(model.iterdir()) if path.is_file()
    }
    base_path = ROOT / "configs/gpu.yaml"
    baseline, candidate = formula_configs(yaml.safe_load(base_path.read_text()), ".cache/docling")
    for name, config in (("baseline", baseline), ("candidate", candidate)):
        write_text(output / f"{name}.yaml", yaml.safe_dump(config, sort_keys=True))
    prepare = importlib.import_module("experiments.005_omnidocbench.prepare")
    write_record(output / "experiment.json", {
        "experiment_id": output.name, "hypothesis": "explicit local artifacts unblock supported formula enrichment",
        "changed_variables": ["docling_formula_enrichment"],
        "baseline": "same local artifacts, enrichment disabled",
        "candidate": "same local artifacts, enrichment enabled",
        "promotion_gate": "valid output, formula improvement, inspect text/order regressions and runtime",
        "page_ids": FORMULA_PAGES, "manifest_sha256": sha256_file(manifest),
        "dataset_identity": content["subset_identity"],
        "base_config_sha256": sha256_file(base_path),
        "configs": {name: sha256_file(output / f"{name}.yaml") for name in ("baseline", "candidate")},
        "model": "docling-project/CodeFormulaV2", "model_files": model_files,
        "model_revision": "local content-addressed artifacts; no mutable Hub lookup",
        "source": prepare.build_source_attestation(), "environment": prepare.build_runtime_attestation(),
        "evaluator_revision": odb.PINNED_UPSTREAM_COMMIT,
        "inference_performed": False, "official_baseline_modified": False,
    })
    print(f"Formula plan/configs: {output}")
    print("Run prepare.py separately with the recorded five page IDs, offline environment, and --keep-runs.")


def replay_tables(baseline: Path, canonical: Path, output: Path) -> None:
    metadata = json.loads((baseline / "run_metadata.json").read_text())
    gt, samples = odb.load_dataset(
        ROOT / "experiments/034a_omnidocbench_snapshot/dataset/full", baseline / "ground_truth_subset.json",
    )
    predictions = baseline / metadata["prediction_directory"]
    odb.validate_prediction_alignment(samples, predictions)
    stored = {}
    for path in canonical.glob("*/final/document.json"):
        payload = json.loads(path.read_text())
        # Only observed serialization hazards need canonical replacement.
        hazards = [cell for page in payload["pages"] for table in page["tables"] for cell in table["cells"]
                   if cell["row_span"] > 1 or cell["col_span"] > 1 or any(c in cell["text"] for c in "|\n\r")]
        if hazards:
            name = Path(payload["metadata"]["input_filename"]).with_suffix(".md").name
            if name in stored:
                raise ValueError("duplicate canonical prediction identity")
            stored[name] = (path, payload)
    unknown = set(stored) - {sample.prediction_filename for sample in samples}
    if unknown:
        raise ValueError("retained canonical hazards include pages outside the selected population")
    target = output / "predictions"
    secure_mkdir(target)
    changed = []
    for sample in samples:
        old = (predictions / sample.prediction_filename).read_text()
        new = old
        if sample.prediction_filename in stored:
            path, payload = stored[sample.prediction_filename]
            document = Document.model_validate(payload)
            if len(document.pages) != 1 or document.metadata.file_hash_sha256 != sha256_file(sample.image_path):
                raise ValueError("retained canonical source identity mismatch")
            new = verified_replacement(document.pages[0], old)
            if new != old:
                changed.append({"page_id": f"{sample.image_name}#{sample.page_no}",
                                "canonical_sha256": sha256_file(path), "canonical_source": str(path),
                                "original_prediction_sha256": sha256_file(predictions / sample.prediction_filename)})
        write_text(target / sample.prediction_filename, new)
    odb.validate_prediction_alignment(samples, target)
    write_text(output / "ground_truth_subset.json", gt.read_text())
    write_text(output / "sample_manifest.json", (baseline / "sample_manifest.json").read_text())
    metadata = {**metadata, "prediction_directory": "predictions", "evaluation_ground_truth": "ground_truth_subset.json"}
    prepare = importlib.import_module("experiments.005_omnidocbench.prepare")
    baseline_prediction_hash = hashlib.sha256()
    candidate_prediction_hash = hashlib.sha256()
    for sample in samples:
        filename = sample.prediction_filename
        baseline_prediction_hash.update(filename.encode("utf-8") + b"\0")
        baseline_prediction_hash.update(sha256_file(predictions / filename).encode("ascii") + b"\0")
        candidate_prediction_hash.update(filename.encode("utf-8") + b"\0")
        candidate_prediction_hash.update(sha256_file(target / filename).encode("ascii") + b"\0")
    metadata["experiment"] = {
        "id": output.name, "type": "serialization-only partial-canonical replay",
        "baseline_run": str(baseline), "replacement_pages": changed,
        "unchanged_control_pages": len(samples) - len(changed),
        "inference_performed": False,
        "source_attestation": prepare.build_source_attestation(),
        "evaluator_revision": odb.PINNED_UPSTREAM_COMMIT,
        "manifest_sha256": sha256_file(baseline / "sample_manifest.json"),
        "ground_truth_subset_sha256": sha256_file(baseline / "ground_truth_subset.json"),
        "baseline_prediction_set_sha256": baseline_prediction_hash.hexdigest(),
        "candidate_prediction_set_sha256": candidate_prediction_hash.hexdigest(),
        "selected_page_count": len(samples),
        "strict_prediction_alignment": True,
        "limitation": "Only retained hazardous tables were reserialized; this is not a fresh full-pipeline baseline.",
    }
    write_record(output / "run_metadata.json", metadata)
    print(f"Exact population {len(samples)}; verified replacements {len(changed)}; outputs: {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["formula-plan", "table-replay"])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--canonical", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output exists; refusing to overwrite experiment artifacts")
    if args.mode == "table-replay" and (args.baseline is None or args.canonical is None):
        parser.error("table-replay requires --baseline and --canonical")
    secure_mkdir(args.output)
    if args.mode == "formula-plan":
        prepare_formula(args.output)
    else:
        replay_tables(args.baseline, args.canonical, args.output)


if __name__ == "__main__":
    main()
