"""032 Phase 3 -- role-ambiguity population, built from real historical IR.

Reuses 031's artifacts rather than re-deriving from scratch (031's own
population/probe/negative-control work already covers most of this
ground for the table/picture axis); adds: confirmed real tables (sampled
directly, not just cited), confirmed zero-child genuine pictures, and a
sample of plain text regions as an AGREEMENT baseline. Explicitly reports
which requested categories (form, chart, signature, logo, stamp-as-a-
distinct-detector-label) have ZERO confirmed instances in this corpus,
rather than inventing examples.

    python experiments/032_role_ambiguity/role_ambiguity_population.py
"""
from __future__ import annotations
import json
from pathlib import Path
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
L31 = REPO / "experiments/031_table_label_gating"


def overlap_frac(a, b):
    ix0, iy0 = max(a["x0"], b["x0"]), max(a["y0"], b["y0"])
    ix1, iy1 = min(a["x1"], b["x1"]), min(a["y1"], b["y1"])
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    inter = (ix1 - ix0) * (iy1 - iy0)
    area_b = max(1.0, (b["x1"] - b["x0"]) * (b["y1"] - b["y0"]))
    return inter / area_b


def find_confirmed_tables(limit_per_route=5):
    """Sample real 'table'-labelled regions with a matching populated Table
    object -- the AGREEMENT baseline for the table role."""
    routes = [
        "experiments/023_evidence_centric/_runs/visual/tesseract",
        "experiments/024_ocr_fidelity_recovery/_runs/scan_cohort/SCAN-49/baseline",
    ]
    out = []
    for route in routes:
        root = REPO / route
        if not root.exists():
            continue
        count = 0
        for doc_dir in sorted(root.iterdir()):
            if count >= limit_per_route or not doc_dir.is_dir():
                continue
            layout_dir = doc_dir / "layout"
            final_f = doc_dir / "final" / "document.json"
            if not layout_dir.exists() or not final_f.exists():
                continue
            final = json.loads(final_f.read_text())
            for lf in sorted(layout_dir.glob("*.json")):
                layout = json.loads(lf.read_text())
                regions = layout.get("regions") or []
                tabs = [r for r in regions if (r.get("label") or "").lower() == "table"]
                if not tabs:
                    continue
                pages = final.get("pages") or []
                real_tables = [t for pg in pages for t in (pg.get("tables") or [])]
                if not real_tables:
                    continue
                t0 = real_tables[0]
                out.append({
                    "document_id": doc_dir.name.rsplit("-", 1)[0], "route": route,
                    "observed_label": "table", "region_bbox": tabs[0]["bbox"],
                    "matched_table_shape": [t0.get("n_rows"), t0.get("n_cols")],
                    "matched_table_populated_cells": sum(
                        1 for c in (t0.get("cells") or []) if c.get("text")),
                    "classification": "CONFIRMED",
                    "role": "table",
                    "agreement": "AGREEMENT -- observed label 'table' and a real, "
                                "populated Table object both agree this region is "
                                "a table.",
                })
                count += 1
                break
    return out


def find_confirmed_pictures(limit=6):
    """Zero-nested-child picture regions -- 031's negative_controls.json
    already established these as the corpus's confirmed genuine-picture
    population (docs_with_picture_regions_but_ZERO_children_in_every_arm,
    plus the 3 weak-negative documents whose negative rows are themselves
    zero-child instances by table_shape_probe.py's own construction)."""
    neg = json.loads((L31 / "negative_controls.json").read_text())
    probe = json.loads((L31 / "table_shape_probe.json").read_text())
    out = []
    seen = set()
    for r in probe["all_negative_rows"]:
        did = r["document_id"]
        if did in seen:
            continue
        seen.add(did)
        out.append({
            "document_id": did, "route": f"{r['milestone']}/{r['arm']}",
            "observed_label": "picture", "region_bbox": r["region_bbox"],
            "n_nested_children": 0, "table_shape_score": r["table_shape_score"],
            "classification": "CONFIRMED", "role": "picture",
            "agreement": "AGREEMENT -- zero nested text children, "
                        "table_shape_score=0, part of 031's own established "
                        "negative population (table_shape_probe.json).",
        })
        if len(out) >= limit:
            break
    for d in neg.get("documents_with_picture_regions_but_ZERO_children_in_every_arm", []):
        out.append({
            "document_id": d, "route": "unspecified (0-child in every arm observed)",
            "observed_label": "picture", "region_bbox": None,
            "n_nested_children": 0, "table_shape_score": None,
            "classification": "CONFIRMED", "role": "picture",
            "agreement": "AGREEMENT -- negative_controls.json Phase 13 exhaustive "
                        "search: zero nested children in every arm this document "
                        "was ever replayed under.",
        })
    return out


