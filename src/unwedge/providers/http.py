"""A tiny keep-alive HTTP transport built on the standard library.

unwedge runs inside hook processes and agent loops, so the core has no third-party
dependencies. A warm connection matters for hosted providers: most of a cold call's
latency is TCP and TLS setup, so connections are kept per thread and per host.
"""

from __future__ import annotations

import http.client
import ssl
import threading
import time
import urllib.parse
from collections.abc import Callable, Mapping

from unwedge.providers.base import ProviderRateLimited, ProviderTimeout, ProviderUnavailable

# (url, body, headers, timeout) -> (status, response body)
Transport = Callable[[str, bytes, Mapping[str, str], float], tuple[int, bytes]]

# A pooled connection the server has already closed (idle keep-alive timeout) fails with one of
# these; on Windows it is usually ConnectionAbortedError (WinError 10053). Retried once, fresh.
_RETRYABLE_ON_REUSE = (http.client.RemoteDisconnected, http.client.CannotSendRequest, ConnectionError)


class KeepAliveTransport:
    """POSTs over reused connections. One connection per (thread, scheme, host, port)."""

    def __init__(self, ssl_context: ssl.SSLContext | None = None) -> None:
        self._local = threading.local()
        self._ssl = ssl_context or ssl.create_default_context()

    def __call__(self, url: str, body: bytes, headers: Mapping[str, str], timeout: float) -> tuple[int, bytes]:
        parts = urllib.parse.urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise ProviderUnavailable(f"unsupported URL: {url}")
        path = parts.path or "/"
        if parts.query:
            path += "?" + parts.query
        key = (parts.scheme, parts.hostname, parts.port)
        for attempt in (1, 2):
            conn, reused = self._connection(key, timeout)
            try:
                conn.request("POST", path, body=body, headers=dict(headers))
                response = conn.getresponse()
                return response.status, response.read()
            except TimeoutError as exc:
                self._drop(key)
                raise ProviderTimeout(f"no answer within {timeout:.2f}s") from exc
            except _RETRYABLE_ON_REUSE as exc:
                self._drop(key)
                if reused and attempt == 1:
                    continue  # a pooled connection the server had already closed: retry once, fresh
                raise ProviderUnavailable(f"{type(exc).__name__}: {exc}") from exc
            except (OSError, http.client.HTTPException) as exc:
                self._drop(key)
                raise ProviderUnavailable(f"{type(exc).__name__}: {exc}") from exc
        raise ProviderUnavailable("connection failed")  # pragma: no cover

    def close(self) -> None:
        for conn in getattr(self._local, "pool", {}).values():
            conn.close()
        self._local.pool = {}

    def _connection(self, key, timeout: float) -> tuple[http.client.HTTPConnection, bool]:
        pool = getattr(self._local, "pool", None)
        if pool is None:
            pool = self._local.pool = {}
        conn = pool.get(key)
        if conn is not None:
            try:
                conn.timeout = timeout
                if conn.sock is not None:
                    conn.sock.settimeout(timeout)
                return conn, True
            except OSError:  # the pooled socket is already dead: start over
                self._drop(key)
        scheme, host, port = key
        if scheme == "https":
            conn = http.client.HTTPSConnection(host, port, timeout=timeout, context=self._ssl)
        else:
            conn = http.client.HTTPConnection(host, port, timeout=timeout)
        pool[key] = conn
        return conn, False

    def _drop(self, key) -> None:
        conn = getattr(self._local, "pool", {}).pop(key, None)
        if conn is not None:
            conn.close()


class TokenBucket:
    """Thread-safe token bucket. Hosted providers may send no rate-limit headers, so the
    client limits itself. `acquire(0)` never waits."""

    def __init__(self, rate_per_sec: float, burst: int) -> None:
        if rate_per_sec <= 0 or burst < 1:
            raise ValueError("rate_per_sec must be > 0 and burst >= 1")
        self._rate, self._capacity = rate_per_sec, float(burst)
        self._tokens, self._stamp = float(burst), time.monotonic()
        self._lock = threading.Lock()

    def acquire(self, timeout: float | None = None) -> bool:
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            with self._lock:
                now = time.monotonic()
                self._tokens = min(self._capacity, self._tokens + (now - self._stamp) * self._rate)
                self._stamp = now
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return True
                wait = (1.0 - self._tokens) / self._rate
            if deadline is not None and time.monotonic() + wait > deadline:
                return False
            time.sleep(wait)


def require_slot(bucket: TokenBucket, wait: float | None) -> None:
    if not bucket.acquire(wait):
        raise ProviderRateLimited("local rate limiter: no request slot available")
