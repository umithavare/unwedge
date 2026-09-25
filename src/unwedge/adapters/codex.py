"""Adapter for OpenAI Codex CLI: hook payloads (PostToolUse, Codex 0.124+) and, for
offline replay, rollout files (~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl).

Codex has no Read tool (files are read through the shell) and its PostToolUse payload
carries only the output text, not an exit code, so failures are read from the text.
The rollout format is internal to Codex; parsing is best-effort.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from unwedge.normalize import classify_command, looks_like_error
from unwedge.scrub import scrub
from unwedge.turns import ToolClass, Turn

SHELL_TOOLS = {"Bash", "shell", "exec_command", "local_shell", "unified_exec"}
_EXIT = re.compile(r"(?:Process exited with code|exit code:?)\s*(-?\d+)", re.IGNORECASE)
_PATCH_FILE = re.compile(r"^\*\*\* (?:Update|Add|Delete) File: (.+)$", re.MULTILINE)
_SHELL_WRAPPER = re.compile(r"^(?:bash|sh|zsh)\s+-l?c\s+(['\"]?)(.*)\1$", re.DOTALL)


def shell_command(value: Any) -> str:
    if isinstance(value, list):
        value = " ".join(map(str, value))
    command = str(value or "").strip()
    wrapped = _SHELL_WRAPPER.match(command)
    return wrapped.group(2).strip() if wrapped else command


def patch_command(patch: str) -> str:
    files = _PATCH_FILE.findall(patch or "")
    return f"apply_patch {' '.join(files) or '(unknown files)'}\n{patch}"


def exit_code(output: str) -> int | None:
    found = _EXIT.search(output or "")
    return int(found.group(1)) if found else None


def turn_from_hook(payload: Mapping[str, Any], index: int) -> Turn | None:
    name = str(payload.get("tool_name") or "")
    if not name:
        return None
    tool_input = payload.get("tool_input") if isinstance(payload.get("tool_input"), Mapping) else {}
    response = payload.get("tool_response")
    output = response if isinstance(response, str) else json.dumps(response, ensure_ascii=False, default=str)
    if name == "apply_patch":
        command, tool, tool_class = patch_command(str(tool_input.get("command") or tool_input.get("input") or "")), \
            "apply_patch", ToolClass.EDIT
    elif name in SHELL_TOOLS:
        command = shell_command(tool_input.get("command") or tool_input.get("cmd"))
        tool, tool_class = classify_command(command)
    else:
        command = f"{name} {json.dumps(tool_input, ensure_ascii=False, sort_keys=True, default=str)[:500]}"
        tool, tool_class = name.lower(), ToolClass.RUN
    command, output = scrub(command), scrub(output or "")
    code = exit_code(output)
    is_error = (code is not None and code != 0) or looks_like_error(output, tool_class)
    return Turn(
        index=index, command=command, tool=tool, tool_class=tool_class, observation=output,
        is_error=is_error, changes_state=tool_class is ToolClass.EDIT and not is_error,
        cost_units=(len(command) + len(output)) / 4.0,
    )


def read_rollout(path: str | Path) -> tuple[str, list[dict]]:
    """Best-effort: (goal, hook-like tool events) from a Codex rollout JSONL file."""
    goal, calls, events = "", {}, []
    with Path(path).open(encoding="utf-8") as handle:
        for line in handle:
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            payload = entry.get("payload") if isinstance(entry, Mapping) else None
            if not isinstance(payload, Mapping):
                continue
            kind = payload.get("type")
            if entry.get("type") == "event_msg" and kind == "user_message" and not goal:
                goal = _clean_prompt(payload.get("message"))
            if entry.get("type") != "response_item":
                continue
            if kind == "message" and payload.get("role") == "user" and not goal:
                texts = [c.get("text", "") for c in payload.get("content") or [] if isinstance(c, Mapping)]
                goal = next((t for t in (_clean_prompt(x) for x in texts) if t), "")
            elif kind == "function_call":
                try:
                    args = json.loads(payload.get("arguments") or "{}")
                except ValueError:
                    args = {}
                cmd = args.get("cmd") or args.get("command")
                name = "Bash" if cmd is not None else str(payload.get("name") or "")
                calls[payload.get("call_id")] = (name, {"command": cmd} if cmd is not None else args)
            elif kind == "custom_tool_call":
                calls[payload.get("call_id")] = (str(payload.get("name") or ""), {"command": payload.get("input", "")})
            elif kind == "local_shell_call":
                action = payload.get("action") or {}
                calls[payload.get("call_id")] = ("Bash", {"command": action.get("command")})
            elif kind in ("function_call_output", "custom_tool_call_output", "local_shell_call_output"):
                call = calls.get(payload.get("call_id"))
                if call:
                    output = payload.get("output")
                    if isinstance(output, Mapping):
                        output = output.get("output") or output.get("content") or json.dumps(output)
                    events.append({"hook_event_name": "PostToolUse", "tool_name": call[0], "tool_input": call[1],
                                   "tool_response": str(output or "")})
    return goal, events


def _clean_prompt(text: Any) -> str:
    text = str(text or "").strip()
    return "" if text.startswith("<") else text
