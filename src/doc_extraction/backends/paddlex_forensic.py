"""Opt-in, bounded PaddleX internal timing for a single forensic run.

This module is imported only when ``DOC_EXTRACTION_PADDLEX_TRACE`` is set in
the isolated E2E worker. It records aggregate shape/count/timing data only;
never image pixels, prompts, or recognized text.
"""
from __future__ import annotations

import json
import os
import statistics
import threading
import time
from collections import Counter
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

_MAX_EVENTS = 8192
_MAX_BYTES = 2 * 1024 * 1024


class Trace:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.started = time.monotonic()
        self.events = 0
        self.bytes_written = 0
        self.current_input_name: str | None = None
        self.lock = threading.Lock()
        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0)
        self.fd = os.open(path, flags, 0o600)
        os.fchmod(self.fd, 0o600)
        self.emit("trace_started", source="opt_in_paddlex_internal_instrumentation")

    def emit(self, event: str, **fields: Any) -> None:
        with self.lock:
            if self.events >= _MAX_EVENTS or self.bytes_written >= _MAX_BYTES:
                return
            record = {
                "trace_elapsed_seconds": round(time.monotonic() - self.started, 4),
                "event": event,
            }
            if self.current_input_name is not None:
                record["input_name"] = self.current_input_name
            record.update(fields)
            encoded = (json.dumps(record, separators=(",", ":"), allow_nan=False) + "\n").encode()
            if self.bytes_written + len(encoded) > _MAX_BYTES:
                return
            try:
                os.write(self.fd, encoded)
                os.fsync(self.fd)
            except OSError:
                # Diagnostics are observational: an unavailable trace target
                # must never change model output or extraction semantics.
                self.events = _MAX_EVENTS
                return
            self.events += 1
            self.bytes_written += len(encoded)

    def close(self) -> None:
        os.close(self.fd)


def _shape(image: Any) -> dict[str, Any] | None:
    shape = getattr(image, "shape", None)
    if shape is None or len(shape) < 2:
        return None
    try:
        height, width = int(shape[0]), int(shape[1])
    except (TypeError, ValueError):
        return None
    return {"width": width, "height": height, "pixels": width * height}


def _generated_lengths(result: Any, model_inputs: Any) -> dict[str, Any]:
    """Summarize generated token counts when the model API exposes sequences.

    PaddleX postprocessing trims each prompt prefix from the returned sequence,
    so the generation tensor's final dimension minus input_ids length is the
    generated-token count. If either shape is unavailable, preserve that fact.
    """
    output_shape = getattr(result, "shape", None)
    if output_shape is None:
        output_shape = getattr(getattr(result, "sequences", None), "shape", None)
    input_ids = model_inputs.get("input_ids") if isinstance(model_inputs, dict) else None
    input_shape = getattr(input_ids, "shape", None)
    if output_shape is None or input_shape is None or len(output_shape) < 2 or len(input_shape) < 2:
        return {"generated_tokens": None, "input_tokens": None, "output_sequence_tokens": None}
    try:
        input_tokens = int(input_shape[-1])
        output_tokens = int(output_shape[-1])
    except (TypeError, ValueError):
        return {"generated_tokens": None, "input_tokens": None, "output_sequence_tokens": None}
    generated = output_tokens - input_tokens
    if generated < 0:
        return {
            "generated_tokens": None,
            "input_tokens": input_tokens,
            "output_sequence_tokens": output_tokens,
        }
    return {
        "generated_tokens": generated,
        "input_tokens": input_tokens,
        "output_sequence_tokens": output_tokens,
    }


def _experiment_cap(raw: str | None) -> int | None:
    if raw is None:
        return None
    try:
        cap = int(raw)
    except ValueError as exc:
        raise ValueError("invalid explicit PaddleX experiment max_new_tokens") from exc
    if cap not in {1024, 2048, 4096}:
        raise ValueError("PaddleX experiment max_new_tokens must be 1024, 2048, or 4096")
    return cap


