from __future__ import annotations

from conftest import make_turn
from fakes import COMPACT_PROFILE, FULL_CALL_A, FakeProvider, hint_answers, stalled_answers

from unwedge.code_signals import compute_signals
from unwedge.guard import Guard, GuardConfig, code_hint, is_gated
from unwedge.policy import Action, Verdict
from unwedge.providers import ProviderRejected, ProviderTimeout
from unwedge.questions import BATTERIES, HINTS, render_hint


def looping_turns(n: int):
    return [make_turn(i, "python a.py", "ValueError: boom") for i in range(1, n + 1)]


def test_question_batteries_are_well_formed():
    for battery in BATTERIES.values():
        assert len(battery.call_a) == 8 and set(battery.call_a) == set(BATTERIES["full"].call_a)
        for question in (*battery.call_a.values(), *battery.call_b.values()):
            assert question["type"] in {"noul", "score", "choice"} and question["instructions"]
    assert set(BATTERIES["full"].call_b["intervention::best_hint"]["criteria"]) == set(HINTS)
    assert "3 times" in render_hint("H01_same_command_same_failure", repeats=3, turns=9)


def test_compact_battery_labels_map_back_to_hints():
    compact = BATTERIES["compact"]
    for label in compact.call_b["intervention::best_hint"]["criteria"]:
        assert compact.hint_id(label) in HINTS
    assert compact.hint_id("H99") is None
    assert BATTERIES["full"].hint_id("H03_error_text_ignored") == "H03_error_text_ignored"


def test_compact_battery_options_are_short():
    # Laya keeps at most 48 tokens per option; ~4 characters per token is a safe proxy
    for question in (*BATTERIES["compact"].call_a.values(), *BATTERIES["compact"].call_b.values()):
        criteria = question.get("criteria") or {}
        options = criteria.values() if isinstance(criteria, dict) else criteria
        assert all(len(str(option)) <= 150 for option in options)


def test_guard_hints_after_two_stalled_windows(tmp_path):
    provider = FakeProvider(stalled_answers(), hint_answers())
    ledger = tmp_path / "ledger.jsonl"
    guard = Guard("fix it", provider, GuardConfig(shadow=False), ledger=ledger)
    outcomes = [guard.on_turn(t) for t in looping_turns(3)]
    assert outcomes[0].gated is False and outcomes[1].gated is True
    assert outcomes[2].decision.action is Action.HINT and outcomes[2].enforced
    assert "3 times" in outcomes[2].hint_text
    assert len(ledger.read_text(encoding="utf-8").splitlines()) == 3
    assert outcomes[1].cost_usd > 0


def test_guard_uses_the_code_hint_when_no_library_hint_fits():
    # an unsure hint choice must not turn a hint into an escalation: the policy owns the severity
    for answers in (hint_answers("H03_error_text_ignored", confidence=0.2), hint_answers("H16_stop_and_escalate")):
        guard = Guard("fix it", FakeProvider(stalled_answers(), answers))
        outcome = [guard.on_turn(t) for t in looping_turns(3)][-1]
        assert outcome.decision.action is Action.HINT
        assert outcome.hint_id == "H01_same_command_same_failure" and "3 times" in outcome.hint_text


def test_guard_fails_open_and_uses_code_tier():
    guard = Guard("fix it", FakeProvider(None, fail=ProviderTimeout("slow")))
    outcomes = [guard.on_turn(t) for t in looping_turns(4)]
    assert outcomes[1].degraded.startswith("ProviderTimeout")
    assert outcomes[3].decision.action is Action.HINT  # code tier: 3 repeats with nothing changed
    assert outcomes[3].hint_id == "H01_same_command_same_failure" and not outcomes[3].enforced


def test_guard_without_provider_and_veto():
    offline = Guard("fix it", None)
    assert offline.on_turn(looping_turns(1)[0]).degraded is None
    assert [offline.on_turn(t) for t in looping_turns(3)[1:]][-1].degraded == "no provider (code-only tier)"
    vetoed = Guard("fix it", FakeProvider(stalled_answers(gate=0.9)))
    assert [vetoed.on_turn(t) for t in looping_turns(3)][-1].decision.action is Action.FLAG


