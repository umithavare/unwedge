from __future__ import annotations

import json

from unwedge.adapters.messages import detect_style, extract_goal, session_turns
from unwedge.turns import ToolClass

TASK = {"role": "user", "content": "<pr_description>\nFix the refund rounding bug\n</pr_description>\nMore text"}
SYSTEM = {"role": "system", "content": "You are a helpful assistant."}


def tool_call(call_id: str, name: str, **args) -> dict:
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}


def openai_trace() -> list[dict]:
    return [
        SYSTEM, TASK,
        {"role": "assistant", "content": "", "tool_calls": [tool_call("a", "str_replace_editor", command="view",
                                                                      path="/w/pay.py")]},
        {"role": "tool", "tool_call_id": "a", "content": "OBSERVATION:\nHere's the result of running `cat -n`"},
        {"role": "assistant", "content": "Run the tests", "tool_calls": [
            tool_call("b", "execute_bash", command="pytest -x"), tool_call("c", "think", thought="hmm")]},
        {"role": "tool", "tool_call_id": "b",
         "content": "OBSERVATION:\nFAILED test_pay.py::test_refund\n[Command finished with exit code 1]"},
        {"role": "tool", "tool_call_id": "c", "content": "Your thought has been logged."},
        {"role": "assistant", "content": "", "tool_calls": [tool_call("d", "str_replace_editor", command="str_replace",
                                                                      path="/w/pay.py", old_str="a", new_str="b")]},
        {"role": "tool", "tool_call_id": "d", "content": "OBSERVATION:\nThe file /w/pay.py has been edited. Here's"},
        {"role": "assistant", "content": "", "tool_calls": [tool_call("e", "str_replace_editor", command="str_replace",
                                                                      path="/w/pay.py", old_str="zz", new_str="b")]},
        {"role": "tool", "tool_call_id": "e",
         "content": "OBSERVATION:\nNo replacement was performed, old_str `zz` did not appear verbatim in /w/pay.py."},
        {"role": "assistant", "content": "", "tool_calls": [tool_call("f", "finish")]},
    ]


def test_openai_tool_calls_become_turns():
    messages = openai_trace()
    assert detect_style(messages) == "tool_calls"
    turns = session_turns(messages)
    assert [t.tool_class for t in turns] == [ToolClass.NAVIGATE, ToolClass.RUN, ToolClass.EDIT, ToolClass.EDIT,
                                             ToolClass.SUBMIT]
    view, test, edit, failed_edit, finish = turns
    assert view.command == "read /w/pay.py" and not view.is_error
    assert test.command == "pytest -x" and test.is_error and "exit code" not in test.observation
    assert edit.changes_state and not edit.is_error
    assert failed_edit.is_error and not failed_edit.changes_state
    assert finish.tool == "submit"
    assert [t.index for t in turns] == [1, 2, 3, 4, 5]
    assert all(t.cost_units > 0 for t in turns) and turns[-1].cost_units > turns[0].cost_units


def markup(name: str, **params) -> str:
    body = "".join(f"<parameter={k}>{v}</parameter>\n" for k, v in params.items())
    return f"Let me look.\n\n<function={name}>\n{body}</function>"


def test_function_markup_becomes_turns():
    messages = [
        SYSTEM, TASK,
        {"role": "assistant", "content": markup("bash", command="python repro.py")},
        {"role": "user", "content": "OBSERVATION:\nTraceback (most recent call last):\nValueError: boom"},
        {"role": "assistant", "content": markup("str_replace_editor", command="create", path="/t/fix.py",
                                                file_text="x = 1")},
        {"role": "user", "content": "OBSERVATION:\nFile created successfully at: /t/fix.py"},
        {"role": "assistant", "content": markup("bash", command="python repro.py")},
        {"role": "user", "content": "Your command ran successfully and did not produce any output."},
        {"role": "assistant", "content": markup("submit")},
    ]
    assert detect_style(messages) == "function_markup"
    run, create, rerun, submit = session_turns(messages)
    assert run.is_error and run.tool_class is ToolClass.RUN
    assert create.changes_state and create.command.startswith("create /t/fix.py")
    assert rerun.observation == "(no output)" and not rerun.is_error
    assert submit.tool_class is ToolClass.SUBMIT