def _safe_label_histogram(boxes: Any) -> dict[str, int] | None:
    if not isinstance(boxes, (list, tuple)):
        return None
    counts: Counter[str] = Counter()
    for box in boxes[:1000]:
        if isinstance(box, dict) and isinstance(box.get("label"), str):
            counts[box["label"][:64]] += 1
    return dict(sorted(counts.items())[:40])


def _result_summary(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        result = value.get("result")
        if isinstance(result, (list, tuple)):
            strings = [item for item in result if isinstance(item, str)]
            return {
                "result_type": "sequence",
                "result_count": len(result),
                "result_text_count": len(strings),
                "result_chars_total": sum(map(len, strings)),
                "result_chars_max": max(map(len, strings), default=0),
            }
        return {
            "result_type": type(result).__name__,
            "result_chars": len(result) if isinstance(result, str) else None,
        }
    raw = getattr(value, "json", None)
    try:
        raw = raw() if callable(raw) else raw
    except Exception:  # noqa: BLE001 - a diagnostic accessor must not alter inference
        raw = None
    if isinstance(raw, dict):
        data = raw.get("res", raw)
        result = data.get("result") if isinstance(data, dict) else None
        return {
            "result_type": type(result).__name__,
            "result_chars": len(result) if isinstance(result, str) else None,
        }
    result = getattr(value, "result", None)
    return {
        "result_type": type(result).__name__ if result is not None else type(value).__name__,
        "result_chars": len(result) if isinstance(result, str) else None,
    }


def _layout_result_summary(value: Any) -> dict[str, Any]:
    raw = getattr(value, "json", None)
    try:
        raw = raw() if callable(raw) else raw
    except Exception:  # noqa: BLE001 - malformed diagnostic metadata is unavailable
        raw = None
    if not isinstance(raw, dict):
        raw = value if isinstance(value, dict) else None
    data = raw.get("res", raw) if isinstance(raw, dict) else None
    boxes = data.get("boxes") if isinstance(data, dict) else None
    return {
        "region_count": len(boxes) if isinstance(boxes, list) else None,
        "labels": _safe_label_histogram(boxes),
    }


def _distribution(values: list[int]) -> dict[str, int] | None:
    if not values:
        return None
    ordered = sorted(values)
    return {
        "count": len(ordered),
        "min": ordered[0],
        "median": int(statistics.median(ordered)),
        "p95": ordered[min(len(ordered) - 1, int((len(ordered) - 1) * 0.95))],
        "max": ordered[-1],
    }


def _batch_rows(value: Any) -> list[Any] | None:
    rows = getattr(value, "instances", value)
    return rows if isinstance(rows, list) else None


def _batch_summary(value: Any) -> dict[str, Any]:
    rows = _batch_rows(value)
    if rows is None:
        return {"input_count": None, "input_shapes": None}
    shapes = [
        _shape(row.get("image")) if isinstance(row, dict) else _shape(row)
        for row in rows[:64]
    ]
    return {
        "input_count": len(rows),
        "input_shapes": shapes,
        "input_pixels": sum((shape or {}).get("pixels", 0) for shape in shapes),
    }


def _wrap_iterator(
    source: Any,
    trace: Trace,
    *,
    start_event: str,
    done_event: str,
    details: dict[str, Any],
    summarize: Callable[[Any], dict[str, Any]] | None = None,
) -> Iterator[Any]:
    started = time.monotonic()
    trace.emit(start_event, **details)

    def iterator() -> Iterator[Any]:
        count = 0
        summaries: list[dict[str, Any]] = []
        try:
            for item in source:
                count += 1
                if summarize is not None and len(summaries) < 1000:
                    summaries.append(summarize(item))
                yield item
            trace.emit(done_event, status="returned", count=count,
                       elapsed_seconds=round(time.monotonic() - started, 4),
                       outputs=summaries if summarize is not None else None)
        except BaseException as exc:
            trace.emit(done_event, status="failed", count=count,
                       error_type=type(exc).__name__,
                       elapsed_seconds=round(time.monotonic() - started, 4))
            raise

    return iterator()


def attach(pipeline_wrapper: Any, trace_path: str, profile_path: str | None = None) -> tuple[Trace, Any]:
    """Wrap observable PaddleX stage methods after normal model initialization."""
    trace = Trace(Path(trace_path))
    pipeline_wrapper_obj = pipeline_wrapper.paddlex_pipeline
    # PaddleOCR's public PaddleX pipeline delegates to an internal pipeline.
    # Attach at the object that actually owns and calls the stage methods.
    pipeline = getattr(pipeline_wrapper_obj, "_pipeline", pipeline_wrapper_obj)
    trace.emit("model_ready", pipeline_class=type(pipeline).__name__)

    original_reader = pipeline.img_reader

    def read_images(instances: Any) -> Any:
        started = time.monotonic()
        trace.emit("image_load_started", input_count=len(instances) if hasattr(instances, "__len__") else None)
        images = original_reader(instances)
        trace.emit("image_load_returned", elapsed_seconds=round(time.monotonic() - started, 4),
                   images=[_shape(image) for image in list(images)[:8]])
        return images

    pipeline.img_reader = read_images

    # The actual predictor is called through Python's special __call__ method.
    # Wrap only these two owned instances; all other model objects are untouched.
    for name, phase in (("layout_det_model", "layout_detection"),):
        model = getattr(pipeline, name, None)
        if model is None:
            trace.emit("model_stage_unavailable", stage=phase)
            continue
        cls = type(model)
        original_call = cls.__call__

        def call(instance: Any, *args: Any, __original: Any = original_call,
                 __target: Any = model, __phase: str = phase, **kwargs: Any) -> Any:
            if instance is not __target:
                return __original(instance, *args, **kwargs)
            inputs = args[0] if args else kwargs.get("input")
            details: dict[str, Any] = {"stage": __phase, "input_count": len(inputs) if hasattr(inputs, "__len__") else None}
            if isinstance(inputs, list):
                details["input_shapes"] = [
                    _shape(item.get("image") if isinstance(item, dict) else item)
                    for item in inputs[:64]
                ]
            elif inputs is not None:
                details["input_shape"] = _shape(inputs)
            trace.emit(f"{__phase}_started", **details)
            result = __original(instance, *args, **kwargs)

            def summarize_output(item: Any) -> dict[str, Any]:
                if __phase == "layout_detection":
                    return _layout_result_summary(item)
                return _result_summary(item)

            return _wrap_iterator(result, trace, start_event=f"{__phase}_iteration_started",
                                  done_event=f"{__phase}_iteration_finished", details={},
                                  summarize=summarize_output)

        # Model classes may differ. Keeping a wrapper installed on the class is
        # safe here because each worker owns a single inference request stream.
        cls.__call__ = call

    vl_model = getattr(pipeline, "vl_rec_model", None)
    if vl_model is not None:
        original_predict = vl_model.predict
        experiment_cap = _experiment_cap(os.environ.get("DOC_EXTRACTION_PADDLEX_EXPERIMENT_MAX_NEW_TOKENS"))
        trace.emit("experiment_generation_cap", max_new_tokens=experiment_cap)

        def recognize(inputs: Any, *args: Any, **kwargs: Any) -> Any:
            if experiment_cap is not None:
                kwargs["max_new_tokens"] = experiment_cap
            batch_inputs = inputs if isinstance(inputs, list) else []
            image_shapes = [
                _shape(item.get("image")) for item in batch_inputs[:64] if isinstance(item, dict)
            ]
            details = {
                "batch_index": getattr(trace, "recognition_batches_started", 0) + 1,
                "regions": len(batch_inputs) if isinstance(inputs, list) else None,
                "crop_pixels": sum((shape or {}).get("pixels", 0) for shape in image_shapes),
                "crop_shapes": image_shapes,
                "max_new_tokens": kwargs.get("max_new_tokens", "default_4096"),
                "experiment_max_new_tokens": experiment_cap,
                "pixel_bounds": [kwargs.get("min_pixels"), kwargs.get("max_pixels")],
                "internal_batch_size": getattr(getattr(vl_model, "batch_sampler", None), "batch_size", None),
            }
            trace.recognition_batches_started = details["batch_index"]
            trace.emit("recognition_batch_started", **details)
            result = original_predict(inputs, *args, **kwargs)
            return _wrap_iterator(
                result,
                trace,
                start_event="recognition_batch_iteration_started",
                done_event="recognition_batch_finished",
                details={"batch_index": details["batch_index"]},
                summarize=_result_summary,
            )

        vl_model.predict = recognize

        original_process = vl_model.process

        def process_batch(data: Any, *args: Any, **kwargs: Any) -> Any:
            batch_index = getattr(trace, "recognition_process_batches_started", 0) + 1
            trace.recognition_process_batches_started = batch_index
            trace.active_recognition_batch = batch_index
            trace.emit("recognition_process_batch_started", batch_index=batch_index,
                       max_new_tokens=kwargs.get("max_new_tokens", "unavailable"),
                       **_batch_summary(data))
            started = time.monotonic()
            try:
                result = original_process(data, *args, **kwargs)
            except BaseException as exc:
                trace.emit("recognition_process_batch_finished", batch_index=batch_index,
                           status="failed", error_type=type(exc).__name__,
                           elapsed_seconds=round(time.monotonic() - started, 4))
                raise
            trace.emit("recognition_process_batch_finished", batch_index=batch_index,
                       status="returned", elapsed_seconds=round(time.monotonic() - started, 4),
                       output=_result_summary(result))
            return result

        vl_model.process = process_batch

        for component, attribute, stage_name in (
            (getattr(vl_model, "processor", None), "preprocess", "recognition_preprocess"),
            (getattr(vl_model, "infer", None), "generate", "model_generate"),
            (getattr(vl_model, "processor", None), "postprocess", "recognition_postprocess"),
        ):
            original_stage = getattr(component, attribute, None) if component is not None else None
            if not callable(original_stage):
                trace.emit("stage_unavailable", stage=stage_name)
                continue

            def timed_stage(*args: Any, __original: Any = original_stage,
                            __name: str = stage_name, **kwargs: Any) -> Any:
                detail: dict[str, Any] = {
                    "batch_index": getattr(trace, "active_recognition_batch", None)
                }
                if __name == "recognition_preprocess" and args:
                    rows = args[0]
                    if isinstance(rows, list):
                        detail.update(_batch_summary(rows))
                trace.emit("stage_started", stage=__name, **detail)
                started = time.monotonic()
                try:
                    result = __original(*args, **kwargs)
                except BaseException as exc:
                    trace.emit("stage_finished", stage=__name, status="failed",
                               error_type=type(exc).__name__,
                               elapsed_seconds=round(time.monotonic() - started, 4))
                    raise
                summary: dict[str, Any] = {}
                if __name == "model_generate":
                    model_inputs = args[0] if args else None
                    summary.update(_generated_lengths(result, model_inputs))
                elif __name == "recognition_postprocess":
                    summary = _result_summary({"result": result})
                trace.emit("stage_finished", stage=__name, status="returned",
                           elapsed_seconds=round(time.monotonic() - started, 4), **summary)
                return result

            setattr(component, attribute, timed_stage)

    for method_name in ("_paddleocr_vl_prepare_page_serial_benchmarked", "_paddleocr_vl_prepare_page_core"):
        original = getattr(pipeline, method_name, None)
        if original is None:
            continue

        def prepare(payload: Any, __original: Any = original, __name: str = method_name) -> Any:
            try:
                _, image, detection, *_ = payload
                boxes = detection.get("boxes") if isinstance(detection, dict) else None
            except (TypeError, ValueError):
                image, boxes = None, None
            trace.emit("region_preparation_started", operation=__name,
                       image_shape=_shape(image), detected_regions=len(boxes) if isinstance(boxes, list) else None,
                       labels=_safe_label_histogram(boxes))
            started = time.monotonic()
            result = __original(payload)
            try:
                blocks = result[1]
                entries = result[2]
                shapes = [_shape(block.get("img")) for block in blocks[:2000] if isinstance(block, dict)]
                pixel_sizes = [(shape or {}).get("pixels", 0) for shape in shapes]
                labels = Counter(str(block.get("label", "unknown"))[:64]
                                 for block in blocks[:1000] if isinstance(block, dict))
                trace.emit("region_preparation_finished", operation=__name,
                           elapsed_seconds=round(time.monotonic() - started, 4),
                           crop_count=len(blocks), vlm_input_count=len(entries),
                           crop_pixels=sum(pixel_sizes), crop_pixel_distribution=_distribution(pixel_sizes),
                           crop_shapes=shapes[:20], block_labels=dict(sorted(labels.items())[:40]))
            except (TypeError, IndexError, KeyError):
                trace.emit("region_preparation_finished", operation=__name,
                           elapsed_seconds=round(time.monotonic() - started, 4), details="unavailable")
            return result

        setattr(pipeline, method_name, prepare)

    for method_name in ("_paddleocr_vl_aggregate_vlm_batches", "_paddleocr_vl_run_vl_recognition_batches",
                        "_paddleocr_vl_assemble_parsing_results"):
        original = getattr(pipeline, method_name, None)
        if original is None:
            continue

        def stage(*args: Any, __original: Any = original, __name: str = method_name, **kwargs: Any) -> Any:
            started = time.monotonic()
            trace.emit("stage_started", stage=__name)
            result = __original(*args, **kwargs)
            fields: dict[str, Any] = {}
            if __name == "_paddleocr_vl_aggregate_vlm_batches" and isinstance(result, tuple) and len(result) >= 4:
                batches = result[3]
                fields["batch_count"] = len(batches) if isinstance(batches, dict) else None
                fields["batches"] = [
                    {"pixel_key": list(key), "regions": len(value.get("images", [])),
                     "crop_pixels": sum((_shape(image) or {}).get("pixels", 0) for image in value.get("images", []))}
                    for key, value in list(batches.items())[:40]
                ] if isinstance(batches, dict) else None
            elif __name == "_paddleocr_vl_assemble_parsing_results" and isinstance(result, tuple):
                lists = result[0]
                fields["result_count"] = sum(len(row) for row in lists) if isinstance(lists, list) else None
            trace.emit("stage_finished", stage=__name, elapsed_seconds=round(time.monotonic() - started, 4), **fields)
            return result

        setattr(pipeline, method_name, stage)

    # Per-pixel-key VL batches are visible at the model predictor boundary.
    # Retain a reference to the model wrapper above: its iterator completion
    # event includes bounded result character counts, not output text.
    trace.emit("instrumentation_ready", observed_methods=[
        name for name in ("img_reader", "layout_det_model", "vl_rec_model",
                          "_paddleocr_vl_prepare_page_serial_benchmarked",
                          "_paddleocr_vl_prepare_page_core", "_paddleocr_vl_aggregate_vlm_batches",
                          "_paddleocr_vl_run_vl_recognition_batches",
                          "_paddleocr_vl_assemble_parsing_results") if hasattr(pipeline, name)
    ])

    profiler = None
    if profile_path:
        import cProfile
        profiler = cProfile.Profile()
        profiler.enable()
        stop = threading.Event()

        def snapshots() -> None:
            while not stop.wait(30):
                try:
                    profiler.dump_stats(profile_path)
                except OSError:
                    pass

        thread = threading.Thread(target=snapshots, name="paddlex-cprofile-snapshot", daemon=True)
        thread.start()
        trace.emit("cprofile_started", snapshot_interval_seconds=30)
        return trace, (profiler, stop, thread)
    return trace, profiler


def finish(trace: Trace | None, profile_state: Any) -> None:
    try:
        if profile_state is not None:
            if isinstance(profile_state, tuple):
                profiler, stop, thread = profile_state
                stop.set()
                thread.join(timeout=1)
            else:
                profiler = profile_state
            profiler.disable()
            profile_path = os.environ.get("DOC_EXTRACTION_PADDLEX_CPROFILE")
            if profile_path:
                profiler.dump_stats(profile_path)
    except (OSError, RuntimeError, ValueError):
        # A diagnostic profile must never turn an inference result into a
        # worker failure or produce a second IPC response.
        pass
    if trace is not None:
        try:
            trace.emit("worker_request_finished")
            trace.close()
        except OSError:
            pass
