"""034a Phase 7 prep -- split the 77-page subset into N roughly-equal
chunks for a concurrency experiment (separate OS processes, per the
_get_component_backends() docstring's explicit 'sequential only, a future
parallel runner must not share backends across threads' constraint --
this experiment uses PROCESSES, never threads, to stay inside that
already-established safety boundary).

    python experiments/034a_omnidocbench_snapshot/build_concurrency_chunks.py N
"""
from __future__ import annotations
import json, shutil, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
SUBSET = HERE / "dataset" / "subset"


def build_chunks(n_chunks):
    raw = json.loads((SUBSET / "OmniDocBench.json").read_text())
    chunk_dirs = []
    for c in range(n_chunks):
        chunk_records = raw[c::n_chunks]  # interleaved, not contiguous -- each
                                          # chunk gets a representative spread
                                          # of difficulty, not e.g. all the
                                          # easy pages in chunk 0
        out_dir = HERE / "dataset" / f"conc_{n_chunks}way_chunk{c}"
        (out_dir / "images").mkdir(parents=True, exist_ok=True)
        for r in chunk_records:
            name = Path(r["page_info"]["image_path"]).name
            src = SUBSET / "images" / name
            dst = out_dir / "images" / name
            if not dst.exists():
                shutil.copy2(src, dst)
        (out_dir / "OmniDocBench.json").write_text(json.dumps(chunk_records, ensure_ascii=False))
        chunk_dirs.append(str(out_dir))
        print(f"chunk {c}: {len(chunk_records)} pages -> {out_dir}")
    return chunk_dirs


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    build_chunks(n)
