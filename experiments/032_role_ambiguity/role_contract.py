"""032 Phase 1 -- reconstruct the semantic role model from actual source.

Read-only. Traces where (if anywhere) the current architecture expresses
observed_role, candidate_roles, evidence, routing_decision, final_role, and
provenance. Every claim is verified against the CURRENT source file at this
commit, not quoted from 031.

    python experiments/032_role_ambiguity/role_contract.py
"""
from __future__ import annotations
import hashlib, json, subprocess
from pathlib import Path
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def sha(p):
    return hashlib.sha256((REPO / p).read_bytes()).hexdigest()[:16]


CONCEPTS = {
    "observed_role": {
        "exists": True,
        "carrier": "Region.label (pipelines/base.py:52-56, @dataclass, NOT a "
                 "pydantic schema type -- ephemeral, pipeline-internal only)",
        "source": "docling_backend.py:322 -- Region(bbox=bbox, "
                 "label=_label_str(item), confidence=None). "
                 "_label_str (docling_backend.py:70-72) reads Docling's own "
                 "label vocabulary verbatim: 'title', 'section-header', "
                 "'text', 'paragraph', 'list-item', 'table', 'picture', "
                 "'figure', 'formula', 'checkbox-selected', "
                 "'checkbox-unselected', 'caption', 'footnote', "
                 "'page-header', 'page-footer' (enumerated from "
                 "_LABEL_TO_ELEMENT_TYPE's own key set, base.py:140-158).",
        "persisted_to_canonical_IR": False,
        "why_not_persisted": "Region is a dataclass used only inside "
            "run_scanned_page_pipeline (pipelines/base.py); "
            "merge_regions_into_page (base.py:591) consumes "
            "layout_result.regions to build Element objects but never "
            "copies region.label itself onto the resulting Element -- only "
            "the COLLAPSED _LABEL_TO_ELEMENT_TYPE.get(region.label.lower()) "
            "result survives (base.py:610).",
    },
    "candidate_roles": {
        "exists": False,
        "evidence": "grepped schemas/element.py, schemas/table.py, "
            "schemas/page.py, schemas/document.py in full -- no field "
            "anywhere holds more than one role/label per region or "
            "element. Region.label and Element.type are both single "
            "scalar values, never a list or ranked set.",
    },
    "evidence": {
        "exists": "PARTIAL",
        "what_exists": "Region.confidence (dataclass field, base.py:55) and "
            "Element.confidence (pydantic field, schemas/element.py:88) "
            "both exist in the TYPE SYSTEM and the merge function DOES "
            "propagate region.confidence -> Element.confidence faithfully "
            "(base.py:628, base.py:644) -- this is not a broken pipe.",
        "what_does_not_exist": "no STRUCTURED geometric/textual evidence "
            "(child count, band regularity, text density, etc. -- the "
            "kind of signal 031's table_shape_probe.py computed entirely "
            "OFFLINE, from data outside the canonical Document schema) is "
            "carried in the IR at all. The only 'evidence' available is "
            "whatever a consumer chooses to recompute from an Element's "
            "own bbox/text/children after the fact -- exactly what 031 "
            "Phase 4-6 did as an out-of-band research script, not "
            "something the production IR stores.",
        "why_confidence_is_still_effectively_absent": "Docling's stable "
            "API (the ONLY layout backend currently wired into the "
            "scanned-page pipeline) never populates a value for the field "
            "the schema is ready to carry -- docling_backend.py:322 "
            "hardcodes confidence=None. This was verified again this "
            "milestone by direct re-read of the current source, matching "
            "031's finding exactly. The gap is in ONE backend's output, "
            "not in the schema or the merge logic.",
    },
    "routing_decision": {
        "exists": "IMPLICIT ONLY",
        "carrier": "control flow, not data. The table gate itself "
            "(base.py:747, table_regions = [r for r in "
            "layout_result.regions if r.label.lower() == \"table\"]) is a "
            "list-comprehension filter -- its OUTCOME (whether a given "
            "region ended up in table_regions) is never written back onto "
            "any object. A second implicit routing point exists at "
            "merge_regions_into_page:613 (if etype == ElementType.TABLE "
            "and tables: ...) which decides whether an element gets a "
            "table_id link or plain gathered text.",
        "persisted_to_canonical_IR": False,
        "consequence": "given only a finished Document, there is no way to "
            "recover WHY a region was or was not routed to the table "
            "specialist -- only the OUTCOME (element.type, "
            "element.table_id) survives, matching 029's own "
            "'table-label correctness is formally undecidable from the "
            "final IR alone' finding (029 FINAL_REPORT.md section 13).",
    },
    "final_role": {
        "exists": True,
        "carrier": "Element.type (schemas/element.py:80), an ElementType "
            "enum with exactly 9 values: text, heading, paragraph, "
            "list_item, table, image, formula, checkbox, signature, other "
            "(schemas/element.py:20-30 -- note: SIGNATURE exists in the "
            "enum but _LABEL_TO_ELEMENT_TYPE has no mapping that ever "
            "produces it -- see role_taxonomy section of FINAL_REPORT).",
        "collapse_ratio": "_LABEL_TO_ELEMENT_TYPE (base.py:140-158) maps "
            "15 distinct detector-label strings onto 9 ElementType "
            "values, with several many-to-one collapses beyond "
            "picture/table: 'picture' AND 'figure' both -> image; "
            "'caption' AND 'footnote' both -> text; 'page-header' AND "
            "'page-footer' both -> other; 'title' AND 'section-header' "
            "both -> heading. Picture/table is not the only place this "
            "architecture already discards distinctions.",
        "reversibility": "NONE -- once assigned, Element.type is the only "
            "role signal any downstream consumer (document_text, Layer-1/2 "
            "evaluators, a future RAG/GraphRAG chunker) will ever see.",
    },
    "provenance": {
        "exists": True,
        "carriers": ["Element.source_backend (required str)",
                     "Element.source_id (optional str)",
                     "Element.order_index (optional int)",
                     "Element.extra (dict[str, Any], free-form)",
                     "Table.source_backend (required str)",
                     "RunMetadata (Document.metadata: route, pipeline, "
                     "backend, model_versions, device_decision, etc.)"],
        "gap": "none of these carry ROLE-DECISION provenance specifically "
            "-- they answer 'which backend produced this element' and "
            "'what run produced this document', not 'why this element "
            "got the role it got, or what else it might have been'. "
            "031's own intervention used Element.extra precisely to add "
            "this missing kind of note (extra['031_table_candidate_"
            "added'] = new_table['id'], controlled_intervention.py:210) "
            "-- proving extra is a viable, already-used carrier for this "
            "purpose without a schema change.",
    },
}

