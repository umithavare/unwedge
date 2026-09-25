from __future__ import annotations

import json
import re
from pathlib import Path

from unwedge import __version__

ROOT = Path(__file__).resolve().parent.parent


def load(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def hook_commands(hooks: dict) -> list[str]:
    return [" ".join([h["command"], *h.get("args", [])]) for groups in hooks["hooks"].values()
            for group in groups for h in group["hooks"]]


def test_versions_agree():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert re.search(r'^version = "([^"]+)"', pyproject, re.M).group(1) == __version__
    assert load("plugins/claude-code/.claude-plugin/plugin.json")["version"] == __version__
    assert load("plugins/codex/plugin.json")["version"] == __version__
    assert load(".claude-plugin/marketplace.json")["plugins"][0]["version"] == __version__


def test_claude_code_plugin_hooks_call_unwedge_in_the_background():
    hooks = load("plugins/claude-code/hooks/hooks.json")
    assert set(hooks["hooks"]) >= {"PostToolUse", "PostToolUseFailure", "UserPromptSubmit"}
    assert set(hook_commands(hooks)) == {"unwedge hook"}
    assert all(h.get("async") for groups in hooks["hooks"].values() for g in groups for h in g["hooks"])
    options = load("plugins/claude-code/.claude-plugin/plugin.json")["userConfig"]
    assert options["typesafe_api_key"]["sensitive"] is True


def test_marketplaces_point_at_the_plugins():
    claude = load(".claude-plugin/marketplace.json")["plugins"][0]["source"]
    codex = load(".agents/plugins/marketplace.json")["plugins"][0]["source"]["path"]
    assert (ROOT / claude / ".claude-plugin" / "plugin.json").exists()
    assert (ROOT / codex / "plugin.json").exists() and (ROOT / codex / "hooks" / "hooks.json").exists()
    assert set(hook_commands(load("plugins/codex/hooks/hooks.json"))) == {"unwedge hook"}
