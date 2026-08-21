"""doc_extraction CLI.

    doc_extraction run     --input <file|dir> [--config configs/cpu.yaml] [--backend baseline|docling|...]
    doc_extraction compare --input <file|dir> [--backends baseline docling]
    doc_extraction inspect [<document_id>] [--output-dir outputs]

Equivalent thin wrappers live in scripts/ for environments without `make`.
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from doc_extraction.config import PipelineConfig, load_config
from doc_extraction.ingest import dispatcher
from doc_extraction.pipelines import image as image_pipeline
from doc_extraction.pipelines import office as office_pipeline
from doc_extraction.pipelines import pdf as pdf_pipeline
from doc_extraction.pipelines.base import BackendUnavailableError
from doc_extraction.schemas.document import Document, RunMetadata
from doc_extraction.schemas.page import Page
from doc_extraction.stages.assemble import assemble_document
from doc_extraction.utils.hashing import sha256_file
from doc_extraction.utils.ids import document_id as make_document_id
from doc_extraction.utils.logging import StageLogger
from doc_extraction.utils.serde import write_json

SUPPORTED_EXTENSIONS = {"pdf", "docx", "xlsx", "pptx", "png", "jpg", "jpeg", "tif", "tiff", "bmp"}


def _discover_inputs(input_path: Path) -> list[Path]:
    if input_path.is_file():
        return [input_path]
    return sorted(
        p for p in input_path.iterdir() if p.is_file() and p.suffix.lower().lstrip(".") in SUPPORTED_EXTENSIONS
    )


_COMPONENT_BACKEND_CACHE: dict[tuple[str, tuple[str, ...]], Any] = {}


def clear_component_backend_cache() -> None:
    """Drop the cached backends (and the models they hold). For tests, and
    for any caller that changes device mid-process."""
    _COMPONENT_BACKEND_CACHE.clear()


def _get_component_backends(config: PipelineConfig):
    """Layout/OCR/table backends for the baseline pipeline's scanned-page
    route. The same Docling instance serves layout+OCR so it only converts
    each page image once (see backends/docling_backend.py).

    Cached per (device, ocr_languages) for the process lifetime. Constructing
    a backend is cheap — models load lazily on first use — but they load into
    *that instance*, so building a fresh one per file made every page pay the
    full model-load cost again. On a benchmark run that dominates everything
    else: the OmniDocBench pages are standalone images, so each one takes the
    visual route and was re-loading the Docling layout weights plus both Table
    Transformer models from disk.

    Reusing instances is safe here because the runner is sequential and these
    backends hold no per-document state (DoclingBackend's `_page_cache` is
    keyed by path). A future parallel runner must not share them across
    threads without checking that assumption again.
    """
    from doc_extraction.backends.docling_backend import DoclingBackend
    from doc_extraction.backends.table_backend import TableTransformerBackend

    key = (config.device, tuple(config.ocr_languages))
    cached = _COMPONENT_BACKEND_CACHE.get(key)
    if cached is None:
        docling = DoclingBackend(device=config.device, ocr_languages=config.ocr_languages)
        table_backend = TableTransformerBackend(device=config.device)
        cached = (docling, docling, table_backend)
        _COMPONENT_BACKEND_CACHE[key] = cached
    return cached


def build_whole_document_backend(name: str, config: PipelineConfig) -> Any:
    """Build a backend usable as an arm of `compare`.

    "baseline" is included deliberately: this repo's own modular pipeline is
    one of the systems under comparison, not a privileged reference. It is
    handled by process_file directly rather than through this factory.
    """
    if name == "docling":
        from doc_extraction.backends.docling_backend import DoclingBackend

        return DoclingBackend(device=config.device, ocr_languages=config.ocr_languages)
    if name == "mineru":
        from doc_extraction.backends.mineru_backend import MinerUBackend

        return MinerUBackend()
    if name == "paddleocr":
        from doc_extraction.backends.paddleocr_backend import PaddleOCRBackend

        return PaddleOCRBackend()
    if name == "vlm":
        from doc_extraction.backends.vlm_backend import VLMBackend

        return VLMBackend()
    raise ValueError(f"unknown backend: {name!r}")


def _package_version(dist_name: str) -> str | None:
    import importlib.metadata as importlib_metadata

    try:
        return importlib_metadata.version(dist_name)
    except Exception:  # noqa: BLE001 - absence is the normal case for optional extras
        return None


def collect_model_versions(backend_name: str) -> dict[str, str]:
    """Record the library versions that actually produced a run, so a result
    file on disk can be attributed to a specific stack later."""
    import doc_extraction

    versions: dict[str, str] = {"doc_extraction": doc_extraction.__version__}
    interesting = ["pymupdf"]
    if backend_name in ("baseline", "docling"):
        interesting += ["docling", "docling-core", "easyocr", "transformers", "torch"]
    if backend_name == "mineru":
        interesting += ["mineru"]
    if backend_name == "paddleocr":
        interesting += ["paddleocr", "paddlepaddle"]
    for dist in interesting:
        version = _package_version(dist)
        if version is not None:
            versions[dist] = version
    return versions


def _collect_page_warnings(pages: list[Page]) -> list[str]:
    """Surface per-page notes that indicate a problem to the document level,
    so `metadata.json` shows them without needing to open every page."""
    warnings: list[str] = []
    for page in pages:
        for note in page.notes:
            if note.startswith("SUSPECT") or "fallback" in note or "skipped" in note:
                warnings.append(f"page {page.index + 1}: {note}")
    return warnings


def _run_baseline_route(
    path: Path, route_decision: dispatcher.RouteDecision, config: PipelineConfig, output_dir: Path, logger: StageLogger
) -> list[Page]:
    route = route_decision.route
    kind = route_decision.file_info.detected_kind

    if route == dispatcher.ROUTE_NATIVE_OFFICE:
        if kind == "docx":
            return office_pipeline.parse_docx(path, logger)
        if kind == "xlsx":
            return office_pipeline.parse_xlsx(path, logger)
        if kind == "pptx":
            return office_pipeline.parse_pptx(path, logger)
        raise ValueError(f"unsupported native office kind: {kind}")

    if route == dispatcher.ROUTE_DIGITAL_PDF:
        # Component backends are constructed lazily and only actually used if
        # a page turns out to need the visual fallback — building them is
        # cheap (models load on first call, not on construction).
        layout_backend, ocr_backend, table_backend = _get_component_backends(config)
        return pdf_pipeline.parse_digital_pdf(
            path,
            config=config,
            output_dir=output_dir,
            layout_backend=layout_backend,
            ocr_backend=ocr_backend,
            image_table_backend=table_backend,
            logger=logger,
        )

    if route == dispatcher.ROUTE_SCANNED_PDF:
        layout_backend, ocr_backend, table_backend = _get_component_backends(config)
        return pdf_pipeline.parse_scanned_pdf(
            path, config.render_dpi, layout_backend, ocr_backend, table_backend, output_dir, logger
        )

    if route == dispatcher.ROUTE_IMAGE:
        layout_backend, ocr_backend, table_backend = _get_component_backends(config)
        return image_pipeline.parse_image(
            path, config.render_dpi, layout_backend, ocr_backend, table_backend, output_dir, logger
        )

    raise ValueError(f"unsupported file for baseline pipeline: {path.name} (kind={kind})")


def process_file(
    path: Path,
    config: PipelineConfig,
    output_root: Path | None = None,
    backend_name: str = "baseline",
    output_dir: Path | None = None,
) -> Document:
    """Run either the baseline modular pipeline or a single named
    whole-document backend over one file. Writes every stage's intermediate
    output under `output_dir` (default: `output_root/<document_id>/`).
    Never swallows an exception — metadata.json + the stage log always
    record a failure before it propagates."""
    if output_dir is None:
        if output_root is None:
            raise ValueError("process_file requires output_root or output_dir")
        file_hash = sha256_file(path)
        output_dir = output_root / make_document_id(path, file_hash)
    else:
        file_hash = sha256_file(path)

    doc_id = output_dir.name
    logger = StageLogger(doc_id, output_dir / "logs")
    start = time.perf_counter()
    route_decision = dispatcher.route(path, config)

    try:
        if backend_name == "baseline":
            pages = _run_baseline_route(path, route_decision, config, output_dir, logger)
        else:
            backend = build_whole_document_backend(backend_name, config)
            if not backend.is_available():
                raise BackendUnavailableError(
                    f"backend '{backend_name}' is not available in this environment — see docs/backends.md"
                )
            pages = backend.convert(path, config).pages

        metadata = RunMetadata(
            input_filename=path.name,
            input_path=str(path),
            file_hash_sha256=file_hash,
            file_type=route_decision.file_info.detected_kind,
            route=route_decision.route,
            pipeline=backend_name,
            backend=backend_name,
            model_versions=collect_model_versions(backend_name),
            config_snapshot=config.to_snapshot(),
            timestamp=datetime.now(timezone.utc).isoformat(),
            device=config.device,
            route_reason=route_decision.reason,
            text_profile=route_decision.text_profile.as_dict() if route_decision.text_profile else None,
            warnings=_collect_page_warnings(pages),
        )
        document = assemble_document(doc_id, metadata, pages, output_dir, logger)
        document.metadata.runtime_seconds = time.perf_counter() - start
        # assemble_document already wrote metadata.json and final/document.json
        # once, before runtime_seconds was known — rewrite both now so neither
        # copy of the metadata silently disagrees with the other.
        write_json(output_dir / "metadata.json", document.metadata)
        write_json(output_dir / "final" / "document.json", document)
        return document

    except Exception as exc:
        elapsed = time.perf_counter() - start
        metadata = RunMetadata(
            input_filename=path.name,
            input_path=str(path),
            file_hash_sha256=file_hash,
            file_type=route_decision.file_info.detected_kind,
            route=route_decision.route,
            pipeline=backend_name,
            backend=backend_name,
            config_snapshot=config.to_snapshot(),
            timestamp=datetime.now(timezone.utc).isoformat(),
            runtime_seconds=elapsed,
            device=config.device,
            errors=[f"{type(exc).__name__}: {exc}"],
            route_reason=route_decision.reason,
            text_profile=route_decision.text_profile.as_dict() if route_decision.text_profile else None,
        )
        write_json(output_dir / "metadata.json", metadata)
        logger.log_event(
            stage="run", backend=backend_name, status="failure", runtime_seconds=elapsed,
            device=config.device, error=f"{type(exc).__name__}: {exc}",
        )
        raise


def cmd_run(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    if args.input:
        config.input_dir = args.input
    if args.output:
        config.output_dir = args.output

    input_path = Path(config.input_dir).resolve()
    output_root = Path(config.output_dir).resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    files = _discover_inputs(input_path)
    if not files:
        print(f"No supported files found under {input_path}", file=sys.stderr)
        return 1

    exit_code = 0
    for path in files:
        print(f"--- {path.name} ---")
        try:
            document = process_file(path, config, output_root=output_root, backend_name=args.backend)
            n_elements = sum(len(p.elements) for p in document.pages)
            n_tables = sum(len(p.tables) for p in document.pages)
            runtime = document.metadata.runtime_seconds or 0.0
            print(
                f"  route={document.metadata.route} pages={len(document.pages)} "
                f"elements={n_elements} tables={n_tables} runtime={runtime:.2f}s "
                f"-> {output_root.name}/{document.document_id}/"
            )
            if document.metadata.warnings:
                print(f"  warnings: {document.metadata.warnings}")
        except Exception as exc:  # noqa: BLE001 - reported per-file, run continues
            exit_code = 1
            print(f"  FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
    return exit_code


def cmd_compare(args: argparse.Namespace) -> int:
    from doc_extraction.evaluation.compare import build_comparison, render_comparison_html

    config = load_config(args.config)
    input_path = Path(args.input).resolve()
    output_root = Path(config.output_dir).resolve()
    comparison_root = output_root / "comparison"

    files = _discover_inputs(input_path)
    if not files:
        print(f"No supported files found under {input_path}", file=sys.stderr)
        return 1

    exit_code = 0
    for path in files:
        # Key on the content hash as well as the name: `compare` is routinely
        # pointed at a directory where two files share a stem.
        doc_dir = comparison_root / make_document_id(path, sha256_file(path))
        documents: dict[str, Document | None] = {}
        errors: dict[str, str] = {}
        print(f"--- {path.name} ---")
        for backend_name in args.backends:
            backend_dir = doc_dir / backend_name
            try:
                documents[backend_name] = process_file(path, config, backend_name=backend_name, output_dir=backend_dir)
                print(f"  {backend_name}: ok")
            except Exception as exc:  # noqa: BLE001 - captured for the comparison summary
                documents[backend_name] = None
                errors[backend_name] = f"{type(exc).__name__}: {exc}"
                exit_code = 1
                print(f"  {backend_name}: FAILED ({errors[backend_name]})")

        comparison = build_comparison(path, documents, errors)
        write_json(doc_dir / "diff.json", comparison)
        (doc_dir / "summary.html").write_text(render_comparison_html(path, comparison), encoding="utf-8")
        print(f"  -> outputs/comparison/{doc_dir.name}/summary.html")
    return exit_code


def cmd_inspect(args: argparse.Namespace) -> int:
    from doc_extraction.evaluation.inspect_html import render_inspection_html
    from doc_extraction.schemas.document import Document as DocumentModel
    from doc_extraction.utils.serde import read_json

    output_root = Path(args.output_dir).resolve()

    if args.document_id:
        document_dirs = [output_root / args.document_id]
    else:
        document_dirs = sorted(p.parent.parent for p in output_root.rglob("final/document.json"))
        if not document_dirs:
            print(f"No processed documents found under {output_root}", file=sys.stderr)
            return 1

    exit_code = 0
    for output_dir in document_dirs:
        document_json_path = output_dir / "final" / "document.json"
        if not document_json_path.exists():
            print(f"No processed document found at {document_json_path}", file=sys.stderr)
            exit_code = 1
            continue
        document = DocumentModel.model_validate(read_json(document_json_path))
        inspection_dir = output_dir / "inspection"
        inspection_dir.mkdir(parents=True, exist_ok=True)
        index_path = inspection_dir / "index.html"
        index_path.write_text(render_inspection_html(document, inspection_dir), encoding="utf-8")
        print(f"-> {index_path}")
    return exit_code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="doc_extraction")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run the baseline pipeline (or one backend) over file(s).")
    run_parser.add_argument("--input", help="File or directory to process (default: config's input_dir).")
    run_parser.add_argument("--output", help="Output root directory (default: config's output_dir).")
    run_parser.add_argument("--config", default="configs/default.yaml", help="Path to a config YAML file.")
    run_parser.add_argument(
        "--backend", default="baseline", choices=["baseline", "docling", "mineru", "paddleocr", "vlm"]
    )
    run_parser.set_defaults(func=cmd_run)

    compare_parser = subparsers.add_parser("compare", help="Run several whole-document backends over the same inputs.")
    compare_parser.add_argument("--input", required=True, help="Directory to process.")
    compare_parser.add_argument("--config", default="configs/default.yaml")
    compare_parser.add_argument(
        "--backends",
        nargs="+",
        default=["baseline", "docling"],
        choices=["baseline", "docling", "mineru", "paddleocr", "vlm"],
        help=(
            "Whole-document systems to compare. 'baseline' is this repo's own modular "
            "pipeline (native parsing + PyMuPDF tables, with Docling/Table-Transformer "
            "components on the visual route) — it is one arm under comparison, not a "
            "privileged reference. Component backends such as table-transformer are "
            "exercised inside 'baseline' and are not standalone arms; see docs/backends.md."
        ),
    )
    compare_parser.set_defaults(func=cmd_compare)

    inspect_parser = subparsers.add_parser(
        "inspect", help="Build a human-readable HTML viewer for one document (or all of them)."
    )
    inspect_parser.add_argument(
        "document_id", nargs="?", help="Document id; omit to build an inspector for every processed document."
    )
    inspect_parser.add_argument("--output-dir", default="outputs")
    inspect_parser.set_defaults(func=cmd_inspect)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