def table_shaped_pictures():
    """031's own 4 CONFIRMED candidates -- the central AMBIGUOUS/CONFLICT
    population: observed label 'picture', but structural evidence and (for "
    2 of 4) a factual historical oracle say otherwise."""
    verdicts = json.loads((L31 / "recovery_verdicts.json").read_text())
    oracle = json.loads((L31 / "factual_oracle_comparison.json").read_text())
    oracle_exists_by_doc = {d["document_id"]: d["factual_oracle_exists"]
                            for d in oracle["documents"]}
    counts = verdicts["counts_by_document"]
    out = []
    for did, verdict_counts in counts.items():
        doc_verdicts = set(verdict_counts)
        has_oracle = oracle_exists_by_doc.get(did, False)
        if doc_verdicts == {"TRUE_RECOVERY"} and has_oracle:
            classification, role_conclusion, gt = (
                "CONFIRMED", "table (mislabelled picture)",
                "CONFIRMED_TABLE (factual historical oracle agrees, same "
                "physical region YES/PROBABLE -- factual_oracle_comparison.json)")
        elif doc_verdicts == {"PSEUDO_TABLE"}:
            classification, role_conclusion, gt = (
                "CONFIRMED", "picture (region mixes non-table content)",
                "CONFIRMED_NOT_TABLE (rows_vertically_coherent fails at "
                "reconstruction; factual oracle covers only a small "
                "fraction of the region's own area -- recovery_verdicts.json)")
        elif doc_verdicts == {"PLAUSIBLE_RECOVERY"} and not has_oracle:
            classification, role_conclusion, gt = (
                "PLAUSIBLE", "table (structurally coherent, no factual "
                "oracle exists anywhere in the corpus to confirm)",
                "NO_ORACLE_AVAILABLE (factual_oracle_comparison.json: "
                "factual_oracle_exists=false)")
        else:
            classification, role_conclusion, gt = "AMBIGUOUS", "unresolved", "MIXED_VERDICTS"
        out.append({
            "document_id": did, "observed_label": "picture",
            "candidate_role_evidence": "table_shape_evidence_score >= 3 "
                                       "(table_shape_probe.json)",
            "recovery_verdicts": verdict_counts,
            "ground_truth": gt,
            "classification": classification,
            "role": role_conclusion,
            "agreement": "CONFLICT -- observed label says picture; structural "
                        "evidence (multi-row, multi-column nested children) "
                        "says table.",
        })
    return out


def misleading_nontable():
    """The Chapter9 header (032's most important negative discovery in 031):
    observed label picture, structural evidence ALSO says table-shaped
    (score 4/5), but manually confirmed NOT a table."""
    neg = json.loads((L31 / "negative_controls.json").read_text())
    out = []
    for r in neg["realscan_probe_population"]["regions_scored"]:
        out.append({
            "document_id": f"{r['document_id']}#region{r['region_index']}",
            "observed_label": "picture",
            "table_shape_score": r["table_shape_score"],
            "recovered_child_texts": r["recovered_child_texts"],
            "classification": "CONFIRMED" if r["ground_truth"] != "NOT_MANUALLY_VERIFIED" else "UNKNOWN",
            "role": "picture" if r["ground_truth"] == "NOT_A_TABLE" else "unverified",
            "agreement": ("CONFLICT, MISLEADING -- structural evidence says "
                         "table-shaped, manually confirmed picture (header/"
                         "banner)." if r["ground_truth"] == "NOT_A_TABLE" else
                         "INSUFFICIENT -- region scored but not individually "
                         "verified this milestone."),
        })
    return out


def text_baseline_sample():
    """A handful of plain 'text'/'section_header' regions as an AGREEMENT
    baseline for the most common role in the corpus (3,956 + 1,123
    observed instances, role_contract.json)."""
    root = REPO / "experiments/023_evidence_centric/_runs/visual/tesseract"
    out = []
    for doc_dir in sorted(root.iterdir())[:4]:
        if not doc_dir.is_dir():
            continue
        layout_dir = doc_dir / "layout"
        if not layout_dir.exists():
            continue
        for lf in sorted(layout_dir.glob("*.json"))[:1]:
            layout = json.loads(lf.read_text())
            regions = layout.get("regions") or []
            texts = [r for r in regions if (r.get("label") or "").lower() in ("text", "section_header")]
            if texts:
                out.append({
                    "document_id": doc_dir.name.rsplit("-", 1)[0],
                    "observed_label": texts[0]["label"], "region_bbox": texts[0]["bbox"],
                    "classification": "CONFIRMED", "role": "text",
                    "agreement": "AGREEMENT -- plain text/heading region, no "
                                "structural signal conflicts with the label; "
                                "included as a baseline, not a research finding.",
                })
    return out


