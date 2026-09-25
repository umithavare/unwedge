from __future__ import annotations

import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fakes import COMPACT_PROFILE, FULL_PROFILE, FakeProvider, stalled_answers

from unwedge.answers import choice, score_mass
from unwedge.providers import (
    JEV_MODEL,
    LAYA_URL,
    ProviderBlocked,
    ProviderMalformed,
    ProviderRateLimited,
    ProviderRejected,
    ProviderTimeout,
    ProviderUnavailable,
    SystemOneHTTP,
    make_provider,
)
from unwedge.providers.base import validate_answers
from unwedge.providers.http import KeepAliveTransport, TokenBucket
from unwedge.providers.laya_local import LayaInProcess, pick_backend
from unwedge.server import make_handler

QUESTIONS = {"q": {"type": "noul", "instructions": "x"}}
OK_BODY = {"model": "jev-1.13.0", "answers": {"q": {"type": "noul", "noul": 0.9}}, "usage": {"input_tokens": 1000}}


def fake_transport(status: int = 200, body: object = OK_BODY, seen: dict | None = None, error: Exception | None = None):
    def transport(url, data, headers, timeout):
        if seen is not None:
            seen.update(url=url, body=json.loads(data), headers=dict(headers), timeout=timeout)
        if error:
            raise error
        return status, json.dumps(body).encode() if not isinstance(body, bytes) else body
    return transport


def client(transport) -> SystemOneHTTP:
    return SystemOneHTTP(url="https://example.test/v1/systemone", model="m", profile=FULL_PROFILE,
                         api_key="secret-key", transport=transport, rate_per_sec=1000, burst=10)


def test_ask_sends_the_protocol_and_parses_answers():
    seen: dict = {}
    result = client(fake_transport(seen=seen)).ask({"s": 1}, QUESTIONS)
    assert result.answers["q"]["noul"] == 0.9 and result.model == "jev-1.13.0" and result.input_tokens == 1000
    assert seen["body"] == {"model": "m", "state": {"s": 1}, "questions": QUESTIONS}
    assert seen["headers"]["Authorization"] == "Bearer secret-key" and seen["timeout"] == 0.5
    assert "secret-key" not in repr(client(fake_transport()))


@pytest.mark.parametrize(
    ("status", "error"),
    [(429, ProviderRateLimited), (503, ProviderUnavailable), (422, ProviderRejected), (403, ProviderBlocked)],
)
def test_http_errors_are_typed(status, error):
    with pytest.raises(error):
        client(fake_transport(status=status, body={"detail": "no"})).ask({}, QUESTIONS)


def test_malformed_bodies_are_rejected():
    with pytest.raises(ProviderMalformed):
        client(fake_transport(body=b"not json")).ask({}, QUESTIONS)
    with pytest.raises(ProviderMalformed):
        client(fake_transport(body={"answers": {}})).ask({}, QUESTIONS)
    with pytest.raises(ProviderMalformed):
        validate_answers([], QUESTIONS)


def test_retries_then_succeeds(monkeypatch):
    monkeypatch.setattr("unwedge.providers.systemone_http.time.sleep", lambda s: None)
    calls = {"n": 0}

    def flaky(url, data, headers, timeout):
        calls["n"] += 1
        return (429, b"{}") if calls["n"] < 3 else (200, json.dumps(OK_BODY).encode())

    assert client(flaky).ask_with_retries({}, QUESTIONS).answers["q"]["noul"] == 0.9
    assert calls["n"] == 3


def test_token_bucket():
    bucket = TokenBucket(rate_per_sec=0.001, burst=1)
    assert bucket.acquire(0) is True and bucket.acquire(0) is False
    with pytest.raises(ValueError):
        TokenBucket(0, 1)
    empty = SystemOneHTTP(url="http://x", model="m", profile=FULL_PROFILE, transport=fake_transport(),
                          rate_per_sec=0.001, burst=1)
    empty.ask({}, QUESTIONS)
    with pytest.raises(ProviderRateLimited):
        empty.ask({}, QUESTIONS)


