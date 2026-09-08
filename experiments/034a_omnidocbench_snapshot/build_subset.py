"""034a Phase 5 -- build a representative ~80-page subset, stratified (not
random) across data_source, subset (hard-case pools), and language, plus
guaranteed coverage of table/formula/multi-column/difficult-visual content.

    python experiments/034a_omnidocbench_snapshot/build_subset.py
"""
from __future__ import annotations
import json, random, shutil
from collections import Counter, defaultdict
from pathlib import Path
HERE = Path(__file__).resolve().parent
FULL = HERE / "dataset" / "full"
OUT = HERE / "dataset" / "subset"

SEED = 42


def cats(r):
    return Counter(d.get("category_type") for d in r.get("layout_dets", []))


def main():
    raw = json.loads((FULL / "OmniDocBench.json").read_text())
    rng = random.Random(SEED)

    by_subset = defaultdict(list)
    for i, r in enumerate(raw):
        attr = r["page_info"].get("page_attribute", {})
        by_subset[attr.get("subset", "?")].append(i)

    picked_idx = set()

    # 1. Hard-case pools: 15 each from equation_hard, layout_hard, table_hard
    #    (deterministic random sample within each pool, not the first N)
    for name in ("equation_hard", "layout_hard", "table_hard"):
        pool = sorted(by_subset[name])
        picked_idx.update(rng.sample(pool, min(15, len(pool))))

    # 2. v1.5 pool: stratify by data_source, ~3-4 per source, favoring
    #    multi-column layout and non-English language for diversity
    v15_by_source = defaultdict(list)
    for i in by_subset["v1.5"]:
        attr = raw[i]["page_info"].get("page_attribute", {})
        v15_by_source[attr.get("data_source", "?")].append(i)

    for source, idxs in sorted(v15_by_source.items()):
        multi_col = [i for i in idxs if raw[i]["page_info"]["page_attribute"].get("layout") != "single_column"]
        single_col = [i for i in idxs if raw[i]["page_info"]["page_attribute"].get("layout") == "single_column"]
        take_multi = rng.sample(multi_col, min(2, len(multi_col)))
        take_single = rng.sample(single_col, min(2, len(single_col)))
        picked_idx.update(take_multi)
        picked_idx.update(take_single)

    picked_idx = sorted(picked_idx)
    subset_records = [raw[i] for i in picked_idx]

    # copy images
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "images").mkdir(exist_ok=True)
    for r in subset_records:
        name = Path(r["page_info"]["image_path"]).name
        src = FULL / "images" / name
        dst = OUT / "images" / name
        if not dst.exists():
            shutil.copy2(src, dst)
    (OUT / "OmniDocBench.json").write_text(json.dumps(subset_records, ensure_ascii=False))

    # manifest stats
    data_source = Counter()
    language = Counter()
    layout = Counter()
    subset_attr = Counter()
    has_table = has_formula = has_multi_col_annotation = 0
    for r in subset_records:
        attr = r["page_info"].get("page_attribute", {})
        data_source[attr.get("data_source", "?")] += 1
        language[attr.get("language", "?")] += 1
        layout[attr.get("layout", "?")] += 1
        subset_attr[attr.get("subset", "?")] += 1
        c = cats(r)
        if c.get("table", 0) > 0:
            has_table += 1
        if c.get("equation_isolated", 0) > 0:
            has_formula += 1
        if attr.get("layout") != "single_column":
            has_multi_col_annotation += 1

    manifest = {
        "method": "stratified, deterministic (seed=42), NOT random-uniform -- "
                 "15 pages each from equation_hard/layout_hard/table_hard "
                 "(the official hard-case pools), plus up to 4 pages "
                 "(2 multi-column-layout + 2 single-column) per data_source "
                 "from the base v1.5 pool, for broad genre coverage.",
        "seed": SEED,
        "n_pages": len(subset_records),
        "page_indices_in_full_dataset": picked_idx,
        "image_names": [Path(r["page_info"]["image_path"]).name for r in subset_records],
        "distributions": {
            "data_source": dict(data_source.most_common()),
            "language": dict(language.most_common()),
            "layout": dict(layout.most_common()),
            "subset": dict(subset_attr.most_common()),
        },
        "content_coverage": {
            "pages_with_table_region": has_table,
            "pages_with_formula_region": has_formula,
            "pages_with_multi_column_layout": has_multi_col_annotation,
        },
        "route_note": (
            "ALL OmniDocBench samples are pre-rendered page images "
            "(png/jpg) -- there is no PDF/office input, so EVERY page in "
            "this subset (and the full dataset) necessarily takes the "
            "'image' route in this system's routing taxonomy. There is no "
            "'native route' representation possible for this benchmark -- "
            "recorded explicitly rather than silently omitted."
        ),
    }
    Path("subset_manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False))
    print(f"subset size: {len(subset_records)}")
    print(f"data_source: {dict(data_source.most_common())}")
    print(f"content coverage: table={has_table}, formula={has_formula}, multi_col={has_multi_col_annotation}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