def test_bash_blocks_become_turns():
    messages = [
        SYSTEM, TASK,
        {"role": "assistant", "content": "THOUGHT: find it\n\n```bash\ngrep -rn refund src\n```"},
        {"role": "user", "content": "<returncode>1</returncode>\n<output>\n</output>"},
        {"role": "assistant", "content": "THOUGHT: run\n\n```bash\npython -m pytest -q\n```"},
        {"role": "user", "content": "<returncode>2</returncode>\n<output>\nE   AssertionError\n</output>"},
        {"role": "assistant",
         "content": "THOUGHT: done\n\n```bash\necho COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT && git add -A\n```"},
    ]
    assert detect_style(messages) == "bash_blocks"
    grep, pytest_run, submit = session_turns(messages)
    assert grep.tool_class is ToolClass.SEARCH and not grep.is_error  # grep's exit 1 means "no match"
    assert pytest_run.is_error and "AssertionError" in pytest_run.observation
    assert submit.tool_class is ToolClass.SUBMIT


def test_goal_and_secrets():
    assert extract_goal([SYSTEM, TASK]) == "Fix the refund rounding bug"
    command = "export KEY=sk-live-abcdefghijklmnopqrstu"
    leaky = [SYSTEM, TASK, {"role": "assistant", "content": markup("bash", command=command)},
             {"role": "user", "content": "OBSERVATION:\nok"}]
    assert "abcdefghijklmnopqrstu" not in session_turns(leaky)[0].command


def test_unknown_or_empty_traces_give_no_turns():
    assert session_turns([]) == ()
    assert session_turns([SYSTEM, TASK, {"role": "assistant", "content": "I am thinking out loud."}]) == ()


def test_cost_of_skipped_think_calls_moves_to_the_next_turn():
    messages = [
        SYSTEM, TASK,
        {"role": "assistant", "content": "", "tool_calls": [tool_call("a", "think", thought="plan")]},
        {"role": "tool", "tool_call_id": "a", "content": "Your thought has been logged."},
        {"role": "assistant", "content": "", "tool_calls": [
            tool_call("b", "execute_bash", command="ls"), tool_call("c", "Think", thought="hm")]},
        {"role": "tool", "tool_call_id": "b", "content": "OBSERVATION:\na.py\n[Command finished with exit code 0]"},
        {"role": "tool", "tool_call_id": "c", "content": "Your thought has been logged."},
        {"role": "assistant", "content": "", "tool_calls": [tool_call("d", "execute_bash", command="pytest")]},
        {"role": "tool", "tool_call_id": "d", "content": "OBSERVATION:\nok\n[Command finished with exit code 0]"},
    ]
    from unwedge.adapters.messages import _costs

    turns = session_turns(messages)
    assert [t.command for t in turns] == ["ls", "pytest"]  # "think" in any case is skipped
    expected = sum(cost for i, cost in _costs(messages).items() if messages[i].get("tool_calls"))
    assert abs(sum(t.cost_units for t in turns) - expected) < 1e-6


def test_answered_messages_without_an_action_become_invalid_turns():
    messages = [
        SYSTEM, TASK,
        {"role": "assistant", "content": markup("bash", command="ls")},
        {"role": "user", "content": "OBSERVATION:\na.py"},
        {"role": "assistant", "content": "I think I should look around first."},
        {"role": "user", "content": "Your last output did not use any tool calls."},
        {"role": "assistant", "content": markup("bash", command="cat a.py")},
        {"role": "user", "content": "OBSERVATION:\nx = 1"},
        {"role": "assistant", "content": "All done, the fix is in place."},  # closing words, never answered
    ]
    turns = session_turns(messages)
    assert [t.tool_class for t in turns] == [ToolClass.SEARCH, ToolClass.INVALID, ToolClass.NAVIGATE]
    assert turns[1].is_error and turns[1].command == ""
