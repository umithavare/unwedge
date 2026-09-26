"""unwedge: an in-loop circuit breaker for AI agent sessions.

Code owns counting, hashing, budgets and policy. A typed-decision model (TypeSafe jev,
or Laya running locally) answers only what code cannot: is the agent still moving toward
*this session's* goal, is the work already done, is it drifting, and does a tool result
try to talk to the reader.

    from unwedge import Guard, make_provider
    guard = Guard(goal="Fix the failing test", provider=make_provider("jev"))
    outcome = guard.on_turn(turn)
"""

from unwedge.guard import Guard, GuardConfig, GuardOutcome
from unwedge.policy import Action, Decision, Thresholds, Verdict
from unwedge.providers import make_provider
from unwedge.turns import Session, ToolClass, Turn

__version__ = "0.2.0"

__all__ = [
    "Action", "Decision", "Guard", "GuardConfig", "GuardOutcome", "Session", "Thresholds", "ToolClass", "Turn",
    "Verdict", "__version__", "make_provider",
]