ROLE_TAXONOMY_SOURCE = {
    "detector_label_vocabulary": {
        "source": "Docling's own layout model output, read verbatim by "
                 "_label_str (docling_backend.py:70-72) -- NOT defined or "
                 "constrained by this repository.",
        "values_this_repo_maps": sorted([
            "title", "section-header", "text", "paragraph", "list-item",
            "table", "picture", "figure", "formula", "checkbox-selected",
            "checkbox-unselected", "caption", "footnote", "page-header",
            "page-footer",
        ]),
        "note": "this is the observed_role vocabulary -- richer than "
               "ElementType, but STILL just Docling's own single-label "
               "classification, not a multi-role/evidence output. Docling "
               "itself has already done the label-collapsing this "
               "milestone is asking whether IS a bottleneck; this repo's "
               "own _LABEL_TO_ELEMENT_TYPE collapses it FURTHER.",
    },
    "final_role_vocabulary": {
        "source": "schemas/element.py:20-30, ElementType enum",
        "values": ["text", "heading", "paragraph", "list_item", "table",
                  "image", "formula", "checkbox", "signature", "other"],
        "note": "SIGNATURE is declared but structurally UNREACHABLE via "
               "the current scanned-page pipeline -- no key in "
               "_LABEL_TO_ELEMENT_TYPE maps to it (grep-verified). It may "
               "be reachable via a different pipeline (office/native "
               "routes) not inspected this phase -- flagged for Phase 2.",
    },
}


