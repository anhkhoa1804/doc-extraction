"""Build compact, license-aware artifacts for the PaddleOCR-VL investigation.

This script does not run extraction or scoring. It records analysis from the
frozen classic result, the completed five-page smoke run, and the interrupted
full-population attempt. Document text and benchmark images are never copied.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "benchmarks/reports/omnidocbench"
CLASSIC = REPORTS / "representative-v2.json"
PREFLIGHT = ROOT / ".benchmarks/runs/omnidocbench/e2e-paddleocr-vl16-preflight-20261002T101500Z"
INTERRUPTED = ROOT / ".benchmarks/runs/omnidocbench/e2e-paddleocr-vl16-representative-v2-20261002T093653Z"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def make_failure_analysis() -> dict[str, Any]:
    baseline = read_json(CLASSIC)
    metrics = baseline["metrics"]
    rows = {row["page_id"]: row for row in metrics["page_results"]}
    page_id_by_image = {row["image_name"]: row["page_id"] for row in metrics["page_results"]}
    per_page = metrics["per_page_metrics"]
    rankings = {
        "text_block_Edit_dist": True,
        "table_Edit_dist": True,
        "TEDS_per_page_mean_diagnostic": False,
        "TEDS_structure_only_per_page_mean_diagnostic": False,
        "reading_order_Edit_dist": True,
        "display_formula_Edit_dist": True,
    }
    selected: set[str] = set()
    for name, highest_is_worst in rankings.items():
        candidates = [
            (values[name], page_id_by_image[image])
            for image, values in per_page.items()
            if name in values and image in page_id_by_image
        ]
        candidates.sort(reverse=highest_is_worst)
        selected.update(page for _, page in candidates[:5])
    selected.update(
        {
            "page-062fc21c-6b9c-40be-8d0e-7a617509a9bc.png#0",
            "page-50ffe5d2-cd27-449a-a813-d4a8c44b12ea.png#0",
            "page-14cd673f-d86d-45a7-a13e-2b4e1d91c08f.png#0",
            "page-112859dc-07d9-473a-a027-94904db8fd84.png#0",
            "page-31fb2a53-5b32-40f6-9db1-52b357f3201f.png#0",
        }
    )
    cases = []
    for page_id in sorted(selected):
        row = rows.get(page_id)
        if row is None:
            continue
        route = row["route_status_runtime"]
        cases.append(
            {
                "page_id": page_id,
                "sample_id": row.get("sample_id"),
                "source_metadata": row.get("source_metadata", {}),
                "route": route.get("route"),
                "backend": "classic production backend",
                "runtime_seconds": route.get("runtime_seconds"),
                "status": route.get("status"),
                "warnings": route.get("warnings", []),
                "warnings_count": route.get("warnings_count"),
                "metrics": row.get("metrics", {}),
                "prediction_id": route.get("prediction_id"),
                "prediction_sha256": route.get("prediction_sha256"),
                "ground_truth_page_id": page_id,
                "classification": "UNKNOWN",
                "notes": "Selected by frozen metric-rank rule for inspection; source text omitted because dataset redistribution terms are unverified.",
            }
        )
    findings = [
        {
            "page_id": "page-062fc21c-6b9c-40be-8d0e-7a617509a9bc.png#0",
            "label": "OBSERVED",
            "finding": "Classic final Document contains five formula-labelled regions with null text; OCR returned zero tokens; benchmark Markdown is header-only/empty.",
            "inference": "The loss precedes the benchmark serializer. The available trace places it in the classic layout/OCR path, but does not identify a lower-level model root cause.",
        },
        {
            "page_id": "page-50ffe5d2-cd27-449a-a813-d4a8c44b12ea.png#0",
            "label": "OBSERVED",
            "finding": "The wide/rotated table page has a negative per-page TEDS diagnostic (-0.036909) while structure-only TEDS is 0.84375.",
            "inference": "The discrepancy is consistent with severe cell-content mismatch or a diagnostic/evaluation edge case; no cause is confirmed.",
        },
        {
            "page_id": "page-14cd673f-d86d-45a7-a13e-2b4e1d91c08f.png#0",
            "label": "OBSERVED",
            "finding": "A handwriting/equation-hard page has near-1 text and formula Edit distance in the frozen baseline.",
            "inference": "Recognition, formula serialization, annotation semantics, and matching remain competing explanations without a complete artifact-by-artifact adjudication.",
        },
    ]
    return {
        "schema_version": "e2e-failure-analysis/1",
        "source_run": baseline["runtime"]["run_id"],
        "selection_rule": "Outcome-ranked analysis sample only: union of the five worst pages on each available per-page metric (higher Edit distance is worse; lower TEDS diagnostic is worse), plus five predeclared empty/table/formula diagnostic pages. This does not redefine the benchmark population.",
        "selected_case_count": len(cases),
        "content_policy": "Only IDs, metadata, hashes, and metric values are committed; no document text or benchmark images are copied.",
        "cases": cases,
        "findings": findings,
        "limitations": [
            "This is a ranked inspection set, not a blinded or representative sample.",
            "Most selected cases have metric evidence only; root-cause labels remain UNKNOWN.",
            "Table TEDS per-page values are diagnostic outputs; official aggregate metrics remain the evaluator's all-table aggregation.",
        ],
    }


def make_e2e_record() -> dict[str, Any]:
    runtime = read_json(PREFLIGHT / "runtime.json")
    metrics = read_json(PREFLIGHT / "metrics.json")
    per_page = runtime["per_page"]
    return {
        "schema_version": "e2e-pretrained-evaluation/1",
        "record_status": "full_population_blocked_no_quality_baseline",
        "benchmark": {
            "name": "OmniDocBench",
            "version": "1.6",
            "subset": "representative-v2 frozen 180 pages; incomplete run not scored",
            "evaluator_commit": "193627ae9e97d89188468ed1ee3b7a856ff76044",
        },
        "classic_comparison_run": "representative-v2-full-20261002T080500Z",
        "population_identity": {
            "sample_count": 180,
            "manifest_sha256": "899191e7471ae5c826a6a07ff7edf3c7c8facec72764196ef9f3f49a8265a93b",
            "same_manifest_requested": True,
        },
        "model": {
            "name": "PaddleOCR-VL-1.6 official page-level PaddleOCR pipeline",
            "model_id": "PaddlePaddle/PaddleOCR-VL-1.6",
            "preflight_run_metadata_revision_field": "676e2aa (recorded value; exact upstream artifact identity not independently verified)",
            "full_attempt_revision_metadata": None,
            "post_run_observed_cache_weight_sha256": {
                "PaddleOCR-VL-1.6/model.safetensors": "85a479d506a11e724e7285d395c551be69f41dbc16b6342d3cacfb189aed71db",
                "PP-DocLayoutV3/inference.pdiparams": "70bd316b0582769ec968829fd1feb1a6a58b7c941b938327e551b6b12b45c137",
            },
            "cache_hash_caveat": "Hashes were computed after inference from the local PaddleX cache; they were not captured in preflight run_metadata.json and cannot prove the bytes used by that invocation.",
            "license": "Apache-2.0 according to official model card; complete deployment dependency/license review remains open.",
        },
        "source_reproducibility": {
            "git_commit_recorded_by_preflight": "eaea32d76dcd1cf01fd1615088a31f4e62d318c5",
            "working_tree_at_run": "modified/uncommitted E2E adapter and runner; exact as-run source snapshot hash was not recorded",
            "current_adapter_sha256": "21be47a68f1be6a4ea4fa2d7505866e22644c1e460eab2dbb21501ec1e2fd648",
            "reproduction_limitation": "The invocation is not fully source-pinned. Current source hash documents this report-building state, not an attested as-run source snapshot.",
        },
        "environment": {
            "gpu": "NVIDIA L4, 23034 MiB",
            "nvidia_driver": "580.178.04",
            "nvidia_smi_cuda": "13.0",
            "paddle_cuda_build": "12.6",
            "paddlepaddle_gpu": "3.2.1",
            "paddleocr": "3.7.0",
            "paddlex": "3.7.2",
            "inference_precision": "official pipeline default; model file BF16",
            "batch_size": 1,
            "config": "configs/gpu.yaml",
            "config_sha256": "ea3e0415e6e7699c081dfc7a3d2abcf9344c02db704865beb91ef783e1102748",
        },
        "smoke_preflight": {
            "status": "completed_diagnostic_only_not_baseline",
            "run_id": "e2e-paddleocr-vl16-preflight-20261002T101500Z",
            "sample_count": 5,
            "succeeded": 5,
            "failed": 0,
            "warnings": 0,
            "wall_seconds": runtime["wall_clock_seconds"],
            "mean_seconds_per_page": runtime["mean_seconds_per_page"],
            "median_seconds_per_page": runtime["median_seconds_per_page"],
            "p95_seconds_per_page": runtime["p95_seconds_per_page"],
            "min_seconds_per_page": runtime["min_seconds_per_page"],
            "max_seconds_per_page": runtime["max_seconds_per_page"],
            "sample_ids": [page["page_id"] for page in per_page],
            "metrics": {
                "text_block_edit_distance": {"value": metrics["text_block"]["all"]["Edit_dist"]["ALL_page_avg"], "n": 4},
                "table_edit_distance": {"value": metrics["table"]["all"]["Edit_dist"]["ALL_page_avg"], "n": 2},
                "table_teds": {"value": metrics["table"]["all"]["TEDS"]["all"], "table_cases": 3, "page_denominator": 2},
                "table_structure_teds": {"value": metrics["table"]["all"]["TEDS_structure_only"]["all"], "table_cases": 3, "page_denominator": 2},
                "reading_order_edit_distance": {"value": metrics["reading_order"]["all"]["Edit_dist"]["ALL_page_avg"], "n": 5},
                "formula_edit_distance": {"value": metrics["display_formula"]["all"]["Edit_dist"]["ALL_page_avg"], "n": 2},
            },
        },
        "full_population_attempt": {
            "status": "interrupted_unscored",
            "run_id": "e2e-paddleocr-vl16-representative-v2-20261002T093653Z",
            "frozen_population": 180,
            "prediction_files_written": 158,
            "last_completed_page_id": "newspaper_Daily Mail_2022-08-01@magazinesclubnew_page_009.png#9",
            "in_progress_page_id": "newspaper_TheWashingtonPost-2025-01-08@magazinesclubnew_page_042.png#42",
            "configured_max_runtime_seconds": 300,
            "observed_operation_elapsed_seconds": ">300",
            "cancellation": "Keyboard interrupt did not terminate PaddleOCR-VL worker within the process; the run process was then terminated and its GPU use verified at zero. No unrelated process was signalled.",
            "metrics": None,
            "reason_not_scored": "Exact prediction/GT coverage was incomplete. Scoring the 158 completed pages would violate the frozen population requirement. Continuing would require bypassing or redesigning runtime isolation, which was not authorized in this measurement.",
        },
        "full_population_quality_metrics": None,
        "result_interpretation": "No full representative-v2 E2E score exists. The five-page smoke is diagnostic only and must not be compared numerically to the 180-page Classic baseline.",
    }


def main() -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    failure = make_failure_analysis()
    e2e = make_e2e_record()
    comparison = {
        "schema_version": "classic-e2e-comparison/1",
        "status": "NOT_COMPARABLE_FULL_POPULATION_E2E_BLOCKED",
        "classic_run": "representative-v2-full-20261002T080500Z",
        "e2e_run": "e2e-paddleocr-vl16-representative-v2-20261002T093653Z",
        "same_manifest": True,
        "classic_metrics": {
            "text_block_edit_distance": {"value": 0.5739880899019053, "n": 168},
            "table_edit_distance": {"value": 0.7125178638784991, "n": 50},
            "table_teds": {"value": 0.3981107344001522, "n_pages": 50, "n_table_cases": 64},
            "table_structure_teds": {"value": 0.6323174152284948, "n_pages": 50, "n_table_cases": 64},
            "reading_order_edit_distance": {"value": 0.5849918953131392, "n": 178},
            "formula_edit_distance": {"value": 0.9853894477253515, "n": 35},
            "success_rate": {"value": 1.0, "n": 180},
            "warning_rate": {"value": 0.0, "n": 180},
            "runtime_seconds": {"value": 1190.221, "n": 180},
        },
        "e2e_full_population_metrics": None,
        "smoke_metrics": "Stored separately in e2e-pretrained-v1.json; five diagnostic pages only; not a same-population comparison.",
        "deltas": None,
        "comparison_rule": "No score delta is emitted unless complete predictions, exact same frozen population, and matching metric protocol exist for both systems.",
    }
    write_json(REPORTS / "failure-analysis-v1.json", failure)
    write_json(REPORTS / "e2e-pretrained-v1.json", e2e)
    write_json(REPORTS / "classic-vs-e2e-v1.json", comparison)

    fail_lines = [
        "# OmniDocBench Failure Analysis v1", "",
        f"Analysis records: **{failure['selected_case_count']} pages** from the frozen classic representative-v2 run.",
        "Selection is outcome-ranked for diagnosis only; it is not a new benchmark population. No benchmark text or images are reproduced because dataset redistribution terms are unverified.", "",
        "## Observed findings", "",
    ]
    for item in failure["findings"]:
        fail_lines += [f"### {item['page_id']}", "", f"**{item['label']}:** {item['finding']}", "", f"**Inference, not confirmed:** {item['inference']}", ""]
    fail_lines += ["## Dominant measured symptoms", "", "The classic frozen metrics show high normalized edit distances for text (0.573988), reading order (0.584992), tables (0.712518), and formulas (0.985389). These are benchmark-protocol mismatches, not causal diagnoses. The available artifacts provide a confirmed empty-output path trace for one page; most ranked pages remain cause-unknown.", "", "Table aggregate TEDS (0.398111) and structure-only TEDS (0.632317) are the evaluator's `all` aggregations. Per-page means (0.413877 and 0.673171) are diagnostics and not interchangeable with these aggregates.", "", "## Limitations", "", *[f"- {note}" for note in failure["limitations"]], ""]
    (REPORTS / "failure-analysis-v1.md").write_text("\n".join(fail_lines), encoding="utf-8")

    e2e_lines = [
        "# PaddleOCR-VL 1.6 Pretrained Baseline Attempt", "",
        "**Status: full representative-v2 quality baseline BLOCKED; no full-population metrics were produced.**", "",
        "## Five-page smoke (diagnostic only)", "",
        "| Metric | Value | N | Status |", "|---|---:|---:|---|",
    ]
    for key, item in e2e["smoke_preflight"]["metrics"].items():
        e2e_lines.append(f"| {key} | {item['value']:.6f} | {item.get('n', item.get('page_denominator', '—'))} | NOT A BASELINE |")
    e2e_lines += [
        "", "The smoke set had 5/5 successful predictions, no warnings, and a 204.765 second wall time. It was deliberately diagnostic, selected to cover several failure types, so these scores cannot be generalized or compared to the 180-page baseline.",
        "", "## Failure-analysis bridge", "",
        "Classic's highest-level symptoms are high text/reading-order/table/formula Edit distances. A concrete empty-output trace was followed through OCR result, canonical page elements, and the benchmark serializer: the classic page had five formula-labelled regions with null text and zero OCR tokens, so the empty Markdown was not introduced by the final benchmark serializer. The smoke output for this page was nonempty (its text ED changed from 1.0 to 0.19436 on this page only). This is a page-level observation, not evidence of general improvement or of the classic backend's precise internal root cause.",
        "", "For tables, classic aggregate TEDS is 0.398111 and structure-only TEDS 0.632317. The higher structure score is consistent with content mismatch after structure is partly recognized, but does not isolate OCR/cell segmentation/normalization. One wide/rotated page has a negative per-page TEDS diagnostic; this needs evaluator/protocol investigation rather than a causal claim. The 5-page E2E smoke includes only two table pages and is not a useful comparative estimate.",
        "", "Formula Edit distance is 0.985389 over 35 pages for Classic. This identifies a weak benchmark result, not whether formulas were missed, serialized incorrectly, or mismatched against annotations. The smoke subset's formula score has N=2 and cannot resolve that ambiguity. Reading-order ED is 0.584992 over 178 pages; order versus missing text and annotation alignment remain entangled.",
        "", "## Candidate audit and selection", "",
        "| Candidate | Assessment | Fit / limitation | Runtime and license note |", "|---|---|---|---|",
        "| PaddleOCR-VL 1.6 (~1.0B card listing) | CANDIDATE FOR IMMEDIATE BASELINE; smoke-tested, full baseline blocked | Official page parsing pipeline emits block labels/content/geometry/order; table HTML can be adapted. Consumed output lacks cell-level geometry/confidence; all claims remain model-output dependent. Vietnamese performance is not established. | Runs on L4, but observed page call exceeded 300s; hard cancellation absent. Model card declares Apache-2.0; dependency distribution review remains open. |",
        "| DeepSeek-OCR-2 (3B) | CANDIDATE FOR FUTURE | Document-to-Markdown/grounding, multilingual; output is less directly region-structured for the present canonical mapping. | Official card's usage examples set `trust_remote_code=True`; 3B VRAM/runtime not tested here. Apache-2.0 on card. |",
        "| olmOCR 2 (7B) | CANDIDATE FOR FUTURE, not selected | Document OCR, tables/equations/reading order, Markdown output and training code; page-level geometry mapping is limited. | 7B path is materially heavier for an L4 first trial; Apache-2.0 project/model listing, exact selected-weight terms still require checking. |",
        "| dots.mocr (3B) | NOT SUITABLE FOR THIS DATA RUN pending rights review | Broad multilingual parsing and structured graphics output, but would require separate adapter and license review. | Custom license agreement restricts unauthorized digitization/scanning of copyrighted publications; benchmark image rights have not been verified. |",
        "", "Selection rationale: PaddleOCR-VL 1.6 has an official page-level pipeline, explicit structured regions/tables and successful local execution on the L4. Its own model card reports OmniDocBench v1.6 evaluation; benchmark-specific optimization/exposure is therefore a generalization concern, not evidence of data leakage. The same local OmniDocBench protocol still provides an apples-to-apples engineering test if the full run becomes safely executable.",
        "", "## Backend and canonical mapping", "",
        "Optional backend `paddleocr_vl` is registered at the existing backend boundary. It imports the runtime lazily; maps model-provided labels/text/order and valid page boxes into existing `Page`/`Element`; converts parseable HTML tables into canonical `Table`/`Cell`; leaves unknown geometry and confidence null; retains malformed table output as text with an `E2E_UNSUPPORTED` note. It accepts raster page images only. No canonical schema or KP fields changed. Smoke tests use deterministic fake model output; model integration is the external smoke/run artifact.",
        "", "## Resource and output limitations", "",
        "L4: NVIDIA L4, 23034 MiB; NVIDIA driver 580.178.04; nvidia-smi CUDA 13.0; tested Paddle GPU wheel CUDA 12.6; PaddlePaddle GPU 3.2.1 / PaddleOCR 3.7.0 / PaddleX 3.7.2; batch size 1; official pipeline defaults and safetensors weights. Sampled VRAM during the interrupted run reached 15028 MiB (not a profiler-captured peak; an earlier single sample reached 20552 MiB).",
        "", "## Full-population attempt", "",
        "The exact frozen 180-page manifest was used. 158 predictions were written; processing exceeded the configured 300-second runtime boundary on `newspaper_TheWashingtonPost-2025-01-08@magazinesclubnew_page_042.png#42`. The in-process Paddle worker did not terminate on interruption. The attempt was stopped, outputs preserved locally, and no partial scoring was run. The directory is labelled incomplete and unscored; it is ignored by Git.",
        "", "Configured runtime check is post-operation for this in-process backend; it therefore does not provide hard cancellation. A worker isolation/cancellation boundary is required before a repeat. No resource limit was changed or bypassed.",
        "", "## Fine-tuning gate", "",
        "**Decision: FINE-TUNING NOT YET JUSTIFIED.** The same-manifest pretrained result is absent, so there is no reproducible quality or failure-mode advantage on which to base training. A future adaptation study could examine Chinese/English text recognition, reading order, table cell content/structure, and formula transcription, but only after a valid pretrained baseline and rights-cleared labeled data exist.",
        "", "## Training-data plan (not collected)", "",
        "For a later physical-extraction dataset, define page-image and document/page identity, text-region polygons/boxes and verbatim content, region type, reading-order edges/indices, table region and cell grid with spans/cell text, formulas (LaTeX/string plus region geometry), and headings/paragraph grouping where annotation consistency is achievable. Store source/license/consent and split by source document to avoid page leakage. Do not include KP entities, relations, ontology labels, or semantic field answers.",
        "", "## Interpretation", "",
        "OBSERVED: five smoke pages converted successfully and yielded nonempty outputs; the 180-page run hit an uninterruptible long inference operation; the classic empty-output case is upstream of benchmark Markdown serialization.",
        "", "INFERRED: a page-level E2E parser may help some visually complex pages; a classic/E2E hybrid could be worth considering only after paired full-subset evidence and operational isolation.",
        "", "NOT ESTABLISHED: full-population E2E quality, superiority to Classic, subgroup generalization, causal bottleneck attribution, production readiness, or a fine-tuning benefit.",
        "", "## Reproducibility", "",
        f"Classic run: `representative-v2-full-20261002T080500Z`; frozen manifest SHA-256 `{e2e['population_identity']['manifest_sha256']}`; config SHA-256 `{e2e['environment']['config_sha256']}`; upstream evaluator revision `{e2e['benchmark']['evaluator_commit']}`. Smoke run metadata and per-page hashes remain in the ignored local run directory; the full partial directory is `e2e-paddleocr-vl16-representative-v2-20261002T093653Z`. Reports are generated by `benchmarks/scripts/build_e2e_research_reports.py`.",
        "", "## Limitations", "",
        "This is a blocked pretrained baseline, not a valid current full-population quality result. The existing runtime guard is post-return for in-process inference. Preflight metadata recorded model revision `676e2aa`, but that value's exact upstream identity was not verified; local cache weight hashes were measured after the run and were not captured as invocation-time hashes. The source tree was dirty during execution, so the recorded Git commit does not uniquely identify the as-run E2E source snapshot. OmniDocBench image licensing is unverified, so source images and prediction text are not committed. The official model card reports its own OmniDocBench evaluation; this does not establish generalization outside that benchmark family.",
        "",
    ]
    (REPORTS / "e2e-pretrained-v1.md").write_text("\n".join(e2e_lines), encoding="utf-8")

    comparison_lines = [
        "# Classic vs E2E v1", "",
        "**Comparison status: NOT DIRECTLY COMPARABLE.** Classic completed all 180 pages; E2E did not. No metric deltas are calculated.", "",
        "| Metric | Classic (N) | E2E full (N) | Delta | Status |", "|---|---:|---:|---:|---|",
        "| Text Edit distance | 0.573988 (168) | — | — | E2E full not measured |",
        "| Table Edit distance | 0.712518 (50 pages) | — | — | E2E full not measured |",
        "| Table TEDS | 0.398111 (64 tables / 50 pages) | — | — | E2E full not measured |",
        "| Table structure TEDS | 0.632317 (64 tables / 50 pages) | — | — | E2E full not measured |",
        "| Reading-order Edit distance | 0.584992 (178) | — | — | E2E full not measured |",
        "| Formula Edit distance | 0.985389 (35) | — | — | E2E full not measured |",
        "| Success rate | 100% (180) | 87.8% written predictions, incomplete | — | Not comparable; prediction file count is not success rate |",
        "| Warning rate | 0% (180) | — | — | E2E aggregate metadata absent after interruption |",
        "| Runtime | 1190.221 s (180) | >300 s/page operation observed | — | Different/incomplete workload |",
        "", "The five-page smoke metrics are reported separately. They are not used as the E2E column above because their selected population differs from the complete frozen baseline population.", "",
    ]
    (REPORTS / "classic-vs-e2e-v1.md").write_text("\n".join(comparison_lines), encoding="utf-8")


if __name__ == "__main__":
    main()
