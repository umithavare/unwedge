"""The in-loop guard. A harness calls `on_turn` after each tool result and before its
next model call; the call blocks for at most the provider's hot-path timeout and fails
open (the turn proceeds on the code-only tier) on any provider problem.

    guard = Guard(goal=task_text, provider=make_provider("jev"))
    for each turn:
        outcome = guard.on_turn(turn)
        if outcome.enforced and outcome.hint_text:
            append outcome.hint_text to the agent's next message
        if outcome.enforced and outcome.decision.action is Action.KILL:
            stop the session

Shadow mode (the default) computes and logs everything but never enforces.
Short-lived processes (hooks) rebuild a guard from history with `replay`, which
feeds earlier turns and their stored verdicts through the policy without new calls.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

from unwedge.answers import choice, noul
from unwedge.code_signals import CodeSignals, SignalTracker
from unwedge.compactor import DigestConfig, build_state
from unwedge.policy import Action, Decision, PolicyState, Thresholds, Verdict, step
from unwedge.providers.base import Provider, ProviderError
from unwedge.questions import BATTERIES, COVERS_KEY, HINT_KEY, render_hint
from unwedge.scrub import scrub
from unwedge.turns import Turn

HINT_ACTIONS = {Action.HINT, Action.VERIFY_HINT, Action.RETURN_HINT}
_FIXED_HINTS = {Action.VERIFY_HINT: "H10_verify_before_finishing", Action.RETURN_HINT: "H09_return_to_goal"}
_PARSE_ERRORS = (KeyError, TypeError, ValueError)


@dataclass(frozen=True)
class GuardConfig:
    digest: DigestConfig = field(default_factory=DigestConfig)
    battery: str = "full"
    thresholds: Thresholds = field(default_factory=Thresholds)
    timeout_s: float = 0.5  # hot-path budget per call; beyond it the turn proceeds unguarded
    periodic_after: int = 6  # drift and "already done" have no code signature, so sample them
    periodic_every: int = 3
    hint_min_confidence: float = 0.50
    library_covers_min: float = 0.60
    shadow: bool = True
    kill_enabled: bool = False

    @classmethod
    def for_provider(cls, provider: Provider | None, **overrides) -> GuardConfig:
        """Digest layout, battery and timeout that fit the provider's context window."""
        if provider is None:
            return cls(**overrides)
        profile = provider.profile
        base = cls(digest=profile.digest, battery=profile.battery, timeout_s=profile.hot_path_timeout_s)
        return replace(base, **overrides)


@dataclass(frozen=True)
class GuardOutcome:
    turn: int
    decision: Decision
    gated: bool
    enforced: bool
    code: CodeSignals
    verdict: Verdict | None = None
    hint_id: str | None = None
    hint_text: str | None = None
    degraded: str | None = None  # why the provider was not used on a gated turn
    latency_ms: float | None = None
    cost_usd: float = 0.0

    def to_record(self) -> dict:
        record = asdict(self)
        record["decision"] = {"action": self.decision.action.value, "reasons": list(self.decision.reasons)}
        return record


def code_hint(code: CodeSignals) -> str:
    """Deterministic hint choice for when no provider can pick one."""
    if code.repeat_without_change >= 1 or code.pair_repeats >= 1 or code.cycle_repeats >= 2:
        return "H01_same_command_same_failure"
    if code.read_only_streak >= 4:
        return "H02_rereading_same_content"
    if code.error_repeats >= 1:
        return "H03_error_text_ignored"
    return "H12_replan_from_summary"


def is_gated(code: CodeSignals, config: GuardConfig) -> bool:
    """Code decides when a judgment is worth paying for."""
    suspicious = (
        code.repeat_without_change >= 1
        or code.result_repeats >= 1
        or code.error_repeats >= 1
        or code.consecutive_errors >= 2
        or code.read_only_streak >= 4
        or code.invalid_streak >= 1
    )
    periodic = code.turn >= config.periodic_after and code.turn % config.periodic_every == 0
    return suspicious or periodic


