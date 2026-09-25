# Claude Code

unwedge runs as a set of Claude Code hooks. Every tool call is recorded, the session is
checked for doom loops, and depending on the mode a short hint is added to Claude's context.

## 1. Install the CLI

The hooks call a `unwedge` executable, so it must be on your `PATH`:

```bash
uv tool install unwedge          # or: pipx install unwedge / pip install unwedge
# before the first PyPI release:
uv tool install git+https://github.com/umithavare/unwedge
unwedge doctor                         # checks PATH, settings and the provider
```

## 2a. Install the plugin (recommended)

In Claude Code:

```text
/plugin marketplace add umithavare/unwedge
/plugin install unwedge@unwedge
```

When the plugin is enabled, Claude Code asks for its options. You can change them later in `/config`
(Claude Code 2.1.269 or later), except the API key, which `/config` does not show:

| option | values | default |
|---|---|---|
| `mode` | `shadow` (record only) or `hint` (also add a hint to Claude's context) | `shadow` |
| `provider` | `none` (code-only, free, local), `jev`, `laya` | `none` |
| `typesafe_api_key` | your TypeSafe key, only for `jev`; kept out of `settings.json` (macOS Keychain, elsewhere `~/.claude/.credentials.json`) | |
| `laya_url` | only for `laya` | `http://127.0.0.1:8000/v1/systemone` |
| `laya_model` | `english`, `multilingual`, `typed-decisions` | `english` |

The plugin's hooks run **in the background** (`async`), so they add no latency to your
session. In `hint` mode a hint reaches Claude on its next step, as a system reminder.

## 2b. Or configure the hooks yourself

Add this to `~/.claude/settings.json` (all projects) or `.claude/settings.json` (one project):

```json
{
  "hooks": {
    "UserPromptSubmit": [{ "hooks": [{ "type": "command", "command": "unwedge", "args": ["hook"], "async": true }] }],
    "PostToolUse": [{ "hooks": [{ "type": "command", "command": "unwedge", "args": ["hook"], "async": true }] }],
    "PostToolUseFailure": [{ "hooks": [{ "type": "command", "command": "unwedge", "args": ["hook"], "async": true }] }]
  },
  "env": { "UNWEDGE_MODE": "hint", "UNWEDGE_PROVIDER": "none" }
}
```

`args` makes Claude Code run `unwedge` directly, without a shell, which behaves the same on
macOS, Linux and Windows.

### Stop mode (opt-in, blocking)

Background hooks cannot end a session. To let unwedge stop a session that keeps looping after
two hints (only with a provider, and only when code also confirms the loop), use a
**synchronous** hook and `UNWEDGE_MODE=stop`:

```json
{
  "hooks": {
    "PostToolUse": [{ "hooks": [{ "type": "command", "command": "unwedge", "args": ["hook"], "timeout": 10 }] }],
    "PostToolUseFailure": [{ "hooks": [{ "type": "command", "command": "unwedge", "args": ["hook"], "timeout": 10 }] }]
  },
  "env": { "UNWEDGE_MODE": "stop", "UNWEDGE_PROVIDER": "jev" }
}
```

Synchronous hooks add their run time to every tool call (measured on Windows: about 0.25 s
without a provider, about 0.6 s with jev on judged turns). The stop is delivered as `{"continue": false, "stopReason": "..."}`. If you set stop
mode on the plugin instead, its background hooks cannot end the session, and the stop arrives
as the "stop and ask the user" message.

## 3. See what it found

```bash
unwedge report            # sessions the hooks saw, first alarm, interventions
unwedge scan              # replay your last 20 Claude Code / Codex sessions (free, local)
unwedge replay ~/.claude/projects/<project>/<session>.jsonl   # turn by turn
```

`unwedge scan` and `unwedge replay` read session transcripts. The transcript format is
internal to Claude Code and can change between releases, so they are best-effort; the hooks
themselves only rely on the documented hook payloads.

## What reaches Claude

Only human-written text from unwedge's hint library, never tool output, for example:

> [UNWEDGE] You have run this command 4 times with the same result. Change something before
> running it again, or step back and re-read the error.

## Troubleshooting

- **Nothing in `unwedge report`**: run `unwedge doctor`; if `unwedge on PATH` says NO, the hook
  cannot start. Hook failures never break your session; they are written to `~/.unwedge/errors.log`.
- **Hooks don't run in a new folder**: Claude Code holds hooks back until you accept the
  workspace trust dialog.
- **Where is the data?** `~/.unwedge/` (override with `UNWEDGE_HOME`). Session folders are
  deleted after 7 days.
