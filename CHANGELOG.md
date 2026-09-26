# Changelog

## 0.2.0 — 2026-09-26

- Code tier: three new loop signals, checked on 3,885 sessions from four public datasets. The
  same command with the same result counts as a repeat even when edits ran in between; a 2-4
  step sequence repeating three times counts as a loop; 35 turns without an applied change count
  when results or errors repeat. Screenshots, empty results and UI tool calls never count as
  "the same result". On the original benchmark, catches rose from 60% to 78% (code only) and
  from 65% to 79% (code + jev) with the same false alarms; on Claude and GPT-4o sessions from
  32% to 47%.
- Code-tier thresholds live in `Thresholds` (`code_repeats`, `code_errors`, `code_cycles`,
  `stall_turns`).
- `unwedge export` writes your recent Claude Code and Codex sessions in the new session format
  (`unwedge.dataset`) so you can label them and measure unwedge on your own work.
- `unwedge.adapters.messages` converts chat-message traces: OpenAI tool calls, SWE-agent function
  markup and mini-swe-agent bash blocks.
- Benchmark: a four-dataset corpus (SWE-agent with Llama 70B; SWE-agent with Claude 3.7/3.5
  Sonnet and GPT-4o; OpenHands; mini-swe-agent with GPT-5) with leave-one-source-out
  evaluation (`benchmarks/multisource.py`) and `docs/dataset.md`.

## 0.1.1 — 2026-09-25

- README: the results section now leads with what unwedge achieves; the full method and
  limitations stay in `docs/benchmark.md`.
- Install instructions point to PyPI (`uv tool install unwedge`).

## 0.1.0 — 2026-09-23

First public version.

- Guard with a code tier (repeats, result fingerprints, error signatures, streaks) and an optional
  typed-decision provider; code-first policy with hysteresis, cooldowns and hint-before-stop.
  Two hints, then an escalation that repeats at most every eight turns; the provider only picks
  which hint, never how strong the intervention is.
- Providers: TypeSafe jev (hosted), Laya via `laya-serve` or `unwedge serve` (local, open weights,
  laya-mlx on Apple silicon), in-process Laya for the Python API, or none. Zero-dependency HTTP
  client; every provider failure fails open.
- Claude Code plugin and marketplace (background hooks; hint and stop modes).
- Codex CLI support through `hooks.json`; experimental Codex plugin marketplace.
- `unwedge hook | scan | replay | report | serve | doctor`.
- A tool result that talks to the reader (a "gate" firing) vetoes the provider's judgments for
  that window and is logged; code-tier alarms still act, and nothing is sent to the agent.
- Benchmark on 218 public SWE-agent trajectories (code only vs jev, plus paired Laya
  comparisons), with reproducible scripts.
