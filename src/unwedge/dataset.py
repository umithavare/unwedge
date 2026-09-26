"""The unwedge session format: one JSON object per line, one session per object.

The benchmark reads public datasets through it, and `unwedge export` writes your own Claude
Code / Codex sessions in it so they can be labelled and added to the benchmark:

    {"format": "unwedge-session/1", "source": "swe-smith", "session_id": "...",
     "group": "success" | "burn" | "wrong" | "submitted" | null,
     "resolved": true, "exit_status": "...", "model": "...", "goal": "...",
     "stuck_turn": 12 | null,
     "turns": [{"index": 1, "command": "...", "tool": "pytest", "tool_class": "run",
                "observation": "...", "is_error": true, "changes_state": false, "cost_units": 812.5}]}

Groups: success = the task was solved; burn = it failed after exhausting a budget (the loops
unwedge should catch); wrong = it failed with a normal finish; submitted = it finished normally
but the outcome is unknown. `stuck_turn` optionally marks the first turn of a loop. Text in a
record is already scrubbed of secrets.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from unwedge.turns import Session, ToolClass, Turn

FORMAT = "unwedge-session/1"
GROUPS = ("success", "burn", "wrong", "submitted", "limit")
_TURN_FIELDS = ("index", "command", "tool", "tool_class", "observation", "is_error", "changes_state", "cost_units")


def session_to_record(session: Session, *, stuck_turn: int | None = None, **extra: Any) -> dict[str, Any]:
    return {
        "format": FORMAT, "source": session.source, "session_id": session.session_id, "group": session.group,
        "resolved": session.resolved, "exit_status": session.exit_status, "model": session.model,
        "goal": session.goal, "stuck_turn": stuck_turn, **extra,
        "turns": [{"index": t.index, "command": t.command, "tool": t.tool, "tool_class": t.tool_class.value,
                   "observation": t.observation, "is_error": t.is_error, "changes_state": t.changes_state,
                   "cost_units": t.cost_units} for t in session.turns],
    }


def session_from_record(record: Mapping[str, Any]) -> Session:
    if record.get("format") != FORMAT:
        raise ValueError(f"unknown record format {record.get('format')!r}; expected {FORMAT}")
    turns = tuple(_turn(raw, position) for position, raw in enumerate(record.get("turns") or [], start=1))
    return Session(
        session_id=str(record.get("session_id") or ""),
        group=str(record.get("group") or "unlabelled"),
        resolved=bool(record.get("resolved")),
        exit_status=str(record.get("exit_status") or ""),
        goal=str(record.get("goal") or ""),
        turns=turns,
        source=str(record.get("source") or ""),
        model=str(record.get("model") or ""),
    )


def _turn(raw: Mapping[str, Any], position: int) -> Turn:
    try:
        tool_class = ToolClass(raw.get("tool_class"))
    except ValueError:
        raise ValueError(f"turn {position}: unknown tool_class {raw.get('tool_class')!r}") from None
    return Turn(
        index=int(raw.get("index") or position), command=str(raw.get("command") or ""),
        tool=str(raw.get("tool") or ""), tool_class=tool_class, observation=str(raw.get("observation") or ""),
        is_error=bool(raw.get("is_error")), changes_state=bool(raw.get("changes_state")),
        cost_units=float(raw.get("cost_units") or 0.0),
    )


def write_sessions(path: str | Path, sessions: Iterable[Session], **extra: Any) -> int:
    """Write sessions as JSON lines; returns how many were written."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for session in sessions:
            handle.write(json.dumps(session_to_record(session, **extra), ensure_ascii=False) + "\n")
            count += 1
    return count


def read_sessions(path: str | Path) -> list[Session]:
    with Path(path).open(encoding="utf-8") as handle:
        return [session_from_record(json.loads(line)) for line in handle if line.strip()]
