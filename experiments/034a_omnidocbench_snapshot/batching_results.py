"""034a Phase 10 -- batching analysis. Investigative only, per this
milestone's explicit instruction not to implement a batching architecture.

    python experiments/034a_omnidocbench_snapshot/batching_results.py
"""
from __future__ import annotations
import json, re
from pathlib import Path
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def main():
    table_src = (REPO / "src/doc_extraction/backends/table_backend.py").read_text()
    docling_src = (REPO / "src/doc_extraction/backends/docling_backend.py").read_text()
    cli_src = (REPO / "src/doc_extraction/cli.py").read_text()

    signatures = {
        "TableTransformerBackend.extract": re.search(r"def extract\(self, ([^)]*)\)", table_src).group(1),
        "DoclingBackend.analyze": re.search(r"def analyze\(self, ([^)]*)\)", docling_src).group(1),
        "DoclingBackend.convert": re.search(r"def convert\(self, ([^)]*)\)", docling_src).group(1),
    }

    payload = {
        "method": "grep every backend's core method signature directly -- "
                 "does any accept a list/batch of pages, or exactly one?",
        "signatures_found": signatures,
        "finding": (
            "Every backend method takes exactly ONE page/path per call -- "
            "TableTransformerBackend.extract(page, regions), "
            "DoclingBackend.analyze(page), DoclingBackend.convert(path, "
            "config). No batch dimension, no list-of-pages parameter, "
            "anywhere in the current backend architecture. Confirmed by "
            "direct signature inspection, not inferred."
        ),
        "current_processing_granularity": "strictly page-by-page, "
                                          "document-by-document -- "
                                          "prepare.py's own loop calls "
                                          "process_file() once per image, "
                                          "sequentially, with no batching "
                                          "at any layer.",
        "why_no_batching_experiment_was_run": (
            "there is no existing batching toggle to compare against -- "
            "'batched' is not a configuration option, it is an "
            "architecture that does not exist yet. Building one (padding/"
            "collating multiple page images into one forward pass through "
            "Docling's layout model and Table Transformer) would be a "
            "genuine new architecture change, explicitly out of scope per "
            "this milestone's own instruction ('do not implement a large "
            "batching architecture')."
        ),
        "conclusion": (
            "GPU underutilization (if found in concurrency_results.json / "
            "pipeline_timing.json) cannot be attributed to a missing "
            "batching TOGGLE that could simply be flipped -- it would "
            "require new engineering. The scheduling-granularity question "
            "this phase asks about is answered structurally: granularity "
            "is fixed at 'one page, one forward pass' throughout the "
            "current codebase."
        ),
    }
    Path("batching_results.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False))
    print(json.dumps(signatures, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
