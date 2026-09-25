"""Build turns for your own agent loop from a command (or tool call) and its output."""

from __future__ import annotations

from unwedge.normalize import classify_command, looks_like_error
from unwedge.scrub import scrub
from unwedge.turns import ToolClass, Turn


def turn_from_command(index: int, command: str, output: str, *, failed: bool | None = None,
                      tool_class: ToolClass | None = None, cost_units: float = 0.0) -> Turn:
    """A scrubbed Turn. `failed=None` infers failure from the output text; pass
    `tool_class` for non-shell tools (e.g. ToolClass.EDIT for a file write)."""
    command, output = scrub(command), scrub(output)
    tool, inferred = classify_command(command)
    cls = tool_class or inferred
    is_error = looks_like_error(output, cls) if failed is None else failed
    return Turn(index=index, command=command, tool=tool, tool_class=cls, observation=output, is_error=is_error,
                changes_state=cls is ToolClass.EDIT and not is_error, cost_units=cost_units)
