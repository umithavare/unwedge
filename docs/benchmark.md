# Benchmark

Does a typed-decision model catch doomed agent sessions that plain code cannot, early enough
to matter, without interrupting sessions that would have succeeded? This page describes how we
tested that, what came out (good and bad), and how to rerun it. Every number here is produced by
the scripts in [`benchmarks/`](../benchmarks) and saved under
[`benchmarks/results/`](../benchmarks/results).

**Short answer:** unwedge's free code tier catches 78% of runaway sessions, typically halfway
through, and 63% of their spend comes after its first alert; 5 of 69 successful sessions were
told they look stuck. Adding jev adds one point of catches and a one-time "the task may already
be done" note. On four public datasets with other agents and models (Claude, GPT-4o, GPT-5,
OpenHands) the code tier catches fewer loops (21-78%) but stays quiet on healthy sessions from
capable models (2.5% for Claude and GPT-4o, none of 600 normal GPT-5 sessions). The provider has
to add to code, not override it: overriding halves the catches. Laya, as configured in this
release, does not add accuracy yet. No detector reached near-zero false alarms everywhere, so
unwedge hints by default and stopping is opt-in.

## Data

218 SWE-agent sessions sampled from the public
[nebius/SWE-agent-trajectories](https://huggingface.co/datasets/nebius/SWE-agent-trajectories)
dataset, all from the same agent and model (`swe-agent-llama-70b`), one session per task and
group:

| group | sessions | meaning |
|---|---|---|
| success | 69 | resolved the task (the negatives: an alarm here is a false alarm) |
| burn | 99 | failed after exhausting the context budget (the positives: the loops we want to catch) |
| wrong | 50 | failed but submitted normally: a wrong patch, usually not a loop (reported on the side) |

The dataset is not redistributed; [`fetch_trajectories.py`](../benchmarks/fetch_trajectories.py)
downloads the same sample (fixed seed).

## Method

Each session is replayed turn by turn, exactly as the hook sees it: commands and outputs are
scrubbed and clipped, code signals are computed from turns up to *t* only, and the provider is
asked only on gated turns (67% of turns here: 46% in successful sessions, 75% in burning ones).
jev answered the eight questions described in [how it works](how-it-works.md) with the digest
the shipped guard sends.

Spend is modelled per turn as the prompt the agent re-sent (its whole context) plus its output,
so later turns cost more, as they do with real models. **Recoverable spend** is the share of the
burning sessions' total spend that came after the first alarm, which is an upper bound on what
stopping there would have saved.

Two kinds of evaluation:

1. **The policy as shipped.** The provider thresholds were written down before the data was seen
   (`unwedge.policy.Thresholds`). The code-tier rules were revised in 0.2.0 after studying the
   four datasets below; their thresholds are round and the same everywhere. An alarm is a hint
   or an escalation before the session's last turn.
2. **Tuned detectors, cross-validated.** Grids of detectors (turn caps, code-signal thresholds,
   jev thresholds, combinations, and logistic regressions on code signals with and without jev
   features) are tuned on training folds under a cap on training-fold false alarms, then scored
   on held-out sessions (5-fold stratified, repeated 5 times).

A decision rule was also fixed in advance: *continue* with a model if it catches ≥ 15 points more
doomed sessions than code, or alarms ≥ 3 turns earlier, with ≤ 1% false alarms; *pivot* to code
only if code alone catches ≥ 85%.

## Results

### The shipped policy, untuned

| policy | caught | false alarms | recoverable spend | first alarm at (median share of the session) | wrong-patch sessions alarmed |
|---|---|---|---|---|---|
| **code only (`provider=none`)** | **78%** | **5 of 69 (7.2%)** | **63%** | **0.52** | **8%** |
| **code + jev** | **79%** | **5 of 69 (7.2%)** | **64%** | **0.52** | **8%** |
| jev only | 26% | 1 of 69 (1.4%) | 27% | 0.58 | 0% |
| original design: jev overrides code | 32% | 2 of 69 (2.9%) | 32% | 0.60 | 0% |
| 0.1 code rules, for comparison | 60% | 5 of 69 (7.2%) | 47% | 0.49 | 8% |

Everything the agent would read in hint mode, not just alarms:

| policy | successful sessions with any message | messages per successful session | per burning session | per wrong-patch session |
|---|---|---|---|---|
| code only | 7.2% | 0.16 | 3.77 | 0.18 |
| **code + jev** | **15.9%** | **0.28** | **3.86** | **0.18** |
| jev only | 10.1% | 0.12 | 1.23 | 0.00 |
| jev overrides code | 11.6% | 0.13 | 1.88 | 0.00 |

The extra messages with jev are a one-time "the task may already be done; verify it and finish"
note. It went to 6 successful sessions (9%) and to no failed session. Escalations
repeat at most every eight turns; gate vetoes (see below) are logged, not sent.

**The original design failed its own test.** In the first design, a jev verdict replaced the code
tier on every turn it judged. That caught 32% instead of 78%: jev often rated a blatant loop as
"still making some progress", and the code alarm was suppressed. The shipped policy lets code act
first and uses jev only to add alarms.

### Tuned detectors, held out

With thresholds tuned to allow no false alarms on the training folds (the 1% cap gives the same
picks):

| detector | caught | false alarms (held out) | recoverable spend | turns saved per doomed session |
|---|---|---|---|---|
| `max_turns` only | 29% ± 3% | 1.4% | 29% | 9.6 |
| code signals | 44% ± 3% | 3.5% ± 1.5% | 39% | 13.5 |
| jev signals | 32% ± 4% | 4.9% ± 1.5% | 29% | 10.5 |
| code suspects, jev confirms | 50% ± 3% | 4.6% ± 0.6% | 46% | 16.5 |
| code or jev | 57% ± 4% | 5.2% ± 1.5% | 48% | 17.3 |
| logistic, code features | 58% ± 3% | 4.9% ± 0.7% | 44% | 15.5 |
| logistic, code + jev features | 46% ± 2% | 3.8% ± 1.2% | 37% | 13.0 |

Allowing 5% training false alarms, the best combinations catch about 80% (code alone 76%) at
9-13% held-out false alarms. Full tables for every cap:
[analysis_plain.md](../benchmarks/results/analysis_plain.md). The frontier plot is
[tradeoff.png](../benchmarks/results/tradeoff.png) (in-sample, so optimistic for every family alike).

**Decision rule:** neither *continue* nor *pivot*. The hybrids gain 6-13 points of catches over
code (the rule asked for 15). "Code suspects, jev confirms" alarms 4.3 turns earlier, which
clears the rule's 3-turn bar, but at 4.6% held-out false alarms, not 1%, and no detector gets
down to 1%. The model's value is real but modest, which is why unwedge treats the provider as
optional; with the 0.2.0 code rules the shipped code + jev policy is one point ahead of code
alone on this dataset.

### Two sessions, turn by turn

- [replay_larpix.txt](../benchmarks/results/replay_larpix.txt): a doomed session. The agent's
  edit was rejected 31 times in a row. unwedge hints at turn 8 (the same edit four times) and
  turn 11 ("read the last error literally"), then escalates at turns 14, 22 and 30. 94% of the
  session's spend came after the first hint.
- [replay_followthemoney.txt](../benchmarks/results/replay_followthemoney.txt): one of the five
  false alarms. The agent fixed the bug at turn 2, then spent 50 turns cycling through the same
  four steps around its own failing reproduction script. unwedge hinted at turn 16 (the repeating
  four-step cycle). The loop was real, but the session counts as a success because the early
  patch was right.

## Four datasets: does it generalize?

The numbers above come from one agent and one model. To check the code tier on other agents,
harnesses and models, it was replayed on 3,885 sessions from four public datasets
([docs/dataset.md](dataset.md) lists them, their licenses and the labelling rules):

| source | agent / models | sessions |
|---|---|---|
| nebius | SWE-agent, Llama 70B (the set above) | 69 success, 99 burn, 50 wrong |
| swe-smith | SWE-agent with function calling; Claude 3.7 Sonnet, Claude 3.5 Sonnet, GPT-4o | 800 success, 211 burn, 400 wrong |
| swe-gym | OpenHands | 192 success, 600 burn, 300 wrong |
| jetbrains | mini-swe-agent; GPT-5-mini, GPT-5.2 | 600 normal finishes, 564 cost-limit exits |

"Burn" is each dataset's closest label to a loop: the session exhausted its budget (nebius,
swe-smith) or was cut off by the harness before finishing (swe-gym). JetBrains' cost-limit exits
are not loops (GPT-5 reaches the limit in a handful of varied, expensive turns), so that source
only measures alarms on normal sessions.

