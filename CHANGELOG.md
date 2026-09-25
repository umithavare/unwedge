# Changelog

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
