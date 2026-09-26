from __future__ import annotations

import json

import pytest
from conftest import make_turn

from unwedge.dataset import FORMAT, read_sessions, session_from_record, session_to_record, write_sessions
from unwedge.turns import Session, ToolClass


def sample_session(**overrides) -> Session:
    turns = (make_turn(1, "pytest -x", "FAILED test_a"), make_turn(2, "pytest -x", "FAILED test_a"))
    fields = {"session_id": "s1", "group": "burn", "resolved": False, "exit_status": "cost_limit",
              "goal": "fix it", "turns": turns, "source": "swe-smith", "model": "claude-3-7-sonnet"}
    return Session(**(fields | overrides))


def test_round_trip_keeps_every_field():
    session = sample_session()
    record = session_to_record(session, stuck_turn=2)
    assert record["format"] == FORMAT and record["stuck_turn"] == 2
    assert record["turns"][0]["tool_class"] == "run"
    assert session_from_record(json.loads(json.dumps(record))) == session


def test_jsonl_files_round_trip(tmp_path):
    path = tmp_path / "corpus.jsonl"
    sessions = [sample_session(), sample_session(session_id="s2", group="success", resolved=True)]
    assert write_sessions(path, sessions) == 2
    assert read_sessions(path) == sessions


def test_unlabelled_records_load_with_a_placeholder_group():
    record = session_to_record(sample_session())
    record.pop("group")
    record["outcome"] = None
    session = session_from_record(record)
    assert session.group == "unlabelled" and session.turns[0].tool_class is ToolClass.RUN


def test_bad_records_are_rejected():
    with pytest.raises(ValueError, match="format"):
        session_from_record({"format": "something-else/9", "turns": []})
    with pytest.raises(ValueError, match="tool_class"):
        record = session_to_record(sample_session())
        record["turns"][0]["tool_class"] = "teleport"
        session_from_record(record)
