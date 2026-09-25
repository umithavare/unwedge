"""Descriptive diagnostics over the stored battery (no inference): how each signal
behaves on successful vs doomed sessions, how often the gate fires on benign traffic,
how often the edge firewall blocks, what a call costs and how long it takes, how
stable a verdict is from one turn to the next, and how many turns code gating keeps.

Usage:  python benchmarks/diagnostics.py [--variant plain|fp|laya-<model>] [--sessions-from VARIANT]
"""

from __future__ import annotations

import argparse
import json

import numpy as np
from common import RESULTS, load_scored, restrict
from families import _code_signals_at
from features import build_flat

from unwedge.guard import GuardConfig, is_gated

SIGNALS = ("stall", "s_repeat", "s_unchanged", "s_error", "p0", "progress", "terminal", "drift", "gate")


def pct(values: np.ndarray, q: float) -> float:
    return float(np.percentile(values, q)) if len(values) else float("nan")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", default="plain", help="scores in results/battery_<variant>.jsonl")
    parser.add_argument("--sessions-from", metavar="VARIANT",
                        help="only the sessions another battery scored, for a paired comparison")
    args = parser.parse_args()
    sessions, battery = load_scored(args.variant)
    name = args.variant
    if args.sessions_from:
        sessions, battery = restrict(sessions, battery, args.sessions_from)
        name = f"{args.variant}_on_{args.sessions_from}"
    flat = build_flat(sessions, battery)
    group_of_row = flat.groups[flat.session_index]
    usable = flat.scored & ~flat.blocked
    groups = [g for g in ("success", "burn", "wrong") if (flat.groups == g).any()]
    usd_per_token = 0.0 if args.variant.startswith("laya") else 0.042e-6  # local models are free
    out: dict = {"variant": name}

    out["signals"] = {
        signal: {group: {"mean": float(np.nanmean(flat.jev[signal][usable & (group_of_row == group)])),
                         "p50": pct(flat.jev[signal][usable & (group_of_row == group)], 50),
                         "p90": pct(flat.jev[signal][usable & (group_of_row == group)], 90)}
                 for group in groups}
        for signal in SIGNALS
    }

    gate = np.nan_to_num(flat.jev["gate"])
    success_rows = usable & (group_of_row == "success")
    vetoed_sessions = {flat.session_index[r] for r in np.flatnonzero(usable & (gate >= 0.6))}
    out["gate_on_benign_traffic"] = {
        "turn_rate_ge_0.6": float((gate[usable] >= 0.6).mean()),
        "success_turn_rate_ge_0.6": float((gate[success_rows] >= 0.6).mean()),
        "sessions_with_a_veto": float(len(vetoed_sessions) / len(flat.starts)),
        "note": "no injected content in this data: every gate firing is a false positive",
    }

    terminal = flat.jev["terminal"]
    last3, anywhere = {}, {}
    for group in groups:
        tail_max, all_max = [], []
        for i in np.flatnonzero(flat.groups == group):
            rows = np.arange(flat.starts[i], flat.starts[i] + flat.n_turns[i])
            rows = rows[usable[rows]]
            if len(rows):
                tail_max.append(np.nanmax(terminal[rows[-3:]]))
                all_max.append(np.nanmax(terminal[rows]))
        last3[group] = {"mean": float(np.mean(tail_max)), "share_ge_0.9": float(np.mean(np.array(tail_max) >= 0.9))}
        anywhere[group] = {"share_sessions_ge_0.9": float(np.mean(np.array(all_max) >= 0.9))}
    out["terminal"] = {"max_over_last_3_turns": last3, "max_over_session": anywhere}

    records = [r for r in battery if "answers" in r]
    blocked = [r for r in battery if r.get("blocked")]
    latency = np.array([r["latency_s"] for r in records])
    tokens = np.array([r["input_tokens"] for r in records])
    blocked_sessions = {(r["session_id"], r["group"]) for r in blocked}
    out["calls"] = {
        "answered": len(records), "blocked_by_edge_firewall": len(blocked),
        "blocked_turn_share": len(blocked) / max(len(records) + len(blocked), 1),
        "sessions_with_any_block": len(blocked_sessions),
        "session_share_with_any_block": len(blocked_sessions) / len(flat.starts),
        "latency_s": {"p50": pct(latency, 50), "p90": pct(latency, 90), "p99": pct(latency, 99),
                      "max": float(latency.max()) if len(latency) else None},
        "input_tokens": {"mean": float(tokens.mean()), "p50": pct(tokens, 50), "max": float(tokens.max())},
        "usd_per_call": float(tokens.mean() * usd_per_token),
        "usd_total": float(tokens.sum() * usd_per_token),
    }

    same_session = flat.session_index[1:] == flat.session_index[:-1]
    both = same_session & usable[1:] & usable[:-1]
    stall, p0 = np.nan_to_num(flat.jev["stall"]), np.nan_to_num(flat.jev["p0"])
    out["stability"] = {
        "mean_abs_delta_stall": float(np.abs(np.diff(stall))[both].mean()),
        "mean_abs_delta_p0": float(np.abs(np.diff(p0))[both].mean()),
        "stall_flip_rate_at_0.85": float(((stall[1:] >= 0.85) != (stall[:-1] >= 0.85))[both].mean()),
        "p0_flip_rate_at_0.6": float(((p0[1:] >= 0.6) != (p0[:-1] >= 0.6))[both].mean()),
    }

    config = GuardConfig()
    gated = np.array([is_gated(_code_signals_at(flat, row), config) for row in range(len(flat.turn))])
    out["gating"] = {group: float(gated[group_of_row == group].mean()) for group in groups}
    out["gating"]["all"] = float(gated.mean())

    path = RESULTS / f"diagnostics_{name}.json"
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
