"""Figures for the README: the savings / false-alarm frontier of each detector family
(in-sample, so optimistic for every family alike) and signal timelines of example sessions.

Usage:  python benchmarks/plots.py [--variant plain] [--sessions ID ID ...]
"""

from __future__ import annotations

import argparse

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from analyze import Precomputed  # noqa: E402
from common import RESULTS, load_scored  # noqa: E402
from families import code_family, hybrid_and_family, jev_family, max_turns_family  # noqa: E402
from features import build_flat  # noqa: E402

COLORS = {"max_turns": "#8a8a8a", "code": "#2f6fb0", "jev": "#d0781f", "hybrid_and": "#2e8b57"}
LABELS = {"max_turns": "max_turns (today's default)", "code": "code only", "jev": "jev only",
          "hybrid_and": "code suspects + jev confirms"}


def frontier(fpr: np.ndarray, savings: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    xs, ys, best = [], [], -1.0
    for x in np.unique(fpr):
        y = savings[fpr <= x].max()
        if y > best:
            xs.append(x)
            ys.append(y)
            best = y
    return np.array(xs), np.array(ys)


def tradeoff(flat, out) -> None:
    pos, neg = flat.groups == "burn", flat.groups == "success"
    fig, ax = plt.subplots(figsize=(7.5, 4.8))
    for family in (max_turns_family(flat), code_family(flat), jev_family(flat), hybrid_and_family(flat)):
        fpr, _, savings = Precomputed(flat, family).train_metrics(flat, pos, neg)
        xs, ys = frontier(fpr, savings)
        ax.step(xs * 100, ys * 100, where="post", color=COLORS[family.name], label=LABELS[family.name], lw=2)
    ax.set_xlabel("false alarms: % of successful sessions interrupted")
    ax.set_ylabel("% of doomed-session spend recoverable")
    ax.set_xlim(0, 30)
    ax.set_ylim(0, 100)
    ax.grid(alpha=0.3)
    ax.legend(loc="lower right", frameon=False)
    ax.set_title("Best achievable trade-off per detector family (in-sample)")
    fig.tight_layout()
    fig.savefig(out, dpi=150)


def timelines(flat, session_ids, out) -> None:
    fig, axes = plt.subplots(len(session_ids), 1, figsize=(9, 2.6 * len(session_ids)), squeeze=False)
    legend: tuple[list, list] = ([], [])
    for ax, sid in zip(axes[:, 0], session_ids, strict=False):
        i = flat.session_ids.index(sid)
        rows = np.arange(flat.starts[i], flat.starts[i] + flat.n_turns[i])
        turns = flat.turn[rows]
        ax.plot(turns, flat.jev["stall"][rows], color="#d0781f", marker=".", label="jev stall (max)")
        ax.plot(turns, flat.jev["p0"][rows], color="#7b3fa0", marker=".", label="jev P(no progress)")
        ax.plot(turns, flat.jev["gate"][rows], color="#999999", lw=1, ls=":", label="jev gate")
        twin = ax.twinx()
        twin.step(turns, flat.code["repeat_without_change"][rows], color="#2f6fb0", where="post",
                  label="code: repeats w/o change")
        twin.step(turns, flat.code["error_repeats"][rows], color="#2e8b57", where="post", label="code: same error")
        twin.set_ylabel("count")
        blocked = rows[flat.blocked[rows]]
        if len(blocked):
            ax.scatter(flat.turn[blocked], np.full(len(blocked), 0.02), marker="x", color="red", label="WAF 403")
        ax.set_ylim(0, 1.02)
        ax.set_title(f"{sid}  ({flat.groups[i]})", fontsize=10, loc="left")
        ax.grid(alpha=0.3)
        for source in (ax, twin):
            for handle, label in zip(*source.get_legend_handles_labels(), strict=False):
                if label not in legend[1]:
                    legend[0].append(handle)
                    legend[1].append(label)
    fig.legend(*legend, loc="upper center", ncol=3, frameon=False, fontsize=8)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(out, dpi=150)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", default="plain")
    parser.add_argument("--sessions", nargs="*", default=[])
    args = parser.parse_args()
    flat = build_flat(*load_scored(args.variant))
    tradeoff(flat, RESULTS / "tradeoff.png")
    if args.sessions:
        timelines(flat, args.sessions, RESULTS / "timelines.png")
    print("figures written to", RESULTS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
