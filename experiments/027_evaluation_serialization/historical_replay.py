"""027 Phase 3/4 -- replay every frozen artifact under both serializers.

Offline, CPU only. Reads saved IR from milestones 023, 024 and 025 (026
reused 025's IR and adds no run of its own), serializes each document twice,
scores both with the FROZEN `run_ab.score`, and reports control /
counterfactual / delta per arm and per changed document.

Nothing is taken from a previous milestone's write-up: every number here is
recomputed from the artifacts. The control is additionally checked against
the real `run_benchmark.document_text` on live pydantic objects for a sample
of documents, so the transcription in `counterfactual_serializer.py` is
verified rather than trusted.

    python experiments/027_evaluation_serialization/historical_replay.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "research/production_corpus"))
sys.path.insert(0, str(REPO / "experiments/023_evidence_centric"))

import run_ab  # noqa: E402
from counterfactual_serializer import cell_sequences, invariants, serialize  # noqa: E402

CORPUS_MANIFEST = REPO / "research/production_corpus/corpus/manifest.json"
SCAN_MANIFEST = REPO / "experiments/024_ocr_fidelity_recovery/scan_cohort_manifest.json"

RUNS = [
    ("023", REPO / "experiments/023_evidence_centric/_runs", "corpus"),
    ("024", REPO / "experiments/024_ocr_fidelity_recovery/_runs", "auto"),
    ("025", REPO / "experiments/025_layout_evidence_recall/_runs", "scan"),
]


def load_manifests():
    corpus = {d["document_id"]: d
              for d in json.loads(CORPUS_MANIFEST.read_text())["documents_list"]}
    scan = {d["document_id"]: d
            for d in json.loads(SCAN_MANIFEST.read_text())["documents_list"]}
    return corpus, scan


def structural_integrity(doc: dict) -> tuple[int, int]:
    """Tables whose cells are stored in non-decreasing bbox y0 order."""
    tot = ok = 0
    for pg in doc.get("pages") or []:
        for tb in pg.get("tables") or []:
            ys = [(c.get("bbox") or {}).get("y0") for c in (tb.get("cells") or [])
                  if isinstance(c.get("bbox"), dict)]
            if not ys:
                continue
            tot += 1
            if ys == sorted(ys):
                ok += 1
    return ok, tot


def main() -> int:
    corpus, scan = load_manifests()
    arms, changed_docs, inv_failures = [], [], []
    verified_against_real = {"checked": 0, "identical": 0}

    # verify the transcription against the real serializer on live objects
    from doc_extraction.schemas.document import Document
    from run_benchmark import document_text as real_document_text

    for milestone, root, mkind in RUNS:
        if not root.exists():
            continue
        by_arm: dict[str, list[Path]] = {}
        for f in root.rglob("final/document.json"):
            arm = str(f.parent.parent.parent.relative_to(root))
            by_arm.setdefault(arm, []).append(f)

        for arm, files in sorted(by_arm.items()):
            rows = []
            si_ok = si_tot = 0
            for f in sorted(files):
                did = f.parent.parent.name.rsplit("-", 1)[0]
                man = scan if (mkind == "scan" or "scan_cohort" in arm) else corpus
                entry = man.get(did) or corpus.get(did) or scan.get(did)
                if entry is None or not entry.get("must_contain"):
                    continue
                doc = json.loads(f.read_text())

                inv = invariants(doc)
                if not all(v for k, v in inv.items() if isinstance(v, bool)):
                    inv_failures.append({"milestone": milestone, "arm": arm,
                                         "document_id": did, "invariants": inv})

                tc, ti = serialize(doc, False), serialize(doc, True)
                if verified_against_real["checked"] < 25:
                    try:
                        real = real_document_text(Document.model_validate(doc))
                        verified_against_real["checked"] += 1
                        verified_against_real["identical"] += int(real == tc)
                    except Exception:
                        pass
                sc, si_ = run_ab.score(entry, tc), run_ab.score(entry, ti)
                a, b = structural_integrity(doc)
                si_ok += a
                si_tot += b

                row = {"document_id": did, "control": sc, "counterfactual": si_,
                       "text_changed": tc != ti,
                       "multiset_same": Counter(tc.split()) == Counter(ti.split())}
                rows.append(row)
                if (sc["text_recall"] != si_["text_recall"]
                        or sc["char_recall"] != si_["char_recall"]
                        or sc["order_ok"] != si_["order_ok"]
                        or sc["hallucinated"] != si_["hallucinated"]):
                    seqs = [s for s in cell_sequences(doc) if s["differs"]]
                    changed_docs.append({
                        "milestone": milestone, "arm": arm, "document_id": did,
                        "control": {k: sc[k] for k in ("text_recall", "char_recall",
                                                       "order_ok", "found", "missing",
                                                       "hallucinated")},
                        "counterfactual": {k: si_[k] for k in ("text_recall", "char_recall",
                                                               "order_ok", "found", "missing",
                                                               "hallucinated")},
                        "text_multiset_identical": row["multiset_same"],
                        "tables_reordered": len(seqs),
                        "sequences": seqs[:2],
                    })
            if not rows:
                continue

            def agg(key):
                n = len(rows)
                return {
                    "n": n,
                    "mean_text_recall": round(sum(r[key]["text_recall"] for r in rows) / n, 4),
                    "mean_char_recall": round(sum(r[key]["char_recall"] for r in rows) / n, 4),
                    "docs_perfect": sum(1 for r in rows if r[key]["text_recall"] == 1.0),
                    "docs_zero": sum(1 for r in rows if r[key]["text_recall"] == 0.0),
                    "docs_order_ok": sum(1 for r in rows if r[key]["order_ok"]),
                    "docs_hallucinated": sum(1 for r in rows if r[key]["hallucinated"]),
                    "must_contain_found": sum(r[key]["found"] for r in rows),
                    "must_contain_required": sum(r[key]["required"] for r in rows),
                }

            c, k = agg("control"), agg("counterfactual")
            arms.append({
                "milestone": milestone, "arm": arm, "documents": len(rows),
                "control": c, "counterfactual": k,
                "delta": {m: round(k[m] - c[m], 4) for m in c if m != "n"},
                "documents_with_changed_text": sum(1 for r in rows if r["text_changed"]),
                "documents_with_changed_multiset": sum(1 for r in rows if not r["multiset_same"]),
                "structural_integrity": {"ordered": si_ok, "tables": si_tot,
                                         "value": round(si_ok / si_tot, 4) if si_tot else None},
            })
            print(f"  {milestone} {arm:<38} n={len(rows):<3} "
                  f"order_ok {c['docs_order_ok']:>2}->{k['docs_order_ok']:<2} "
                  f"exact {c['mean_text_recall']}->{k['mean_text_recall']} "
                  f"char {c['mean_char_recall']}->{k['mean_char_recall']} "
                  f"SI {si_ok}/{si_tot}", flush=True)

    payload = {
        "commit": "c92eb8bdeba4a7b58579bfdf9a3240ef871d73f3",
        "control": "frozen run_benchmark.document_text (raw cell list order)",
        "counterfactual": "identical, except table cells iterated in (row, col) order",
        "transcription_check": verified_against_real,
        "invariant_failures": inv_failures,
        "all_invariants_hold": not inv_failures,
        "note": "evidence coverage / orphan rate / overlap rate / evidence duplication are "
                "token-and-region properties. The serializer reads neither, so they are "
                "invariant under this counterfactual by construction; 025's values stand "
                "unchanged. tables_ok is computed by the caller from tables_found vs "
                "tables_expected and is likewise serializer-invariant.",
        "arms": arms,
        "changed_documents": changed_docs,
    }
    (HERE / "historical_replay.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False))

    print(f"\narms replayed: {len(arms)}")
    print(f"transcription vs real document_text: "
          f"{verified_against_real['identical']}/{verified_against_real['checked']} identical")
    print(f"all invariants hold: {payload['all_invariants_hold']}")
    print(f"documents whose SCORE changed: {len(changed_docs)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
