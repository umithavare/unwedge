from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest
from conftest import make_turn

from unwedge.compactor import COMPACT_DIGEST, DigestConfig, build_state
from unwedge.config import Settings
from unwedge.policy import Verdict
from unwedge.store import LockTimeout, SessionStore, append_ledger, prune_sessions, safe_id


def test_settings_defaults_and_auto_provider(tmp_path):
    settings = Settings.from_env({"UNWEDGE_HOME": str(tmp_path)})
    assert (settings.provider, settings.mode, settings.home) == ("none", "shadow", tmp_path)
    auto = Settings.from_env({"TYPESAFE_API_KEY": "k"})
    assert auto.provider == "jev" and auto.api_key == "k" and "k" not in repr(auto)


def test_settings_read_claude_plugin_options():
    env = {"CLAUDE_PLUGIN_OPTION_PROVIDER": "laya", "CLAUDE_PLUGIN_OPTION_MODE": "hint",
           "CLAUDE_PLUGIN_OPTION_LAYA_URL": "http://box:8000/v1/systemone",
           "CLAUDE_PLUGIN_OPTION_LAYA_MODEL": "english"}
    settings = Settings.from_env(env)
    assert (settings.provider, settings.mode, settings.url, settings.model) == (
        "laya", "hint", "http://box:8000/v1/systemone", "english")
    assert Settings.from_env({**env, "UNWEDGE_MODE": "stop"}).mode == "stop"  # UNWEDGE_* wins
    assert Settings.from_env({"UNWEDGE_PROVIDER": "jev", "CLAUDE_PLUGIN_OPTION_TYPESAFE_API_KEY": "pk"}).api_key == "pk"
    assert Settings.from_env({"UNWEDGE_TIMEOUT": "1.5"}).timeout_s == 1.5


@pytest.mark.parametrize("env", [{"UNWEDGE_PROVIDER": "gpt"}, {"UNWEDGE_MODE": "yolo"},
                                 {"UNWEDGE_PROVIDER": "laya-local"}])
def test_settings_reject_unknown_values(env):
    with pytest.raises(ValueError):
        Settings.from_env(env)


def test_settings_make_provider():
    assert Settings.from_env({}).make_provider() is None
    laya = Settings.from_env({"UNWEDGE_PROVIDER": "laya", "LAYA_URL": "http://127.0.0.1:9/v1/systemone"}).make_provider()
    assert laya.url.endswith(":9/v1/systemone") and laya.profile.battery == "compact"


def test_session_store_round_trips(tmp_path):
    store = SessionStore(tmp_path, "claude-code", "abc/../x")
    assert store.dir.parent == tmp_path / "sessions" / "claude-code"  # separators removed: no traversal
    assert SessionStore(tmp_path, "claude-code", "..").dir.name == "unknown"
    store.add_prompt("fix the parser")
    store.add_prompt("also add a test")
    assert store.goal() == "fix the parser\n\nLatest instruction from the user: also add a test"
    assert store.next_index() == 1
    store.append_turn(make_turn(1, "python a.py", "x" * 10_000))
    store.append_turn(make_turn(2, "ls", "a.py"))
    turns = store.turns()
    assert [t.index for t in turns] == [1, 2] and len(turns[0].observation) <= 4000
    verdict = Verdict(stall=0.9, p0=0.7, progress=0.5, terminal=0.0, drift=0.1, gate=0.0)
    store.append_verdict(1, verdict)
    store.append_verdict(2, None)
    assert store.verdicts() == {1: verdict, 2: None}
    (store.dir / "turns.jsonl").open("a", encoding="utf-8").write("{torn line\n")
    assert len(store.turns()) == 2 and store.next_index() == 3


def test_session_store_lock(tmp_path):
    store = SessionStore(tmp_path, "codex", "s1")
    with store.lock(), pytest.raises(LockTimeout), store.lock(timeout=0.05):
        pass
    lock = store.dir / ".lock"
    lock.write_text("")
    old = time.time() - 120
    os.utime(lock, (old, old))
    with store.lock(timeout=0.5):  # a stale lock from a crashed hook is broken
        pass
    assert not lock.exists()


def test_ledger_and_prune(tmp_path):
    append_ledger(tmp_path, {"a": 1})
    assert json.loads((tmp_path / "ledger.jsonl").read_text(encoding="utf-8")) == {"a": 1}
    fresh = SessionStore(tmp_path, "claude-code", "new")
    fresh.add_prompt("x")
    stale = SessionStore(tmp_path, "claude-code", "old")
    stale.add_prompt("y")
    old = time.time() - 30 * 86400
    os.utime(stale.dir, (old, old))
    assert prune_sessions(tmp_path, retention_days=7) == 1
    assert fresh.dir.exists() and not stale.dir.exists()
    assert prune_sessions(Path(tmp_path) / "missing") == 0
    assert safe_id("") == "unknown"


def test_compact_layout_puts_newest_evidence_first():
    turns = [make_turn(i, f"python run.py --n {i}", f"output {i} " + "y" * 300) for i in range(1, 12)]
    state = build_state("goal " * 200, turns, COMPACT_DIGEST)
    assert list(state) == ["goal", "latest", "recent"]
    assert state["latest"]["turn"] == 11 and state["recent"][0].startswith("T10 ")
    assert len(json.dumps(state, ensure_ascii=False)) <= COMPACT_DIGEST.max_state_chars
    full = build_state("g", turns, DigestConfig())
    capped = build_state("g", turns, DigestConfig(max_state_chars=2000))
    assert len(json.dumps(capped, ensure_ascii=False)) <= 2000 < len(json.dumps(full, ensure_ascii=False))
    assert 0 < len(capped["window"]) < len(full["window"]) and capped["window"][-1].startswith("T11 ")
    with pytest.raises(ValueError):
        build_state("g", [], COMPACT_DIGEST)
