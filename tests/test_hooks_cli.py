from __future__ import annotations

import io
import json

import pytest
from conftest import make_turn
from fakes import FakeProvider, hint_answers, stalled_answers

from unwedge import cli, hooks
from unwedge.code_signals import compute_signals
from unwedge.config import Settings
from unwedge.guard import GuardOutcome
from unwedge.policy import Action, Decision
from unwedge.replay import guess_harness, recent_transcripts, replay_file
from unwedge.report import format_report, load_ledger, summarize


def run_hook(payload: dict, monkeypatch, tmp_path, **env) -> str:
    monkeypatch.setenv("UNWEDGE_HOME", str(tmp_path))
    for key in ("UNWEDGE_PROVIDER", "UNWEDGE_MODE", "TYPESAFE_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    out = io.StringIO()
    assert hooks.main(io.StringIO(json.dumps(payload)), out) == 0
    return out.getvalue()


def failing_bash(session="s1", **extra):
    return {"hook_event_name": "PostToolUseFailure", "session_id": session, "tool_name": "Bash",
            "tool_input": {"command": "pytest -x"}, "error": "Exit code 1\nAssertionError: boom", **extra}


def test_hint_mode_injects_a_code_tier_hint_on_a_blatant_loop(monkeypatch, tmp_path):
    run_hook({"hook_event_name": "UserPromptSubmit", "session_id": "s1", "prompt": "fix the test"},
             monkeypatch, tmp_path, UNWEDGE_MODE="hint")
    outputs = [run_hook(failing_bash(), monkeypatch, tmp_path, UNWEDGE_MODE="hint") for _ in range(4)]
    assert outputs[:3] == ["", "", ""]
    response = json.loads(outputs[3])
    context = response["hookSpecificOutput"]["additionalContext"]
    assert response["hookSpecificOutput"]["hookEventName"] == "PostToolUseFailure" and "4 times" in context
    ledger = load_ledger(tmp_path)
    assert len(ledger) == 4 and ledger[-1]["action"] == "hint" and ledger[-1]["harness"] == "claude-code"


def test_shadow_mode_is_silent_but_records(monkeypatch, tmp_path):
    outputs = [run_hook(failing_bash(), monkeypatch, tmp_path) for _ in range(4)]
    assert outputs == ["", "", "", ""]
    assert load_ledger(tmp_path)[-1]["action"] == "hint"


def test_codex_payloads_are_detected(monkeypatch, tmp_path):
    payload = {"hook_event_name": "PostToolUse", "session_id": "c1", "turn_id": "t", "tool_name": "Bash",
               "tool_input": {"command": "pytest -x"}, "tool_response": "Process exited with code 1\nFAILED"}
    for _ in range(4):
        run_hook(payload, monkeypatch, tmp_path, UNWEDGE_MODE="hint")
    assert (tmp_path / "sessions" / "codex" / "c1" / "turns.jsonl").exists()
    assert hooks.detect_harness({"transcript_path": "/home/u/.codex/sessions/x.jsonl"}) == "codex"
    assert hooks.detect_harness({"transcript_path": "/home/u/.claude/projects/p/s.jsonl"}) == "claude-code"


def test_hook_never_breaks_the_agent(monkeypatch, tmp_path):
    monkeypatch.setenv("UNWEDGE_HOME", str(tmp_path))
    out = io.StringIO()
    assert hooks.main(io.StringIO("{not json"), out) == 0 and out.getvalue() == ""
    assert "Traceback" in (tmp_path / "errors.log").read_text(encoding="utf-8")
    assert run_hook({"hook_event_name": "Notification"}, monkeypatch, tmp_path) == ""
    assert run_hook({"hook_event_name": "SessionStart", "session_id": "x"}, monkeypatch, tmp_path) == ""
    assert run_hook(failing_bash(), monkeypatch, tmp_path, UNWEDGE_PROVIDER="jev") == ""  # no key: code tier


def test_hook_uses_the_provider_and_replays_stored_verdicts(monkeypatch, tmp_path):
    provider = FakeProvider(stalled_answers(), hint_answers())
    monkeypatch.setattr(Settings, "make_provider", lambda self: provider)
    outputs = [run_hook(failing_bash(), monkeypatch, tmp_path, UNWEDGE_MODE="hint") for _ in range(3)]
    assert json.loads(outputs[2])["hookSpecificOutput"]["additionalContext"].startswith("[UNWEDGE]")
    assert provider.closed
    verdicts = (tmp_path / "sessions" / "claude-code" / "s1" / "verdicts.jsonl").read_text(encoding="utf-8")
    assert verdicts.count('"stall": 0.95') == 2  # turns 2 and 3 were judged; turn 1 was not gated


def outcome(action: Action, hint: str | None = None) -> GuardOutcome:
    code = compute_signals([make_turn(1, "ls", "a")])[0]
    return GuardOutcome(turn=1, decision=Decision(action, ("stall=0.95",)), gated=True, enforced=True, code=code,
                        hint_text=hint)


@pytest.mark.parametrize(
    ("action", "mode", "harness", "expect"),
    [
        (Action.KILL, "stop", "claude-code", "stop"),
        (Action.KILL, "stop", "codex", "system"),
        (Action.ESCALATE, "hint", "codex", "system"),
        (Action.FLAG, "hint", "claude-code", None),
        (Action.FLAG, "stop", "codex", None),
        (Action.HINT, "hint", "claude-code", "hint"),
        (Action.CASCADE, "hint", "claude-code", None),
        (Action.HINT, "shadow", "claude-code", None),
    ],
)
def test_render_per_mode_and_harness(action, mode, harness, expect):
    hint = "Read the last error message literally." if expect == "hint" else None
    response = hooks.render(outcome(action, hint), mode, harness, "PostToolUse")
    if expect is None:
        assert response is None
    elif expect == "stop":
        assert response["continue"] is False and "unwedge stopped" in response["stopReason"]
        # an async hook ignores `continue`, so the escalation must still reach the agent
        assert response["hookSpecificOutput"]["additionalContext"] == hooks.ESCALATE_TEXT
    elif expect == "system":
        assert "systemMessage" in response and response["hookSpecificOutput"]["additionalContext"]
    else:
        assert response["hookSpecificOutput"]["additionalContext"] == f"[UNWEDGE] {hint}"
        assert "systemMessage" not in response


def test_report_summarizes_the_ledger(monkeypatch, tmp_path):
    for _ in range(4):
        run_hook(failing_bash(cwd="/repo"), monkeypatch, tmp_path)
    lines = format_report(summarize(load_ledger(tmp_path)))
    assert "turn 4" in lines[1] and "1 with a loop alarm" in lines[-1]
    assert format_report([])[0].startswith("No guarded sessions")


def write_transcript(path):
    entries = [{"type": "user", "message": {"content": "fix it"}}]
    for i in range(5):
        entries.append({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": f"t{i}", "name": "Bash", "input": {"command": "pytest -x"}}]}})
        entries.append({"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": f"t{i}", "is_error": True, "content": "Exit code 1 boom"}]}})
    path.write_text("\n".join(json.dumps(e) for e in entries), encoding="utf-8")


