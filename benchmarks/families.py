"""Detector families. Each family is a grid of parameter combos; each combo yields the
first alarm turn for every session. Selection happens later, inside cross-validation.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass

import numpy as np
from features import INF, Flat, first_alarm, persistent

from unwedge.code_signals import CodeSignals
from unwedge.guard import GuardConfig, is_gated
from unwedge.policy import Action, PolicyState, Thresholds, Verdict, step

OFF = None
MAX_TURNS = (10, 12, 15, 20, 25, 30, 40, 50, 60, OFF)


@dataclass(frozen=True)
class Family:
    name: str
    params: tuple[dict, ...]
    alarms: np.ndarray  # (combos, sessions)


def _feature_first(flat: Flat, feature: str, threshold: float | None) -> np.ndarray:
    if threshold is OFF:
        return np.full(len(flat.starts), INF)
    return first_alarm(flat, flat.code[feature] >= threshold)


def _turn_cap(flat: Flat, cap: int | None) -> np.ndarray:
    return np.full(len(flat.starts), INF) if cap is OFF else np.where(flat.n_turns >= cap, float(cap), INF)


def max_turns_family(flat: Flat) -> Family:
    params = tuple({"max_turns": cap} for cap in MAX_TURNS)
    return Family("max_turns", params, np.stack([_turn_cap(flat, p["max_turns"]) for p in params]).astype(np.float32))


CODE_GRID = {
    "repeat_without_change": (1, 2, 3, OFF),
    "result_repeats": (1, 2, 3, 5, OFF),
    "error_repeats": (1, 2, 3, 5, OFF),
    "read_only_streak": (6, 10, 15, OFF),
    "turns_since_change": (10, 15, 20, 30, OFF),
    "max_turns": (15, 20, 25, 30, 40, 50, 60, OFF),
}


def code_family(flat: Flat) -> Family:
    """OR of thresholded loop counters, plus an optional turn cap (a real code tier has one)."""
    tables = {
        name: {v: (_turn_cap(flat, v) if name == "max_turns" else _feature_first(flat, name, v)) for v in values}
        for name, values in CODE_GRID.items()
    }
    params, rows = [], []
    for combo in itertools.product(*CODE_GRID.values()):
        param = dict(zip(CODE_GRID, combo, strict=False))
        params.append(param)
        rows.append(np.minimum.reduce([tables[name][value] for name, value in param.items()]))
    return Family("code", tuple(params), np.stack(rows).astype(np.float32))


JEV_GRID = {
    "stall_min": (0.0, 0.5, 0.7, 0.8, 0.85, 0.9, 0.95),
    "p0_min": (0.0, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8),
    "veto_gate": (0.6, OFF),
    "consecutive": (1, 2, 3),
}


def jev_condition(flat: Flat, stall_min: float, p0_min: float, veto_gate: float | None) -> np.ndarray:
    """Blocked or unscored turns never alarm: that is the fail-open behaviour in production."""
    jev = flat.jev
    usable = flat.scored & ~flat.blocked
    cond = usable & (np.nan_to_num(jev["stall"]) >= stall_min) & (np.nan_to_num(jev["p0"]) >= p0_min)
    if veto_gate is not OFF:
        cond &= np.nan_to_num(jev["gate"]) < veto_gate
    return cond


def jev_family(flat: Flat) -> Family:
    params, rows = [], []
    for combo in itertools.product(*JEV_GRID.values()):
        param = dict(zip(JEV_GRID, combo, strict=False))
        if param["stall_min"] == 0.0 and param["p0_min"] == 0.0:
            continue  # "always alarm" is not a detector
        cond = jev_condition(flat, param["stall_min"], param["p0_min"], param["veto_gate"])
        params.append(param)
        rows.append(first_alarm(flat, persistent(flat, cond, param["consecutive"])))
    return Family("jev", tuple(params), np.stack(rows).astype(np.float32))


AND_CODE_GRID = {
    "repeat_without_change": (1, 2, OFF),
    "result_repeats": (1, 2, OFF),
    "error_repeats": (1, 2, 3, OFF),
    "read_only_streak": (6, 10, OFF),
    "turns_since_change": (10, 20, OFF),
}
AND_JEV_GRID = {"stall_min": (0.0, 0.5, 0.7, 0.85), "p0_min": (0.0, 0.2, 0.4, 0.6), "veto_gate": (0.6, OFF)}


def hybrid_and_family(flat: Flat) -> Family:
    """Code suspects, jev confirms at the same turn; the turn cap stays as a code-only net.
    This is where goal-relative judgment could remove code's false alarms."""
    code_masks = {}
    for combo in itertools.product(*AND_CODE_GRID.values()):
        param = dict(zip(AND_CODE_GRID, combo, strict=False))
        if all(v is OFF for v in combo):
            continue
        mask = np.zeros(len(flat.turn), dtype=bool)
        for name, value in param.items():
            if value is not OFF:
                mask |= flat.code[name] >= value
        code_masks[combo] = (param, mask)
    jev_masks = {
        combo: (dict(zip(AND_JEV_GRID, combo, strict=False)), jev_condition(flat, *combo))
        for combo in itertools.product(*AND_JEV_GRID.values())
    }
    caps = {cap: _turn_cap(flat, cap) for cap in (30, 40, 60, OFF)}
    params, rows = [], []
    for code_param, code_mask in code_masks.values():
        for jev_param, jev_mask in jev_masks.values():
            first = first_alarm(flat, code_mask & jev_mask)
            for cap, cap_alarm in caps.items():
                params.append({**{f"code.{k}": v for k, v in code_param.items()},
                               **{f"jev.{k}": v for k, v in jev_param.items()}, "max_turns": cap})
                rows.append(np.minimum(first, cap_alarm))
    return Family("hybrid_and", tuple(params), np.stack(rows).astype(np.float32))


