"""Private protocol worker for the optional PaddleOCR-VL page backend."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import resource
import struct
import sys
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

    try:
        from paddleocr import PaddleOCRVL

        from doc_extraction.backends.paddleocr_vl_backend import page_from_paddle_result

        pipeline = PaddleOCRVL(pipeline_version="v1.6", device="gpu:0" if args.device == "cuda" else "cpu")
        from doc_extraction.backends.paddleocr_vl_backend import PaddleOCRVLBackend

        model_versions = PaddleOCRVLBackend.model_versions()
    except Exception as exc:  # noqa: BLE001 - startup failures must cross the worker protocol
        _write_message(
            protocol_fd,
            {"state": "failed", "kind": "model_load_failure", "message": type(exc).__name__},
            maximum,
        )
        return 2

    _write_message(protocol_fd, {"state": "ready", "model_versions": model_versions}, maximum)
    for raw_line in sys.stdin.buffer:
        try:
            if len(raw_line) > 64 * 1024:
                raise ValueError("request exceeds protocol limit")
            request = json.loads(raw_line)
            if not isinstance(request, dict) or request.get("op") != "predict":
                raise ValueError("unknown worker operation")
            source = Path(request["input_path"])
            expected_sha256 = request["input_sha256"]
            before_sha256 = _sha256_file(source)
            if before_sha256 != expected_sha256:
                raise ValueError("input identity changed before model execution")
            results = list(pipeline.predict(str(source)))
            if len(results) != 1:
                raise ValueError("model returned an unexpected result count")
            page = page_from_paddle_result(results[0])
            after_sha256 = _sha256_file(source)
            if after_sha256 != expected_sha256:
                raise ValueError("input identity changed during model execution")
            _write_message(
                protocol_fd,
                {
                    "state": "completed",
                    "input_sha256": after_sha256,
                    "page": page.model_dump(mode="json"),
                    "model_versions": model_versions,
                },
                maximum,
            )
        except Exception as exc:  # noqa: BLE001 - record per-request failure without leaking payloads
            kind = "invalid_model_output" if isinstance(exc, (TypeError, ValueError, KeyError)) else "model_inference_failure"
            _write_message(
                protocol_fd,
                {"state": "failed", "kind": kind, "message": type(exc).__name__},
                maximum,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
