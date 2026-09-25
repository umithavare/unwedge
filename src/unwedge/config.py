"""Settings from the environment.

Precedence: UNWEDGE_* variables, then plugin options (Claude Code exports a plugin's
userConfig to hooks as CLAUDE_PLUGIN_OPTION_<KEY>), then defaults. Provider keys use
the provider's own variable names (TYPESAFE_API_KEY, LAYA_URL, LAYA_API_KEY, LAYA_MODEL).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from unwedge.providers import Provider, make_provider

MODES = ("shadow", "hint", "stop")
# laya-local would load a checkpoint (seconds, ~1 GB) in every short-lived hook process
SETTINGS_PROVIDERS = ("none", "jev", "laya")
_PLUGIN = "CLAUDE_PLUGIN_OPTION_"


def _pick(env: Mapping[str, str], *names: str) -> str | None:
    for name in names:
        value = env.get(name)
        if value is not None and value.strip():
            return value.strip()
    return None


@dataclass(frozen=True)
class Settings:
    provider: str = "auto"  # auto | none | jev | laya
    mode: str = "shadow"  # shadow | hint | stop
    url: str | None = None
    model: str | None = None
    api_key: str | None = field(default=None, repr=False)
    timeout_s: float | None = None
    home: Path = field(default_factory=lambda: Path.home() / ".unwedge")

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if env is None else env
        provider = (_pick(env, "UNWEDGE_PROVIDER", _PLUGIN + "PROVIDER") or "auto").lower()
        if provider == "laya-local":
            raise ValueError("UNWEDGE_PROVIDER=laya-local would load the model in every hook process; "
                             "run `unwedge serve` (or laya-serve) and use UNWEDGE_PROVIDER=laya")
        if provider not in ("auto", *SETTINGS_PROVIDERS):
            raise ValueError(f"UNWEDGE_PROVIDER must be auto or one of {', '.join(SETTINGS_PROVIDERS)}")
        mode = (_pick(env, "UNWEDGE_MODE", _PLUGIN + "MODE") or "shadow").lower()
        if mode not in MODES:
            raise ValueError(f"UNWEDGE_MODE must be one of {', '.join(MODES)}")
        timeout = _pick(env, "UNWEDGE_TIMEOUT")
        home = _pick(env, "UNWEDGE_HOME")
        if provider == "auto":
            has_key = _pick(env, "TYPESAFE_API_KEY", _PLUGIN + "TYPESAFE_API_KEY")
            provider = "jev" if has_key else "none"
        if provider == "jev":
            url = _pick(env, "UNWEDGE_URL")
            model = _pick(env, "UNWEDGE_MODEL")
            key = _pick(env, "UNWEDGE_API_KEY", "TYPESAFE_API_KEY", _PLUGIN + "TYPESAFE_API_KEY")
        elif provider == "laya":
            url = _pick(env, "UNWEDGE_URL", "LAYA_URL", _PLUGIN + "LAYA_URL")
            model = _pick(env, "UNWEDGE_MODEL", "LAYA_MODEL", _PLUGIN + "LAYA_MODEL")
            key = _pick(env, "UNWEDGE_API_KEY", "LAYA_API_KEY", _PLUGIN + "LAYA_API_KEY")
        else:
            url = model = key = None
        return cls(
            provider=provider,
            mode=mode,
            url=url,
            model=model,
            api_key=key,
            timeout_s=float(timeout) if timeout else None,
            home=Path(home).expanduser() if home else Path.home() / ".unwedge",
        )

    def make_provider(self) -> Provider | None:
        return make_provider(self.provider, url=self.url, model=self.model, api_key=self.api_key)
