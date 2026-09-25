"""The kill test: does jev catch doomed sessions that code cannot, early, without
false alarms on sessions that would have succeeded?

Positives: 'burn' sessions (failed after exhausting the context budget).
Negatives: 'success' sessions (resolved). 'wrong' sessions (failed, submitted
normally) are reported on the side: stopping them early also saves money.

Every tuned detector picks its thresholds on training folds only (repeated
stratified 5-fold CV) and is scored out-of-fold. The pre-registered decision
rule from the design doc is applied at the end.

Usage:  python benchmarks/analyze.py [--variant plain|fp|laya-<model>] [--sessions-from VARIANT]
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict

import numpy as np
from common import RESULTS, load_scored, restrict
from families import (
    POLICY_MODES,
    Family,
    code_family,
    hybrid_and_family,
    jev_family,
    max_turns_family,
    policy_message_counts,
    report_policy_alarms,
)
from features import INF, Flat, Metrics, build_flat, evaluate, first_alarm, persistent
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import StandardScaler

from unwedge.policy import Action

ALPHAS = (0.0, 0.01, 0.02, 0.05)
REPEATS, FOLDS = 5, 5
TOP_K = 25  # members of each family combined pairwise for the OR-hybrid


class Precomputed:
    """Per-family caught/saved matrices so that train-fold metrics are cheap."""

    def __init__(self, flat: Flat, family: Family) -> None:
        self.family = family
        effective = np.where(family.alarms < flat.n_turns, family.alarms, INF)
        self.caught = np.isfinite(effective)
        rows = flat.starts + np.where(self.caught, effective, 1).astype(int) - 1
        self.saved = np.where(self.caught, flat.cost_after[rows], 0.0).astype(np.float32)

    def train_metrics(self, flat: Flat, pos: np.ndarray, neg: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        fpr = self.caught[:, neg].mean(axis=1)
        catch = self.caught[:, pos].mean(axis=1)
        savings = self.saved[:, pos].sum(axis=1) / flat.total_cost[pos].sum()
        return fpr, catch, savings


def select(fpr: np.ndarray, catch: np.ndarray, savings: np.ndarray, alpha: float) -> int | None:
    allowed = fpr <= alpha + 1e-9
    if not allowed.any():
        return None
    score = np.where(allowed, savings + 1e-6 * catch, -np.inf)
    return int(np.argmax(score))


def top_members(fpr, catch, savings, alpha, k) -> np.ndarray:
    score = np.where(fpr <= alpha + 1e-9, savings + 1e-6 * catch, -np.inf)
    order = np.argsort(-score)[:k]
    return order[np.isfinite(score[order])]


def logistic_features(flat: Flat, with_jev: bool) -> np.ndarray:
    code = flat.code
    columns = [np.log1p(code[name]) for name in (
        "repeat_without_change", "result_repeats", "error_repeats", "read_only_streak",
        "turns_since_change", "consecutive_errors", "invalid_streak")]
    columns += [code["action_similarity"], code["result_similarity"], np.log(flat.turn)]
    if with_jev:
        jev = flat.jev
        usable = flat.scored & ~flat.blocked
        for name in ("s_repeat", "s_unchanged", "s_error", "p0", "terminal", "drift", "gate"):
            columns.append(np.where(usable, np.nan_to_num(jev[name]), 0.0))
        columns.append(np.where(usable, np.nan_to_num(jev["progress"]) / 3.0, 0.5))
        columns.append((~usable).astype(float))
    return np.column_stack(columns)


def logistic_alarms(flat: Flat, x: np.ndarray, train_sessions: np.ndarray, labels: np.ndarray):
    """Fit on the training sessions' turns; return candidate alarm matrices over thresholds."""
    rows = np.isin(flat.session_index, train_sessions)
    weights = 1.0 / flat.n_turns[flat.session_index[rows]]
    scaler = StandardScaler().fit(x[rows])
    model = LogisticRegression(max_iter=3000, class_weight="balanced")
    model.fit(scaler.transform(x[rows]), labels[flat.session_index[rows]], sample_weight=weights)
    risk = model.predict_proba(scaler.transform(x))[:, 1]
    thresholds = np.unique(np.quantile(risk[rows], np.linspace(0.5, 0.9995, 120)))
    alarms, params = [], []
    for k in (1, 2):
        for tau in thresholds:
            alarms.append(first_alarm(flat, persistent(flat, risk >= tau, k)))
            params.append({"tau": float(tau), "consecutive": k})
    return Family("logistic", tuple(params), np.stack(alarms).astype(np.float32))