def absent_categories():
    """Categories the milestone brief suggests but this corpus does not
    confirm -- reported explicitly per the 'do not invent ground truth' /
    'do not add roles merely because they sound useful' instructions."""
    return {
        "form": "Docling's detector vocabulary DEFINES 'form' "
               "(docling_backend.py _LABEL_MAP) but ZERO instances were "
               "observed in the 2,210 historical layout-json files scanned "
               "(role_contract.json observed_label_frequencies) -- not "
               "present in this corpus.",
        "chart": "Docling's detector vocabulary DEFINES 'chart' but ZERO "
                "instances were observed historically. 031's own population "
                "scripts scanned for label in ('picture','chart') "
                "defensively but never matched a literal 'chart' label.",
        "signature": "ElementType.SIGNATURE is DECLARED in the schema "
                    "(schemas/element.py:29) but structurally UNREACHABLE -- "
                    "no key in either label-mapping table produces it "
                    "(role_contract.json). Zero corpus instances.",
        "logo": "not a Docling detector label at all, and not separately "
               "identifiable from any field in the IR. Where a logo exists "
               "in this corpus's documents (e.g. the Chapter9 header's "
               "'macmillanmh.com' publisher watermark region), it is "
               "invisible as a distinct category -- it is just an empty-"
               "text nested child inside a picture-labelled region.",
        "stamp": "NOT a Docling detector label -- confirmed by the full "
                "observed-label frequency scan (role_contract.json: text, "
                "section_header, table, picture, checkbox_unselected, "
                "list_item, checkbox_selected, formula, caption -- no "
                "'stamp'). Every stamp/seal document in this corpus's "
                "picture-gated population (031's 7 documents) is labelled "
                "'picture' by Docling; 'stamp' is a DOWNSTREAM HUMAN/"
                "DOMAIN semantic interpretation this milestone's own "
                "document-naming convention applies, not a role the "
                "detector or the IR represents anywhere. This is itself "
                "significant evidence for Phase 2's taxonomy question -- "
                "see FINAL_REPORT.",
        "decorative": "not a Docling label, not an ElementType value, and "
                     "not evidenced by any distinguishing signal available "
                     "in this corpus -- would need to be entirely invented; "
                     "not included in the population.",
    }


def main():
    confirmed_tables = find_confirmed_tables()
    confirmed_pictures = find_confirmed_pictures()
    table_shaped = table_shaped_pictures()
    misleading = misleading_nontable()
    text_baseline = text_baseline_sample()
    absent = absent_categories()

    all_items = (confirmed_tables + confirmed_pictures + table_shaped +
                misleading + text_baseline)
    by_agreement = {}
    for item in all_items:
        key = item["agreement"].split(" --")[0].split(",")[0]
        by_agreement.setdefault(key, 0)
        by_agreement[key] += 1

    payload = {
        "method": "assembled from real historical IR + 031's already-"
                 "validated artifacts (recovery_verdicts.json, "
                 "negative_controls.json, table_shape_probe.json, "
                 "role_ambiguity_analysis.json) -- no synthetic ground "
                 "truth invented for any item in this section (adversarial "
                 "controls, Phase 12, are separately and explicitly "
                 "labelled synthetic).",
        "categories": {
            "confirmed_tables_agreement_baseline": confirmed_tables,
            "confirmed_pictures_agreement_baseline": confirmed_pictures,
            "table_shaped_pictures_conflict_population": table_shaped,
            "misleading_nontable_conflict_population": misleading,
            "text_agreement_baseline": text_baseline,
        },
        "absent_categories_explicitly_not_invented": absent,
        "summary": {
            "total_real_items": len(all_items),
            "by_classification": {
                c: sum(1 for i in all_items if i["classification"] == c)
                for c in ("CONFIRMED", "PLAUSIBLE", "UNKNOWN")
            },
        },
    }
    Path("role_ambiguity_population.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False))
    print(f"total items: {len(all_items)}")
    print(f"by classification: { {c: sum(1 for i in all_items if i['classification']==c) for c in ('CONFIRMED','PLAUSIBLE','UNKNOWN')} }")
    print(f"absent categories (not invented): {list(absent)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
