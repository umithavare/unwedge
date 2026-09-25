# Providers

unwedge's code tier (repeat, fingerprint and error-signature counters) runs everywhere for
free. A **provider** adds judgments code cannot make: is the agent still moving toward this
session's goal, is the work already done, is it drifting, does a tool result talk to the
reader. Providers are typed-decision models that answer `noul` / `choice` / `score` questions
with probabilities; they never generate text.

| | `none` | `jev` | `laya` |
|---|---|---|---|
| what | code tier only | TypeSafe's hosted jev API | Laya, open weights, on your machine |
| where it runs | locally | api.typesafe.ai (US) | `laya-serve` or `unwedge serve` on localhost |
| cost | free | ~$0.0001 per judged turn | free (your hardware) |
| latency per judged turn | 0 | p50 0.32 s, p99 0.64 s (measured from Turkey) | p50 2.4 s (`multilingual`) to 4.1 s (`english`) on a CPU with 8 threads; GPU and Apple silicon not measured |
| gain over code alone in our benchmark | – | +5 points of doomed sessions caught | none measured |
| context | – | large: full question battery, 12-turn digest | 512-1,024 tokens: compact battery and digest |
| data leaves the machine | no | yes, scrubbed of secrets | no |

Pick one with `UNWEDGE_PROVIDER` (or the plugin option). `auto` (the default) means `jev` if
`TYPESAFE_API_KEY` is set, otherwise `none`.

## jev (TypeSafe)

```bash
export TYPESAFE_API_KEY=...            # never commit it
export UNWEDGE_PROVIDER=jev
unwedge doctor
```

- The model is pinned to `jev-1.13.0`: an alias can move and shift every threshold.
- The client limits itself to 16 requests/s (the documented limit is 1,200/min and the API
  sends no rate-limit headers).
- **Edge firewall.** The API sits behind Cloudflare. In our benchmark about 6% of calls
  carrying agent transcripts were answered with HTTP 403 (for example, SWE-bench's standard
  `python -c "import ..."` line). unwedge treats a 403 as "no judgment" and continues on the
  code tier; it does not try to get around the firewall.
- Everything sent is scrubbed of secrets first and clipped to a small digest (~2,400 tokens).

## laya (local, open weights)

[Laya](https://github.com/NandhaKishorM/laya) (Convai Innovations) is an open-weight
typed-decision model that answers the same question types with the same answer schema, and
ships a server that speaks the same HTTP protocol as jev. [laya-mlx](https://github.com/mizorewww/laya-mlx)
is a native MLX port for Apple silicon.

### Any OS: laya-serve (PyTorch)

```bash
pip install "laya[serve]"               # CPU-only machines: install torch from the PyTorch CPU index first
LAYA_HOST=127.0.0.1 LAYA_PORT=8000 LAYA_PRELOAD=1 LAYA_MODELS=english laya-serve
export UNWEDGE_PROVIDER=laya            # LAYA_URL defaults to http://127.0.0.1:8000/v1/systemone
unwedge doctor
```

### Apple silicon: laya-mlx through `unwedge serve`

laya-mlx has no HTTP server of its own, and hook processes are too short-lived to load a
checkpoint, so unwedge can host one:

```bash
pip install "unwedge[laya-mlx]"
unwedge serve --backend mlx --model english        # http://127.0.0.1:8000/v1/systemone
export UNWEDGE_PROVIDER=laya
```

`unwedge serve` binds to 127.0.0.1 by default and refuses other addresses unless you give it a
bearer key (`--api-key-env NAME`; clients send it via `LAYA_API_KEY`). It can also run the
PyTorch package (`--backend torch`).

In a long-running Python process you can skip the server: `make_provider("laya-local")` loads
the checkpoint in-process (a timed-out forward pass finishes in the background). Hooks cannot
use it, because every hook call is a new process that would load the model again, so
`UNWEDGE_PROVIDER` accepts only `none`, `jev` and `laya`.

### Which checkpoint

| checkpoint | context | notes |
|---|---|---|
| `english` (default) | 512 tokens | in our benchmark: answers near the middle for every question, in stuck and healthy sessions alike; p50 4.1 s on a CPU |
| `multilingual` | 1,024 tokens | fastest (322M), meant for non-English text; in our benchmark: "yes" to almost every question; p50 2.4 s on a CPU |
| `typed-decisions` | 1,024 tokens | tuned for upstream workflows; near-uninformative on this task in our probes |

Set it with `LAYA_MODEL` (or the plugin option). unwedge sends Laya a compact state (goal,
latest result, recent steps newest first) sized to the checkpoint's context, and a compact
question battery whose options fit Laya's per-option budget of 48 tokens.

**Quality.** In our [benchmark](benchmark.md#laya) neither checkpoint separated stuck from
healthy sessions, so with the shipped policy `laya` behaves like `none` (plus CPU load). The
questions and thresholds were written for jev and not tuned for Laya. Use Laya in shadow mode,
or as a starting point for Laya-specific questions; contributions that make it useful are
welcome.

## Writing your own provider

Anything with this shape works (see `unwedge/providers/base.py`):

```python
class MyProvider:
    profile: Profile          # battery ("full"/"compact"), digest layout, timeout, price

    def ask(self, state, questions, *, timeout=None) -> ProviderResult: ...
    def close(self) -> None: ...
```

Any server that implements `POST /v1/systemone` with `{model, state, questions}` →
`{model, answers, usage}` works with `UNWEDGE_PROVIDER=laya` and `LAYA_URL`/`LAYA_MODEL`.
