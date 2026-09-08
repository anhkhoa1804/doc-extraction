"""030 Phase 5 -- natural paired experiments already present in 023-029.

Uses existing arm variation as an identification strategy. No synthetic
data. Confounders are named explicitly where a pairing is not clean.
"""
from __future__ import annotations
import json
from collections import defaultdict
from pathlib import Path
HERE = Path(__file__).resolve().parent

h1 = json.loads((HERE / "h1_resolution.json").read_text())
rows = h1["all_rows"]

pairs = []

# --- Pairing 1: same document, different OCR recognizer, same milestone/route ---
# (hc_encoding_vi across 023 adaptive/{easyocr,fusion,tesseract,selection,union})
by_doc_route = defaultdict(dict)
for r in rows:
    if r["milestone"] != "023" or "adaptive" not in r["arm"]:
        continue
    backend = r["arm"].split("/")[-1]
    by_doc_route[r["document_id"]][backend] = r["undershoot_px"]
recognizer_pairs = {d: v for d, v in by_doc_route.items() if len(v) > 1 and len(set(v.values())) > 1}
pairs.append({
    "pairing": "same document, same route (023/adaptive), different OCR recognizer",
    "confounder": "NONE -- Table Transformer is confirmed backend-independent "
                  "(table_backend.py takes no OCR input); recognizer differences can "
                  "only act through which text corroborates tier-3 synthesis",
    "documents_with_variance_across_recognizers": recognizer_pairs,
    "interpretation": "hc_encoding_vi is the only document showing recognizer-dependent "
                      "undershoot (0px under easyocr, ~2px under fusion/tesseract/"
                      "selection/union) -- directly demonstrating H1's implicit claim "
                      "that OCR recognition, not just document visual properties, gates "
                      "whether the defect manifests (029 section 7's finding, "
                      "independently reconfirmed here via undershoot rather than "
                      "declared-shape).",
})

# --- Pairing 2: same document, adaptive vs visual routing (table_transformer only) ---
by_doc_mode = defaultdict(dict)
for r in rows:
    if "scan_cohort" in r["arm"]:
        continue
    mode = "adaptive" if "adaptive" in r["arm"] else "visual" if "visual" in r["arm"] else None
    if mode is None:
        continue
    key = (r["milestone"], r["document_id"])
    by_doc_mode[key].setdefault(mode, []).append(r["undershoot_px"])
routing_pairs = []
for (ms, did), v in by_doc_mode.items():
    if "adaptive" in v and "visual" in v:
        a_mean = sum(v["adaptive"]) / len(v["adaptive"])
        v_mean = sum(v["visual"]) / len(v["visual"])
        routing_pairs.append({"milestone": ms, "document_id": did,
                              "adaptive_mean_undershoot": round(a_mean, 3),
                              "visual_mean_undershoot": round(v_mean, 3),
                              "concordant_sign": (a_mean > 1.0) == (v_mean > 1.0)})
pairs.append({
    "pairing": "same document, same milestone, adaptive vs visual routing "
              "(table_transformer subset only)",
    "confounder": "routing determines WHETHER table_transformer runs at all "
                  "(adaptive often uses pymupdf_tables); this pairing is restricted to "
                  "cases where BOTH modes happened to invoke table_transformer",
    "pairs": routing_pairs,
    "concordance_rate": round(sum(1 for p in routing_pairs if p["concordant_sign"]) / len(routing_pairs), 4)
                        if routing_pairs else None,
})

# --- Pairing 3: same document, across milestones (023 vs 024 vs 025, same doc, adaptive route) ---
by_doc_milestone = defaultdict(dict)
for r in rows:
    if "adaptive" not in r["arm"] or "scan_cohort" in r["arm"]:
        continue
    by_doc_milestone[r["document_id"]][r["milestone"]] = r["undershoot_px"]
cross_milestone = {d: v for d, v in by_doc_milestone.items() if len(v) > 1}
pairs.append({
    "pairing": "same document, same route family (adaptive), across milestones "
              "023/024/025 -- tests temporal/pipeline-version stability",
    "confounder": "pipeline code may differ subtly across milestones (though L5/tier-3 "
                  "synthesis code itself was frozen from 024 onward per this session's "
                  "own git history)",
    "documents": cross_milestone,
    "interpretation": "hc_encoding_vi shows undershoot in EVERY milestone's adaptive "
                      "arm once past 023's easyocr-only baseline -- consistent, not "
                      "milestone-specific noise.",
})

payload = {"pairings": pairs}
(HERE / "paired_comparisons.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False))
print(json.dumps(pairs[0]["documents_with_variance_across_recognizers"], indent=1))
print(f"\nrouting pairs: {len(routing_pairs)}, concordance: "
      f"{payload['pairings'][1]['concordance_rate']}")
print(f"\ncross-milestone docs with data: {list(cross_milestone.keys())}")