**The 0.1 code rules did not transfer well.** They caught 60% on nebius but 32% on swe-smith and
19% on swe-gym. Studying the misses led to three additions in 0.2.0: the same command with the
same result counts as a repeat even when edits ran in between (an edit that leaves the test
failing the same way changed nothing that matters), a 2-4 step sequence repeating three times
counts as a loop, and 35 turns without an applied change counts when results or errors repeat.
Screenshots, empty results and UI tool calls never count as "the same result".

| source | caught, 0.1 rules | **caught, 0.2 rules** | false alarms, 0.1 | **false alarms, 0.2** | recoverable spend, 0.2 |
|---|---|---|---|---|---|
| nebius | 60% | **78%** | 7.2% | **7.2%** | 63% |
| swe-smith | 32% | **47%** | 1.8% | **2.5%** | 32% |
| swe-gym | 19% | **21%** | 15.1% | **16.7%** | 39% |
| jetbrains | – | – | 0 of 600 | **0 of 600** | – |
| all three with labels | 26% | **33%** | 4.5% | **5.4%** | 37% |

Detectors tuned on three sources and tested on the fourth did not do better: under a 2%
training false-alarm cap, the tuned code-signal grid caught 34% at 6.3% held-out false alarms and
a logistic model 14% at 1.4% ([multisource.md](../benchmarks/results/multisource.md)). The simple
rules transfer at least as well and are easier to reason about.

