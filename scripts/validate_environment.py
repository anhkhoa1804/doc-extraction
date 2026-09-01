#!/usr/bin/env python
"""Check that this machine can actually run the project, and say what it can't.

The problem this solves: the pipeline's failure modes at first run are mostly
*environmental*, and several of them look alike from the outside. A CPU-only
torch build on an idle GPU, a GPU that is busy, and a machine with no GPU all
surface as `torch.cuda.is_available() == False`. A missing OCR language pack
and a missing model cache both surface as `FileNotFoundError`. Guessing
between them wastes more time than checking.

So this reports each capability separately, with the specific remedy for the
specific failure. It is deliberately cheap — no model is loaded, no CUDA
context is created, no document is processed — so it is safe to run on a
shared machine at any time, including while another project is using the GPU.

    python scripts/validate_environment.py
    python scripts/validate_environment.py --json env.json

Exit code is 0 unless something *required* is broken; optional backends being
absent is reported, not failed, because the project is designed to run
without them.
"""
from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

OK, WARN, FAIL = "ok", "warn", "fail"
_MARK = {OK: "PASS", WARN: "WARN", FAIL: "FAIL"}


class Report:
    def __init__(self) -> None:
        self.checks: list[dict[str, Any]] = []

    def add(self, name: str, status: str, detail: str, remedy: str | None = None,
            required: bool = True, **extra: Any) -> None:
        self.checks.append({
            "check": name, "status": status, "detail": detail,
            "remedy": remedy, "required": required, **extra,
        })

    @property
    def failed_required(self) -> list[dict[str, Any]]:
        return [c for c in self.checks if c["status"] == FAIL and c["required"]]


def check_python(report: Report) -> None:
    v = sys.version_info
    detail = f"{platform.python_version()} ({platform.python_implementation()})"
    if (v.major, v.minor) >= (3, 10):
        report.add("python", OK, detail, version=platform.python_version())
    else:
        report.add("python", FAIL, detail, remedy="requires-python is >=3.10; use uv to install 3.12")


def check_platform(report: Report) -> None:
    report.add("platform", OK, f"{platform.system()} {platform.release()}",
               required=False, machine=platform.machine())


def check_imports(report: Report) -> None:
    """Core dependencies must import; optional extras are reported, not failed."""
    core = [("yaml", "pyyaml"), ("pydantic", "pydantic"), ("pymupdf", "pymupdf"),
            ("docx", "python-docx"), ("openpyxl", "openpyxl"), ("pptx", "python-pptx"),
            ("PIL", "pillow")]
    optional = [("docling", "docling"), ("easyocr", "easyocr"),
                ("transformers", "transformers"), ("torch", "torch"), ("timm", "timm")]

    for module, dist in core:
        try:
            importlib.import_module(module)
            report.add(f"import:{dist}", OK, _version(dist) or "installed")
        except Exception as exc:  # noqa: BLE001
            report.add(f"import:{dist}", FAIL, f"{type(exc).__name__}: {exc}",
                       remedy='pip install -e "."')

    for module, dist in optional:
        try:
            importlib.import_module(module)
            report.add(f"import:{dist}", OK, _version(dist) or "installed", required=False)
        except Exception:  # noqa: BLE001
            report.add(f"import:{dist}", WARN, "not installed", required=False,
                       remedy='pip install -e ".[docling,tables]" for the visual/OCR route')


def _version(dist: str) -> str | None:
    import importlib.metadata as md
    try:
        return md.version(dist)
    except Exception:  # noqa: BLE001
        return None


def check_package(report: Report) -> None:
    try:
        import doc_extraction
        from doc_extraction.schemas.version import SCHEMA_VERSION
        report.add("doc_extraction", OK,
                   f"{doc_extraction.__version__} (IR schema {SCHEMA_VERSION})",
                   schema_version=SCHEMA_VERSION)
    except Exception as exc:  # noqa: BLE001
        report.add("doc_extraction", FAIL, f"{type(exc).__name__}: {exc}",
                   remedy='pip install -e "." from the repository root')


def check_gpu(report: Report) -> None:
    """Separate three things that all look like "no GPU" from one boolean."""
    try:
        from doc_extraction.utils.resources import classify_gpu, query_gpu, torch_cuda_usable
    except Exception as exc:  # noqa: BLE001
        report.add("gpu", WARN, f"resource module unavailable: {exc}", required=False)
        return

    usable, torch_reason = torch_cuda_usable()
    state = query_gpu()

    if not state.available:
        report.add("gpu:device", WARN, "no GPU visible to nvidia-smi", required=False,
                   remedy="CPU execution is fully supported; this is not an error")
    else:
        classification, reason = classify_gpu(state)
        status = OK if classification in ("clear", "limited") else WARN
        report.add("gpu:device", status,
                   f"{state.name} — {state.free_mib} MiB free of {state.total_mib} MiB, "
                   f"{state.utilization_pct}% util → {classification}",
                   required=False, gpu_state=classification, reason=reason,
                   co_tenants=[{"pid": p.pid, "used_mib": p.used_mib} for p in state.processes])

    if usable:
        report.add("gpu:torch", OK, torch_reason, required=False)
    else:
        remedy = None
        if "CPU-only build" in torch_reason:
            remedy = ("this is a torch *build* limitation, not a missing GPU — reinstall with "
                      "--index-url https://download.pytorch.org/whl/cu128")
        report.add("gpu:torch", WARN, torch_reason, required=False, remedy=remedy)


