from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for extra in (ROOT / "src", ROOT / "benchmarks", ROOT / "tests"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from unwedge.normalize import classify_command, looks_like_error  # noqa: E402
from unwedge.turns import Turn  # noqa: E402


def make_turn(index: int, command: str, observation: str = "ok", *, applied: bool | None = None) -> Turn:
    """Build a Turn the way an adapter would, for tests."""
    tool, tool_class = classify_command(command)
    is_error = looks_like_error(observation, tool_class) if applied is not False else True
    changes = tool_class.value == "edit" and applied is not False and not is_error
    return Turn(
        index=index, command=command, tool=tool, tool_class=tool_class, observation=observation,
        is_error=is_error, changes_state=changes, cost_units=100.0 * index,
    )