class Guard:
    def __init__(self, goal: str, provider: Provider | None, config: GuardConfig | None = None,
                 ledger: Path | None = None) -> None:
        self._goal = goal
        self._provider = provider
        self._config = config or GuardConfig.for_provider(provider)
        self._battery = BATTERIES[self._config.battery]
        self._ledger = ledger
        self._turns: tuple[Turn, ...] = ()
        self._signals = SignalTracker(self._config.digest.window)
        self._policy = PolicyState()

    @property
    def config(self) -> GuardConfig:
        return self._config

    @property
    def policy_state(self) -> PolicyState:
        return self._policy

    def set_goal(self, goal: str) -> None:
        """The user changed or extended the task mid-session."""
        self._goal = goal

    def replay(self, turn: Turn, verdict: Verdict | None) -> Decision:
        """Feed a past turn and its stored verdict through the policy, without provider calls."""
        self._turns = (*self._turns, turn)
        code = self._signals.add(turn)
        self._policy, decision = step(self._policy, verdict, code, self._config.thresholds,
                                      kill_enabled=self._config.kill_enabled)
        return decision

    def on_turn(self, turn: Turn) -> GuardOutcome:
        self._turns = (*self._turns, turn)
        code = self._signals.add(turn)
        gated = is_gated(code, self._config)
        verdict, degraded, latency, cost = None, None, None, 0.0
        if gated and self._provider is None:
            degraded = "no provider (code-only tier)"
        elif gated:
            verdict, degraded, latency, cost = self._judge()
        self._policy, decision = step(self._policy, verdict, code, self._config.thresholds,
                                      kill_enabled=self._config.kill_enabled)
        hint_id, hint_text, extra_cost = None, None, 0.0
        if decision.action in HINT_ACTIONS:
            # a second hot-path round trip only when the first one just worked
            provider_usable = self._provider is not None and (not gated or degraded is None)
            hint_id, hint_text, extra_cost = self._choose_hint(decision, code, provider_usable)
        outcome = GuardOutcome(
            turn=turn.index, decision=decision, gated=gated, enforced=not self._config.shadow,
            code=code, verdict=verdict, hint_id=hint_id, hint_text=hint_text,
            degraded=degraded, latency_ms=latency, cost_usd=cost + extra_cost,
        )
        self._write_ledger(outcome)
        return outcome

    def _state(self) -> dict:
        return build_state(self._goal, self._turns, self._config.digest)

    def _judge(self) -> tuple[Verdict | None, str | None, float | None, float]:
        """Call A. Every failure, including an HTTP 200 with a malformed body, fails open."""
        started = time.perf_counter()
        try:
            result = self._provider.ask(self._state(), self._battery.call_a, timeout=self._config.timeout_s)
        except ProviderError as exc:  # the message can echo a response body: scrub it before it is logged
            degraded = scrub(f"{type(exc).__name__}: {exc}")[:200]
            return None, degraded, (time.perf_counter() - started) * 1000, 0.0
        try:
            verdict = Verdict.from_answers(result.answers)
        except _PARSE_ERRORS as exc:
            return None, f"malformed answers: {exc!r}"[:200], result.latency_s * 1000, result.cost_usd
        return verdict, None, result.latency_s * 1000, result.cost_usd

    def _choose_hint(self, decision: Decision, code: CodeSignals,
                     provider_usable: bool) -> tuple[str | None, str | None, float]:
        numbers = {"repeats": code.exact_repeats + 1, "turns": code.turn}
        fixed = _FIXED_HINTS.get(decision.action)
        if fixed:
            return fixed, render_hint(fixed, **numbers), 0.0
        fallback = code_hint(code)
        if not provider_usable:
            return fallback, render_hint(fallback, **numbers), 0.0
        try:
            result = self._provider.ask(self._state(), self._battery.call_b, timeout=self._config.timeout_s)
        except ProviderError:  # fail open to a hint picked by code
            return fallback, render_hint(fallback, **numbers), 0.0
        try:
            label, confidence = choice(result.answers, HINT_KEY)
            covered = noul(result.answers, COVERS_KEY)
        except _PARSE_ERRORS:
            return fallback, render_hint(fallback, **numbers), result.cost_usd
        hint_id = self._battery.hint_id(label)
        # the policy decides how strong the intervention is (hint, hint, then escalate); the model
        # only picks which hint. When none fits confidently, the hint code picked is used instead
        unsure = confidence < self._config.hint_min_confidence or covered < self._config.library_covers_min
        if hint_id is None or hint_id == "H16_stop_and_escalate" or unsure:
            return fallback, render_hint(fallback, **numbers), result.cost_usd
        return hint_id, render_hint(hint_id, **numbers) or None, result.cost_usd

    def _write_ledger(self, outcome: GuardOutcome) -> None:
        if self._ledger is None:
            return
        with self._ledger.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(outcome.to_record(), ensure_ascii=False) + "\n")