What the table says about each source:

- **OpenHands (swe-gym)** is hard: its runs already stop themselves when an action repeats, so
  many loops end right where unwedge would fire, and successful runs often contain a short loop
  (the same directory listed four times) before the agent recovers. Those count as false alarms.
- **Capable models are quiet:** 2.5% of successful Claude and GPT-4o sessions and none of 600
  normal GPT-5 sessions got a hint.
- **A real-world check:** on 60 of the author's own recent Claude Code and Codex sessions, the
  0.2 rules flagged one, a genuine loop that hit the same error five times. The first version of
  the new rules also flagged a session that took screenshots while scrolling a page, because
  screenshots have no text; that is why empty results and UI tools are now excluded.

## What jev is good and bad at here

From [diagnostics_plain.json](../benchmarks/results/diagnostics_plain.json):

- **Window reading works.** The stall judgment separates the groups (median 0.28 in successful
  sessions, 0.70 in burning ones). The "already done" judgment is high near the end of
  successful sessions (mean 0.60 over the last three turns vs 0.11 in burning ones).
- **Outcome prediction is weak.** In burning sessions the median window still gets only
  P(no progress) = 0.13: many doomed sessions look like honest exploration, one window at a time.
- **Answers jitter.** The same request sent ten times gave stall answers spread by 0.07 on average
  and up to 0.22 ([null_spread.json](../benchmarks/results/null_spread.json)). Consecutive
  windows cross the 0.85 stall threshold 25% of the time. That is why the policy needs two
  windows in a row before acting.
- **The prompt-injection gate fires on benign data.** There is no injected content in this
  dataset, yet the gate reached 0.6 on 2.8% of turns and in 13% of sessions. unwedge therefore
  only logs a gate firing, and the veto discards the provider's judgments, never code's; it is
  not an injection filter.

## Cost, latency and an edge-firewall finding

jev, measured from Turkey against the public API (5,633 answered calls):

| | |
|---|---|
| latency per call | p50 0.32 s, p90 0.40 s, p99 0.64 s, max 1.48 s |
| input per call | ~2,400 tokens (max 5,600) |
| cost | $0.00010 per call; $0.57 for all 218 sessions (≈ $0.003 per session) |
| rejected by the edge firewall | 362 calls (6.0%), in 13 sessions: HTTP 403 before the model, apparently because agent transcripts (shell commands, code) resemble attack payloads |

A rejected call is treated like a timeout: that turn falls back to the code tier. unwedge does
not try to evade the firewall.

The default hot-path budget is 0.5 s per call; in the live replays about one call in 30 hit it
and failed open.

## Laya

Laya ran locally with its own server (`laya-serve`, laya 0.3.11, PyTorch on a CPU with 8
threads), using unwedge's compact question battery and a state sized to each checkpoint's
context. Local inference is slow on a CPU, so it was scored on paired subsets: the first 30
successful and 30 doomed sessions for the `multilingual` checkpoint, and the first 5 + 5 of those
for `english` (the default checkpoint). jev and code alone were scored on exactly the same sessions.

| sessions | policy | caught | false alarms | recoverable spend |
|---|---|---|---|---|
| 30 + 30 | code only | 77% | 0 of 30 | 65% |
| 30 + 30 | code + jev | 80% | 0 of 30 | 67% |
| 30 + 30 | code + Laya `multilingual` | 77% | 0 of 30 | 65% |
| 30 + 30 | Laya `multilingual` only | 0% | 0 of 30 | 0% |
| 5 + 5 | code only | 80% | 0 of 5 | 68% |
| 5 + 5 | code + jev | 80% | 0 of 5 | 68% |
| 5 + 5 | code + Laya `english` | 80% | 0 of 5 | 68% |
| 5 + 5 | Laya `english` only | 0% | 0 of 5 | 0% |

Median answers, successful / doomed sessions:

| | stall | P(no progress) | already done | drift | gate |
|---|---|---|---|---|---|
| jev (the 30 + 30 sessions) | 0.23 / 0.72 | 0.00 / 0.18 | 0.10 / 0.03 | 0.14 / 0.24 | 0.18 / 0.18 |
| Laya `multilingual` (30 + 30) | 0.95 / 0.97 | 0.07 / 0.09 | 0.79 / 0.84 | 0.79 / 0.82 | 0.84 / 0.87 |
| Laya `english` (5 + 5) | 0.64 / 0.63 | 0.30 / 0.30 | 0.48 / 0.50 | 0.59 / 0.54 | 0.54 / 0.54 |

