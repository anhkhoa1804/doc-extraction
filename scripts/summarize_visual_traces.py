"""Summarize opt-in visual traces; never read predictions, images or models."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from doc_extraction.utils.visual_forensics import MAX_BYTES, summarize_traces


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("traces", type=Path, nargs="+")
    args = parser.parse_args(argv)
    if len(args.traces) > 1000:
        parser.error("at most 1000 trace files per invocation")
    total: Counter[str] = Counter()
    omitted = 0
    for path in args.traces:
        with path.open("rb") as stream:
            data = stream.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            parser.error("trace exceeds the diagnostic byte limit")
        record = json.loads(data)
        if record.get("format") != "classic-visual-forensics-v1":
            parser.error("unsupported trace format")
        total.update(summarize_traces([record]))
        omitted += record["omitted_pages"]
    print(json.dumps({"patterns": dict(sorted(total.items())), "omitted_pages": omitted}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
