"""`unwedge report`: what the hooks saw, per session, from <home>/ledger.jsonl."""

from __future__ import annotations

import json
import time
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

QUIET = {"continue", "cascade"}


@dataclass
class SessionSummary:
    harness: str
    session: str
    cwd: str | None = None
    turns: int = 0
    gated: int = 0
    judged: int = 0
    degraded: int = 0
    first_intervention: int | None = None
    last_ts: float = 0.0
    actions: Counter = field(default_factory=Counter)
    latencies: list = field(default_factory=list)


def load_ledger(home: Path, days: float | None = None) -> list[dict]:
    path = Path(home) / "ledger.jsonl"
    if not path.exists():
        return []
    cutoff = time.time() - days * 86400 if days else 0.0
    records = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if record.get("ts", 0) >= cutoff:
                records.append(record)
    return records


def summarize(records: Iterable[dict]) -> list[SessionSummary]:
    sessions: dict[tuple[str, str], SessionSummary] = {}
    for record in records:
        key = (record.get("harness", "?"), str(record.get("session")))
        summary = sessions.setdefault(key, SessionSummary(harness=key[0], session=key[1], cwd=record.get("cwd")))
        summary.turns = max(summary.turns, int(record.get("turn") or 0))
        summary.gated += bool(record.get("gated"))
        summary.judged += record.get("stall") is not None
        summary.degraded += bool(record.get("degraded")) and record.get("provider") not in ("none", None)
        summary.last_ts = max(summary.last_ts, float(record.get("ts") or 0))
        action = record.get("action", "continue")
        summary.actions[action] += 1
        if action not in QUIET and summary.first_intervention is None:
            summary.first_intervention = record.get("turn")
        if record.get("latency_ms") is not None:
            summary.latencies.append(record["latency_ms"])
    return sorted(sessions.values(), key=lambda s: s.last_ts, reverse=True)


def format_report(summaries: list[SessionSummary]) -> list[str]:
    if not summaries:
        return ["No guarded sessions yet. Install the hook (see README) and run an agent session."]
    lines = [f"{'when':<16} {'harness':<11} {'turns':>5} {'judged':>6} {'first alarm':>11}  actions  (cwd)"]
    for s in summaries:
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(s.last_ts)) if s.last_ts else "?"
        acts = ", ".join(f"{a}={n}" for a, n in s.actions.most_common() if a not in QUIET) or "-"
        first = f"turn {s.first_intervention}" if s.first_intervention else "-"
        lines.append(f"{when:<16} {s.harness:<11} {s.turns:>5} {s.judged:>6} {first:>11}  {acts}  ({s.cwd or ''})")
    flagged = [s for s in summaries if s.first_intervention]
    wasted = sum(s.turns - s.first_intervention for s in flagged)
    lines.append("")
    lines.append(f"{len(summaries)} sessions, {len(flagged)} with a loop alarm; "
                 f"{wasted} turns ran after the first alarm.")
    latencies = sorted(x for s in summaries for x in s.latencies)
    if latencies:
        lines.append(f"provider latency p50 {latencies[len(latencies) // 2]:.0f} ms, "
                     f"max {latencies[-1]:.0f} ms over {len(latencies)} calls")
    return lines