def test_replay_and_cli(tmp_path, monkeypatch, capsys):
    path = tmp_path / "session.jsonl"
    write_transcript(path)
    result = replay_file(path)
    assert result.harness == "claude-code" and len(result.turns) == 5
    assert result.first_intervention == 4 and result.turns_after_first_intervention == 1
    assert guess_harness("/x/.codex/sessions/2026/rollout-1.jsonl") == "codex"
    assert cli.main(["replay", str(path)]) == 0
    assert "first alarm: turn 4" in capsys.readouterr().out
    monkeypatch.setattr("unwedge.replay.recent_transcripts", lambda limit=20: [path])
    assert cli.main(["scan"]) == 0
    assert "1 of 1 sessions show a loop alarm" in capsys.readouterr().out
    monkeypatch.setenv("UNWEDGE_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.delenv("UNWEDGE_PROVIDER", raising=False)
    assert cli.main(["report"]) == 0 and "No guarded sessions" in capsys.readouterr().out
    assert cli.main(["doctor"]) == 0 and "code-only tier" in capsys.readouterr().out
    assert cli.main(["doctor", "--provider", "jev"]) == 1
    assert cli.main(["serve", "--host", "0.0.0.0"]) == 2


def test_recent_transcripts_finds_both_harnesses(tmp_path, monkeypatch):
    (tmp_path / ".claude" / "projects" / "p").mkdir(parents=True)
    (tmp_path / ".claude" / "projects" / "p" / "a.jsonl").write_text("{}", encoding="utf-8")
    rollout_dir = tmp_path / ".codex" / "sessions" / "2026" / "09" / "23"
    rollout_dir.mkdir(parents=True)
    (rollout_dir / "rollout-x.jsonl").write_text("{}", encoding="utf-8")
    monkeypatch.delenv("CODEX_HOME", raising=False)
    found = recent_transcripts(home=tmp_path)
    assert {p.name for p in found} == {"a.jsonl", "rollout-x.jsonl"}


def test_cli_reports_invalid_settings(monkeypatch, capsys):
    monkeypatch.setenv("UNWEDGE_PROVIDER", "laya-local")
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["doctor"])
    assert exit_info.value.code == 2 and "unwedge serve" in capsys.readouterr().err
