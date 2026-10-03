"""Run the isolated five-page PaddleOCR-VL max_new_tokens experiment.

Candidate outputs live only under ``.benchmarks/diagnostics``. The script
never changes configs/gpu.yaml or the frozen representative-v2 manifest.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

MANIFEST = ROOT / "benchmarks/manifests/omnidocbench-representative-v2.json"
DATASET = ROOT / "experiments/034a_omnidocbench_snapshot/dataset/full"
BASE_CONFIG = ROOT / "configs/gpu.yaml"
EVALUATOR_REPO = ROOT / ".external/OmniDocBench"
EVALUATOR_REVISION = "193627ae9e97d89188468ed1ee3b7a856ff76044"
PAGE_IDS = [
    "newspaper_TheWashingtonPost-2025-01-08@magazinesclubnew_page_042.png#42",
    "newspaper_5a8b7563a3262beecbecd7ddd3ef8827_1.jpg#1",
    "newspaper_8076765115f6c402e81c6bfb48139bc2_1.jpg#1",
    "newspaper_TheBostonGlobe-2025-1-8@magazinesclubnew_page_033.png#33",
    "newspaper_Chicago Tribune_0801@magazinesclubnew_page_032.png#32",
]
V3_RUN = ROOT / ".benchmarks/runs/omnidocbench/e2e-gpu-v3-20261003T065100Z/08-full-180-20261003T065030Z"


class ExperimentError(RuntimeError):
    pass


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def experiment_identity(
    *, config_id: str, max_new_tokens: int, base_config_sha256: str,
    manifest_sha256: str, source_commit: str, source_snapshot_sha256: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    payload = {
        "config_id": config_id,
        "max_new_tokens": max_new_tokens,
        "base_config_sha256": base_config_sha256,
        "manifest_sha256": manifest_sha256,
        "source_commit": source_commit,
        "source_snapshot_sha256": source_snapshot_sha256,
        "timeout_seconds": timeout_seconds,
        "override": "DOC_EXTRACTION_PADDLEX_EXPERIMENT_MAX_NEW_TOKENS",
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return {**payload, "experiment_config_sha256": sha256_bytes(canonical)}


def select_pages(manifest: dict[str, Any], v3_runtime: dict[str, Any], v3_predictions: Path) -> list[dict[str, Any]]:
    samples = manifest.get("subset", {}).get("samples", [])
    by_id = {sample.get("page_id"): sample for sample in samples}
    if len(by_id) != len(samples) or any(page_id not in by_id for page_id in PAGE_IDS):
        raise ExperimentError("five-page experiment IDs are missing/duplicated in the frozen manifest")
    successful = {
        record.get("page_id") for record in v3_runtime.get("per_page", [])
        if record.get("status") in {"success", "success_with_warnings"}
    }
    for page_id in PAGE_IDS[1:]:
        prediction = v3_predictions / Path(page_id.rsplit("#", 1)[0]).with_suffix(".md").name
        if page_id not in successful or not prediction.is_file():
            raise ExperimentError(f"stored 4096 v3 baseline missing success/prediction for {page_id}")
    if PAGE_IDS[0] in successful:
        raise ExperimentError("page #42 unexpectedly appears as a successful official 4096 page")
    return [by_id[page_id] for page_id in PAGE_IDS]


def parse_trace(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"status": "unavailable", "pages": {}}
    pages: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        input_name = event.get("input_name")
        if not isinstance(input_name, str):
            continue
        page = pages.setdefault(input_name, {"generation_calls": [], "regions": None})
        if event.get("event") == "recognition_process_batch_started":
            page["regions"] = event.get("input_count")
        if event.get("event") == "stage_finished" and event.get("stage") == "model_generate":
            page["generation_calls"].append({
                "batch_index": event.get("batch_index"),
                "runtime_seconds": event.get("elapsed_seconds"),
                "generated_tokens": event.get("generated_tokens"),
                "input_tokens": event.get("input_tokens"),
                "output_sequence_tokens": event.get("output_sequence_tokens"),
            })
        if event.get("event") == "recognition_process_batch_finished":
            page["last_batch_status"] = event.get("status")
            output = event.get("output")
            if isinstance(output, dict):
                page.setdefault("output_chars", []).append(output.get("result_chars"))
    for page in pages.values():
        values = [item["generated_tokens"] for item in page["generation_calls"]
                  if isinstance(item.get("generated_tokens"), int)]
        page["generation_calls_completed"] = len(page["generation_calls"])
        page["max_generated_tokens"] = max(values) if values else None
        page["aggregate_generated_tokens"] = sum(values) if values else None
        page["generated_token_observations"] = len(values)
    return {"status": "available", "pages": pages}


def _gpu_check() -> dict[str, Any]:
    gpu = subprocess.run(
        ["nvidia-smi", "--query-gpu=name,memory.total,memory.used", "--format=csv,noheader,nounits"],
        check=True, capture_output=True, text=True, timeout=10,
    ).stdout.strip().splitlines()
    processes = subprocess.run(
        ["nvidia-smi", "--query-compute-apps=pid,process_name,used_memory", "--format=csv,noheader,nounits"],
        check=True, capture_output=True, text=True, timeout=10,
    ).stdout.strip().splitlines()
    if len(gpu) != 1 or "L4" not in gpu[0]:
        raise ExperimentError(f"expected one NVIDIA L4, observed {gpu!r}")
    if processes:
        raise ExperimentError(f"GPU became occupied; leaving unrelated processes untouched: {processes!r}")
    fields = [part.strip() for part in gpu[0].split(",")]
    if len(fields) != 3 or int(fields[2]) > 512:
        raise ExperimentError(f"L4 is not idle enough for controlled experiment: {gpu[0]}")
    return {"gpu": gpu[0], "compute_processes": processes}


def _run_prepare(
    *, runtime_python: Path, dataset: Path, manifest: Path, config: Path,
    output: Path, page_ids: list[str], cap: int, trace_path: Path,
) -> int:
    _gpu_check()
    command = [
        str(runtime_python), str(ROOT / "experiments/005_omnidocbench/prepare.py"),
        "--dataset", str(dataset), "--backend", "paddleocr_vl", "--output", str(output),
        "--config", str(config), "--manifest", str(manifest), "--page-ids", *page_ids,
        "--keep-runs",
    ]
    env = dict(os.environ)
    env["DOC_EXTRACTION_PADDLEX_EXPERIMENT_MAX_NEW_TOKENS"] = str(cap)
    env["DOC_EXTRACTION_PADDLEX_TRACE"] = str(trace_path)
    print("+", " ".join(command), flush=True)
    completed = subprocess.run(command, cwd=ROOT, env=env, check=False)
    _gpu_check()
    return completed.returncode


def _coverage(run: Path, expected: list[str]) -> dict[str, Any]:
    runtime_path = run / "runtime.json"
    if not runtime_path.is_file():
        return {"expected": len(expected), "runtime_record": "missing", "valid": False}
    runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
    records = runtime.get("per_page", [])
    attempted = [record.get("page_id") for record in records]
    successful_statuses = {"success", "success_with_warnings"}
    failures = [record for record in records if record.get("status") not in successful_statuses]
    prediction_dir_name = json.loads((run / "run_metadata.json").read_text(encoding="utf-8")).get("prediction_directory", "")
    pred_dir = run / prediction_dir_name
    predictions = sorted(path.name for path in pred_dir.glob("*.md")) if pred_dir.is_dir() else []
    expected_names = sorted(Path(page.rsplit("#", 1)[0]).with_suffix(".md").name for page in expected)
    return {
        "expected": len(expected),
        "attempted": len(records),
        "success": sum(record.get("status") in successful_statuses for record in records),
        "failures": failures,
        "attempted_page_ids": attempted,
        "exact_attempts": attempted == expected and len(set(attempted)) == len(expected),
        "prediction_files": len(predictions),
        "missing_predictions": sorted(set(expected_names) - set(predictions)),
        "unexpected_predictions": sorted(set(predictions) - set(expected_names)),
        "valid": (
            attempted == expected and len(set(attempted)) == len(expected)
            and predictions == expected_names
        ),
    }


def _evaluate(runtime_python: Path, evaluator_python: Path, run: Path, dataset: Path) -> int:
    command = [
        str(runtime_python), str(ROOT / "experiments/005_omnidocbench/evaluate.py"),
        "--dataset", str(dataset), "--output", str(run),
        "--ground-truth", str(run / "ground_truth_subset.json"),
        "--omnidoc-repo", str(EVALUATOR_REPO), "--omnidoc-python", str(evaluator_python),
        "--match-method", "quick_match", "--match-workers", "1", "--teds-workers", "1",
        "--require-pinned-evaluator",
    ]
    return subprocess.run(command, cwd=ROOT, check=False).returncode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DATASET)
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--base-config", type=Path, default=BASE_CONFIG)
    parser.add_argument("--runtime-python", type=Path, default=ROOT / ".cache/e2e/paddleocr-vl-1_6-venv/bin/python")
    parser.add_argument("--evaluator-python", type=Path, default=ROOT / ".venv-omnidoc/bin/python")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--diagnostic-reference-timeout", type=int, default=600)
    parser.add_argument("--execute", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    import yaml

    from benchmarks.scripts.build_omnidocbench_manifest import verify_manifest

    output_root = args.output_root.resolve()
    if output_root.exists():
        raise ExperimentError(f"refusing to overwrite existing experiment directory: {output_root}")
    manifest_path = args.manifest.resolve()
    dataset = args.dataset.resolve()
    config = args.base_config.resolve()
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    _selected, _records, verified_manifest = verify_manifest(dataset, manifest_path)
    if verified_manifest["subset_identity"]["sha256"] != manifest["subset_identity"]["sha256"]:
        raise ExperimentError("manifest verification identity mismatch")
    v3_runtime = json.loads((V3_RUN / "runtime.json").read_text(encoding="utf-8"))
    metadata_path = V3_RUN / "run_metadata.json"
    v3_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    v3_prediction_dir = V3_RUN / v3_metadata["prediction_directory"]
    select_pages(manifest, v3_runtime, v3_prediction_dir)
    evaluator_revision = subprocess.run(
        ["git", "-C", str(EVALUATOR_REPO), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    if evaluator_revision != EVALUATOR_REVISION:
        raise ExperimentError(f"pinned evaluator mismatch: {evaluator_revision}")
    base = yaml.safe_load(config.read_text(encoding="utf-8"))
    if base.get("device") != "cuda" or base.get("limits", {}).get("max_runtime_seconds") != 300:
        raise ExperimentError("base config must remain CUDA + 300 second runtime policy")
    if hashlib.sha256(config.read_bytes()).hexdigest() != v3_metadata.get("config_sha256"):
        raise ExperimentError("stored v3 4096 baseline config differs from current base config")
    if not args.execute:
        print(json.dumps({"pages": PAGE_IDS, "base_config_sha256": hashlib.sha256(config.read_bytes()).hexdigest(),
                          "manifest_sha256": sha256_bytes(manifest_bytes), "evaluator_revision": evaluator_revision,
                          "v3_run": str(V3_RUN), "diagnostic_reference_timeout": args.diagnostic_reference_timeout,
                          "note": "plan only; no inference"}, indent=2, ensure_ascii=False))
        return 0

    gpu = _gpu_check()
    if args.diagnostic_reference_timeout <= 300 or args.diagnostic_reference_timeout > 900:
        raise ExperimentError("diagnostic reference timeout must be bounded in (300, 900] seconds")
    # Keep venv launchers unresolved: uv-managed/Python venv interpreters are
    # often symlinks, and resolving them drops the venv site-packages.
    runtime_python = Path(os.path.abspath(args.runtime_python))
    evaluator_python = Path(os.path.abspath(args.evaluator_python))
    output_root.mkdir(parents=True, exist_ok=False)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
                          capture_output=True, text=True).stdout.strip()
    prepare_spec = importlib.util.spec_from_file_location(
        "omnidocbench_prepare", ROOT / "experiments/005_omnidocbench/prepare.py"
    )
    if prepare_spec is None or prepare_spec.loader is None:
        raise ExperimentError("cannot load benchmark source-attestation helper")
    prepare_module = importlib.util.module_from_spec(prepare_spec)
    prepare_spec.loader.exec_module(prepare_module)
    source_attestation = prepare_module.build_source_attestation()
    base_hash = hashlib.sha256(config.read_bytes()).hexdigest()
    identity = {
        "experiment": "PaddleOCR-VL max_new_tokens sensitivity; diagnostic only",
        "gpu_preflight": gpu,
        "source_commit": head,
        "source_snapshot_sha256": source_attestation["source_snapshot_sha256"],
        "source_working_tree_clean": source_attestation["working_tree_clean"],
        "manifest_sha256": sha256_bytes(manifest_bytes),
        "subset_identity": manifest["subset_identity"],
        "dataset_annotation_sha256": manifest.get("dataset_identity", {}).get("annotation_sha256"),
        "evaluator_revision": evaluator_revision,
        "base_config_path": "configs/gpu.yaml",
        "base_config_sha256": base_hash,
        "model_identity_expected_from_v3": v3_metadata.get("pre_run_model_versions"),
        "page_ids": PAGE_IDS,
        "v3_reference_run": str(V3_RUN.relative_to(ROOT)),
        "diagnostic_reference_timeout_seconds": args.diagnostic_reference_timeout,
        "official_timeout_seconds": 300,
        "configs": {},
        "status": "running",
    }
    (output_root / "experiment.json").write_text(json.dumps(identity, indent=2, ensure_ascii=False) + "\n")

    # Page #42 gets a bounded non-benchmark 4096 reference with only the
    # timeout changed. Official 4096 results continue to mean 300 seconds.
    ref_dir = output_root / "4096-reference"
    ref_dir.mkdir()
    ref_config_obj = yaml.safe_load(config.read_text(encoding="utf-8"))
    ref_config_obj["limits"]["max_runtime_seconds"] = args.diagnostic_reference_timeout
    ref_config = ref_dir / "diagnostic-gpu.yaml"
    ref_config.write_text(yaml.safe_dump(ref_config_obj, sort_keys=False))
    ref_config_identity = experiment_identity(
        config_id="e2e-v3-tokens-4096-reference-only", max_new_tokens=4096,
        base_config_sha256=base_hash, manifest_sha256=sha256_bytes(manifest_bytes),
        source_commit=head, source_snapshot_sha256=source_attestation["source_snapshot_sha256"],
        timeout_seconds=args.diagnostic_reference_timeout,
    )
    (ref_dir / "experiment_config.json").write_text(json.dumps(ref_config_identity, indent=2) + "\n")
    ref_trace = ref_dir / "paddlex-trace.jsonl"
    ref_rc = _run_prepare(runtime_python=runtime_python, dataset=dataset, manifest=manifest_path,
                          config=ref_config, output=ref_dir / "run", page_ids=[PAGE_IDS[0]],
                          cap=4096, trace_path=ref_trace)
    identity["configs"]["4096_reference"] = {
        **ref_config_identity, "prepare_return_code": ref_rc,
        "coverage": _coverage(ref_dir / "run", [PAGE_IDS[0]]),
        "trace": parse_trace(ref_trace),
    }
    (output_root / "experiment.json").write_text(json.dumps(identity, indent=2, ensure_ascii=False) + "\n")

    for cap in (2048, 1024):
        name = str(cap)
        run_dir = output_root / name
        run_dir.mkdir()
        config_identity = experiment_identity(
            config_id=f"e2e-v3-tokens-{cap}", max_new_tokens=cap,
            base_config_sha256=base_hash, manifest_sha256=sha256_bytes(manifest_bytes),
            source_commit=head, source_snapshot_sha256=source_attestation["source_snapshot_sha256"],
            timeout_seconds=300,
        )
        (run_dir / "experiment_config.json").write_text(json.dumps(config_identity, indent=2) + "\n")
        trace_path = run_dir / "paddlex-trace.jsonl"
        rc = _run_prepare(runtime_python=runtime_python, dataset=dataset, manifest=manifest_path,
                          config=config, output=run_dir / "run", page_ids=PAGE_IDS,
                          cap=cap, trace_path=trace_path)
        coverage = _coverage(run_dir / "run", PAGE_IDS)
        run_metadata = json.loads((run_dir / "run" / "run_metadata.json").read_text(encoding="utf-8"))
        recorded_versions = run_metadata.get("pre_run_model_versions", {})
        expected_versions = v3_metadata.get("pre_run_model_versions", {})
        if expected_versions and recorded_versions != expected_versions:
            raise ExperimentError(f"model/package/weight identity changed for {cap} run")
        evaluation_rc = None
        if coverage.get("valid") and rc == 0:
            evaluation_rc = _evaluate(runtime_python, evaluator_python, run_dir / "run", dataset)
        identity["configs"][name] = {
            **config_identity, "prepare_return_code": rc,
            "coverage": coverage, "evaluation_return_code": evaluation_rc,
            "trace": parse_trace(trace_path),
        }
        (output_root / "experiment.json").write_text(json.dumps(identity, indent=2, ensure_ascii=False) + "\n")

    # Assemble an exact five-page 4096 quality reference from four already
    # completed v3 predictions plus the separate 4096 diagnostic page #42.
    reference_eval = ref_dir / "five-page-evaluation"
    reference_predictions = reference_eval / "predictions"
    reference_predictions.mkdir(parents=True)
    gt_source = output_root / "2048" / "run" / "ground_truth_subset.json"
    if gt_source.is_file():
        shutil.copy2(gt_source, reference_eval / "ground_truth_subset.json")
        for page_id in PAGE_IDS[1:]:
            name = Path(page_id.rsplit("#", 1)[0]).with_suffix(".md").name
            shutil.copy2(v3_prediction_dir / name, reference_predictions / name)
        ref_prediction_dir = ref_dir / "run" / json.loads((ref_dir / "run" / "run_metadata.json").read_text())["prediction_directory"]
        target_name = Path(PAGE_IDS[0].rsplit("#", 1)[0]).with_suffix(".md").name
        target_prediction = ref_prediction_dir / target_name
        if target_prediction.is_file():
            shutil.copy2(target_prediction, reference_predictions / target_name)
            baseline_rc = _evaluate(runtime_python, evaluator_python, reference_eval, dataset)
            identity["configs"]["4096_reference"]["five_page_evaluation_return_code"] = baseline_rc
        else:
            identity["configs"]["4096_reference"]["five_page_evaluation_return_code"] = None
    identity["status"] = "completed_experiment_runs"
    identity["final_gpu_preflight"] = _gpu_check()
    (output_root / "experiment.json").write_text(json.dumps(identity, indent=2, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ExperimentError, OSError, ValueError, json.JSONDecodeError, subprocess.SubprocessError) as exc:
        print(f"token-cap experiment failed closed: {exc}", file=sys.stderr)
        raise SystemExit(2)
