# Contributing

Thanks for helping. unwedge is small on purpose: a zero-dependency core, one hook command, and a
benchmark that keeps us honest.

## Setup

```bash
git clone https://github.com/umithavare/unwedge && cd unwedge
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev,bench]"
ruff check src tests benchmarks && pytest -q
```

## Ground rules

- **The core stays dependency-free.** It runs in a hook process on every tool call.
- **The guard never breaks the agent.** Provider or hook failures fail open; add a test when you
  touch that path.
- **Code counts, models judge.** Anything code can compute exactly (repeats, counts, time,
  budgets) stays in code. Providers only answer questions code cannot.
- **Nothing from tool output reaches the agent.** Hints are human-written; providers only select one.
- **Numbers come from the benchmark.** If you change the policy, questions or digest, rerun
  `benchmarks/analyze.py` and update the README tables with what it prints, good or bad.

## Adding a harness

Write an adapter that turns the harness's tool-call payload into a `Turn`
(`src/unwedge/adapters/`), teach `hooks.detect_harness` to recognize it, and add tests with
real payload samples.

## Adding a provider

Implement the `Provider` protocol (`src/unwedge/providers/base.py`) or expose a
`POST /v1/systemone` endpoint and use the `laya` provider with `LAYA_URL`. Add a `Profile` that
matches the model's context size (full or compact battery).
