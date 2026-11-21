"""Unit tests for the pure cost-discipline helpers (no network, no LLM)."""

from __future__ import annotations

from misfire.log_utils import truncate_logs


def test_truncate_returns_short_logs_unchanged() -> None:
    logs = "line 1\nline 2\nline 3"
    assert truncate_logs(logs, tail_lines=200) == logs


def test_truncate_keeps_the_failing_tail() -> None:
    logs = "\n".join(f"line {i}" for i in range(1000))
    out = truncate_logs(logs, tail_lines=10)
    assert "line 999" in out          # tail preserved
    assert "line 500" not in out      # bulk dropped
    assert "truncated" in out         # elision marker present


def test_truncate_preserves_first_error_block_from_head() -> None:
    # The originating error sits near the top; the tail is unrelated noise.
    head = ["setup ok"] * 50
    head[10] = "E   AssertionError: boom in auth.py:42"
    tail = [f"teardown {i}" for i in range(20)]
    logs = "\n".join(head + tail)

    out = truncate_logs(logs, tail_lines=20)
    assert "E   AssertionError: boom in auth.py:42" in out  # error rescued from head
    assert "teardown 19" in out                             # tail still present
    # Head noise before the error is dropped.
    assert out.count("setup ok") < 50


def test_truncate_tail_only_when_no_error_in_head() -> None:
    logs = "\n".join(f"noise {i}" for i in range(500))
    out = truncate_logs(logs, tail_lines=5)
    lines = out.splitlines()
    assert lines[0].startswith("...")   # leading truncation marker
    assert lines[-1] == "noise 499"
