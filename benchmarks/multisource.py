"""Multi-source benchmark for the code tier: does unwedge generalize across agents, harnesses
and models?

Sources (see sources.py): nebius (SWE-agent, Llama 70B), swe-smith (SWE-agent with function
calling; Claude 3.7/3.5 Sonnet, GPT-4o), swe-gym (OpenHands), jetbrains (mini-swe-agent;
GPT-5-mini, GPT-5.2; no success label, so its "submitted" sessions stand in as negatives).

Reported per source:
  shipped      the code tier exactly as released, untuned
  tuned        detector families tuned on the OTHER sources (leave one source out) under a
               false-alarm cap on their successful sessions, then scored on the held-out source

Your own labelled sessions (from `unwedge export`) join as extra sources with --extra FILE.

Usage:  python benchmarks/multisource.py [--alphas 0.01 0.02 0.05] [--no-logistic] [--extra FILE ...]
"""

from __future__ import annotations

import argparse
import json
import time

import numpy as np
from analyze import Precomputed, logistic_alarms, logistic_features, select
from common import RESULTS
from families import code_family, max_turns_family, report_policy_alarms
from features import INF, Flat, build_flat, evaluate
from sources import SOURCES, corpus_path

from unwedge.dataset import read_sessions
from unwedge.policy import Action
from unwedge.turns import Session

INTERVENTIONS = frozenset({Action.HINT, Action.ESCALATE, Action.KILL})


def load_corpus(sources=SOURCES) -> list[Session]:
    sessions: list[Session] = []
    for source in sources:
        path = corpus_path(source)
        if not path.exists():
            raise FileNotFoundError(f"{path} is missing; run benchmarks/build_corpus.py")
        sessions.extend(read_sessions(path))
    return sessions


def sources_of(flat: Flat) -> list[str]:
    present = set(flat.sources.tolist())
    return [s for s in SOURCES if s in present] + sorted(present - set(SOURCES))


def source_metrics(flat: Flat, alarms: np.ndarray) -> dict:
    """Per-source and pooled metrics for one alarm vector."""
    out = {}
    effective = np.where(alarms < flat.n_turns, alarms, INF)
    for source in [*sources_of(flat), "all"]:
        in_source = np.ones(len(flat.groups), bool) if source == "all" else flat.sources == source
        pos, neg = in_source & (flat.groups == "burn"), in_source & (flat.groups == "success")
        m = evaluate(flat, alarms, pos, neg)
        submitted, wrong = in_source & (flat.groups == "submitted"), in_source & (flat.groups == "wrong")
        out[source] = {
            "catch": m.catch, "false_alarm": m.false_alarm, "savings": m.savings, "position": m.position,
            "submitted_alarm": float(np.isfinite(effective[submitted]).mean()) if submitted.any() else None,
            "wrong_alarm": float(np.isfinite(effective[wrong]).mean()) if wrong.any() else None,
            "n_burn": int(pos.sum()), "n_success": int(neg.sum()),
        }
    return out


def leave_one_source_out(flat: Flat, pre: Precomputed, alpha: float) -> tuple[np.ndarray, dict]:
    alarms, chosen = np.full(len(flat.groups), INF), {}
    for held in sources_of(flat):
        train = flat.sources != held
        pos, neg = train & (flat.groups == "burn"), train & (flat.groups == "success")
        fpr, catch, savings = pre.train_metrics(flat, pos, neg)
        index = select(fpr, catch, savings, alpha)
        test = flat.sources == held
        alarms[test] = pre.family.alarms[index, test] if index is not None else INF
        chosen[held] = pre.family.params[index] if index is not None else None
    return alarms, chosen


