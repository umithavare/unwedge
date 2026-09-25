from __future__ import annotations

import pytest

from unwedge.normalize import (
    classify_command,
    command_similarity,
    error_signature,
    fingerprint,
    jaccard,
    looks_like_error,
    normalize_command,
    shingles,
)
from unwedge.scrub import scrub
from unwedge.turns import ToolClass


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("open src/app.py 40", ToolClass.NAVIGATE),
        ("scroll_down", ToolClass.NAVIGATE),
        ("search_dir \"foo\" src", ToolClass.SEARCH),
        ("grep -rn foo .", ToolClass.SEARCH),
        ("edit 10:12\n    x = 1\nend_of_edit", ToolClass.EDIT),
        ("python reproduce.py", ToolClass.RUN),
        ("pytest -x tests/test_a.py", ToolClass.RUN),
        ("pip install requests", ToolClass.EDIT),
        ("sed -n 1,20p a.py", ToolClass.NAVIGATE),
        ("sed -i 's/a/b/' a.py", ToolClass.EDIT),
        ("git diff", ToolClass.SEARCH),
        ("git checkout -- a.py", ToolClass.EDIT),
        ("echo hi > out.txt", ToolClass.EDIT),
        ("ls && python run.py", ToolClass.RUN),
        ("submit", ToolClass.SUBMIT),
        ("", ToolClass.INVALID),
    ],
)
def test_classify_command(command, expected):
    assert classify_command(command)[1] is expected


def test_classify_returns_first_word_as_tool():
    assert classify_command("find_file \"x.py\"")[0] == "find_file"


def test_normalize_command_hashes_multiline_body():
    a = normalize_command("edit 1:2\nfoo\nend_of_edit")
    b = normalize_command("edit   1:2\nbar\nend_of_edit")
    assert a.startswith("edit 1:2 <body:") and a != b
    assert normalize_command("  ls   -la ") == "ls -la"
    assert normalize_command("") == ""


def test_fingerprint_ignores_incidental_detail():
    first = "failed at 2026-09-01 10:00:01 object at 0x7f3a9c2b in 0.53s /tmp/abc123/x"
    second = "failed at 2026-09-02 11:30:59 object at 0x1111aaaa in 1.2s /tmp/zzz/x"
    assert fingerprint(first) == fingerprint(second)
    assert fingerprint("AssertionError: 1 != 2") != fingerprint("AssertionError: 1 != 3")


def test_shingles_and_jaccard():
    same = shingles("the quick brown fox jumps")
    assert jaccard(same, same) == 1.0
    assert jaccard(frozenset(), frozenset()) == 1.0
    assert 0.0 < jaccard(same, shingles("the quick brown dog jumps")) < 1.0
    assert shingles("a b") == frozenset({"a", "b"})


def test_command_similarity():
    assert command_similarity("python a.py", "python a.py") == 1.0
    assert command_similarity("python a.py", "pytest tests") < 0.8


def test_looks_like_error_depends_on_tool_class():
    grep_hits = "src/x.py: raise ValueError('bad')\nsrc/y.py: except TypeError:"
    assert not looks_like_error(grep_hits, ToolClass.SEARCH)
    assert looks_like_error("Traceback (most recent call last):\nValueError: bad", ToolClass.RUN)
    assert looks_like_error("File missing.py not found", ToolClass.NAVIGATE)
    viewer = "[File: /a.py (10 lines total)]\n1:raise ValueError('x')"
    assert not looks_like_error(viewer, ToolClass.RUN)
    assert not looks_like_error("3 passed", ToolClass.RUN)


def test_error_signature_prefers_last_exception_line():
    text = 'Traceback (most recent call last):\n  File "a.py", line 3\nKeyError: \'x\'\nValueError: final'
    assert error_signature(text) == "ValueError: final"
    assert error_signature("bash: foo: command not found") == "bash: foo: command not found"
    assert error_signature("") == ""


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("key AKIAABCDEFGHIJKLMNOP here", "aws_key"),
        ("token ghp_abcdefghijklmnopqrstuvwxyz0123456789", "github_token"),
        ("Authorization: Bearer abcdefghijklmnop1234", "bearer"),
        ("sk-ant-api03-abcdefghijklmnopqrstuvwxyz", "api_key"),
        ("eyJhbGciOiJIUzI1.eyJzdWIiOiIxMjM0.SflKxwRJSMeKKF2QT4", "jwt"),
        ("xoxb-123456789012-abcdef", "slack_token"),
    ],
)
def test_scrub_rules(text, kind):
    assert f"[REDACTED:{kind}]" in scrub(text)


@pytest.mark.parametrize(
    "secret",
    ["sk_live_4eC39HqLyjWDarjtT1zdp7dc", "pk_test_TYooMQauvdEDq54NiTphI7jx", "rk_live_51HabcdefghijklmnopQRSTU",
     "AIzaSyD-1234567890abcdefghijklmnopqrstu"],
)
def test_scrub_underscore_and_google_keys(secret):
    assert secret not in scrub(f"config key = {secret} end")


def test_scrub_catches_a_private_key_split_across_turns():
    first_page = "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEAu1SU1LfVLPHCozMxH2Mo4lgOEePzNm0tRgeLezV6ffAt0gun"
    second_page = ("VTLw7onLRnrq0/IzW7yWR7QkrmBL7jTKEn5u+qKhbwKfBstIs+bMY2Zkp18gnTxKLxoS2tFczGkPLPgizskuemMghRniWaoL\n"
                   "-----END RSA PRIVATE KEY-----")
    assert "MIIEowIBAAKCAQEAu1SU1LfVLPHCozMxH2Mo4lgOEePzNm0tRgeLezV6ffAt0gun" not in scrub(first_page)
    cleaned = scrub(second_page)
    assert "VTLw7onLRnrq0" not in cleaned and "END RSA PRIVATE KEY" not in cleaned


def test_scrub_leaves_ordinary_code_alone():
    code = "def add(a, b):\n    return a + b  # simple\nfor i in range(10): print(i)"
    assert scrub(code) == code


def test_scrub_url_credentials_and_assignments_and_keys():
    assert scrub("postgres://admin:hunter22@db:5432/x") == "postgres://[REDACTED:url_credentials]@db:5432/x"
    assert "hunter22secret" not in scrub("PASSWORD='hunter22secret'")
    block = "-----BEGIN RSA PRIVATE KEY-----\nMIIabc\n-----END RSA PRIVATE KEY-----"
    assert scrub(block) == "[REDACTED:private_key]"
    assert scrub("nothing secret here") == "nothing secret here"
