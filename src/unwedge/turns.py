"""Harness-neutral record of one agent turn. Adapters build these; everything else reads them."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ToolClass(str, Enum):
    NAVIGATE = "navigate"  # read-only look at a file: open, goto, scroll, cat
    SEARCH = "search"  # read-only lookup: grep, find, ls, search_dir
    EDIT = "edit"  # changes the world: edit, create, write, install, mv, rm
    RUN = "run"  # executes code or tests: python, pytest, make
    SUBMIT = "submit"  # the agent declares it is done
    INVALID = "invalid"  # the agent produced no usable action (format error)


@dataclass(frozen=True)
class Turn:
    """One action and its result. Text fields are already scrubbed of secrets."""

    index: int  # 1-based position in the session
    command: str  # the action exactly as the agent issued it
    tool: str  # first word of the command, e.g. "edit", "python"
    tool_class: ToolClass
    observation: str  # tool result with harness boilerplate removed
    is_error: bool  # the result reports a failure
    changes_state: bool  # an edit/write/install that was actually applied
    cost_units: float  # proxy for the tokens the agent's model call consumed this turn


@dataclass(frozen=True)
class Session:
    """A finished session with its outcome, used for offline evaluation and replay."""

    session_id: str
    group: str  # sampling group: success / burn / wrong (or submitted / unlabelled)
    resolved: bool  # the task was solved (ground truth from the benchmark)
    exit_status: str
    goal: str
    turns: tuple[Turn, ...]
    source: str = ""  # where the session comes from: a dataset, a harness, "local"
    model: str = ""  # the agent's model, when known

    @property
    def total_cost(self) -> float:
        return sum(turn.cost_units for turn in self.turns)
