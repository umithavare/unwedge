"""`unwedge export`: turn your own Claude Code and Codex sessions into labelled data.

Each session becomes one line in the unwedge session format (see unwedge.dataset) with
"group": null for you to fill in, and unwedge's own first alarm to speed up labelling:

    "group": "success" | "burn" | "wrong"   (burn = it got stuck in a loop)
    "stuck_turn": 17                        (optional: the first turn of the loop)

The benchmark reads labelled files with `python benchmarks/multisource.py --extra FILE`.
Commands and tool output are included (secrets are scrubbed by pattern): review the file
before you share it.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from unwedge.dataset import session_to_record
from unwedge.replay import replay_file
from unwedge.turns import Session

MIN_TURNS = 3


@dataclass(frozen=True)
class ExportSummary:
    written: int
    flagged: int
    skipped: int


def export_sessions(paths: Iterable[str | Path], out: str | Path, min_turns: int = MIN_TURNS) -> ExportSummary:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    written = flagged = skipped = 0
    with out.open("w", encoding="utf-8") as handle:
        for path in paths:
            try:
                result = replay_file(path)  # code tier only: free, local, nothing leaves the machine
            except (OSError, ValueError, UnicodeDecodeError):
                skipped += 1
                continue
            if len(result.turns) < min_turns:
                skipped += 1
                continue
            session = Session(session_id=Path(path).stem, group="unlabelled", resolved=False, exit_status="",
                              goal=result.goal, turns=result.turns, source=f"local-{result.harness}")
            record = session_to_record(session, unwedge_first_alarm=result.first_intervention)
            record["group"] = None  # yours to label
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            written += 1
            flagged += result.first_intervention is not None
    return ExportSummary(written, flagged, skipped)
