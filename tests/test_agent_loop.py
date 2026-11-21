"""Unit tests for the Claude agent loop's write-safety contract.

The core advisory promise is that `post_pr_comment` — the single write action —
fires **at most once** per run. These tests drive `claude.run` with a scripted
model (no network, no key) and a counting GitHub client to prove the loop
enforces that in code, not just in the structural suite.
"""

from __future__ import annotations

from misfire.agents import claude
from misfire.testkit import ScriptedAnthropic, final, tool_use


class CountingClient:
    """Records writes; get-methods are unused in these tests."""

    def __init__(self) -> None:
        self.posts: list[tuple[int, str]] = []

    def upsert_pr_comment(self, pr_number: int, body: str, *, marker: str) -> str:
        self.posts.append((pr_number, body))
        return f"https://github.com/x/y/pull/{pr_number}#issuecomment-1"


def _diagnosis(root_cause: str) -> dict:
    """Structured post_pr_comment args (no failing_test_id → no history lookup)."""
    return {"root_cause": root_cause, "category": "test_assertion", "confidence": 0.8}


def test_second_post_is_not_dispatched() -> None:
    client = CountingClient()
    script = [
        tool_use("post_pr_comment", _diagnosis("first cause"), id="a"),
        tool_use("post_pr_comment", _diagnosis("second cause"), id="b"),
        final("done"),
    ]
    body = claude.run(1, 7, client, anthropic_client=ScriptedAnthropic(script))

    # Only the first post reaches GitHub; the duplicate is refused.
    assert len(client.posts) == 1
    pr_number, posted = client.posts[0]
    assert pr_number == 7
    assert "first cause" in posted  # rendered body, not the raw arg
    assert "second cause" not in posted
    # The returned body is the rendered comment that was actually posted.
    assert body == posted


def test_unknown_tool_does_not_crash_the_loop() -> None:
    client = CountingClient()
    script = [
        tool_use("bogus_tool", {"x": 1}, id="a"),  # not a real tool → KeyError in dispatch
        final("done"),
    ]
    body = claude.run(1, 7, client, anthropic_client=ScriptedAnthropic(script))
    assert client.posts == []  # nothing posted, and no exception propagated
    assert body == ""


def test_bad_tool_args_do_not_crash_the_loop() -> None:
    client = CountingClient()
    script = [
        tool_use("post_pr_comment", {}, id="a"),  # missing required args → TypeError
        final("done"),
    ]
    body = claude.run(1, 7, client, anthropic_client=ScriptedAnthropic(script))
    assert client.posts == []
    assert body == ""


def test_single_post_still_dispatches_normally() -> None:
    client = CountingClient()
    script = [
        tool_use("post_pr_comment", _diagnosis("only cause"), id="a"),
        final("done"),
    ]
    body = claude.run(1, 7, client, anthropic_client=ScriptedAnthropic(script))

    assert len(client.posts) == 1
    assert client.posts[0][0] == 7
    assert "only cause" in body
    assert body == client.posts[0][1]
