"""Agent-loop guardrails: turn cap + token budget (Item 4).

A misbehaving model could call tools forever; these prove `claude.run` stops
gracefully at the turn cap and the token budget, returning a clear message
instead of looping (and without posting).
"""

from __future__ import annotations

from misfire import tools
from misfire.agents import claude
from misfire.testkit import ScriptedAnthropic, final, tool_use


class _LogsOnlyClient:
    """Serves logs so get_failing_logs dispatch works; never posts."""

    def fetch_failing_logs(self, run_id: int) -> str:
        return "boom\n"

    def upsert_pr_comment(  # pragma: no cover
        self, pr_number: int, body: str, *, marker: str
    ) -> str:
        raise AssertionError("should not post when a limit is hit before posting")


def _bind() -> None:
    tools.bind(_LogsOnlyClient())


def test_stops_at_max_turns_without_posting() -> None:
    _bind()
    # The model keeps asking for a tool and never concludes.
    script = [tool_use("get_failing_logs", {"run_id": 1}, id=f"t{i}") for i in range(10)]
    anthropic_client = ScriptedAnthropic(script)

    body = claude.run(1, 7, _LogsOnlyClient(), anthropic_client=anthropic_client, max_turns=3)

    assert anthropic_client.messages.calls == 3  # capped, not 10
    assert "3-turn" in body
    assert "no advisory was posted" in body


def test_stops_at_token_budget_without_posting() -> None:
    _bind()
    # Each turn reports 100k tokens; a 150k budget allows two calls then stops.
    script = [
        tool_use("get_failing_logs", {"run_id": 1}, id=f"t{i}", tokens=100_000)
        for i in range(10)
    ]
    anthropic_client = ScriptedAnthropic(script)

    body = claude.run(
        1, 7, _LogsOnlyClient(), anthropic_client=anthropic_client, token_budget=150_000
    )

    assert anthropic_client.messages.calls == 2
    assert "150000-token budget" in body
    assert "no advisory was posted" in body


def test_normal_run_within_limits_is_unaffected() -> None:
    _bind()
    # A well-behaved short run finishes normally well under the defaults.
    script = [
        tool_use("get_failing_logs", {"run_id": 1}, id="a", tokens=500),
        final("done", tokens=200),
    ]
    body = claude.run(1, 7, _LogsOnlyClient(), anthropic_client=ScriptedAnthropic(script))
    assert body == ""  # nothing posted, but it concluded on its own (no limit message)
