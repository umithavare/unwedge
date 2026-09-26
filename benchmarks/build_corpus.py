"""Convert the raw datasets into the unwedge session format, one JSONL file per source.

Usage:  python benchmarks/build_corpus.py [--sources swe-smith swe-gym jetbrains nebius]
"""

from __future__ import annotations

import argparse
import collections
import time

from sources import CAPS, SOURCES, corpus_path, raw_sessions, sample

from unwedge.dataset import write_sessions


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sources", nargs="+", default=list(SOURCES), choices=SOURCES)
    args = parser.parse_args()
    for source in args.sources:
        started = time.time()
        sessions = sample(list(raw_sessions(source)), CAPS.get(source))
        count = write_sessions(corpus_path(source), sessions)
        groups = collections.Counter(s.group for s in sessions)
        models = collections.Counter(s.model for s in sessions).most_common(4)
        print(f"{source}: {count} sessions {dict(groups)} models {models} ({time.time() - started:.0f}s)",
              flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
