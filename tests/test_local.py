"""Local / offline analysis mode (`misfire analyze`).

Covers the deterministic `--no-ai` path (categorizer + summary, no model, no
network) and the local AI path (agent over a captured client, scripted model),
plus the CLI wiring for file and stdin input.
"""

from __future__ import annotations

import io

from misfire import cli, local
from misfire.schema import FailureCategory
from misfire.testkit import ScriptedAnthropic, final, tool_use

# --- deterministic categorizer ------------------------------------------------

def test_categorize_rules() -> None:
    cases = [
        ("E   AssertionError: expected 1 got 2", FailureCategory.TEST_ASSERTION),
        ("ModuleNotFoundError: No module named 'foo'", FailureCategory.DEPENDENCY),
        ("SyntaxError: invalid syntax", FailureCategory.COMPILE_ERROR),
        ("E TimeoutError: timed out after 5s", FailureCategory.TIMEOUT),
        ("curl: (7) Connection refused", FailureCategory.INFRASTRUCTURE),
        ("everything was fine, exit 0", FailureCategory.UNKNOWN),
    ]
    for text, expected in cases:
        assert local.categorize(text) is expected, text


def test_summarize_is_deterministic_and_scrubs() -> None:
    logs = (
        "GITHUB_TOKEN=ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789\n"
        "tests/test_auth.py:42: AssertionError: expected 'active' got 'pending'\n"
    )
    out = local.summarize(logs)
    assert out == local.summarize(logs)  # deterministic
    assert "`test_assertion`" in out
    assert "tests/test_auth.py:42" in out
    assert "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789" not in out  # scrubbed
    assert "no AI" in out


# --- local AI path (scripted model, captured client, no network) --------------

def test_analyze_with_ai_captures_rendered_advisory() -> None:
    script = [
        tool_use("get_failing_logs", {"run_id": 0}, id="a"),
        tool_use("get_pr_diff", {"pr_number": 0}, id="b"),
        tool_use(
            "post_pr_comment",
            {
                "root_cause": "auth.py:42 flipped 'active' to 'pending'.",
                "category": "test_assertion",
                "confidence": 0.9,
            },
            id="c",
        ),
        final("done"),
    ]
    body = local.analyze_with_ai(
        "boom", diff="--- a\n+++ b\n", anthropic_client=ScriptedAnthropic(script)
    )
    assert "**Root cause:** auth.py:42 flipped" in body
    assert local.MARKER in body  # rendered advisory, not posted anywhere


def test_analyze_with_ai_handles_no_post() -> None:
    body = local.analyze_with_ai("boom", anthropic_client=ScriptedAnthropic([final("nothing")]))
    assert "nothing actionable" in body


# --- CLI wiring ---------------------------------------------------------------

def test_cli_analyze_no_ai_from_file(tmp_path, capsys) -> None:
    log = tmp_path / "ci.log"
    log.write_text("ModuleNotFoundError: No module named 'requests'\n")
    assert cli.main(["analyze", "--logs", str(log), "--no-ai"]) == 0
    out = capsys.readouterr().out
    assert "`dependency`" in out
    assert "No module named 'requests'" in out


def test_cli_analyze_no_ai_from_stdin(monkeypatch, capsys) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("E AssertionError: nope\n"))
    assert cli.main(["analyze", "--logs", "-", "--no-ai"]) == 0
    assert "`test_assertion`" in capsys.readouterr().out