def cross_validate(flat: Flat, families: dict[str, Precomputed], alpha: float, with_logistic: bool) -> dict:
    groups = flat.groups
    cv_sessions = np.flatnonzero(np.isin(groups, ("burn", "success")))
    labels_all = (groups == "burn").astype(int)
    wrong = groups == "wrong"
    names = [*families, "hybrid_or"] + (["logistic_code", "logistic_code_jev"] if with_logistic else [])
    per_repeat: dict[str, list[Metrics]] = {name: [] for name in names}
    wrong_rates: dict[str, list[float]] = {name: [] for name in names}
    oof_by_repeat: dict[str, list[np.ndarray]] = {name: [] for name in names}
    chosen: dict[str, list[dict]] = {name: [] for name in names}
    x_code = logistic_features(flat, with_jev=False) if with_logistic else None
    x_all = logistic_features(flat, with_jev=True) if with_logistic else None
    for repeat in range(REPEATS):
        oof = {name: np.full(len(groups), INF) for name in names}
        folds = StratifiedKFold(FOLDS, shuffle=True, random_state=repeat)
        for train_i, test_i in folds.split(cv_sessions, labels_all[cv_sessions]):
            train, test = cv_sessions[train_i], cv_sessions[test_i]
            pos = np.zeros(len(groups), bool)
            neg = np.zeros(len(groups), bool)
            pos[train], neg[train] = labels_all[train] == 1, labels_all[train] == 0
            picks = {}
            for name, pre in families.items():
                fpr, catch, savings = pre.train_metrics(flat, pos, neg)
                index = select(fpr, catch, savings, alpha)
                picks[name] = index
                _assign(oof[name], pre.family, index, test, wrong, wrong_rates[name], chosen[name])
            _hybrid_or(flat, families["code"], families["jev"], pos, neg, alpha, test, wrong, oof["hybrid_or"],
                       wrong_rates["hybrid_or"], chosen["hybrid_or"])
            if with_logistic:
                for name, x in (("logistic_code", x_code), ("logistic_code_jev", x_all)):
                    family = logistic_alarms(flat, x, train, labels_all)
                    pre = Precomputed(flat, family)
                    fpr, catch, savings = pre.train_metrics(flat, pos, neg)
                    _assign(oof[name], family, select(fpr, catch, savings, alpha), test, wrong, wrong_rates[name],
                            chosen[name])
        positives = np.zeros(len(groups), bool)
        negatives = np.zeros(len(groups), bool)
        positives[cv_sessions] = labels_all[cv_sessions] == 1
        negatives[cv_sessions] = labels_all[cv_sessions] == 0
        for name in names:
            per_repeat[name].append(evaluate(flat, oof[name], positives, negatives))
            oof_by_repeat[name].append(oof[name])
    summary = {name: _mean_metrics(per_repeat[name]) | {"wrong_alarm_rate": float(np.mean(wrong_rates[name]))}
               for name in names}
    return {"summary": summary, "oof": oof_by_repeat, "chosen": chosen}


def _assign(oof, family: Family, index, test, wrong, wrong_rates, chosen) -> None:
    if index is None:
        oof[test] = INF
        wrong_rates.append(0.0)
        chosen.append({"none": True})
        return
    oof[test] = family.alarms[index, test]
    wrong_rates.append(float(np.isfinite(family.alarms[index, wrong]).mean()) if wrong.any() else 0.0)
    chosen.append(family.params[index])


def _hybrid_or(flat, code: Precomputed, jev: Precomputed, pos, neg, alpha, test, wrong, oof, wrong_rates,
               chosen) -> None:
    code_fpr, code_catch, code_sav = code.train_metrics(flat, pos, neg)
    jev_fpr, jev_catch, jev_sav = jev.train_metrics(flat, pos, neg)
    code_top = top_members(code_fpr, code_catch, code_sav, alpha, TOP_K)
    jev_top = top_members(jev_fpr, jev_catch, jev_sav, alpha, TOP_K)
    if len(code_top) == 0:
        _assign(oof, code.family, None, test, wrong, wrong_rates, chosen)
        return
    pairs = [(c, j) for c in code_top for j in jev_top] or [(c, None) for c in code_top]
    alarms = np.stack([np.minimum(code.family.alarms[c], jev.family.alarms[j]) if j is not None
                       else code.family.alarms[c] for c, j in pairs])
    params = tuple({"code": code.family.params[c], "jev": jev.family.params[j] if j is not None else None}
                   for c, j in pairs)
    family = Family("hybrid_or", params, alarms)
    fpr, catch, savings = Precomputed(flat, family).train_metrics(flat, pos, neg)
    _assign(oof, family, select(fpr, catch, savings, alpha), test, wrong, wrong_rates, chosen)