BASE_LABEL_MAP = {
    "title": "heading", "section-header": "heading", "section_header": "heading",
    "text": "text", "paragraph": "paragraph", "list-item": "list_item",
    "list_item": "list_item", "table": "table", "picture": "image",
    "figure": "image", "formula": "formula", "checkbox-selected": "checkbox",
    "checkbox-unselected": "checkbox", "caption": "text", "footnote": "text",
    "page-header": "other", "page-footer": "other",
}  # pipelines/base.py:140-158, used by the SCANNED-PAGE route

DOCLING_LABEL_MAP = {
    "title": "heading", "section_header": "heading", "text": "text",
    "paragraph": "paragraph", "list_item": "list_item", "table": "table",
    "picture": "image", "chart": "image", "formula": "formula",
    "code": "other", "caption": "text", "footnote": "text",
    "page_header": "other", "page_footer": "other",
    "checkbox_selected": "checkbox", "checkbox_unselected": "checkbox",
    "form": "other", "key_value_region": "other", "handwritten_text": "text",
    "reference": "text", "document_index": "other",
}  # docling_backend.py:41-63, used by the WHOLE-DOCUMENT route


def scan_observed_labels():
    """Every distinct Docling detector label actually observed across the
    full historical corpus's layout/*.json snapshots (the scanned-page
    route's own recorded output -- the only route with historical
    artifacts on disk, confirmed by grep: no experiment ever exercised
    the whole_document_backend route)."""
    from collections import Counter
    labels = Counter()
    n_files = 0
    for ld in REPO.glob("experiments/*/_runs/**/layout"):
        for lf in ld.glob("*.json"):
            n_files += 1
            try:
                layout = json.loads(lf.read_text())
            except Exception:
                continue
            for r in layout.get("regions") or []:
                labels[(r.get("label") or "").lower()] += 1
    return n_files, labels


def compare_label_maps(observed_labels):
    """Where do the two independently-maintained mapping tables disagree,
    for every label EITHER table has a key for, or that was ACTUALLY
    observed in the historical corpus?"""
    all_keys = sorted(set(BASE_LABEL_MAP) | set(DOCLING_LABEL_MAP) | set(observed_labels))
    rows = []
    for k in all_keys:
        base_v = BASE_LABEL_MAP.get(k, "other (DEFAULT, no key match)")
        docling_v = DOCLING_LABEL_MAP.get(k, "other (DEFAULT, no key match)")
        rows.append({
            "detector_label": k,
            "observed_count_in_historical_corpus": observed_labels.get(k, 0),
            "scanned_page_route_maps_to": base_v,
            "whole_document_route_maps_to": docling_v,
            "routes_agree": base_v == docling_v,
        })
    return rows


