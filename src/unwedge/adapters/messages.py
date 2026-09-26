"""Adapter for chat-message traces, the format most agent loops and datasets use.

Three common ways of writing tool use are recognized:

- ``tool_calls``: OpenAI-style function calling (assistant ``tool_calls`` answered by ``tool``
  messages), used by OpenHands and most custom loops;
- ``function_markup``: SWE-agent's ``<function=bash><parameter=command>...</parameter></function>``
  written into the assistant text;
- ``bash_blocks``: one fenced bash block per assistant message, answered with
  ``<returncode>N</returncode><output>...</output>`` (mini-swe-agent).

Shell tools, the common file editor (``str_replace_editor``) and finish/submit calls are mapped
onto Turns; anything else becomes a generic RUN turn. Text is scrubbed of secrets.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from unwedge.normalize import classify_command, looks_like_error
from unwedge.scrub import scrub
from unwedge.turns import ToolClass, Turn

MAX_OBSERVATION_CHARS = 8000
OUTPUT_PRICE_MULTIPLIER = 4.0  # output tokens cost ~4x input tokens on typical price sheets
CHARS_PER_TOKEN = 4.0

SHELL_TOOLS = {"bash", "execute_bash", "shell", "run_shell", "terminal", "run_command", "cmd_run"}
EDITOR_TOOLS = {"str_replace_editor", "str_replace_based_edit_tool", "file_editor", "edit_file"}
SUBMIT_TOOLS = {"submit", "finish", "task_complete", "attempt_completion"}
SILENT_TOOLS = {"think"}  # no effect on the world, no progress signal

_FUNCTION = re.compile(r"<function=([\w\-.]+)>(.*?)</function>", re.S)
_PARAMETER = re.compile(r"<parameter=([\w\-.]+)>(.*?)</parameter>", re.S)
_BASH_BLOCK = re.compile(r"```(?:bash|sh|shell)?[ \t]*\n(.*?)```", re.S)
_EXIT_LINE = re.compile(r"\[Command finished with exit code (-?\d+)\]")
_INTERPRETER_LINE = re.compile(r"^\[Python Interpreter: [^\]]*\]\s*$", re.M)
_RETURNCODE = re.compile(r"<returncode>(-?\d+)</returncode>")
_OUTPUT = re.compile(r"<output>\n?(.*?)</output>", re.S)
_PR = re.compile(r"<pr_description>\s*(.*?)\s*</pr_description>", re.S)
_EDITOR_FAILURE = re.compile(
    r"^(?:ERROR\b|No replacement was performed|Invalid `?\w+`? parameter|Parameter `\w+` is required"
    r"|The path \S+ does not exist|The `view_range` parameter|No match|Did not find)", re.M)
_NO_OUTPUT = "Your command ran successfully and did not produce any output."
_SUBMIT_MARKERS = ("COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT", "MINI_SWE_AGENT_FINAL_OUTPUT")


@dataclass(frozen=True)
class _Step:
    name: str
    args: Mapping[str, Any]
    observation: str
    exit_code: int | None
    cost_units: float


def _text(message: Mapping[str, Any]) -> str:
    content = message.get("content")
    if isinstance(content, list):  # content parts
        return "\n".join(str(part.get("text", "")) if isinstance(part, Mapping) else str(part) for part in content)
    return "" if content is None or content == "None" else str(content)


def detect_style(messages: Sequence[Mapping[str, Any]]) -> str:
    assistant = [m for m in messages if m.get("role") == "assistant"]
    if any(m.get("tool_calls") for m in assistant):
        return "tool_calls"
    if any("<function=" in _text(m) for m in assistant):
        return "function_markup"
    if any(_BASH_BLOCK.search(_text(m)) for m in assistant):
        return "bash_blocks"
    return "unknown"


def extract_goal(messages: Sequence[Mapping[str, Any]], limit: int = 4000) -> str:
    """The task: the PR description when the prompt has one, else the first user message."""
    first = next((_text(m) for m in messages if m.get("role") == "user"), "")
    match = _PR.search(first)
    return scrub((match.group(1) if match else first).strip())[:limit]


def session_turns(messages: Sequence[Mapping[str, Any]], style: str | None = None) -> tuple[Turn, ...]:
    """Turns for one trace; an empty tuple when no tool use is recognized."""
    style = style or detect_style(messages)
    steps = {"tool_calls": _tool_call_steps, "function_markup": _markup_steps,
             "bash_blocks": _bash_block_steps}.get(style, lambda _: [])(messages)
    turns: list[Turn] = []
    carried = 0.0  # a model call spent on a silent tool is paid by the next real turn
    for step in steps:
        if step.name.lower() in SILENT_TOOLS:
            carried += step.cost_units
            continue
        turns.append(_turn(len(turns) + 1, replace(step, cost_units=step.cost_units + carried)))
        carried = 0.0
    if carried and turns:
        turns[-1] = replace(turns[-1], cost_units=turns[-1].cost_units + carried)
    return tuple(turns)


def _answered(messages: Sequence[Mapping[str, Any]], i: int) -> bool:
    """The harness replied to assistant message i (so a message without an action was a failed
    step, not the agent's closing words)."""
    return i + 1 < len(messages) and messages[i + 1].get("role") in ("user", "tool")


def _invalid_step(cost: float) -> _Step:
    return _Step("bash", {"command": ""}, "", None, cost)


# ---- styles -------------------------------------------------------------------------------

def _costs(messages: Sequence[Mapping[str, Any]]) -> dict[int, float]:
    """Cost of the model call behind each assistant message: its context plus its output."""
    context, costs = 0, {}
    for i, message in enumerate(messages):
        size = len(_text(message)) + len(json.dumps(message.get("tool_calls") or "", default=str))
        if message.get("role") == "assistant":
            costs[i] = (context + OUTPUT_PRICE_MULTIPLIER * size) / CHARS_PER_TOKEN
        context += size
    return costs


def _tool_call_steps(messages: Sequence[Mapping[str, Any]]) -> list[_Step]:
    by_id = {m.get("tool_call_id"): _text(m) for m in messages if m.get("role") == "tool" and m.get("tool_call_id")}
    costs, steps = _costs(messages), []
    for i, message in enumerate(messages):
        calls = message.get("tool_calls") or [] if message.get("role") == "assistant" else []
        if message.get("role") == "assistant" and not calls and _answered(messages, i):
            steps.append(_invalid_step(costs[i]))
            continue
        following = [_text(m) for m in messages[i + 1:i + 1 + len(calls)] if m.get("role") == "tool"]
        for n, call in enumerate(calls):
            function = call.get("function") or {}
            observation = by_id.get(call.get("id")) or (following[n] if n < len(following) else "")
            observation, exit_code = _openhands_observation(observation)
            steps.append(_Step(str(function.get("name") or ""), _arguments(function.get("arguments")),
                               observation, exit_code, costs[i] / len(calls)))
    return steps


def _markup_steps(messages: Sequence[Mapping[str, Any]]) -> list[_Step]:
    costs, steps = _costs(messages), []
    for i, message in enumerate(messages):
        if message.get("role") != "assistant":
            continue
        match = _FUNCTION.search(_text(message))
        if not match:
            if _answered(messages, i):
                steps.append(_invalid_step(costs[i]))
            continue
        args = {key: value.strip("\n") for key, value in _PARAMETER.findall(match.group(2))}
        reply = messages[i + 1] if i + 1 < len(messages) and messages[i + 1].get("role") != "assistant" else {}
        steps.append(_Step(match.group(1), args, _strip_observation(_text(reply)), None, costs[i]))
    return steps


def _bash_block_steps(messages: Sequence[Mapping[str, Any]]) -> list[_Step]:
    costs, steps = _costs(messages), []
    for i, message in enumerate(messages):
        if message.get("role") != "assistant":
            continue
        blocks = _BASH_BLOCK.findall(_text(message))
        reply = _text(messages[i + 1]) if i + 1 < len(messages) and messages[i + 1].get("role") != "assistant" else ""
        code = _RETURNCODE.search(reply)
        output = _OUTPUT.search(reply)
        observation = output.group(1) if output else reply
        if len(blocks) != 1 and not _answered(messages, i):
            continue  # closing words at the end of a trace, not a step
        command = blocks[0].strip() if len(blocks) == 1 else ""  # the harness rejects zero or several blocks
        steps.append(_Step("bash", {"command": command}, observation.strip(), int(code.group(1)) if code else None,
                           costs[i]))
    return steps


def _arguments(raw: Any) -> Mapping[str, Any]:
    if isinstance(raw, Mapping):
        return raw
    try:
        parsed = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {"raw": str(raw)}
    return parsed if isinstance(parsed, Mapping) else {"raw": parsed}


def _strip_observation(text: str) -> str:
    text = text.strip()
    if text.startswith("OBSERVATION:"):
        text = text[len("OBSERVATION:"):].strip()
    return "(no output)" if text == _NO_OUTPUT or not text else text


def _openhands_observation(text: str) -> tuple[str, int | None]:
    code = _EXIT_LINE.search(text)
    text = _INTERPRETER_LINE.sub("", _EXIT_LINE.sub("", text))
    return _strip_observation(text), int(code.group(1)) if code else None


# ---- mapping a step to a Turn -------------------------------------------------------------

def _turn(index: int, step: _Step) -> Turn:
    name = step.name.lower()
    observation = scrub(step.observation)[:MAX_OBSERVATION_CHARS]
    if name in EDITOR_TOOLS:
        command, tool, cls = _editor_command(step.args)
        is_error = bool(_EDITOR_FAILURE.search(observation))
    elif name in SUBMIT_TOOLS:
        command, tool, cls, is_error = "submit", "submit", ToolClass.SUBMIT, False
    elif name in SHELL_TOOLS:
        command = str(step.args.get("command") or "")
        if any(marker in command for marker in _SUBMIT_MARKERS):
            tool, cls = "submit", ToolClass.SUBMIT
        elif not command.strip():
            tool, cls = "", ToolClass.INVALID
        else:
            tool, cls = classify_command(command)
        is_error = _shell_error(cls, step.exit_code, observation)
    else:
        command = f"{step.name} {json.dumps(step.args, ensure_ascii=False, sort_keys=True, default=str)[:500]}"
        tool, cls = name or "tool", ToolClass.RUN
        is_error = looks_like_error(observation, cls)
    if cls is ToolClass.INVALID:
        observation = "(the agent produced no valid command)"
    command = scrub(command)
    return Turn(index=index, command=command, tool=tool, tool_class=cls, observation=observation,
                is_error=is_error, changes_state=cls is ToolClass.EDIT and not is_error, cost_units=step.cost_units)


def _editor_command(args: Mapping[str, Any]) -> tuple[str, str, ToolClass]:
    action, path = str(args.get("command") or ""), str(args.get("path") or "")
    if action == "view":
        window = args.get("view_range")
        return f"read {path}" + (f" {window}" if window else ""), "read", ToolClass.NAVIGATE
    if action == "create":
        return f"create {path}\n{args.get('file_text', '')}", "create", ToolClass.EDIT
    if action == "str_replace":
        body = json.dumps([args.get("old_str"), args.get("new_str")], ensure_ascii=False)
        return f"edit {path}\n{body}", "edit", ToolClass.EDIT
    if action == "insert":
        return f"edit {path} insert@{args.get('insert_line')}\n{args.get('new_str', '')}", "edit", ToolClass.EDIT
    if action == "undo_edit":
        return f"undo_edit {path}", "edit", ToolClass.EDIT
    return f"editor {action} {path}".strip(), "editor", ToolClass.RUN


def _shell_error(cls: ToolClass, exit_code: int | None, observation: str) -> bool:
    if cls is ToolClass.INVALID:
        return True
    if cls in (ToolClass.NAVIGATE, ToolClass.SEARCH, ToolClass.SUBMIT):
        # grep and friends exit non-zero on "no match": only tool-level failures count
        return looks_like_error(observation, cls)
    if exit_code is not None:
        return exit_code != 0
    return looks_like_error(observation, cls)
