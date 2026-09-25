"""On-disk session state for short-lived hook processes.

Every tool call runs a fresh `unwedge hook` process, so the history lives on disk:

    <home>/sessions/<harness>/<session_id>/
        goal.json       first and latest user prompt
        turns.jsonl     one scrubbed, clipped Turn per line
        verdicts.jsonl  the provider verdict (or none) recorded for each turn
    <home>/ledger.jsonl one line per guarded turn, for `unwedge report`

Tool output is stored locally, scrubbed of secrets and clipped; sessions older than
`retention_days` are deleted on the next session start.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path

from unwedge.compactor import clip
from unwedge.policy import Verdict
from unwedge.turns import ToolClass, Turn

OBSERVATION_CHARS = 4000  # enough for fingerprints and the latest result; keeps files small
_SAFE_ID = re.compile(r"[^A-Za-z0-9_.-]")


def safe_id(value: str) -> str:
    cleaned = _SAFE_ID.sub("-", value or "")[:128].strip(".")
    return cleaned or "unknown"


class LockTimeout(Exception):
    pass


class SessionStore:
    def __init__(self, home: Path, harness: str, session_id: str) -> None:
        self.dir = Path(home) / "sessions" / safe_id(harness) / safe_id(session_id)

    @contextmanager
    def lock(self, timeout: float = 2.0, stale_after: float = 10.0) -> Iterator[None]:
        """Cross-platform exclusive lock: overlapping async hooks append one at a time. Locked
        sections only read and append small files, so a lock older than `stale_after` belongs
        to a hook that was killed (for example by a harness timeout)."""
        self.dir.mkdir(parents=True, exist_ok=True)
        path = self.dir / ".lock"
        deadline = time.monotonic() + timeout
        while True:
            try:
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
                break
            except FileExistsError:
                try:
                    if time.time() - path.stat().st_mtime > stale_after:
                        path.unlink(missing_ok=True)  # a crashed hook left it behind
                        continue
                except FileNotFoundError:
                    continue
                if time.monotonic() > deadline:
                    raise LockTimeout(str(path)) from None
                time.sleep(0.02)
        try:
            yield
        finally:
            path.unlink(missing_ok=True)

    # goal -------------------------------------------------------------------------------
    def add_prompt(self, prompt: str) -> None:
        prompt = (prompt or "").strip()
        if not prompt:
            return
        current = self._read_json("goal.json") or {}
        first = current.get("first") or prompt
        self._write_json("goal.json", {"first": first, "latest": prompt})

    def goal(self) -> str:
        current = self._read_json("goal.json") or {}
        first, latest = current.get("first", ""), current.get("latest", "")
        if latest and latest != first:
            return f"{first}\n\nLatest instruction from the user: {latest}"
        return first

    # turns ------------------------------------------------------------------------------
    def next_index(self) -> int:
        return len(self._read_lines("turns.jsonl")) + 1

    def append_turn(self, turn: Turn) -> None:
        record = asdict(turn)
        record["tool_class"] = turn.tool_class.value
        record["observation"] = clip(turn.observation, OBSERVATION_CHARS)
        self._append("turns.jsonl", record)

    def turns(self) -> list[Turn]:
        out = []
        for record in self._read_lines("turns.jsonl"):
            try:
                out.append(Turn(**{**record, "tool_class": ToolClass(record["tool_class"])}))
            except (KeyError, TypeError, ValueError):
                continue  # a torn or foreign line never breaks the hook
        return out

    # verdicts ---------------------------------------------------------------------------
    def append_verdict(self, index: int, verdict: Verdict | None) -> None:
        self._append("verdicts.jsonl", {"turn": index, "verdict": asdict(verdict) if verdict else None})

    def verdicts(self) -> dict[int, Verdict | None]:
        out: dict[int, Verdict | None] = {}
        for record in self._read_lines("verdicts.jsonl"):
            try:
                out[int(record["turn"])] = Verdict(**record["verdict"]) if record.get("verdict") else None
            except (KeyError, TypeError, ValueError):
                continue
        return out

    # io ---------------------------------------------------------------------------------
    def _append(self, name: str, record: dict) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        with (self.dir / name).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _read_lines(self, name: str) -> list[dict]:
        path = self.dir / name
        if not path.exists():
            return []
        out = []
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
        return out

    def _read_json(self, name: str) -> dict | None:
        try:
            return json.loads((self.dir / name).read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            return None

    def _write_json(self, name: str, value: dict) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self.dir / f".{name}.tmp"
        tmp.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.dir / name)


def append_ledger(home: Path, record: dict) -> None:
    Path(home).mkdir(parents=True, exist_ok=True)
    with (Path(home) / "ledger.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def prune_sessions(home: Path, retention_days: float = 7.0) -> int:
    """Delete session directories untouched for longer than the retention period."""
    root = Path(home) / "sessions"
    if not root.exists():
        return 0
    cutoff, removed = time.time() - retention_days * 86400, 0
    for harness in root.iterdir():
        for session in harness.iterdir() if harness.is_dir() else ():
            try:
                if session.is_dir() and session.stat().st_mtime < cutoff:
                    shutil.rmtree(session, ignore_errors=True)
                    removed += 1
            except OSError:
                continue
    return removed
