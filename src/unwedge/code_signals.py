"""Tier 0: exact, free loop signals computed in code for every turn.

This is the baseline jev has to beat. It is deliberately strong: exact and fuzzy
action repeats, result fingerprints and near-duplicates, repeated error
signatures, and streak counters. A signal at turn t only looks at turns <= t.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from unwedge.normalize import (
    command_similarity,
    error_signature,
    fingerprint,
    jaccard,
    normalize_command,
    shingles,
)
from unwedge.turns import ToolClass, Turn

DEFAULT_WINDOW = 12
_READ_ONLY = {ToolClass.NAVIGATE, ToolClass.SEARCH}


@dataclass(frozen=True)
class CodeSignals:
    turn: int
    exact_repeats: int  # earlier turns in the window with the identical normalized command
    repeat_without_change: int  # of those, repeats with no applied state change in between
    action_similarity: float  # max similarity to an earlier command in the window
    result_repeats: int  # earlier turns in the window with the identical result fingerprint
    result_similarity: float  # max shingle-Jaccard to an earlier result in the window
    error_repeats: int  # earlier failing turns (whole session) with the same error signature
    consecutive_errors: int
    turns_since_change: int  # turns since the last applied edit/write/install
    read_only_streak: int  # consecutive navigate/search turns ending here
    invalid_streak: int  # consecutive turns without a valid action ending here
    pair_repeats: int = 0  # earlier turns in the window with the same command AND the same result
    cycle_repeats: int = 1  # how often the last 2-4 (command, result) steps repeat back to back


@dataclass(frozen=True)
class _Prepared:
    command: str
    result_fp: str
    result_shingles: frozenset[str]
    error_sig: str | None
    informative: bool  # the result is evidence about the world (see _informative)


class SignalTracker:
    """Incremental signals for the hot path: each `add` costs O(window), not O(history).
    The cached per-turn preparations are private and append-only."""

    def __init__(self, window: int = DEFAULT_WINDOW) -> None:
        self._window = window
        self._turns: list[Turn] = []
        self._prepared: list[_Prepared] = []
        self._last_change: list[int] = []  # 1-based index of the latest applied edit at or before i

    def add(self, turn: Turn) -> CodeSignals:
        previous_change = self._last_change[-1] if self._last_change else 0
        self._turns.append(turn)
        self._prepared.append(_prepare(turn))
        self._last_change.append(turn.index if turn.changes_state else previous_change)
        return _signals_at(len(self._turns) - 1, self._turns, self._prepared, self._last_change, self._window)


def may_change_state(turn: Turn) -> bool:
    """An applied edit, or a command that ran successfully and is not read-only (a script,
    a scroll in a browser, an install). Failed commands are assumed to have changed nothing,
    so "the same failing command again" still counts as a repeat."""
    return turn.changes_state or (turn.tool_class is ToolClass.RUN and not turn.is_error)


def compute_signals(turns: Sequence[Turn], window: int = DEFAULT_WINDOW) -> tuple[CodeSignals, ...]:
    """One CodeSignals per turn, in order."""
    tracker = SignalTracker(window)
    return tuple(tracker.add(turn) for turn in turns)


def _prepare(turn: Turn) -> _Prepared:
    return _Prepared(
        command=normalize_command(turn.command),
        result_fp=fingerprint(turn.observation),
        result_shingles=shingles(turn.observation),
        error_sig=error_signature(turn.observation) if turn.is_error else None,
        informative=_informative(turn),
    )


_EMPTY_RESULTS = {"", "(no output)", "[image]", "(interrupted)"}


def _informative(turn: Turn) -> bool:
    """Whether "the same result again" means anything. An empty or image-only result (a
    screenshot) says nothing about what changed, and UI tools (MCP servers such as a browser)
    answer with the same text while the page they act on changes."""
    return turn.observation.strip() not in _EMPTY_RESULTS and not turn.command.startswith("mcp__")


def _signals_at(
    i: int,
    turns: Sequence[Turn],
    prepared: Sequence[_Prepared],
    last_change: Sequence[int],
    window: int,
) -> CodeSignals:
    here, turn = prepared[i], turns[i]
    earlier = range(max(0, i - window + 1), i)
    same_command = [j for j in earlier if prepared[j].command and prepared[j].command == here.command]
    # a repeat counts as "without change" when no *other* action that may change state ran after
    # turn j: rerunning the same command back to back is a repeat, a scroll or an edit in between is not
    no_change_repeats = [
        j for j in same_command
        if not any(may_change_state(turns[k]) and prepared[k].command != here.command for k in range(j + 1, i))
    ]
    # the same command with the same result counts even when edits ran in between: an edit that
    # leaves the test failing the same way changed nothing that matters
    same_pair = [j for j in same_command if here.informative and prepared[j].result_fp == here.result_fp]
    return CodeSignals(
        turn=turn.index,
        exact_repeats=len(same_command),
        repeat_without_change=len(no_change_repeats),
        action_similarity=max((command_similarity(turns[j].command, turn.command) for j in earlier), default=0.0),
        result_repeats=sum(1 for j in earlier if prepared[j].result_fp == here.result_fp),
        result_similarity=max(
            (jaccard(prepared[j].result_shingles, here.result_shingles) for j in earlier), default=0.0
        ),
        error_repeats=sum(1 for j in range(i) if here.error_sig and prepared[j].error_sig == here.error_sig),
        consecutive_errors=_streak(turns, i, lambda t: t.is_error),
        turns_since_change=turn.index - last_change[i],
        read_only_streak=_streak(turns, i, lambda t: t.tool_class in _READ_ONLY),
        invalid_streak=_streak(turns, i, lambda t: t.tool_class is ToolClass.INVALID),
        pair_repeats=len(same_pair),
        cycle_repeats=_cycle_repeats(prepared, i, max(window, 12)),
    )


def _cycle_repeats(prepared: Sequence[_Prepared], i: int, lookback: int) -> int:
    """How many times the last p (command, result) steps repeat back to back, p = 2..4:
    view, run, view, run, view, run gives 3."""
    recent = prepared[max(0, i + 1 - lookback):i + 1]
    keys = [(p.command, p.result_fp) for p in recent]
    end, best = len(keys), 1
    for period in (2, 3, 4):
        block = keys[end - period:end]
        if len(block) < period or len({command for command, _ in block}) < 2:
            continue  # a block of one repeated command is a pair repeat, not a cycle
        if not all(step.informative for step in recent[end - period:end]):
            continue  # a screenshot-and-scroll cycle can be real progress through a page
        reps = 1
        while end - (reps + 1) * period >= 0 and keys[end - (reps + 1) * period:end - reps * period] == block:
            reps += 1
        best = max(best, reps)
    return best


def _streak(turns: Sequence[Turn], i: int, predicate) -> int:
    count = 0
    while i >= 0 and predicate(turns[i]):
        count += 1
        i -= 1
    return count