def test_guard_fails_open_on_malformed_answers():
    broken = stalled_answers()
    del broken["stall::result_unchanged"]
    guard = Guard("fix it", FakeProvider(broken))
    outcomes = [guard.on_turn(t) for t in looping_turns(4)]
    assert outcomes[1].verdict is None and outcomes[1].degraded.startswith("malformed answers")
    assert outcomes[3].decision.action is Action.HINT  # the code tier still works


def test_guard_ignores_an_unknown_hint_id():
    guard = Guard("fix it", FakeProvider(stalled_answers(), hint_answers("H99_not_in_library")))
    outcome = [guard.on_turn(t) for t in looping_turns(3)][-1]
    assert outcome.decision.action is Action.HINT and outcome.hint_id == "H01_same_command_same_failure"


def test_guard_does_not_call_b_after_call_a_failed():
    provider = FakeProvider(None, fail=ProviderTimeout("slow"))
    guard = Guard("fix it", provider)
    outcomes = [guard.on_turn(t) for t in looping_turns(4)]
    assert outcomes[3].decision.action is Action.HINT
    assert all(questions is FULL_CALL_A for questions in provider.calls)  # no second hot-path round trip


def test_guard_uses_the_providers_layout_and_battery():
    provider = FakeProvider(stalled_answers(), hint_answers("H01"), profile=COMPACT_PROFILE)
    guard = Guard("fix it", provider)
    assert guard.config.battery == "compact" and guard.config.timeout_s == 5.0
    outcome = [guard.on_turn(t) for t in looping_turns(3)][-1]
    assert set(provider.states[0]) == {"goal", "latest", "recent"}
    assert provider.calls[0] is BATTERIES["compact"].call_a
    assert outcome.hint_id == "H01_same_command_same_failure"  # short label mapped back


def test_replay_rebuilds_policy_state_without_calls():
    provider = FakeProvider(stalled_answers(), hint_answers())
    live = Guard("fix it", provider, GuardConfig(shadow=False))
    live_outcomes = [live.on_turn(t) for t in looping_turns(3)]
    rebuilt = Guard("fix it", FakeProvider(None, fail=AssertionError("must not be called")))
    for turn, outcome in zip(looping_turns(2), live_outcomes[:2], strict=True):
        rebuilt.replay(turn, outcome.verdict)
    assert rebuilt.policy_state.stall_streak == 1  # turn 1 ungated, turn 2 stalled once
    verdict = Verdict(stall=0.95, p0=0.8, progress=0.3, terminal=0.01, drift=0.02, gate=0.02)
    assert rebuilt.replay(looping_turns(3)[2], verdict).action is Action.HINT


def test_set_goal_changes_the_state():
    provider = FakeProvider(stalled_answers(), hint_answers())
    guard = Guard("old goal", provider)
    guard.set_goal("new goal")
    for turn in looping_turns(2):
        guard.on_turn(turn)
    assert provider.states[-1]["goal"] == "new goal"


def test_gating_and_code_hint():
    turns = [make_turn(i, f"open a.py {i}", f"view {i}") for i in range(1, 7)]
    signals = compute_signals(turns)
    assert not is_gated(signals[1], GuardConfig())
    assert is_gated(signals[5], GuardConfig())  # periodic sample at turn 6 and a long read-only streak
    assert code_hint(signals[5]) == "H02_rereading_same_content"
    assert code_hint(compute_signals([make_turn(1, "python a.py", "ok")])[0]) == "H12_replan_from_summary"


def test_outcome_record_is_json_ready():
    outcome = Guard("g", None).on_turn(looping_turns(1)[0])
    record = outcome.to_record()
    assert record["decision"]["action"] == "continue" and record["turn"] == 1


def test_guard_scrubs_provider_errors_before_logging():
    echoed = "HTTP 400: {'echo': 'Authorization: Bearer sk-live-abcdefghijklmnopqrstuvwxyz0123'}"
    guard = Guard("fix it", FakeProvider(None, fail=ProviderRejected(echoed)))
    outcome = [guard.on_turn(t) for t in looping_turns(2)][-1]
    assert outcome.degraded.startswith("ProviderRejected") and "abcdefghijklmnopqrstuvwxyz" not in outcome.degraded