def _mean_metrics(items: list[Metrics]) -> dict:
    keys = asdict(items[0]).keys()
    return {key: float(np.nanmean([asdict(m)[key] for m in items])) for key in keys} | {
        f"{key}_sd": float(np.nanstd([asdict(m)[key] for m in items])) for key in ("catch", "false_alarm", "savings")}


def earlier_by(flat: Flat, oof_a: list[np.ndarray], oof_b: list[np.ndarray]) -> float:
    """Median turns by which detector b alarms before detector a, on burn sessions both catch."""
    burn = flat.groups == "burn"
    diffs = []
    for a, b in zip(oof_a, oof_b, strict=False):
        a_eff = np.where(a < flat.n_turns, a, INF)
        b_eff = np.where(b < flat.n_turns, b, INF)
        both = burn & np.isfinite(a_eff) & np.isfinite(b_eff)
        if both.any():
            diffs.append(float(np.median(a_eff[both] - b_eff[both])))
    return float(np.mean(diffs)) if diffs else float("nan")


def decision_rule(code: dict, hybrid: dict, earlier: float) -> dict:
    """The design doc's pre-registered rule, written before any data was seen.
    Continue: the hybrid catches >= 15 points more doomed sessions, or alarms >= 3 turns
    earlier, with <= 1% false alarms on successful sessions.
    Pivot: code alone catches >= 85% of doomed sessions at the same early point."""
    gain = hybrid["catch"] - code["catch"]
    return {
        "catch_gain_points": round(100 * gain, 1),
        "earlier_turns": round(earlier, 2),
        "hybrid_false_alarm": round(hybrid["false_alarm"], 3),
        "continue": bool((gain >= 0.15 or earlier >= 3) and hybrid["false_alarm"] <= 0.01),
        "pivot": bool(code["catch"] >= 0.85 and earlier < 3),
    }


def policy_earlier(flat: Flat, base: np.ndarray, other: np.ndarray) -> float:
    return earlier_by(flat, [base], [other])


