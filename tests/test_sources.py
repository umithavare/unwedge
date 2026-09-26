from __future__ import annotations

import pytest

pytest.importorskip("numpy", reason="the benchmark modules need numpy")

from sources import jetbrains_group, sample, swe_gym_group, swe_smith_group  # noqa: E402

from unwedge.turns import Session  # noqa: E402


def test_swe_smith_groups_by_resolution_and_budget_exit():
    assert swe_smith_group(True, [{"content": "Exit due to cost limit"}]) == "success"
    assert swe_smith_group(False, [{"content": "OBSERVATION:\nok Exit due to cost limit"}]) == "burn"
    assert swe_smith_group(False, [{"content": "Exit due to total execution time exceeded"}]) == "burn"
    assert swe_smith_group(False, [{"content": "input length and `max_tokens` exceed context limit"}]) == "burn"
    assert swe_smith_group(False, [{"content": "<function=submit>\n</function>"}]) == "wrong"


def test_swe_gym_groups_by_resolution_and_finish_call():
    finish = [{"role": "assistant", "tool_calls": [{"function": {"name": "finish"}}]}]
    cut = [{"role": "assistant", "tool_calls": [{"function": {"name": "str_replace_editor"}}]}]
    assert swe_gym_group(True, cut) == "success"
    assert swe_gym_group(False, finish) == "wrong"
    assert swe_gym_group(False, cut) == "burn"


def test_jetbrains_groups_by_exit_status():
    assert jetbrains_group("LimitsExceeded") == "limit"
    assert jetbrains_group("Submitted") == "submitted"


def test_sample_is_reproducible_and_respects_caps():
    sessions = [Session(f"s{i}", "success" if i % 3 else "burn", True, "", "", ()) for i in range(30)]
    first, again = sample(sessions, {"success": 5}), sample(sessions, {"success": 5})
    assert first == again
    assert sum(s.group == "success" for s in first) == 5 and sum(s.group == "burn" for s in first) == 10
