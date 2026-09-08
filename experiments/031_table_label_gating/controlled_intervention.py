"""031 Phase 10/11 -- offline controlled intervention over stored IR.

Does NOT modify src/. Reuses the band-clustering logic from 026 (validated
against real corpus geometry there) to reconstruct a Table object from a
picture-labelled region's nested Docling text children, entirely from data
already present in the frozen document.json -- no new model, no re-render,
no crop.

Three arms, same underlying IR, only the reconstruction rule differs:

  CONTROL       : current production output, unchanged
  CONSERVATIVE  : reconstruct ONLY where table_shape_probe score >= 3
  AGGRESSIVE    : reconstruct EVERY picture-labelled region with >=1 nested
                  text child, no gate

Measures recovery (cells, row/col coherence) AND regression (Layer 1 text/
char recall, duplication, false-table creation on the probe's only tested
negative population) for both arms against control.

    python experiments/031_table_label_gating/controlled_intervention.py
"""
from __future__ import annotations
import json, sys
from collections import Counter
from pathlib import Path
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
L28 = REPO / "experiments/028_layer2_evaluation"
sys.path.insert(0, str(L28))
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "research/production_corpus"))
sys.path.insert(0, str(REPO / "experiments/023_evidence_centric"))

import run_ab  # noqa: E402
from doc_extraction.schemas.document import Document  # noqa: E402
from run_benchmark import _norm, document_text as layer1_document_text  # noqa: E402
from structural_integrity import structural_integrity  # noqa: E402


def overlap_frac(a, b):
    ix0, iy0 = max(a["x0"], b["x0"]), max(a["y0"], b["y0"])
    ix1, iy1 = min(a["x1"], b["x1"]), min(a["y1"], b["y1"])
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    inter = (ix1 - ix0) * (iy1 - iy0)
    area_b = max(1.0, (b["x1"] - b["x0"]) * (b["y1"] - b["y0"]))
    return inter / area_b


def bbox_iou(a, b):
    ix0, iy0 = max(a["x0"], b["x0"]), max(a["y0"], b["y0"])
    ix1, iy1 = min(a["x1"], b["x1"]), min(a["y1"], b["y1"])
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    inter = (ix1 - ix0) * (iy1 - iy0)
    ua = (a["x1"] - a["x0"]) * (a["y1"] - a["y0"])
    ub = (b["x1"] - b["x0"]) * (b["y1"] - b["y0"])
    union = ua + ub - inter
    return inter / union if union > 0 else 0.0


def attach_text_from_elements(children, elements):
    """The layout/*.json snapshot `apply_intervention` reads children from
    carries only {bbox, label, confidence, source_id} -- NO text field
    (verified: Region dict keys in layout json). OCR text is attached later,
    downstream of layout, into the page's `elements` list in the SAME
    document.json this function already has in hand (Docling emits the same
    nested-child geometry into both places per traverse_pictures=True, so
    the bboxes line up near-exactly). Without this step every reconstructed
    cell.text is '' regardless of intervention mode -- discovered this
    milestone when the first Phase 10 run produced 79/79 conservative
    reconstructions with 100% empty cell text. Match by IoU, not equality,
    since coordinate rounding differs slightly by route; text-typed
    elements only (a table/image element's own bbox can also overlap a
    child geometrically without being the matching text)."""
    text_els = [e for e in elements if e.get("type") not in ("table", "image") and e.get("text")]
    for c in children:
        cb = c.get("bbox")
        if not cb:
            c["text"] = ""
            continue
        best, best_iou = None, 0.0
        for e in text_els:
            eb = e.get("bbox")
            if not eb:
                continue
            i = bbox_iou(cb, eb)
            if i > best_iou:
                best, best_iou = e, i
        c["text"] = best["text"] if best is not None and best_iou > 0.5 else ""
        c["_text_match_iou"] = round(best_iou, 4)
    return children


def band_cluster(boxes, key_lo, key_hi):
    """Same mutual-overlap band clustering 026 validated -- group by overlap,
    not a fixed pixel tolerance."""
    if not boxes:
        return []
    items = sorted(boxes, key=lambda b: b[key_lo])
    bands = [[items[0]]]
    for b in items[1:]:
        band = bands[-1]
        ref = band[-1]
        lo, hi = max(b[key_lo], ref[key_lo]), min(b[key_hi], ref[key_hi])
        if hi > lo:
            band.append(b)
        else:
            bands.append([b])
    return bands


