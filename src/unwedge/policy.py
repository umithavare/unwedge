"""The decision policy. Pure functions: (state, verdict, code signals) -> (new state, decision).

Jev never decides alone. It supplies probabilities; thresholds, hysteresis, the
injection veto and the hint-before-kill order all live here, in code.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from enum import Enum

from unwedge.answers import noul, score_mass, score_value
from unwedge.code_signals import CodeSignals
from unwedge.questions import DRIFT_KEY, GATE_KEYS, PROGRESS_KEY, STALL_KEYS, TERMINAL_KEY


class Action(str, Enum):
    CONTINUE = "continue"
    HINT = "hint"  # choose a hint from the library (call B)
    VERIFY_HINT = "verify_hint"  # the goal may be met: ask for one confirming check
    RETURN_HINT = "return_hint"  # drifting: point back to the goal and notify a human
    ESCALATE = "escalate"  # hand to a human; repeated at most every `reescalate_turns`
    CASCADE = "cascade"  # persistently ambiguous: ask a frontier model
    FLAG = "flag"  # veto: a tool result talks to the reader; logged, no automated action
    KILL = "kill"  # only when explicitly enabled, after hints, with code evidence


@dataclass(frozen=True)
class Thresholds:
    # starting values from the design doc; bands are >= 0.05 apart and must be refit
    stall_continue: float = 0.70
    stall_intervene: float = 0.85
    p0_continue: float = 0.50
    p0_intervene: float = 0.60
    gate_veto: float = 0.60
    terminal: float = 0.90
    terminal_gate_max: float = 0.40
    drift: float = 0.85
    consecutive: int = 2  # windows in the intervene band before acting
    max_hints: int = 2
    ambiguous_before_cascade: int = 3
    cooldown_turns: int = 3  # no new code-tier intervention within this many turns of the last one
    reescalate_turns: int = 8  # after an escalation, repeat it at most this often while the loop goes on


@dataclass(frozen=True)
class Verdict:
    """One call-A answer set reduced to the numbers the policy uses."""

    stall: float  # max of the stall Nouls, never the mean
    p0: float  # probability mass on progress level 0 ("no closer")
    progress: float  # Score expectation; ordering only, never a magnitude
    terminal: float
    drift: float
    gate: float  # max of the gate Nouls

    @classmethod
    def from_answers(cls, answers: Mapping[str, Mapping]) -> Verdict:
        return cls(
            stall=max(noul(answers, key) for key in STALL_KEYS),
            p0=score_mass(answers, PROGRESS_KEY, 0),
            progress=score_value(answers, PROGRESS_KEY),
            terminal=noul(answers, TERMINAL_KEY),
            drift=noul(answers, DRIFT_KEY),
            gate=max(noul(answers, key) for key in GATE_KEYS),
        )


@dataclass(frozen=True)
class PolicyState:
    stall_streak: int = 0
    drift_streak: int = 0
    ambiguous_streak: int = 0
    hints_given: int = 0
    terminal_hinted: bool = False
    last_intervention_turn: int = 0
    last_escalation_turn: int = 0


@dataclass(frozen=True)
class Decision:
    action: Action
    reasons: tuple[str, ...] = ()


def code_stall_evidence(code: CodeSignals) -> bool:
    return code.repeat_without_change >= 2 or code.result_repeats >= 2 or code.error_repeats >= 2


def code_only_decision(code: CodeSignals) -> Decision:
    """The code tier's stateless test: only blatant loops act."""
    if code.repeat_without_change >= 3 or code.error_repeats >= 4:
        return Decision(Action.HINT, ("code: blatant repeat with nothing changed",))
    return Decision(Action.CONTINUE, ("code-only tier",))


def step(
    state: PolicyState,
    verdict: Verdict | None,
    code: CodeSignals,
    t: Thresholds = Thresholds(),
    *,
    kill_enabled: bool = False,
    code_first: bool = True,
) -> tuple[PolicyState, Decision]:
    """One policy step.

    code_first=True (default): a blatant loop found by code acts even when the provider sees
    no stall; the provider only adds interventions. A gate veto discards the provider's
    judgments for the window, not code's exact counts, so a provider that flags everything
    cannot silence the code tier. The benchmark showed the alternative, letting the
    provider's verdict replace the code tier (code_first=False, "jev as a brake"), halves
    the loops caught.
    """
    if verdict is None:
        return _code_tier(state, code, t)
    new_state, decision = _judged(state, verdict, code, t, kill_enabled)
    if code_first and decision.action in (Action.CONTINUE, Action.CASCADE, Action.FLAG):
        tier_state, tier_decision = _code_tier(new_state, code, t)
        if tier_decision.action is not Action.CONTINUE:
            vetoed = decision.reasons if decision.action is Action.FLAG else ()
            return tier_state, Decision(tier_decision.action, (*tier_decision.reasons, *vetoed))
    return new_state, decision


