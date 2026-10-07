"""Opt-in, bounded timing probe for Docling CodeFormulaVlmModel.

This diagnostic patches methods in-process only. It does not modify installed
packages or model inputs/settings, and records no image pixels, prompts, or
generated text. Example:

    python benchmarks/scripts/profile_docling_formula.py \
      --dataset experiments/034a_omnidocbench_snapshot/dataset/full \
      --manifest benchmarks/manifests/omnidocbench-representative-v2.json \
      --config .benchmarks/diagnostics/phase1-completion-formula-local-20261006/candidate.yaml \
      --output .benchmarks/diagnostics/formula-profile-run \
      --page-ids PAGE_ID_1 PAGE_ID_2
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path
from typing import Any


def _token_id_set(value: Any) -> set[int]:
    values = value if isinstance(value, (list, tuple, set)) else [value]
    return {int(item) for item in values if item is not None}


def summarize_generated_rows(
    rows: list[list[int]],
    *,
    input_tokens: int | None,
    eos_token_id: Any,
    pad_token_id: Any,
    max_new_tokens: int | None,
) -> list[dict[str, Any]] | None:
    """Count generated positions to EOS/padding without retaining token IDs.

    Transformers returns a rectangular tensor for a batch. The shared prompt
    width is removed first; each row is then measured independently. A row
    whose visible length equals the configured cap is reported as
    ``cap_length_observed`` rather than claiming the model stopped because of
    the cap: EOS at that exact position is also possible.
    """
    if input_tokens is None:
        return None
    eos_ids = _token_id_set(eos_token_id)
    pad_ids = _token_id_set(pad_token_id)
    summaries: list[dict[str, Any]] = []
    for row in rows:
        tail = row[input_tokens:]
        eos_at = next((index for index, token in enumerate(tail) if token in eos_ids), None)
        pad_at = next((index for index, token in enumerate(tail) if token in pad_ids), None)
        if eos_at is not None and (pad_at is None or eos_at <= pad_at):
            count, reason = eos_at + 1, "eos_observed"
        elif pad_at is not None:
            count, reason = pad_at, "pad_observed_without_prior_eos"
        else:
            count = len(tail)
            reason = "cap_length_observed" if max_new_tokens is not None and count >= max_new_tokens else "returned_without_eos_or_pad"
        summaries.append({
            "generated_tokens": count,
            "completion_observation": reason,
            "cap_length_observed": max_new_tokens is not None and count >= max_new_tokens,
        })
    return summaries


def generation_input_kwargs(
    kwargs: dict[str, Any], *, formula_cap_override: int | None
) -> dict[str, Any]:
    """Return VlmEngineInput kwargs with an opt-in formula-only cap override.

    The override is for isolated diagnostics only. Production configuration is
    unchanged, and callers receive a copy so the installed library's defaults
    are not mutated in place.
    """
    result = dict(kwargs)
    if formula_cap_override is not None and result.get("prompt") == "<formula>":
        result["max_new_tokens"] = formula_cap_override
    return result


def run_profile(
    dataset: Path,
    manifest: Path,
    config: Path,
    output: Path,
    page_ids: list[str],
    *,
    formula_cap_override: int | None = None,
) -> int:
    from docling.datamodel.settings import settings
    from docling.document_converter import DocumentConverter
    from docling.models.base_model import BaseItemAndImageEnrichmentModel
    from docling.models.stages.code_formula import (
        code_formula_vlm_model as code_formula_module,
    )
    from docling.models.stages.code_formula.code_formula_vlm_model import (
        CodeFormulaVlmModel,
    )

    from doc_extraction.backends.docling_backend import DoclingBackend

    events: dict[str, Any] = {
        "schema_version": "docling-formula-profile/2",
        "scope": "diagnostic-only; method wrappers; no prompts, pixels, or generated text",
        "formula_cap_override": formula_cap_override,
        "initializations": [],
        "crop_preparation": [],
        "generation_batches": [],
        "formula_stage_calls": [],
        "pipeline_cache_events": [],
        "backend_lifecycle": [],
        "docling_pipeline_timings": [],
        "limits": {"max_pages": 5, "max_records_per_kind": 512},
    }
    context: dict[str, Any] = {
        "page_id": None,
        "next_region_index": 0,
        "region_indices_by_item_id": {},
        "active_batch_regions": [],
    }
    original_prepare = BaseItemAndImageEnrichmentModel.prepare_element
    original_init = CodeFormulaVlmModel.__init__
    original_call = CodeFormulaVlmModel.__call__
    original_converter_get_pipeline = DocumentConverter._get_pipeline
    original_converter_convert = DocumentConverter.convert
    original_backend_init = DoclingBackend.__init__
    original_backend_get_converter = DoclingBackend._get_converter
    original_vlm_engine_input = code_formula_module.VlmEngineInput
    original_profile_timings = settings.debug.profile_pipeline_timings
    pipeline_ids: dict[int, int] = {}
    converter_ids: dict[int, int] = {}
    backend_ids: dict[int, int] = {}

    def stable_object_id(obj: Any, registry: dict[int, int]) -> int:
        key = id(obj)
        if key not in registry:
            registry[key] = len(registry) + 1
        return registry[key]

    def page_record(kind: str, record: dict[str, Any]) -> None:
        records = events[kind]
        if len(records) < events["limits"]["max_records_per_kind"]:
            records.append({"page_id": context["page_id"], **record})

    def traced_prepare(self, conv_res, element):
        started = time.perf_counter()
        result = original_prepare(self, conv_res, element)
        if result is not None and getattr(getattr(element, "label", None), "value", None) == "formula":
            region_index = context["next_region_index"]
            context["next_region_index"] += 1
            context["region_indices_by_item_id"][id(getattr(element, "item", element))] = region_index
            image = result.image
            if hasattr(image, "size") and isinstance(image.size, tuple):
                width, height = image.size
            else:
                height, width = image.shape[:2]
            page_record("crop_preparation", {
                "region_index": region_index,
                "label": "formula",
                "crop_width": int(width), "crop_height": int(height),
                "crop_pixels": int(width * height),
                "prepare_seconds": round(time.perf_counter() - started, 6),
            })
        return result

    def traced_init(self, *args, **kwargs):
        started = time.perf_counter()
        original_init(self, *args, **kwargs)
        page_record("initializations", {
            "seconds": round(time.perf_counter() - started, 6),
            "model_repo": getattr(self, "repo_id", None),
            "model_revision": getattr(self, "revision", None),
            "engine_class": type(getattr(self, "engine", None)).__name__,
            "model_instance_sequence": len(events["initializations"]) + 1,
        })
        engine = self.engine
        original_predict_batch = engine.predict_batch

        def traced_predict_batch(inputs):
            images = [getattr(item, "image", None) for item in inputs]
            dimensions = []
            for image in images:
                if image is None:
                    dimensions.append(None)
                elif hasattr(image, "size") and isinstance(image.size, tuple):
                    dimensions.append([int(image.size[0]), int(image.size[1])])
                else:
                    dimensions.append([int(image.shape[1]), int(image.shape[0])])
            inline_engine = getattr(engine, "actual_engine", engine)
            model = getattr(inline_engine, "vlm_model", None)
            original_generate = getattr(model, "generate", None)
            generated: list[dict[str, Any]] = []
            if model is not None and callable(original_generate):
                def traced_generate(*gen_args, **gen_kwargs):
                    input_ids = gen_kwargs.get("input_ids")
                    if input_ids is None and gen_args:
                        input_ids = gen_args[0]
                    input_tokens = int(input_ids.shape[-1]) if input_ids is not None else None
                    started = time.perf_counter()
                    output = original_generate(*gen_args, **gen_kwargs)
                    elapsed = time.perf_counter() - started
                    output_tokens = int(output.shape[-1]) if hasattr(output, "shape") else None
                    generation_config = gen_kwargs.get("generation_config")
                    configured_cap = getattr(generation_config, "max_new_tokens", None)
                    eos_value = getattr(generation_config, "eos_token_id", None)
                    pad_value = getattr(generation_config, "pad_token_id", None)
                    parameter_device = None
                    row_summaries = None
                    if hasattr(output, "detach") and input_tokens is not None:
                        try:
                            rows = output.detach().to("cpu").tolist()
                            row_summaries = summarize_generated_rows(
                                rows,
                                input_tokens=input_tokens,
                                eos_token_id=eos_value,
                                pad_token_id=pad_value,
                                max_new_tokens=configured_cap,
                            )
                        except Exception:  # noqa: BLE001 - telemetry must not alter inference
                            row_summaries = None
                    try:
                        parameter_device = str(next(model.parameters()).device)
                    except (AttributeError, StopIteration, TypeError):
                        pass
                    generated.append({
                        "input_tokens": input_tokens,
                        "output_sequence_tokens": output_tokens,
                        "padded_new_sequence_positions": (
                            max(0, output_tokens - input_tokens)
                            if output_tokens is not None and input_tokens is not None else None
                        ),
                        "configured_max_new_tokens": configured_cap,
                        "per_region_generation": row_summaries,
                        "input_device": str(getattr(input_ids, "device", None)) if input_ids is not None else None,
                        "output_device": str(getattr(output, "device", None)),
                        "model_parameter_device": parameter_device,
                        "generation_seconds": round(elapsed, 6),
                    })
                    return output
                model.generate = traced_generate
            started = time.perf_counter()
            try:
                outputs = original_predict_batch(inputs)
            finally:
                if model is not None and callable(original_generate):
                    model.generate = original_generate
            elapsed = time.perf_counter() - started
            page_record("generation_batches", {
                "regions": len(inputs),
                "region_indices": [item.get("region_index") for item in context["active_batch_regions"]],
                "region_labels": [item.get("label") for item in context["active_batch_regions"]],
                "crop_dimensions": dimensions,
                "batch_seconds_including_processor_decode": round(elapsed, 6),
                "generation_calls": generated,
                "batch_padded_new_sequence_positions": max((
                    item["padded_new_sequence_positions"] for item in generated
                    if item["padded_new_sequence_positions"] is not None
                ), default=None),
                "output_char_counts": [len(getattr(item, "text", "")) for item in outputs],
            })
            return outputs

        engine.predict_batch = traced_predict_batch

    def traced_backend_init(self, *args, **kwargs):
        original_backend_init(self, *args, **kwargs)
        page_record("backend_lifecycle", {
            "event": "backend_constructed",
            "backend_instance_sequence": stable_object_id(self, backend_ids),
            "device": getattr(self, "device", None),
            "formula_enrichment": getattr(self, "formula_enrichment", None),
        })

    def traced_backend_get_converter(self):
        cached_before = getattr(self, "_converter", None) is not None
        converter = original_backend_get_converter(self)
        page_record("backend_lifecycle", {
            "event": "converter_returned",
            "backend_instance_sequence": stable_object_id(self, backend_ids),
            "converter_instance_sequence": stable_object_id(converter, converter_ids),
            "converter_was_cached_before_call": cached_before,
        })
        return converter

    def traced_get_pipeline(self, *args, **kwargs):
        fmt = kwargs.get("doc_format")
        if fmt is None and args:
            fmt = args[0]
        format_option = self.format_to_options.get(fmt) if fmt is not None else None
        pipeline_cls = getattr(format_option, "pipeline_cls", None)
        options = getattr(format_option, "pipeline_options", None)
        # Mirror Docling's key construction without retaining serialized config.
        from docling.utils.pipeline_cache import create_pipeline_options_hash
        options_hash = create_pipeline_options_hash(options) if options is not None else None
        cache_key = (pipeline_cls, options_hash)
        cache_hit_before_call = cache_key in self.initialized_pipelines
        pipeline = original_converter_get_pipeline(self, *args, **kwargs)
        page_record("pipeline_cache_events", {
            "converter_instance_sequence": stable_object_id(self, converter_ids),
            "format": str(getattr(fmt, "value", fmt)),
            "pipeline_class": getattr(pipeline_cls, "__name__", None),
            "options_hash": options_hash,
            "cache_hit_before_call": cache_hit_before_call,
            "pipeline_instance_sequence": stable_object_id(pipeline, pipeline_ids) if pipeline is not None else None,
            "cache_entries_after_call": len(self.initialized_pipelines),
        })
        return pipeline

    def traced_converter_convert(self, *args, **kwargs):
        result = original_converter_convert(self, *args, **kwargs)
        timings = getattr(result, "timings", {}) or {}
        serialized = {}
        for key, value in timings.items():
            times = list(getattr(value, "times", []) or [])
            serialized[key] = {
                "count": int(getattr(value, "count", len(times))),
                "seconds": [round(float(item), 6) for item in times[:32]],
                "total_seconds": round(sum(float(item) for item in times), 6),
            }
        page_record("docling_pipeline_timings", {
            "converter_instance_sequence": stable_object_id(self, converter_ids),
            "timings": serialized,
        })
        return result

    def traced_call(self, doc, element_batch):
        started = time.perf_counter()
        batch = list(element_batch)
        active = []
        for element in batch:
            item = element.item
            label = getattr(getattr(item, "label", None), "value", None)
            if label == "formula":
                index = context["region_indices_by_item_id"].get(id(item))
                if index is None:
                    index = context["next_region_index"]
                    context["next_region_index"] += 1
                active.append({"region_index": index, "label": label})
        context["active_batch_regions"] = active
        try:
            yield from original_call(self, doc, batch)
        finally:
            page_record("formula_stage_calls", {
                "formula_items": sum(
                    getattr(getattr(item.item, "label", None), "value", None) == "formula"
                    for item in batch
                ),
                "seconds": round(time.perf_counter() - started, 6),
            })
            context["active_batch_regions"] = []

    def diagnostic_vlm_engine_input(*args, **kwargs):
        return original_vlm_engine_input(
            *args,
            **generation_input_kwargs(
                kwargs, formula_cap_override=formula_cap_override
            ),
        )

    BaseItemAndImageEnrichmentModel.prepare_element = traced_prepare
    CodeFormulaVlmModel.__init__ = traced_init
    CodeFormulaVlmModel.__call__ = traced_call
    DoclingBackend.__init__ = traced_backend_init
    DoclingBackend._get_converter = traced_backend_get_converter
    DocumentConverter._get_pipeline = traced_get_pipeline
    DocumentConverter.convert = traced_converter_convert
    # Docling's own TimeRecorder exposes build/assemble/enrich subphases. This
    # only enables timing collection; it does not alter model options/results.
    settings.debug.profile_pipeline_timings = True
    if formula_cap_override is not None:
        code_formula_module.VlmEngineInput = diagnostic_vlm_engine_input
    # Load the existing benchmark preparation entry point after installing
    # wrappers. No second runner or modified prediction/evaluation path exists.
    repo_root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repo_root))
    sys.path.insert(0, str(repo_root / "src"))
    prepare_path = repo_root / "experiments/005_omnidocbench/prepare.py"
    spec = importlib.util.spec_from_file_location("omnidocbench_prepare_profiled", prepare_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load benchmark preparation entry point: {prepare_path}")
    prepare = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(prepare)
    image_to_page = {page_id.rsplit("#", 1)[0]: page_id for page_id in page_ids}
    original_process_sample = prepare._process_sample

    def traced_process_sample(image_path, *args, **kwargs):
        context["page_id"] = image_to_page.get(Path(image_path).name)
        context["next_region_index"] = 0
        context["region_indices_by_item_id"] = {}
        context["active_batch_regions"] = []
        return original_process_sample(image_path, *args, **kwargs)

    prepare._process_sample = traced_process_sample
    try:
        status = prepare.main([
            "--dataset", str(dataset), "--manifest", str(manifest),
            "--backend", "baseline", "--config", str(config),
            "--output", str(output), "--page-ids", *page_ids, "--keep-runs",
        ])
    finally:
        output.mkdir(parents=True, exist_ok=True)
        (output / "formula_profile.json").write_text(
            json.dumps(events, indent=2), encoding="utf-8"
        )
        prepare._process_sample = original_process_sample
        BaseItemAndImageEnrichmentModel.prepare_element = original_prepare
        CodeFormulaVlmModel.__init__ = original_init
        CodeFormulaVlmModel.__call__ = original_call
        DoclingBackend.__init__ = original_backend_init
        DoclingBackend._get_converter = original_backend_get_converter
        DocumentConverter._get_pipeline = original_converter_get_pipeline
        DocumentConverter.convert = original_converter_convert
        settings.debug.profile_pipeline_timings = original_profile_timings
        code_formula_module.VlmEngineInput = original_vlm_engine_input
    return status


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--page-ids", nargs="+", required=True)
    parser.add_argument(
        "--formula-cap-override",
        type=int,
        help="diagnostic-only max_new_tokens override for formula prompts",
    )
    args = parser.parse_args()
    if not args.page_ids or len(args.page_ids) > 5 or len(args.page_ids) != len(set(args.page_ids)):
        parser.error("provide 1–5 unique frozen-manifest page IDs")
    if args.formula_cap_override is not None and args.formula_cap_override <= 0:
        parser.error("formula cap override must be positive")
    return run_profile(
        args.dataset,
        args.manifest,
        args.config,
        args.output,
        args.page_ids,
        formula_cap_override=args.formula_cap_override,
    )


if __name__ == "__main__":
    raise SystemExit(main())
