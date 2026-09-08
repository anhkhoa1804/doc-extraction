"""031 Phase 7 -- test stamp/occlusion causal models A/B/C/D against paired evidence.

Read-only. Uses paired_gating_cases.json (same document, gate outcome
varies by arm) as the primary evidence, since document-level stamp/
occlusion presence is a CONSTANT within a document -- if gate outcome
varies while the stamp is present in every arm, the stamp cannot be the
sole or direct cause.

    python experiments/031_table_label_gating/causal_models.py
"""
from __future__ import annotations
import json
from pathlib import Path
HERE = Path(__file__).resolve().parent

paired = json.loads((HERE / "paired_gating_cases.json").read_text())

MODELS = {
    "A": "stamp/occlusion DIRECTLY causes picture label (deterministic: stamp present "
        "-> always picture-labelled)",
    "B": "stamp/occlusion DEGRADES layout evidence, indirectly causing picture label "
        "(probabilistic, mediated by evidence quality)",
    "C": "OCR/layout backend interaction causes picture label; stamp merely increases "
        "probability (route/backend is the proximate cause)",
    "D": "stamp is incidental; another document property is causal",
}

evidence = []
for pc in paired["paired_cases"]:
    did = pc["document_id"]
    gated = pc["arms_ONLY_gated_never_tabled"]
    tabled = pc["arms_ONLY_tabled_never_gated"]
    both = pc["arms_in_both_states_simultaneously"]

    # classify the route family of gated-only vs tabled-only arms
    def route_family(arm):
        if "scan_cohort" in arm:
            return "scan_cohort (rasterized image, forced-scan)"
        if "adaptive" in arm:
            return "adaptive (native/digital-PDF route where applicable)"
        if "visual" in arm:
            return "visual (forced OCR route, NOT rasterized)"
        return "other"

    gated_families = sorted({route_family(a) for a in gated})
    tabled_families = sorted({route_family(a) for a in tabled})

    evidence.append({
        "document_id": did,
        "stamp_occlusion_present": True,  # constant, all 3 are 025-named stamp docs
        "gated_only_route_families": gated_families,
        "tabled_only_route_families": tabled_families,
        "clean_flip_by_route": bool(gated_families) and bool(tabled_families) and
                               gated_families != tabled_families,
    })

# Model A test: if gate outcome ever varies for the SAME document (stamp constant),
# model A (deterministic direct cause) is falsified.
flips = [e for e in evidence if e["clean_flip_by_route"]]
model_a_falsified = len(flips) > 0

verdicts = {
    "A": {
        "verdict": "REJECTED" if model_a_falsified else "UNRESOLVED",
        "reasoning": (
            f"{len(flips)}/{len(evidence)} documents show the SAME document, with "
            f"the SAME stamp/occlusion content present in every arm, flipping "
            f"between gated and tabled depending on ROUTE FAMILY alone "
            f"(paired_gating_cases.json). A deterministic 'stamp -> picture label' "
            f"rule cannot produce this: cmb_stamp_table_vi is gated under "
            f"scan_cohort/coverage but tabled under adaptive/023-024, hc_stamp_table_vi "
            f"is gated under visual+scan_cohort but tabled under adaptive. The stamp "
            f"itself is present identically in all these runs -- only the route "
            f"differs."
        ),
    },
    "C": {
        "verdict": "SUPPORTED" if model_a_falsified else "UNRESOLVED",
        "reasoning": (
            "The SAME flip evidence that rejects A directly supports C: route family "
            "(adaptive/native vs scan_cohort/rasterized vs visual/forced-OCR) is the "
            "variable that changes while stamp content stays constant. This is "
            "consistent with 030's H1 finding that OCR-recognizer choice, not "
            "document visual properties, gates the DOWNSTREAM row-synthesis "
            "mechanism -- here the same kind of route/backend sensitivity appears "
            "one stage earlier, at the LAYOUT LABEL itself, not just at cell "
            "recovery. INFERENCE, not proven at the pixel level: WHY route changes "
            "Docling's layout classification (different rendering DPI/quality "
            "between adaptive's native extraction and scan_cohort's rasterization?) "
            "was not traced to Docling's internal model this milestone."
        ),
    },
    "B": {
        "verdict": "PARTIALLY SUPPORTED",
        "reasoning": (
            "Consistent with the evidence but not independently distinguished from C "
            "-- 'degraded layout evidence' (B) and 'backend/route interaction' (C) "
            "are not mutually exclusive: rasterization (scan_cohort) could BOTH "
            "change the route AND degrade the visual evidence Docling's layout model "
            "sees (lower effective resolution, JPEG compression per 024's own "
            "_rasterize method at q58-66). This milestone cannot cleanly separate "
            "'route changed' from 'route changed AND evidence degraded' without "
            "inspecting Docling's layout model output at matched resolution, which "
            "was not done."
        ),
    },
    "D": {
        "verdict": "REJECTED as the SOLE explanation, not as a contributing factor",
        "reasoning": (
            "The route-family flip pattern is consistent across cmb_stamp_table_vi "
            "and hc_stamp_table_vi -- not idiosyncratic to one document -- which "
            "argues against 'incidental, another property is causal' as the primary "
            "story. Some OTHER document-specific property may still contribute "
            "(document layout complexity, e.g.) but route family alone already "
            "explains the flip pattern well enough that a fully independent cause "
            "is not needed to explain the data."
        ),
    },
}

payload = {"models": MODELS, "paired_flip_evidence": evidence,
          "documents_with_clean_route_flip": len(flips), "verdicts": verdicts}
Path("causal_models.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False))
print(f"documents with clean route-driven flip: {len(flips)}/{len(evidence)}")
for e in evidence:
    print(f"  {e['document_id']:<25} gated={e['gated_only_route_families']} "
          f"tabled={e['tabled_only_route_families']} flip={e['clean_flip_by_route']}")
for k, v in verdicts.items():
    print(f"\nModel {k}: {v['verdict']}")
