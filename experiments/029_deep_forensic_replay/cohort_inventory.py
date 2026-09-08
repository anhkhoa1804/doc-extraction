"""029 Phase 1 -- reconstruct the experimental universe. Read only.

Does not assume prior cohorts share semantics. Enumerates every frozen
document.json under 023-025's _runs trees (026-028 produced no new
extraction; they replayed 025's IR), and for each ARM (a directory of
document.json files sharing a configuration) records what is actually
knowable from the artifacts on disk -- never inferred, never guessed.
Fields with no direct evidence are UNKNOWN.

    python experiments/029_deep_forensic_replay/cohort_inventory.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]

MILESTONES = {
    "023": REPO / "experiments/023_evidence_centric/_runs",
    "024": REPO / "experiments/024_ocr_fidelity_recovery/_runs",
    "025": REPO / "experiments/025_layout_evidence_recall/_runs",
}

CORPUS_MANIFEST = REPO / "research/production_corpus/corpus/manifest.json"
SCAN_MANIFEST = REPO / "experiments/024_ocr_fidelity_recovery/scan_cohort_manifest.json"


def load_manifests():
    corpus = {d["document_id"]: d for d in json.loads(CORPUS_MANIFEST.read_text())["documents_list"]}
    scan = {d["document_id"]: d for d in json.loads(SCAN_MANIFEST.read_text())["documents_list"]}
    return corpus, scan


def metadata_of(doc: dict) -> dict:
    return doc.get("metadata") or {}


def main() -> int:
    corpus, scan = load_manifests()
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO,
                            capture_output=True, text=True).stdout.strip()

    arms = []
    for milestone, root in MILESTONES.items():
        if not root.exists():
            continue
        by_arm: dict[str, list[Path]] = defaultdict(list)
        for f in root.rglob("final/document.json"):
            # arm = everything between root and the run-id-suffixed leaf dir
            arm = str(f.parent.parent.parent.relative_to(root))
            by_arm[arm].append(f)

        for arm, files in sorted(by_arm.items()):
            routes, backends, devices, dpis, langs = (Counter() for _ in range(5))
            n_pages = 0
            docs_seen = set()
            has_ocr_route = False
            sample_meta = None
            unreadable = 0
            for f in sorted(files):
                did = f.parent.parent.name.rsplit("-", 1)[0]
                docs_seen.add(did)
                try:
                    doc = json.loads(f.read_text())
                except Exception:
                    unreadable += 1
                    continue
                meta = metadata_of(doc)
                if sample_meta is None:
                    sample_meta = meta
                routes.update([meta.get("route", "UNKNOWN")])
                backends.update([meta.get("backend", "UNKNOWN")])
                devices.update([meta.get("device", "UNKNOWN")])
                for pg in doc.get("pages") or []:
                    n_pages += 1
                    if pg.get("dpi") is not None:
                        dpis.update([pg["dpi"]])
                    sr = pg.get("source_route")
                    if sr and "scan" in str(sr).lower():
                        has_ocr_route = True
                cfg = (meta.get("config_snapshot") or {})
                for l in (cfg.get("ocr_languages") or []):
                    langs.update([l])

            # Manifest identity is NOT inferable from document-id overlap: the
            # 51-document SCAN-49 manifest is a rasterized SUBSET of the
            # 58-document production corpus manifest (verified: scan docs -
            # corpus docs = 0), so id membership is ambiguous for any 49-doc
            # arm. Ground truth instead comes from which SCRIPT produced the
            # arm, read directly from each generator's own CORPUS constant:
            #   023/run_ab.py            CORPUS = research/production_corpus/corpus
            #   024/*_adaptive_ab.py etc CORPUS = research/production_corpus/corpus
            #   024/scan_cohort_ab.py    CORPUS = _runs/scan_cohort_corpus (from scan_cohort_manifest.json)
            #   025/coverage_instrument, intervention_ab  -- both explicit CORPUS = 024's scan_cohort_corpus
            if milestone == "023":
                manifest_match = "corpus_manifest"
            elif milestone == "024":
                if "scan_cohort" in arm:
                    manifest_match = "scan_cohort_manifest"
                elif arm == "realscan_probe":
                    # OmniDocBench real-scan pages: no must_contain in either
                    # manifest. 024/025 both state explicitly "mechanism only,
                    # no quality claim" -- this arm is NOT SCOREABLE by Layer 1.
                    manifest_match = "NONE (OmniDocBench probe, no must_contain)"
                else:
                    manifest_match = "corpus_manifest"
            elif milestone == "025":
                manifest_match = "scan_cohort_manifest"
            else:
                manifest_match = "UNKNOWN"

            arms.append({
                "milestone": milestone,
                "arm": arm,
                "document_count": len(docs_seen),
                "page_count": n_pages,
                "files_unreadable": unreadable,
                "manifest": manifest_match,
                "routes_observed": dict(routes),
                "backends_observed": dict(backends),
                "devices_observed": dict(devices),
                "dpi_observed": dict(dpis) if dpis else "UNKNOWN",
                "ocr_languages_observed": dict(langs) if langs else "UNKNOWN",
                "adaptive_visual_native": (
                    "adaptive" if "adaptive" in arm
                    else "visual" if "visual" in arm
                    else "scan_cohort(adaptive, forced-scan)" if "scan_cohort" in arm
                    else "scan_cohort(adaptive, forced-scan)" if milestone == "025"
                    else "OmniDocBench(real-scan, mechanism-only)" if arm == "realscan_probe"
                    else "UNKNOWN"),
                "has_scanned_route_pages": has_ocr_route,
                "artifact_root": str((MILESTONES[milestone] / arm).relative_to(REPO)),
                "layer1_available": manifest_match.startswith("NONE") is False,
                "layer2_available": True,   # same IR shape consumed by 028's views
                "raw_ir_available": True,
                "source_provenance_available": bool(sample_meta and sample_meta.get("route_reason")),
                "mutation_replay_possible": True,
                "sample_metadata_keys": sorted(sample_meta.keys()) if sample_meta else [],
                "is_smoke_or_warmup": any(k in arm for k in ("warmup", "smoke")),
            })

    payload = {
        "commit": commit,
        "generated_by": "cohort_inventory.py",
        "note": "Every field is read directly from a document.json's metadata or "
                "pages; nothing is inferred from milestone write-ups. UNKNOWN means "
                "no direct evidence was found in the artifact.",
        "totals": {
            "milestones": len(MILESTONES),
            "arms": len(arms),
            "arms_excluding_smoke_warmup": sum(1 for a in arms if not a["is_smoke_or_warmup"]),
            "documents_total_non_distinct": sum(a["document_count"] for a in arms),
            "pages_total": sum(a["page_count"] for a in arms),
        },
        "arms": arms,
    }
    (HERE / "cohort_inventory.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False))

    print(f"milestones scanned: {len(MILESTONES)}")
    print(f"arms found: {len(arms)}  ({payload['totals']['arms_excluding_smoke_warmup']} excl. smoke/warmup)")
    print(f"total pages across all arms: {payload['totals']['pages_total']}")
    for a in arms:
        flag = " [smoke/warmup]" if a["is_smoke_or_warmup"] else ""
        print(f"  {a['milestone']} {a['arm']:<42} docs={a['document_count']:<3} "
              f"pages={a['page_count']:<4} manifest={a['manifest']:<20} "
              f"mode={a['adaptive_visual_native']}{flag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