def _code_tier(state: PolicyState, code: CodeSignals, t: Thresholds) -> tuple[PolicyState, Decision]:
    decision = code_only_decision(code)
    if decision.action is Action.CONTINUE:
        return state, decision
    if state.last_intervention_turn and code.turn - state.last_intervention_turn < t.cooldown_turns:
        return state, Decision(Action.CONTINUE, ("cooling down after an intervention",))
    if state.hints_given < t.max_hints:
        return replace(state, hints_given=state.hints_given + 1, last_intervention_turn=code.turn), decision
    return _escalate(state, code.turn, t, ("code: blatant repeat continues after hints",))


def _escalate(state: PolicyState, turn: int, t: Thresholds,
              reasons: tuple[str, ...]) -> tuple[PolicyState, Decision]:
    """Escalate once, then again only every `reescalate_turns` turns while the loop goes on:
    repeating the same message on every turn adds noise, not information."""
    if state.last_escalation_turn and turn - state.last_escalation_turn < t.reescalate_turns:
        return state, Decision(Action.CONTINUE, (*reasons, "escalated recently"))
    return replace(state, last_intervention_turn=turn, last_escalation_turn=turn), Decision(Action.ESCALATE, reasons)


def _judged(state: PolicyState, verdict: Verdict, code: CodeSignals, t: Thresholds,
            kill_enabled: bool) -> tuple[PolicyState, Decision]:
    if verdict.gate >= t.gate_veto:
        reason = f"veto: tool output addresses the reader or asserts approval (gate={verdict.gate:.2f})"
        return replace(state, stall_streak=0, drift_streak=0, ambiguous_streak=0), Decision(Action.FLAG, (reason,))
    if verdict.terminal >= t.terminal and verdict.gate < t.terminal_gate_max and not state.terminal_hinted:
        reason = f"goal may already be satisfied (terminal={verdict.terminal:.2f})"
        return replace(state, terminal_hinted=True), Decision(Action.VERIFY_HINT, (reason,))
    stalled = verdict.stall >= t.stall_intervene and verdict.p0 >= t.p0_intervene
    healthy = verdict.stall < t.stall_continue and verdict.p0 < t.p0_continue
    if stalled:
        return _stalled(state, verdict, code, t, kill_enabled)
    drifting = verdict.drift >= t.drift and verdict.stall < t.stall_continue
    drift_streak = state.drift_streak + 1 if drifting else 0
    if drifting and drift_streak >= t.consecutive:
        reason = f"drift for {drift_streak} windows (drift={verdict.drift:.2f})"
        return replace(state, drift_streak=0, stall_streak=0), Decision(Action.RETURN_HINT, (reason,))
    if healthy:
        return replace(state, stall_streak=0, ambiguous_streak=0, drift_streak=drift_streak), Decision(Action.CONTINUE)
    ambiguous = state.ambiguous_streak + 1
    if ambiguous >= t.ambiguous_before_cascade:
        reason = f"ambiguous for {ambiguous} windows (stall={verdict.stall:.2f}, p0={verdict.p0:.2f})"
        return replace(state, ambiguous_streak=0, drift_streak=drift_streak), Decision(Action.CASCADE, (reason,))
    new_state = replace(state, ambiguous_streak=ambiguous, drift_streak=drift_streak)
    return new_state, Decision(Action.CONTINUE, ("ambiguous",))


def _stalled(state: PolicyState, verdict: Verdict, code: CodeSignals, t: Thresholds,
             kill_enabled: bool) -> tuple[PolicyState, Decision]:
    streak = state.stall_streak + 1
    reason = f"stall={verdict.stall:.2f} p0={verdict.p0:.2f} for {streak} windows"
    base = replace(state, stall_streak=streak, ambiguous_streak=0, drift_streak=0)
    if streak < t.consecutive:
        return base, Decision(Action.CONTINUE, ("stall band, waiting for confirmation",))
    if state.hints_given < t.max_hints:
        hinted = replace(base, stall_streak=0, hints_given=state.hints_given + 1, last_intervention_turn=code.turn)
        return hinted, Decision(Action.HINT, (reason,))
    if kill_enabled and code_stall_evidence(code):
        return base, Decision(Action.KILL, (reason, "hints exhausted", "code confirms the loop"))
    return _escalate(base, code.turn, t, (reason, "hints exhausted"))
