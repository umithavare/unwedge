"""Side-by-side view of the shipped policy across analysis files, for paired comparisons
(for example jev and Laya scored on the same sessions).

Usage:  python benchmarks/compare.py plain_on_laya-multilingual laya-multilingual
        (names of results/analysis_<name>.json files written by analyze.py)
"""

from __future__ import annotations

import argparse
import json

from common import RESULTS

POLICIES = (
    ("code_tier_only", "code only"),
    ("full", "code + provider (shipped)"),
    ("jev_only", "provider only"),
    ("jev_brake", "provider overrides code"),
)


def rows(name: str) -> list[str]:
    report = json.loads((RESULTS / f"analysis_{name}.json").read_text(encoding="utf-8"))
    successes = report["sessions"]["success"]
    lines = []
    for mode, label in POLICIES:
        m = report["report_policy"][mode]
        any_message = m["messages"]["success"]["sessions_with_any"]
        lines.append(f"| {name} | {label} | {m['catch']:.0%} | {m['false_alarm_count']} of {successes} | "
                     f"{any_message:.0%} | {m['savings']:.0%} |")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("names", nargs="+", help="analysis names, e.g. plain_on_laya-multilingual")
    args = parser.parse_args()
    print("| scores | policy | caught | false alarms | successful sessions with any message | recoverable spend |")
    print("|---|---|---|---|---|---|")
    for name in args.names:
        for line in rows(name):
            print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