def reconstruct_table(picture_region, text_children, table_counter):
    """Build a Table dict from a picture region's nested text children.
    Row bands by y-overlap, column position by x0 within each row (sorted).
    A conservative rule: column INDEX is assigned by rank within the row,
    not by shared x-band across rows (avoids inventing false column
    alignment the geometry doesn't actually support)."""
    if not text_children:
        return None
    row_bands = band_cluster([c["bbox"] for c in text_children], "y0", "y1")
    # re-attach original child dicts to their band (band_cluster only kept bboxes)
    by_bbox_id = {id(c["bbox"]): c for c in text_children}
    cells = []
    for r, band in enumerate(sorted(row_bands, key=lambda b: min(x["y0"] for x in b))):
        band_children = sorted(
            [by_bbox_id[id(b)] for b in band], key=lambda c: c["bbox"]["x0"])
        for col, child in enumerate(band_children):
            cells.append({
                "row": r, "col": col, "row_span": 1, "col_span": 1,
                "bbox": child["bbox"], "text": child.get("text", ""),
                "is_header": r == 0, "confidence": None,
                "source": "031_intervention_D_reconstruction",
            })
    if not cells:
        return None
    n_rows = max(c["row"] for c in cells) + 1
    n_cols = max(c["col"] for c in cells) + 1
    table_counter[0] += 1
    return {
        "id": f"031-recon-t{table_counter[0]}",
        "bbox": picture_region["bbox"],
        "page_number": None,
        "n_rows": n_rows, "n_cols": n_cols,
        "cells": cells,
        "source_backend": "031_intervention_D_geometric_reconstruction",
        "confidence": None,
    }


def find_layout_and_doc(milestone, arm, document_id):
    roots = {
        "023": REPO / "experiments/023_evidence_centric/_runs",
        "024": REPO / "experiments/024_ocr_fidelity_recovery/_runs",
        "025": REPO / "experiments/025_layout_evidence_recall/_runs",
    }
    base = roots[milestone] / arm
    if not base.exists():
        return None, None
    for d in base.iterdir():
        if d.is_dir() and d.name.rsplit("-", 1)[0] == document_id:
            doc_f = d / "final" / "document.json"
            layout_dir = d / "layout"
            if doc_f.exists() and layout_dir.exists():
                return doc_f, layout_dir
    return None, None


def apply_intervention(doc, layout_dir, mode, probe_threshold=3):
    """Returns (modified_doc, recon_log). mode in {'conservative','aggressive'}.
    Modifies a DEEPCOPY-equivalent (json roundtrip) of doc; caller's original
    is untouched -- this is a read-only fork, not a mutation of stored data."""
    from table_shape_probe import compute_signals, table_shape_score

    doc = json.loads(json.dumps(doc))  # cheap deep copy, no mutation of caller's object
    recon_log = []
    for pg in doc.get("pages") or []:
        pidx = pg.get("index", 0)
        layout_f = layout_dir / f"page-{pidx+1:03d}.json"
        if not layout_f.exists():
            continue
        layout = json.loads(layout_f.read_text())
        regions = layout.get("regions") or []
        pictures = [r for r in regions if (r.get("label") or "").lower() in ("picture", "chart")]
        for pic in pictures:
            pbb = pic.get("bbox")
            if pbb is None:
                continue
            children = [r for r in regions if r.get("bbox")
                       and overlap_frac(pbb, r["bbox"]) > 0.5
                       and (r.get("label") or "").lower() not in ("picture", "chart", "table")]
            if not children:
                continue
            children = attach_text_from_elements(children, pg.get("elements") or [])
            sig = compute_signals(pbb, children)
            score, reasons = table_shape_score(sig)
            gate_pass = score >= probe_threshold if mode == "conservative" else True
            if not gate_pass:
                continue
            counter = [len(pg.get("tables") or [])]
            new_table = reconstruct_table(pic, children, counter)
            if new_table is None:
                continue
            pg.setdefault("tables", []).append(new_table)
            # find the corresponding IMAGE element covering this region and
            # mark it (do not delete -- provenance: keep the original picture
            # element, add the table alongside, exactly like intervention B's design)
            for el in pg.get("elements") or []:
                if el.get("type") == "image" and el.get("bbox") and overlap_frac(pbb, el["bbox"]) > 0.9:
                    el.setdefault("extra", {})["031_table_candidate_added"] = new_table["id"]
            n_with_text = sum(1 for c in new_table["cells"] if c.get("text"))
            recon_log.append({
                "page_index": pidx, "table_id": new_table["id"],
                "probe_score": score, "gate_passed": gate_pass,
                "n_cells": len(new_table["cells"]), "n_rows": new_table["n_rows"],
                "n_cols": new_table["n_cols"],
                "n_cells_with_text": n_with_text,
                "n_cells_empty": len(new_table["cells"]) - n_with_text,
            })
    return doc, recon_log


