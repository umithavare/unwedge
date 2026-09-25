"""Offline replay: run the guard over a finished Claude Code transcript or Codex rollout
and show where it would have intervened. With the default provider "none" it is free,
local and instant; with a provider it spends one judgment per gated turn."""

from __future__ import annotations

import glob
import os
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from unwedge.adapters import claude_code, codex
from unwedge.compactor import digest_line
from unwedge.guard import Guard, GuardConfig, GuardOutcome
from unwedge.policy import Action
from unwedge.providers.base import Provider
from unwedge.turns import Turn

QUIET = {Action.CONTINUE, Action.CASCADE}


@dataclass(frozen=True)
class ReplayResult:
    path: str
    harness: str
    goal: str
    turns: tuple[Turn, ...]
    outcomes: tuple[GuardOutcome, ...]

    @property
    def interventions(self) -> list[GuardOutcome]:
        return [o for o in self.outcomes if o.decision.action not in QUIET]

    @property
    def first_intervention(self) -> int | None:
        found = self.interventions
        return found[0].turn if found else None

    @property
    def turns_after_first_intervention(self) -> int:
        first = self.first_intervention
        return 0 if first is None else len(self.turns) - first


def guess_harness(path: str | Path) -> str:
    text = str(path).replace("\\", "/")
    return "codex" if "/.codex/" in text or "/rollout-" in text else "claude-code"


def replay_file(path: str | Path, provider: Provider | None = None, harness: str | None = None) -> ReplayResult:
    harness = harness or guess_harness(path)
    adapter, reader = (codex, codex.read_rollout) if harness == "codex" else (claude_code, claude_code.read_transcript)
    goal, events = reader(path)
    guard = Guard(goal, provider, GuardConfig.for_provider(provider, shadow=True))
    turns, outcomes = [], []
    for event in events:
        turn = adapter.turn_from_hook(event, len(turns) + 1)
        if turn is None:
            continue
        turns.append(turn)
        outcomes.append(guard.on_turn(turn))
    return ReplayResult(str(path), harness, goal, tuple(turns), tuple(outcomes))


def recent_transcripts(limit: int = 20, home: Path | None = None) -> list[Path]:
    """Newest Claude Code transcripts and Codex rollouts on this machine."""
    home = home or Path.home()
    codex_home = Path(os.environ.get("CODEX_HOME") or home / ".codex")
    patterns = [str(home / ".claude" / "projects" / "*" / "*.jsonl"),
                str(codex_home / "sessions" / "*" / "*" / "*" / "rollout-*.jsonl")]
    paths = [Path(p) for pattern in patterns for p in glob.glob(pattern)]
    paths.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return paths[:limit]


def format_timeline(result: ReplayResult, width: int = 90) -> Iterable[str]:
    yield f"{result.harness}  {result.path}"
    yield f"goal: {result.goal[:160].replace(chr(10), ' ')}"
    for turn, outcome in zip(result.turns, result.outcomes, strict=True):
        action = outcome.decision.action
        verdict = outcome.verdict
        if verdict:
            signals = f"S={verdict.stall:.2f} P0={verdict.p0:.2f}"
        else:
            signals = f"rep={outcome.code.repeat_without_change}"
        marker = ""
        if action not in QUIET:
            marker = f"  <<< {action.value}" + (f" [{outcome.hint_id}]" if outcome.hint_id else "")
        yield f"{digest_line(turn)[:width]:<{width}} | {signals:<16}{marker}"
