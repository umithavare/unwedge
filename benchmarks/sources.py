"""Labelled sessions from public Hugging Face datasets, in addition to the original SWE-agent set.

Each source maps its own outcome fields onto the benchmark groups:
  success = the task was solved (the negatives: an alarm here is a false alarm)
  burn    = it failed after exhausting a budget (cost, context, time, steps) or was stopped by the
            harness mid-task: the runaway sessions unwedge should catch
  wrong   = it failed with a normal finish (reported on the side)
  submitted = it finished normally but the dataset has no success label (jetbrains)
  limit   = it hit a cost limit without looping: jetbrains' GPT-5 runs reach it in a handful of
            varied, expensive turns, so these are budget overruns rather than loops and are not
            counted as positives

Raw parquet files live in benchmarks/data/hf/<source>/ (fetch them with fetch_sources.py);
build_corpus.py converts them once into benchmarks/data/corpus/<source>.jsonl.
"""

from __future__ import annotations

import json
import random
import re
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

from common import BENCH, load_sessions

from unwedge.adapters.messages import extract_goal, session_turns
from unwedge.turns import Session

HF = BENCH / "data" / "hf"
CORPUS = BENCH / "data" / "corpus"
SOURCES = ("nebius", "swe-smith", "swe-gym", "jetbrains")
MIN_TURNS = 3
CAPS: dict[str, dict[str, int]] = {  # sessions kept per group, sampled with a fixed seed
    "swe-smith": {"success": 800, "burn": 600, "wrong": 400},
    "swe-gym": {"success": 600, "burn": 600, "wrong": 300},
    "jetbrains": {"limit": 600, "submitted": 600},
}

_BUDGET_EXIT = re.compile(
    r"Exit due to (?:cost limit|context window|total execution time exceeded)|exceed context limit"
    r"|maximum context length|context_length_exceeded", re.I)


def swe_smith_group(resolved: bool, messages: Sequence[Mapping[str, Any]]) -> str:
    if resolved:
        return "success"
    tail = " ".join(str(m.get("content") or "") for m in messages[-3:])
    return "burn" if _BUDGET_EXIT.search(tail) else "wrong"


def swe_gym_group(resolved: bool, messages: Sequence[Mapping[str, Any]]) -> str:
    """OpenHands runs that end without a finish call were cut off by the harness (iteration
    budget, stuck detector, errors)."""
    if resolved:
        return "success"
    calls = [call for m in messages if m.get("role") == "assistant" for call in (m.get("tool_calls") or [])]
    last = (calls[-1].get("function") or {}).get("name") if calls else None
    return "wrong" if last == "finish" else "burn"


def jetbrains_group(exit_status: str) -> str:
    return "limit" if exit_status == "LimitsExceeded" else "submitted"


def _parquet_rows(source: str, columns: Sequence[str]) -> Iterator[dict]:
    import pyarrow.parquet as pq  # only the corpus build needs pyarrow

    files = sorted((HF / source).glob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"no parquet files in {HF / source}; run benchmarks/fetch_sources.py first")
    for path in files:
        yield from pq.read_table(path, columns=list(columns)).to_pylist()


def _messages(value: Any) -> list[dict]:
    return json.loads(value) if isinstance(value, str) else list(value or [])


def _session(source: str, session_id: str, group: str, resolved: bool, exit_status: str, model: str,
             messages: list[dict]) -> Session | None:
    turns = session_turns(messages)
    if len(turns) < MIN_TURNS:
        return None
    return Session(session_id=session_id, group=group, resolved=resolved, exit_status=exit_status,
                   goal=extract_goal(messages), turns=turns, source=source, model=model)


def raw_sessions(source: str) -> Iterator[Session]:
    """Every usable session of one source, labelled (unsampled)."""
    if source == "nebius":
        for session in load_sessions():
            yield Session(**{**session.__dict__, "source": "nebius", "model": "swe-agent-llama-70b"})
        return
    if source == "swe-smith":
        for row in _parquet_rows(source, ["messages", "resolved", "model", "traj_id"]):
            messages = _messages(row["messages"])
            group = swe_smith_group(bool(row["resolved"]), messages)
            session = _session(source, str(row["traj_id"]), group, bool(row["resolved"]), group, str(row["model"]),
                               messages)
            if session:
                yield session
        return
    if source == "swe-gym":
        for row in _parquet_rows(source, ["messages", "resolved", "instance_id", "run_id"]):
            messages = _messages(row["messages"])
            group = swe_gym_group(bool(row["resolved"]), messages)
            session = _session(source, f"{row['instance_id']}#{row['run_id']}", group, bool(row["resolved"]),
                               group, "", messages)
            if session:
                yield session
        return
    if source == "jetbrains":
        for n, row in enumerate(_parquet_rows(source, ["messages", "instance_id", "selected_models", "exit_status"])):
            models = row.get("selected_models") or []
            model = str(models[0]).rsplit("/", 1)[-1] if models else ""
            session = _session(source, f"{row['instance_id']}#{n}", jetbrains_group(str(row["exit_status"])), False,
                               str(row["exit_status"]), model, _messages(row["messages"]))
            if session:
                yield session
        return
    raise ValueError(f"unknown source {source!r}; choose from {', '.join(SOURCES)}")


def sample(sessions: Sequence[Session], caps: Mapping[str, int] | None, seed: int = 20260926) -> list[Session]:
    """At most caps[group] sessions per group, reproducibly; groups without a cap are kept whole."""
    if not caps:
        return list(sessions)
    rng = random.Random(seed)
    kept: list[Session] = []
    for group in sorted({s.group for s in sessions}):
        members = [s for s in sessions if s.group == group]
        cap = caps.get(group)
        kept.extend(members if cap is None or len(members) <= cap else rng.sample(members, cap))
    return kept


def corpus_path(source: str) -> Path:
    return CORPUS / f"{source}.jsonl"
