"""Judgment providers. Pick one with `make_provider(name)`:

- "jev": TypeSafe's hosted jev API (needs TYPESAFE_API_KEY). Large context, full question battery.
- "laya": a local Laya server speaking the same protocol (`laya-serve` or `unwedge serve`).
- "laya-local": Laya loaded into this process (laya-mlx on Apple silicon, else PyTorch laya).
- "none": no model at all; unwedge runs on its code-only tier.
"""

from __future__ import annotations

import os
from dataclasses import replace

from unwedge.compactor import COMPACT_DIGEST, DigestConfig
from unwedge.providers.base import (
    Profile,
    Provider,
    ProviderBlocked,
    ProviderError,
    ProviderMalformed,
    ProviderRateLimited,
    ProviderRejected,
    ProviderResult,
    ProviderTimeout,
    ProviderUnavailable,
)
from unwedge.providers.systemone_http import SystemOneHTTP

JEV_URL = "https://api.typesafe.ai/v1/systemone"
JEV_MODEL = "jev-1.13.0"  # pinned: an alias can move and shift every threshold
LAYA_URL = "http://127.0.0.1:8000/v1/systemone"
# "english" answered simple English yes/no questions far more sensibly than "multilingual" in
# our probes; use "multilingual" for non-English sessions (see docs/providers.md).
LAYA_MODEL = "english"

JEV_PROFILE = Profile(name="jev", battery="full", digest=DigestConfig(), usd_per_input_token=0.042e-6,
                      hot_path_timeout_s=0.5)
# Laya checkpoints read at most 512 ("english") or 1,024 tokens per question row, question
# included, so the state is compact and the questions are short. CPU inference takes seconds;
# on a GPU or Apple silicon it is ~0.1 s.
LAYA_PROFILE = Profile(name="laya", battery="compact", digest=COMPACT_DIGEST, usd_per_input_token=0.0,
                       hot_path_timeout_s=5.0)
LAYA_512_PROFILE = replace(LAYA_PROFILE, digest=replace(COMPACT_DIGEST, window=5, goal_chars=300,
                                                        last_result_chars=300, max_state_chars=1100))


def laya_profile(checkpoint: str) -> Profile:
    return LAYA_512_PROFILE if checkpoint == "english" else LAYA_PROFILE


PROVIDER_NAMES = ("none", "jev", "laya", "laya-local")

__all__ = [
    "JEV_MODEL", "JEV_PROFILE", "JEV_URL", "LAYA_512_PROFILE", "LAYA_MODEL", "LAYA_PROFILE", "LAYA_URL",
    "PROVIDER_NAMES", "laya_profile",
    "Profile", "Provider", "ProviderBlocked", "ProviderError", "ProviderMalformed", "ProviderRateLimited",
    "ProviderRejected", "ProviderResult", "ProviderTimeout", "ProviderUnavailable", "SystemOneHTTP",
    "make_provider",
]


def make_provider(name: str, *, url: str | None = None, model: str | None = None, api_key: str | None = None,
                  backend: str = "auto") -> Provider | None:
    """Build a provider. Returns None for "none" (code-only tier)."""
    name = (name or "none").strip().lower()
    if name in ("none", "off", "code"):
        return None
    if name == "jev":
        key = api_key or os.environ.get("TYPESAFE_API_KEY")
        if not key:
            raise ValueError("provider 'jev' needs an API key: set TYPESAFE_API_KEY")
        return SystemOneHTTP(url=url or JEV_URL, model=model or JEV_MODEL, profile=JEV_PROFILE, api_key=key)
    if name == "laya":
        checkpoint = model or os.environ.get("LAYA_MODEL") or LAYA_MODEL
        return SystemOneHTTP(
            url=url or os.environ.get("LAYA_URL") or LAYA_URL,
            model=checkpoint,
            profile=laya_profile(checkpoint),
            api_key=api_key or os.environ.get("LAYA_API_KEY") or None,
            rate_per_sec=50.0,
            burst=10,
        )
    if name == "laya-local":
        from unwedge.providers.laya_local import LayaInProcess

        checkpoint = model or os.environ.get("LAYA_MODEL") or LAYA_MODEL
        return LayaInProcess(profile=laya_profile(checkpoint), checkpoint=checkpoint, backend=backend)
    raise ValueError(f"unknown provider {name!r}; choose one of {', '.join(PROVIDER_NAMES)}")
