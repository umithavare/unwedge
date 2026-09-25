"""Adapter for Claude Code: hook payloads (PostToolUse / PostToolUseFailure) and, for
offline replay, session transcripts (~/.claude/projects/<project>/<session>.jsonl).

The transcript format is internal to Claude Code and can change between releases, so
transcript parsing is best-effort; the hook payloads are the documented contract.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from unwedge.normalize import classify_command, looks_like_error
from unwedge.scrub import scrub
from unwedge.turns import ToolClass, Turn

SHELL_TOOLS = {"Bash", "PowerShell"}
NAVIGATE_TOOLS = {"Read", "NotebookRead"}
SEARCH_TOOLS = {"Grep", "Glob", "LS", "WebFetch", "WebSearch", "ToolSearch", "BashOutput",
                "ListMcpResourcesTool", "ReadMcpResourceTool"}
EDIT_TOOLS = {"Edit", "MultiEdit", "Write", "NotebookEdit"}
# bookkeeping and conversation tools say nothing about progress on the task
SKIP_TOOLS = {"TodoWrite", "TaskCreate", "TaskUpdate", "TaskList", "TaskGet", "ExitPlanMode", "EnterPlanMode",
              "AskUserQuestion", "Skill", "KillShell", "KillBash"}
VIEW_LINES = 120


def command_for(name: str, tool_input: Mapping[str, Any]) -> str:
    path = tool_input.get("file_path") or tool_input.get("notebook_path") or tool_input.get("path") or ""
    if name in SHELL_TOOLS:
        return str(tool_input.get("command", ""))
    if name in NAVIGATE_TOOLS:
        extras = "".join(f" {key}={tool_input[key]}" for key in ("offset", "limit") if tool_input.get(key))
        return f"read {path}{extras}"
    if name in ("Edit", "MultiEdit"):
        body = tool_input.get("edits") or [tool_input.get("old_string"), tool_input.get("new_string")]
        return f"edit {path}\n{json.dumps(body, ensure_ascii=False, sort_keys=True)}"
    if name == "Write":
        return f"create {path}\n{tool_input.get('content', '')}"
    if name == "NotebookEdit":
        return f"edit {path} cell={tool_input.get('cell_id', '')}\n{tool_input.get('new_source', '')}"
    if name == "Grep":
        return "grep " + json.dumps({k: tool_input[k] for k in sorted(tool_input)}, ensure_ascii=False)
    if name == "Glob":
        return f"glob {tool_input.get('pattern', '')} {path}".strip()
    if name == "WebFetch":
        return f"webfetch {tool_input.get('url', '')}"
    if name == "WebSearch":
        return f"websearch {tool_input.get('query', '')}"
    if name in ("Task", "Agent"):
        return f"agent {tool_input.get('subagent_type', '')}: {tool_input.get('description', '')}".strip()
    return f"{name} {json.dumps(tool_input, ensure_ascii=False, sort_keys=True, default=str)[:500]}"


def tool_and_class(name: str, command: str) -> tuple[str, ToolClass]:
    if name in SHELL_TOOLS:
        return classify_command(command)
    if name in NAVIGATE_TOOLS:
        return "read", ToolClass.NAVIGATE
    if name in SEARCH_TOOLS:
        return name.lower(), ToolClass.SEARCH
    if name in EDIT_TOOLS:
        return ("create" if name == "Write" else "edit"), ToolClass.EDIT
    return name.lower(), ToolClass.RUN


def observation_for(tool_response: Any) -> str:
    """Render a tool result as text. Schemas differ per tool, so this is tolerant."""
    if tool_response is None:
        return ""
    if isinstance(tool_response, str):
        return tool_response
    if isinstance(tool_response, list):
        return "\n".join(str(item.get("text", "")) if isinstance(item, Mapping) else str(item)
                         for item in tool_response)
    if not isinstance(tool_response, Mapping):
        return str(tool_response)
    if "stdout" in tool_response or "stderr" in tool_response:
        text = str(tool_response.get("stdout") or "")
        if tool_response.get("stderr"):
            text += "\n" + str(tool_response["stderr"])
        return text + ("\n(interrupted)" if tool_response.get("interrupted") else "")
    file = tool_response.get("file")
    if isinstance(file, Mapping) and "content" in file:
        return _render_view(file)
    if isinstance(tool_response.get("filenames"), list):
        names = tool_response["filenames"]
        return f"Found {tool_response.get('numFiles', len(names))} files\n" + "\n".join(map(str, names[:50]))
    if isinstance(tool_response.get("content"), str):
        return tool_response["content"]
    if "filePath" in tool_response and ({"structuredPatch", "newString", "oldString"} & set(tool_response)
                                        or tool_response.get("type") in ("create", "update")):
        return f"(edit applied) {tool_response['filePath']}"
    for key in ("result", "output", "text"):
        if isinstance(tool_response.get(key), str):
            return tool_response[key]
    return json.dumps(tool_response, ensure_ascii=False, default=str)[:6000]


def _render_view(file: Mapping[str, Any]) -> str:
    start = int(file.get("startLine") or 1)
    lines = str(file.get("content", "")).splitlines()
    total = file.get("totalLines") or file.get("numLines") or len(lines)
    body = "\n".join(f"{start + i}:{line}" for i, line in enumerate(lines[:VIEW_LINES]))
    return f"[File: {file.get('filePath', '?')} ({total} lines total)]\n{body}"


def turn_from_hook(payload: Mapping[str, Any], index: int) -> Turn | None:
    """A Turn from a PostToolUse or PostToolUseFailure payload; None for bookkeeping tools."""
    name = str(payload.get("tool_name") or "")
    if not name or name in SKIP_TOOLS:
        return None
    tool_input = payload.get("tool_input") if isinstance(payload.get("tool_input"), Mapping) else {}
    command = scrub(command_for(name, tool_input))
    tool, tool_class = tool_and_class(name, command)
    if payload.get("hook_event_name") == "PostToolUseFailure":
        observation = scrub(str(payload.get("error") or "the tool call failed"))
        is_error = True
    else:
        observation = scrub(observation_for(payload.get("tool_response")))
        is_error = tool_class is ToolClass.RUN and looks_like_error(observation, ToolClass.RUN)
    return Turn(
        index=index, command=command, tool=tool, tool_class=tool_class, observation=observation,
        is_error=is_error, changes_state=tool_class is ToolClass.EDIT and not is_error,
        cost_units=(len(command) + len(observation)) / 4.0,
    )


def read_transcript(path: str | Path) -> tuple[str, list[dict]]:
    """Best-effort: (goal, hook-like tool events) from a Claude Code session transcript."""
    goal, uses, events = "", {}, []
    with Path(path).open(encoding="utf-8") as handle:
        for line in handle:
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if not isinstance(entry, Mapping) or entry.get("isSidechain"):
                continue
            content = (entry.get("message") or {}).get("content")
            if entry.get("type") == "assistant" and isinstance(content, list):
                for item in content:
                    if isinstance(item, Mapping) and item.get("type") == "tool_use":
                        uses[item.get("id")] = (str(item.get("name") or ""), item.get("input") or {})
            elif entry.get("type") == "user":
                goal = goal or _prompt_text(content)
                for item in content if isinstance(content, list) else ():
                    is_result = isinstance(item, Mapping) and item.get("type") == "tool_result"
                    if is_result and item.get("tool_use_id") in uses:
                        name, tool_input = uses[item["tool_use_id"]]
                        failed = bool(item.get("is_error"))
                        text = observation_for(item.get("content"))
                        rich = entry.get("toolUseResult")
                        events.append({
                            "hook_event_name": "PostToolUseFailure" if failed else "PostToolUse",
                            "tool_name": name, "tool_input": tool_input,
                            "tool_response": rich if isinstance(rich, Mapping) and not failed else text,
                            "error": text if failed else None,
                        })
    return goal, events


def _prompt_text(content: Any) -> str:
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        text = next((str(i.get("text", "")) for i in content if isinstance(i, Mapping) and i.get("type") == "text"), "")
    else:
        return ""
    return "" if text.lstrip().startswith("<") else text.strip()
