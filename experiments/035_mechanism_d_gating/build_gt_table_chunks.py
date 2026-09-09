"""035 support -- split the gt_tables sub-dataset (458 pages) into 2
disjoint chunks for CPU-parallel extraction (2 OS processes, matching the
project's own established process-level-only concurrency pattern -- see
_get_component_backends()'s docstring re: sequential-only within a
process, and 034a's run_concurrency_arm.sh, which uses separate processes
for exactly this reason). CPU-only throughout (GPU is PROTECTED --
Research-No.1's own job; see baseline.json) -- 2 chunks x ~3 threads each
was chosen to leave headroom on this 8-core machine rather than saturate
every core.

    python experiments/035_mechanism_d_gating/build_gt_table_chunks.py
"""
from __future__ import annotations
import json, shutil
from pathlib import Path
HERE = Path(__file__).resolve().parent
SRC = HERE / "dataset" / "gt_tables"
N_CHUNKS = 2


def main():
    raw = json.loads((SRC / "OmniDocBench.json").read_text())
    n = len(raw)
    chunk_size = -(-n // N_CHUNKS)  # ceil
    for c in range(N_CHUNKS):
        recs = raw[c * chunk_size:(c + 1) * chunk_size]
        out = HERE / "dataset" / f"gt_tables_chunk{c}"
        (out / "images").mkdir(parents=True, exist_ok=True)
        for r in recs:
            name = Path(r["page_info"]["image_path"]).name
            src = SRC / "images" / name
            dst = out / "images" / name
            if not dst.exists():
                shutil.copy2(src, dst)
        (out / "OmniDocBench.json").write_text(json.dumps(recs, ensure_ascii=False))
        print(f"chunk{c}: {len(recs)} pages -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
