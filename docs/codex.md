# OpenAI Codex CLI

Codex CLI 0.124 and later has lifecycle hooks in the same format as Claude Code, and unwedge
uses the same `unwedge hook` command for both; it recognizes a Codex payload by itself.

Codex support is built on Codex's documented hook payloads and covered by tests. If your Codex
version behaves differently, please open an issue with the hook payload (secrets removed).

## 1. Install the CLI

```bash
uv tool install unwedge      # or pipx / pip; see the Claude Code guide
unwedge doctor
```

## 2. Add the hooks

Put this in `~/.codex/hooks.json` (all projects) or `<repo>/.codex/hooks.json` (one trusted project):

```json
{
  "hooks": {
    "UserPromptSubmit": [{ "hooks": [{ "type": "command", "command": "unwedge hook", "timeout": 10 }] }],
    "PostToolUse": [{ "hooks": [{ "type": "command", "command": "unwedge hook", "timeout": 15 }] }]
  }
}
```

Or, inline in `~/.codex/config.toml`:

```toml
[[hooks.PostToolUse]]
[[hooks.PostToolUse.hooks]]
type = "command"
command = "unwedge hook"
timeout = 15
```

Set the mode and provider in your shell environment (`UNWEDGE_MODE=hint`,
`UNWEDGE_PROVIDER=jev` with `TYPESAFE_API_KEY`, and so on; see [configuration](configuration.md)).

Codex does not run a hook until you review and trust it: open `/hooks` in Codex and approve it.
Editing the hook command revokes the approval.

Codex waits for each hook, so unwedge adds its run time to every tool call: about 0.25 s without
a provider and about 0.6 s with jev on judged turns (measured on Windows), and a few seconds with
Laya on a CPU. Start with `UNWEDGE_PROVIDER=none` if that matters to you.

## Plugin (experimental)

The repository also contains a Codex plugin (`plugins/codex`) and a repo marketplace
(`.agents/plugins/marketplace.json`):

```bash
codex plugin marketplace add umithavare/unwedge
```

then install `unwedge` from `/plugins`. This path follows OpenAI's plugin documentation but has
not been tested end to end yet; the `hooks.json` setup above is the supported one.

## Differences from Claude Code

| | Claude Code | Codex CLI |
|---|---|---|
| hint to the model | yes (`additionalContext`) | yes (`additionalContext`, as a developer message) |
| warning to the user | no (background hooks) | yes (`systemMessage` on escalation) |
| failed tool calls | separate `PostToolUseFailure` event | same event; unwedge reads the exit code from the output |
| file reads | `Read` tool | shell commands (`cat`, `sed -n`, `rg`), classified by unwedge |
| stop the session | yes, in stop mode | **no**: no Codex hook can end a session; unwedge hints and warns |

## See what it found

```bash
unwedge report
unwedge scan                                     # includes ~/.codex/sessions rollouts
unwedge replay ~/.codex/sessions/2026/09/23/rollout-....jsonl
```

Rollouts older than 7 days are compressed (`.jsonl.zst`) by Codex; `scan` and `replay` read
only uncompressed files.
