"""Client for any endpoint that speaks the System One wire protocol:
`POST <url>` with `{model, state, questions}` -> `{model, answers, usage}`.

That covers TypeSafe's hosted jev API, Laya's self-hosted `laya-serve`, and
`unwedge serve`. Only the URL, model name, key and profile differ.
"""

from __future__ import annotations

import json
import time
from collections.abc import Mapping
from typing import Any

from unwedge.providers.base import (
    Profile,
    ProviderBlocked,
    ProviderMalformed,
    ProviderRateLimited,
    ProviderRejected,
    ProviderResult,
    ProviderTimeout,
    ProviderUnavailable,
    validate_answers,
)
from unwedge.providers.http import KeepAliveTransport, TokenBucket, Transport, require_slot

USER_AGENT = "unwedge (+https://github.com/umithavare/unwedge)"


class SystemOneHTTP:
    def __init__(
        self,
        *,
        url: str,
        model: str,
        profile: Profile,
        api_key: str | None = None,
        rate_per_sec: float = 16.0,
        burst: int = 4,
        transport: Transport | None = None,
    ) -> None:
        self.url = url
        self.model = model
        self.profile = profile
        self._api_key = api_key
        self._transport = transport or KeepAliveTransport()
        self.bucket = TokenBucket(rate_per_sec, burst)

    def __repr__(self) -> str:  # never print the key
        return f"SystemOneHTTP(url={self.url!r}, model={self.model!r}, profile={self.profile.name!r})"

    def close(self) -> None:
        close = getattr(self._transport, "close", None)
        if callable(close):
            close()

    def __enter__(self) -> SystemOneHTTP:
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def ask(self, state: Any, questions: Mapping[str, Mapping], *, timeout: float | None = None,
            wait_for_slot: float | None = 0.0) -> ProviderResult:
        require_slot(self.bucket, wait_for_slot)
        timeout = self.profile.hot_path_timeout_s if timeout is None else timeout
        body = json.dumps({"model": self.model, "state": state, "questions": questions}).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "application/json", "User-Agent": USER_AGENT}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        started = time.perf_counter()
        status, raw = self._transport(self.url, body, headers, timeout)
        latency = time.perf_counter() - started
        if status == 429:
            raise ProviderRateLimited("HTTP 429")
        if status >= 500:
            raise ProviderUnavailable(f"HTTP {status}")
        if status == 403:
            raise ProviderBlocked("HTTP 403 (edge firewall or forbidden)")
        if status != 200:
            raise ProviderRejected(f"HTTP {status}: {raw[:200].decode('utf-8', 'replace')}")
        try:
            payload = json.loads(raw)
        except ValueError as exc:
            raise ProviderMalformed("response is not JSON") from exc
        answers = validate_answers(payload, questions)
        usage = payload.get("usage") if isinstance(payload.get("usage"), Mapping) else {}
        tokens = int(usage.get("input_tokens") or 0)
        return ProviderResult(
            answers=answers,
            input_tokens=tokens,
            latency_s=latency,
            model=str(payload.get("model") or self.model),
            cost_usd=tokens * self.profile.usd_per_input_token,
        )

    def ask_with_retries(self, state: Any, questions: Mapping[str, Mapping], *, timeout: float = 15.0,
                         attempts: int = 6) -> ProviderResult:
        """Offline batch use only: back off on 429, 5xx and timeouts. Never on the hot path."""
        for attempt in range(attempts):
            try:
                return self.ask(state, questions, timeout=timeout, wait_for_slot=None)
            except (ProviderRateLimited, ProviderUnavailable, ProviderTimeout):
                if attempt == attempts - 1:
                    raise
                time.sleep(min(30.0, 1.5 * 2**attempt))
        raise ProviderUnavailable("unreachable")  # pragma: no cover
