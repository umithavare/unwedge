"""Adapter for SWE-agent transcripts (the nebius/SWE-agent-trajectories format).

A transcript is a list of {role, text} messages: system, the task (user), then
alternating ai (thought + one fenced command) and user (observation). Harness
boilerplate is rewritten into short status text here, because only the adapter
knows which words are the harness talking and which are the tool's output.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from unwedge.normalize import classify_command, looks_like_error
from unwedge.scrub import scrub
from unwedge.turns import Session, ToolClass, Turn

OUTPUT_PRICE_MULTIPLIER = 4.0  # output tokens cost ~4x input tokens on typical price sheets
CHARS_PER_TOKEN = 4.0

_FENCE = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)
_FOOTER = re.compile(r"\n*\(Open file: [^\n]*\)\s*\n\(Current directory: [^\n]*\)\s*\n?bash-\$\s*$")
_EDIT_OK = re.compile(
    r"File updated\. Please review the changes and make sure they are correct"
    r" \(correct indentation, no duplicate lines, etc\)\. Edit the file again if necessary\.")
_EDIT_REJECTED = re.compile(r"Your proposed edit has introduced new syntax error\(s\)")
_REJECTED_ERRORS = re.compile(r"ERRORS:\s*\n((?:- .*\n?)+)")
_NO_OUTPUT = "Your command ran successfully and did not produce any output."
_FORMAT_ERROR = re.compile(r"Your output (?:was not formatted correctly|contained)")
_ISSUE = re.compile(r"ISSUE:\s*\n(.*?)(?:\n\s*INSTRUCTIONS:|\Z)", re.DOTALL)


def extract_goal(task_text: str) -> str:
    match = _ISSUE.search(task_text)
    return scrub((match.group(1) if match else task_text).strip())


def extract_command(ai_text: str) -> str:
    blocks = _FENCE.findall(ai_text)
    return blocks[-1].strip() if blocks else ""


def clean_observation(raw: str) -> tuple[str, bool | None]:
    """Strip the prompt footer and rewrite harness messages.

    Returns the cleaned text and, when the harness itself says whether an edit was
    applied, that verdict (True applied, False rejected, None not an edit message).
    """
    text = _FOOTER.sub("", raw).rstrip()
    if _EDIT_REJECTED.search(text):
        errors = _REJECTED_ERRORS.search(text)
        detail = " ".join(line[2:].strip() for line in errors.group(1).splitlines()) if errors else "syntax error"
        return f"edit REJECTED, not applied: {detail}", False
    if _EDIT_OK.search(text):
        return _EDIT_OK.sub("", text).rstrip() + "\n(edit applied)", True
    if text.strip() == _NO_OUTPUT:
        return "(no output)", None
    return text, None


def parse_transcript(messages: Sequence[Mapping[str, str]]) -> tuple[str, tuple[Turn, ...]]:
    """Return (goal, turns) for one transcript."""
    task_index = next((i for i, m in enumerate(messages) if m["role"] == "user"), None)
    if task_index is None:
        return "", ()
    goal = extract_goal(messages[task_index]["text"])
    context_chars = sum(len(m["text"] or "") for m in messages[: task_index + 1])
    turns: list[Turn] = []
    i = task_index + 1
    while i < len(messages):
        if messages[i]["role"] != "ai":
            context_chars += len(messages[i]["text"] or "")
            i += 1
            continue
        ai_text = messages[i]["text"] or ""
        raw_obs = messages[i + 1]["text"] if i + 1 < len(messages) and messages[i + 1]["role"] == "user" else ""
        turns.append(_build_turn(len(turns) + 1, ai_text, raw_obs or "", context_chars))
        context_chars += len(ai_text) + len(raw_obs or "")
        i += 2
    return goal, tuple(turns)


def _build_turn(index: int, ai_text: str, raw_obs: str, context_chars: int) -> Turn:
    command = scrub(extract_command(ai_text))
    tool, tool_class = classify_command(command)
    observation, edit_verdict = clean_observation(scrub(raw_obs))
    if _FORMAT_ERROR.search(raw_obs) or not command:
        tool_class, observation = ToolClass.INVALID, "(the agent produced no valid command)"
    applied = edit_verdict if edit_verdict is not None else (tool_class is ToolClass.EDIT)
    is_error = tool_class is ToolClass.INVALID or edit_verdict is False or looks_like_error(observation, tool_class)
    cost = (context_chars + OUTPUT_PRICE_MULTIPLIER * len(ai_text)) / CHARS_PER_TOKEN
    return Turn(
        index=index,
        command=command,
        tool=tool,
        tool_class=tool_class,
        observation=observation,
        is_error=is_error,
        changes_state=tool_class is ToolClass.EDIT and applied and not is_error,
        cost_units=cost,
    )


def session_from_row(row: Mapping, group: str) -> Session:
    goal, turns = parse_transcript(row["trajectory"])
    return Session(
        session_id=str(row["instance_id"]),
        group=group,
        resolved=bool(row["target"]),
        exit_status=str(row["exit_status"]),
        goal=goal,
        turns=turns,
    )
