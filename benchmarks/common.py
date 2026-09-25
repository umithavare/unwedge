"""Shared loading helpers for the offline experiments."""

from __future__ import annotations

import json
import sys
from pathlib import Path

BENCH = Path(__file__).resolve().parent
SRC = BENCH.parent / "src"
if str(SRC) not in sys.path:  # run from a checkout without installing the package
    sys.path.insert(0, str(SRC))

from unwedge.adapters.sweagent import session_from_row  # noqa: E402
from unwedge.turns import Session  # noqa: E402

RAW = BENCH / "data" / "raw"
RESULTS = BENCH / "results"
GROUPS = ("success", "burn", "wrong")


def load_sessions(groups: tuple[str, ...] = GROUPS, min_turns: int = 3) -> list[Session]:
    sessions: list[Session] = []
    for group in groups:
        path = RAW / f"{group}.jsonl"
        if not path.exists():
            continue
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    session = session_from_row(json.loads(line), group)
                    if len(session.turns) >= min_turns:
                        sessions.append(session)
    return sessions


def load_scored(variant: str) -> tuple[list[Session], list[dict]]:
    """Sessions that the battery has scored, with the battery records. A task can appear in
    two groups (two runs of the same instance), so sessions are keyed by (id, group)."""
    battery = read_jsonl(RESULTS / f"battery_{variant}.jsonl")
    scored = {(record["session_id"], record["group"]) for record in battery}
    return [s for s in load_sessions() if (s.session_id, s.group) in scored], battery


def restrict(sessions: list[Session], battery: list[dict], other: str) -> tuple[list[Session], list[dict]]:
    """Only the sessions another battery scored, for a paired comparison."""
    keep = {(s.session_id, s.group) for s in load_scored(other)[0]}
    return ([s for s in sessions if (s.session_id, s.group) in keep],
            [r for r in battery if (r["session_id"], r["group"]) in keep])


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]