def test_make_provider_presets(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.delenv("LAYA_URL", raising=False)
    monkeypatch.delenv("LAYA_MODEL", raising=False)
    assert make_provider("none") is None
    with pytest.raises(ValueError):
        make_provider("jev")
    jev = make_provider("jev", api_key="k")
    assert jev.model == JEV_MODEL and jev.profile.battery == "full"
    laya = make_provider("laya")
    assert laya.url == LAYA_URL and laya.model == "english" and laya.profile.digest.max_state_chars == 1100
    monkeypatch.setenv("LAYA_MODEL", "multilingual")
    multi = make_provider("laya")
    assert multi.model == "multilingual" and multi.profile.digest.max_state_chars == 2200
    with pytest.raises(ValueError):
        make_provider("gpt")


def test_answer_readers():
    answers = {"s": {"probabilities": {"2": 0.35, "3": 0.65}}, "c": {"choice": "H01", "confidence": 0.8}}
    assert score_mass(answers, "s", 0) == 0.0 and score_mass(answers, "s", 3) == 0.65
    assert choice(answers, "c") == ("H01", 0.8)


class _Agent:
    def __init__(self, fail: Exception | None = None):
        self.fail, self.seen = fail, []

    def predict(self, state, questions):
        self.seen.append((state, questions))
        if self.fail:
            raise self.fail
        return {"model": "laya-rl-agent", "answers": {k: {"type": "noul", "noul": 0.7} for k in questions},
                "usage": {"input_tokens": 321, "output_tokens": 0}}


def test_laya_in_process_with_a_fake_loader():
    agent = _Agent()
    provider = LayaInProcess(profile=COMPACT_PROFILE, checkpoint="multilingual", loader=lambda b, c, d: agent)
    result = provider.ask({"goal": "x"}, QUESTIONS)
    assert result.answers["q"]["noul"] == 0.7 and result.input_tokens == 321 and result.cost_usd == 0.0
    assert provider.model == "laya-multilingual-torch"
    failing = LayaInProcess(profile=COMPACT_PROFILE, loader=lambda b, c, d: _Agent(fail=ValueError("budget")))
    with pytest.raises(ProviderUnavailable):
        failing.ask({}, QUESTIONS)
    provider.close()
    with pytest.raises(ProviderUnavailable):
        provider.ask({}, QUESTIONS)
    with pytest.raises(ValueError):
        LayaInProcess(profile=COMPACT_PROFILE, checkpoint="nope", loader=lambda b, c, d: agent)
    with pytest.raises(ValueError):
        pick_backend("cuda")


# ---- real sockets: keep-alive transport and `unwedge serve` ---------------------------------------

class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    delay = 0.0

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        time.sleep(type(self).delay)
        data = json.dumps(OK_BODY).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        return


@pytest.fixture
def local_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()


def test_keep_alive_transport_reuses_and_recovers(local_server):
    url = f"http://127.0.0.1:{local_server.server_address[1]}/v1/systemone"
    provider = SystemOneHTTP(url=url, model="m", profile=FULL_PROFILE, rate_per_sec=1000, burst=10)
    assert provider.ask({}, QUESTIONS, timeout=5).answers["q"]["noul"] == 0.9
    assert provider.ask({}, QUESTIONS, timeout=5).answers["q"]["noul"] == 0.9  # pooled connection
    pool = provider._transport._local.pool
    next(iter(pool.values())).sock.close()  # the server side went away while idle
    assert provider.ask({}, QUESTIONS, timeout=5).answers["q"]["noul"] == 0.9
    provider.close()


def test_keep_alive_transport_times_out(local_server):
    _Handler.delay = 0.5
    try:
        url = f"http://127.0.0.1:{local_server.server_address[1]}/v1/systemone"
        with pytest.raises(ProviderTimeout):
            KeepAliveTransport()(url, b"{}", {"Content-Type": "application/json"}, 0.1)
    finally:
        _Handler.delay = 0.0
    with pytest.raises(ProviderUnavailable):
        KeepAliveTransport()("ftp://nope", b"{}", {}, 0.1)
    with pytest.raises((ProviderUnavailable, ProviderTimeout)):  # Windows may time out instead of refusing
        KeepAliveTransport()("http://127.0.0.1:1/v1/systemone", b"{}", {}, 0.5)


@pytest.fixture
def unwedge_server():
    provider = FakeProvider(stalled_answers())
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(provider, api_key="k3y"))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def test_unwedge_serve_speaks_the_protocol(unwedge_server):
    questions = {"stall::repeating_action": {"type": "noul", "instructions": "x"}}
    remote = SystemOneHTTP(url=f"{unwedge_server}/v1/systemone", model="any", profile=FULL_PROFILE, api_key="k3y",
                           rate_per_sec=1000, burst=10)
    result = remote.ask({"goal": "g"}, questions, timeout=5)
    assert result.answers["stall::repeating_action"]["noul"] == 0.95 and result.input_tokens == 4000
    wrong_key = SystemOneHTTP(url=f"{unwedge_server}/v1/systemone", model="any", profile=FULL_PROFILE,
                              api_key="bad", rate_per_sec=1000, burst=10)
    with pytest.raises(ProviderRejected):
        wrong_key.ask({"goal": "g"}, questions, timeout=5)
    transport = KeepAliveTransport()
    auth = {"Authorization": "Bearer k3y", "Content-Type": "application/json"}
    assert transport(f"{unwedge_server}/v1/systemone", b"not json", auth, 5)[0] == 400
    assert transport(f"{unwedge_server}/v1/systemone", json.dumps({"state": 1}).encode(), auth, 5)[0] == 400
    too_many = {"state": 1, "questions": {f"q{i}": {"type": "noul", "instructions": "x"} for i in range(65)}}
    assert transport(f"{unwedge_server}/v1/systemone", json.dumps(too_many).encode(), auth, 5)[0] == 413
    assert transport(f"{unwedge_server}/nope", b"{}", auth, 5)[0] == 404


