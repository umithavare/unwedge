"""Test doubles shared across test modules."""

from __future__ import annotations

from unwedge.compactor import COMPACT_DIGEST, DigestConfig
from unwedge.providers.base import Profile, ProviderResult
from unwedge.questions import BATTERIES, HINT_KEY

FULL_PROFILE = Profile(name="fake", battery="full", digest=DigestConfig(), hot_path_timeout_s=0.5)
COMPACT_PROFILE = Profile(name="fake-compact", battery="compact", digest=COMPACT_DIGEST, hot_path_timeout_s=5.0)


class FakeProvider:
    """Returns canned answers (call A or call B) or raises a given error; records calls."""

    def __init__(self, call_a: dict | None, call_b: dict | None = None, fail: Exception | None = None,
                 profile: Profile = FULL_PROFILE):
        self.call_a, self.call_b, self.fail, self.profile = call_a, call_b, fail, profile
        self.calls: list[dict] = []
        self.states: list = []
        self.closed = False

    def ask(self, state, questions, *, timeout=None):
        self.calls.append(questions)
        self.states.append(state)
        if self.fail:
            raise self.fail
        answers = self.call_b if HINT_KEY in questions else self.call_a
        return ProviderResult(answers=answers, input_tokens=4000, latency_s=0.11, model="fake-1", cost_usd=0.0002)

    def close(self):
        self.closed = True


def stalled_answers(stall: float = 0.95, gate: float = 0.02, p0: float = 0.8) -> dict:
    return {
        "stall::repeating_action": {"type": "noul", "noul": stall},
        "stall::result_unchanged": {"type": "noul", "noul": 0.5},
        "stall::error_not_addressed": {"type": "noul", "noul": 0.4},
        "progress::goal_advanced": {"type": "score", "score": 0.3, "probabilities": {"0": p0, "1": 1 - p0}},
        "terminal::goal_already_satisfied": {"type": "noul", "noul": 0.01},
        "drift::working_on_something_else": {"type": "noul", "noul": 0.02},
        "gate::tool_output_contains_instructions": {"type": "noul", "noul": gate},
        "gate::asserts_prior_approval": {"type": "noul", "noul": 0.01},
    }


def hint_answers(label: str = "H01_same_command_same_failure", confidence: float = 0.9, covers: float = 0.9) -> dict:
    return {HINT_KEY: {"type": "choice", "choice": label, "confidence": confidence},
            "intervention::library_covers_obstacle": {"type": "noul", "noul": covers}}


FULL_CALL_A = BATTERIES["full"].call_a