def leave_one_source_out_logistic(flat: Flat, alpha: float) -> tuple[np.ndarray, dict]:
    x = logistic_features(flat, with_jev=False)
    labels = (flat.groups == "burn").astype(int)
    alarms, chosen = np.full(len(flat.groups), INF), {}
    for held in sources_of(flat):
        train = flat.sources != held
        train_sessions = np.flatnonzero(train & np.isin(flat.groups, ("burn", "success")))
        family = logistic_alarms(flat, x, train_sessions, labels)
        pre = Precomputed(flat, family)
        fpr, catch, savings = pre.train_metrics(flat, train & (flat.groups == "burn"),
                                                train & (flat.groups == "success"))
        index = select(fpr, catch, savings, alpha)
        test = flat.sources == held
        alarms[test] = family.alarms[index, test] if index is not None else INF
        chosen[held] = family.params[index] if index is not None else None
    return alarms, chosen


def write_markdown(report: dict, path) -> None:
    lines = ["# Multi-source benchmark (code tier)", "", f"Sessions: {report['sessions']}", ""]

    def table(title: str, metrics: dict) -> None:
        lines.extend([f"### {title}", "", "| source | caught | false alarms | recoverable spend | first alert at | "
                      "normal-submit alarms | wrong-patch alarms |", "|---|---|---|---|---|---|---|"])
        for source, m in metrics.items():
            def pct(value):
                return "n/a" if value is None or value != value else f"{value:.0%}"
            fa = "n/a" if m["false_alarm"] != m["false_alarm"] else f"{m['false_alarm']:.1%} of {m['n_success']}"
            lines.append(f"| {source} | {pct(m['catch'])} of {m['n_burn']} | {fa} | {pct(m['savings'])} | "
                         f"{m['position']:.2f} | {pct(m['submitted_alarm'])} | {pct(m['wrong_alarm'])} |")
        lines.append("")

    table("Shipped code tier (untuned)", report["shipped"])
    for alpha, entry in report["tuned"].items():
        for name, metrics in entry.items():
            table(f"{name}, tuned on the other sources, false-alarm cap {float(alpha):.0%}", metrics)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--alphas", type=float, nargs="+", default=[0.01, 0.02, 0.05])
    parser.add_argument("--no-logistic", action="store_true")
    parser.add_argument("--extra", nargs="*", default=[], help="labelled session files, e.g. from unwedge export")
    args = parser.parse_args()
    started = time.time()
    sessions = load_corpus()
    for path in args.extra:
        labelled = [s for s in read_sessions(path) if s.group in ("success", "burn", "wrong", "submitted")]
        print(f"{path}: {len(labelled)} labelled sessions", flush=True)
        sessions.extend(labelled)
    flat = build_flat(sessions, [])
    print(f"loaded {len(sessions)} sessions, {len(flat.turn)} turns ({time.time() - started:.0f}s)", flush=True)
    report: dict = {"sessions": {source: {group: int(((flat.sources == source) & (flat.groups == group)).sum())
                                          for group in ("success", "burn", "wrong", "submitted", "limit")}
                                 for source in sources_of(flat)}}
    shipped = report_policy_alarms(flat, sessions, INTERVENTIONS, "code_tier_only")
    report["shipped"] = source_metrics(flat, shipped)
    print("shipped:", json.dumps({k: round(v["catch"], 3) for k, v in report["shipped"].items()}), flush=True)
    families = {"max_turns": Precomputed(flat, max_turns_family(flat)), "code": Precomputed(flat, code_family(flat))}
    report["tuned"], report["chosen"] = {}, {}
    for alpha in args.alphas:
        entry, chosen = {}, {}
        for name, pre in families.items():
            alarms, chosen[name] = leave_one_source_out(flat, pre, alpha)
            entry[name] = source_metrics(flat, alarms)
        if not args.no_logistic:
            alarms, chosen["logistic_code"] = leave_one_source_out_logistic(flat, alpha)
            entry["logistic_code"] = source_metrics(flat, alarms)
        report["tuned"][str(alpha)], report["chosen"][str(alpha)] = entry, chosen
        pooled = {name: m["all"] for name, m in entry.items()}
        print(f"alpha={alpha}: " + ", ".join(f"{name} catch={m['catch']:.2f} fa={m['false_alarm']:.3f}"
                                             for name, m in pooled.items()), flush=True)
    (RESULTS / "multisource.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    write_markdown(report, RESULTS / "multisource.md")
    print(f"wrote {RESULTS / 'multisource.md'} ({time.time() - started:.0f}s)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