class _SlowAgent(_Agent):
    def __init__(self, delay: float):
        super().__init__()
        self.delay = delay

    def predict(self, state, questions):
        time.sleep(self.delay)
        return super().predict(state, questions)


def test_laya_in_process_enforces_the_timeout_and_wraps_errors():
    slow = LayaInProcess(profile=COMPACT_PROFILE, loader=lambda b, c, d: _SlowAgent(0.5))
    started = time.perf_counter()
    with pytest.raises(ProviderTimeout):
        slow.ask({}, QUESTIONS, timeout=0.05)
    with pytest.raises(ProviderTimeout):  # the first pass still holds the model
        slow.ask({}, QUESTIONS, timeout=0.05)
    assert time.perf_counter() - started < 0.4
    assert slow.ask({}, QUESTIONS, timeout=5).answers["q"]["noul"] == 0.7  # waits for the model, then answers
    crashing = LayaInProcess(profile=COMPACT_PROFILE, loader=lambda b, c, d: _Agent(fail=RuntimeError("cuda")))
    with pytest.raises(ProviderUnavailable, match="RuntimeError"):
        crashing.ask({}, QUESTIONS)


def raw_exchange(base: str, request: bytes) -> bytes:
    host, port = base.removeprefix("http://").split(":")
    with socket.create_connection((host, int(port)), timeout=5) as sock:
        sock.sendall(request)
        chunks = []
        while chunk := sock.recv(65536):
            chunks.append(chunk)
    return b"".join(chunks)


def test_unwedge_serve_refuses_unframed_bodies_and_closes(unwedge_server):
    smuggled = (b"POST /v1/systemone HTTP/1.1\r\nHost: x\r\nTransfer-Encoding: chunked\r\n\r\n"
                b"5\r\nhello\r\n0\r\n\r\nGET /health HTTP/1.1\r\nHost: x\r\n\r\n")
    reply = raw_exchange(unwedge_server, smuggled)
    assert reply.startswith(b"HTTP/1.1 501") and b"Connection: close" in reply
    assert reply.count(b"HTTP/1.1 ") == 1  # the request hidden in the body was never parsed
    unsized = raw_exchange(unwedge_server, b"POST /v1/systemone HTTP/1.1\r\nHost: x\r\n\r\n")
    assert unsized.startswith(b"HTTP/1.1 411")
    signed = raw_exchange(unwedge_server, b"POST /v1/systemone HTTP/1.1\r\nHost: x\r\nContent-Length: -1\r\n\r\n")
    assert signed.startswith(b"HTTP/1.1 400")
