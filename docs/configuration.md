# Configuration

unwedge reads its settings from environment variables. The Claude Code plugin exposes the same
settings as plugin options (Claude Code passes them to the hook as `CLAUDE_PLUGIN_OPTION_*`);
`UNWEDGE_*` variables win over plugin options.

| variable | default | meaning |
|---|---|---|
| `UNWEDGE_MODE` | `shadow` | `shadow`: record only. `hint`: add a hint to the agent's context when a loop is found. `stop`: as hint, and a synchronous Claude Code hook may end the session after hints fail. |
| `UNWEDGE_PROVIDER` | `auto` | `auto` (= `jev` if `TYPESAFE_API_KEY` is set, else `none`), `none`, `jev`, `laya`. (In-process Laya is only for the Python API; hooks talk to a Laya server.) |
| `TYPESAFE_API_KEY` | | key for `jev` |
| `LAYA_URL` | `http://127.0.0.1:8000/v1/systemone` | endpoint for `laya` |
| `LAYA_MODEL` | `english` | Laya checkpoint: `english`, `multilingual`, `typed-decisions` |
| `LAYA_API_KEY` | | bearer key, if your Laya server requires one |
| `UNWEDGE_URL`, `UNWEDGE_MODEL`, `UNWEDGE_API_KEY` | | override the selected provider's endpoint, model or key |
| `UNWEDGE_TIMEOUT` | provider default (jev 0.5 s, laya 5 s) | how long a synchronous judgment may take before the turn continues without it |
| `UNWEDGE_HOME` | `~/.unwedge` | where session state, the ledger and `errors.log` live |

## What the modes do

| | shadow | hint | stop |
|---|---|---|---|
| records every tool call and decision | ✓ | ✓ | ✓ |
| adds a hint to the agent's context | | ✓ | ✓ |
| tells the agent to stop and ask the user after hints fail | | ✓ | ✓ |
| ends the session (Claude Code, synchronous hook only) | | | ✓ |

With the plugin's background hooks, stop mode cannot end a session; the stop then arrives as the
same "stop and ask the user" message that hint mode sends.

## The policy, in short

- **Code tier** (always on): a hint when the same action runs a fourth time with nothing changed
  in between or with the same result, the same error comes back a fifth time, a 2-4 step
  sequence repeats three times, or 35 turns pass without an applied change while results or
  errors repeat (a long session without edits is not a loop on its own: reviews and research
  look like that). A cooldown of three turns separates
  interventions; after two hints it escalates (asks the agent to stop and ask the user), and
  repeats the escalation at most every eight turns while the loop goes on.
- **Provider** (when configured): it is asked only on turns code finds suspicious, plus every
  third turn after turn six, and adds interventions: a stall confirmed in two consecutive
  windows, "the goal may already be met", or drift. If a tool result looks like it is talking
  to the reader (injected instructions, "the operator already approved this"), the provider's
  answers for that window are discarded and the event is logged; nothing is sent to the agent,
  and code-tier alarms still act.
- **Kill** happens only in stop mode, only after two hints, only when the provider sees a stall
  and code confirms the loop.

Thresholds live in `unwedge.policy.Thresholds`; the Python API takes your own.

Hooks rebuild the policy state from the session's stored turns on every call, using the current
settings. If you change `UNWEDGE_MODE` or the provider in the middle of a session, earlier turns
are re-evaluated under the new settings.

## Files

```
~/.unwedge/
  sessions/<harness>/<session-id>/   goal.json, turns.jsonl, verdicts.jsonl (deleted after 7 days)
  ledger.jsonl                        one line per guarded tool call (read by `unwedge report`)
  errors.log                          hook failures; hooks never break the agent
```

Tool output is scrubbed of secrets (API keys, tokens, private keys, credentials in URLs) and
clipped before it is stored or sent anywhere.
