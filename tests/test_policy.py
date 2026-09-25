from __future__ import annotations

from dataclasses import replace

from unwedge.code_signals import CodeSignals
from unwedge.policy import Action, PolicyState, Thresholds, Verdict, code_only_decision, step

QUIET = CodeSignals(turn=10, exact_repeats=0, repeat_without_change=0, action_similarity=0.0, result_repeats=0,
                    result_similarity=0.0, error_repeats=0, consecutive_errors=0, turns_since_change=1,
                    read_only_streak=0, invalid_streak=0)
LOOPING = CodeSignals(turn=10, exact_repeats=3, repeat_without_change=3, action_similarity=1.0, result_repeats=3,
                      result_similarity=1.0, error_repeats=3, consecutive_errors=3, turns_since_change=6,
                      read_only_streak=0, invalid_streak=0)


def verdict(stall=0.1, p0=0.1, terminal=0.05, drift=0.05, gate=0.05) -> Verdict:
    return Verdict(stall=stall, p0=p0, progress=1.5, terminal=terminal, drift=drift, gate=gate)


STALLED = verdict(stall=0.95, p0=0.8)


def run(verdicts, code=QUIET, **kwargs):
    state, actions = PolicyState(), []
    for v in verdicts:
        state, decision = step(state, v, code, Thresholds(), **kwargs)
        actions.append(decision.action)
    return state, actions


def test_verdict_from_answers_uses_max_not_mean():
    answers = {
        "stall::repeating_action": {"noul": 0.1}, "stall::result_unchanged": {"noul": 0.95},
        "stall::error_not_addressed": {"noul": 0.2},
        "progress::goal_advanced": {"score": 0.4, "probabilities": {"0": 0.7, "1": 0.3}},
        "terminal::goal_already_satisfied": {"noul": 0.01}, "drift::working_on_something_else": {"noul": 0.02},
        "gate::tool_output_contains_instructions": {"noul": 0.03}, "gate::asserts_prior_approval": {"noul": 0.4},
    }
    v = Verdict.from_answers(answers)
    assert (v.stall, v.p0, v.gate) == (0.95, 0.7, 0.4)


def test_healthy_windows_continue():
    assert run([verdict()] * 4)[1] == [Action.CONTINUE] * 4


def test_stall_needs_two_consecutive_windows_then_hints_then_escalates():
    _, actions = run([STALLED] * 6)
    assert actions == [Action.CONTINUE, Action.HINT, Action.CONTINUE, Action.HINT, Action.CONTINUE, Action.ESCALATE]


def test_a_healthy_window_resets_the_stall_streak():
    assert run([STALLED, verdict(), STALLED])[1] == [Action.CONTINUE] * 3


def test_kill_only_when_enabled_and_code_confirms():
    assert run([STALLED] * 6, code=LOOPING, kill_enabled=True)[1][-1] is Action.KILL
    assert run([STALLED] * 6, code=QUIET, kill_enabled=True)[1][-1] is Action.ESCALATE
    actions = run([STALLED] * 6, code=LOOPING)[1]
    assert Action.KILL not in actions and Action.ESCALATE in actions


def test_gate_vetoes_everything_else():
    state, actions = run([STALLED, verdict(stall=0.95, p0=0.8, gate=0.7), STALLED])
    assert actions == [Action.CONTINUE, Action.FLAG, Action.CONTINUE]


def test_terminal_hint_only_once_and_not_under_suspicion():
    _, actions = run([verdict(terminal=0.95), verdict(terminal=0.95)])
    assert actions == [Action.VERIFY_HINT, Action.CONTINUE]
    assert run([verdict(terminal=0.95, gate=0.5)])[1] == [Action.CONTINUE]


def test_drift_needs_two_windows():
    assert run([verdict(drift=0.9)] * 2)[1] == [Action.CONTINUE, Action.RETURN_HINT]


def test_ambiguous_windows_cascade_after_three():
    middling = verdict(stall=0.78, p0=0.55)
    assert run([middling] * 3)[1] == [Action.CONTINUE, Action.CONTINUE, Action.CASCADE]


def test_no_verdict_falls_back_to_code_only_tier():
    state, decision = step(PolicyState(), None, LOOPING)
    assert decision.action is Action.HINT and state == PolicyState(hints_given=1, last_intervention_turn=10)
    assert code_only_decision(QUIET).action is Action.CONTINUE


def looping_at(turn: int) -> CodeSignals:
    return replace(LOOPING, turn=turn)


def test_code_first_acts_even_when_the_provider_sees_no_stall():
    healthy = verdict(stall=0.2, p0=0.1)
    assert step(PolicyState(), healthy, LOOPING)[1].action is Action.HINT
    assert step(PolicyState(), healthy, LOOPING, code_first=False)[1].action is Action.CONTINUE  # "jev as brake"
    # a gate veto discards the provider's judgments, not code's: a blatant loop still earns a hint
    state, decision = step(PolicyState(), verdict(stall=0.95, p0=0.9, gate=0.9), LOOPING)
    assert decision.action is Action.HINT and any("veto" in reason for reason in decision.reasons)
    assert step(PolicyState(), verdict(gate=0.9), QUIET)[1].action is Action.FLAG
    assert step(PolicyState(), verdict(gate=0.9), LOOPING, code_first=False)[1].action is Action.FLAG


def test_code_tier_cools_down_then_escalates():
    state, actions = PolicyState(), []
    for turn in range(10, 20):
        state, decision = step(state, None, looping_at(turn))
        actions.append(decision.action)
    assert actions[:4] == [Action.HINT, Action.CONTINUE, Action.CONTINUE, Action.HINT]
    assert actions[6] is Action.ESCALATE and Action.KILL not in actions


def test_escalation_repeats_at_most_every_reescalate_turns():
    state, actions = PolicyState(), []
    for turn in range(10, 40):
        state, decision = step(state, STALLED, looping_at(turn))
        actions.append((turn, decision.action))
    escalations = [turn for turn, action in actions if action is Action.ESCALATE]
    assert len(escalations) >= 2
    gaps = [b - a for a, b in zip(escalations, escalations[1:], strict=False)]
    assert all(gap >= Thresholds().reescalate_turns for gap in gaps)
    # in between, neither the judged path nor the code tier repeats the message
    assert [a for _, a in actions].count(Action.HINT) == Thresholds().max_hints


def test_code_tier_escalation_is_rate_limited_too():
    state, actions = PolicyState(), []
    for turn in range(10, 30):
        state, decision = step(state, None, looping_at(turn))
        actions.append(decision.action)
    first = actions.index(Action.ESCALATE)
    assert Action.ESCALATE not in actions[first + 1:first + Thresholds().reescalate_turns]
    assert actions[first + Thresholds().reescalate_turns] is Action.ESCALATE
