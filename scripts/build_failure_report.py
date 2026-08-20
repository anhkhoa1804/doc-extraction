#!/usr/bin/env python
"""Build a failure-analysis report over an outputs/ directory.

This is the bridge from "the pipeline ran" to "here is where it went wrong".
It reads only artifacts already written by `doc_extraction run` / `compare`
— it never re-runs extraction, so it is fast and can be re-run freely as the
outputs directory grows.

    python scripts/build_failure_report.py --input outputs/

Produces:

    failure_report/
      summary.md          human-readable overview, most-suspicious first
      documents.csv       one row per processed document
      pages.csv           one row per page
      regions.csv         one row per element (bbox-level detail)
      suspicious_text/    extracted text of pages that failed quality checks
      tables/             CSV dump of every extracted table
      inspection/         index linking to each document's HTML inspector

Nothing here scores or ranks backend quality — it surfaces evidence. See
docs/experimentation.md.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from doc_extraction.evaluation.disagreement import page_text as disagreement_page_text  # noqa: E402
from doc_extraction.schemas.document import Document  # noqa: E402

# A page with a lot of elements but almost no text, or a wall of text in a
# single element, is worth a look — both usually mean a segmentation problem.
LOW_TEXT_PER_ELEMENT = 5.0
HIGH_TEXT_PER_ELEMENT = 4000.0
# Runtime outliers are reported relative to the median, not an absolute
# threshold, so this stays meaningful as the corpus and hardware change.
RUNTIME_OUTLIER_FACTOR = 5.0


def _load_documents(outputs_root: Path) -> list[tuple[Path, Document]]:
    documents: list[tuple[Path, Document]] = []
    for document_json in sorted(outputs_root.rglob("final/document.json")):
        try:
            data = json.loads(document_json.read_text(encoding="utf-8"))
            documents.append((document_json.parent.parent, Document.model_validate(data)))
        except Exception as exc:  # noqa: BLE001 - a corrupt result file is itself a finding
            print(f"  ! could not read {document_json}: {type(exc).__name__}: {exc}", file=sys.stderr)
    return documents


def _load_failed_runs(outputs_root: Path) -> list[dict[str, Any]]:
    """Documents whose metadata.json records an error but which produced no
    final/document.json — i.e. runs that failed outright."""
    failed = []
    for metadata_path in sorted(outputs_root.rglob("metadata.json")):
        document_dir = metadata_path.parent
        if (document_dir / "final" / "document.json").exists():
            continue
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if metadata.get("errors"):
            failed.append({"document_dir": document_dir.name, **metadata})
    return failed


# Shared with the comparison tooling so "how much text is on this page" means
# the same thing in both places — table cell content included, which matters
# for spreadsheet pages whose entire content lives in Page.tables.
_page_text = disagreement_page_text


def _collect_disagreements(outputs_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for diff_path in sorted(outputs_root.rglob("comparison/*/diff.json")):
        try:
            diff = json.loads(diff_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        for pair in diff.get("disagreements", []):
            for page in pair.get("pages", []):
                rows.append(
                    {
                        "input_file": diff.get("input_file", diff_path.parent.name),
                        "left": pair["left"],
                        "right": pair["right"],
                        "page": page["page_index"] + 1,
                        "element_delta": page["element_count_delta"],
                        "table_delta": page["table_count_delta"],
                        "text_similarity": page["text_similarity"],
                        "bbox_match_rate": page["bbox_match_rate"],
                        "reading_order_correlation": page["reading_order_correlation"],
                    }
                )
    return rows


def build_report(outputs_root: Path, report_root: Path) -> dict[str, Any]:
    report_root.mkdir(parents=True, exist_ok=True)
    (report_root / "suspicious_text").mkdir(exist_ok=True)
    (report_root / "tables").mkdir(exist_ok=True)
    (report_root / "inspection").mkdir(exist_ok=True)

    documents = _load_documents(outputs_root)
    failed_runs = _load_failed_runs(outputs_root)

    document_rows: list[dict[str, Any]] = []
    page_rows: list[dict[str, Any]] = []
    region_rows: list[dict[str, Any]] = []
    suspicious_pages: list[dict[str, Any]] = []
    density_outliers: list[dict[str, Any]] = []
    fallback_pages: list[dict[str, Any]] = []
    rerouted_documents: list[dict[str, Any]] = []

    for document_dir, document in documents:
        meta = document.metadata

        # A document rerouted away from the native path because its text
        # layer failed quality checks is a finding in its own right — its
        # pages now come from OCR and carry no per-page quality note, so it
        # would otherwise be invisible in the page-level sections below.
        profile = meta.text_profile or {}
        if profile.get("suspicious_page_ratio", 0):
            worst_reasons: list[str] = []
            for page_report in (profile.get("per_page") or {}).values():
                if page_report.get("suspicious"):
                    worst_reasons.extend(page_report.get("reasons", []))
            rerouted_documents.append(
                {
                    "input_file": meta.input_filename,
                    "route": meta.route,
                    "suspicious_page_ratio": profile.get("suspicious_page_ratio"),
                    "text_page_ratio": profile.get("text_page_ratio"),
                    "reasons": " | ".join(dict.fromkeys(worst_reasons)),
                }
            )
        total_text = 0
        total_tables = 0
        n_suspicious = 0

        for page in document.pages:
            text = _page_text(page)
            total_text += len(text)
            total_tables += len(page.tables)

            notes = " | ".join(page.notes)
            page_suspicious = any(
                n.startswith("SUSPECT") or ("mixed_script" in n) or ("unexpected_script" in n)
                for n in page.notes
            )
            used_fallback = any("fallback" in n for n in page.notes)
            if page_suspicious:
                n_suspicious += 1
                suspicious_pages.append(
                    {
                        "document": document.document_id,
                        "input_file": meta.input_filename,
                        "page": page.index + 1,
                        "notes": notes,
                    }
                )
                safe_name = f"{document.document_id}_p{page.index + 1:03d}.txt"
                (report_root / "suspicious_text" / safe_name).write_text(
                    f"# {meta.input_filename} page {page.index + 1}\n"
                    f"# route={meta.route} backend={meta.backend}\n"
                    f"# notes: {notes}\n\n{text}",
                    encoding="utf-8",
                )
            if used_fallback:
                fallback_pages.append(
                    {"document": document.document_id, "page": page.index + 1, "notes": notes}
                )

            n_elements = len(page.elements)
            text_per_element = (len(text) / n_elements) if n_elements else 0.0
            if n_elements > 0 and (
                text_per_element < LOW_TEXT_PER_ELEMENT or text_per_element > HIGH_TEXT_PER_ELEMENT
            ):
                density_outliers.append(
                    {
                        "document": document.document_id,
                        "page": page.index + 1,
                        "elements": n_elements,
                        "text_chars": len(text),
                        "text_per_element": round(text_per_element, 1),
                    }
                )

            page_rows.append(
                {
                    "document": document.document_id,
                    "input_file": meta.input_filename,
                    "page_index": page.index,
                    "is_rendered_page": page.is_rendered_page,
                    "route": meta.route,
                    "source_route": page.source_route or "",
                    "backend": page.source_backend or meta.backend,
                    "elements": n_elements,
                    "tables": len(page.tables),
                    "text_chars": len(text),
                    "text_per_element": round(text_per_element, 1),
                    "suspicious": page_suspicious,
                    "used_fallback": used_fallback,
                    "notes": notes,
                }
            )

            for element in page.elements:
                bbox = element.bbox
                region_rows.append(
                    {
                        "document": document.document_id,
                        "page_index": page.index,
                        "element_id": element.id,
                        "type": element.type.value,
                        "page_number": element.page_number if element.page_number is not None else "",
                        "x0": round(bbox.x0, 2) if bbox else "",
                        "y0": round(bbox.y0, 2) if bbox else "",
                        "x1": round(bbox.x1, 2) if bbox else "",
                        "y1": round(bbox.y1, 2) if bbox else "",
                        "confidence": element.confidence if element.confidence is not None else "",
                        "source_backend": element.source_backend,
                        "text_chars": len(element.text or ""),
                    }
                )

            for table in page.tables:
                table_csv = report_root / "tables" / f"{document.document_id}_p{page.index + 1:03d}_{table.id}.csv"
                with open(table_csv, "w", newline="", encoding="utf-8") as f:
                    csv.writer(f).writerows(table.to_grid())

        document_rows.append(
            {
                "document": document.document_id,
                "input_file": meta.input_filename,
                "schema_version": document.schema_version,
                "file_type": meta.file_type,
                "route": meta.route,
                "route_reason": meta.route_reason or "",
                "backend": meta.backend,
                "device": meta.device,
                "pages": len(document.pages),
                "elements": sum(len(p.elements) for p in document.pages),
                "tables": total_tables,
                "text_chars": total_text,
                "suspicious_pages": n_suspicious,
                "runtime_seconds": round(meta.runtime_seconds, 3) if meta.runtime_seconds else "",
                "errors": " | ".join(meta.errors),
                "warnings": " | ".join(meta.warnings),
            }
        )

    # Runtime outliers, relative to the median of this batch.
    runtimes = sorted(r["runtime_seconds"] for r in document_rows if isinstance(r["runtime_seconds"], float))
    runtime_outliers: list[dict[str, Any]] = []
    if runtimes:
        median = runtimes[len(runtimes) // 2]
        threshold = median * RUNTIME_OUTLIER_FACTOR
        for row in document_rows:
            rt = row["runtime_seconds"]
            if isinstance(rt, float) and rt > threshold and rt > 1.0:
                runtime_outliers.append(
                    {"document": row["document"], "runtime_seconds": rt, "median": median}
                )

    disagreements = _collect_disagreements(outputs_root)

    _write_csv(report_root / "documents.csv", document_rows)
    _write_csv(report_root / "pages.csv", page_rows)
    _write_csv(report_root / "regions.csv", region_rows)

    _write_inspection_index(report_root, outputs_root, documents)

    summary = {
        "documents": len(documents),
        "failed_runs": failed_runs,
        "rerouted_documents": rerouted_documents,
        "suspicious_pages": suspicious_pages,
        "fallback_pages": fallback_pages,
        "density_outliers": density_outliers,
        "runtime_outliers": runtime_outliers,
        "disagreements": disagreements,
        "document_rows": document_rows,
    }
    _write_summary_md(report_root / "summary.md", summary)
    return summary


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _write_inspection_index(report_root: Path, outputs_root: Path, documents) -> None:
    import os

    items = []
    for document_dir, document in documents:
        index_html = document_dir / "inspection" / "index.html"
        if index_html.exists():
            rel = os.path.relpath(index_html, report_root / "inspection")
            items.append(f'<li><a href="{Path(rel).as_posix()}">{document.metadata.input_filename}</a></li>')
        else:
            items.append(
                f"<li>{document.metadata.input_filename} — no inspector built "
                f"(<code>doc_extraction inspect {document.document_id}</code>)</li>"
            )
    (report_root / "inspection" / "index.html").write_text(
        "<!doctype html><html><head><meta charset='utf-8'><title>Inspection index</title>"
        "<style>body{font-family:system-ui,sans-serif;margin:2rem}</style></head><body>"
        f"<h1>Per-document inspectors</h1><ul>{''.join(items)}</ul></body></html>",
        encoding="utf-8",
    )


def _write_summary_md(path: Path, summary: dict[str, Any]) -> None:
    lines: list[str] = ["# Failure report", ""]
    lines.append(f"Documents analysed: **{summary['documents']}**")
    lines.append("")
    lines.append(
        "This report surfaces evidence, it does not score backends. Every section "
        "below is a pointer at something worth a human look."
    )
    lines.append("")

    def section(title: str, rows: list[dict[str, Any]], columns: list[str], empty: str) -> None:
        lines.append(f"## {title} ({len(rows)})")
        lines.append("")
        if not rows:
            lines.append(f"_{empty}_")
            lines.append("")
            return
        lines.append("| " + " | ".join(columns) + " |")
        lines.append("|" + "|".join(["---"] * len(columns)) + "|")
        for row in rows[:50]:
            lines.append("| " + " | ".join(str(row.get(c, ""))[:120] for c in columns) + " |")
        if len(rows) > 50:
            lines.append(f"| _...{len(rows) - 50} more, see the CSVs_ |" + " |" * (len(columns) - 1))
        lines.append("")

    section(
        "Parser failures", summary["failed_runs"], ["document_dir", "input_filename", "route", "errors"],
        "No run failed outright.",
    )
    section(
        "Documents rerouted away from the native path (text layer failed quality checks)",
        summary["rerouted_documents"],
        ["input_file", "route", "text_page_ratio", "suspicious_page_ratio", "reasons"],
        "No document was rerouted for text quality.",
    )
    section(
        "Suspicious native text retained (kept on the native path and flagged)",
        summary["suspicious_pages"],
        ["input_file", "page", "notes"],
        "No page was kept with suspicious native text.",
    )
    section(
        "Pages re-extracted via visual fallback", summary["fallback_pages"],
        ["document", "page", "notes"],
        "No page needed the visual fallback.",
    )
    section(
        "Text-density outliers (possible segmentation problems)", summary["density_outliers"],
        ["document", "page", "elements", "text_chars", "text_per_element"],
        "No page had an anomalous text-per-element ratio.",
    )
    section(
        "Runtime outliers", summary["runtime_outliers"], ["document", "runtime_seconds", "median"],
        "No document was a runtime outlier for this batch.",
    )
    section(
        "Backend disagreements", summary["disagreements"],
        ["input_file", "left", "right", "page", "element_delta", "table_delta",
         "text_similarity", "reading_order_correlation"],
        "No comparison runs found — run `doc_extraction compare` to populate this.",
    )

    lines.append("## Per-document overview")
    lines.append("")
    columns = ["input_file", "route", "backend", "pages", "elements", "tables", "text_chars", "suspicious_pages", "runtime_seconds"]
    lines.append("| " + " | ".join(columns) + " |")
    lines.append("|" + "|".join(["---"] * len(columns)) + "|")
    for row in summary["document_rows"]:
        lines.append("| " + " | ".join(str(row.get(c, ""))[:80] for c in columns) + " |")
    lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", default="outputs", help="Outputs directory to analyse.")
    parser.add_argument("--output", default=None, help="Report directory (default: <input>/failure_report).")
    args = parser.parse_args()

    outputs_root = Path(args.input).resolve()
    if not outputs_root.exists():
        print(f"No such directory: {outputs_root}", file=sys.stderr)
        return 1
    report_root = Path(args.output).resolve() if args.output else outputs_root / "failure_report"

    summary = build_report(outputs_root, report_root)
    print(f"Analysed {summary['documents']} document(s)")
    print(f"  parser failures        : {len(summary['failed_runs'])}")
    print(f"  rerouted documents     : {len(summary['rerouted_documents'])}")
    print(f"  suspicious text pages  : {len(summary['suspicious_pages'])}")
    print(f"  visual-fallback pages  : {len(summary['fallback_pages'])}")
    print(f"  density outliers       : {len(summary['density_outliers'])}")
    print(f"  runtime outliers       : {len(summary['runtime_outliers'])}")
    print(f"  disagreement rows      : {len(summary['disagreements'])}")
    print(f"-> {report_root / 'summary.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
