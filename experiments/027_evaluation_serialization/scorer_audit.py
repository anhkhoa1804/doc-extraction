"""027 Phase 1 -- freeze and document the current scorer. READ ONLY.

Records exactly what the evaluation stack does today, with file paths, line
numbers, source hashes and the commit it was read at, so the counterfactual
in this milestone is measured against a pinned reference rather than a
remembered one. Nothing here modifies any scorer file.

    python experiments/027_evaluation_serialization/scorer_audit.py
"""
from __future__ import annotations

import hashlib
import inspect
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "research/production_corpus"))
sys.path.insert(0, str(REPO / "experiments/023_evidence_centric"))

import run_ab  # noqa: E402
import run_benchmark  # noqa: E402

FILES = {
    "serializer": REPO / "research/production_corpus/run_benchmark.py",
    "scorer": REPO / "experiments/023_evidence_centric/run_ab.py",
    "table_schema": REPO / "src/doc_extraction/schemas/table.py",
}


def where(fn):
    src, line = inspect.getsourcelines(fn)
    return {"name": fn.__name__,
            "file": str(Path(inspect.getsourcefile(fn)).relative_to(REPO)),
            "first_line": line, "last_line": line + len(src) - 1,
            "source_sha256": hashlib.sha256("".join(src).encode()).hexdigest()[:16]}


def main() -> int:
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO,
                            capture_output=True, text=True).stdout.strip()
    payload = {
        "commit": commit,
        "read_only": True,
        "files": {k: {"path": str(v.relative_to(REPO)),
                      "sha256": hashlib.sha256(v.read_bytes()).hexdigest(),
                      "bytes": v.stat().st_size} for k, v in FILES.items()},
        "functions": {
            "document_text": where(run_benchmark.document_text),
            "_norm": where(run_benchmark._norm),
            "score": where(run_ab.score),
            "char_recall": where(run_ab.char_recall),
            "order_ok": where(run_ab.order_ok),
            "aggregate": where(run_ab.aggregate),
        },
        "behaviour": {
            "page_elements": "iterated in `page.elements` list order; each element's "
                             "`text` appended if truthy. `order_index` is NOT consulted.",
            "tables": "iterated in `page.tables` list order; within a table `tbl.cells` "
                      "is iterated in RAW LIST ORDER via "
                      "`for row in tbl.cells: for cell in (row if isinstance(row, list) "
                      "else [row])`, which tolerates a flat list or a list-of-lists grid. "
                      "`Table.cells` is `list[Cell]`, so the flat branch is taken.",
            "row_col_ignored": True,
            "row_col_evidence": "`cell.row` / `cell.col` appear nowhere in the function body.",
            "tables_appended_after_elements": "all element text for a page precedes all "
                                              "table cell text for that page, so a table "
                                              "sitting visually mid-page is serialized "
                                              "after every text element on that page.",
            "normalization": "`_norm` = NFC + collapse whitespace runs + strip. "
                             "NO case folding. Applied to the joined string and to each "
                             "`must_contain` needle.",
            "exact_recall": "`text.find(_norm(s)) >= 0` per required string; found/required.",
            "char_recall": "difflib.SequenceMatcher(needle, haystack) matching-block sizes "
                           "summed / len(needle). SEQUENCE-ORDER SENSITIVE: matching blocks "
                           "must be non-decreasing in both strings, so permuting the "
                           "haystack can change the score even when its character multiset "
                           "is unchanged.",
            "order_ok": "positions of the FOUND required strings must be non-decreasing in "
                        "the flattened text; strings not found contribute no position. "
                        "Because table cells are appended after element text AND in raw "
                        "list order, this is sensitive to table detector emission order, "
                        "not only to page reading order.",
            "perfect_document": "text_recall == 1.0 (`docs_perfect`).",
            "zero_document": "text_recall == 0.0 (`docs_zero`).",
            "tables_ok": "computed by the CALLER, not by `score`: "
                         "`tables_found >= tables_expected`. Independent of serialization.",
            "must_contain": "strings in manifest document order; drives text_recall, "
                            "char_recall and order_ok.",
            "must_not_contain": "`_norm(s) in text` -> hallucination. Order-insensitive "
                                "except across join boundaries.",
        },
        "sequence_sensitivity": {
            "exact_recall": "insensitive, except a needle spanning a join boundary",
            "char_recall": "SENSITIVE (difflib in-order matching blocks)",
            "order_ok": "SENSITIVE by design -- that is what it measures",
            "must_not_contain": "sensitive only across join boundaries",
            "tables_ok": "insensitive",
        },
        "document_text_source": inspect.getsource(run_benchmark.document_text),
    }
    (HERE / "scorer_audit.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False))

    print(f"commit {commit}")
    for k, v in payload["files"].items():
        print(f"  {k:<13} {v['path']:<52} sha256 {v['sha256'][:16]}  {v['bytes']}B")
    print()
    for k, v in payload["functions"].items():
        print(f"  {k:<14} {v['file']}:{v['first_line']}-{v['last_line']}")
    print(f"\n  row/col ignored by document_text : {payload['behaviour']['row_col_ignored']}")
    print(f"  cells iterated in                : RAW LIST ORDER")
    print(f"  order-sensitive metrics          : char_recall, order_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