def check_model_cache(report: Report) -> None:
    """Docling disables auto-download once DOCLING_ARTIFACTS_PATH is set, so an
    empty cache is a hard failure at first use rather than a slow first run."""
    from doc_extraction.config import DEFAULT_CACHE_DIR

    docling_dir = DEFAULT_CACHE_DIR / "docling"
    easyocr_dir = docling_dir / "EasyOcr"
    if not docling_dir.is_dir() or not any(docling_dir.iterdir()):
        report.add("models:docling", WARN, f"{docling_dir} is empty", required=False,
                   remedy="make models  (~1.5 GB; required before the visual/OCR route runs)")
        return

    size_mb = sum(f.stat().st_size for f in docling_dir.rglob("*") if f.is_file()) / 2**20
    langs = sorted(p.stem for p in easyocr_dir.glob("*.pth")) if easyocr_dir.is_dir() else []
    report.add("models:docling", OK, f"{size_mb:.0f} MB cached", required=False,
               easyocr_models=langs)

    if easyocr_dir.is_dir() and not langs:
        report.add("models:easyocr", WARN, "no EasyOCR weights cached", required=False,
                   remedy="make models")
    elif langs:
        report.add("models:easyocr", OK, ", ".join(langs), required=False,
                   note="a language in ocr_languages with no matching model here fails at run time")


def check_docker(report: Report) -> None:
    exe = shutil.which("docker")
    if exe is None:
        report.add("docker", WARN, "docker not installed", required=False)
        return
    try:
        proc = subprocess.run([exe, "info", "--format", "{{.ServerVersion}}"],
                              capture_output=True, text=True, timeout=15, check=False)
    except (subprocess.TimeoutExpired, OSError) as exc:
        report.add("docker", WARN, f"docker present but not reachable: {exc}", required=False)
        return
    if proc.returncode == 0:
        report.add("docker", OK, f"daemon reachable (server {proc.stdout.strip()})", required=False)
    else:
        report.add("docker", WARN, "daemon not reachable by this user", required=False,
                   remedy="use sudo, or add the user to the docker group (a host-level change)")


def check_data_corpus(report: Report) -> None:
    """The corpus is private and legitimately absent on most machines."""
    data_dir = REPO_ROOT / "data"
    docs = [p for p in data_dir.iterdir()
            if p.is_file() and p.suffix.lower().lstrip(".") in {"pdf", "docx", "xlsx", "pptx"}] \
        if data_dir.is_dir() else []
    if docs:
        report.add("data:corpus", OK, f"{len(docs)} local document(s)", required=False)
    else:
        report.add("data:corpus", WARN, "no local documents (expected on a clean checkout)",
                   required=False,
                   remedy="corpus-dependent tests will skip; see data/README.md")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--json", default=None, help="Also write the full report here.")
    args = parser.parse_args(argv)

    report = Report()
    for check in (check_python, check_platform, check_package, check_imports,
                  check_gpu, check_model_cache, check_docker, check_data_corpus):
        try:
            check(report)
        except Exception as exc:  # noqa: BLE001 - a broken check must not hide the others
            report.add(check.__name__, FAIL, f"check itself raised {type(exc).__name__}: {exc}")

    width = max(len(c["check"]) for c in report.checks) + 2
    print(f"doc-extraction environment  —  {REPO_ROOT}\n")
    for c in report.checks:
        print(f"  [{_MARK[c['status']]}] {c['check']:<{width}} {c['detail']}")
        if c.get("remedy") and c["status"] != OK:
            print(f"         {'':<{width}} -> {c['remedy']}")

    failed = report.failed_required
    warned = [c for c in report.checks if c["status"] == WARN]
    print()
    if failed:
        print(f"{len(failed)} required check(s) FAILED — the pipeline will not run correctly.")
    else:
        print("All required checks passed."
              + (f" {len(warned)} optional capability/capabilities unavailable." if warned else ""))

    if args.json:
        out = Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"repo_root": str(REPO_ROOT), "checks": report.checks}, indent=2),
                       encoding="utf-8")
        print(f"-> {out}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
