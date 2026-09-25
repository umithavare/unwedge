"""Deterministic text plumbing: tool classes, normalization, fingerprints, similarity.

Everything here is exact and free, so none of it is ever asked of jev.
"""

from __future__ import annotations

import hashlib
import re
from difflib import SequenceMatcher

from unwedge.turns import ToolClass

_NAVIGATE = {"open", "goto", "scroll_down", "scroll_up", "cat", "head", "tail", "less", "more", "view"}
_SEARCH = {
    "search_dir", "search_file", "find_file", "grep", "rg", "find", "ls", "tree", "pwd",
    "which", "cd", "echo", "wc", "diff", "file", "stat",
}
_EDIT = {"edit", "create", "insert", "append", "rm", "mv", "cp", "touch", "mkdir", "patch", "chmod", "ln"}
_READ_ONLY_GIT = {"log", "status", "diff", "show", "blame", "grep"}
_CLASS_RANK = {  # when a compound command mixes classes, the strongest wins
    ToolClass.EDIT: 4, ToolClass.RUN: 3, ToolClass.SUBMIT: 2,
    ToolClass.SEARCH: 1, ToolClass.NAVIGATE: 0, ToolClass.INVALID: -1,
}

_ADDRESS = re.compile(r"0x[0-9a-fA-F]{4,}")
_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?")
_DURATION = re.compile(r"\b\d+(?:\.\d+)?\s?(?:s|ms|sec|seconds)\b")
_TMP_PATH = re.compile(r"/tmp/[\w./-]+")
_WHITESPACE = re.compile(r"\s+")
_TOKEN = re.compile(r"\w+|[^\w\s]")
_VIEWER_LINE = re.compile(r"^\s*(?:\d+:|Line \d+:)")  # file-viewer and search-hit lines

_TOOL_FAILURE = (
    r"command not found|No such file or directory|Permission denied|Usage: "
    r"|(?:File|Directory) .{1,200} not found|No file open|edit REJECTED"
    r"|must be (?:less|greater|a positive)|invalid option|unrecognized (?:option|arguments)"
)
_TOOL_FAILURE_PATTERNS = re.compile(_TOOL_FAILURE, re.MULTILINE)
_ERROR_PATTERNS = re.compile(
    r"Traceback \(most recent call last\)"
    r"|^\s*[A-Za-z_][\w.]*(?:Error|Exception)\b"
    r"|\bFAILED\b|\bERROR\b|^\s*error:|^E\s{2,}\w|" + _TOOL_FAILURE,
    re.MULTILINE,
)
_EXCEPTION_LINE = re.compile(r"^\s*([A-Za-z_][\w.]*(?:Error|Exception|Exit|Interrupt)\b.*)$", re.MULTILINE)


def classify_command(command: str) -> tuple[str, ToolClass]:
    """Return the tool name (first word) and the strongest tool class in the command."""
    first_line = command.strip().splitlines()[0] if command.strip() else ""
    if not first_line:
        return "", ToolClass.INVALID
    tool = first_line.split()[0]
    parts = re.split(r"&&|\|\||;|\|", first_line)
    classes = [_classify_simple(part.strip()) for part in parts if part.strip()]
    if re.search(r"(?<![0-9&])>{1,2}(?!&)", first_line) and not first_line.startswith(("edit", "search")):
        classes.append(ToolClass.EDIT)  # redirection writes a file
    best = max(classes, key=lambda cls: _CLASS_RANK[cls]) if classes else ToolClass.RUN
    return tool, best


def _classify_simple(part: str) -> ToolClass:
    words = part.split()
    head = words[0]
    if head == "submit":
        return ToolClass.SUBMIT
    if head in _NAVIGATE:
        return ToolClass.NAVIGATE
    if head in _SEARCH:
        return ToolClass.SEARCH
    if head in _EDIT:
        return ToolClass.EDIT
    if head == "sed":
        return ToolClass.EDIT if "-i" in words else ToolClass.NAVIGATE
    if head == "git":
        return ToolClass.SEARCH if len(words) > 1 and words[1] in _READ_ONLY_GIT else ToolClass.EDIT
    if head in {"pip", "pip3", "conda", "apt", "apt-get", "npm", "yarn"} and "install" in words:
        return ToolClass.EDIT
    return ToolClass.RUN


def normalize_command(command: str) -> str:
    """First line with collapsed whitespace; a multi-line body is replaced by its hash."""
    lines = command.strip().splitlines()
    if not lines:
        return ""
    head = _WHITESPACE.sub(" ", lines[0]).strip()
    body = "\n".join(lines[1:]).strip()
    if body:
        head += f" <body:{hashlib.sha1(body.encode('utf-8')).hexdigest()[:8]}>"
    return head


def normalize_observation(text: str) -> str:
    """Remove incidental detail (addresses, timestamps, durations, temp paths)."""
    text = _ADDRESS.sub("0x_", text)
    text = _TIMESTAMP.sub("<ts>", text)
    text = _DURATION.sub("<dur>", text)
    text = _TMP_PATH.sub("/tmp/_", text)
    return _WHITESPACE.sub(" ", text).strip()


def fingerprint(text: str, length: int = 12) -> str:
    return hashlib.sha1(normalize_observation(text).encode("utf-8")).hexdigest()[:length]


def shingles(text: str, size: int = 3) -> frozenset[str]:
    tokens = _TOKEN.findall(normalize_observation(text).lower())
    if len(tokens) < size:
        return frozenset(tokens)
    return frozenset(" ".join(tokens[i : i + size]) for i in range(len(tokens) - size + 1))


def jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    if not left and not right:
        return 1.0
    union = len(left | right)
    return len(left & right) / union if union else 0.0


def command_similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, normalize_command(left), normalize_command(right)).ratio()


def looks_like_error(observation: str, tool_class: ToolClass = ToolClass.RUN) -> bool:
    """True when the result reports a failure.

    Read-only tools return data (file contents, grep hits) that can mention errors
    without failing, so for them only tool-level failures count. File-viewer lines
    are ignored everywhere."""
    kept = "\n".join(line for line in observation.splitlines() if not _VIEWER_LINE.match(line))
    if tool_class in (ToolClass.NAVIGATE, ToolClass.SEARCH):
        return bool(_TOOL_FAILURE_PATTERNS.search(kept))
    return bool(_ERROR_PATTERNS.search(kept))


def error_signature(observation: str, limit: int = 200) -> str:
    """The most informative failure line: the last exception line, else the first line
    that mentions an error, else the first non-empty line."""
    kept = [line for line in observation.splitlines() if line.strip() and not _VIEWER_LINE.match(line)]
    text = "\n".join(kept)
    exceptions = _EXCEPTION_LINE.findall(text)
    if exceptions:
        line = exceptions[-1]
    else:
        line = next((ln for ln in kept if re.search(r"error|fail|not found|denied", ln, re.I)), kept[0] if kept else "")
    return normalize_observation(line)[:limit]
