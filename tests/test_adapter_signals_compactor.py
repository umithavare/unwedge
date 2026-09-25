from __future__ import annotations

from conftest import make_turn

from unwedge.adapters.sweagent import (
    clean_observation,
    extract_command,
    extract_goal,
    parse_transcript,
    session_from_row,
)
from unwedge.code_signals import compute_signals
from unwedge.compactor import DigestConfig, build_state, clip, digest_line, display_command, summarize_result
from unwedge.turns import ToolClass

FOOTER = "\n(Open file: /repo/a.py)\n(Current directory: /repo)\nbash-$"
REJECTED = (
    "Your proposed edit has introduced new syntax error(s). Please read this error message carefully and then "
    "retry editing the file.\n\nERRORS:\n- E999 IndentationError: unexpected indent\n\nThis is how your edit "
    "would have looked if applied\n...\nYour changes have NOT been applied." + FOOTER
)
APPLIED = (
    "[File: /repo/a.py (20 lines total)]\n1:x = 1\n2:y = 2\nFile updated. Please review the changes and make sure "
    "they are correct (correct indentation, no duplicate lines, etc). Edit the file again if necessary." + FOOTER
)


def test_goal_and_command_extraction():
    task = "We're solving this.\nISSUE:\nThe parser crashes on empty input.\n\nINSTRUCTIONS:\nDo things."
    assert extract_goal(task) == "The parser crashes on empty input."
    assert extract_goal("no markers here") == "no markers here"
    assert extract_command("Let me look.\n```\nopen a.py\n```") == "open a.py"
    assert extract_command("no fence") == ""


def test_clean_observation_rewrites_harness_text():
    expected = ("edit REJECTED, not applied: E999 IndentationError: unexpected indent", False)
    assert clean_observation(REJECTED) == expected
    text, applied = clean_observation(APPLIED)
    assert applied is True and text.endswith("(edit applied)") and "Please review" not in text
    assert clean_observation("Your command ran successfully and did not produce any output." + FOOTER) == (
        "(no output)", None)
    assert clean_observation("hello" + FOOTER) == ("hello", None)


def test_parse_transcript_builds_turns_with_growing_cost():
    messages = [
        {"role": "system", "text": ""},
        {"role": "user", "text": "ISSUE:\nFix it.\n\nINSTRUCTIONS:\ngo"},
        {"role": "ai", "text": "try\n```\nedit 1:1\nx=2\nend_of_edit\n```"},
        {"role": "user", "text": REJECTED},
        {"role": "ai", "text": "again\n```\npython a.py\n```"},
        {"role": "user", "text": "Traceback (most recent call last):\nValueError: no" + FOOTER},
        {"role": "ai", "text": "oops, no command"},
        {"role": "user", "text": "Your output was not formatted correctly." + FOOTER},
        {"role": "ai", "text": "```\nsubmit\n```"},
    ]
    goal, turns = parse_transcript(messages)
    assert goal == "Fix it."
    assert [t.tool_class for t in turns] == [ToolClass.EDIT, ToolClass.RUN, ToolClass.INVALID, ToolClass.SUBMIT]
    assert turns[0].is_error and not turns[0].changes_state
    assert turns[1].is_error and turns[2].is_error
    assert all(a.cost_units < b.cost_units for a, b in zip(turns, turns[1:], strict=False))
    assert parse_transcript([{"role": "system", "text": ""}]) == ("", ())


def test_session_from_row_keeps_outcome_labels():
    row = {"instance_id": "org__repo-1", "target": True, "exit_status": "submitted",
           "trajectory": [{"role": "user", "text": "ISSUE:\nBug.\n\nINSTRUCTIONS:\nx"},
                          {"role": "user", "text": "stray message"},
                          {"role": "ai", "text": "```\nls\n```"}, {"role": "user", "text": "a.py" + FOOTER}]}
    session = session_from_row(row, "success")
    labels = (session.session_id, session.group, session.resolved, session.goal)
    assert labels == ("org__repo-1", "success", True, "Bug.")
    assert len(session.turns) == 1 and session.turns[0].observation == "a.py"
    assert session.total_cost == session.turns[0].cost_units


