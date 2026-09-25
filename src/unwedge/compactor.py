"""The digest compactor: a session's recent history as a small `state` for the provider.

Typed-decision models do not summarize (they generate no text) and their context is
bounded (32k tokens for jev, 512-1,024 for Laya), so code decides what the judgment
sees: the goal, one line per recent turn, and the latest results close to verbatim.
Keeping the state small is also an accuracy measure: unrelated detail distracts.

Two layouts:
- "full"    {goal, window (oldest -> newest), last_results}: for large-context providers.
- "compact" {goal, latest, recent (newest -> oldest)}: for small-context providers that
            truncate the *end* of the state, so the newest evidence comes first.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass

from unwedge.normalize import error_signature, fingerprint
from unwedge.turns import ToolClass, Turn

_FILE_HEADER = re.compile(r"\[File: ([^\]]+?) \((\d+) lines total\)\]")
_VIEWER_NUMBER = re.compile(r"^(\d+):", re.MULTILINE)
_WS = re.compile(r"\s+")


@dataclass(frozen=True)
class DigestConfig:
    window: int = 12  # turns summarized as one line each
    goal_chars: int = 2000
    command_chars: int = 110
    snippet_chars: int = 160
    last_results: int = 2  # most recent results kept close to verbatim
    last_result_chars: int = 1500
    fingerprints: bool = False  # add code-computed result fingerprints to each line
    layout: str = "full"  # "full" or "compact"
    max_state_chars: int | None = None  # hard cap on the serialized state; oldest lines go first


# ~2,200 characters of state leaves room for the question inside a 1,024-token row
COMPACT_DIGEST = DigestConfig(window=7, goal_chars=450, command_chars=80, snippet_chars=90, last_results=1,
                              last_result_chars=450, layout="compact", max_state_chars=2200)


def build_state(goal: str, turns: Sequence[Turn], config: DigestConfig = DigestConfig()) -> dict:
    """State for a decision taken after the last turn in `turns`."""
    if not turns:
        raise ValueError("build_state needs at least one turn")
    recent = list(turns[-config.window :])
    if config.layout == "compact":
        latest = recent[-1]
        state = {
            "goal": clip(goal, config.goal_chars, head_share=0.75),
            "latest": {
                "turn": latest.index,
                "action": display_command(latest.command, 200),
                "result": clip(latest.observation, config.last_result_chars) or "(no output)",
            },
            "recent": [digest_line(turn, config) for turn in reversed(recent[:-1])],
        }
        return _fit(state, "recent", config.max_state_chars, drop_from_end=True)
    state = {
        "goal": clip(goal, config.goal_chars, head_share=0.75),
        "window": [digest_line(turn, config) for turn in recent],
        "last_results": [
            {
                "turn": turn.index,
                "action": clip(turn.command, 300),
                "result": clip(turn.observation, config.last_result_chars) or "(no output)",
            }
            for turn in recent[-config.last_results :]
        ],
    }
    return _fit(state, "window", config.max_state_chars, drop_from_end=False)


def _fit(state: dict, lines_key: str, max_chars: int | None, *, drop_from_end: bool) -> dict:
    """Drop the oldest digest lines until the serialized state fits the budget."""
    if max_chars is None:
        return state
    lines = list(state[lines_key])
    while lines and len(json.dumps({**state, lines_key: lines}, ensure_ascii=False)) > max_chars:
        lines = lines[:-1] if drop_from_end else lines[1:]
    return {**state, lines_key: lines}


def digest_line(turn: Turn, config: DigestConfig = DigestConfig()) -> str:
    line = f"T{turn.index} {display_command(turn.command, config.command_chars)} -> {summarize_result(turn, config)}"
    if config.fingerprints:
        line += f" [fp:{fingerprint(turn.observation)[:4]}]"
    return line


def display_command(command: str, limit: int) -> str:
    lines = command.strip().splitlines()
    if not lines:
        return "(none)"
    head = clip(_WS.sub(" ", lines[0]).strip(), limit)
    return f"{head} (+{len(lines) - 1} lines)" if len(lines) > 1 else head


def summarize_result(turn: Turn, config: DigestConfig = DigestConfig()) -> str:
    text, limit = turn.observation, config.snippet_chars
    if turn.tool_class is ToolClass.INVALID:
        return "no valid command"
    if turn.tool_class is ToolClass.SUBMIT:
        return "submitted"
    if turn.tool_class is ToolClass.EDIT and turn.is_error:
        return clip(_first_line(text), limit)
    if turn.is_error:
        return "ERROR " + clip(error_signature(text), limit)
    if turn.tool_class is ToolClass.EDIT and turn.tool in {"edit", "create", "insert", "append"}:
        return "edit applied"
    if turn.tool_class is ToolClass.NAVIGATE:
        view = _describe_view(text)
        if view:
            return view
    if turn.tool_class is ToolClass.SEARCH:
        first = _first_line(text)
        extra = max(0, len([ln for ln in text.splitlines() if ln.strip()]) - 1)
        return clip(first, limit) + (f" (+{extra} lines)" if extra else "")
    return "ok: " + clip(_WS.sub(" ", text).strip(), limit) if text.strip() else "ok (no output)"


def _describe_view(text: str) -> str | None:
    header = _FILE_HEADER.search(text)
    numbers = [int(n) for n in _VIEWER_NUMBER.findall(text)]
    if not header or not numbers:
        return None
    return f"shows {header.group(1)} lines {min(numbers)}-{max(numbers)} of {header.group(2)}"


def _first_line(text: str) -> str:
    return next((line.strip() for line in text.splitlines() if line.strip()), "")


def clip(text: str, limit: int, head_share: float = 0.4) -> str:
    """Keep head and tail; the middle of long output is the least informative part.
    Tool output keeps more tail (errors come last); a task statement keeps more head."""
    text = text.strip()
    if len(text) <= limit:
        return text
    head = int(limit * head_share)
    tail = limit - head - 3
    return text[:head].rstrip() + " … " + text[-tail:].lstrip()
