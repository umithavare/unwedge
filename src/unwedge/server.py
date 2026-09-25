"""`unwedge serve`: a local System One endpoint backed by an in-process Laya model.

laya-mlx (Apple silicon) ships no HTTP server, and hook processes are too short-lived to
load a checkpoint, so this keeps the model resident and speaks the same wire protocol as
jev and `laya-serve`: POST /v1/systemone {state, questions, model?} -> {model, answers, usage}.
Binds to 127.0.0.1 by default; set an API key before exposing it on a network.
"""

from __future__ import annotations

import hmac
import json
from collections.abc import Mapping
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from unwedge.providers.base import Provider, ProviderError

MAX_BODY_BYTES = 2_000_000
MAX_QUESTIONS = 64


def make_handler(provider: Provider, api_key: str | None = None) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "unwedge-serve"
        sys_version = ""
        protocol_version = "HTTP/1.1"  # keep-alive: every response carries Content-Length

        def do_GET(self) -> None:  # noqa: N802 - http.server naming
            if self.path.rstrip("/") in ("", "/health", "/v1/health"):
                self._send(200, {"status": "ok", "model": getattr(provider, "model", provider.profile.name)})
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self) -> None:  # noqa: N802
            length = self._body_length()
            if length is None:
                return
            raw = self.rfile.read(length) if length else b""  # always drain before answering
            if self.path.rstrip("/") != "/v1/systemone":
                return self._send(404, {"error": "not found"})
            if api_key and not self._authorized():
                return self._send(401, {"error": "missing or invalid bearer token"})
            if not raw:
                return self._send(400, {"error": "empty body"})
            try:
                body = json.loads(raw)
            except ValueError:
                return self._send(400, {"error": "body is not JSON"})
            problem = _validate(body)
            if problem:
                return self._send(400 if problem != "too many questions" else 413, {"error": problem})
            try:
                result = provider.ask(body["state"], body["questions"])
            except ProviderError as exc:
                return self._send(503, {"error": type(exc).__name__})
            self._send(200, {"model": result.model, "answers": result.answers,
                             "usage": {"input_tokens": result.input_tokens, "output_tokens": 0}})

        def _body_length(self) -> int | None:
            """Content-Length, or None after refusing a body that cannot be read safely. Such a
            body is never read, so the connection is closed: leftover bytes must not be parsed
            as the next request."""
            raw = self.headers.get("Content-Length")
            if self.headers.get("Transfer-Encoding"):
                status, problem = 501, "chunked bodies are not supported; send Content-Length"
            elif raw is None:
                status, problem = 411, "Content-Length required"
            elif not raw.strip().isdigit():
                status, problem = 400, "bad Content-Length"
            elif int(raw) > MAX_BODY_BYTES:
                status, problem = 413, "body too large"
            else:
                return int(raw)
            self.close_connection = True
            self._send(status, {"error": problem})
            return None

        def _authorized(self) -> bool:
            header = self.headers.get("Authorization") or ""
            token = header[7:] if header.startswith("Bearer ") else ""
            return hmac.compare_digest(token.encode(), (api_key or "").encode())

        def _send(self, status: int, body: dict) -> None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            if self.close_connection:
                self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args: Any) -> None:  # quiet by default; states can be sensitive
            return

    return Handler


def _validate(body: Any) -> str | None:
    if not isinstance(body, Mapping):
        return "body must be a JSON object"
    if "state" not in body or not isinstance(body.get("questions"), Mapping) or not body["questions"]:
        return "body needs 'state' and a non-empty 'questions' object"
    if len(body["questions"]) > MAX_QUESTIONS:
        return "too many questions"
    return None


def serve(provider: Provider, host: str = "127.0.0.1", port: int = 8000, api_key: str | None = None) -> None:
    httpd = ThreadingHTTPServer((host, port), make_handler(provider, api_key))
    print(f"unwedge serve: {getattr(provider, 'model', provider.profile.name)} on http://{host}:{port}/v1/systemone",
          flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        provider.close()
