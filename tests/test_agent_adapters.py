from __future__ import annotations

import json

from unwedge.adapters import claude_code, codex
from unwedge.turns import ToolClass


def cc(tool_name, tool_input, tool_response=None, *, failed=False, error=None):
    return {"hook_event_name": "PostToolUseFailure" if failed else "PostToolUse", "session_id": "s",
            "tool_name": tool_name, "tool_input": tool_input, "tool_response": tool_response, "error": error}


def test_claude_code_bash_success_and_failure():
    ok = claude_code.turn_from_hook(cc("Bash", {"command": "pytest -x"}, {"stdout": "1 passed", "stderr": ""}), 1)
    assert (ok.tool, ok.tool_class, ok.is_error, ok.observation) == ("pytest", ToolClass.RUN, False, "1 passed")
    bad = claude_code.turn_from_hook(cc("Bash", {"command": "pytest -x"}, failed=True,
                                        error="Exit code 1\nAssertionError: boom"), 2)
    assert bad.is_error and "AssertionError" in bad.observation and not bad.changes_state


def test_claude_code_tool_mapping():
    read = claude_code.turn_from_hook(cc("Read", {"file_path": "/r/a.py", "offset": 10},
                                         {"type": "text", "file": {"filePath": "/r/a.py", "content": "x = 1\ny = 2",
                                                                   "startLine": 10, "totalLines": 300}}), 1)
    assert read.tool_class is ToolClass.NAVIGATE and read.command == "read /r/a.py offset=10"
    assert "[File: /r/a.py (300 lines total)]" in read.observation and "11:y = 2" in read.observation
    edit = claude_code.turn_from_hook(cc("Edit", {"file_path": "/r/a.py", "old_string": "a", "new_string": "b"},
                                         {"filePath": "/r/a.py", "structuredPatch": []}), 2)
    assert edit.tool_class is ToolClass.EDIT and edit.changes_state and edit.observation == "(edit applied) /r/a.py"
    write = claude_code.turn_from_hook(cc("Write", {"file_path": "/r/b.py", "content": "print(1)"},
                                          {"type": "create", "filePath": "/r/b.py"}), 3)
    assert write.tool == "create" and write.command.startswith("create /r/b.py\n")
    grep = claude_code.turn_from_hook(cc("Grep", {"pattern": "foo", "path": "/r"},
                                         {"filenames": ["/r/a.py", "/r/b.py"], "numFiles": 2}), 4)
    assert grep.tool_class is ToolClass.SEARCH and grep.observation.startswith("Found 2 files")
    assert claude_code.turn_from_hook(cc("TodoWrite", {"todos": []}), 5) is None
    mcp = claude_code.turn_from_hook(cc("mcp__db__query", {"sql": "select 1"}, [{"type": "text", "text": "1"}]), 6)
    assert mcp.tool_class is ToolClass.RUN and mcp.observation == "1"
    agent = claude_code.turn_from_hook(cc("Agent", {"subagent_type": "Explore", "description": "find x"}, "done"), 7)
    assert agent.command == "agent Explore: find x"


def test_claude_code_scrubs_secrets():
    turn = claude_code.turn_from_hook(cc("Bash", {"command": "curl -H 'Authorization: Bearer abcdefghijklmnop123'"},
                                         {"stdout": "token=supersecret123"}), 1)
    assert "abcdefghijklmnop123" not in turn.command and "supersecret123" not in turn.observation


def test_claude_code_transcript(tmp_path):
    path = tmp_path / "s.jsonl"
    lines = [
        {"type": "user", "message": {"content": "<command-name>/clear</command-name>"}},
        {"type": "user", "message": {"content": "Fix the failing test"}},
        {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t1", "name": "Bash",
                                                       "input": {"command": "pytest"}}]}},
        {"type": "user", "toolUseResult": {"stdout": "", "stderr": "boom"},
         "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "is_error": True,
                                  "content": [{"type": "text", "text": "Exit code 1 boom"}]}]}},
        {"type": "assistant", "isSidechain": True, "message": {"content": [{"type": "tool_use", "id": "t9",
                                                                            "name": "Read", "input": {}}]}},
        {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t2", "name": "Read",
                                                       "input": {"file_path": "/a.py"}}]}},
        {"type": "user", "toolUseResult": {"file": {"filePath": "/a.py", "content": "x", "totalLines": 1}},
         "message": {"content": [{"type": "tool_result", "tool_use_id": "t2", "content": "x"}]}},
    ]
    path.write_text("\n".join(json.dumps(x) for x in lines) + "\nnot json\n", encoding="utf-8")
    goal, events = claude_code.read_transcript(path)
    assert goal == "Fix the failing test" and len(events) == 2
    assert events[0]["hook_event_name"] == "PostToolUseFailure" and events[0]["error"] == "Exit code 1 boom"
    assert events[1]["tool_response"]["file"]["filePath"] == "/a.py"