- **Neither checkpoint separated stuck from healthy sessions on this task.** `multilingual`
  answered "yes" to almost every yes/no question; `english` stayed near the middle on all of
  them, in both groups.
- **So with the shipped policy Laya adds nothing: code + Laya equals code alone.** It does not
  hurt either, thanks to a fix this benchmark prompted. `multilingual`'s gate crossed 0.6 on 92%
  of turns, and in a pre-release version a gate veto also silenced the code tier (with the 0.1
  code rules, code + Laya `multilingual` caught 13% instead of 60%). The veto now discards only
  the provider's judgments.
- **Latency on the CPU:** `multilingual` p50 2.4 s, p99 4.3 s; `english` p50 4.1 s, p90 5.0 s,
  so about one `english` call in ten would exceed the default 5 s budget and fail open. GPU and
  Apple silicon were not measured.
- **What this does and does not show.** One task, one prompt design, untuned thresholds, small
  samples. Laya may need questions phrased differently, or its own calibration, for agent
  transcripts. The integration works (same protocol and answer schema, `unwedge serve`, fail
  open); its value for this job is not established. Until it is, use `none` or `jev`, or run
  Laya in shadow mode and compare with `unwedge report`.

## Other variants

- **Result fingerprints in the digest** (`--fingerprints`, variant `fp`): no gain (78% caught,
  7.2% false alarms, the same as without them). See [analysis_fp.md](../benchmarks/results/analysis_fp.md).

## Caveats

- **Mostly one task type.** All four datasets are coding agents fixing repository issues. Claude
  Code and Codex sessions are more varied (parallel tool calls, MCP tools, non-coding work).
  Treat the numbers as public, reproducible data points, not a guarantee.
- **The 0.2 rules were designed with these datasets in view.** The thresholds are round and the
  same for every source, and detectors tuned on other sources did not transfer better, but the
  numbers here are in-sample for the rule design. Your own labelled sessions
  ([docs/dataset.md](dataset.md)) are the independent test.
- **Outcome labels are a proxy for loops.** Some "burn" sessions ran out of budget without
  looping, and some successful sessions contain a short loop. Turn-level labels would remove
  that noise.
- **69 successful sessions** means each false alarm is 1.4 points; the confidence intervals are wide.
- **Offline replay.** Hints were not actually delivered, so this measures detection, not whether
  the agent recovers after a hint.
- **Recoverable spend is an upper bound.** It assumes the session would have been stopped at the
  alarm.
- **The provider thresholds were not tuned**, for jev or for Laya. Tuning them on this data
  would overfit it.
- **Six tasks appear twice** (a successful and a failed run of the same instance). Sessions are
  keyed by task and group throughout; an earlier version of the analysis keyed them by task
  only and mixed up those runs' provider answers. The numbers here are from the corrected code.
- **Not measured:** prompt-injection robustness. The red-team script
  ([redteam.py](../benchmarks/redteam.py)) sends adversarial content to the provider and requires
  `--i-have-approval`: check your provider's terms before running it.

## Reproduce

```bash
pip install -e ".[bench]"
python benchmarks/fetch_trajectories.py                         # ~15 MB of sessions into benchmarks/data/raw
python benchmarks/run_battery.py --provider jev                 # needs TYPESAFE_API_KEY; about $0.60
python benchmarks/analyze.py --variant plain                    # tables above -> results/analysis_plain.md
python benchmarks/diagnostics.py --variant plain                # signal distributions, latency, cost
python benchmarks/replay_demo.py --session samkohn__larpix-control-68   # a live turn-by-turn replay

# Laya, free and local (start `laya-serve` or `unwedge serve` first)
python benchmarks/run_battery.py --provider laya --model multilingual --per-group 30 --groups success,burn
python benchmarks/run_battery.py --provider laya --model english --per-group 5 --groups success,burn
python benchmarks/analyze.py --variant laya-multilingual
python benchmarks/analyze.py --variant plain --sessions-from laya-multilingual   # jev on the same sessions
python benchmarks/compare.py plain_on_laya-multilingual laya-multilingual      # side by side

# four datasets, code tier only (free)
python benchmarks/fetch_sources.py                                             # ~330 MB of parquet
python benchmarks/build_corpus.py                                              # -> data/corpus/*.jsonl
python benchmarks/multisource.py [--extra my-sessions.jsonl]                   # -> results/multisource.md
```

The per-turn provider answers (`results/battery_*.jsonl`) are not committed; rerunning the
battery reproduces them (jev answers jitter slightly between runs).
