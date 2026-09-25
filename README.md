# unwedge

**A circuit breaker for AI coding agents.** unwedge notices when Claude Code, Codex CLI or your
own agent loop is stuck (the same failing command again, the same error ignored, no progress
toward the task) and says so before the loop burns your budget.

*Wedged* is old developer slang for a process that is stuck and cannot go on without help;
unwedge spots a wedged agent, nudges it, and tells you when a nudge is not enough.

[![ci](https://github.com/umithavare/unwedge/actions/workflows/ci.yml/badge.svg)](https://github.com/umithavare/unwedge/actions/workflows/ci.yml)
[![license](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
![python](https://img.shields.io/badge/python-3.10%2B-blue.svg)

[Türkçe](README.tr.md) · [Claude Code](docs/claude-code.md) · [Codex](docs/codex.md) ·
[Providers](docs/providers.md) · [How it works](docs/how-it-works.md) · [Benchmark](docs/benchmark.md)

---

Agents fail in a characteristic way: stuck at turn 9, still retrying at turn 60. `max_turns`,
token caps and timeouts protect the budget, not the behaviour, so they fire after the money is
spent. unwedge watches the behaviour:

```text
T6  edit 199:205 (+19 lines) -> edit REJECTED, not applied: F821 undefined name   S=0.97 P0=0.13
T7  edit 199:205 (+19 lines) -> edit REJECTED, not applied: F821 undefined name   S=0.97 P0=0.18
T8  edit 199:205 (+19 lines) -> edit REJECTED, not applied: F821 undefined name   S=0.97 P0=0.19  <<< hint
    [UNWEDGE] You have run this command 4 times with the same result. Change something before
    running it again, or step back and re-read the error.
T11 ...                                                                                            <<< hint
T14 ...                                                                                            <<< escalate
```

*A real SWE-agent session from the benchmark, replayed with live jev judgments (S = stall,
P0 = probability of no progress). The agent's edit was rejected 31 times in a row, and 94% of
the session's spend came after unwedge's first hint.
[Full replay](benchmarks/results/replay_larpix.txt).*

## What it does

- **Records every tool call** through a hook and computes loop signals in code: repeated actions
  with nothing changed in between, repeated results, repeated error signatures, streaks. Free and local.
- **Optionally asks a typed-decision model** the questions code cannot answer, relative to *this*
  session's task: is the agent still getting closer, is the work already done, is it drifting.
  Providers: [TypeSafe jev](https://docs.typesafe.ai) (hosted) or
  [Laya](https://github.com/NandhaKishorM/laya) (open weights, runs locally;
  [laya-mlx](https://github.com/mizorewww/laya-mlx) on Apple silicon). Models only return
  probabilities; they never write text to your agent.
- **Acts according to its mode:** `shadow` only records; `hint` adds a short, human-written hint to
  the agent's context; `stop` (opt-in) can end a session that keeps looping after two hints.
- **Never breaks the agent:** every provider or hook problem fails open.

## Quick start

```bash
uv tool install unwedge   # or: pipx install unwedge / pip install unwedge
unwedge scan        # replay your recent Claude Code and Codex sessions and flag loops; free, local
unwedge doctor      # check settings and the provider
```

**Claude Code**

```text
/plugin marketplace add umithavare/unwedge
/plugin install unwedge@unwedge
```

The plugin runs in the background (no added latency) and asks for its mode and provider when you
enable it. Details, manual `settings.json` setup and stop mode: [docs/claude-code.md](docs/claude-code.md).

**Codex CLI** (0.124+): add to `~/.codex/hooks.json`, then approve it in `/hooks`:

```json
{ "hooks": { "PostToolUse": [{ "hooks": [{ "type": "command", "command": "unwedge hook", "timeout": 15 }] }] } }
```

More, including the plugin marketplace: [docs/codex.md](docs/codex.md).

**Your own agent loop**

```python
from unwedge import Guard, GuardConfig, make_provider
from unwedge.adapters.generic import turn_from_command

provider = make_provider("none")                      # or "jev", "laya"
guard = Guard(goal=task, provider=provider, config=GuardConfig.for_provider(provider, shadow=False))
outcome = guard.on_turn(turn_from_command(index, command, output))
if outcome.hint_text:
    next_message += outcome.hint_text
```

See [docs/python-api.md](docs/python-api.md).

## Providers

| | `none` (default) | `jev` | `laya` |
|---|---|---|---|
| runs | locally, code only | TypeSafe API (US) | your machine (`laya-serve` or `unwedge serve`) |
| cost per judged turn | free | ~$0.0001 | free |
| latency per judged turn | none | p50 0.32 s, p99 0.64 s | p50 2.4 s (`multilingual`) to 4.1 s (`english`) on an 8-thread CPU; GPU and Apple silicon not measured |
| gain over code alone in our benchmark | – | +5 points of runaway sessions caught, +8 points of spend recovered | experimental: no gain measured yet |
| data leaves the machine | no | yes (a scrubbed digest) | no |

Choose with `UNWEDGE_PROVIDER` or the plugin option. Setup for each: [docs/providers.md](docs/providers.md).

## Results

We replayed 218 real agent sessions from a public dataset (SWE-agent on SWE-bench tasks) through
unwedge turn by turn, with every threshold fixed before looking at the data. "Runaway" sessions
are the ones that ended by exhausting their context budget.

| setup | runaway sessions caught | their spend after the first alert | successful sessions that got a hint |
|---|---|---|---|
| code only (`provider=none`, free) | 60% | 47% | 5 of 69 |
| **code + jev (recommended)** | **65%** | **55%** | **5 of 69** |

- **Catches most runaway sessions, early:** 65% were flagged, typically halfway through.
- **Saves real money:** 55% of those sessions' spend came after unwedge's first alert, which is
  what stopping there would have saved.
- **Rarely bothers healthy sessions:** 5 of 69 successful sessions got a hint. A hint is one short
  message, not a stop, so a mistaken one costs little.
- **Useful for free:** the code-only tier needs no model and no API key. jev adds 5 points of
  catches for about $0.003 per session.
- **Hints first, stopping on request:** unwedge nudges the agent, escalates to you if the loop
  goes on, and stops a session only in the opt-in stop mode.

Method, cross-validation, latency, cost and limitations: [docs/benchmark.md](docs/benchmark.md).
Everything is reproducible from [`benchmarks/`](benchmarks).

## How it works

Code signals on every turn → a provider only on suspicious turns (plus a periodic sample) → a
pure-function policy with hysteresis, cooldowns and hint-before-stop → a hook response. The
provider sees a small, secret-scrubbed digest of the session, sized to its context window.
[docs/how-it-works.md](docs/how-it-works.md) · [docs/configuration.md](docs/configuration.md)

## Privacy and security

Tool output is scrubbed of common secrets and clipped before it is stored (`~/.unwedge`, deleted
after 7 days) or sent to a provider. With `none` or `laya` nothing leaves your machine. unwedge is
a cost and liveness guard, **not** a security control. See [SECURITY.md](SECURITY.md).

## Status

Alpha (0.1). Tested on Linux, macOS and Windows with Python 3.10-3.13. Claude Code and Codex CLI
support follows their documented hook APIs; `scan` and `replay` read local transcripts on a
best-effort basis. Feedback from real sessions is very welcome: please open an issue.

## Contributing

Issues and pull requests are welcome; see [CONTRIBUTING.md](CONTRIBUTING.md).

## License and credits

Apache-2.0. TypeSafe and jev are products of TypeSafe AI. Laya is by Convai Innovations;
laya-mlx is an independent MLX port. The benchmark samples the public
[nebius/SWE-agent-trajectories](https://huggingface.co/datasets/nebius/SWE-agent-trajectories)
dataset, which is not redistributed here. This project is independent and not affiliated with
any of them.
