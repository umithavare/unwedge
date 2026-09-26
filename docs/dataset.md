# Data: public datasets and your own sessions

unwedge's rules are only as good as the sessions they were checked on. Agents, harnesses and
models get stuck in different ways, so the benchmark combines several public datasets, and you
can add your own Claude Code and Codex sessions to it.

## The session format

Every session is one JSON object per line (`unwedge-session/1`, see `src/unwedge/dataset.py`):

```json
{"format": "unwedge-session/1", "source": "local-claude-code", "session_id": "a1b2c3d4",
 "group": "burn", "stuck_turn": 12, "resolved": false, "exit_status": "", "model": "",
 "goal": "Fix the flaky login test",
 "turns": [{"index": 1, "command": "read tests/test_login.py", "tool": "read", "tool_class": "navigate",
            "observation": "...", "is_error": false, "changes_state": false, "cost_units": 1830.5}]}
```

| field | meaning |
|---|---|
| `group` | `success` (the task was done), `burn` (it got stuck or ran out of budget), `wrong` (it finished but got it wrong), `submitted` (finished, outcome unknown) |
| `stuck_turn` | optional: the first turn of the loop, if you know it |
| `tool_class` | `navigate`, `search`, `edit`, `run`, `submit` or `invalid` |
| `cost_units` | a proxy for the tokens the agent's model call used on that turn |

Text is scrubbed of common secrets when a session is converted.

## Label your own sessions

```bash
unwedge export --limit 50 --out my-sessions.jsonl
```

This replays your most recent Claude Code transcripts and Codex rollouts locally (nothing is sent
anywhere) and writes one line per session with `"group": null`. Each line also has
`"unwedge_first_alarm"`: the turn where unwedge's code tier would have fired, which is usually
the fastest place to start looking.

For each line, set `group` and, when it got stuck, `stuck_turn`. `unwedge replay <transcript>`
shows a session turn by turn if you need more context. Then measure unwedge on your sessions
next to the public ones:

```bash
python benchmarks/multisource.py --extra my-sessions.jsonl
```

Your sessions appear as their own source (`local-claude-code`, `local-codex`) in
`benchmarks/results/multisource.md`, including a "tuned on the other sources" row that shows how
well rules chosen on public data transfer to your work.

The exported file contains your commands and tool output. Secrets are scrubbed by pattern, which
cannot be perfect: review the file before you share it with anyone.

## Public datasets in the benchmark

| source | agent / harness | models | groups used | license |
|---|---|---|---|---|
| `nebius` ([nebius/SWE-agent-trajectories](https://huggingface.co/datasets/nebius/SWE-agent-trajectories)) | SWE-agent | Llama 70B | success, burn (context exhausted), wrong | CC-BY-4.0 |
| `swe-smith` ([SWE-bench/SWE-smith-trajectories](https://huggingface.co/datasets/SWE-bench/SWE-smith-trajectories), `tool` split) | SWE-agent, function calling | Claude 3.7 Sonnet, Claude 3.5 Sonnet, GPT-4o | success, burn (cost, context or time limit), wrong | MIT |
| `swe-gym` ([SWE-Gym/OpenHands-Sampled-Trajectories](https://huggingface.co/datasets/SWE-Gym/OpenHands-Sampled-Trajectories)) | OpenHands | not stated | success, burn (cut off without finishing), wrong | not stated on the card |
| `jetbrains` ([JetBrains-Research/agent-trajectories-swe-bench-test-minus-verified](https://huggingface.co/datasets/JetBrains-Research/agent-trajectories-swe-bench-test-minus-verified)) | mini-swe-agent | GPT-5-mini, GPT-5.2 | submitted, limit (cost limit without a loop) | MIT |

None of them is redistributed here. To rebuild the corpus:

```bash
pip install -e ".[bench]"
python benchmarks/fetch_trajectories.py   # the original SWE-agent sample
python benchmarks/fetch_sources.py        # ~330 MB of parquet from the other datasets
python benchmarks/build_corpus.py         # -> benchmarks/data/corpus/<source>.jsonl
python benchmarks/multisource.py          # -> benchmarks/results/multisource.md
```

Labels come from each dataset's own fields (`sources.py` documents the rules). They describe the
outcome of a session, not whether it looped, so they are a proxy: some "burn" sessions ran out of
budget without looping, and some successful sessions contain a short loop that the agent escaped
on its own. Turn-level labels (`stuck_turn`) remove that noise; they are the most valuable thing
you can add.

## Add another dataset

Chat-message traces in the common formats (OpenAI tool calls, SWE-agent function markup,
mini-swe-agent bash blocks) convert with `unwedge.adapters.messages.session_turns`. Add a
loader and a labelling rule to `benchmarks/sources.py`, a fetch entry to `fetch_sources.py`, and
the source name to `SOURCES`.
