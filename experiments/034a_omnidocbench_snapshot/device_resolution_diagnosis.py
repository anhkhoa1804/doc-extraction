"""034a (interrupt) Phase 1/2 -- diagnose the device-resolution gap found
by the smoke test, and classify every process_file() caller in the repo.

Read-only: greps/inspects source, does not modify anything.

    python experiments/034a_omnidocbench_snapshot/device_resolution_diagnosis.py
"""
from __future__ import annotations
import json, re, subprocess
from pathlib import Path
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def grep(pattern, path, extra=()):
    cmd = ["grep", "-n", pattern, str(REPO / path), *extra]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.stdout.strip()


CALLERS = [
    {"file": "src/doc_extraction/cli.py", "line": 360, "site": "cmd_run",
     "kind": "CLI dispatch", "protected": True,
     "why": "resolve_device(config) called at cli.py:339, BEFORE this call -- config.device is already concrete."},
    {"file": "src/doc_extraction/cli.py", "line": 406, "site": "cmd_compare",
     "kind": "CLI dispatch", "protected": True,
     "why": "resolve_device(config) called at cli.py:383, BEFORE this call."},
    {"file": "research/production_corpus/run_benchmark.py", "line": 205, "site": "module-level run loop",
     "kind": "research/production-adjacent benchmark (Layer-1 scorer's own document producer, "
            "cited by docs/production-contract.md's Capabilities table)",
     "protected": True,
     "why": "its own configure() helper (line 137-141) calls resolve_device(config) explicitly "
           "before process_file() is ever invoked -- an established, correct convention, not "
           "an accident."},
    {"file": "research/hardcases/run_benchmark.py", "line": 147, "site": "module-level run loop",
     "kind": "research/production-adjacent benchmark (source of production-contract.md's "
            "hardcase capability claims)",
     "protected": True,
     "why": "same configure()-calls-resolve_device() convention (line 125), confirmed by direct read."},
    {"file": "experiments/015_scan_recovery/run_production_recovery.py", "line": 91, "site": "main",
     "kind": "experiment (named production-adjacent)", "protected": "LIKELY (uses --device with an "
            "explicit default of \"cuda\", never \"auto\"; not exhaustively traced further this milestone)",
     "why": "CLI flag default is device=\"cuda\" (literal), not \"auto\" -- the bug requires the literal "
           "string \"auto\" to reach process_file(); a literal cuda/cpu never triggers it regardless of "
           "whether resolve_device() ran."},
    {"file": "tests/test_determinism.py", "line": 49, "site": "test_process_file_is_deterministic (or similar)",
     "kind": "production test suite", "protected": True,
     "why": "hardcodes PipelineConfig(device=\"cpu\") explicitly (line 46) -- never \"auto\"."},
    {"file": "experiments/023_evidence_centric/run_ab.py", "line": 320, "kind": "research experiment",
     "protected": True, "why": "no resolve_device call found, AND no \"auto\" default found -- this script "
                              "never constructs a config with device=\"auto\" in the first place."},
    {"file": "experiments/018_bottleneck_discovery/run_order_recovery_hardcases.py", "line": 74,
     "kind": "research experiment", "protected": True, "why": "same as above -- never uses \"auto\"."},
    {"file": "experiments/018_bottleneck_discovery/run_order_recovery.py", "line": 91,
     "kind": "research experiment", "protected": True, "why": "same."},
    {"file": "experiments/024_ocr_fidelity_recovery/scan_cohort_realscan_probe.py", "line": 101,
     "kind": "research experiment", "protected": True, "why": "same."},
    {"file": "experiments/016_scan_failure_boundary/forensics.py", "line": 171,
     "kind": "research experiment", "protected": True, "why": "same."},
    {"file": "experiments/024_ocr_fidelity_recovery/scan_cohort_ab.py", "line": 242,
     "kind": "research experiment", "protected": True, "why": "same."},
    {"file": "experiments/024_ocr_fidelity_recovery/line5_adaptive_ab.py", "line": 245,
     "kind": "research experiment", "protected": True, "why": "same."},
    {"file": "experiments/025_layout_evidence_recall/coverage_instrument.py", "line": 148,
     "kind": "research experiment", "protected": True, "why": "same."},
    {"file": "experiments/025_layout_evidence_recall/intervention_ab.py", "line": 172,
     "kind": "research experiment", "protected": True, "why": "same."},
    {"file": "experiments/015_scan_recovery/run_scan_recovery.py", "line": 95,
     "kind": "research experiment", "protected": True, "why": "same."},
    {"file": "experiments/005_omnidocbench/prepare.py", "line": 44, "site": "_process_sample",
     "kind": "BENCHMARK caller (this milestone)", "protected": False,
     "why": "THE VULNERABLE CALLER. run.py's config default is configs/cpu.yaml (device=\"cpu\" literal) "
           "-- also never \"auto\" BY DEFAULT. This milestone is the FIRST caller in this repository's "
           "entire history to deliberately pass device=\"auto\" through this path (chosen because "
           "docs/production-contract.md describes \"auto\" as the correct resource-aware production "
           "posture on a shared machine), which is exactly what exposed the gap."},
]


