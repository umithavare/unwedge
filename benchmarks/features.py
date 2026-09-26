"""Per-session arrays and vectorized detector evaluation for the offline analysis.

Every detector reduces to one number per session: the first turn at which it would
alarm (INF when it never does). Metrics then follow from outcomes and costs.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

import numpy as np

from unwedge.code_signals import compute_signals
from unwedge.questions import DRIFT_KEY, GATE_KEYS, PROGRESS_KEY, STALL_KEYS, TERMINAL_KEY
from unwedge.turns import Session

INF = np.inf
CODE_FEATURES = (
    "exact_repeats", "repeat_without_change", "result_repeats", "error_repeats", "read_only_streak",
    "turns_since_change", "consecutive_errors", "invalid_streak", "action_similarity", "result_similarity",
    "pair_repeats", "cycle_repeats",
)
JEV_FEATURES = ("s_repeat", "s_unchanged", "s_error", "stall", "p0", "progress", "terminal", "drift", "gate")


@dataclass(frozen=True)
class Flat:
    """All sessions' turns concatenated; `starts[i]` is session i's first row."""

    session_ids: tuple[str, ...]
    groups: np.ndarray  # per session
    sources: np.ndarray  # per session: the dataset it came from
    n_turns: np.ndarray  # per session
    total_cost: np.ndarray  # per session
    starts: np.ndarray  # per session, offset into the flat arrays
    turn: np.ndarray  # flat, 1-based turn index
    session_index: np.ndarray  # flat
    cost_after: np.ndarray  # flat: cost of the turns after this one (what an alarm here saves)
    code: dict[str, np.ndarray]  # flat
    jev: dict[str, np.ndarray]  # flat, NaN when not scored
    blocked: np.ndarray  # flat bool: the call was refused by the edge firewall

    @property
    def scored(self) -> np.ndarray:
        return ~np.isnan(self.jev["stall"])


def build_flat(sessions: Sequence[Session], battery: Iterable[dict]) -> Flat:
    if any(not s.turns for s in sessions):
        raise ValueError("every session needs at least one turn (reduceat would borrow the next session's row)")
    answers = {(r["session_id"], r["group"], r["turn"]): r for r in battery}  # a task can be in two groups
    rows: dict[str, list] = {k: [] for k in ("turn", "session_index", "cost_after", "blocked", *CODE_FEATURES,
                                              *JEV_FEATURES)}
    starts, n_turns, totals = [], [], []
    for i, session in enumerate(sessions):
        starts.append(len(rows["turn"]))
        costs = np.array([t.cost_units for t in session.turns])
        after = costs[::-1].cumsum()[::-1] - costs  # cost of turns strictly after each turn
        n_turns.append(len(session.turns))
        totals.append(costs.sum())
        for signal, turn, saved in zip(compute_signals(session.turns), session.turns, after, strict=False):
            rows["turn"].append(turn.index)
            rows["session_index"].append(i)
            rows["cost_after"].append(saved)
            for name in CODE_FEATURES:
                rows[name].append(getattr(signal, name))
            record = answers.get((session.session_id, session.group, turn.index))
            rows["blocked"].append(bool(record and record.get("blocked")))
            values = _jev_values(record["answers"]) if record and "answers" in record else {}
            for name in JEV_FEATURES:
                rows[name].append(values.get(name, np.nan))
    return Flat(
        session_ids=tuple(s.session_id for s in sessions),
        groups=np.array([s.group for s in sessions]),
        sources=np.array([s.source or "nebius" for s in sessions]),
        n_turns=np.array(n_turns),
        total_cost=np.array(totals),
        starts=np.array(starts),
        turn=np.array(rows["turn"]),
        session_index=np.array(rows["session_index"]),
        cost_after=np.array(rows["cost_after"], dtype=float),
        code={name: np.array(rows[name], dtype=float) for name in CODE_FEATURES},
        jev={name: np.array(rows[name], dtype=float) for name in JEV_FEATURES},
        blocked=np.array(rows["blocked"], dtype=bool),
    )


def _jev_values(answers: dict) -> dict[str, float]:
    stall = [answers[k] for k in STALL_KEYS]
    progress = answers[PROGRESS_KEY]
    return {
        "s_repeat": stall[0], "s_unchanged": stall[1], "s_error": stall[2], "stall": max(stall),
        "p0": float(progress["p"].get("0", 0.0)), "progress": float(progress["score"]),
        "terminal": answers[TERMINAL_KEY], "drift": answers[DRIFT_KEY],
        "gate": max(answers[k] for k in GATE_KEYS),
    }


def first_alarm(flat: Flat, mask: np.ndarray) -> np.ndarray:
    """First alarming turn per session (INF if none) for a flat boolean mask."""
    values = np.where(mask, flat.turn, INF)
    return np.minimum.reduceat(values, flat.starts)


def persistent(flat: Flat, mask: np.ndarray, k: int) -> np.ndarray:
    """True where `mask` has held for k consecutive turns of the same session."""
    out = mask.copy()
    for lag in range(1, k):
        shifted = np.zeros_like(mask)
        shifted[lag:] = mask[:-lag]
        same_session = np.zeros_like(mask)
        same_session[lag:] = flat.session_index[lag:] == flat.session_index[:-lag]
        out &= shifted & same_session
    return out


def saved_cost(flat: Flat, alarms: np.ndarray) -> np.ndarray:
    """Per-session cost that stopping at the alarm turn would have saved."""
    saved = np.zeros(len(alarms))
    hit = np.isfinite(alarms)
    rows = flat.starts[hit] + alarms[hit].astype(int) - 1
    saved[hit] = flat.cost_after[rows]
    return saved


@dataclass(frozen=True)
class Metrics:
    catch: float  # share of positive sessions alarmed before their last turn
    false_alarm: float  # share of successful sessions alarmed before their last turn
    savings: float  # share of positive sessions' total cost that stopping at the alarm saves
    position: float  # median alarm turn / session length among caught positives
    turns_saved: float  # mean turns saved per positive session


def evaluate(flat: Flat, alarms: np.ndarray, positives: np.ndarray, negatives: np.ndarray) -> Metrics:
    effective = np.where(alarms < flat.n_turns, alarms, INF)  # an alarm on the final turn changes nothing
    caught = np.isfinite(effective)
    saved = saved_cost(flat, effective)
    pos_caught = caught & positives
    return Metrics(
        catch=float(caught[positives].mean()) if positives.any() else float("nan"),
        false_alarm=float(caught[negatives].mean()) if negatives.any() else float("nan"),
        savings=float(saved[positives].sum() / flat.total_cost[positives].sum()) if positives.any() else 0.0,
        position=(float(np.median(effective[pos_caught] / flat.n_turns[pos_caught])) if pos_caught.any()
                  else float("nan")),
        turns_saved=float(np.where(pos_caught, flat.n_turns - np.nan_to_num(effective, posinf=0), 0)[positives].mean())
        if positives.any() else 0.0,
    )