def write_markdown(report: dict, path) -> None:
    lines = [f"# Kill test — variant `{report['variant']}`", "", f"Sessions: {report['sessions']}", "",
             "## Design-doc policy replayed, untuned (all sessions)", "",
             "| mode | caught | false alarms | recovered spend | alarm position | wrong-group alarms |",
             "|---|---|---|---|---|---|"]
    for mode, m in report["report_policy"].items():
        lines.append(f"| {mode} | {m['catch']:.0%} | {m['false_alarm_count']} ({m['false_alarm']:.1%}) | "
                     f"{m['savings']:.0%} | {m['position']:.2f} | {m['wrong_alarm_rate']:.0%} |")
    lines += ["", "Every message the agent would receive in hint mode (hints, escalations, the one-time "
              "\"verify and finish\" and \"back to the goal\" notes; a gate veto is only logged):", "",
              "| mode | successful sessions with any message | messages per success | per burn | per wrong |",
              "|---|---|---|---|---|"]
    for mode, m in report["report_policy"].items():
        msg = m["messages"]
        per = {g: f"{msg[g]['per_session']:.2f}" if g in msg else "n/a" for g in ("success", "burn", "wrong")}
        lines.append(f"| {mode} | {msg['success']['sessions_with_any']:.1%} | {per['success']} | "
                     f"{per['burn']} | {per['wrong']} |")
    lines += ["", "Decision rule on the untuned policies:", ""]
    for name, rule in report["decision_untuned"].items():
        lines.append(f"- {name}: {rule}")
    for alpha, entry in report["alphas"].items():
        lines += ["", f"## Tuned by CV, false-alarm cap on training folds = {float(alpha):.0%}", "",
                  "| detector | caught | false alarms (held out) | recovered spend | alarm position | turns saved |",
                  "|---|---|---|---|---|---|"]
        for name, m in entry["summary"].items():
            lines.append(f"| {name} | {m['catch']:.0%} ± {m['catch_sd']:.0%} | {m['false_alarm']:.1%} ± "
                         f"{m['false_alarm_sd']:.1%} | {m['savings']:.0%} | {m['position']:.2f} | "
                         f"{m['turns_saved']:.1f} |")
        for name, rule in entry.get("decision", {}).items():
            lines.append(f"\n- decision rule, {name}: {rule}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", default="plain",
                        help="scores in results/battery_<variant>.jsonl: plain, fp, laya-english, ...")
    parser.add_argument("--sessions-from", metavar="VARIANT",
                        help="only the sessions another battery scored, for a paired comparison")
    parser.add_argument("--no-logistic", action="store_true")
    args = parser.parse_args()
    sessions, battery = load_scored(args.variant)
    name = args.variant
    if args.sessions_from:
        sessions, battery = restrict(sessions, battery, args.sessions_from)
        name = f"{args.variant}_on_{args.sessions_from}"
    flat = build_flat(sessions, battery)
    families = {f.name: Precomputed(flat, f) for f in (max_turns_family(flat), code_family(flat), jev_family(flat),
                                                        hybrid_and_family(flat))}
    report: dict = {"variant": name, "sessions": {g: int((flat.groups == g).sum()) for g in
                                                          ("success", "burn", "wrong")}}
    positives, negatives = flat.groups == "burn", flat.groups == "success"
    interventions = frozenset({Action.HINT, Action.ESCALATE, Action.KILL})
    report["report_policy"], policy_alarms = {}, {}
    for mode in POLICY_MODES:
        alarm = report_policy_alarms(flat, sessions, interventions, mode)
        policy_alarms[mode] = alarm
        report["report_policy"][mode] = asdict(evaluate(flat, alarm, positives, negatives)) | {
            "wrong_alarm_rate": float(np.isfinite(alarm[flat.groups == "wrong"]).mean()),
            "false_alarm_count": int(np.sum(np.isfinite(np.where(alarm < flat.n_turns, alarm, INF))[negatives]))}
        messages = policy_message_counts(flat, mode)
        report["report_policy"][mode]["messages"] = {
            group: {"sessions_with_any": float((messages[flat.groups == group] > 0).mean()),
                    "per_session": float(messages[flat.groups == group].mean())}
            for group in ("success", "burn", "wrong") if (flat.groups == group).any()}
        rounded = {k: round(v, 3) for k, v in report["report_policy"][mode].items() if not isinstance(v, dict)}
        print(f"report policy [{mode}]: {json.dumps(rounded)}")
    code_policy = report["report_policy"]["code_tier_only"]
    report["decision_untuned"] = {
        mode: decision_rule(code_policy, report["report_policy"][mode],
                            policy_earlier(flat, policy_alarms["code_tier_only"], policy_alarms[mode]))
        for mode in ("full", "jev_brake")
    }
    report["alphas"] = {}
    for alpha in ALPHAS:
        result = cross_validate(flat, families, alpha, with_logistic=not args.no_logistic)
        entry = {"summary": result["summary"], "decision": {}}
        for hybrid in ("hybrid_or", "hybrid_and", "logistic_code_jev"):
            if hybrid in result["oof"]:
                baseline = "code" if hybrid != "logistic_code_jev" else "logistic_code"
                earlier = earlier_by(flat, result["oof"][baseline], result["oof"][hybrid])
                entry[f"earlier_{hybrid}_vs_{baseline}"] = earlier
                entry["decision"][f"{hybrid} vs {baseline}"] = decision_rule(
                    result["summary"][baseline], result["summary"][hybrid], earlier)
        entry["chosen_examples"] = {name: picks[:3] for name, picks in result["chosen"].items()}
        report["alphas"][str(alpha)] = entry
        print(f"alpha={alpha}: " + ", ".join(
            f"{name} catch={m['catch']:.2f} fa={m['false_alarm']:.3f} save={m['savings']:.2f}"
            for name, m in result["summary"].items()), flush=True)
    out = RESULTS / f"analysis_{name}.json"
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    write_markdown(report, RESULTS / f"analysis_{name}.md")
    print(f"wrote {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