POLICY_MODES = ("full", "jev_brake", "code_tier_only", "jev_only")
# what reaches the agent in hint mode (hooks.render): a gate veto (FLAG) and CASCADE are only logged
AGENT_MESSAGES = frozenset({Action.HINT, Action.VERIFY_HINT, Action.RETURN_HINT, Action.ESCALATE, Action.KILL})


def report_policy_alarms(flat: Flat, sessions, actions: frozenset[Action], mode: str = "full") -> np.ndarray:
    """Replay the policy exactly as the Guard runs it (code gating, bands, hysteresis, veto,
    code tier). Nothing is tuned.

    full           the shipped policy: code tier acts on blatant loops, the provider adds alarms
    jev_brake      the design doc's original policy: on gated turns the provider's verdict
                   replaces the code tier (kept to show why it was changed)
    code_tier_only never consults the provider
    jev_only       only the provider's judgments, no code tier
    """
    alarms = np.full(len(flat.starts), INF)
    for i in range(len(flat.starts)):
        for row, decision in _replay_policy(flat, i, mode):
            if decision.action in actions:
                alarms[i] = flat.turn[row]
                break
    return alarms


def policy_message_counts(flat: Flat, mode: str = "full") -> np.ndarray:
    """How many messages each session's agent would receive in hint mode, over the whole session."""
    return np.array([sum(1 for _, decision in _replay_policy(flat, i, mode) if decision.action in AGENT_MESSAGES)
                     for i in range(len(flat.starts))], dtype=np.int32)


def _replay_policy(flat: Flat, i: int, mode: str):
    """Yield (row, decision) for every turn of session i."""
    if mode not in POLICY_MODES:
        raise ValueError(f"unknown mode {mode}")
    thresholds, config = Thresholds(), GuardConfig()
    state = PolicyState()
    for row in range(flat.starts[i], flat.starts[i] + flat.n_turns[i]):
        code = _code_signals_at(flat, row)
        verdict = None
        if mode != "code_tier_only" and is_gated(code, config) and flat.scored[row] and not flat.blocked[row]:
            verdict = _verdict_at(flat, row)
        if verdict is None and mode == "jev_only":
            continue
        state, decision = step(state, verdict, code, thresholds, code_first=mode == "full")
        yield row, decision


def _code_signals_at(flat: Flat, row: int) -> CodeSignals:
    values = {name: flat.code[name][row] for name in flat.code}
    return CodeSignals(
        turn=int(flat.turn[row]),
        exact_repeats=int(values["exact_repeats"]),
        repeat_without_change=int(values["repeat_without_change"]),
        action_similarity=float(values["action_similarity"]),
        result_repeats=int(values["result_repeats"]),
        result_similarity=float(values["result_similarity"]),
        error_repeats=int(values["error_repeats"]),
        consecutive_errors=int(values["consecutive_errors"]),
        turns_since_change=int(values["turns_since_change"]),
        read_only_streak=int(values["read_only_streak"]),
        invalid_streak=int(values["invalid_streak"]),
        pair_repeats=int(values["pair_repeats"]),
        cycle_repeats=int(values["cycle_repeats"]),
    )


def _verdict_at(flat: Flat, row: int) -> Verdict:
    jev = flat.jev
    return Verdict(stall=jev["stall"][row], p0=jev["p0"][row], progress=jev["progress"][row],
                   terminal=jev["terminal"][row], drift=jev["drift"][row], gate=jev["gate"][row])
