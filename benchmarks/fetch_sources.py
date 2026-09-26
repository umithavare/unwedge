"""Download the public datasets behind the multi-source benchmark (about 330 MB of parquet).

Files come from each dataset's auto-converted parquet branch on Hugging Face and land in
benchmarks/data/hf/<source>/. The original SWE-agent sample is fetched separately by
fetch_trajectories.py. Then run build_corpus.py.

Usage:  python benchmarks/fetch_sources.py [--sources swe-smith swe-gym jetbrains]
"""

from __future__ import annotations

import argparse
import shutil
import urllib.request
from pathlib import Path

from sources import HF

BASE = "https://huggingface.co/datasets/{repo}/resolve/refs%2Fconvert%2Fparquet/{file}"
FILES = {  # source -> (dataset, [parquet files]); SWE-smith and JetBrains: MIT; SWE-Gym: no license on its card
    "swe-smith": ("SWE-bench/SWE-smith-trajectories", ["default/tool/0001.parquet", "default/tool/0002.parquet"]),
    "swe-gym": ("SWE-Gym/OpenHands-Sampled-Trajectories", ["default/train.raw/0000.parquet"]),
    "jetbrains": ("JetBrains-Research/agent-trajectories-swe-bench-test-minus-verified",
                  ["default/train/0000.parquet"]),
}


def fetch(source: str) -> list[Path]:
    repo, files = FILES[source]
    written = []
    for file in files:
        target = HF / source / file.replace("default/", "").replace("/", "-")
        if target.exists() and target.stat().st_size > 0:
            written.append(target)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(BASE.format(repo=repo, file=file), headers={"User-Agent": "unwedge-bench"})
        partial = target.with_suffix(".part")
        with urllib.request.urlopen(request, timeout=120) as response, partial.open("wb") as handle:
            shutil.copyfileobj(response, handle, length=1 << 20)
        partial.replace(target)
        written.append(target)
    return written


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sources", nargs="+", default=list(FILES), choices=list(FILES))
    args = parser.parse_args()
    for source in args.sources:
        for path in fetch(source):
            print(f"{source}: {path.name} {path.stat().st_size / 1e6:.0f} MB", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
