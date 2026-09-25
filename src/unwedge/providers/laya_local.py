"""Laya inside this process: `laya_mlx` on Apple silicon when installed, otherwise the
`laya` (PyTorch) package. Loading a checkpoint takes seconds and about a gigabyte of
memory, so this backend suits long-lived processes and `unwedge serve`. Hook processes
are short-lived and must talk to a server (`laya-serve` or `unwedge serve`) instead;
`UNWEDGE_PROVIDER` does not accept this backend.
"""

from __future__ import annotations

import importlib
import threading
import time
from collections.abc import Callable, Mapping
from typing import Any

from unwedge.providers.base import (
    Profile,
    ProviderResult,
    ProviderTimeout,
    ProviderUnavailable,
    validate_answers,
)

# checkpoint name -> (PyTorch `laya.load` kwargs, laya-mlx Hub id)
CHECKPOINTS: dict[str, tuple[dict, str]] = {
    "english": ({"model_id_or_path": "convaiinnovations/laya"}, "aac6fef/laya-mlx"),
    "multilingual": ({"model_id_or_path": "convaiinnovations/laya", "subfolder": "multilingual"},
                     "aac6fef/laya-multilingual-mlx"),
    "typed-decisions": ({"model_id_or_path": "convaiinnovations/laya", "subfolder": "typed-decisions"},
                        "aac6fef/laya-typed-decisions-mlx"),
}
BACKENDS = ("auto", "mlx", "torch")

Loader = Callable[[str, str, str | None], Any]  # (backend, checkpoint, device) -> agent with .predict()


def default_loader(backend: str, checkpoint: str, device: str | None) -> Any:
    torch_kwargs, mlx_id = CHECKPOINTS[checkpoint]
    if backend == "mlx":
        laya_mlx = importlib.import_module("laya_mlx")
        return laya_mlx.load(mlx_id, **({"device": device} if device else {}))
    laya = importlib.import_module("laya")
    return laya.load(**torch_kwargs, **({"device": device} if device else {}))


def pick_backend(requested: str) -> str:
    if requested not in BACKENDS:
        raise ValueError(f"backend must be one of {BACKENDS}")
    if requested != "auto":
        return requested
    for backend, module in (("mlx", "laya_mlx"), ("torch", "laya")):
        try:
            importlib.import_module(module)
            return backend
        except ImportError:
            continue
    raise ProviderUnavailable("neither laya-mlx nor laya is installed: pip install laya "
                              "(or laya-mlx on Apple silicon)")


class LayaInProcess:
    def __init__(self, *, profile: Profile, checkpoint: str = "english", backend: str = "auto",
                 device: str | None = None, loader: Loader | None = None) -> None:
        if checkpoint not in CHECKPOINTS:
            raise ValueError(f"checkpoint must be one of {sorted(CHECKPOINTS)}")
        self.profile = profile
        self.backend = pick_backend(backend) if loader is None else (backend if backend != "auto" else "torch")
        self.model = f"laya-{checkpoint}-{self.backend}"
        self._agent = (loader or default_loader)(self.backend, checkpoint, device)
        self._lock = threading.Lock()  # one forward pass at a time; the checkpoint is shared

    def close(self) -> None:
        self._agent = None

    def ask(self, state: Any, questions: Mapping[str, Mapping], *, timeout: float | None = None) -> ProviderResult:
        """A forward pass cannot be interrupted, so it runs in a worker thread: past `timeout`
        the call raises ProviderTimeout and the pass finishes in the background, holding the
        model until it does (later calls wait for it within their own timeout)."""
        agent = self._agent
        if agent is None:
            raise ProviderUnavailable("provider is closed")
        started = time.perf_counter()
        if not self._lock.acquire(timeout=-1 if timeout is None else max(timeout, 0.0)):
            raise ProviderTimeout(f"model busy for more than {timeout:.2f}s")
        outcome: dict[str, Any] = {}

        def run() -> None:
            try:
                outcome["result"] = agent.predict(state, dict(questions))
            except Exception as exc:  # noqa: BLE001 - reported to the caller as a provider error
                outcome["error"] = exc
            finally:
                self._lock.release()

        worker = threading.Thread(target=run, name="laya-predict", daemon=True)
        worker.start()
        worker.join(None if timeout is None else max(timeout - (time.perf_counter() - started), 0.0))
        if worker.is_alive():
            raise ProviderTimeout(f"no answer within {timeout:.2f}s")
        error = outcome.get("error")
        if isinstance(error, ValueError):  # e.g. "too many options for the token budget"
            raise ProviderUnavailable(f"laya rejected the request: {error}") from error
        if error is not None:
            raise ProviderUnavailable(f"laya failed: {type(error).__name__}: {error}") from error
        result = outcome["result"]
        answers = validate_answers(result, questions)
        usage = result.get("usage") or {}
        return ProviderResult(answers=answers, input_tokens=int(usage.get("input_tokens") or 0),
                              latency_s=time.perf_counter() - started, model=self.model, cost_usd=0.0)
