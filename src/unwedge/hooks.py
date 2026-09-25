"""`unwedge hook`: one command for Claude Code and Codex CLI hooks.

Reads the hook payload (JSON on stdin), records the tool call, runs the guard over the
session so far and prints the hook response on stdout. It never breaks the agent: any
error is logged to <home>/errors.log and the hook exits 0 with no output (fail open).

Modes (UNWEDGE_MODE or the plugin option):
  shadow  log only; nothing reaches the agent (default)
  hint    a short, human-written hint is added to the model's context when a loop is found
  stop    as hint, and a synchronous Claude Code hook may end the session after hints fail
"""

from __future__ import annotations

import json
import sys
import time
import traceback
from collections.abc import Mapping
from typing import Any, TextIO

from unwedge.adapters import claude_code, codex
from unwedge.config import Settings
from unwedge.guard import HINT_ACTIONS, Guard, GuardConfig, GuardOutcome
from unwedge.policy import Action
from unwedge.providers import ProviderError
from unwedge.store import SessionStore, append_ledger, prune_sessions

TOOL_EVENTS = ("PostToolUse", "PostToolUseFailure")
ESCALATE_TEXT = ("[UNWEDGE] You seem to be stuck: the same kind of step keeps failing without progress. "
                 "Stop repeating it, summarize what you have tried and what failed, and ask the user how to proceed.")
# Not rendered: a gate veto (Action.FLAG) is only logged. On benign benchmark sessions the gate fired
# in about 7% of successful sessions, so a warning would mostly be noise; unwedge is not an injection filter.


def detect_harness(payload: Mapping[str, Any]) -> str:
    if "turn_id" in payload:
        return "codex"
    transcript = str(payload.get("transcript_path") or "").replace("\\", "/")
    if "/.codex/" in transcript or "/rollout-" in transcript:
        return "codex"
    return "claude-code"


def handle(payload: Mapping[str, Any], settings: Settings) -> dict | None:
    """Process one hook event; returns the JSON response to print, or None."""
    harness = detect_harness(payload)
    event = payload.get("hook_event_name")
    store = SessionStore(settings.home, harness, str(payload.get("session_id") or "unknown"))
    if event == "SessionStart":
        prune_sessions(settings.home)
        return None
    if event == "UserPromptSubmit":
        with store.lock():
            store.add_prompt(str(payload.get("prompt") or ""))
        return None
    if event not in TOOL_EVENTS:
        return None
    adapter = codex if harness == "codex" else claude_code
    with store.lock():
        turn = adapter.turn_from_hook(payload, store.next_index())
        if turn is None:
            return None
        store.append_turn(turn)
        history, verdicts, goal = store.turns(), store.verdicts(), store.goal()
    if not goal:
        goal = _goal_from_transcript(harness, payload.get("transcript_path"))
    outcome = _judge(history, verdicts, goal, settings)
    with store.lock():
        store.append_verdict(history[-1].index, outcome.verdict)
    append_ledger(settings.home, _ledger_record(outcome, harness, payload, settings))
    return render(outcome, settings.mode, harness, str(event))


def _judge(history, verdicts, goal: str, settings: Settings) -> GuardOutcome:
    try:
        provider = settings.make_provider()
    except (ValueError, ProviderError):
        provider = None  # misconfigured provider: fall back to the code-only tier
    overrides: dict = {"shadow": settings.mode == "shadow", "kill_enabled": settings.mode == "stop"}
    if settings.timeout_s:
        overrides["timeout_s"] = settings.timeout_s
    try:
        guard = Guard(goal, provider, GuardConfig.for_provider(provider, **overrides))
        for past in history[:-1]:
            guard.replay(past, verdicts.get(past.index))
        return guard.on_turn(history[-1])
    finally:
        if provider is not None:
            provider.close()


def render(outcome: GuardOutcome, mode: str, harness: str, event: str) -> dict | None:
    action = outcome.decision.action
    if mode == "shadow" or action in (Action.CONTINUE, Action.CASCADE):
        return None
    reason = "; ".join(outcome.decision.reasons)[:300]
    if action is Action.KILL and mode == "stop" and harness == "claude-code":
        # a synchronous hook ends the session; an async one (the plugin) ignores `continue`,
        # so the escalation text rides along and still reaches the agent
        return {"continue": False, "stopReason": f"unwedge stopped this session: {reason}. "
                                                 "Run `unwedge report` for the details.",
                "hookSpecificOutput": {"hookEventName": event, "additionalContext": ESCALATE_TEXT}}
    if action in HINT_ACTIONS and outcome.hint_text:
        text = f"[UNWEDGE] {outcome.hint_text}"
    elif action in (Action.ESCALATE, Action.KILL, Action.HINT):
        text = ESCALATE_TEXT
    else:
        return None  # FLAG and anything else stay in the ledger
    response: dict = {"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}}
    if harness == "codex" and action in (Action.ESCALATE, Action.KILL):
        response["systemMessage"] = f"unwedge: possible doom loop ({reason})"
    return response


def _goal_from_transcript(harness: str, path: Any) -> str:
    if not path:
        return ""
    try:
        reader = codex.read_rollout if harness == "codex" else claude_code.read_transcript
        return reader(path)[0]
    except (OSError, ValueError):
        return ""


def _ledger_record(outcome: GuardOutcome, harness: str, payload: Mapping[str, Any], settings: Settings) -> dict:
    verdict = outcome.verdict
    return {
        "ts": round(time.time(), 3), "harness": harness, "session": payload.get("session_id"),
        "cwd": payload.get("cwd"), "turn": outcome.turn, "tool": payload.get("tool_name"),
        "action": outcome.decision.action.value, "reasons": list(outcome.decision.reasons)[:3],
        "hint": outcome.hint_id, "gated": outcome.gated, "degraded": outcome.degraded,
        "latency_ms": round(outcome.latency_ms, 1) if outcome.latency_ms is not None else None,
        "cost_usd": outcome.cost_usd, "provider": settings.provider, "mode": settings.mode,
        "stall": verdict.stall if verdict else None, "p0": verdict.p0 if verdict else None,
        "repeats": outcome.code.repeat_without_change, "error_repeats": outcome.code.error_repeats,
    }


def main(stdin: TextIO = sys.stdin, stdout: TextIO = sys.stdout) -> int:
    settings = None
    try:
        settings = Settings.from_env()
        raw = stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
        response = handle(payload, settings) if isinstance(payload, Mapping) else None
        if response:
            stdout.write(json.dumps(response, ensure_ascii=False))
    except Exception:  # noqa: BLE001 - a guard must never break the agent it guards
        _log_error(settings)
    return 0


def _log_error(settings: Settings | None) -> None:
    try:
        home = settings.home if settings else Settings().home
        home.mkdir(parents=True, exist_ok=True)
        with (home / "errors.log").open("a", encoding="utf-8") as handle:
            handle.write(f"--- {time.strftime('%Y-%m-%d %H:%M:%S')}\n{traceback.format_exc(limit=8)}\n")
    except OSError:
        pass
