# Python API

Use the guard directly inside your own agent loop. It is synchronous, has no third-party
dependencies, and fails open: any provider problem leaves the turn on the code-only tier.

```python
from unwedge import Action, Guard, GuardConfig, make_provider
from unwedge.adapters.generic import turn_from_command

provider = make_provider("jev")          # or "laya", "laya-local", or "none"
guard = Guard(
    goal="Fix the failing test in payments/test_settlement.py without changing its assertions.",
    provider=provider,
    config=GuardConfig.for_provider(provider, shadow=False),   # shadow=True: log only
)

for index, (command, output, failed) in enumerate(run_agent_steps(), start=1):
    outcome = guard.on_turn(turn_from_command(index, command, output, failed=failed))
    if outcome.hint_text:
        next_message = outcome.hint_text              # e.g. append to the agent's next user message
    if outcome.decision.action is Action.ESCALATE:
        ask_a_human(outcome.decision.reasons)
    if outcome.decision.action is Action.KILL:        # only with GuardConfig(kill_enabled=True)
        break
```

`turn_from_command` scrubs secrets and infers the tool class (navigate, search, edit, run) from
the command. For tool calls that are not shell commands, pass `tool_class=ToolClass.EDIT` (or
another class) explicitly.

`GuardOutcome` carries the decision and its reasons, the code signals, the provider verdict
(stall, P(no progress), terminal, drift, gate), latency, cost and the hint. Pass
`ledger=Path(...)` to the guard to append one JSON line per turn.

Actions that come with `hint_text`: `HINT`, `VERIFY_HINT` ("the task may already be done; verify
it and finish", at most once per session) and `RETURN_HINT` (drift). `ESCALATE` has no text of
its own; the hooks send a fixed "stop and ask the user" message. `FLAG` means a tool result
looked like it was addressing the agent; that window's judgments were ignored, and it is
informational only. `CASCADE` marks a long ambiguous stretch, if you want to consult a larger
model.

## Claude Agent SDK

The hook handler behind `unwedge hook` accepts the SDK's hook input as is. It does blocking
I/O, so run it in a thread (sketch, not tested against every SDK release):

```python
import asyncio
from claude_agent_sdk import ClaudeAgentOptions, HookMatcher
from unwedge.config import Settings
from unwedge.hooks import handle

settings = Settings.from_env()             # UNWEDGE_MODE, UNWEDGE_PROVIDER, ...

async def unwedge(input_data, tool_use_id, context):
    return await asyncio.to_thread(handle, input_data, settings) or {}

options = ClaudeAgentOptions(hooks={
    "UserPromptSubmit": [HookMatcher(hooks=[unwedge])],
    "PostToolUse": [HookMatcher(hooks=[unwedge])],
})
```

## Replaying recorded sessions

```python
from unwedge.replay import replay_file

result = replay_file("~/.claude/projects/p/session.jsonl")    # Claude Code or Codex rollout
print(result.first_intervention, result.turns_after_first_intervention)
```

## Your own policy

Everything the guard decides comes from `unwedge.policy.step`, a pure function of the
previous state, the provider verdict and the code signals. Adjust `Thresholds` or wrap `step`
to change behaviour; the stored verdicts in a ledger let you replay a new policy over past
sessions without new model calls.
