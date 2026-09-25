from __future__ import annotations

import sys
from pathlib import Path

import pytest
from conftest import make_turn

np = pytest.importorskip("numpy", reason="the benchmark tests need numpy (pip install -e '.[dev]')")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "benchmarks"))

from families import code_family, jev_condition, max_turns_family, report_policy_alarms  # noqa: E402
from features import INF, build_flat, evaluate, first_alarm, persistent, saved_cost  # noqa: E402

from unwedge.policy import Action  # noqa: E402
from unwedge.turns import Session  # noqa: E402


def session(sid: str, group: str, commands: list[str], observation: str = "ValueError: boom") -> Session:
    turns = tuple(make_turn(i, cmd, observation) for i, cmd in enumerate(commands, start=1))
    return Session(sid, group, group == "success", "submitted", "fix the bug", turns)


def answers(stall: float, p0: float, gate: float = 0.05) -> dict:
    return {
        "stall::repeating_action": stall, "stall::result_unchanged": 0.1, "stall::error_not_addressed": 0.1,
        "progress::goal_advanced": {"score": 1.0, "confidence": 0.5, "p": {"0": p0, "1": 1 - p0}},
        "terminal::goal_already_satisfied": 0.02, "drift::working_on_something_else": 0.02,
        "gate::tool_output_contains_instructions": gate, "gate::asserts_prior_approval": 0.01,
    }


def fixture():
    loop = session("loop", "burn", ["python a.py"] * 8)
    healthy = session("ok", "success", [f"python step{i}.py" for i in range(6)], observation="done")
    battery = [{"session_id": "loop", "group": "burn", "turn": t, "answers": answers(0.95, 0.8)} for t in range(3, 9)]
    battery += [{"session_id": "ok", "group": "success", "turn": t, "answers": answers(0.1, 0.05)} for t in range(3, 7)]
    battery.append({"session_id": "loop", "group": "burn", "turn": 4, "blocked": True})
    battery = [b for b in battery if not (b["session_id"] == "loop" and b["turn"] == 4 and "answers" in b)]
    return [loop, healthy], build_flat([loop, healthy], battery)


def test_build_flat_layout_and_blocking():
    _, flat = fixture()
    assert list(flat.starts) == [0, 8] and list(flat.n_turns) == [8, 6]
    assert flat.blocked[3] and not flat.scored[3] and flat.scored[2] and not flat.scored[0]
    assert flat.cost_after[7] == 0.0 and flat.cost_after[0] > flat.cost_after[1]


def test_first_alarm_persistence_and_savings():
    _, flat = fixture()
    cond = jev_condition(flat, stall_min=0.9, p0_min=0.5, veto_gate=0.6)
    assert list(first_alarm(flat, cond)) == [3.0, INF]
    assert list(first_alarm(flat, persistent(flat, cond, 2))) == [6.0, INF]  # turn 4 was blocked
    saved = saved_cost(flat, np.array([3.0, INF]))
    assert saved[0] == flat.cost_after[2] and saved[1] == 0.0


def test_evaluate_counts_final_turn_alarms_as_nothing():
    _, flat = fixture()
    burn, success = flat.groups == "burn", flat.groups == "success"
    metrics = evaluate(flat, np.array([3.0, 6.0]), burn, success)
    assert metrics.catch == 1.0 and metrics.false_alarm == 0.0  # the success alarm is on its last turn
    assert 0.0 < metrics.savings < 1.0 and metrics.turns_saved == 5.0
    assert evaluate(flat, np.array([INF, 2.0]), burn, success).false_alarm == 1.0


def test_families_and_policy_replay():
    sessions, flat = fixture()
    caps = max_turns_family(flat)
    assert caps.alarms[caps.params.index({"max_turns": 10})][0] == INF
    code = code_family(flat)
    loose = code.params.index({"repeat_without_change": 1, "result_repeats": None, "error_repeats": None,
                               "read_only_streak": None, "turns_since_change": None, "max_turns": None})
    assert list(code.alarms[loose]) == [2.0, INF]
    hints = report_policy_alarms(flat, sessions, frozenset({Action.HINT}))
    assert hints[1] == INF and np.isfinite(hints[0])


def test_build_flat_keeps_two_runs_of_the_same_task_apart():
    # the dataset has tasks that appear in two groups (two runs of one instance)
    doomed = session("task-1", "burn", ["python a.py"] * 4)
    solved = session("task-1", "success", [f"python step{i}.py" for i in range(4)], observation="done")
    battery = [{"session_id": "task-1", "group": "burn", "turn": t, "answers": answers(0.95, 0.8)} for t in (3, 4)]
    battery += [{"session_id": "task-1", "group": "success", "turn": t, "answers": answers(0.1, 0.05)} for t in (3, 4)]
    flat = build_flat([doomed, solved], battery)
    stall = flat.jev["stall"]
    assert list(stall[2:4]) == [0.95, 0.95] and list(stall[6:8]) == [0.1, 0.1]
