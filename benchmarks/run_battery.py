"""Score every turn of every sampled session with a provider's call-A battery and store
the probabilities. Scoring every turn (not only gated ones) lets the analysis replay
any gating or threshold policy afterwards at zero inference cost.

Output: results/battery_<variant>.jsonl, keyed by (session, group, turn), so runs resume.

Examples:
  python benchmarks/run_battery.py --provider jev --variant plain            # the published jev run
  python benchmarks/run_battery.py --provider jev --variant fp               # + code fingerprints in the digest
  python benchmarks/run_battery.py --provider laya --model multilingual --per-group 30 --groups success,burn
"""

from __future__ import annotations

import argparse
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace

from common import RESULTS, load_sessions, read_jsonl

from unwedge.compactor import build_state
from unwedge.providers import ProviderBlocked, ProviderError, make_provider
from unwedge.questions import BATTERIES

MIN_TURN = 3  # a window needs a little history before stall questions mean anything


def compact(answers: dict) -> dict:
    out: dict = {}
    for key, answer in answers.items():
        if answer["type"] == "noul":
            out[key] = answer["noul"]
        elif answer["type"] == "score":
            out[key] = {"score": answer["score"], "confidence": answer.get("confidence"),
                        "p": {str(k): v for k, v in answer.get("probabilities", {}).items()}}
    return out


def pick_sessions(groups: list[str], per_group: int):
    sessions = [s for s in load_sessions() if s.group in groups]
    if not per_group:
        return sessions
    kept, counts = [], {}
    for session in sessions:  # file order, so a subset is reproducible and shared across providers
        if counts.get(session.group, 0) < per_group:
            kept.append(session)
            counts[session.group] = counts.get(session.group, 0) + 1
    return kept


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=("jev", "laya"), default="jev")
    parser.add_argument("--model", default=None, help="provider model, e.g. multilingual for laya")
    parser.add_argument("--variant", default=None, help="output label; default plain (jev) or laya-<model>")
    parser.add_argument("--fingerprints", action="store_true", help="add code fingerprints to digest lines")
    parser.add_argument("--groups", default="success,burn,wrong")
    parser.add_argument("--per-group", type=int, default=0, help="limit sessions per group (0 = all)")
    parser.add_argument("--max-turn", type=int, default=90)
    parser.add_argument("--budget", type=float, default=3.0, help="stop when this many USD are spent")
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--timeout", type=float, default=None)
    args = parser.parse_args()

    provider = make_provider(args.provider, model=args.model)
    profile = provider.profile
    variant = args.variant or ("fp" if args.fingerprints else "plain" if args.provider == "jev"
                               else f"laya-{provider.model}")
    digest = replace(profile.digest, fingerprints=args.fingerprints)
    battery = BATTERIES[profile.battery]
    workers = args.workers or (6 if args.provider == "jev" else 1)
    timeout = args.timeout or (15.0 if args.provider == "jev" else 600.0)

    out_path = RESULTS / f"battery_{variant}.jsonl"
    done = {(r["session_id"], r["group"], r["turn"]) for r in read_jsonl(out_path)}
    sessions = pick_sessions(args.groups.split(","), args.per_group)
    tasks = [((s.session_id, s.group, upto), build_state(s.goal, s.turns[:upto], digest))
             for s in sessions for upto in range(MIN_TURN, min(len(s.turns), args.max_turn) + 1)
             if (s.session_id, s.group, upto) not in done]
    print(f"{variant}: {len(sessions)} sessions, {len(tasks)} turns to score ({len(done)} already done)", flush=True)

    lock = threading.Lock()
    spent = {"usd": 0.0, "calls": 0, "errors": 0, "blocked": 0}
    stop = threading.Event()

    def write(record: dict) -> None:
        with out_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")

    def work(key, state):
        if stop.is_set():
            return
        base = {"session_id": key[0], "group": key[1], "turn": key[2], "variant": variant}
        try:
            result = provider.ask_with_retries(state, battery.call_a, timeout=timeout)
        except ProviderBlocked:  # permanent for this content: record it so the analysis can count it
            with lock:
                spent["blocked"] += 1
                write({**base, "blocked": True})
            return
        except ProviderError:  # transient: not recorded, a rerun retries it
            with lock:
                spent["errors"] += 1
            return
        with lock:
            spent["usd"] += result.cost_usd
            spent["calls"] += 1
            write({**base, "answers": compact(result.answers), "input_tokens": result.input_tokens,
                   "latency_s": round(result.latency_s, 4), "model": result.model})
            if spent["usd"] >= args.budget:
                stop.set()

    started = time.time()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(work, key, state) for key, state in tasks]
        for n, future in enumerate(as_completed(futures), start=1):
            future.result()
            if n % 100 == 0 or n == len(futures):
                rate = spent["calls"] / max(time.time() - started, 1e-6)
                print(f"{n}/{len(futures)} calls={spent['calls']} blocked={spent['blocked']} "
                      f"errors={spent['errors']} spent=${spent['usd']:.3f} rate={rate:.2f}/s", flush=True)
    provider.close()
    if stop.is_set():
        print(f"budget ${args.budget} reached; rerun to resume", flush=True)
    print(f"done: calls={spent['calls']} blocked={spent['blocked']} errors={spent['errors']} "
          f"spent=${spent['usd']:.4f}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
