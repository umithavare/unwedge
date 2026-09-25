"""Null-request spread: send the same state N times and measure how much each answer
moves. Thresholds must sit farther than this from any value the policy acts on.

Usage:  python benchmarks/null_spread.py [--states 10] [--repeats 10]
"""

from __future__ import annotations

import argparse
import json
import random

import numpy as np
from common import RESULTS, load_sessions

from unwedge.compactor import build_state
from unwedge.policy import Verdict
from unwedge.providers import ProviderBlocked, make_provider
from unwedge.questions import BATTERIES


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--states", type=int, default=10)
    parser.add_argument("--repeats", type=int, default=10)
    parser.add_argument("--provider", choices=("jev", "laya"), default="jev")
    parser.add_argument("--model", default=None)
    args = parser.parse_args()
    rng = random.Random(7)
    sessions = [s for s in load_sessions() if len(s.turns) >= 8]
    picks = [(s, rng.randint(5, len(s.turns))) for s in rng.sample(sessions, min(len(sessions), args.states * 2))]
    spreads: dict[str, list[float]] = {}
    measured = 0
    provider = make_provider(args.provider, model=args.model)
    battery = BATTERIES[provider.profile.battery]
    try:
        for session, upto in picks:
            if measured >= args.states:
                break
            state = build_state(session.goal, session.turns[:upto], provider.profile.digest)
            try:
                answers = [provider.ask_with_retries(state, battery.call_a, timeout=600).answers
                           for _ in range(args.repeats)]
            except ProviderBlocked:
                continue
            measured += 1
            verdicts = [Verdict.from_answers(a).__dict__ for a in answers]
            for key in verdicts[0]:
                values = np.array([v[key] for v in verdicts])
                spreads.setdefault(key, []).append(float(values.max() - values.min()))
    finally:
        provider.close()
    summary = {key: {"mean_range": float(np.mean(v)), "max_range": float(np.max(v))} for key, v in spreads.items()}
    summary["_states"] = measured
    summary["_repeats"] = args.repeats
    (RESULTS / f"null_spread_{args.provider}.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
