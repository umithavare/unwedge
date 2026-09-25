"""Remove secrets before any text leaves the process. Runs on every command and result.

Stateless on purpose: a file viewer can page a key across two turns, so key bodies and
END markers are removed even when the page has no BEGIN marker.
"""

from __future__ import annotations

import re

_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private_key", re.compile(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)", re.DOTALL)),
    ("private_key", re.compile(r"-----END [A-Z ]*PRIVATE KEY-----")),
    # a line of mixed-case base64 (key bodies, certificates); plain hex hashes are left alone
    ("base64_blob", re.compile(
        r"^(?=[A-Za-z0-9+/]*[A-Z])(?=[A-Za-z0-9+/]*[a-z])(?=[A-Za-z0-9+/]*[0-9])[A-Za-z0-9+/]{40,}={0,2}$",
        re.MULTILINE)),
    ("jwt", re.compile(r"\beyJ[\w-]{8,}\.[\w-]{8,}\.[\w-]{8,}")),
    ("aws_key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("github_token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})")),
    ("slack_token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_-]{30,}")),
    ("api_key", re.compile(r"\b(?:sk|pk|rk)[-_][A-Za-z0-9_-]{20,}")),  # OpenAI/Anthropic sk-…, Stripe sk_live_…
    ("bearer", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{16,}")),
    ("url_credentials", re.compile(r"\b([a-z][a-z0-9+.-]*://)[^\s:/@]+:[^\s@/]+@")),
    ("assignment", re.compile(
        r"(?i)\b((?:api[_-]?key|secret|token|passw(?:or)?d|pwd|access[_-]?key)\w*\s*[:=]\s*)"
        r"(['\"]?)[^\s'\"]{6,}\2")),
)


def scrub(text: str) -> str:
    """Replace every secret-looking span with a typed placeholder."""
    for kind, pattern in _RULES:
        if kind == "url_credentials":
            text = pattern.sub(lambda m: f"{m.group(1)}[REDACTED:url_credentials]@", text)
        elif kind == "assignment":
            text = pattern.sub(lambda m: f"{m.group(1)}[REDACTED:secret]", text)
        else:
            text = pattern.sub(f"[REDACTED:{kind}]", text)
    return text