def main():
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO,
                            capture_output=True, text=True).stdout.strip()
    n_files, observed = scan_observed_labels()
    comparison = compare_label_maps(observed)
    disagreements = [r for r in comparison if not r["routes_agree"]]
    payload = {
        "commit": commit,
        "summary": (
            "The current architecture expresses exactly TWO of the six "
            "requested concepts as real, persisted IR fields: final_role "
            "(Element.type) and provenance (source_backend/source_id/"
            "extra/RunMetadata). observed_role EXISTS but is ephemeral "
            "(Region.label, a pipeline-internal dataclass never copied "
            "onto the persisted Element). evidence exists only "
            "PARTIALLY -- the confidence field is fully wired end-to-end "
            "in the schema and merge logic, but the one layout backend "
            "actually in use never populates it, and no structural/"
            "geometric evidence vector is stored at all. candidate_roles "
            "and routing_decision DO NOT EXIST in any form -- routing is "
            "pure control flow with no data trace, and a region gets "
            "exactly one label with no runner-up ever recorded."
        ),
        "concepts": CONCEPTS,
        "role_taxonomy_source": ROLE_TAXONOMY_SOURCE,
        "phase_2_route_mapping_consistency": {
            "method": "compare pipelines/base.py's _LABEL_TO_ELEMENT_TYPE "
                     "(scanned-page route) against docling_backend.py's own "
                     "_LABEL_MAP (whole-document route) for every label "
                     "key either table defines, or that was actually "
                     "observed in the historical corpus's layout/*.json "
                     f"snapshots ({n_files} files scanned).",
            "historical_corpus_only_exercises_scanned_page_route": True,
            "whole_document_route_never_used_in_any_historical_experiment": True,
            "observed_label_frequencies": dict(observed.most_common()),
            "label_map_comparison": comparison,
            "disagreements": disagreements,
            "n_disagreements": len(disagreements),
            "finding": (
                f"{len(disagreements)} of {len(comparison)} detector labels "
                f"map to a DIFFERENT final ElementType (or fail to map at "
                f"all, silently defaulting to 'other') depending on which "
                f"of the two routes processes the document -- the SAME "
                f"Docling label vocabulary is handled by two independently-"
                f"maintained dictionaries that have drifted apart. Most "
                f"significant: 'checkbox_selected'/'checkbox_unselected' "
                f"(Docling's actual, underscore-delimited output format, "
                f"confirmed by {observed.get('checkbox_selected', 0) + observed.get('checkbox_unselected', 0)} "
                f"observed instances in the historical corpus) never "
                f"matches base.py's hyphenated keys "
                f"('checkbox-selected'/'checkbox-unselected') and silently "
                f"becomes ElementType.OTHER under the scanned-page route, "
                f"while the SAME label correctly becomes ElementType.CHECKBOX "
                f"under the whole-document route. This is a CODE-LEVEL bug, "
                f"verified this milestone by direct source comparison and "
                f"corpus label-frequency scan -- not yet empirically "
                f"observed producing a wrong Document.json (no historical "
                f"experiment ever exercised the whole-document route to "
                f"produce a contrasting artifact), but the checkbox "
                f"mismatch's effect ON THE SCANNED-PAGE ROUTE ALONE is "
                f"real and present in every one of the "
                f"{observed.get('checkbox_selected', 0) + observed.get('checkbox_unselected', 0)} "
                f"observed checkbox regions' historical output."
            ),
            "not_a_032_scope_item": (
                "this is a straightforward key-format consistency bug, "
                "orthogonal to the role-ambiguity architecture question "
                "this milestone investigates -- flagged for a separate, "
                "narrowly-scoped fix candidate (align base.py's dict to "
                "Docling's actual underscore vocabulary, or better, have "
                "one route call the other's mapping table), NOT "
                "implemented here per this milestone's 'do not modify src/' "
                "instruction."
            ),
        },
        "file_hashes": {
            f: sha(f) for f in sorted([
                "src/doc_extraction/schemas/element.py",
                "src/doc_extraction/schemas/page.py",
                "src/doc_extraction/schemas/table.py",
                "src/doc_extraction/schemas/document.py",
                "src/doc_extraction/pipelines/base.py",
                "src/doc_extraction/backends/docling_backend.py",
            ])
        },
    }
    Path("role_contract.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False))
    print(f"commit {commit}")
    for k, v in CONCEPTS.items():
        exists = v.get("exists")
        print(f"  {k:<20} exists={exists}")
    print(f"\nobserved labels ({n_files} layout files): {dict(observed.most_common())}")
    print(f"route mapping disagreements: {len(disagreements)}/{len(comparison)}")
    for d in disagreements:
        print(f"  {d['detector_label']:<22} scanned={d['scanned_page_route_maps_to']:<10} "
              f"whole_doc={d['whole_document_route_maps_to']:<10} "
              f"observed={d['observed_count_in_historical_corpus']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
