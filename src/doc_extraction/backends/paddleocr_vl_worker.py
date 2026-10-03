"""Private protocol worker for the optional PaddleOCR-VL page backend."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import resource
import struct
import sys
import time
from pathlib import Path
from typing import Any


def _write_message(fd: int, value: dict[str, Any], maximum: int) -> None:
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    if len(encoded) > maximum:
        encoded = json.dumps(
            {"state": "failed", "kind": "invalid_model_output", "message": "bounded result exceeded IPC limit"},
            separators=(",", ":"),
        ).encode("utf-8")
    packet = struct.pack(">I", len(encoded)) + encoded
    offset = 0
    while offset < len(packet):
        offset += os.write(fd, packet[offset:])


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _set_file_size_limit() -> None:
    limit = int(os.environ["DOC_EXTRACTION_WORKER_FILE_LIMIT"])
    resource.setrlimit(resource.RLIMIT_FSIZE, (limit, limit))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", choices=("cpu", "cuda"), required=True)
    args = parser.parse_args()

    protocol_fd = os.dup(sys.stdout.fileno())
    maximum = int(os.environ.get("DOC_EXTRACTION_WORKER_MESSAGE_LIMIT", str(16 * 1024 * 1024)))
    devnull = os.open(os.devnull, os.O_WRONLY)
    os.dup2(devnull, 1)
    os.dup2(devnull, 2)
    os.close(devnull)
    _set_file_size_limit()

    forensic_trace = None
    forensic_profile = None
    try:
        model_import_started = time.perf_counter()
        from paddleocr import PaddleOCRVL

        from doc_extraction.backends.paddleocr_vl_backend import page_from_paddle_result

        pipeline = PaddleOCRVL(pipeline_version="v1.6", device="gpu:0" if args.device == "cuda" else "cpu")
        model_initialization_seconds = time.perf_counter() - model_import_started
        from doc_extraction.backends.paddleocr_vl_backend import PaddleOCRVLBackend

        attestation_started = time.perf_counter()
        model_versions = PaddleOCRVLBackend.model_versions()
        model_weight_attestation_seconds = time.perf_counter() - attestation_started
        forensic_path = os.environ.get("DOC_EXTRACTION_PADDLEX_TRACE")
        if forensic_path:
            from doc_extraction.backends.paddlex_forensic import attach

            forensic_trace, forensic_profile = attach(
                pipeline,
                forensic_path,
                os.environ.get("DOC_EXTRACTION_PADDLEX_CPROFILE"),
            )
    except Exception as exc:  # noqa: BLE001 - startup failures must cross the worker protocol
        _write_message(
            protocol_fd,
            {"state": "failed", "kind": "model_load_failure", "message": type(exc).__name__},
            maximum,
        )
        return 2

    _write_message(
        protocol_fd,
        {
            "state": "ready",
            "model_versions": model_versions,
            "model_initialization_seconds": model_initialization_seconds,
            "model_weight_attestation_seconds": model_weight_attestation_seconds,
        },
        maximum,
    )
    for raw_line in sys.stdin.buffer:
        try:
            if len(raw_line) > 64 * 1024:
                raise ValueError("request exceeds protocol limit")
            request = json.loads(raw_line)
            if not isinstance(request, dict) or request.get("op") != "predict":
                raise ValueError("unknown worker operation")
            source = Path(request["input_path"])
            expected_sha256 = request["input_sha256"]
            if forensic_trace is not None:
                forensic_trace.emit("page_request_started", input_name=source.name)
            input_hash_started = time.perf_counter()
            before_sha256 = _sha256_file(source)
            if before_sha256 != expected_sha256:
                raise ValueError("input identity changed before model execution")
            input_hash_seconds = time.perf_counter() - input_hash_started
            predict_started = time.perf_counter()
            results = list(pipeline.predict(str(source)))
            pipeline_predict_seconds = time.perf_counter() - predict_started
            if forensic_trace is not None:
                forensic_trace.emit("pipeline_predict_returned", elapsed_seconds=round(pipeline_predict_seconds, 4),
                                    result_count=len(results))
            if len(results) != 1:
                raise ValueError("model returned an unexpected result count")
            phase_timings = {
                "input_hash_seconds": input_hash_seconds,
                # Public PaddleOCR-VL predict() bundles its internal image
                # preprocessing, inference, and result generation. Do not
                # report unsupported subdivisions as measured phases.
                "pipeline_predict_seconds": pipeline_predict_seconds,
            }
            page = page_from_paddle_result(results[0], phase_timings)
            after_hash_started = time.perf_counter()
            after_sha256 = _sha256_file(source)
            if after_sha256 != expected_sha256:
                raise ValueError("input identity changed during model execution")
            phase_timings["input_hash_seconds"] += time.perf_counter() - after_hash_started
            page_serialization_started = time.perf_counter()
            page_payload = page.model_dump(mode="json")
            phase_timings["canonical_page_serialization_seconds"] = (
                time.perf_counter() - page_serialization_started
            )
            phase_timings["worker_accounted_seconds"] = sum(
                value for key, value in phase_timings.items()
                if key.endswith("_seconds") and key != "canonical_mapping_inclusive_seconds"
            )
            _write_message(
                protocol_fd,
                {
                    "state": "completed",
                    "input_sha256": after_sha256,
                    "page": page_payload,
                    "model_versions": model_versions,
                    "phase_timings": phase_timings,
                },
                maximum,
            )
            if forensic_trace is not None:
                from doc_extraction.backends.paddlex_forensic import finish

                finish(forensic_trace, forensic_profile)
                forensic_trace = None
                forensic_profile = None
        except Exception as exc:  # noqa: BLE001 - record per-request failure without leaking payloads
            kind = "invalid_model_output" if isinstance(exc, (TypeError, ValueError, KeyError)) else "model_inference_failure"
            if forensic_trace is not None:
                from doc_extraction.backends.paddlex_forensic import finish

                finish(forensic_trace, forensic_profile)
                forensic_trace = None
                forensic_profile = None
            _write_message(
                protocol_fd,
                {"state": "failed", "kind": kind, "message": type(exc).__name__},
                maximum,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
