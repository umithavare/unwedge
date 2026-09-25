"""Sample outcome-labelled SWE-agent trajectories from the public HF dataset.

Source: nebius/SWE-agent-trajectories (SWE-agent runs, Llama models, each row has
`target` = resolved, and `exit_status`). Rows are read in tiny pages from the public
datasets-server `/rows` JSON API at random offsets. Consecutive rows belong to the
same task, so pages are kept small and each task is used at most once per group.
The anonymous API rate-limits by request count, so requests are paced evenly.

Groups (all model_name = swe-agent-llama-70b, one row per instance_id per group):
  success : target = true
  burn    : target = false and the run exhausted its context budget
  wrong   : target = false and the agent submitted normally (a wrong patch, not a loop)

Rows are appended to data/raw/<group>.jsonl as they arrive, so the script resumes.
Usage:  python benchmarks/fetch_trajectories.py
"""

from __future__ import annotations

import json
import random
import sys
import time
import urllib.parse
from pathlib import Path

import httpx

API = "https://datasets-server.huggingface.co/rows"
DATASET = "nebius/SWE-agent-trajectories"
TOTAL_ROWS = 80036
MODEL = "swe-agent-llama-70b"
OUT_DIR = Path(__file__).resolve().parent / "data" / "raw"
SEED = 20260923
PHASE = 2  # bump to draw fresh offsets when resuming with a new page size
PAGE = 3
TARGETS = {"success": 100, "burn": 100, "wrong": 50}
BURN_EXITS = {"submitted (exit_context)", "exit_context"}
KEEP = ("instance_id", "model_name", "target", "exit_status", "generated_patch")
MAX_BYTES = 45_000_000  # cap on this run's transfer
PAUSE_S = 1.6


def group_of(row: dict) -> str | None:
    if row.get("model_name") != MODEL:
        return None
    if row.get("target"):
        return "success"
    if row.get("exit_status") in BURN_EXITS:
        return "burn"
    if row.get("exit_status") == "submitted":
        return "wrong"
    return None


def fetch_rows(client: httpx.Client, offset: int) -> tuple[list[dict], int]:
    url = f"{API}?dataset={urllib.parse.quote(DATASET)}&config=default&split=train&offset={offset}&length={PAGE}"
    for attempt in range(8):
        try:
            response = client.get(url, timeout=60.0)
        except httpx.HTTPError as exc:
            print(f"  network error {type(exc).__name__}, retrying", flush=True)
            time.sleep(5 * (attempt + 1))
            continue
        if response.status_code == 200:
            items = response.json()["rows"]
            rows = [item["row"] for item in items if not item.get("truncated_cells")]  # cut-off transcripts are useless
            return rows, len(response.content)
        if response.status_code == 429:
            print("  429 from datasets-server, pausing 60s", flush=True)
            time.sleep(60)
            continue
        print(f"  HTTP {response.status_code}, retrying", flush=True)
        time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"datasets-server kept failing at offset {offset}")


def slim(row: dict) -> dict:
    kept = {key: row.get(key) for key in KEEP}
    kept["trajectory"] = [{"role": m.get("role"), "text": m.get("text") or ""} for m in row["trajectory"]]
    return kept


def load_existing() -> dict[str, set[str]]:
    seen: dict[str, set[str]] = {group: set() for group in TARGETS}
    for group in TARGETS:
        path = OUT_DIR / f"{group}.jsonl"
        if path.exists():
            with path.open(encoding="utf-8") as handle:
                seen[group] = {json.loads(line)["instance_id"] for line in handle if line.strip()}
    return seen


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    seen = load_existing()
    rng = random.Random(SEED + PHASE)
    offsets = rng.sample(range(TOTAL_ROWS - PAGE), TOTAL_ROWS - PAGE)
    transferred, draws = 0, 0
    with httpx.Client(headers={"User-Agent": "unwedge-benchmark/0.1"}) as client:
        for offset in offsets:
            if all(len(seen[g]) >= n for g, n in TARGETS.items()):
                break
            if transferred >= MAX_BYTES:
                print("transfer cap reached, stopping", flush=True)
                break
            rows, size = fetch_rows(client, offset)
            transferred += size
            draws += 1
            for row in rows:
                group = group_of(row)
                if group and len(seen[group]) < TARGETS[group] and row["instance_id"] not in seen[group]:
                    with (OUT_DIR / f"{group}.jsonl").open("a", encoding="utf-8") as handle:
                        handle.write(json.dumps(slim(row), ensure_ascii=False) + "\n")
                    seen[group].add(row["instance_id"])
            if draws % 10 == 0:
                counts = " ".join(f"{g}={len(seen[g])}/{n}" for g, n in TARGETS.items())
                print(f"draws={draws} {counts} transferred={transferred / 1e6:.1f}MB", flush=True)
            time.sleep(PAUSE_S)
    counts = " ".join(f"{g}={len(seen[g])}" for g in TARGETS)
    print(f"done: draws={draws} {counts} transferred={transferred / 1e6:.1f}MB", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