def test_repeat_without_change_resets_after_an_applied_edit():
    turns = [
        make_turn(1, "python a.py", "ValueError: boom"),
        make_turn(2, "python a.py", "ValueError: boom"),
        make_turn(3, "edit 1:1\nfix\nend_of_edit", "(edit applied)", applied=True),
        make_turn(4, "python a.py", "ValueError: boom"),
    ]
    signals = compute_signals(turns)
    assert signals[1].repeat_without_change == 1 and signals[1].result_repeats == 1
    assert signals[3].exact_repeats == 2 and signals[3].repeat_without_change == 0
    assert signals[3].error_repeats == 2 and signals[3].turns_since_change == 1
    assert signals[2].turns_since_change == 0


def test_streak_signals():
    turns = [make_turn(i, f"open a.py {i * 50}", f"view {i}") for i in range(1, 6)]
    turns.append(make_turn(6, "", "(the agent produced no valid command)"))
    signals = compute_signals(turns)
    assert signals[4].read_only_streak == 5 and signals[4].result_repeats == 0
    assert signals[5].invalid_streak == 1 and signals[5].read_only_streak == 0
    assert signals[0].action_similarity == 0.0


def test_build_state_shape_and_window():
    turns = [make_turn(i, f"python run.py --n {i}", f"output {i}") for i in range(1, 16)]
    state = build_state("goal text", turns, DigestConfig(window=5, last_results=2))
    assert state["goal"] == "goal text"
    assert len(state["window"]) == 5 and state["window"][0].startswith("T11 ")
    assert [r["turn"] for r in state["last_results"]] == [14, 15]
    fp_line = digest_line(turns[0], DigestConfig(fingerprints=True))
    assert "[fp:" in fp_line and "[fp:" not in digest_line(turns[0])


def test_summarize_result_per_tool_class():
    view = make_turn(1, "open a.py", "[File: /r/a.py (300 lines total)]\n(10 more lines above)\n11:a\n12:b")
    assert summarize_result(view) == "shows /r/a.py lines 11-12 of 300"
    search = make_turn(2, "search_dir foo", "Found 2 matches for \"foo\" in /r:\n/r/a.py\n/r/b.py")
    assert summarize_result(search) == 'Found 2 matches for "foo" in /r: (+2 lines)'
    failing = make_turn(3, "python a.py", "Traceback (most recent call last):\nKeyError: 'k'")
    assert summarize_result(failing) == "ERROR KeyError: 'k'"
    assert summarize_result(make_turn(4, "edit 1:1\nx\nend_of_edit", "(edit applied)", applied=True)) == "edit applied"
    assert summarize_result(make_turn(5, "submit", "")) == "submitted"
    assert summarize_result(make_turn(6, "", "")) == "no valid command"
    assert summarize_result(make_turn(7, "python quiet.py", "")) == "ok (no output)"
    rejected = make_turn(8, "edit 1:1\nx\nend_of_edit", "edit REJECTED, not applied: E999", applied=False)
    assert summarize_result(rejected) == "edit REJECTED, not applied: E999"


def test_display_command_and_clip():
    assert display_command("edit 1:3\na\nb\nend_of_edit", 50) == "edit 1:3 (+3 lines)"
    assert display_command("", 10) == "(none)"
    clipped = clip("a" * 50 + "MIDDLE" + "z" * 50, 40)
    assert len(clipped) <= 41 and clipped.startswith("a") and clipped.endswith("z") and " … " in clipped
    assert clip("short", 40) == "short"


def test_a_successful_command_between_repeats_counts_as_a_change():
    from unwedge.turns import ToolClass as TC

    screenshot = "mcp__preview__screenshot {\"serverId\": \"s1\"}"
    scroll = make_turn(2, "mcp__preview__eval {\"expression\": \"scrollBy(0, 800)\"}", "ok")
    assert scroll.tool_class is TC.RUN and not scroll.is_error
    turns = [make_turn(1, screenshot, "[image]"), scroll, make_turn(3, screenshot, "[image]")]
    assert compute_signals(turns)[2].repeat_without_change == 0 and compute_signals(turns)[2].exact_repeats == 1
    failing = [make_turn(1, "python a.py", "ValueError: x"), make_turn(2, "python b.py", "KeyError: y"),
               make_turn(3, "python a.py", "ValueError: x")]
    assert compute_signals(failing)[2].repeat_without_change == 1  # a failed command changed nothing


def test_back_to_back_identical_successful_commands_still_accumulate():
    turns = [make_turn(i, "python reproduce.py", "same output") for i in range(1, 6)]
    assert compute_signals(turns)[4].repeat_without_change == 4