def main():
    sys.path.insert(0, str(HERE))
    pop = json.loads((HERE / "gated_table_population.json").read_text())
    inv = json.loads((REPO / "experiments/029_deep_forensic_replay/cohort_inventory.json").read_text())
    arm_roots = {(a["milestone"], a["arm"]): a for a in inv["arms"]}

    corpus = {d["document_id"]: d for d in
             json.loads((REPO / "research/production_corpus/corpus/manifest.json").read_text())["documents_list"]}
    scan = {d["document_id"]: d for d in
           json.loads((REPO / "experiments/024_ocr_fidelity_recovery/scan_cohort_manifest.json").read_text())["documents_list"]}

    # test population: every (milestone, arm, document) that appears in the
    # gated_table_population candidates (CONFIRMED + AMBIGUOUS -- includes the
    # probe's only tested negative population too, so false-table creation on
    # negatives is measured in the SAME run)
    test_keys = sorted({(c["milestone"], c["arm"], c["document_id"]) for c in pop["candidates"]})

    results = {"control": [], "conservative": [], "aggressive": []}
    for milestone, arm, did in test_keys:
        doc_f, layout_dir = find_layout_and_doc(milestone, arm, did)
        if doc_f is None:
            continue
        raw = json.loads(doc_f.read_text())
        man = scan if arm_roots[(milestone, arm)]["manifest"] == "scan_cohort_manifest" else corpus
        entry = man.get(did)
        if entry is None or not entry.get("must_contain"):
            continue

        for mode in ("control", "conservative", "aggressive"):
            if mode == "control":
                mod_doc, recon_log = raw, []
            else:
                mod_doc, recon_log = apply_intervention(raw, layout_dir, mode)

            pyd = Document.model_validate(mod_doc)
            text = layer1_document_text(pyd)
            score = run_ab.score(entry, text)
            si = structural_integrity(mod_doc)
            new_tables = [t for t in si if t["table_id"].startswith("031-recon")]

            results[mode].append({
                "milestone": milestone, "arm": arm, "document_id": did,
                "labels": entry.get("hard_case_labels", []),
                "layer1": {k: score[k] for k in ("text_recall", "char_recall", "order_ok", "hallucinated")},
                "tables_reconstructed": len(new_tables),
                "recon_log": recon_log,
                "new_tables_structurally_valid": sum(1 for t in new_tables if t["structurally_valid"]),
            })

    # aggregate deltas
    def agg(mode):
        rows = results[mode]
        n = len(rows) or 1
        return {
            "n": len(rows),
            "mean_text_recall": round(sum(r["layer1"]["text_recall"] for r in rows) / n, 4),
            "mean_char_recall": round(sum(r["layer1"]["char_recall"] for r in rows) / n, 4),
            "docs_hallucinated": sum(1 for r in rows if r["layer1"]["hallucinated"]),
            "total_tables_reconstructed": sum(r["tables_reconstructed"] for r in rows),
            "tables_structurally_valid": sum(r["new_tables_structurally_valid"] for r in rows),
            "total_cells_reconstructed": sum(
                e["n_cells"] for r in rows for e in r["recon_log"]),
            "total_cells_with_text": sum(
                e.get("n_cells_with_text", 0) for r in rows for e in r["recon_log"]),
            "total_cells_empty": sum(
                e.get("n_cells_empty", 0) for r in rows for e in r["recon_log"]),
        }

    ctl, cons, aggr = agg("control"), agg("conservative"), agg("aggressive")

    # false-table creation on the probe's NEGATIVE documents (1-2 child stamp fragments)
    neg_docs = {"cmb_lowcontrast_stamp_vi", "hc_stamp_text_vi", "hc_transparent_seal_vi"}
    false_tables = {
        mode: sum(r["tables_reconstructed"] for r in results[mode] if r["document_id"] in neg_docs)
        for mode in results
    }
    # true recovery on the confirmed gating-failure documents
    true_docs = {"cmb_stamp_table_vi", "hc_stamp_table_vi", "cmb_scan_stamp_table_vi"}
    true_recovery = {
        mode: sum(r["tables_reconstructed"] for r in results[mode] if r["document_id"] in true_docs)
        for mode in results
    }

    payload = {
        "control": ctl, "conservative": cons, "aggressive": aggr,
        "false_table_creation_on_probe_negative_documents": false_tables,
        "true_table_recovery_on_confirmed_gated_documents": true_recovery,
        "negative_documents_tested": sorted(neg_docs),
        "confirmed_gated_documents_tested": sorted(true_docs),
        "rows": results,
    }
    Path("intervention_results.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False))

    print(f"CONTROL:      {ctl}")
    print(f"CONSERVATIVE: {cons}")
    print(f"AGGRESSIVE:   {aggr}")
    print(f"\nfalse tables created on NEGATIVE (non-table) documents: {false_tables}")
    print(f"true tables recovered on CONFIRMED gated documents: {true_recovery}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
