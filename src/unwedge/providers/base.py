"""The provider contract. A provider answers typed questions (noul / choice / score)
about a state; everything else in unwedge is provider-agnostic."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from unwedge.compactor import DigestConfig


class ProviderError(Exception):
    """Any failure to get answers. The guard fails open on every subclass."""


class ProviderTimeout(ProviderError):
    pass


class ProviderRateLimited(ProviderError):
    pass


class ProviderUnavailable(ProviderError):
    pass


class ProviderRejected(ProviderError):
    pass


class ProviderBlocked(ProviderRejected):
    """HTTP 403 from an edge firewall: agent transcripts (shell commands, code) can look
    like attacks to a WAF, and the request never reaches the model."""


class ProviderMalformed(ProviderError):
    """The provider answered, but not with a usable answer set."""


@dataclass(frozen=True)
class Profile:
    """What a provider needs from the rest of the system."""

    name: str
    battery: str  # "full" (large context, e.g. jev) or "compact" (512-1,024 token models, e.g. Laya)
    digest: DigestConfig
    usd_per_input_token: float = 0.0
    hot_path_timeout_s: float = 0.5


@dataclass(frozen=True)
class ProviderResult:
    answers: Mapping[str, Mapping]
    input_tokens: int
    latency_s: float
    model: str
    cost_usd: float = 0.0


@runtime_checkable
class Provider(Protocol):
    profile: Profile

    def ask(self, state: Any, questions: Mapping[str, Mapping], *, timeout: float | None = None) -> ProviderResult:
        """One attempt. Raises a ProviderError subclass on any failure."""
        ...

    def close(self) -> None:
        ...


def validate_answers(payload: Any, questions: Mapping[str, Mapping]) -> Mapping[str, Mapping]:
    """Return the answers mapping, or raise ProviderMalformed if any asked question is missing."""
    answers = payload.get("answers") if isinstance(payload, Mapping) else None
    if not isinstance(answers, Mapping):
        raise ProviderMalformed("response has no 'answers' object")
    missing = [key for key in questions if not isinstance(answers.get(key), Mapping)]
    if missing:
        raise ProviderMalformed(f"answers missing for: {', '.join(sorted(missing)[:5])}")
    return answers