def test_codex_hook_payloads():
    payload = {"hook_event_name": "PostToolUse", "turn_id": "t", "tool_name": "Bash",
               "tool_input": {"command": "bash -lc 'pytest -x'"},
               "tool_response": "Process exited with code 1\nFAILED tests/test_a.py"}
    turn = codex.turn_from_hook(payload, 1)
    assert turn.command == "pytest -x" and turn.tool == "pytest" and turn.is_error
    clean = codex.turn_from_hook({**payload, "tool_input": {"command": ["cat", "a.py"]},
                                  "tool_response": "Process exited with code 0\nprint(1)"}, 2)
    assert clean.tool_class is ToolClass.NAVIGATE and not clean.is_error
    patch = "*** Begin Patch\n*** Update File: src/a.py\n@@\n-x\n+y\n*** End Patch"
    edit = codex.turn_from_hook({"tool_name": "apply_patch", "tool_input": {"command": patch},
                                 "tool_response": "Success. Updated the following files:\nM src/a.py"}, 3)
    assert edit.tool_class is ToolClass.EDIT and edit.changes_state
    assert edit.command.startswith("apply_patch src/a.py\n")
    mcp = codex.turn_from_hook({"tool_name": "mcp__gh__search", "tool_input": {"q": "x"}, "tool_response": {"n": 1}}, 4)
    assert mcp.tool_class is ToolClass.RUN and mcp.observation == '{"n": 1}'
    assert codex.turn_from_hook({"tool_name": ""}, 5) is None
    assert codex.exit_code("no code here") is None and codex.shell_command(None) == ""


def test_codex_rollout(tmp_path):
    path = tmp_path / "rollout-2026-09-23T10-00-00-abc.jsonl"
    items = [
        {"type": "response_item", "payload": {"type": "message", "role": "user",
                                              "content": [{"type": "input_text", "text": "<environment_context>"}]}},
        {"type": "event_msg", "payload": {"type": "user_message", "message": "fix the test"}},
        {"type": "response_item", "payload": {"type": "function_call", "name": "exec_command", "call_id": "c1",
                                              "arguments": json.dumps({"cmd": "pytest -x"})}},
        {"type": "response_item", "payload": {"type": "function_call_output", "call_id": "c1",
                                              "output": "Process exited with code 1\nFAILED"}},
        {"type": "response_item", "payload": {"type": "custom_tool_call", "call_id": "c2", "name": "apply_patch",
                                              "input": "*** Begin Patch\n*** Add File: b.py\n+x\n*** End Patch"}},
        {"type": "response_item", "payload": {"type": "custom_tool_call_output", "call_id": "c2",
                                              "output": {"output": "Success"}}},
    ]
    path.write_text("\n".join(json.dumps(x) for x in items), encoding="utf-8")
    goal, events = codex.read_rollout(path)
    assert goal == "fix the test" and [e["tool_name"] for e in events] == ["Bash", "apply_patch"]
    assert codex.turn_from_hook(events[0], 1).is_error and events[1]["tool_response"] == "Success"


def test_generic_turn_from_command():
    from unwedge.adapters.generic import turn_from_command

    failing = turn_from_command(1, "pytest -x", "Traceback (most recent call last):\nValueError: x")
    assert failing.is_error and failing.tool == "pytest" and failing.tool_class is ToolClass.RUN
    write = turn_from_command(2, "save notes.md", "ok", failed=False, tool_class=ToolClass.EDIT)
    assert write.changes_state and not write.is_error
    secret = "sk_live_4eC39HqLyjWDarjtT1zdp7dc"
    assert secret not in turn_from_command(3, f"echo {secret}", "").command


def test_claude_code_failed_edit_arrives_as_a_failure_event():
    # PostToolUse is success-only in Claude Code; a failed Edit comes as PostToolUseFailure
    edit = {"file_path": "a.py", "old_string": "x", "new_string": "y"}
    failed = claude_code.turn_from_hook(cc("Edit", edit, failed=True, error="String to replace not found in file."), 3)
    assert failed.tool_class is ToolClass.EDIT and failed.is_error and not failed.changes_state
    applied = claude_code.turn_from_hook(cc("Edit", edit, {"filePath": "a.py", "oldString": "x", "newString": "y"}), 4)
    assert applied.changes_state and not applied.is_error and applied.observation == "(edit applied) a.py"


def test_claude_code_transcript_goal_skips_injected_skill_text(tmp_path):
    entries = [
        {"type": "user", "isMeta": True, "message": {"content": [
            {"type": "text", "text": "Base directory for this skill: /home/me/.claude/plugins/x"}]}},
        {"type": "user", "message": {"content": "Fix the flaky login test"}},
    ]
    path = tmp_path / "t.jsonl"
    path.write_text("\n".join(json.dumps(e) for e in entries), encoding="utf-8")
    goal, _ = claude_code.read_transcript(path)
    assert goal == "Fix the flaky login test"
