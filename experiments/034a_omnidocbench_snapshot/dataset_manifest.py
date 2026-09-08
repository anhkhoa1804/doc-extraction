"""034a Phase 3 -- full dataset validation, using the repo's OWN
odb.load_dataset() validator (not a reimplementation), plus additional
manifest statistics (modality/language distribution, hashes, category
counts, byte totals) the validator itself doesn't compute.

    python experiments/034a_omnidocbench_snapshot/dataset_manifest.py
"""
from __future__ import annotations
import hashlib, json, sys
from collections import Counter
from pathlib import Path
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "src"))

from doc_extraction.evaluation import omnidocbench as odb  # noqa: E402

DATASET_ROOT = HERE / "dataset" / "full"


def main():
    gt_path, samples = odb.load_dataset(DATASET_ROOT)  # raises DatasetError on any schema violation

    raw = json.loads(gt_path.read_text(encoding="utf-8"))
    n_records = len(raw)
    n_resolved = len(samples)
    n_missing = n_records - n_resolved

    # duplicate image_path detection (within the raw records, not just resolved samples)
    image_names = [Path(r["page_info"]["image_path"]).name for r in raw if r.get("page_info", {}).get("image_path")]
    dup_counter = Counter(image_names)
    duplicates = {k: v for k, v in dup_counter.items() if v > 1}

    # modality/language/layout/data_source distributions from page_attribute
    data_source = Counter()
    language = Counter()
    layout = Counter()
    subset = Counter()
    special_issue = Counter()
    for r in raw:
        attr = (r.get("page_info") or {}).get("page_attribute") or {}
        data_source[attr.get("data_source", "?")] += 1
        language[attr.get("language", "?")] += 1
        layout[attr.get("layout", "?")] += 1
        subset[attr.get("subset", "?")] += 1
        for si in attr.get("special_issue") or []:
            special_issue[si] += 1

    # image file integrity: exists, non-zero size, hash a small sample
    images_dir = DATASET_ROOT / "images"
    all_images = sorted(images_dir.glob("*"))
    total_bytes = sum(p.stat().st_size for p in all_images)
    zero_byte = [p.name for p in all_images if p.stat().st_size == 0]

    # sample hashes: every 50th image, deterministic, cheap (not all 1651 --
    # this is an integrity spot-check, not a full checksum manifest)
    sample_hashes = {}
    for i, p in enumerate(all_images):
        if i % 50 == 0:
            sample_hashes[p.name] = hashlib.sha256(p.read_bytes()).hexdigest()[:16]

    gt_hash = odb.dataset_content_hash(gt_path) if hasattr(odb, "dataset_content_hash") else None

    payload = {
        "dataset_root": str(DATASET_ROOT.relative_to(REPO)),
        "ground_truth_json": gt_path.name,
        "ground_truth_content_hash": gt_hash,
        "validator": "doc_extraction.evaluation.omnidocbench.load_dataset "
                    "(the repo's own OmniDocBench dataset validator, not a "
                    "reimplementation) -- raised no DatasetError, so schema, "
                    "JSON validity, and page_info/image_path presence are "
                    "all confirmed by production code.",
        "n_records_in_ground_truth": n_records,
        "n_samples_resolved_to_an_image": n_resolved,
        "n_missing_images": n_missing,
        "duplicate_image_names": duplicates,
        "n_image_files_on_disk": len(all_images),
        "total_bytes": total_bytes,
        "total_gb": round(total_bytes / 1e9, 3),
        "zero_byte_images": zero_byte,
        "sample_hashes_every_50th_image": sample_hashes,
        "distributions": {
            "data_source": dict(data_source.most_common()),
            "language": dict(language.most_common()),
            "layout": dict(layout.most_common()),
            "subset": dict(subset.most_common()),
            "special_issue": dict(special_issue.most_common()),
        },
        "annotation_format": "OmniDocBench v1.6 -- top-level JSON array of "
                            "page records, each {layout_dets: [...], "
                            "page_info: {page_no, height, width, "
                            "image_path, page_attribute}, extra: "
                            "{relation}} -- exact schema documented in "
                            "experiments/005_omnidocbench/README.md, "
                            "re-verified directly against these records.",
        "integrity_verdict": (
            "CLEAN" if n_missing == 0 and not duplicates and not zero_byte
            else "ISSUES FOUND -- see n_missing_images/duplicate_image_names/zero_byte_images"
        ),
    }
    Path("dataset_manifest.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False))
    print(f"records: {n_records}, resolved: {n_resolved}, missing: {n_missing}")
    print(f"duplicates: {len(duplicates)}, zero-byte: {len(zero_byte)}")
    print(f"total size: {payload['total_gb']} GB")
    print(f"data_source distribution: {dict(data_source.most_common())}")
    print(f"language distribution: {dict(language.most_common())}")
    print(f"integrity verdict: {payload['integrity_verdict']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
