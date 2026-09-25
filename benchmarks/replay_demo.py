"""Live replay: feed a recorded session to the Guard turn by turn, with real blocking
jev calls and the hot-path timeout, and print what the guard would have done.

Usage:  python benchmarks/replay_demo.py [--session ID] [--group burn|success] [--timeout 0.5]
"""

from __future__ import annotations

import argparse
import time

from common import RESULTS, load_sessions

from unwedge.compactor import digest_line
from unwedge.guard import Guard, GuardConfig
from unwedge.policy import Action
from unwedge.providers import make_provider

QUIET = {Action.CONTINUE, Action.CASCADE, Action.FLAG}  # not sent to the agent (hooks.render)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session")
    parser.add_argument("--group", default="burn")
    parser.add_argument("--timeout", type=float, default=None)
    parser.add_argument("--provider", choices=("jev", "laya", "none"), default="jev")
    parser.add_argument("--model", default=None)
    args = parser.parse_args()
    sessions = load_sessions()
    session = next(s for s in sessions if (s.session_id == args.session if args.session else s.group == args.group))
    ledger = RESULTS / f"replay_{session.session_id}.jsonl"
    ledger.unlink(missing_ok=True)
    print(f"session {session.session_id}  group={session.group}  resolved={session.resolved}  "
          f"turns={len(session.turns)}  exit={session.exit_status}\n")
    provider = make_provider(args.provider, model=args.model)
    overrides = {"shadow": False, **({"timeout_s": args.timeout} if args.timeout else {})}
    config = GuardConfig.for_provider(provider, **overrides)
    spent, latencies, first_intervention = 0.0, [], None
    try:
        guard = Guard(session.goal, provider, config, ledger=ledger)
        for turn in session.turns:
            started = time.perf_counter()
            outcome = guard.on_turn(turn)
            wall_ms = (time.perf_counter() - started) * 1000
            spent += outcome.cost_usd
            if outcome.latency_ms is not None:
                latencies.append(wall_ms)
            v = outcome.verdict
            signals = (f"S={v.stall:.2f} P0={v.p0:.2f} T={v.terminal:.2f} G={v.gate:.2f}" if v else
                       ("fail-open: " + outcome.degraded[:40] if outcome.degraded else "not gated"))
            action = outcome.decision.action.value
            marker = "" if outcome.decision.action in QUIET else "  <<<"
            if marker and first_intervention is None:
                first_intervention = turn.index
            print(f"{digest_line(turn)[:78]:<78} | {signals:<34} | {wall_ms:6.0f} ms | {action}{marker}")
            if outcome.hint_text:
                print(f"{'':>80}hint [{outcome.hint_id}]: {outcome.hint_text}")
    finally:
        if provider is not None:
            provider.close()
    total = session.total_cost
    after = sum(t.cost_units for t in session.turns if first_intervention and t.index > first_intervention)
    print(f"\nfirst intervention: turn {first_intervention} of {len(session.turns)}; "
          f"agent spend after it: {after / total:.0%} of the session")
    if latencies:
        latencies.sort()
        print(f"guard wall-clock on gated turns: p50 {latencies[len(latencies) // 2]:.0f} ms, "
              f"max {latencies[-1]:.0f} ms over {len(latencies)} calls; provider spend ${spent:.5f}")
    print(f"ledger: {ledger.relative_to(RESULTS.parent.parent).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