def main():
    cli_src = (REPO / "src/doc_extraction/cli.py").read_text()
    table_src = (REPO / "src/doc_extraction/backends/table_backend.py").read_text()
    config_src = (REPO / "src/doc_extraction/config.py").read_text()

    # verify claims directly against source rather than asserting from memory
    resolve_device_def_line = next(i for i, l in enumerate(cli_src.splitlines(), 1) if l.startswith("def resolve_device"))
    process_file_def_line = next(i for i, l in enumerate(cli_src.splitlines(), 1) if l.startswith("def process_file"))
    resolve_device_calls = [i for i, l in enumerate(cli_src.splitlines(), 1) if "resolve_device(config)" in l and not l.strip().startswith("def")]
    process_file_body_end = process_file_def_line + 90  # generous bound
    process_file_body = "\n".join(cli_src.splitlines()[process_file_def_line - 1:process_file_body_end])
    process_file_calls_resolve = "resolve_device(" in process_file_body

    device_field_doc = [l.strip() for l in config_src.splitlines() if '"auto"' in l or "auto" in l.lower()][:3]

    to_device_lines = [i for i, l in enumerate(table_src.splitlines(), 1) if ".to(self.device)" in l or ".to(device)" in l]

    cache_docstring_present = "must not share them across\n    threads" in "\n".join(
        l.strip() for l in cli_src.splitlines()
    ) or "must not share them across" in cli_src

    payload = {
        "call_graph": {
            "cli_command_path": (
                "CLI: `doc_extraction run/compare` -> argparse main() -> cmd_run/cmd_compare "
                f"-> resolve_device(config) [cli.py:{resolve_device_def_line}, called at line(s) "
                f"{resolve_device_calls}] -> process_file(config) [config.device already concrete] "
                "-> _get_component_backends/build_whole_document_backend -> TableTransformerBackend(device=config.device)"
            ),
            "library_caller_path": (
                f"library caller (e.g. experiments/005_omnidocbench/prepare.py) -> process_file(config) "
                f"directly [cli.py:{process_file_def_line}, verified this function's body does NOT call "
                f"resolve_device: {not process_file_calls_resolve}] -> backend construction with WHATEVER "
                "config.device currently is -> if the caller set device=\"auto\" and never called "
                "resolve_device() itself, the literal string \"auto\" reaches "
                "TableTransformerBackend(device=\"auto\") -> .to(\"auto\") -> RuntimeError"
            ),
        },
        "exact_source_locations": {
            "resolve_device_definition": f"src/doc_extraction/cli.py:{resolve_device_def_line}",
            "resolve_device_call_sites": [f"src/doc_extraction/cli.py:{ln}" for ln in resolve_device_calls],
            "process_file_definition": f"src/doc_extraction/cli.py:{process_file_def_line}",
            "process_file_calls_resolve_device": process_file_calls_resolve,
            "table_backend_to_device_calls": [f"src/doc_extraction/backends/table_backend.py:{ln}" for ln in to_device_lines],
            "config_device_field_doc": f"src/doc_extraction/config.py (PipelineConfig.device): {device_field_doc}",
        },
        "failure_condition": (
            "A caller constructs or loads a PipelineConfig with device==\"auto\" and calls "
            "process_file(path, config, ...) WITHOUT first calling resolve_device(config) itself. "
            "process_file() passes config.device verbatim into backend constructors "
            "(_get_component_backends -> TableTransformerBackend(device=config.device), "
            "DoclingBackend(device=config.device)). TableTransformerBackend crashes immediately "
            "(.to(\"auto\") is not a valid torch device string). DoclingBackend does NOT crash on "
            "\"auto\" (confirmed empirically this milestone: layout+ocr stages succeeded in the smoke "
            "test log, only the table stage failed) -- Docling's own device handling appears to "
            "tolerate or ignore an unrecognized string rather than raising, which is a SEPARATE, "
            "smaller finding (Docling silently not-erroring on a bad device string is arguably its own "
            "minor correctness gap, out of scope to fix here)."
        ),
        "why_cli_and_library_paths_differ": (
            "resolve_device() is a manual step every caller must remember to invoke -- it is not "
            "enforced by process_file()'s own signature or body. The CLI's cmd_run/cmd_compare, and "
            "the two production-adjacent research benchmarks (production_corpus/run_benchmark.py, "
            "hardcases/run_benchmark.py), all independently established the convention of calling it "
            "themselves before process_file(). Every OTHER historical caller never needed to, because "
            "none of them ever constructed a config with device==\"auto\" in the first place -- "
            "configs/cpu.yaml and configs/default.yaml (the only historically-used config files) both "
            "hardcode device: \"cpu\" literally. This milestone is the first to deliberately request "
            "\"auto\" through prepare.py's direct process_file() call, which is exactly why this gap "
            "was never discovered before Milestone 034a."
        ),
        "correct_fix_boundary": {
            "chosen": "process_file() itself, guarded",
            "why_not_elsewhere": (
                "NOT configuration normalization (e.g. resolving 'auto' at PipelineConfig construction/"
                "load_config() time) -- 'auto' is EXPLICITLY documented (config.py) as meaning "
                "'inspect the GPU's CURRENT state', which is only meaningful right before use, not at "
                "config-load time (a config can be loaded long before a run starts). NOT backend "
                "construction (_get_component_backends/build_whole_document_backend) -- would require "
                "duplicating the resolve-or-skip guard in every backend-construction call site "
                "(_get_component_backends AND build_whole_document_backend AND any future one), "
                "violating 'prefer one centralized resolution boundary, not duplicated logic'. "
                "process_file() is the SINGLE function every caller (CLI and library) already goes "
                "through before any backend is touched -- the correct, minimal, centralized boundary."
            ),
            "exact_guard": "if config.device == \"auto\": config = resolve_device(config)  "
                          "-- placed at the top of process_file(), before route_decision/backend "
                          "construction. Guarded (not an unconditional call) specifically to avoid "
                          "double-invoking resolve_device() for callers that already resolved it "
                          "themselves (cmd_run/cmd_compare/the two research benchmarks) -- an "
                          "unconditional call would be idempotent for config.device's VALUE (select_device "
                          "returns the already-concrete value unchanged) but would CLOBBER the "
                          "process-global _DEVICE_DECISION metadata (overwriting a rich "
                          "state=clear/limited/protected+gpu-stats decision with a bland "
                          "state='not_probed' one), a real metadata-quality regression for every "
                          "existing protected caller.",
        },
        "concurrency_relevant_finding": (
            "src/doc_extraction/cli.py's _get_component_backends() docstring explicitly states: "
            "'the runner is sequential and these backends hold no per-document state... A future "
            "parallel runner must not share them across threads without checking that assumption "
            "again.' Backends are cached in a MODULE-LEVEL dict (_COMPONENT_BACKEND_CACHE) keyed by "
            "(device, ocr_languages, ocr_backend) for the PROCESS lifetime -- safe across separate OS "
            "processes (each gets its own cache/module state) but explicitly NOT asserted safe across "
            "threads within one process. This governs how the later concurrency experiment (Phase 7-9) "
            "must be structured: separate processes, not threads."
        ),
        "caller_classification": CALLERS,
        "summary_counts": {
            "total_callers_found": len(CALLERS),
            "protected_already": sum(1 for c in CALLERS if c["protected"] is True),
            "vulnerable": sum(1 for c in CALLERS if c["protected"] is False),
            "likely_protected_not_exhaustively_traced": sum(1 for c in CALLERS if c["protected"] not in (True, False)),
        },
        "phase_2_classification": "REAL PRODUCTION INFRASTRUCTURE BUG -- process_file() is a genuine, "
                                  "actively-used library entry point (the CLI's own cmd_run/cmd_compare "
                                  "are thin wrappers around it; two production-adjacent research "
                                  "benchmarks that back docs/production-contract.md's own capability "
                                  "claims call it directly), and PipelineConfig.device=\"auto\" is a "
                                  "documented, first-class, supported value (config.py's own docstring) "
                                  "-- but process_file() silently assumes the value it receives is "
                                  "already concrete, with no validation and no docstring warning. The "
                                  "blast radius has been LATENT/ZERO in practice (every historical "
                                  "caller either avoided \"auto\" entirely or resolved it themselves by "
                                  "convention), not something that has caused a past production incident "
                                  "-- both facts are true simultaneously and neither should be overstated.",
    }
    # Phase 3/4: the fix actually applied (working tree only, not committed
    # separately from this milestone's own commit -- see FINAL_REPORT for
    # whether it should become its own production commit).
    cli_diff = subprocess.run(["git", "diff", "src/doc_extraction/cli.py"],
                              cwd=REPO, capture_output=True, text=True).stdout
    test_result = subprocess.run(
        ["/home/leanhkhoa150204/.venvs/doc-extraction-linux312/bin/python3", "-m", "pytest",
         "-q", "tests/test_cli_device_resolution.py"],
        cwd=REPO, capture_output=True, text=True,
    )
    full_suite = subprocess.run(
        ["/home/leanhkhoa150204/.venvs/doc-extraction-linux312/bin/python3", "-m", "pytest", "-q"],
        cwd=REPO, capture_output=True, text=True,
    )
    payload["phase_3_minimal_fix"] = {
        "file": "src/doc_extraction/cli.py",
        "function": "process_file (line 246)",
        "diff": cli_diff,
        "invariant_established": "every backend constructed downstream of process_file() receives a "
                                "concrete resolved device string, never the literal \"auto\" -- "
                                "REGARDLESS of whether the caller went through the CLI (cmd_run/"
                                "cmd_compare, which already resolved it) or called process_file() "
                                "directly as a library function (which previously did not).",
        "why_minimal": "1 guarded call (2 lines of logic + docstring), reuses the EXISTING "
                      "resolve_device() function verbatim -- no new resolution logic, no "
                      "duplication across the multiple backend-construction call sites "
                      "(_get_component_backends, build_whole_document_backend).",
        "regression_surface": "process_file() is called by 17 known sites (caller_classification "
                             "above). For the 15 already-protected callers, config.device is already "
                             "concrete when process_file() runs, so the guard condition "
                             "(config.device == \"auto\") is False and this is a strict no-op -- "
                             "zero behavior change. For the 1 vulnerable caller (this milestone's "
                             "own prepare.py) and any future caller passing \"auto\" directly, this "
                             "is the fix. No other code path is touched.",
        "not_committed_separately": "left in the working tree as part of this milestone's changes; "
                                    "FINAL_REPORT.md's production recommendation states explicitly "
                                    "whether this should become its OWN standalone production commit "
                                    "(Phase 18's instruction) rather than being silently folded into "
                                    "a benchmark-snapshot commit.",
    }
    payload["phase_4_regression_test"] = {
        "file": "tests/test_cli_device_resolution.py (new)",
        "tests": [
            "test_process_file_resolves_auto_device_before_any_backend_is_touched -- THE core "
            "regression test; confirmed to FAIL without the fix (git-stash-verified this milestone: "
            "AssertionError: assert 'auto' == 'cpu') and PASS with it",
            "test_process_file_does_not_reprobe_an_already_resolved_device -- guards against a "
            "naive unconditional-call fix that would clobber already-resolved _DEVICE_DECISION "
            "metadata for protected callers",
            "test_process_file_honours_an_explicit_device_verbatim[cpu/cuda] -- confirms the "
            "existing 'explicit device is never overridden or probed' contract "
            "(tests/test_resources.py) still holds through process_file(), not just select_device() "
            "in isolation",
        ],
        "falsification_performed": "git stash push -- src/doc_extraction/cli.py; ran the core test "
                                   "(FAILED as expected: assert 'auto' == 'cpu'); git stash pop "
                                   "(restored the fix); re-ran (PASSED) -- proves this is a genuine "
                                   "regression test, not a tautology.",
        "new_test_suite_result": test_result.stdout.strip().splitlines()[-1] if test_result.stdout.strip() else test_result.stderr.strip(),
        "full_suite_result": full_suite.stdout.strip().splitlines()[-1] if full_suite.stdout.strip() else full_suite.stderr.strip(),
        "baseline_was": "341 passed, 10 skipped",
    }

    Path("device_resolution_diagnosis.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False))
    print(f"resolve_device defined at line {resolve_device_def_line}, called at {resolve_device_calls}")
    print(f"process_file defined at line {process_file_def_line}, calls resolve_device: {process_file_calls_resolve}")
    print(f"callers found: {len(CALLERS)}, protected: {payload['summary_counts']['protected_already']}, "
          f"vulnerable: {payload['summary_counts']['vulnerable']}")
    print(f"classification: {payload['phase_2_classification'][:80]}...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
